"""Telegram planning commands for the caller's active, filtered subscriptions."""

import html
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.services.myschedule_filters import MyScheduleFilterService
from shared_lib.html_tools import split_telegram_html_message
from shared_lib.i18n import translator
from shared_lib.redis_client import redis_client
from shared_lib.services.schedule_planning import load_schedule_plan


class SchedulePlanningManager:
    """Expose /plan, /conflicts and /free for a private seven-day schedule view."""

    def __init__(self, client):
        self.client = client
        self.filters = MyScheduleFilterService()
        self.router = Router()
        self.router.message(Command("plan", "conflicts", "free"), F.chat.type == "private")(
            self.plan
        )

    async def plan(self, message: Message):
        # Help callbacks also call this method directly, bypassing router filters.
        if message.chat.type != "private":
            return
        lang = await translator.get_language(message.from_user.id)
        ru = lang == "ru"
        try:
            acquired = await redis_client.client.set(
                f"schedule_plan_cooldown:{message.from_user.id}", "1", nx=True, ex=5
            )
            if not acquired:
                await message.answer(
                    "Повторите через несколько секунд." if ru else "Try again in a few seconds."
                )
                return
        except Exception:
            # The shared freshness service still coalesces source reads if Redis is down.
            pass
        subscriptions = await self.filters.get_active_subscriptions(message.from_user.id)
        filters = await self.filters.get(message.from_user.id)
        selected = [
            sub for sub in subscriptions if sub["id"] not in filters.get("excluded_subs", [])
        ]
        if not selected:
            await message.answer(
                "Добавьте подписку через /schedule."
                if ru
                else "Add a subscription using /schedule."
            )
            return
        if len({(sub["entity_type"], str(sub["entity_id"])) for sub in selected}) > 6:
            await message.answer(
                "Оставьте до 6 подписок в фильтрах /myschedule для сравнения."
                if ru
                else "Select up to 6 subscriptions in /myschedule filters to compare."
            )
            return
        today = datetime.now(ZoneInfo("Europe/Moscow")).date()
        status = await message.answer("Сравниваю расписания…" if ru else "Comparing schedules…")
        try:
            result = await load_schedule_plan(
                self.client,
                selected,
                start_date=today,
                end_date=today + timedelta(days=6),
                excluded_types=set(filters.get("excluded_types", [])),
            )
        except ValueError:
            await status.edit_text(
                "План доступен в пределах текущего семестра. Проверьте даты на сайте."
                if ru
                else "Planning is available within the current semester. Check dates on the website."
            )
            return
        except Exception:
            logging.exception("Schedule planning could not complete")
            await status.edit_text(
                "Не удалось проверить расписания. Повторите /plan позже."
                if ru
                else "Could not verify schedules. Retry /plan later."
            )
            return
        lines = ["<b>План на 7 дней · Москва</b>" if ru else "<b>Seven-day plan · Moscow</b>"]
        lines.append("Пересечения:" if ru else "Conflicts:")
        for conflict in result["conflicts"][:15]:
            left = datetime.fromisoformat(conflict["start"])
            right = datetime.fromisoformat(conflict["end"])
            names = " / ".join(html.escape(item["discipline"]) for item in conflict["lessons"])
            lines.append(f"• {left:%d.%m %H:%M}–{right:%H:%M}: {names}")
        if not result["conflicts"]:
            lines.append(
                "Пересечений в доступных данных нет."
                if ru
                else "No conflicts in the available data."
            )
        if result["incomplete"]:
            lines.append(
                "Не все источники проверены; свободные окна пока не показываются. Повторите /plan после обновления."
                if ru
                else "Some sources are unverified; free windows are withheld. Retry /plan after refresh."
            )
        else:
            lines.append(
                "Общие окна 08:00–22:00 (от 30 минут):"
                if ru
                else "Common windows 08:00–22:00 (30+ minutes):"
            )
            for window in result["free_windows"][:20]:
                left, right = (
                    datetime.fromisoformat(window["start"]),
                    datetime.fromisoformat(window["end"]),
                )
                lines.append(
                    f"• {left:%d.%m %H:%M}–{right:%H:%M} · {window['duration_minutes']} min"
                )
        if len(result["conflicts"]) > 15 or len(result["free_windows"]) > 20:
            lines.append(
                "Показана часть списка; полный план доступен на сайте."
                if ru
                else "List shortened; the complete plan is available on the website."
            )
        if "room_availability_is_timetable_only" in result["warnings"]:
            lines.append(
                "Окно в расписании аудитории не подтверждает её доступность."
                if ru
                else "A room timetable gap does not confirm physical availability."
            )
        chunks = split_telegram_html_message("\n".join(lines), max_chars=3800)
        await status.edit_text(chunks[0], parse_mode="HTML")
        for chunk in chunks[1:]:
            await message.answer(chunk, parse_mode="HTML")
