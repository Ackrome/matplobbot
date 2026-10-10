"""Pure, strict parsing of public MyPrepod Financial University HTML pages."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

SOURCE_ORIGIN = "https://myprepod.ru"
CATALOGUE_URL = f"{SOURCE_ORIGIN}/universiteti/fa/prepodavateli"
UNIVERSITY_NAME = "Финансовый университет"
MAX_HTML_BYTES = 2 * 1024 * 1024
MAX_COUNT = 2_147_483_647
_PROFILE_PATH = re.compile(r"/fa/[a-z0-9]+(?:-[a-z0-9]+)*-[1-9][0-9]{0,11}")
_NAME_PART = re.compile(r"[а-яё]{2,}(?:-[а-яё]{2,})*", re.IGNORECASE)
_UNIVERSITY_NAMES = {
    "финансовый университет",
    "финансовый университет при правительстве российской федерации",
}


class SourceParseError(ValueError):
    """The page cannot establish the expected source identity or valid data."""


class AmbiguousTeacherError(SourceParseError):
    """Multiple conflicting structured identities describe the requested teacher."""


class UnsafeSourceUrl(ValueError):
    """A URL is outside the fixed public Financial University source routes."""


@dataclass(frozen=True, slots=True)
class TeacherCandidate:
    name: str
    url: str


@dataclass(frozen=True, slots=True)
class CatalogueResult:
    candidates: tuple[TeacherCandidate, ...]
    observed_urls: tuple[str, ...]
    next_urls: tuple[str, ...]
    total_found: int | None
    search_complete: bool
    ambiguous: bool


@dataclass(frozen=True, slots=True)
class TeacherRatingProfile:
    name: str
    url: str
    department: str | None
    rating_percent: float | None
    vote_count: int | None
    review_count: int | None


def display_teacher_name(value: str) -> str:
    """Collapse separators without inventing missing name components."""
    return " ".join(value.replace("_", " ").split()) if isinstance(value, str) else ""


def normalize_teacher_name(value: str) -> str:
    """Canonical exact comparison; do not reorder names or expand initials."""
    return display_teacher_name(value).casefold().replace("ё", "е")


def is_full_teacher_name(value: str) -> bool:
    """Support one complete Cyrillic surname/given-name/patronymic identity."""
    name = display_teacher_name(value)
    parts = name.split()
    return len(name) <= 200 and len(parts) == 3 and all(_NAME_PART.fullmatch(p) for p in parts)


def validate_source_url(url: str, *, profile_only: bool = False) -> str:
    """Validate every request and redirect before HTTP; no arbitrary source URLs."""
    if not isinstance(url, str) or len(url) > 2048 or any(ord(c) <= 32 for c in url):
        raise UnsafeSourceUrl("Invalid source URL")
    try:
        parts = urlsplit(url)
    except ValueError as exc:
        raise UnsafeSourceUrl("Invalid source URL") from exc
    if (
        parts.scheme != "https"
        or parts.netloc != "myprepod.ru"
        or parts.fragment
        or "\\" in url
        or "%" in parts.path
    ):
        raise UnsafeSourceUrl("Source URL must use the fixed HTTPS host")
    if _PROFILE_PATH.fullmatch(parts.path):
        if parts.query:
            raise UnsafeSourceUrl("Profile URLs cannot contain query parameters")
        return SOURCE_ORIGIN + parts.path
    if profile_only or parts.path != "/universiteti/fa/prepodavateli":
        raise UnsafeSourceUrl("Unsupported source path")
    try:
        query = parse_qsl(parts.query, keep_blank_values=True, strict_parsing=True)
    except ValueError as exc:
        raise UnsafeSourceUrl("Invalid catalogue query") from exc
    values = dict(query)
    if len(values) != len(query) or not set(values) <= {"q", "page"}:
        raise UnsafeSourceUrl("Unsupported catalogue query")
    if "q" in values and (not is_full_teacher_name(values["q"])):
        raise UnsafeSourceUrl("Catalogue search requires a supported full name")
    if "page" in values and not re.fullmatch(r"[1-9][0-9]{0,3}", values["page"]):
        raise UnsafeSourceUrl("Invalid catalogue page")
    ordered = [(key, values[key]) for key in ("q", "page") if key in values]
    return urlunsplit(("https", "myprepod.ru", parts.path, urlencode(ordered), ""))


def build_catalogue_url(name: str, page: int = 1) -> str:
    """The observed public catalogue uses GET q=<full name> and optional page."""
    if not is_full_teacher_name(name):
        raise SourceParseError("A complete Cyrillic teacher name is required")
    if isinstance(page, bool) or not isinstance(page, int) or not 1 <= page <= 9999:
        raise SourceParseError("Invalid catalogue page")
    query: dict[str, str | int] = {"q": display_teacher_name(name)}
    if page != 1:
        query["page"] = page
    return CATALOGUE_URL + "?" + urlencode(query)


def _internal_url(value: str, source_url: str, *, profile_only: bool = False) -> str:
    if value.startswith("/") and not value.startswith("//"):
        value = urljoin(source_url, value)
    elif value.startswith("?"):
        value = urljoin(source_url, value)
    return validate_source_url(value, profile_only=profile_only)


def _json(text: str):
    def reject_constant(value):
        raise ValueError("Non-finite JSON number")

    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON field")
            result[key] = value
        return result

    try:
        return json.loads(text, parse_constant=reject_constant, object_pairs_hook=unique_object)
    except (ValueError, RecursionError) as exc:
        raise SourceParseError("Invalid source structured data") from exc


class _PageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.catalogue_configs: list[dict] = []
        self.cards: list[dict] = []
        self.links: list[tuple[str, str]] = []
        self.structured: list[str] = []
        self._card: dict | None = None
        self._heading = False
        self._script: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "data-tutor-catalog" in attrs:
            config = _json(attrs.get("data-config") or "null")
            if not isinstance(config, dict):
                raise SourceParseError("Invalid catalogue configuration")
            self.catalogue_configs.append(config)
        if tag in {"a", "link"} and attrs.get("href"):
            self.links.append((attrs["href"], attrs.get("rel", "")))
        if tag == "a":
            self._card = {"url": attrs.get("href", ""), "title": attrs.get("title"), "heading": []}
        elif tag == "h3" and self._card is not None:
            self._heading = True
        elif tag == "script" and attrs.get("type", "").lower() == "application/ld+json":
            self._script = []

    def handle_endtag(self, tag):
        if tag == "a" and self._card is not None:
            if self._card["heading"]:
                self.cards.append(self._card)
            self._card = None
            self._heading = False
        elif tag == "h3":
            self._heading = False
        elif tag == "script" and self._script is not None:
            self.structured.append("".join(self._script))
            self._script = None

    def handle_data(self, data):
        if self._script is not None:
            self._script.append(data)
        elif self._heading and self._card is not None:
            self._card["heading"].append(data)


def _page(html: str) -> _PageParser:
    if not isinstance(html, str) or len(html.encode("utf-8")) > MAX_HTML_BYTES:
        raise SourceParseError("Source HTML exceeds the size bound")
    parser = _PageParser()
    try:
        parser.feed(html)
        parser.close()
    except (RecursionError, AssertionError) as exc:
        raise SourceParseError("Malformed source HTML") from exc
    return parser


def _count(value, *, optional: bool = True) -> int | None:
    if value is None and optional:
        return None
    if isinstance(value, str) and re.fullmatch(r"[0-9]{1,10}", value):
        value = int(value)
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= MAX_COUNT:
        raise SourceParseError("Source count must be a bounded nonnegative integer")
    return value


def parse_catalogue(
    html: str, expected_name: str, source_url: str | None = None
) -> CatalogueResult:
    """Return exact candidates; callers must exhaust pagination before matching."""
    if not is_full_teacher_name(expected_name):
        raise SourceParseError("A complete Cyrillic teacher name is required")
    source_url = validate_source_url(source_url or build_catalogue_url(expected_name))
    request = urlsplit(source_url)
    if request.path != urlsplit(CATALOGUE_URL).path:
        raise SourceParseError("Expected the university catalogue")
    query = dict(parse_qsl(request.query))
    expected = normalize_teacher_name(expected_name)
    if normalize_teacher_name(query.get("q", "")) != expected:
        raise SourceParseError("Catalogue query does not match the requested teacher")
    page = _page(html)
    if len(page.catalogue_configs) != 1:
        raise SourceParseError("Missing or ambiguous catalogue structure")
    config = page.catalogue_configs[0]
    state = config.get("state")
    if (
        config.get("baseUrl") != CATALOGUE_URL
        or not isinstance(state, dict)
        or normalize_teacher_name(state.get("q", "")) != expected
        or state.get("dep", "")
        or state.get("reviews", False) is not False
    ):
        raise SourceParseError("Source catalogue changed the requested identity or filters")
    total = _count(config.get("found"), optional=False)
    if total is None:  # Required above; keep the public optional-count type honest.
        raise SourceParseError("Missing catalogue count")
    candidates: dict[str, TeacherCandidate] = {}
    seen_cards: dict[str, str] = {}
    for card in page.cards:
        name = display_teacher_name("".join(card["heading"]))
        if not is_full_teacher_name(name):
            continue
        try:
            url = _internal_url(card["url"], source_url, profile_only=True)
        except UnsafeSourceUrl:
            if normalize_teacher_name(name) == expected:
                raise SourceParseError("Exact-name candidate has an unsafe profile URL") from None
            continue
        canonical = normalize_teacher_name(name)
        if url in seen_cards and seen_cards[url] != canonical:
            raise SourceParseError("One profile URL has conflicting catalogue names")
        seen_cards[url] = canonical
        if normalize_teacher_name(name) != expected:
            continue
        title = card["title"]
        if title and normalize_teacher_name(title.removesuffix(" — отзывы студентов")) != expected:
            raise SourceParseError("Candidate heading and title disagree")
        candidates[url] = TeacherCandidate(name=name, url=url)
    current_page = int(query.get("page", "1"))
    next_urls: dict[int, str] = {}
    for href, rel in page.links:
        try:
            url = _internal_url(href, source_url)
        except UnsafeSourceUrl:
            if "next" in rel.split():
                raise SourceParseError("Unsafe catalogue pagination URL") from None
            continue
        parsed = urlsplit(url)
        if parsed.path != request.path:
            if "next" in rel.split():
                raise SourceParseError("Pagination left the university catalogue")
            continue
        values = dict(parse_qsl(parsed.query))
        if "page" not in values:
            if "next" in rel.split():
                raise SourceParseError("Pagination did not identify a later page")
            continue
        number = int(values["page"])
        if "next" in rel.split() and number <= current_page:
            raise SourceParseError("Pagination did not identify a later page")
        if number > current_page:
            if normalize_teacher_name(values.get("q", "")) != expected:
                raise SourceParseError("Pagination changed the requested teacher")
            next_urls[number] = url
    # A changed/empty page must not establish a false negative or unique match.
    complete = not next_urls and (total == 0 or bool(seen_cards))
    if current_page == 1 and total > len(seen_cards):
        complete = False
    if total == 0 and seen_cards:
        raise SourceParseError("Catalogue result count contradicts its cards")
    return CatalogueResult(
        candidates=tuple(candidates.values()),
        observed_urls=tuple(seen_cards),
        next_urls=tuple(next_urls[n] for n in sorted(next_urls)),
        total_found=total,
        search_complete=complete,
        ambiguous=len(candidates) > 1,
    )


def _entities(value):
    """Only schema roots/@graph nodes; never review authors or nearby aggregates."""
    pending = [value]
    visited = 0
    while pending:
        current = pending.pop()
        visited += 1
        if visited > 2048:
            raise SourceParseError("Structured data has too many entities")
        if isinstance(current, list):
            pending.extend(reversed(current))
        elif isinstance(current, dict):
            yield current
            if isinstance(current.get("@graph"), list):
                pending.extend(reversed(current["@graph"]))


def _has_type(value: dict, expected: str) -> bool:
    types = value.get("@type")
    return types == expected or (isinstance(types, list) and expected in types)


def _university_matches(entity: dict) -> bool:
    # MyPrepod currently represents a teacher as Organization with this parent.
    for key in ("parentOrganization", "worksFor", "affiliation"):
        university = entity.get(key)
        if not isinstance(university, dict) or not _has_type(university, "CollegeOrUniversity"):
            continue
        if (
            normalize_teacher_name(university.get("name", "")) in _UNIVERSITY_NAMES
            and university.get("url") == CATALOGUE_URL
        ):
            return True
    return False


def _number(value) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise SourceParseError("Invalid source rating")
    try:
        number = float(value)
    except (ValueError, OverflowError) as exc:
        raise SourceParseError("Invalid source rating") from exc
    if not math.isfinite(number) or not 0 <= number <= 100:
        raise SourceParseError("Source rating is outside its native 0–100 scale")
    return number


def parse_profile(html: str, expected_name: str, source_url: str) -> TeacherRatingProfile:
    """Bind the native aggregate to the exact teacher, profile and university."""
    if not is_full_teacher_name(expected_name):
        raise SourceParseError("A complete Cyrillic teacher name is required")
    source_url = validate_source_url(source_url, profile_only=True)
    expected = normalize_teacher_name(expected_name)
    matches: list[TeacherRatingProfile] = []
    for text in _page(html).structured:
        for entity in _entities(_json(text)):
            if not (_has_type(entity, "Person") or _has_type(entity, "Organization")):
                continue
            if normalize_teacher_name(entity.get("name", "")) != expected:
                continue
            if not _university_matches(entity):
                continue
            try:
                identity_url = validate_source_url(entity.get("url"), profile_only=True)
            except UnsafeSourceUrl as exc:
                raise SourceParseError("Teacher structured data has an unsafe URL") from exc
            if identity_url != source_url:
                raise AmbiguousTeacherError(
                    "Teacher structured data identifies a different profile"
                )
            aggregate = entity.get("aggregateRating")
            rating = votes = reviews = None
            if aggregate is not None:
                if not isinstance(aggregate, dict) or not _has_type(aggregate, "AggregateRating"):
                    raise SourceParseError("Invalid teacher aggregate")
                votes = _count(aggregate.get("ratingCount"))
                reviews = _count(aggregate.get("reviewCount"))
                if aggregate.get("ratingValue") is not None:
                    if (
                        _number(aggregate.get("bestRating")) != 100
                        or _number(aggregate.get("worstRating")) != 0
                    ):
                        raise SourceParseError("Unsupported source rating scale")
                    rating = _number(aggregate["ratingValue"])
                    if votes == 0:
                        rating = None
            department = entity.get("knowsAbout")
            if not isinstance(department, str) or not department.strip():
                department = None
            elif len(department) > 300:
                raise SourceParseError("Source department is too long")
            else:
                department = " ".join(department.split())
            result = TeacherRatingProfile(
                name=display_teacher_name(entity["name"]),
                url=source_url,
                department=department,
                rating_percent=rating,
                vote_count=votes,
                review_count=reviews,
            )
            if result not in matches:
                matches.append(result)
    if len(matches) > 1:
        raise AmbiguousTeacherError("Conflicting teacher profile aggregates")
    if not matches:
        raise SourceParseError("No exact teacher profile at the requested university")
    return matches[0]
