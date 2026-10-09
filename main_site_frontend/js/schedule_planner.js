/* Bounded comparison of explicit schedules; no assumption about real room occupancy. */
(() => {
    const panel = document.getElementById('schedulePlanner');
    if (!panel) return;
    const base = window.getMpbApiBase ? window.getMpbApiBase() : '/api';
    const byId = id => document.getElementById(id);
    const tr = (key, fallback, params) => window.mpbI18n?.t(key, fallback, params) || fallback;
    const storageKey = 'mpb-schedule-plan-v1';
    let saved;
    try { saved = JSON.parse(localStorage.getItem(storageKey) || 'null'); } catch {}
    const entities = Array.isArray(saved?.entities) ? saved.entities.filter(e=>['group','person','auditorium'].includes(e.entity_type)&&typeof e.entity_id==='string').slice(0,6) : [];
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
    const fields=['planStart','planEnd','planDayStart','planDayEnd','planMin'];
    for(const id of fields) if(typeof saved?.[id]==='string') byId(id).value=saved[id];
    function persist(){try{localStorage.setItem(storageKey,JSON.stringify({entities,...Object.fromEntries(fields.map(id=>[id,byId(id).value]))}));}catch{}}
    function validate(){
        for(const id of fields){byId(id).setCustomValidity('');byId(id).removeAttribute('aria-invalid');byId(id+'Error')?.remove();}
        const days=(Date.parse(byId('planEnd').value)-Date.parse(byId('planStart').value))/86400000;
        const invalid=days<0||days>13?'planEnd':byId('planDayStart').value>=byId('planDayEnd').value?'planDayEnd':null;
        if(invalid){const message=tr(invalid==='planEnd'?'ux.planDateError':'ux.planTimeError','Check the selected range.');const input=byId(invalid);input.setCustomValidity(message);input.setAttribute('aria-invalid','true');const error=document.createElement('p');error.id=invalid+'Error';error.className='plan-field-error';error.textContent=message;input.setAttribute('aria-describedby',error.id);input.after(error);return false;}return true;
    }
    function textItem(parent, text) {
        const item = document.createElement('li'); item.textContent = text; parent.append(item); return item;
    }
    function renderEntities() {
        const list = byId('planEntities'); list.replaceChildren();
        entities.forEach((entity, index) => {
            const modules=entity.selected_modules==null?tr('ux.allModules','All modules'):entity.selected_modules.length?entity.selected_modules.join(', '):tr('ux.commonOnly','Common classes only');
            const item = textItem(list, `${entity.entity_name || entity.entity_id} · ${modules} · ${tr(entity.lesson_mode==='exams_only'?'ux.examsOnly':'ux.allClasses','All classes')} `);
            const button = document.createElement('button'); button.type = 'button';
            button.textContent = tr('plan.remove', 'Remove');
            button.setAttribute('aria-label', `${button.textContent}: ${entity.entity_name || entity.entity_id}`);
            button.addEventListener('click', () => { entities.splice(index, 1); invalidatePlan(); renderEntities(); });
            item.append(button);
        });
        persist();
    }
    function addEntity(entity) {
        const existing=entities.findIndex(item => item.entity_type === entity.entity_type && item.entity_id === entity.entity_id);
        if(existing>=0){entities[existing]=entity;invalidatePlan();renderEntities();return;}
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
        renderTimeline(target);
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
        if(!validate()){byId('planForm').reportValidity();return;}
        persist();
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
    fields.forEach(id=>byId(id).addEventListener('input',()=>{invalidatePlan();validate();persist();}));
    function renderTimeline(target){
        const wrapper=document.createElement('section');wrapper.className='plan-timeline';
        const label=document.createElement('label');label.textContent=tr('ux.timeline','Timetable comparison');
        const select=document.createElement('select');select.className='ui-input';select.setAttribute('aria-label',label.textContent);
        const start=lastResult.start_date||byId('planStart').value,end=lastResult.end_date||byId('planEnd').value;
        for(let day=new Date(start+'T12:00:00Z');day<=new Date(end+'T12:00:00Z');day.setUTCDate(day.getUTCDate()+1)){const value=day.toISOString().slice(0,10);select.add(new Option(new Intl.DateTimeFormat(window.mpbI18n.getLanguage(),{day:'numeric',month:'long',weekday:'short',timeZone:'UTC'}).format(day),value));}
        const hint=document.createElement('p');hint.className='ui-muted';hint.textContent=tr('ux.timelineHint','Scroll the timeline horizontally. Select a class or free window for details.');
        const plot=document.createElement('div');label.append(select);wrapper.append(label,hint,plot);target.append(wrapper);
        const minutes=value=>Number(value.slice(11,13))*60+Number(value.slice(14,16));
        const draw=()=>{plot.replaceChildren();const left=byId('planDayStart').value.split(':').map(Number),right=byId('planDayEnd').value.split(':').map(Number),min=left[0]*60+left[1],max=right[0]*60+right[1];
            const axis=document.createElement('div');axis.className='plan-axis';axis.textContent=`${byId('planDayStart').value} — ${byId('planDayEnd').value} · ${lastResult.timezone}`;plot.append(axis);
            const rows=(lastResult.sources||[]).map(source=>({title:source.entity_name||source.entity_id,items:(lastResult.lessons||[]).filter(l=>l.sources?.includes(`${source.entity_type}:${source.entity_id}`)),free:false}));
            if(!lastResult.incomplete)rows.push({title:tr('plan.free','Common free windows'),items:lastResult.free_windows||[],free:true});
            for(const row of rows){const line=document.createElement('div');line.className='plan-lane';const title=document.createElement('h4');title.textContent=row.title;const track=document.createElement('div');track.className='plan-track';let lanes=[];
                for(const item of row.items.filter(i=>i.start.slice(0,10)===select.value).sort((a,b)=>a.start.localeCompare(b.start))){const a=Math.max(min,minutes(item.start)),b=Math.min(max,minutes(item.end));if(b<=a)continue;let lane=lanes.findIndex(end=>end<=a);if(lane<0)lane=lanes.length;lanes[lane]=b;
                    const button=document.createElement('button');button.type='button';button.className=`plan-bar ${row.free?'plan-free':(lastResult.conflicts||[]).some(c=>c.lessons.some(l=>l.id===item.id))?'plan-conflict':''}`;button.style.left=`${(a-min)/(max-min)*100}%`;button.style.width=`${(b-a)/(max-min)*100}%`;button.style.top=`${lane*48+4}px`;button.textContent=row.free?`${item.duration_minutes} ${tr('plan.minutes','min')}`:item.discipline;button.title=`${timeRange(item)} · ${button.textContent}`;
                    button.addEventListener('click',()=>{const content=document.createElement('div');for(const text of [timeRange(item),item.auditorium,item.lecturer])if(text){const p=document.createElement('p');p.textContent=text;content.append(p);}MpbUI.dialog({title:item.discipline||row.title,content,actions:[{label:tr('ux.close','Close'),value:'close'}]});});track.append(button);
                }track.style.height=`${Math.max(1,lanes.length)*48+8}px`;if(!track.children.length){const empty=document.createElement('span');empty.className='ui-muted';empty.textContent=tr('ux.noIntervals','No intervals in this range');track.append(empty);}line.append(title,track);plot.append(line);
            }
        };select.addEventListener('change',draw);draw();
    }
    renderEntities();
    window.mpbI18n?.registerTranslator(() => {
        panel.querySelectorAll('[data-plan-i18n]').forEach(node=>{node.textContent=tr(node.dataset.planI18n,node.textContent);});
        renderEntities();renderResult();
    });
})();
