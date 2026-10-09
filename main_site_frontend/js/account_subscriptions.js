/* Account entry point for the shared calendar subscription manager. */
(() => {
    'use strict';
    const byId = id => document.getElementById(id);
    const t = (key, params = {}) => window.mpbI18n.t(`account.subscriptions.${key}`, key, params);
    let currentState = null, searchSequence = 0, profileSequence = 0, chosen = null;
    const host = window.MpbCalendarHost = {
        user: null, entity: null, modules: [], selectedModules: [],
        onState: renderState,
        onProfileSelected: loadProfileModules,
        openSchedule(profile) {
            const params = new URLSearchParams({type: profile.entity_type, id: profile.entity_id,
                name: profile.entity_name || profile.name, calendar: '1', profile: profile.id});
            location.href = `/schedule?${params}`;
        },
    };
    function node(tag, className = '', text) {
        const el = document.createElement(tag); el.className = className;
        if (text !== undefined) el.textContent = text;
        return el;
    }
    function action(label, handler, id, variant = '') {
        const button = node('button', `subscription-button ${variant}`, label);
        button.type = 'button'; button.id = id; button.addEventListener('click', handler);
        return button;
    }
    function link(label, href, className = 'subscription-button') {
        const el = node('a', className, label); el.href = href; return el;
    }
    function botUrl(payload) {
        const url = new URL(window.__MPB_BOT_DEEPLINK__ || 'https://t.me/matplobbot');
        url.search = ''; url.searchParams.set('start', payload); return url.href;
    }
    function updateBotLinks() {
        byId('subscriptions-bot-add').href = botUrl('web_subscribe');
        byId('subscriptions-bot-manage').href = botUrl('web_subscriptions');
    }
    function feedback(key) {
        byId('subscriptions-status').textContent = key ? t(key) : '';
        byId('subscriptions-status').dataset.message = key || '';
    }
    function renderState(state) {
        currentState = state;
        const list = byId('subscriptions-list');
        if (!list) return;
        const activeId = list.contains(document.activeElement) ? document.activeElement.id : '';
        list.replaceChildren(); list.setAttribute('aria-busy', String(state.loading));
        byId('subscriptions-add').disabled = state.loading || !host.user?.telegram_id;
        byId('subscriptions-refresh').disabled = state.loading;
        const custom = (state.profiles || []).filter(profile => profile.kind === 'custom');
        byId('subscriptions-count').textContent = state.loading ? t('loading') : t('count', {count: custom.length});
        if (!host.user) {
            list.append(node('p', 'subscription-note', t('signIn')), link(t('signInButton'), '/login?next=/account'));
        } else if (!host.user.telegram_id) {
            list.append(node('p', 'subscription-note', t('unlinked')), link(t('signInTelegram'), '/login?next=/account'));
        } else if (state.hasError) {
            list.append(node('p', 'subscription-note', t('error')), action(t('retry'), () => window.refreshCalendarSubscription(), 'subscriptions-retry'));
        } else if (state.loading && !state.profiles.length) {
            list.append(node('p', 'subscription-note', t('loading')));
        } else {
            if (!state.sync_enabled) list.append(node('p', 'subscription-warning', t('paused')));
            if (!custom.length) list.append(node('p', 'subscription-note', t('empty')));
            custom.forEach(profile => {
                const row = node('article', 'subscription-row');
                const heading = node('div', 'subscription-row-heading');
                heading.append(node('h3', '', getCalendarProfileTitle(profile)));
                const entityType = ['group','person','auditorium'].includes(profile.entity_type) ? profile.entity_type : 'source';
                heading.append(node('span', 'subscription-type', t(entityType)));
                row.append(heading, node('p', 'subscription-note', getCalendarProfileDescription(profile)));
                const buttons = node('div', 'subscription-actions');
                buttons.append(action(t('edit'), () => openProfile(profile, true), `subscription-edit-${profile.id}`),
                    action(t('calendar'), () => openProfile(profile, false), `subscription-calendar-${profile.id}`));
                if (profile.can_delete) buttons.append(action(t('delete'), () => window.deleteCalendarSubscriptionProfile(profile.id), `subscription-delete-${profile.id}`, 'subscription-delete'));
                else buttons.append(link(t('manageBot'), botUrl('web_subscriptions')));
                row.append(buttons); list.append(row);
            });
            if (state.profiles.some(profile => profile.id === 'all')) list.append(action(t('combined'), () => openProfile(state.profiles.find(profile => profile.id === 'all'), false), 'subscriptions-combined', 'subscription-link'));
        }
        list.querySelectorAll('button').forEach(button => { button.disabled = state.loading; });
        if (activeId) byId(activeId)?.focus({preventScroll:true});
    }
    async function openProfile(profile, edit) {
        host.panelMode = edit ? 'edit' : 'calendar';
        // Reset panel disclosures deliberately when entering a different account action.
        calendarDialogView.open.clear();
        const panel = byId('calendarSubscriptionSection');
        panel.querySelectorAll('details').forEach(item => { item.open = false; });
        if (edit) calendarDialogView.open.add('calendar-source');
        window.openCalendarSyncPanel();
        const alreadySelected = currentState?.selected_profile_id === profile.id;
        if (alreadySelected) await loadProfileModules(profile);
        else await window.selectCalendarSubscriptionProfile(profile.id);
        if (edit && isCalendarSyncPanelOpen) {
            const source = byId('calendar-source'); if (source) source.open = true;
        }
    }
    async function loadProfileModules(profile) {
        const sequence = ++profileSequence;
        host.entity = profile?.entity_id ? {type:profile.entity_type, id:profile.entity_id, name:profile.entity_name || profile.name} : null;
        host.modules = []; host.selectedModules = profile?.modules || [];
        host.modulesError = false; host.modulesLoading = Boolean(host.entity && profile.kind === 'custom');
        renderCalendarSubscription();
        if (!host.entity || profile.kind !== 'custom') return;
        try {
            const data = await window.ScheduleApi.loadScheduleData(host.entity);
            if (sequence !== profileSequence) return;
            host.modules = Array.isArray(data.available_modules) ? data.available_modules : [];
            host.modulesLoading = false;
            calendarProfileModuleDrafts.delete(profile.id);
            renderCalendarSubscription();
        } catch {
            // Saved filters remain intact; the shared dialog offers the schedule as a fallback.
            if (sequence === profileSequence) { host.modulesLoading = false; host.modulesError = true; renderCalendarSubscription(); }
        }
    }
    function clearSearch() {
        ++searchSequence; chosen = null;
        byId('subscription-search-results').replaceChildren();
        byId('subscription-search-button').disabled = false;
        byId('subscription-create').disabled = true;
        byId('subscription-choice').textContent = '';
    }
    const search = byId('subscription-search-form');
    search.addEventListener('submit', async event => {
        event.preventDefault(); clearSearch();
        const term = byId('subscription-query').value.trim();
        if (term.length < 2) { feedback('searchHint'); return; }
        const sequence = searchSequence;
        feedback('searching'); byId('subscription-search-button').disabled = true;
        try {
            const rows = await window.ScheduleApi.searchEntities(term, byId('subscription-type').value);
            if (sequence !== searchSequence) return;
            feedback(rows.length ? '' : 'noResults');
            rows.slice(0,20).forEach((entity, index) => {
                const button = action(entity.label, () => {
                    chosen = entity; byId('subscription-choice').textContent = t('chosen',{name:entity.label});
                    byId('subscription-create').disabled = false;
                    byId('subscription-search-results').querySelectorAll('button').forEach(el=>el.setAttribute('aria-pressed',String(el===button)));
                }, `subscription-result-${index}`, 'subscription-search-result');
                button.setAttribute('aria-pressed','false'); byId('subscription-search-results').append(button);
            });
        } catch { if (sequence === searchSequence) feedback('searchError'); }
        finally { if (sequence === searchSequence) byId('subscription-search-button').disabled = false; }
    });
    function invalidateSearch() { clearSearch(); byId('subscription-search-button').disabled = false; feedback(''); }
    byId('subscription-query').addEventListener('input', invalidateSearch);
    byId('subscription-type').addEventListener('change', invalidateSearch);
    byId('subscriptions-add').addEventListener('click', () => {
        byId('subscription-create-panel').hidden = false; byId('subscriptions-add').setAttribute('aria-expanded','true');
        byId('subscription-query').focus();
    });
    byId('subscription-cancel').addEventListener('click', () => {
        clearSearch(); byId('subscription-create-panel').hidden = true;
        byId('subscriptions-add').setAttribute('aria-expanded','false'); byId('subscriptions-add').focus(); feedback('');
    });
    byId('subscription-create').addEventListener('click', async () => {
        if (!chosen || currentState?.loading) return;
        const entity = chosen;
        byId('subscription-create').disabled = true;
        const result = await performCalendarMutation(`${CALENDAR_API_BASE}/cal/subscription/profiles`, {
            method:'POST', body:JSON.stringify({entity_type:entity.type, entity_id:String(entity.id), entity_name:entity.label, modules:[], lesson_mode:'all', timezone:'Europe/Moscow'}),
        });
        byId('subscription-create').disabled = false;
        if (result) {
            byId('subscription-create-panel').hidden = true; byId('subscriptions-add').setAttribute('aria-expanded','false');
            clearSearch(); feedback('created');
            const profile = result.profiles.find(item=>item.selected);
            if (profile) { byId(`subscription-edit-${profile.id}`)?.focus(); await openProfile(profile,true); }
        } else feedback('createFailed');
    });
    byId('subscriptions-refresh').addEventListener('click', () => window.refreshCalendarSubscription());
    window.addEventListener('mpb-language-change', () => {
        if (currentState) renderState(currentState);
        if (chosen) byId('subscription-choice').textContent = t('chosen',{name:chosen.label});
        feedback(byId('subscriptions-status').dataset.message);
        renderCalendarSubscription();
    });
    window.MpbAccountSubscriptions = { async init(user) {
        host.user = user; updateBotLinks(); await window.refreshCalendarSubscription();
    }};
})();
