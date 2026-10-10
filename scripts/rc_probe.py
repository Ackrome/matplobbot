"""Run real API/DB/queue journeys inside an isolated RC network (synthetic data)."""

import argparse
import asyncio
import base64
import hashlib
import hmac
import json
import os
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

STATE = Path("/tmp/matplobbot-rc-state.json")
API = "http://api:9583/api"


def request(method, path, payload=None, token=None, expected=200, raw=False):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    body = json.dumps(payload).encode() if payload is not None else None
    try:
        with urlopen(
            Request(API + path, data=body, headers=headers, method=method), timeout=45
        ) as response:
            status, content = response.status, response.read()
    except HTTPError as error:
        status, content = error.code, error.read()
    if status != expected:
        raise AssertionError(
            f"{method} {path.split('?')[0]} returned {status}, expected {expected}: {content[:300]!r}"
        )
    return content if raw else json.loads(content) if content else None


def login(user_id):
    data = {
        "id": user_id,
        "first_name": "RC Student",
        "username": f"rc{user_id}",
        "auth_date": int(time.time()),
    }
    secret = hashlib.sha256(os.environ["BOT_TOKEN"].encode()).digest()
    signed = "\n".join(f"{key}={value}" for key, value in sorted(data.items()))
    data["hash"] = hmac.new(secret, signed.encode(), hashlib.sha256).hexdigest()
    return request("POST", "/auth/telegram", data)["access_token"]


async def seed_schedule():
    from shared_lib.database import close_db_pool, get_session, init_db_pool
    from shared_lib.models import CachedSchedule

    await init_db_pool()
    today = datetime.now(UTC).date().isoformat()
    async with get_session() as session:
        session.add(
            CachedSchedule(
                entity_type="group",
                entity_id="rc-group",
                entity_name="RC group",
                updated_at=datetime.now(UTC),
                schedule_data=[
                    {
                        "date": today,
                        "beginLesson": "10:10",
                        "endLesson": "11:40",
                        "discipline": "RC Physics",
                        "kindOfWork": "Лекция",
                        "auditorium": "101",
                        "lecturer": "RC Teacher",
                        "group": "RC group",
                        "subGroup": "",
                        "stream": "",
                    }
                ],
            )
        )
        await session.commit()
    await close_db_pool()


def prepare():
    first, other = login(910000001), login(910000002)
    asyncio.run(seed_schedule())
    content = r"\documentclass{article}\begin{document}RC persisted source\end{document}"
    project = request(
        "POST",
        "/studio/projects",
        {"name": "RC ownership", "project_type": "latex", "initial_content": content},
        first,
    )
    survivor = request(
        "POST",
        "/studio/projects",
        {"name": "RC preserved after restore", "project_type": "latex", "initial_content": content},
        other,
    )
    files = request("GET", f"/studio/projects/{project['id']}", token=first)
    request(
        "PUT",
        f"/studio/projects/{project['id']}/files/{files[0]['id']}",
        {"content": content + "\n% persisted"},
        first,
    )
    request("GET", f"/studio/projects/{project['id']}", token=other, expected=404)
    job = request("POST", f"/studio/projects/{project['id']}/jobs", token=first, expected=202)
    profile = request(
        "POST",
        "/cal/subscription/profiles",
        {"entity_type": "group", "entity_id": "rc-group", "entity_name": "RC group"},
        first,
    )
    STATE.write_text(
        json.dumps(
            {
                "token": first,
                "other": other,
                "project": project["id"],
                "job": job["job_id"],
                "profile": profile["selected_profile_id"],
                "survivor": survivor["id"],
            }
        ),
        encoding="utf-8",
    )
    STATE.chmod(0o600)


def result(job, token):
    for _ in range(180):
        response = request("GET", "/studio/jobs/" + job, token=token)
        if response["status"] in {"error", "cancelled"}:
            raise AssertionError(f"Real worker compile failed: {response}")
        if response["status"] == "success":
            return response["result"]
        time.sleep(1)
    raise AssertionError("Real Celery job did not finish within 180 seconds")


