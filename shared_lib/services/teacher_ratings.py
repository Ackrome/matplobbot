"""Durable exact-name teacher ratings with bounded public-HTML source access."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import uuid
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urljoin, urlsplit

import aiohttp
from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from shared_lib.database import get_session
from shared_lib.egress import get_global_http_proxy_url
from shared_lib.models import TeacherRatingCache
from shared_lib.services import teacher_rating_source as source

logger = logging.getLogger(__name__)

UNIVERSITY_KEY = "fa"
CACHE_TTL = timedelta(hours=24)
FAILURE_BACKOFF = timedelta(minutes=5)
REFRESH_LEASE = timedelta(seconds=60)
LOOKUP_TIMEOUT_SECONDS = 20
INITIAL_WAIT_SECONDS = 22
MAX_REFRESH_TASKS = 32
MAX_CATALOGUE_PAGES = 3
MAX_HTTP_REQUESTS = 10
HTTP_TIMEOUT_SECONDS = 4
HTTP_START_INTERVAL_SECONDS = 1.0


class TeacherSourceUnavailable(RuntimeError):
    """The source could not be completely verified within the bounded budget."""


def _utc(value):
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def teacher_identity(name: str) -> tuple[str, str]:
    """Stable identity deliberately excludes semester-specific RUZ person IDs."""
    canonical = source.normalize_teacher_name(name)
    digest = hashlib.sha256(f"myprepod:{UNIVERSITY_KEY}\0{canonical}".encode()).hexdigest()
    return digest, canonical


def _snapshot(row):
    if row is None:
        return None
    return {
        "status": row.status,
        "profile": dict(row.profile) if row.profile else None,
        "checked_at": _utc(row.checked_at),
        "next_check_at": _utc(row.next_check_at),
        "last_error": row.last_error,
    }


class TeacherRatingsService:
    """One API-lifespan service; DB leases also coalesce across API processes."""

    def __init__(self, http_session, *, session_factory=None):
        self.http_session = http_session
        self._sessions = session_factory or get_session
        self._tasks: dict[str, asyncio.Task] = {}
        self._http_slots = asyncio.Semaphore(2)
        self._http_start_lock = asyncio.Lock()
        self._last_http_start = 0.0
        self._closed = False

    async def close(self):
        """Cancel refreshes before the shared HTTP session and DB pool close."""
        self._closed = True
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()

    async def _read(self, key):
        async with self._sessions() as session:
            row = (
                await session.execute(
                    select(TeacherRatingCache).where(TeacherRatingCache.identity_key == key)
                )
            ).scalar_one_or_none()
            return _snapshot(row)

    async def _claim(self, key, canonical):
        now = datetime.now(UTC)
        async with self._sessions() as session:
            exists = (
                await session.execute(
                    select(TeacherRatingCache.identity_key).where(
                        TeacherRatingCache.identity_key == key
                    )
                )
            ).scalar_one_or_none()
            if exists is None:
                session.add(
                    TeacherRatingCache(
                        identity_key=key,
                        university_key=UNIVERSITY_KEY,
                        canonical_name=canonical,
                        status="unavailable",
                        provenance={},
                        next_check_at=now,
                    )
                )
                try:
                    await session.commit()
                except IntegrityError:
                    # A concurrent insert owns the same canonical identity.
                    await session.rollback()
            token = str(uuid.uuid4())
            result = await session.execute(
                update(TeacherRatingCache)
                .where(
                    TeacherRatingCache.identity_key == key,
                    TeacherRatingCache.next_check_at <= now,
                    or_(
                        TeacherRatingCache.refresh_started_at.is_(None),
                        TeacherRatingCache.refresh_started_at < now - REFRESH_LEASE,
                    ),
                )
                .values(refresh_token=token, refresh_started_at=now, last_attempt_at=now)
                .returning(TeacherRatingCache.refresh_token)
            )
            acquired = result.scalar_one_or_none()
            await session.commit()
            return acquired

    async def _publish(self, key, token, status, profile, provenance):
        now = datetime.now(UTC)
        values: dict[str, object] = {"refresh_token": None, "refresh_started_at": None}
        if status == "unavailable":
            # Preserve the prior successful snapshot and its retrieval time.
            values.update(next_check_at=now + FAILURE_BACKOFF, last_error="source_unavailable")
        else:
            values.update(
                status=status,
                profile=profile,
                provenance=provenance,
                checked_at=now,
                next_check_at=now + CACHE_TTL,
                last_error=None,
            )
        async with self._sessions() as session:
            result = await session.execute(
                update(TeacherRatingCache)
                .where(
                    TeacherRatingCache.identity_key == key,
                    TeacherRatingCache.refresh_token == token,
                )
                .values(**values)
            )
            await session.commit()
            return result.rowcount == 1

    async def _release(self, key, token):
        async with self._sessions() as session:
            await session.execute(
                update(TeacherRatingCache)
                .where(
                    TeacherRatingCache.identity_key == key,
                    TeacherRatingCache.refresh_token == token,
                )
                .values(refresh_token=None, refresh_started_at=None)
            )
            await session.commit()

    def _response(self, name, snapshot=None):
        checked = snapshot["checked_at"] if snapshot else None
        stale = bool(
            checked and (datetime.now(UTC) >= checked + CACHE_TTL or snapshot.get("last_error"))
        )
        return {
            "query_name": name,
            "status": snapshot["status"] if snapshot else "unavailable",
            "profile": snapshot["profile"] if snapshot else None,
            "checked_at": checked,
            "stale": stale,
        }

    async def get(self, name: str) -> dict:
        """Serve fresh/stale cache immediately; wait only for an uncached first lookup."""
        display = source.display_teacher_name(name)
        if not source.is_full_teacher_name(display):
            return {**self._response(display), "status": "unsupported"}
        key, canonical = teacher_identity(display)
        try:
            snapshot = await self._read(key)
        except (SQLAlchemyError, ConnectionError):
            logger.warning("Teacher rating cache unavailable")
            return self._response(display)
        now = datetime.now(UTC)
        if snapshot and snapshot["next_check_at"] > now:
            return self._response(display, snapshot)
        task = self._tasks.get(key)
        if task is None and not self._closed and len(self._tasks) < MAX_REFRESH_TASKS:
            task = asyncio.create_task(self._refresh(key, canonical, display))
            self._tasks[key] = task
            task.add_done_callback(lambda completed: self._forget(key, completed))
        if snapshot and snapshot["checked_at"] is not None:
            return self._response(display, snapshot)
        if task is not None:
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=INITIAL_WAIT_SECONDS)
                snapshot = await self._read(key)
            except (TimeoutError, SQLAlchemyError, ConnectionError):
                pass
        return self._response(display, snapshot)

    def _forget(self, key, task):
        if self._tasks.get(key) is task:
            self._tasks.pop(key, None)
        if not task.cancelled():
            task.exception()

    async def _refresh(self, key, canonical, display):
        token = None
        try:
            token = await self._claim(key, canonical)
            if token is None:
                return
            try:
                async with asyncio.timeout(LOOKUP_TIMEOUT_SECONDS):
                    status, profile, provenance = await self._lookup_live(display)
            except source.AmbiguousTeacherError:
                status, profile, provenance = "ambiguous", None, {}
            except Exception as exc:
                # Source/transport failures must not discard a verified snapshot.
                # Cancellation is BaseException and still propagates to shutdown.
                status, profile, provenance = "unavailable", None, {}
                logger.warning("Teacher rating source lookup unavailable (%s)", type(exc).__name__)
            await self._publish(key, token, status, profile, provenance)
        except (SQLAlchemyError, ConnectionError):
            logger.warning("Teacher rating refresh persistence unavailable")
        finally:
            if token is not None:
                try:
                    await self._release(key, token)
                except (SQLAlchemyError, ConnectionError):
                    logger.warning("Teacher rating refresh lease release unavailable")

    @staticmethod
    def _validate_request_url(url, expected_name, *, profile_url=None, catalogue_url=None):
        validated = source.validate_source_url(url, profile_only=profile_url is not None)
        parts = urlsplit(validated)
        if profile_url is None:
            query = parse_qs(parts.query)
            if parts.path != urlsplit(source.CATALOGUE_URL).path or source.normalize_teacher_name(
                query.get("q", [""])[0]
            ) != source.normalize_teacher_name(expected_name):
                raise TeacherSourceUnavailable("Catalogue redirect changed the query")
            if catalogue_url is not None:
                original = parse_qs(urlsplit(catalogue_url).query)
                if query.get("page", ["1"]) != original.get("page", ["1"]):
                    raise TeacherSourceUnavailable("Catalogue redirect changed the page")
        elif parts.path.rsplit("-", 1)[-1] != urlsplit(profile_url).path.rsplit("-", 1)[-1]:
            raise TeacherSourceUnavailable("Profile redirect changed the person identifier")
        return validated

    async def _fetch_html(self, url, name, budget, *, profile=False):
        original_profile = url if profile else None
        initial = self._validate_request_url(url, name, profile_url=original_profile)
        for attempt in range(2):
            current = initial
            try:
                for redirect in range(3):
                    if budget[0] >= MAX_HTTP_REQUESTS:
                        raise TeacherSourceUnavailable("HTTP request budget exhausted")
                    budget[0] += 1
                    async with self._http_slots:
                        async with self._http_start_lock:
                            clock = asyncio.get_running_loop().time
                            delay = self._last_http_start + HTTP_START_INTERVAL_SECONDS - clock()
                            if delay > 0:
                                await asyncio.sleep(delay)
                            self._last_http_start = clock()
                        async with self.http_session.get(
                            current,
                            allow_redirects=False,
                            auto_decompress=False,
                            timeout=aiohttp.ClientTimeout(
                                total=HTTP_TIMEOUT_SECONDS, sock_connect=3
                            ),
                            proxy=get_global_http_proxy_url(),
                            headers={
                                "Accept": "text/html,application/xhtml+xml",
                                "Accept-Encoding": "identity",
                                "User-Agent": "Matplobbot-TeacherRatings/1.0",
                            },
                        ) as response:
                            if response.status in {301, 302, 303, 307, 308}:
                                location = response.headers.get("Location")
                                if not location or redirect == 2:
                                    raise TeacherSourceUnavailable("Redirect limit exceeded")
                                current = self._validate_request_url(
                                    urljoin(current, location),
                                    name,
                                    profile_url=original_profile,
                                    catalogue_url=None if profile else initial,
                                )
                                continue
                            if response.status >= 500 and attempt == 0:
                                break
                            if response.status != 200:
                                raise TeacherSourceUnavailable("Source HTTP request failed")
                            content_type = response.headers.get("Content-Type", "").split(";")[0]
                            if content_type.lower() not in {"text/html", "application/xhtml+xml"}:
                                raise TeacherSourceUnavailable("Source response is not HTML")
                            if (
                                response.headers.get("Content-Encoding", "identity").lower()
                                != "identity"
                            ):
                                raise TeacherSourceUnavailable("Unexpected content encoding")
                            if (
                                response.content_length
                                and response.content_length > source.MAX_HTML_BYTES
                            ):
                                raise TeacherSourceUnavailable("HTML size limit exceeded")
                            data = bytearray()
                            async for chunk in response.content.iter_chunked(32 * 1024):
                                data.extend(chunk)
                                if len(data) > source.MAX_HTML_BYTES:
                                    raise TeacherSourceUnavailable("HTML size limit exceeded")
                            return bytes(data).decode("utf-8"), current
            except (aiohttp.ClientError, TimeoutError):
                if attempt:
                    raise
        raise TeacherSourceUnavailable("Source retry budget exhausted")

    async def _lookup_live(self, name):
        first = source.build_catalogue_url(name)
        queue = [first]
        visited: set[str] = set()
        candidates = {}
        observed_urls: set[str] = set()
        total_found = None
        budget = [0]
        while queue:
            if len(visited) >= MAX_CATALOGUE_PAGES:
                raise TeacherSourceUnavailable("Filtered catalogue is incomplete")
            url = queue.pop(0)
            if url in visited:
                continue
            visited.add(url)
            html, final_url = await self._fetch_html(url, name, budget)
            page = source.parse_catalogue(html, name, final_url)
            for candidate in page.candidates:
                candidates[candidate.url] = candidate
            if page.ambiguous or len(candidates) > 1:
                return "ambiguous", None, {"catalogue_url": first, "university_key": UNIVERSITY_KEY}
            if page.total_found is None or (
                total_found is not None and total_found != page.total_found
            ):
                raise TeacherSourceUnavailable("Filtered catalogue result count changed")
            total_found = page.total_found
            if observed_urls.intersection(page.observed_urls):
                raise TeacherSourceUnavailable("Filtered catalogue repeated profile cards")
            observed_urls.update(page.observed_urls)
            if len(observed_urls) > total_found:
                raise TeacherSourceUnavailable("Filtered catalogue exceeds its result count")
            if not page.search_complete and not page.next_urls:
                raise TeacherSourceUnavailable("Filtered catalogue completeness is unknown")
            for next_url in page.next_urls:
                next_url = self._validate_request_url(next_url, name)
                if next_url not in visited and next_url not in queue:
                    queue.append(next_url)
        if len(observed_urls) != total_found:
            raise TeacherSourceUnavailable("Filtered catalogue omitted profile cards")
        provenance = {
            "source": "myprepod",
            "university_key": UNIVERSITY_KEY,
            "catalogue_url": first,
            "catalogue_pages": len(visited),
            "catalogue_results_observed": len(observed_urls),
            "identity_method": "exact_full_name_and_university",
        }
        if not candidates:
            return "not_found", None, provenance
        candidate = next(iter(candidates.values()))
        html, final_url = await self._fetch_html(candidate.url, name, budget, profile=True)
        profile = source.parse_profile(html, name, final_url)
        provenance["profile_url"] = profile.url
        return "matched", asdict(profile), provenance
