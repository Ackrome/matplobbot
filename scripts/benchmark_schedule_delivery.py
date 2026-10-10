"""Offline delivery load probe: isolated SQLite, synthetic upstream and no sends."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import platform
import sys
import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import JSON, Integer, MetaData, create_engine, func, select
from sqlalchemy.orm import Session

from scheduler_app import jobs
from shared_lib import database, schedule_outbox
from shared_lib.models import CachedSchedule, ScheduleChangeDelivery, User, UserScheduleSubscription
from shared_lib.services.university_api import RuzAPIError


async def benchmark(
    *,
    users=1000,
    entities=20,
    profiles_per_user=2,
    source_delay_ms=10,
    send_delay_ms=1,
    fail_every=0,
):
    """Measure real grouping/outbox SQL against explicitly simulated provider latency."""
    if not 1 <= users <= 10000 or not 1 <= entities <= min(users, 500):
        raise ValueError("Use 1..10000 users and 1..min(users,500) entities")
    if (
        not 1 <= profiles_per_user <= 6
        or not 0 <= source_delay_ms <= 1000
        or not 0 <= send_delay_ms <= 1000
        or fail_every < 0
    ):
        raise ValueError("Invalid profile count or simulated latency/failure setting")
    engine = create_engine("sqlite:///:memory:")
    metadata = MetaData()
    for model in (User, UserScheduleSubscription, ScheduleChangeDelivery, CachedSchedule):
        table = model.__table__.to_metadata(metadata)
        if model is ScheduleChangeDelivery:
            table.c.id.type = Integer()
        if model is CachedSchedule:
            table.c.schedule_data.type = JSON()
    metadata.create_all(engine)
    now = datetime.now(UTC)
    occurrence = (now - timedelta(minutes=10)).replace(second=0, microsecond=0)
    # Every occurrence is due, including around midnight. All identities are synthetic.
    with engine.begin() as connection:
        connection.execute(
            User.__table__.insert(),
            [{"user_id": user + 1, "full_name": "Synthetic"} for user in range(users)],
        )
        connection.execute(
            UserScheduleSubscription.__table__.insert(),
            [
                {
                    "user_id": user + 1,
                    "chat_id": user + 1,
                    "entity_type": "group",
                    "entity_id": str(user % entities),
                    "entity_name": "Synthetic group",
                    "notification_time": (occurrence + timedelta(seconds=profile))
                    .time()
                    .replace(tzinfo=None),
                    "timezone": "UTC",
                    "is_active": True,
                    "delivery_mode": "telegram",
                }
                for user in range(users)
                for profile in range(profiles_per_user)
            ],
        )
        connection.execute(
            CachedSchedule.__table__.insert(),
            [
                {
                    "entity_type": "group",
                    "entity_id": str(entity),
                    "entity_name": "Synthetic group",
                    "schedule_data": [],
                    "updated_at": now,
                }
                for entity in range(entities)
            ],
        )

    @asynccontextmanager
    async def sessions():
        with Session(engine) as session:

            class Adapter:
                async def execute(self, statement):
                    return session.execute(statement)

                async def commit(self):
                    session.commit()

            yield Adapter()

    source_calls = source_failures = send_calls = 0

    async def source(*args, **kwargs):
        nonlocal source_calls, source_failures
        source_calls += 1
        await asyncio.sleep(source_delay_ms / 1000)
        if fail_every and source_calls % fail_every == 0:
            source_failures += 1
            raise RuzAPIError("Synthetic outage; cached schedule is available")
        return []

    async def send(*args, **kwargs):
        nonlocal send_calls
        send_calls += 1
        await asyncio.sleep(send_delay_ms / 1000)
        return {"message_id": send_calls}

    started = time.perf_counter()
    try:
        with (
            patch.object(database, "get_session", sessions),
            patch.object(schedule_outbox, "get_session", sessions),
            patch.object(jobs.translator, "get_language", AsyncMock(return_value="en")),
            patch.object(jobs, "format_schedule", AsyncMock(return_value="Synthetic schedule")),
            patch.object(jobs, "send_telegram_message", send),
        ):
            api = SimpleNamespace(get_schedule=source)
            async with asyncio.timeout(600):
                preparation = await jobs.send_daily_schedules(None, api)
                prepared_at = time.perf_counter()
                batches = 1
                while send_calls < users:
                    summary = await jobs.deliver_pending_schedule_change_notifications(None)
                    batches += 1
                    if not summary["claimed"]:
                        raise RuntimeError("Synthetic queue stopped making progress")
                drained_at = time.perf_counter()
                calls_before_retry = (source_calls, send_calls)
                replay = await jobs.send_daily_schedules(None, api)
                if (source_calls, send_calls) != calls_before_retry or replay["prepared"]:
                    raise AssertionError("Repeated daily tick duplicated preparation or delivery")
            with Session(engine) as session:
                statuses = dict(
                    session.execute(
                        select(ScheduleChangeDelivery.status, func.count()).group_by(
                            ScheduleChangeDelivery.status
                        )
                    ).all()
                )
            if statuses != {"sent": users} or source_calls != entities:
                raise AssertionError("Synthetic grouping or delivery count changed")
            elapsed = drained_at - started
            return {
                "scope": "offline SQLite SQL/grouping probe; synthetic source, formatter and Telegram; no production capacity claim",
                "drain_mode": "continuous caller-driven batches; excludes minute scheduler cadence and provider rate limits",
                "observed_at": now.isoformat(),
                "python": platform.python_version(),
                "scenario": {
                    "users": users,
                    "entities": entities,
                    "profiles_per_user": profiles_per_user,
                    "source_delay_ms": source_delay_ms,
                    "send_delay_ms": send_delay_ms,
                    "fail_every": fail_every,
                },
                "source_calls": source_calls,
                "source_failures_with_cache": source_failures,
                "network_requests": 0,
                "synthetic_sends": send_calls,
                "preparation_and_first_batch_seconds": round(prepared_at - started, 3),
                "total_drain_seconds": round(elapsed, 3),
                "effective_deliveries_per_second": round(users / elapsed, 2),
                "drain_batches": batches,
                "preparation": preparation,
                "status_counts": statuses,
                "repeated_tick_duplicates": 0,
            }
    finally:
        engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--users", type=int, default=1000)
    parser.add_argument("--entities", type=int, default=20)
    parser.add_argument("--profiles-per-user", type=int, default=2)
    parser.add_argument("--source-delay-ms", type=int, default=10)
    parser.add_argument("--send-delay-ms", type=int, default=1)
    parser.add_argument("--fail-every", type=int, default=0)
    parser.add_argument("--output", type=Path)
    args = vars(parser.parse_args())
    output = args.pop("output")
    logging.getLogger().setLevel(logging.ERROR)
    report = asyncio.run(benchmark(**args))
    payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if output:
        output.write_text(payload, encoding="utf-8")
    print(payload, end="")


if __name__ == "__main__":
    main()
