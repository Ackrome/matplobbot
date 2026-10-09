/* Bounded comparison of explicit schedules; no assumption about real room occupancy. */
(() => {
    const panel = document.getElementById('schedulePlanner');
    if (!panel) return;
    const base = window.getMpbApiBase ? window.getMpbApiBase() : '/api';
    const byId = id => document.getElementById(id);
    const tr = (key, fallback, params) => window.mpbI18n?.t(key, fallback, params) || fallback;
    const entities = [];
    let lastResult = null;
    let searchSerial = 0;
    let planSerial = 0;
    function invalidatePlan() {
        planSerial += 1; lastResult = null; renderResult();
        byId('planRun').disabled = false; byId('planStatus').textContent = '';
    }
    const status = (key, fallback) => { byId('planStatus').textContent = tr(key, fallback); };
    const today = new Intl.DateTimeFormat('en-CA', {timeZone: 'Europe/Moscow', year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
    byId('planStart').value = today;
    byId('planEnd').value = today;
    function textItem(parent, text) {
        const item = document.createElement('li'); item.textContent = text; parent.append(item); return item;
    }
    function renderEntities() {
        const list = byId('planEntities'); list.replaceChildren();
        entities.forEach((entity, index) => {
            const item = textItem(list, `${entity.entity_name || entity.entity_id} `);
            const button = document.createElement('button'); button.type = 'button';
            button.textContent = tr('plan.remove', 'Remove');
            button.setAttribute('aria-label', `${button.textContent}: ${entity.entity_name || entity.entity_id}`);
            button.addEventListener('click', () => { entities.splice(index, 1); invalidatePlan(); renderEntities(); });
            item.append(button);
        });
    }
    function addEntity(entity) {
        if (entities.some(item => item.entity_type === entity.entity_type && item.entity_id === entity.entity_id)) return;
        if (entities.length >= 6) { status('plan.limit', 'Choose up to six schedules.'); return; }
        entities.push(entity); invalidatePlan(); renderEntities(); status('plan.added', 'Schedule added.');
    }
    byId('planAddCurrent').addEventListener('click', () => {
        const state = window.schedulePageState;
        const entity = state?.entity;
        if (!entity?.id) { status('plan.choose', 'Open a schedule or use the search below.'); return; }
        addEntity({entity_type: entity.type, entity_id: String(entity.id), entity_name: entity.name,
            selected_modules: state.selectedModules ?? null, lesson_mode: state.lessonMode || 'all'});
    });
    byId('planSearchButton').addEventListener('click', async () => {
        const term = byId('planSearch').value.trim();
        if (term.length < 2) { status('plan.queryShort', 'Enter at least two characters.'); return; }
        const serial = ++searchSerial;
        status('plan.loading', 'Loading…');
        try {
            const response = await fetch(`${base}/schedule/search?${new URLSearchParams({term, type:'all'})}`);
            if (!response.ok) throw new Error('search');
            const data = await response.json();
            if (serial !== searchSerial) return;
            const results = Array.isArray(data) ? data : data.results || [];
            const target = byId('planSearchResults'); target.replaceChildren();
            for (const result of results.slice(0, 20)) {
                const type = result.type || result.entity_type;
                const id = result.id ?? result.entity_id;
                if (!['group','person','auditorium'].includes(type) || id == null) continue;
                const button = document.createElement('button'); button.type='button';
                const name = result.label || result.name || result.entity_name || String(id);
                button.textContent = name;
                button.addEventListener('click', () => addEntity({entity_type:type,entity_id:String(id),entity_name:name}));
                target.append(button);
            }
            status(results.length ? 'plan.selectResult' : 'plan.noResults', results.length ? 'Select a schedule to add.' : 'No schedules found.');
        } catch { if (serial === searchSerial) status('plan.failed', 'Could not load data. Please retry.'); }
    });
    byId('planSearch').addEventListener('keydown', event => {
        if (event.key === 'Enter') { event.preventDefault(); byId('planSearchButton').click(); }
    });
    const timeRange = item => {
        const formatter = new Intl.DateTimeFormat(window.mpbI18n?.getLanguage() || 'en', {
            timeZone:lastResult?.timezone || 'Europe/Moscow', month:'short',day:'numeric',hour:'2-digit',minute:'2-digit',hour12:false,
        });
        return `${formatter.format(new Date(item.start))} – ${formatter.format(new Date(item.end))}`;
    };
    function renderResult() {
        const target = byId('planResult'); target.replaceChildren();
        if (!lastResult) return;
        if (lastResult.incomplete) {
            const warning = document.createElement('p'); warning.className='mpb-warning';
            warning.textContent=tr('plan.incomplete', 'Some sources are stale or unavailable. Free windows are not shown; conflicts may be incomplete.'); target.append(warning);
        }
        for (const [key, fallback, values, format] of [
            ['plan.conflicts','Conflicts',lastResult.conflicts, item => `${timeRange(item)}: ${item.lessons.map(lesson=>lesson.discipline).join(' / ')}`],
            ['plan.free','Common free windows',lastResult.free_windows, item => `${timeRange(item)} · ${item.duration_minutes} ${tr('plan.minutes','min')}`],
        ]) {
            const title=document.createElement('h3');title.textContent=tr(key,fallback);target.append(title);
            const list=document.createElement('ul');target.append(list);
            if (!values?.length) textItem(list,tr('plan.none','None for the selected period.'));
            for (const item of values || []) textItem(list,format(item));
        }
        const sourceTitle=document.createElement('h3');sourceTitle.textContent=tr('plan.sources','Source checks');target.append(sourceTitle);
        const sources=document.createElement('ul');target.append(sources);
        for (const source of lastResult.sources || []) textItem(sources,`${source.entity_name || source.entity_id}: ${tr('plan.freshness.'+source.freshness,source.freshness)} · ${source.source_checked_at ? new Date(source.source_checked_at).toLocaleString(window.mpbI18n?.getLanguage() || 'ru') : tr('plan.unknown','not verified')}`);
    }
    byId('planForm').addEventListener('submit', async event => {
        event.preventDefault();
        if (!entities.length) { status('plan.choose','Choose at least one schedule.'); return; }
        const serial=++planSerial;
        const button=byId('planRun'); button.disabled=true; lastResult=null;renderResult();status('plan.loading','Loading…');
        try {
            const response=await fetch(`${base}/schedule/plan`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
                entities, start_date:byId('planStart').value,end_date:byId('planEnd').value,timezone:'Europe/Moscow',
                day_start:byId('planDayStart').value,day_end:byId('planDayEnd').value,min_free_minutes:Number(byId('planMin').value),
            })});
            if (serial !== planSerial) return;
            if (!response.ok) { status(response.status===422?'plan.invalid':'plan.failed',response.status===422?'Check dates (up to 14 days) and time bounds.':'Could not load data. Please retry.');return; }
            const result=await response.json();
            if (serial !== planSerial) return;
            lastResult=result;renderResult();status('plan.done','Comparison complete.');
        } catch {if(serial===planSerial)status('plan.failed','Could not load data. Please retry.');}
        finally {if(serial===planSerial)button.disabled=false;}
    });
    ['planStart','planEnd','planDayStart','planDayEnd','planMin'].forEach(id=>byId(id).addEventListener('input',invalidatePlan));
    window.mpbI18n?.registerTranslator(() => {
        panel.querySelectorAll('[data-plan-i18n]').forEach(node=>{node.textContent=tr(node.dataset.planI18n,node.textContent);});
        renderEntities();renderResult();
    });
})();
