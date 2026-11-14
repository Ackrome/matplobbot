"""PostgreSQL delivery concurrency checks for the disposable RC harness only."""

import asyncio
import hashlib
import os
from datetime import date, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from shared_lib.database import (
    get_session,
    remove_schedule_subscription,
    toggle_subscription_status,
)
from shared_lib.models import ScheduleChangeDelivery, User, UserScheduleSubscription
from shared_lib.schedule_history import build_schedule_history
from shared_lib.schedule_outbox import (
    ScheduleBaselineConflict,
    claim_schedule_change_deliveries,
    commit_schedule_change_transition,
    enqueue_schedule_change_deliveries,
    get_schedule_notification_snapshot,
    is_schedule_delivery_current,
    mark_schedule_change_delivery_sent,
    schedule_snapshot_hash,
)

FIXTURE_USER = 910000002


async def verify_delivery_concurrency(read_history) -> dict:
    """Use real transactions/locks; caller initializes its disposable PostgreSQL pool.

    No network transport is constructed. Synthetic successful claims are acknowledged
    directly, solely to leave the fixture queue clear for subsequent checks.
    """
    if os.environ.get("MPB_ISOLATED_RC") != "1":
        raise RuntimeError("Only the disposable RC harness may run this probe")
    entities = ["rc-delivery-lock", "rc-delivery-baseline", "rc-delivery-cancel"]
    profiles = {}
    async with get_session() as db:
        assert await db.get(User, FIXTURE_USER) is not None, "RC fixture user must exist"
        existing = await db.scalar(
            select(func.count())
            .select_from(UserScheduleSubscription)
            .where(UserScheduleSubscription.entity_id.in_(entities))
        )
        assert existing == 0, "Concurrency probe requires unused fixture entities"
        for entity in entities:
            count = 2 if entity.endswith("cancel") else 1
            profiles[entity] = []
            for hour in range(count):
                profile = UserScheduleSubscription(
                    user_id=FIXTURE_USER,
                    chat_id=FIXTURE_USER,
                    entity_type="group",
                    entity_id=entity,
                    entity_name=entity,
                    notification_time=time(hour),
                    is_active=True,
                    delivery_mode="telegram",
                )
                db.add(profile)
                await db.flush()
                profiles[entity].append(profile.id)
        await db.commit()

    recipient = [{"user_id": FIXTURE_USER, "chat_id": FIXTURE_USER, "payload": "RC fixture"}]
    entity = entities[0]
    for suffix in ["first", "second"]:
        assert (
            await enqueue_schedule_change_deliveries(
                f"rc-delivery-lock-{suffix}", "group", entity, recipient
            )
            == 1
        )
    async with get_session() as locked:
        # The queue timestamps come from PostgreSQL; use the same clock in the
        # probe so a fractional-second host/container skew cannot mask locking.
        eligible_time = await locked.scalar(select(func.now())) + timedelta(seconds=1)
        first_id = await locked.scalar(
            select(ScheduleChangeDelivery.id)
            .where(ScheduleChangeDelivery.event_key == "rc-delivery-lock-first")
            .with_for_update()
        )
        claimed = await asyncio.wait_for(
            claim_schedule_change_deliveries(limit=1, now_utc=eligible_time), timeout=5
        )
        assert len(claimed) == 1 and claimed[0]["event_key"] == "rc-delivery-lock-second"
        assert claimed[0]["id"] != first_id and claimed[0]["attempt_count"] == 1
        await locked.rollback()
    await mark_schedule_change_delivery_sent(claimed[0]["id"], expected_attempt_count=1)
    first_claim = await claim_schedule_change_deliveries(limit=1, now_utc=eligible_time)
    assert len(first_claim) == 1 and first_claim[0]["id"] == first_id
    await mark_schedule_change_delivery_sent(first_id, expected_attempt_count=1)

    entity = entities[1]

    def lesson(room):
        return {
            "lessonOid": 1,
            "date": "2099-11-01",
            "beginLesson": "10:10",
            "endLesson": "11:40",
            "discipline": "RC fixture",
            "kindOfWork": "Lecture",
            "auditorium": room,
        }

    previous = [lesson("RC old")]

    async def transition(event, data, revision, deliveries):
        return await commit_schedule_change_transition(
            event_key=hashlib.sha256(event.encode()).hexdigest(),
            entity_type="group",
            entity_id=entity,
            entity_name=entity,
            schedule_data=data,
            new_hash=schedule_snapshot_hash(data),
            expected_revision=revision,
            deliveries=deliveries,
            history=build_schedule_history(
                previous,
                data,
                semester_start="2099-08-01",
                semester_end="2100-01-31",
                today=date(2099, 10, 10),
            )
            if revision
            else [],
        )

    assert await transition("rc-delivery-initial", previous, None, []) == 0
    outcomes = await asyncio.wait_for(
        asyncio.gather(
            transition("rc-delivery-cas-a", [lesson("RC A")], 1, recipient),
            transition("rc-delivery-cas-b", [lesson("RC B")], 1, recipient),
            return_exceptions=True,
        ),
        timeout=5,
    )
    assert sum(isinstance(value, ScheduleBaselineConflict) for value in outcomes) == 1
    assert sum(value == 1 for value in outcomes) == 1
    baseline = await get_schedule_notification_snapshot("group", entity)
    assert baseline["revision"] == 2
    async with get_session() as db:
        pending = (
            (
                await db.execute(
                    select(ScheduleChangeDelivery).where(ScheduleChangeDelivery.entity_id == entity)
                )
            )
            .scalars()
            .all()
        )
        assert len(pending) == 1, "The losing scanner must not enqueue its transition"
        winner_id = pending[0].id
        winner_event = pending[0].event_key
    # PostgreSQL enforces the recipient FK after the baseline UPDATE: all writes
    # must roll back when enqueue fails, including the baseline revision/hash.
    try:
        await transition(
            "rc-delivery-rollback",
            [lesson("RC invalid recipient")],
            2,
            [{"user_id": -910000002, "chat_id": FIXTURE_USER, "payload": "RC invalid"}],
        )
    except IntegrityError:
        pass
    else:
        raise AssertionError("Invalid fixture recipient unexpectedly satisfied its foreign key")
    assert await get_schedule_notification_snapshot("group", entity) == baseline
    await mark_schedule_change_delivery_sent(winner_id)

    history_path = f"/schedule/history/group/{entity}"
    history = await asyncio.to_thread(read_history, history_path)
    assert len(history["items"]) == 1, "Only the winning transition can appear in public history"
    change = history["items"][0]
    assert change["before"]["room"] == "RC old"
    assert change["after"]["room"] == baseline["schedule_data"][0]["auditorium"]
    assert await asyncio.to_thread(read_history, f"{history_path}?event={winner_event}") == history

    entity = entities[2]
    assert (
        await enqueue_schedule_change_deliveries("rc-delivery-overlap", "group", entity, recipient)
        == 1
    )
    first_profile, second_profile = profiles[entity]
    assert await remove_schedule_subscription(first_profile, FIXTURE_USER) == entity
    async with get_session() as db:
        eligible_time = await db.scalar(select(func.now())) + timedelta(seconds=1)
    claimed = await claim_schedule_change_deliveries(limit=1, now_utc=eligible_time)
    assert len(claimed) == 1 and claimed[0]["event_key"] == "rc-delivery-overlap"
    assert await is_schedule_delivery_current(claimed[0]["id"], 1)
    assert await toggle_subscription_status(second_profile, FIXTURE_USER) == (False, entity)
    assert not await is_schedule_delivery_current(claimed[0]["id"], 1)
    async with get_session() as db:
        row = await db.get(ScheduleChangeDelivery, claimed[0]["id"])
        assert row.status == "cancelled" and row.payload == "" and row.locked_at is None

    return {
        "skip_locked": True,
        "baseline_single_winner": True,
        "failed_enqueue_rolls_back_baseline": True,
        "public_history_single_winner": True,
        "overlapping_profile_preserves_delivery": True,
        "pause_after_claim_cancels": True,
        "external_sends": 0,
    }
