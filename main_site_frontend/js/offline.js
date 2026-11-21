(() => {
    document.getElementById('offline-retry').addEventListener('click',()=>location.reload());
    const saved = window.MpbSessionOffline.read();
    if (saved) {
        const link = document.getElementById("offline-session");
        link.href = window.MpbSessionOffline.url(saved);
        link.hidden = false;
    }
    let status='offlineCache';const translate=()=>document.getElementById('offline-status').textContent=window.MpbUI.t(status);window.addEventListener('online',()=>{status='onlineAgain';translate();});window.addEventListener('mpb-language-change',translate);
    (async()=>{await window.mpbI18n.ready;for(const name of ['schedule','studio']){let cached=false;try{cached=Boolean(await caches.match('/'+name)||await caches.match('/'+name+'.html'));}catch{}const link=document.getElementById('offline-'+name);link.hidden=!cached;}document.getElementById('offline-status').textContent=window.MpbUI.t('offlineCache');})();
})();
