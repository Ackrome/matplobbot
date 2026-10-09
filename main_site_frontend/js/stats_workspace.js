(() => {
    const main=document.querySelector('main'),insights=document.getElementById('outcomeInsights');
    const heading=document.createElement('h1');heading.className='ui-heading';heading.dataset.i18n='ux.adminTitle';heading.textContent=window.MpbUI.t('adminTitle');
    const nav=document.createElement('div');nav.className='ui-row stats-workspace-nav';nav.setAttribute('role','group');nav.setAttribute('aria-label',window.MpbUI.t('adminTitle'));
    const setMode=mode=>{document.body.dataset.statsMode=mode;nav.querySelectorAll('button').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.mode===mode)));if(mode==='manage')document.getElementById('statsViewModulesBtn').click();else document.getElementById('statsViewDashboardBtn').click();if(mode!=='manage')insights.open=true;};
    for(const [mode,key] of [['health','serviceHealth'],['usage','usage'],['manage','management']]){const b=document.createElement('button');b.type='button';b.className='ui-button';b.dataset.mode=mode;b.dataset.i18n='ux.'+key;b.textContent=window.MpbUI.t(key);b.addEventListener('click',()=>setMode(mode));nav.append(b);}main.prepend(heading,nav);setMode('health');
    const bar=document.getElementById('mobileActionBar');bar.classList.remove('fixed');bar.classList.add('stats-context-actions');bar.removeAttribute('style');
    const diagnostics=document.getElementById('mobileActionDiagnostics');diagnostics.classList.add('ui-button');
    const sync=()=>{const failed=!document.getElementById('globalErrorBanner').classList.contains('hidden')||!document.getElementById('partialDegradationBanner').classList.contains('hidden');document.getElementById('mobileActionRetry').hidden=!failed;document.getElementById('mobileActionReset').hidden=document.body.dataset.statsMode!=='usage';};
    for(const id of ['globalErrorBanner','partialDegradationBanner'])new MutationObserver(sync).observe(document.getElementById(id),{attributes:true,attributeFilter:['class']});nav.addEventListener('click',sync);sync();
})();