def verify():
    state = json.loads(STATE.read_text(encoding="utf-8"))
    token, other = state["token"], state["other"]
    files = request("GET", f"/studio/projects/{state['project']}", token=token)
    assert files[0]["content"].endswith("% persisted")
    payload = result(state["job"], token)
    assert base64.b64decode(payload["pdf"]).startswith(b"%PDF-")
    request("GET", "/studio/jobs/" + state["job"], token=other, expected=404)
    for kind, content, key, signature in (
        ("markdown", "# RC Markdown\n\nA real PDF.", "pdf", b"%PDF-"),
        ("mermaid", "graph TD; A[RC] --> B[Ready];", "image", b"\x89PNG"),
    ):
        job = request(
            "POST", "/studio/jobs", {"type": kind, "content": content}, token, expected=202
        )
        rendered = result(job["job_id"], token)
        encoded = rendered.get(key) or rendered.get("png")
        assert encoded and base64.b64decode(encoded).startswith(signature), (kind, list(rendered))
    profile = request("GET", "/cal/subscription", token=token)
    assert any(p["id"] == state["profile"] for p in profile["profiles"])
    url = profile["http_url"]
    from urllib.parse import urlsplit

    path = urlsplit(url).path.removeprefix("/api")
    feed = request("GET", path, raw=True)
    assert b"BEGIN:VCALENDAR" in feed and b"RC Physics" in feed
    request("PATCH", "/cal/subscription/profiles/" + state["profile"], {"timezone": "UTC"}, token)
    exported = request("GET", "/auth/account/export", token=token)
    assert any(p["name"] == "RC ownership" for p in exported["projects"])
    request(
        "DELETE",
        "/auth/account",
        {"confirmation": "DELETE", "export_token": exported["deletion_token"]},
        token,
    )
    request("GET", "/auth/me", token=token, expected=401)
    request("GET", "/auth/me", token=other)
    request("GET", f"/studio/projects/{state['survivor']}", token=other)
    concurrent = login(910000002)
    request("POST", "/auth/logout", token=other)
    request("GET", "/auth/me", token=other, expected=401)
    request("GET", "/auth/me", token=concurrent)
    request("POST", "/auth/logout-all", token=concurrent)
    request("GET", "/auth/me", token=concurrent, expected=401)
    fresh = login(910000002)
    request("GET", "/auth/me", token=fresh)
    asyncio.run(websocket_revocation(fresh))
    password_login()
    asyncio.run(login_lua())
    STATE.write_text(
        json.dumps({"revoked": [other, concurrent, fresh], "fresh": login(910000002)}),
        encoding="utf-8",
    )


async def websocket_revocation(token):
    import aiohttp
    from redis.asyncio import Redis

    redis = Redis.from_url(os.environ["REDIS_URL"])
    try:
        async with aiohttp.ClientSession() as client:
            async with client.ws_connect(
                f"http://api:9583/ws/users/910000002?token={token}"
            ) as socket:
                request("POST", "/auth/logout", token=token)
                await redis.publish("user_updates:910000002", "synthetic-after-revocation")
                message = await socket.receive(timeout=20)
                assert message.type == aiohttp.WSMsgType.CLOSE and socket.close_code == 1008
            try:
                await client.ws_connect(f"http://api:9583/ws/users/910000002?token={token}")
            except aiohttp.WSServerHandshakeError as error:
                assert error.status == 403
            else:
                raise AssertionError("Revoked token established a new WebSocket")
    finally:
        await redis.aclose()


def password_login():
    from urllib.parse import urlencode

    def form(username, password, expected):
        body = urlencode({"username": username, "password": password}).encode()
        try:
            response = urlopen(
                Request(
                    API + "/auth/login",
                    data=body,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                ),
                timeout=10,
            )
        except HTTPError as error:
            response = error
        with response:
            assert response.code == expected, (response.code, expected)
            if expected == 429:
                assert 0 < int(response.headers["Retry-After"]) <= 60
            return json.loads(response.read())

    authenticated = form(os.environ["STATS_USER"], os.environ["STATS_PASS"], 200)
    request("GET", "/auth/me", token=authenticated["access_token"])
    for index in range(11):
        form("rc-nonexistent", "wrong-synthetic-password", 401 if index < 10 else 429)


def after_revocation():
    state = json.loads(STATE.read_text(encoding="utf-8"))
    for token in state["revoked"]:
        request("GET", "/auth/me", token=token, expected=401)
    request("GET", "/auth/me", token=state["fresh"])
    STATE.unlink()


