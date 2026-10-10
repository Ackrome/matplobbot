"""Exercise actual aiogram handler registration and FSM across first-time deep links."""

import __future__

import ast
import asyncio
import logging
import unittest
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from aiogram import Bot, F, Router, types
from aiogram.filters import Command, CommandStart, Filter, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message, User
from aiogram.utils.keyboard import InlineKeyboardBuilder


class OnboardingDestinationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # Keep real router, filters and full BaseManager class. Only unrelated
        # third-party library imports and outbound Telegram I/O are replaced.
        source = Path("bot/handlers/base.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        classes = [node for node in tree.body if isinstance(node, ast.ClassDef)]
        self.database = SimpleNamespace(
            is_onboarding_completed=AsyncMock(return_value=False),
            get_user_settings=AsyncMock(return_value={}),
            update_user_settings_db=AsyncMock(),
            set_onboarding_completed=AsyncMock(),
        )
        self.destinations = {}
        self.destination_ttls = {}

        async def save_destination(key, value, *, ex):
            self.destinations[key] = value
            self.destination_ttls[key] = ex

        async def consume_destination(key):
            return self.destinations.pop(key, None)

        async def delete_destination(key):
            self.destinations.pop(key, None)

        self.redis = SimpleNamespace(
            client=SimpleNamespace(
                set=AsyncMock(side_effect=save_destination),
                getdel=AsyncMock(side_effect=consume_destination),
                delete=AsyncMock(side_effect=delete_destination),
            )
        )
        scope = dict(
            globals(),
            F=F,
            Router=Router,
            Filter=Filter,
            Command=Command,
            CommandStart=CommandStart,
            StateFilter=StateFilter,
            InlineKeyboardBuilder=InlineKeyboardBuilder,
            InlineKeyboardButton=InlineKeyboardButton,
            database=self.database,
            redis_client=self.redis,
            AdminPermissionError=type("AdminPermissionError", (Exception,), {}),
            translator=SimpleNamespace(
                get_language=AsyncMock(return_value="ru"), gettext=lambda lang, key, **kwargs: key
            ),
            kb=SimpleNamespace(get_main_reply_keyboard=AsyncMock(return_value=None)),
        )
        exec(
            compile(
                ast.Module(body=classes, type_ignores=[]),
                "bot/handlers/base.py",
                "exec",
                flags=__future__.annotations.compiler_flag,
            ),
            scope,
        )
        self.settings = SimpleNamespace(
            **{
                name: AsyncMock()
                for name in (
                    "command_subscriptions_private",
                    "command_settings_private",
                    "command_account_data",
                )
            }
        )
        self.schedule = SimpleNamespace(cmd_schedule=AsyncMock(), cmd_calendar_sync=AsyncMock())
        self.manager = scope["BaseManager"](
            None, None, self.schedule, None, None, None, self.settings, None, None
        )
        self.bot = Bot("123456:unit-test-token")
        self.addAsyncCleanup(self.bot.session.close)
        self.storage = MemoryStorage()
        self.addAsyncCleanup(self.storage.close)
        self.state = FSMContext(self.storage, StorageKey(bot_id=123456, chat_id=77, user_id=77))
        self.human = User(id=77, is_bot=False, first_name="Owner")
        self.bot_user = User(id=123456, is_bot=True, first_name="Bot")
        for owner, name in (
            (Message, "answer"),
            (Message, "edit_text"),
            (Message, "delete"),
            (CallbackQuery, "answer"),
        ):
            replacement = patch.object(owner, name, AsyncMock())
            replacement.start()
            self.addCleanup(replacement.stop)

    def message(self, text, *, sender=None, chat_type="private"):
        return Message(
            message_id=1,
            date=datetime.now(UTC),
            chat=types.Chat(id=77, type=chat_type),
            from_user=sender or self.human,
            text=text,
        ).as_(self.bot)

    async def dispatch_callback(self, data):
        callback = CallbackQuery(
            id="callback",
            from_user=self.human,
            chat_instance="test",
            message=self.message("tour", sender=self.bot_user),
            data=data,
        ).as_(self.bot)
        return await self.manager.router.propagate_event(
            "callback_query", callback, state=self.state, bot=self.bot
        )

    async def test_every_known_destination_survives_language_and_skip_or_finish(self):
        destinations = {
            "web_account": self.settings.command_account_data,
            "web_settings": self.settings.command_settings_private,
            "web_subscriptions": self.settings.command_subscriptions_private,
            "web_subscribe": self.schedule.cmd_schedule,
            "calendar_sync": self.schedule.cmd_calendar_sync,
            "cal_sync": self.schedule.cmd_calendar_sync,
        }
        for destination, target in destinations.items():
            for ending in ("onboarding_skip", "onboarding_finish"):
                with self.subTest(destination=destination, ending=ending):
                    target.reset_mock()
                    await self.manager.router.propagate_event(
                        "message",
                        self.message("/start " + destination),
                        state=self.state,
                        bot=self.bot,
                    )
                    target.assert_not_awaited()
                    self.assertEqual(list(self.destinations.values()), [destination])
                    self.assertNotIn("onboarding_destination", await self.state.get_data())
                    await self.dispatch_callback("set_lang_init:ru")
                    await self.dispatch_callback("go_to_onboarding_final")
                    await self.dispatch_callback(ending)
                    target.assert_awaited_once()
                    resumed = target.call_args.args[0]
                    self.assertEqual(resumed.from_user.id, 77)
                    self.assertEqual(resumed.text, "/start " + destination)
                    self.assertNotIn("onboarding_destination", await self.state.get_data())
                    self.assertEqual(self.destinations, {})

    async def test_existing_user_routes_directly_and_restart_clears_old_destination(self):
        self.database.is_onboarding_completed.return_value = True
        await self.manager.router.propagate_event(
            "message", self.message("/start web_account"), state=self.state, bot=self.bot
        )
        self.settings.command_account_data.assert_awaited_once()
        self.database.is_onboarding_completed.return_value = False
        await self.manager.router.propagate_event(
            "message", self.message("/start web_account"), state=self.state, bot=self.bot
        )
        await self.manager.router.propagate_event(
            "message", self.message("/start unknown"), state=self.state, bot=self.bot
        )
        self.assertNotIn("onboarding_destination", await self.state.get_data())
        self.assertEqual(self.destinations, {})

    async def test_feature_detours_clear_fsm_but_preserve_durable_destination(self):
        # Execute the real feature completion handlers which originally erased
        # the destination, while replacing rendering/search and Telegram I/O.
        for kind in ("schedule", "latex"):
            with self.subTest(kind=kind):
                await self.manager.router.propagate_event(
                    "message", self.message("/start web_account"), state=self.state, bot=self.bot
                )
                await self.dispatch_callback("set_lang_init:ru")
                await self.state.set_state("feature:exercise")
                await self.state.update_data(search_type="group")
                if kind == "schedule":
                    path, owner, name = (
                        "bot/handlers/schedule.py",
                        "ScheduleManager",
                        "handle_search_query",
                    )
                    tasks = []
                    manager = SimpleNamespace(
                        _perform_search_and_reply=AsyncMock(), _track_background_task=tasks.append
                    )
                else:
                    path, owner, name = (
                        "bot/handlers/rendering.py",
                        "RenderingManager",
                        "process_latex_formula",
                    )
                    manager = SimpleNamespace()
                tree = ast.parse(Path(path).read_text(encoding="utf-8"))
                cls = next(
                    node
                    for node in tree.body
                    if isinstance(node, ast.ClassDef) and node.name == owner
                )
                method = next(
                    node
                    for node in cls.body
                    if isinstance(node, ast.AsyncFunctionDef) and node.name == name
                )
                scope = dict(
                    globals(),
                    database=SimpleNamespace(
                        get_user_settings=AsyncMock(
                            return_value={"latex_padding": 1, "latex_dpi": 100}
                        )
                    ),
                    translator=SimpleNamespace(
                        get_language=AsyncMock(return_value="ru"),
                        gettext=lambda *args, **kwargs: "fixture",
                    ),
                    document_renderer=SimpleNamespace(
                        render_latex_to_image=AsyncMock(
                            side_effect=ValueError("fixture render rejection")
                        )
                    ),
                )
                exec(
                    compile(
                        ast.Module(body=[method], type_ignores=[]),
                        path,
                        "exec",
                        flags=__future__.annotations.compiler_flag,
                    ),
                    scope,
                )
                with (
                    patch.object(
                        Message,
                        "answer",
                        AsyncMock(return_value=SimpleNamespace(edit_text=AsyncMock())),
                    ),
                    patch.object(Bot, "send_chat_action", AsyncMock()),
                    patch.object(logging, "error"),
                ):
                    await scope[name](manager, self.message("example"), self.state)
                if kind == "schedule":
                    await asyncio.gather(*tasks)
                self.assertEqual(await self.state.get_data(), {})
                self.assertEqual(list(self.destinations.values()), ["web_account"])
                self.settings.command_account_data.reset_mock()
                await self.dispatch_callback("go_to_onboarding_final")
                await self.dispatch_callback("onboarding_finish")
                self.settings.command_account_data.assert_awaited_once()
                self.assertEqual(self.destinations, {})

    async def test_destination_replacement_and_consumption_are_scoped_and_once(self):
        for destination in ("web_account", "web_settings"):
            await self.manager.router.propagate_event(
                "message", self.message("/start " + destination), state=self.state, bot=self.bot
            )
        key = self.manager._onboarding_destination_key(self.message(""), 77)
        other_key = self.manager._onboarding_destination_key(self.message(""), 88)
        self.assertTrue(key.startswith("user_cache:77:"))
        self.destinations[other_key] = "web_account"
        self.assertEqual(self.destination_ttls[key], 30 * 24 * 60 * 60)
        # Both completions may run, but GETDEL grants the destination to one only.
        await asyncio.gather(
            self.dispatch_callback("onboarding_finish"), self.dispatch_callback("onboarding_skip")
        )
        self.settings.command_settings_private.assert_awaited_once()
        self.settings.command_account_data.assert_not_awaited()
        self.assertEqual(self.destinations, {other_key: "web_account"})
        self.database.update_user_settings_db.assert_not_awaited()

    async def test_private_destinations_do_not_run_in_groups(self):
        for payload in ("web_account", "web_settings", "calendar_sync"):
            await self.manager.command_start_regular(
                self.message("/start " + payload, chat_type="supergroup"), self.state
            )
        self.settings.command_account_data.assert_not_awaited()
        self.settings.command_settings_private.assert_not_awaited()
        self.schedule.cmd_calendar_sync.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
