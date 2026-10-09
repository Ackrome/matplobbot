/* Progressive schedule controls, full lesson details, and keyboard/focus contracts. */
(() => {
    const byId=id=>document.getElementById(id),t=key=>window.MpbUI.t(key);
    const planner=byId('schedulePlanner'),controls=byId('scheduleControls');
    const options=byId('useShortNames').closest('.border-b');
    const settings=document.createElement('details');settings.id='schedule-display-options';settings.className='schedule-options';const summary=document.createElement('summary');summary.dataset.i18n='ux.displayOptions';summary.textContent=t('displayOptions');settings.append(summary);options.before(settings);settings.append(options);
    const actionRow=byId('calendarSyncOpenBtn').parentElement;const compare=document.createElement('button');compare.type='button';compare.className='ui-button';compare.dataset.i18n='ux.compare';compare.textContent=t('compare');compare.addEventListener('click',()=>{planner.open=!planner.open;compare.setAttribute('aria-expanded',String(planner.open));if(planner.open)planner.scrollIntoView({block:'start',behavior:'smooth'});});compare.setAttribute('aria-controls','schedulePlanner');compare.setAttribute('aria-expanded','false');actionRow.append(compare);
    byId('mainScheduleBlock').after(planner);planner.addEventListener('toggle',()=>compare.setAttribute('aria-expanded',String(planner.open)));
    const hint=document.createElement('p');hint.className='ui-muted schedule-search-hint';hint.dataset.i18n='ux.searchExample';hint.textContent=t('searchExample');byId('searchContainer').append(hint);
    function sync(){const selected=Boolean(window.schedulePageState?.entity?.id);document.body.classList.toggle('schedule-unselected',!selected);hint.hidden=selected;settings.hidden=!selected;actionRow.hidden=!selected;const dateRow=byId('scheduleTodayBtn').parentElement;dateRow.hidden=!selected;}
    window.addEventListener('mpb-schedule-state-change',sync);sync();
    const input=byId('groupSearch'),results=byId('searchResults');let active=-1;
    input.setAttribute('role','combobox');input.setAttribute('aria-autocomplete','list');input.setAttribute('aria-controls','searchResults');input.setAttribute('aria-expanded','false');results.setAttribute('role','listbox');
    const entries=()=>[...results.querySelectorAll('[data-search-option]')];
    const update=()=>{const open=!results.classList.contains('hidden');input.setAttribute('aria-expanded',String(open));if(!open){active=-1;input.removeAttribute('aria-activedescendant');}entries().forEach((node,i)=>{node.id=`schedule-option-${i}`;node.setAttribute('role','option');node.setAttribute('aria-selected',String(i===active));node.classList.toggle('search-active',i===active);});};
    new MutationObserver(update).observe(results,{childList:true,attributes:true,attributeFilter:['class']});
    input.addEventListener('input',()=>{active=-1;input.removeAttribute('aria-activedescendant');});
    input.addEventListener('keydown',event=>{const rows=entries();if(event.key==='Escape'){results.classList.add('hidden');update();event.stopPropagation();return;}if(['ArrowDown','ArrowUp'].includes(event.key)&&rows.length){event.preventDefault();results.classList.remove('hidden');active=(active+(event.key==='ArrowDown'?1:-1)+rows.length)%rows.length;update();input.setAttribute('aria-activedescendant',rows[active].id);rows[active].scrollIntoView({block:'nearest'});}if(event.key==='Enter'&&active>=0&&rows[active]){event.preventDefault();rows[active].click();results.classList.add('hidden');update();}});
    controls.classList.add('schedule-workspace-controls');
})();