async def login_lua():
    """Execute the exact limiter script through two real Redis client connections."""
    from redis.asyncio import Redis

    from fastapi_stats_app.login_limits import _SCRIPT, LIMITS

    first = Redis.from_url(os.environ["REDIS_URL"])
    second = Redis.from_url(os.environ["REDIS_URL"])
    try:
        keys = ["rc:limiter:" + str(i) for i in range(3)]
        values = await asyncio.gather(
            *[(first if i % 2 else second).eval(_SCRIPT, 3, *keys, 60, *LIMITS) for i in range(11)]
        )
        assert sum(int(value) > 0 for value in values) == 1
        assert 0 < await first.ttl(keys[2]) <= 60
        assert int(await second.get(keys[2])) == 11
        await first.expire(keys[2], 1)
        await asyncio.sleep(1.1)
        assert await second.get(keys[2]) is None
        # Distinct pairs still share the account budget across clients.
        waits = []
        for i in range(21):
            waits.append(
                await first.eval(
                    _SCRIPT, 3, f"rc:client:{i}", "rc:shared-account", f"rc:pair:{i}", 60, *LIMITS
                )
            )
        assert sum(int(value) > 0 for value in waits) == 1
        waits = [
            await second.eval(
                _SCRIPT,
                3,
                "rc:shared-client",
                f"rc:account:{i}",
                f"rc:client-pair:{i}",
                60,
                *LIMITS,
            )
            for i in range(61)
        ]
        assert sum(int(value) > 0 for value in waits) == 1
    finally:
        await first.aclose()
        await second.aclose()


async def outbox():
    """Real scheduler + PostgreSQL; only external Telegram is a local HTTP fixture."""
    import aiohttp
    from aiohttp import web
    from sqlalchemy import select, update

    from scheduler_app.jobs import deliver_pending_schedule_change_notifications
    from shared_lib.database import close_db_pool, get_session, init_db_pool
    from shared_lib.models import ScheduleChangeDelivery, UserScheduleSubscription
    from shared_lib.schedule_outbox import enqueue_daily_schedule_delivery

    await init_db_pool()
    now = datetime.now(UTC)
    async with get_session() as db:
        db.add(
            UserScheduleSubscription(
                user_id=910000002,
                chat_id=910000002,
                entity_type="group",
                entity_id="rc-group",
                entity_name="RC group",
                notification_time=now.time().replace(tzinfo=None),
                is_active=True,
                delivery_mode="telegram",
            )
        )
        await db.commit()
    row = {
        "user_id": 910000002,
        "chat_id": 910000002,
        "entity_type": "group",
        "entity_id": "rc-group",
        "expires_at": now + timedelta(hours=1),
    }
    assert (
        await enqueue_daily_schedule_delivery(
            event_key="c" * 64, subscription=row, payload="RC notification"
        )
        == 1
    )
    assert (
        await enqueue_daily_schedule_delivery(
            event_key="c" * 64, subscription=row, payload="RC notification"
        )
        == 0
    )
    calls = []

    async def receive(request):
        calls.append(await request.json())
        return web.json_response(
            {"ok": False} if len(calls) == 1 else {"ok": True, "result": {"message_id": 1}},
            status=503 if len(calls) == 1 else 200,
        )

    app = web.Application()
    app.router.add_post("/send", receive)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    try:
        async with aiohttp.ClientSession() as session:

            class Transport:
                def post(self, url, **kwargs):
                    assert url.startswith("https://api.telegram.org/")
                    return session.post(f"http://127.0.0.1:{port}/send", **kwargs)

            failed = await deliver_pending_schedule_change_notifications(Transport())
            assert failed["rescheduled"] == 1
            async with get_session() as db:
                await db.execute(
                    update(ScheduleChangeDelivery).values(
                        next_attempt_at=now - timedelta(seconds=1)
                    )
                )
                await db.commit()
            delivered = await deliver_pending_schedule_change_notifications(Transport())
            assert delivered["sent"] == 1
            async with get_session() as db:
                saved = (await db.execute(select(ScheduleChangeDelivery))).scalar_one()
                assert saved.status == "sent" and saved.attempt_count == 2
            assert len(calls) == 2 and calls[1]["chat_id"] == 910000002
        from rc_delivery_probe import verify_delivery_concurrency

        print("PostgreSQL concurrency:", await verify_delivery_concurrency())
    finally:
        await runner.cleanup()
        await close_db_pool()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["prepare", "verify", "after_revocation", "outbox"])
    phase = parser.parse_args().phase
    if os.environ.get("MPB_ISOLATED_RC") != "1":
        raise SystemExit("Only the disposable RC harness may run this probe")
    if phase == "outbox":
        asyncio.run(outbox())
    else:
        globals()[phase]()
    print("RC phase passed:", phase)
