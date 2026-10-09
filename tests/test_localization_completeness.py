import json
import re
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path

# `shared_lib.i18n` imports database helpers from `shared_lib.database`,
# which depends on SQLAlchemy. For this unit test we only need Translator
# fallback logic, so we provide a lightweight stub module.
fake_database_module = types.ModuleType("shared_lib.database")


async def _fake_get_settings(*_args, **_kwargs):
    return {}


fake_database_module.get_chat_settings = _fake_get_settings
fake_database_module.get_user_settings = _fake_get_settings
sys.modules.setdefault("shared_lib.database", fake_database_module)

from shared_lib.i18n import Translator


class TestLocalizationCompleteness(unittest.TestCase):
    def run_browser_script(self, script):
        result = subprocess.run(
            ["node", "-e", script], capture_output=True, text=True, encoding="utf-8", timeout=20
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    @unittest.skipUnless(shutil.which("node"), "node is required for browser logic tests")
    def test_frontend_ready_waits_for_remaining_locale_after_one_fails(self):
        self.run_browser_script("""
            const assert = require('node:assert/strict'), fs = require('node:fs'), vm = require('node:vm');
            const pending = new Map(), requests = [], translations = [], errors = [];
            const sandbox = {document:{documentElement:{lang:'ru'}},
                localStorage:{getItem:()=> 'ru',setItem(){}},
                window:{dispatchEvent(){}},CustomEvent:class {},
                console:{error:(...args)=>errors.push(args)},
                fetch:(url, options)=>{requests.push({url, options});return new Promise((resolve,reject)=>pending.set(url,{resolve,reject}));}};
            vm.createContext(sandbox);
            vm.runInContext(fs.readFileSync('main_site_frontend/js/frontend_i18n.js','utf8'),sandbox);
            const i18n=sandbox.window.mpbI18n;
            let ready=false;i18n.ready.then(()=>ready=true);
            i18n.registerTranslator((lang,t)=>translations.push(t('account.subscriptions.count','count',{count:3})));
            (async()=>{
                const en=requests.find(item=>item.url.includes('/en.json'));
                const ru=requests.find(item=>item.url.includes('/ru.json'));
                assert.ok(new URL(ru.url,'https://example.test').searchParams.get('v'));
                assert.equal(ru.options.cache,'no-cache');
                pending.get(en.url).reject(new Error('English unavailable'));
                await new Promise(resolve=>setImmediate(resolve));
                assert.equal(ready,false,'a failed fallback locale must not finish startup before Russian');
                pending.get(ru.url).resolve({ok:true,json:async()=>({'account.subscriptions.count':'Сохранено: {count}'})});
                await i18n.ready;
                assert.equal(translations.at(-1),'Сохранено: 3');
                assert.equal(sandbox.document.documentElement.lang,'ru');
                assert.equal(errors.length,1);
            })().catch(error=>{console.error(error);process.exitCode=1;});
        """)

    @unittest.skipUnless(shutil.which("node"), "node is required for browser logic tests")
    def test_locale_service_worker_uses_network_then_latest_offline_copy(self):
        self.run_browser_script("""
            const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
            const stores=new Map(),handlers={};let network;
            const key=value=>typeof value==='string'?value:value.url;
            const cache=name=>{
                if(!stores.has(name))stores.set(name,new Map());const rows=stores.get(name);
                return {match:async request=>rows.get(key(request))?.clone(),
                    put:async(request,response)=>rows.set(key(request),response.clone())};
            };
            const sandbox={Request,Response,URL,
                self:{location:{origin:'https://example.test'},addEventListener:(event,handler)=>handlers[event]=handler},
                caches:{open:async name=>cache(name),match:async request=>{
                    for(const rows of stores.values())if(rows.has(key(request)))return rows.get(key(request)).clone();
                }},fetch:async()=>{if(network instanceof Error)throw network;return network.clone();}};
            vm.createContext(sandbox);vm.runInContext(fs.readFileSync('main_site_frontend/service-worker.js','utf8'),sandbox);
            const runtime=vm.runInContext('RUNTIME_CACHE',sandbox),core=vm.runInContext('CORE_CACHE',sandbox);
            const request=new Request('https://example.test/locales/ru.json?v=test');
            const read=()=>{let result;handlers.fetch({request,respondWith:value=>result=value});assert.ok(result);return result;};
            (async()=>{
                await cache(core).put(request,Response.json({heading:'old dictionary'}));
                network=Response.json({heading:'Расписание и подписки'});
                assert.equal((await (await read()).json()).heading,'Расписание и подписки');
                network=new Error('offline');
                assert.equal((await (await read()).json()).heading,'Расписание и подписки','runtime must win over old install snapshot');
                network=new Response('unavailable',{status:503});
                assert.equal((await (await read()).json()).heading,'Расписание и подписки');
                stores.get(runtime).clear();network=new Error('offline');
                assert.equal((await (await read()).json()).heading,'old dictionary','precache remains an offline fallback');
                stores.get(core).clear();network=new Response('unavailable',{status:503});
                assert.equal((await read()).status,503);
            })().catch(error=>{console.error(error);process.exitCode=1;});
        """)

    def test_locale_asset_versions_match_loader_pages_and_precache(self):
        root = Path("main_site_frontend")
        loader = (root / "js/frontend_i18n.js").read_text(encoding="utf-8")
        version = re.search(r'const LOCALE_VERSION = "([^"]+)"', loader).group(1)
        worker = (root / "service-worker.js").read_text(encoding="utf-8")
        for locale in ("en", "ru"):
            self.assertIn(f'"/locales/{locale}.json?v={version}"', worker)
        for page in root.glob("*.html"):
            for asset in re.findall(
                r'src="(/js/frontend_i18n\.js[^\"]*)"', page.read_text(encoding="utf-8")
            ):
                self.assertIn(f'"{asset}"', worker, str(page))
                self.assertIn("?v=", asset)

    def test_ru_and_en_locale_key_sets_are_in_sync(self):
        en_path = Path("shared_lib/locales/en.json")
        ru_path = Path("shared_lib/locales/ru.json")

        en_data = json.loads(en_path.read_text(encoding="utf-8"))
        ru_data = json.loads(ru_path.read_text(encoding="utf-8"))

        self.assertEqual(set(en_data.keys()), set(ru_data.keys()))

    def test_translator_fallback_behavior(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            (tmp_path / "en.json").write_text(
                json.dumps({"hello": "Hello", "fallback_only": "Default value"}),
                encoding="utf-8",
            )
            (tmp_path / "ru.json").write_text(
                json.dumps({"hello": "Привет"}),
                encoding="utf-8",
            )

            translator = Translator(locales_dir=tmp_path, default_lang="en")

            self.assertEqual(translator.gettext("ru", "hello"), "Привет")
            self.assertEqual(translator.gettext("ru", "fallback_only"), "Default value")
            self.assertEqual(translator.gettext("es", "fallback_only"), "Default value")
            self.assertEqual(translator.gettext("ru", "missing_key"), "_missing_key_")

    def test_frontend_locale_key_sets_and_placeholders_are_in_sync(self):
        locales_dir = Path("main_site_frontend/locales")
        en_data = json.loads((locales_dir / "en.json").read_text(encoding="utf-8"))
        ru_data = json.loads((locales_dir / "ru.json").read_text(encoding="utf-8"))

        self.assertEqual(set(en_data), set(ru_data))
        placeholder_pattern = re.compile(r"\{(\w+)\}")
        mismatched_placeholders = {
            key: (
                set(placeholder_pattern.findall(en_data[key])),
                set(placeholder_pattern.findall(ru_data[key])),
            )
            for key in en_data
            if set(placeholder_pattern.findall(en_data[key]))
            != set(placeholder_pattern.findall(ru_data[key]))
        }
        self.assertEqual(mismatched_placeholders, {})

    def test_frontend_translation_attributes_reference_known_keys(self):
        locales_dir = Path("main_site_frontend/locales")
        known_keys = set(json.loads((locales_dir / "en.json").read_text(encoding="utf-8")))
        attribute_pattern = re.compile(
            r"data-(?:i18n|i18n-placeholder|i18n-title|i18n-aria-label|"
            r'stats-i18n|stats-placeholder|stats-title|stats-aria-label)="([^"]+)"'
        )
        used_keys: set[str] = set()
        for html_path in Path("main_site_frontend").glob("*.html"):
            used_keys.update(attribute_pattern.findall(html_path.read_text(encoding="utf-8")))

        self.assertEqual(used_keys - known_keys, set())

    def test_frontend_scripts_use_shared_locale_loader(self):
        navbar_source = Path("main_site_frontend/js/navbar.js").read_text(encoding="utf-8")
        stats_source = Path("main_site_frontend/js/stats.js").read_text(encoding="utf-8")
        self.assertNotIn("const I18N =", navbar_source)
        self.assertNotIn("const STATS_I18N =", stats_source)

        for page_name in (
            "index.html",
            "login.html",
            "register.html",
            "schedule.html",
            "stats.html",
            "studio.html",
        ):
            source = Path("main_site_frontend", page_name).read_text(encoding="utf-8")
            loader_position = source.index("/js/frontend_i18n.js")
            navbar_position = source.index("/js/navbar.js")
            self.assertLess(loader_position, navbar_position, page_name)
