"""Account-to-bot routing and shared calendar host lifecycle regressions."""

import __future__

import ast
import shutil
import subprocess
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

ROOT = Path(__file__).resolve().parents[1]


def handler(path, owner, name, dependencies):
    """Load the actual method without importing the bot's optional ML libraries."""
    tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == owner)
    method = next(
        node for node in cls.body if isinstance(node, ast.AsyncFunctionDef) and node.name == name
    )
    module = ast.Module(body=[method], type_ignores=[])
    scope = dict(dependencies)
    exec(compile(module, path, "exec", flags=__future__.annotations.compiler_flag), scope)
    return scope[name]


class SubscriptionEntrypointTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.translator = SimpleNamespace(
            get_language=AsyncMock(return_value="ru"),
            gettext=Mock(side_effect=lambda lang, key, **kw: key),
        )
        self.manager = SimpleNamespace(
            _onboarding_destination_key=lambda message, user_id: "fixture-destination",
            settings_manager=SimpleNamespace(
                command_subscriptions_private=AsyncMock(), command_settings_private=AsyncMock()
            ),
            schedule_manager=SimpleNamespace(cmd_schedule=AsyncMock()),
        )
        self.message = SimpleNamespace(
            text="/start web_subscriptions",
            chat=SimpleNamespace(type="private", id=77),
            from_user=SimpleNamespace(id=77),
            answer=AsyncMock(),
        )
        self.state = SimpleNamespace(clear=AsyncMock())
        self.start = handler(
            "bot/handlers/base.py",
            "BaseManager",
            "command_start_regular",
            {
                "translator": self.translator,
                "redis_client": SimpleNamespace(client=SimpleNamespace(delete=AsyncMock())),
            },
        )

    async def test_manage_link_opens_subscription_list(self):
        await self.start(self.manager, self.message, self.state)
        self.state.clear.assert_awaited_once()
        self.manager.settings_manager.command_subscriptions_private.assert_awaited_once_with(
            self.message
        )
        self.manager.schedule_manager.cmd_schedule.assert_not_awaited()

    async def test_add_link_starts_search_with_existing_fsm(self):
        self.message.text = "/start web_subscribe"
        await self.start(self.manager, self.message, self.state)
        self.state.clear.assert_awaited_once()
        self.message.answer.assert_awaited_once_with("cal_sync_add_subscription_hint")
        self.manager.schedule_manager.cmd_schedule.assert_awaited_once_with(
            self.message, self.state
        )

    async def test_deep_links_never_render_private_data_in_groups(self):
        self.message.chat.type = "supergroup"
        for payload in ("web_subscriptions", "web_subscribe"):
            self.message.text = f"/start {payload}"
            await self.start(self.manager, self.message, self.state)
        self.manager.settings_manager.command_subscriptions_private.assert_not_awaited()
        self.manager.schedule_manager.cmd_schedule.assert_not_awaited()
        self.message.answer.assert_not_awaited()

    async def test_existing_settings_link_is_preserved(self):
        self.message.text = "/start web_settings"
        await self.start(self.manager, self.message, self.state)
        self.manager.settings_manager.command_settings_private.assert_awaited_once_with(
            self.message
        )

    async def test_private_list_uses_callers_identity(self):
        function = handler(
            "bot/handlers/settings.py", "SettingsManager", "command_subscriptions_private", {}
        )
        keyboard = SimpleNamespace(as_markup=lambda: "buttons")
        manager = SimpleNamespace(
            _personal_subscriptions_view=AsyncMock(return_value=("subscriptions", keyboard))
        )
        await function(manager, self.message)
        manager._personal_subscriptions_view.assert_awaited_once_with(77)
        self.message.answer.assert_awaited_once_with("subscriptions", reply_markup="buttons")
        manager._personal_subscriptions_view.reset_mock()
        self.message.chat.type = "group"
        await function(manager, self.message)
        manager._personal_subscriptions_view.assert_not_awaited()

    async def test_empty_and_paused_subscriptions_use_existing_keyboard(self):
        query = AsyncMock(
            return_value=([{"id": 42, "entity_name": "Group", "is_active": False}], 6)
        )
        keyboard = Mock()
        function = handler(
            "bot/handlers/settings.py",
            "SettingsManager",
            "_personal_subscriptions_view",
            {
                "translator": self.translator,
                "get_user_subscriptions": query,
                "InlineKeyboardBuilder": lambda: keyboard,
                "InlineKeyboardButton": SimpleNamespace,
            },
        )
        manager = SimpleNamespace()
        self.assertEqual(await function(manager, 77), ("subscriptions_header", keyboard))
        query.assert_awaited_with(77, page=0, page_size=5)
        callbacks = [
            button.callback_data for call in keyboard.row.call_args_list for button in call.args
        ]
        self.assertIn("sub_open:42", callbacks)
        self.assertIn("subs_page:1", callbacks)
        query.return_value = ([], 0)
        self.assertEqual((await function(manager, 77))[0], "subscriptions_empty")


@unittest.skipUnless(shutil.which("node"), "Node required for shared calendar lifecycle")
class CalendarHostTests(unittest.TestCase):
    def test_account_host_without_schedule_globals_and_stale_auth_response(self):
        source = r"""
            const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
            let token='owner-a', pending=[];
            const host={user:{id:1,telegram_id:77},onState:state=>host.last=state};
            const context={URLSearchParams,Set,Map,console,
                localStorage:{getItem:key=>key==='jwt_token'?token:null,setItem(){}},
                document:{addEventListener(){},getElementById(){return null;}},
                window:{MpbCalendarHost:host,location:{search:''},addEventListener(){},
                    mpbI18n:{t:(key,fallback)=>fallback,getLanguage:()=> 'ru'}},
                fetch:()=>new Promise(resolve=>pending.push(resolve))};
            vm.createContext(context);
            vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),context);
            const response = name=>({ok:true,status:200,json:async()=>({enabled:true,sync_enabled:true,profiles:[{id:name}]})});
            (async()=>{
                let load=context.window.refreshCalendarSubscription();
                pending.shift()(response('first')); await load;
                assert.equal(host.last.profiles[0].id,'first');
                load=context.window.refreshCalendarSubscription();
                token='owner-b'; pending.shift()(response('private-owner-a')); await load;
                assert.notEqual(host.last.profiles[0]?.id,'private-owner-a');
                const earlier=context.window.refreshCalendarSubscription();
                const later=context.window.refreshCalendarSubscription();
                const resolveEarlier=pending.shift(); pending.shift()(response('newer')); await later;
                resolveEarlier(response('older')); await earlier;
                assert.equal(host.last.profiles[0].id,'newer');
                const failed=context.window.refreshCalendarSubscription();
                pending.shift()({status:401}); await failed;
                assert.equal(host.user,null); assert.equal(host.last.profiles.length,0);
            })().catch(error=>{console.error(error);process.exitCode=1;});
        """
        result = subprocess.run(
            ["node", "-e", source, str(ROOT / "main_site_frontend/js/calendar_sync.js")],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
