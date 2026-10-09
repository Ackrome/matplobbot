/* Admin-only outcome metrics. Values always come from authenticated server aggregates. */
(() => {
    const panel = document.getElementById('outcomeInsights');
    if (!panel) return;
    const base=window.getMpbApiBase ? window.getMpbApiBase() : '/api';
    const tr=(key,fallback,params)=>window.mpbI18n?.t(key,fallback,params)||fallback;
    let latest=null, requestSerial=0, authSerial=0;
    const byId=id=>document.getElementById(id);
    const localTime=value=>new Date(value).toLocaleString(window.mpbI18n?.getLanguage() || 'ru');
    function cell(row,text,header=false) {const node=document.createElement(header?'th':'td');node.textContent=String(text);row.append(node);}
    function table(parent,headers,rows) {
        const wrapper=document.createElement('div');wrapper.className='mpb-scroll';
        const element=document.createElement('table'),head=document.createElement('thead'),body=document.createElement('tbody'),row=document.createElement('tr');
        headers.forEach(value=>cell(row,value,true));head.append(row);
        rows.forEach(values=>{const row=document.createElement('tr');values.forEach(value=>cell(row,value));body.append(row);});
        element.append(head,body);wrapper.append(element);parent.append(wrapper);
    }
    function render() {
        panel.querySelectorAll('[data-insights-i18n]').forEach(node=>{node.textContent=tr(node.dataset.insightsI18n,node.textContent);});
        const operations=byId('insightOperations'),product=byId('insightProduct');operations.replaceChildren();product.replaceChildren();
        if (!latest) return;
        const [ops,metrics]=latest;
        if (!ops.available) {const warning=document.createElement('p');warning.textContent=tr('insights.unavailable','Operational heartbeats unavailable.');operations.append(warning);}
        table(operations,[tr('insights.operation','Operation'),tr('insights.state','State'),tr('insights.lastSuccess','Last success'),tr('insights.duration','Duration, s')],
            (ops.operations||[]).map(item=>[
                tr('insights.operation.'+item.name,item.name),tr('insights.status.'+item.status,item.status),
                item.last_success ? localTime(item.last_success) : '—',item.last_duration_seconds ?? '—',
            ]));
        const queue=document.createElement('p');
        queue.textContent=tr('insights.outbox','Pending: {pending}; processing: {processing}; failed: {failed}; oldest pending: {age} min.',{
            pending:ops.deliveries?.counts?.pending||0,processing:ops.deliveries?.counts?.processing||0,failed:ops.deliveries?.counts?.failed||0,
            age:ops.deliveries?.oldest_pending_age_seconds==null?'—':Math.round(ops.deliveries.oldest_pending_age_seconds/60),
        });operations.append(queue);
        const freshness=document.createElement('p');freshness.textContent=tr('insights.freshness','Last cache write (not all schedules): {time}',{time:ops.schedule_last_checked_at?localTime(ops.schedule_last_checked_at):'—'});operations.append(freshness);
        table(product,[tr('insights.metric','Metric'),tr('insights.value','Value')],[
            [tr('insights.active','Active accounts'),metrics.active_users],
            [tr('insights.returning','Accounts active on two or more UTC days'),metrics.returning_users],
            [tr('insights.searchSuccess','Searches with results'),metrics.counts.search_succeeded],
            [tr('insights.searchRate','Search success rate'),metrics.search_success_rate==null?'—':`${Math.round(metrics.search_success_rate*100)}%`],
            [tr('insights.searchEmpty','Searches with no results'),metrics.counts.search_empty],
            [tr('insights.searchFailed','Searches with unavailable sources'),metrics.counts.search_failed],
            [tr('insights.subscription','First recorded subscriptions'),metrics.counts.subscription_created],
            [tr('insights.compile','Successful compile results opened'),metrics.counts.studio_succeeded],
            [tr('insights.compileFailed','Failed compile results opened'),metrics.counts.studio_failed],
        ]);
        table(product,[tr('insights.day','UTC date'),tr('insights.active','Active accounts'),tr('insights.events','Outcome events')],
            metrics.daily.map(day=>[day.date,day.active_users,day.events]));
        byId('insightStatus').textContent=tr('insights.updated','Updated: {time}',{time:localTime(ops.checked_at)});
    }
    async function load() {
        if (panel.hidden) return;
        const serial=++requestSerial;
        const token=localStorage.getItem('jwt_token');
        const isCurrent=()=>serial===requestSerial && token===localStorage.getItem('jwt_token');
        byId('insightRefresh').disabled=true;
        byId('insightStatus').textContent=tr('insights.loading','Loading…');
        try {
            const responses=await Promise.all(['/insights/operations',`/insights/product?days=${byId('insightDays').value}`].map(url=>fetch(base+url,{headers:{Authorization:`Bearer ${token}`},cache:'no-store'})));
            if (!isCurrent()) return;
            if (responses.some(response=>[401,403].includes(response.status))) {panel.hidden=true;latest=null;render();return;}
            if (responses.some(response=>!response.ok)) throw new Error('metrics');
            const data=await Promise.all(responses.map(response=>response.json()));
            if (!isCurrent()) return;
            latest=data;render();
        } catch {if(isCurrent())byId('insightStatus').textContent=tr('insights.failed','Could not load metrics. Please retry.');}
        finally {if(isCurrent())byId('insightRefresh').disabled=false;}
    }
    async function authorize() {
        const serial=++authSerial;
        requestSerial+=1;latest=null;panel.hidden=true;render();
        byId('insightStatus').textContent='';byId('insightRefresh').disabled=false;
        try {
            const token=localStorage.getItem('jwt_token');if(!token)return;
            const response=await fetch(base+'/auth/me',{headers:{Authorization:`Bearer ${token}`},cache:'no-store'});
            if(!response.ok) return;
            const user=await response.json();
            if(serial!==authSerial || token!==localStorage.getItem('jwt_token'))return;
            if(user.role==='admin') {panel.hidden=false;if(panel.open)load();}
        } catch { /* Existing stats auth UI handles sign-in; no private values retained here. */ }
    }
    panel.addEventListener('toggle',()=>{if(panel.open&&!latest)load();});
    byId('insightRefresh').addEventListener('click',load);
    byId('insightDays').addEventListener('change',load);
    window.addEventListener('mpb-auth-token-changed',authorize);
    window.addEventListener('storage',event=>{if(event.key==='jwt_token')authorize();});
    window.mpbI18n?.registerTranslator(render);
    authorize();
})();
