/* Browser regression for the real Studio asset transport, using synthetic owners. */
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import http from 'node:http';
import { fileURLToPath } from 'node:url';
import { chromium } from '@playwright/test';

const source = await fs.readFile(new URL('../main_site_frontend/js/studio.js', import.meta.url), 'utf8');
const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl6QAAAAABJRU5ErkJggg==', 'base64');
const requests = [];
const server = http.createServer((request, response) => {
    if (request.url.startsWith('/api/')) {
        requests.push({url:request.url, authorization:request.headers.authorization});
        if (request.headers.authorization !== 'Bearer synthetic-owner-token') {
            response.writeHead(401, {'Content-Type':'text/plain'}).end('Authentication required');
            return;
        }
        const active = request.url.includes('active.html');
        setTimeout(() => {
            response.writeHead(200, {
                'Content-Type':active?'application/octet-stream':'image/png',
                'Content-Disposition':active?'attachment':'inline',
                'Content-Security-Policy':"sandbox; default-src 'none'",
                'X-Content-Type-Options':'nosniff',
            });
            response.end(active?'<script>window.activeAssetExecuted=true</script>':png);
        }, request.url.includes('slow.png')?150:0);
        return;
    }
    response.writeHead(200, {'Content-Type':'text/html'}).end('<!doctype html><div id="preview"></div>');
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const origin = `http://127.0.0.1:${server.address().port}`;
let browser;
try {
    browser = await chromium.launch({headless:true});
    const page = await browser.newPage();
    await page.goto(origin);
    await page.evaluate(()=>localStorage.setItem('jwt_token','synthetic-owner-token'));
    // Load production functions without launching the unrelated editor/CDN bootstrap.
    await page.addScriptTag({content:source.replace(/\nrun\(initStudio\);\s*$/,'')});
    const result = await page.evaluate(async()=>{
        currentMode='project';currentProjectId=1;previewGeneration=1;
        const container=document.getElementById('preview');
        container.innerHTML='<img data-studio-asset="image.png">';
        await loadPreviewAssets(container,1,1);
        const image=container.querySelector('img');
        await image.decode();
        const success=image.src.startsWith('blob:') && image.naturalWidth===1;
        const previousUrl=image.src;
        clearPreviewAssetUrls();
        let revoked=false;
        try { await fetch(previousUrl); } catch { revoked=true; }

        container.innerHTML='<img data-studio-asset="active.html">';
        await loadPreviewAssets(container,1,1);
        const activeBlocked=!container.querySelector('img').getAttribute('src') && !window.activeAssetExecuted;

        container.innerHTML='<img data-studio-asset="slow.png">';
        const pending=loadPreviewAssets(container,1,1);
        currentProjectId=2;previewGeneration=2;
        await pending;
        const staleIgnored=!container.querySelector('img').getAttribute('src') && previewAssetUrls.size===0;
        return {success,revoked,activeBlocked,staleIgnored};
    });
    assert.deepEqual(result,{success:true,revoked:true,activeBlocked:true,staleIgnored:true});
    assert.equal(requests.length,3);
    for(const request of requests) {
        assert.equal(request.authorization,'Bearer synthetic-owner-token');
        assert.ok(!request.url.includes('token='));
    }
    await page.goto(`${origin}/api/studio/projects/1/assets/active.html?token=synthetic-owner-token`);
    assert.equal(await page.textContent('body'),'Authentication required');
    console.log(JSON.stringify({check:fileURLToPath(import.meta.url),...result,credentialFreeUrls:true}));
} finally {
    await browser?.close();
    await new Promise(resolve=>server.close(resolve));
}
