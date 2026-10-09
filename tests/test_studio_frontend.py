"""Execute deterministic editor durability and safe-login regressions in Node."""

import shutil
import subprocess
import unittest
from pathlib import Path


@unittest.skipUnless(shutil.which("node"), "node is required for Studio browser-state tests")
class TestStudioFrontend(unittest.TestCase):
    def test_draft_durability_and_redirect_contracts(self):
        script = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const {create, accountScope} = require('./main_site_frontend/js/studio_session.js');
function memory() {
    const values = new Map();
    return {getItem:key=>values.get(key)||null,setItem:(key,value)=>values.set(key,value),removeItem:key=>values.delete(key)};
}
(async()=>{
    const storage=memory(), sent=[];
    let fail=true;
    const state=create({storage,scope:'alice',save:async record=>{if(fail)throw Error('HTTP 500');sent.push(record);}});
    state.open({projectId:1,fileId:11,content:'saved A'});
    state.edit('dirty A');
    await assert.rejects(state.flush(),/HTTP 500/);
    assert.equal(state.dirty(),true);
    const reloaded=create({storage,scope:'alice',save:async()=>{}});
    assert.equal(reloaded.open({projectId:1,fileId:11,content:'saved A'}).content,'dirty A');
    assert.equal(create({storage,scope:'bob',save:async()=>{}}).open({projectId:1,fileId:11,content:'saved A'}).content,'saved A');
    fail=false;await state.flush();
    assert.equal(sent[0].projectId,1);assert.equal(sent[0].fileId,11);assert.equal(sent[0].content,'dirty A');
    state.open({projectId:2,fileId:22,content:'B'});assert.equal(state.dirty(),false);
    assert.equal(reloaded.open({projectId:1,fileId:11,content:'dirty A'}).recovered,false);

    let release, calls=0;const ordered=[];
    const racing=create({storage:memory(),scope:'race',save:async record=>{ordered.push(record.content);if(calls++===0)await new Promise(resolve=>{release=resolve;});}});
    racing.open({projectId:1,fileId:1,content:'zero'});racing.edit('one');
    const first=racing.flush();await new Promise(resolve=>setImmediate(resolve));
    racing.edit('two');const second=racing.flush();release();await Promise.all([first,second]);
    assert.deepEqual(ordered,['one','two']);assert.equal(racing.dirty(),false);

    const conflictStore=memory();const conflict=create({storage:conflictStore,scope:'conflict',save:async()=>{throw Error('must not save unresolved conflict');}});
    conflict.open({projectId:1,fileId:1,content:'old server'});conflict.edit('local work');
    const next=conflict.open({projectId:1,fileId:1,content:'new server'});
    assert.equal(next.conflict,true);assert.equal(next.content,'new server');await conflict.flush();
    assert.equal(conflict.resolveConflict(true).content,'local work');
    const quick=create({storage,scope:'quick',save:async()=>{throw Error('quick must remain local');}});
    quick.open({type:'latex',content:'template'});quick.edit('my formula');await quick.flush();
    quick.open({type:'markdown',content:'md'});assert.equal(quick.open({type:'latex',content:'template'}).content,'my formula');
    let warnings=0;const unavailable=create({storage:{getItem(){throw Error('denied');},setItem(){throw Error('quota');},removeItem(){}},scope:'disabled',save:async()=>{},onStorageError:()=>warnings++});
    unavailable.open({projectId:1,fileId:1,content:'base'});unavailable.edit('survives');await unavailable.flush();assert.equal(warnings,1);assert.equal(unavailable.snapshot().content,'survives');
    const encoded=Buffer.from(JSON.stringify({sub:'42'})).toString('base64url');assert.equal(accountScope(`x.${encoded}.y`),'42');

    const auth=fs.readFileSync('main_site_frontend/js/auth.js','utf8');
    const start=auth.indexOf('function getAuthReturnPath('),end=auth.indexOf('document.querySelectorAll(',start);
    const context={URL,URLSearchParams};vm.createContext(context);vm.runInContext(auth.slice(start,end),context);
    const redirect=raw=>context.getAuthReturnPath('?next='+encodeURIComponent(raw),'https://example.com');
    assert.equal(redirect('/studio?project=7#code'),'/studio?project=7#code');
    for(const raw of ['https://evil.test','//evil.test','/\\evil.test','/login','/register.html','javascript:alert(1)','/\n/evil.test'])assert.equal(redirect(raw),'/schedule',raw);
    console.log('durability, serial save, draft recovery, conflict, account isolation, storage failure and safe redirect passed');
})().catch(error=>{console.error(error);process.exit(1);});
"""
        result = subprocess.run(
            [shutil.which("node"), "-e", script],
            cwd=Path(__file__).resolve().parents[1],
            text=True,
            encoding="utf-8",
            capture_output=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
