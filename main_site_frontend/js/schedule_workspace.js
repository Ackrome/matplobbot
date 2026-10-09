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
    let focusOrigin = null, inertNodes = [], previousOverflow = '', previousScroll = null;
    function calendarFocus(open) {
        const panel = byId('calendarSubscriptionSection');
        if (!panel) return;
        panel.setAttribute('role', open ? 'dialog' : 'region');
        panel.setAttribute('aria-modal', String(open));
        if (open && !focusOrigin) {
            focusOrigin = document.activeElement;
            previousOverflow = document.documentElement.style.overflow;
            previousScroll = { left: window.scrollX, top: window.scrollY };
            document.documentElement.style.overflow = 'hidden';
            for (const sibling of document.body.children) {
                if (sibling !== panel && sibling.id !== 'calendarSubscriptionBackdrop' && !sibling.inert) {
                    sibling.inert = true;
                    inertNodes.push(sibling);
                }
            }
            requestAnimationFrame(() => {
                if (panel.classList.contains('hidden')) return;
                panel.tabIndex = -1;
                (panel.querySelector('.calendar-close') || panel).focus({ preventScroll: true });
            });
        } else if (!open && focusOrigin) {
            inertNodes.forEach(node => { node.inert = false; });
            inertNodes = [];
            document.documentElement.style.overflow = previousOverflow;
            focusOrigin.focus?.({ preventScroll: true });
            window.scrollTo({ ...previousScroll, behavior: 'instant' });
            focusOrigin = null;
        }
    }
    document.addEventListener('keydown', event => {
        if (event.key !== 'Tab' || !focusOrigin) return;
        const panel = byId('calendarSubscriptionSection');
        const items = [...panel.querySelectorAll('button,a[href],input,select,textarea,summary,[tabindex="0"]')]
            .filter(node => {
                const closedSection = node.closest('details:not([open])');
                return !node.disabled && node.getClientRects().length
                    && (!closedSection || node === closedSection.querySelector('summary'));
            });
        if (!items.length) { event.preventDefault(); panel.focus(); return; }
        const first = items[0], last = items.at(-1);
        if (event.shiftKey && (document.activeElement === first || !panel.contains(document.activeElement))) {
            event.preventDefault(); last.focus();
        } else if (!event.shiftKey && (document.activeElement === last || !panel.contains(document.activeElement))) {
            event.preventDefault(); first.focus();
        }
    });
    window.MpbScheduleUX={calendarFocus};
    controls.classList.add('schedule-workspace-controls');
})();
