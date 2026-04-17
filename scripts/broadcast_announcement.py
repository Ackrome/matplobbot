import argparse
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / ".env")

from aiogram import Bot  # noqa: E402
from aiogram.exceptions import TelegramRetryAfter  # noqa: E402

from shared_lib.database import (  # noqa: E402
    close_db_pool,
    get_active_broadcast_user_ids,
    init_db_pool,
)
from shared_lib.egress import get_telegram_proxy_url  # noqa: E402
from shared_lib.services.broadcast_service import (  # noqa: E402
    DEFAULT_BROADCAST_ACTIVE_DAYS,
    DEFAULT_BROADCAST_RATE_PER_SECOND,
    DEFAULT_BROADCAST_TITLE,
    broadcast_chunks_to_users,
    dedupe_user_ids,
    format_broadcast_plan,
    format_broadcast_result,
    load_broadcast_text,
    split_telegram_message,
)
from shared_lib.telegram_bot_session import TelegramBotSession  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Safely broadcast announcement/changelog Markdown to active Telegram users. "
            "Dry-run is the default; pass --execute to send."
        )
    )
    parser.add_argument("--execute", action="store_true", help="Actually send the broadcast.")
    parser.add_argument(
        "--active-days",
        type=int,
        default=DEFAULT_BROADCAST_ACTIVE_DAYS,
        help="Users with activity in this many days are included.",
    )
    parser.add_argument(
        "--rate",
        type=float,
        default=DEFAULT_BROADCAST_RATE_PER_SECOND,
        help="Telegram send rate. Values above 30 msg/sec are capped.",
    )
    parser.add_argument("--limit", type=int, help="Limit target users for staged rollouts.")
    parser.add_argument(
        "--user-id",
        action="append",
        type=int,
        default=[],
        help="Send only to a specific user. Can be repeated.",
    )
    parser.add_argument(
        "--file",
        action="append",
        default=[],
        help=(
            "Markdown source to include. Can be repeated. Defaults to docs/announcement.md "
            "when present and the current changelog."
        ),
    )
    parser.add_argument(
        "--title",
        default=DEFAULT_BROADCAST_TITLE,
        help="Plain text heading prepended to the broadcast.",
    )
    parser.add_argument(
        "--no-schedule-subscribers",
        action="store_true",
        help="Do not include users with active schedule subscriptions unless they were active.",
    )
    parser.add_argument(
        "--print-preview",
        action="store_true",
        help="Print the first Telegram chunk before exiting/sending.",
    )
    return parser


async def _send_message_with_retry(bot: Bot, user_id: int, text: str):
    try:
        await bot.send_message(user_id, text)
    except TelegramRetryAfter as exc:
        retry_after = float(getattr(exc, "retry_after", 1) or 1)
        await asyncio.sleep(retry_after + 1)
        await bot.send_message(user_id, text)


async def _resolve_target_users(args: argparse.Namespace) -> list[int]:
    if args.user_id:
        users = dedupe_user_ids(args.user_id)
        return users[: args.limit] if args.limit else users

    await init_db_pool()
    return await get_active_broadcast_user_ids(
        args.active_days,
        include_schedule_subscribers=not args.no_schedule_subscribers,
        limit=args.limit,
    )


async def async_main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    broadcast_text, files = load_broadcast_text(args.file or None, root=ROOT, title=args.title)
    chunks = split_telegram_message(broadcast_text)

    db_initialized = False
    try:
        if not args.user_id:
            db_initialized = True
        target_user_ids = await _resolve_target_users(args)
    finally:
        if db_initialized:
            await close_db_pool()

    plan = format_broadcast_plan(
        user_count=len(target_user_ids),
        chunks=chunks,
        files=files,
        active_days=args.active_days,
        rate_per_second=args.rate,
        dry_run=not args.execute,
        include_schedule_subscribers=not args.no_schedule_subscribers,
    )
    print(plan)

    if args.print_preview and chunks:
        print("\n--- first chunk preview ---")
        print(chunks[0])
        print("--- end preview ---")

    if not args.execute:
        print("\nDry run only. Re-run with --execute to send.")
        return 0

    if not target_user_ids:
        print("\nNo target users found.")
        return 0

    if not chunks:
        print("\nBroadcast text is empty.")
        return 1

    token = os.getenv("BOT_TOKEN")
    if not token:
        print("BOT_TOKEN is not set; cannot execute broadcast.", file=sys.stderr)
        return 2

    bot = Bot(token=token, session=TelegramBotSession(get_telegram_proxy_url()))
    try:
        result = await broadcast_chunks_to_users(
            target_user_ids,
            chunks,
            lambda user_id, chunk: _send_message_with_retry(bot, user_id, chunk),
            rate_per_second=args.rate,
            dry_run=False,
        )
    finally:
        await bot.session.close()

    print()
    print(format_broadcast_result(result))
    return 0 if result.failed_messages == 0 else 1


def main() -> int:
    return asyncio.run(async_main())


if __name__ == "__main__":
    raise SystemExit(main())
