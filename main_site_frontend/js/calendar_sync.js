const CALENDAR_PLATFORM_KEY = "mpb_calendar_sync_platform";
const CALENDAR_REVEALED_PROFILES_KEY = "mpb_calendar_sync_revealed_profiles";
const CALENDAR_BOT_DEEPLINK =
    window.__MPB_BOT_DEEPLINK__ || "https://t.me/matplobbot?start=calendar_sync";
const calendarSyncLaunchParams = new URLSearchParams(window.location.search);
const shouldFocusCalendarSyncPanel =
    calendarSyncLaunchParams.get('calendar') === '1' ||
    calendarSyncLaunchParams.get('panel') === 'calendar';
let calendarPlatform = loadCalendarPlatform();
let revealedCalendarProfileIds = loadRevealedCalendarProfileIds();
let isCalendarSyncPanelOpen = shouldFocusCalendarSyncPanel;
window.calendarCurrentViewMode = 'all';

function createDefaultCalendarSubscriptionState() {
    return {
        loading: false,
        hasError: false,
        justReset: false,
        enabled: false,
        sync_enabled: true,
        selected_profile_id: 'all',
        profile_limit: 0,
        timezone_options: [{ value: 'Europe/Moscow', label: 'GMT+3 (Moscow)' }],
        eligibility: {
            available: false,
            has_telegram_link: false,
            has_active_subscriptions: false,
            reasons:[],
            detail: ''
        },
        source_summary: {
            total_subscriptions: 0,
            active_subscriptions: 0,
            active_entities: 0
        },
        profiles:[]
    };
}
let calendarSubscriptionState = createDefaultCalendarSubscriptionState();
const calendarProfileModuleDrafts = new Map();

function loadCalendarPlatform() {
    try {
        const saved = localStorage.getItem(CALENDAR_PLATFORM_KEY);
        if (saved === 'apple' || saved === 'google' || saved === 'outlook') return saved;
    } catch (error) {}
    return 'apple';
}
function setCalendarPlatform(nextPlatform) {
    calendarPlatform = nextPlatform === 'google' || nextPlatform === 'outlook' ? nextPlatform : 'apple';
    try {
        localStorage.setItem(CALENDAR_PLATFORM_KEY, calendarPlatform);
    } catch (error) {}
    renderCalendarSubscription();
}
function loadRevealedCalendarProfileIds() {
    try {
        const saved = JSON.parse(localStorage.getItem(CALENDAR_REVEALED_PROFILES_KEY) || '[]');
        return new Set(Array.isArray(saved) ? saved :[]);
    } catch (error) {
        return new Set();
    }
}
function persistRevealedCalendarProfileIds() {
    try {
        localStorage.setItem(
            CALENDAR_REVEALED_PROFILES_KEY,
            JSON.stringify(Array.from(revealedCalendarProfileIds))
        );
    } catch (error) {}
}
function setCalendarDrawerVisibility(open) {
    const container = document.getElementById('calendarSubscriptionSection');
    const backdrop = document.getElementById('calendarSubscriptionBackdrop');
    if (!container) return;
    container.classList.toggle('hidden', !open);
    container.classList.toggle('is-open', open);
    container.setAttribute('aria-hidden', String(!open));
    backdrop?.classList.toggle('hidden', !open);
    backdrop?.classList.toggle('is-open', open);
    document.querySelectorAll('[data-calendar-sync-trigger]').forEach(button => {
        button.setAttribute('aria-expanded', String(open));
        button.setAttribute('aria-haspopup', 'dialog');
        button.setAttribute('aria-controls', 'calendarSubscriptionSection');
    });
    if (!open) window.MpbScheduleUX?.calendarFocus(false);
}

function renderCalendarBotLink(className = '') {
    return `
        <a href="${escapeHtml(CALENDAR_BOT_DEEPLINK)}" target="_blank" rel="noopener"
            class="inline-flex items-center justify-center rounded-xl px-3 py-2 text-center text-xs font-bold leading-tight whitespace-normal transition-colors ${className}">
            ${escapeHtml(t('schedule.calendar.botManage', 'Open in bot'))}
        </a>
    `;
}

function getCalendarLessonModeLabel(profileOrMode) {
    const mode = typeof profileOrMode === 'string' ? profileOrMode : profileOrMode?.lesson_mode;
    return mode === 'exams_only'
        ? t('schedule.calendar.mode.exams', 'Exams only')
        : t('schedule.calendar.mode.all', 'All classes');
}

function getCalendarModulesLabel(profile) {
    return profile?.modules?.length
        ? t('schedule.calendar.currentView.someModules', 'Selected modules: {count}', { count: profile.modules.length })
        : t('schedule.calendar.currentView.allModules', 'All modules');
}

function getCalendarProfileModules(profile) {
    return Array.isArray(profile?.modules)
        ? profile.modules.map((module) => String(module).trim()).filter(Boolean)
        : [];
}

function isCalendarProfileOnCurrentEntity(profile) {
    return Boolean(
        profile?.kind === 'custom' &&
        currentEntity?.id &&
        profile.entity_type === currentEntity.type &&
        String(profile.entity_id) === String(currentEntity.id)
    );
}

function getCalendarAvailableModulesForProfile(profile) {
    const savedModules = getCalendarProfileModules(profile);
    const currentModules = isCalendarProfileOnCurrentEntity(profile) && Array.isArray(allAvailableModules)
        ? allAvailableModules.map((module) => String(module).trim()).filter(Boolean)
        : [];
    return Array.from(new Set([...currentModules, ...savedModules])).sort((a, b) => a.localeCompare(b));
}

function getCalendarProfileModuleDraft(profile) {
    if (!profile?.id) return new Set();
    const availableModules = getCalendarAvailableModulesForProfile(profile);
    if (!calendarProfileModuleDrafts.has(profile.id)) {
        const savedModules = getCalendarProfileModules(profile);
        calendarProfileModuleDrafts.set(
            profile.id,
            new Set(savedModules.length ? savedModules : availableModules)
        );
    }
    return new Set(calendarProfileModuleDrafts.get(profile.id) || []);
}

function getCalendarProfileModulePayload(profile) {
    const availableModules = getCalendarAvailableModulesForProfile(profile);
    const draftModules = Array.from(getCalendarProfileModuleDraft(profile)).filter(Boolean);
    if (!availableModules.length) return getCalendarProfileModules(profile);
    const availableSet = new Set(availableModules);
    const normalized = draftModules.filter((module) => availableSet.has(module));
    if (!normalized.length || normalized.length === availableModules.length) return [];
    return normalized.sort((a, b) => a.localeCompare(b));
}

window.openCalendarSyncPanel = function() {
    isCalendarSyncPanelOpen = true;
    window.MpbUI?.start('calendar_connected');
    renderCalendarSubscription();
}

window.closeCalendarSyncPanel = function() {
    isCalendarSyncPanelOpen = false;
    setCalendarDrawerVisibility(false);
}

window.toggleCalendarSyncPanel = function() {
    if (isCalendarSyncPanelOpen) window.closeCalendarSyncPanel();
    else window.openCalendarSyncPanel();
}

function installCalendarSyncHandle() {
    document.querySelectorAll('[data-calendar-sync-trigger]').forEach((button) => {
        if (button.dataset.bound === '1') return;
        button.dataset.bound = '1';
        button.addEventListener('click', () => window.toggleCalendarSyncPanel());
    });
    const backdrop = document.getElementById('calendarSubscriptionBackdrop');
    if (backdrop && backdrop.dataset.bound !== '1') {
        backdrop.dataset.bound = '1';
        backdrop.addEventListener('click', () => window.closeCalendarSyncPanel());
    }
    if (document.body.dataset.calendarEscapeBound !== '1') {
        document.body.dataset.calendarEscapeBound = '1';
        document.addEventListener('keydown', (event) => {
            if (event.key === 'Escape' && isCalendarSyncPanelOpen) {
                window.closeCalendarSyncPanel();
            }
        });
    }
    if (document.body.dataset.calendarResizeBound !== '1') {
        document.body.dataset.calendarResizeBound = '1';
        window.addEventListener('resize', () => setCalendarDrawerVisibility(isCalendarSyncPanelOpen));
    }
    setCalendarDrawerVisibility(isCalendarSyncPanelOpen);
}

const calendarDialogView = { open: new Set(), focus: '', scroll: 0 };

function calendarButton(key, fallback, action, variant = '', focus = key) {
    return `<button type="button" class="calendar-button ${variant}" data-calendar-focus="${escapeHtml(focus)}" onclick="${escapeHtml(action)}">${escapeHtml(t(key, fallback))}</button>`;
}

function getCalendarProfileTitle(profile) {
    if (!profile) return t('schedule.calendar.dialog.noProfile', 'Choose a subscription');
    if (profile.kind !== 'custom') return getCalendarLessonModeLabel(profile);
    // Older automatically generated names contain counts that can become stale.
    const source = String(profile.entity_name || '');
    const name = String(profile.name || source);
    const generated = name === source || name.replace(/(?: - exams)?(?: \(\d+ modules\))?$/, '') === source;
    return generated ? source : name;
}

function getCalendarProfileDescription(profile) {
    if (!profile) return '';
    if (profile.kind !== 'custom') return t('schedule.calendar.dialog.combined', 'From your Telegram and website subscriptions');
    const modules = getCalendarProfileModules(profile);
    const total = isCalendarProfileOnCurrentEntity(profile) ? getCalendarAvailableModulesForProfile(profile).length : 0;
    const count = modules.length && total
        ? t('schedule.calendar.dialog.moduleCount', '{count} of {total} modules', { count: modules.length, total })
        : getCalendarModulesLabel(profile);
    return `${count} · ${getCalendarLessonModeLabel(profile)}`;
}

function getCalendarTimezoneLabel(value, fallback = '') {
    return value === 'Europe/Moscow'
        ? t('schedule.calendar.dialog.moscow', 'Moscow, UTC+3')
        : (fallback || value || 'UTC');
}

function renderCalendarDialog(body) {
    const container = document.getElementById('calendarSubscriptionSection');
    const active = document.activeElement;
    const hadFocus = container.contains(active);
    if (container.dataset.loading !== 'true') {
        container.querySelectorAll('details[id]').forEach(el => {
            if (el.open) calendarDialogView.open.add(el.id);
            else calendarDialogView.open.delete(el.id);
        });
        if (hadFocus) calendarDialogView.focus = active.dataset.calendarFocus || '';
        calendarDialogView.scroll = container.scrollTop;
    }
    const loading = Boolean(calendarSubscriptionState.loading);
    container.dataset.loading = String(loading);
    container.setAttribute('aria-busy', String(loading));
    container.innerHTML = `<div class="calendar-sync-card">
        <header class="calendar-dialog-header">
            <div><h2 id="calendar-dialog-title">${escapeHtml(t('schedule.calendar.dialog.title', 'Add your schedule'))}</h2>
            <p>${escapeHtml(t('schedule.calendar.dialog.subtitle', 'To your calendar app'))}</p></div>
            <button type="button" class="calendar-close" data-calendar-focus="close" onclick="closeCalendarSyncPanel()" aria-label="${escapeHtml(t('schedule.calendar.hidePanel', 'Close'))}">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18" stroke-width="1.8" stroke-linecap="round"/></svg>
            </button>
        </header>${body}</div>`;
    container.querySelectorAll('details[id]').forEach(el => { if (calendarDialogView.open.has(el.id)) el.open = true; });
    if (hadFocus) {
        const target = [...container.querySelectorAll('[data-calendar-focus]')].find(el => el.dataset.calendarFocus === calendarDialogView.focus);
        (target || container.querySelector('.calendar-close')).focus({ preventScroll: true });
    }
    container.scrollTop = calendarDialogView.scroll;
    window.MpbScheduleUX?.calendarFocus(true);
}

function renderCalendarSourceSettings(profile, state) {
    if (!profile) return '';
    const id = JSON.stringify(profile.id);
    const custom = profile.kind === 'custom';
    const available = getCalendarAvailableModulesForProfile(profile);
    const draft = getCalendarProfileModuleDraft(profile);
    const canEditModules = custom && isCalendarProfileOnCurrentEntity(profile) && available.length;
    const mode = `<label class="calendar-field">${escapeHtml(t('schedule.calendar.meta.mode', 'Classes'))}
        <select data-calendar-focus="mode" aria-label="${escapeHtml(t('schedule.calendar.meta.mode', 'Classes'))}" onchange="${escapeHtml(`updateCalendarSubscriptionProfile(${id}, {lesson_mode:this.value})`)}">
            <option value="all" ${profile.lesson_mode !== 'exams_only' ? 'selected' : ''}>${escapeHtml(t('schedule.calendar.mode.all', 'All classes'))}</option>
            <option value="exams_only" ${profile.lesson_mode === 'exams_only' ? 'selected' : ''}>${escapeHtml(t('schedule.calendar.mode.exams', 'Exams only'))}</option>
        </select></label>`;
    const timezone = `<label class="calendar-field">${escapeHtml(t('schedule.calendar.meta.timezone', 'Timezone'))}
        <select data-calendar-focus="timezone" aria-label="${escapeHtml(t('schedule.calendar.meta.timezone', 'Timezone'))}" onchange="${escapeHtml(`updateCalendarSubscriptionProfile(${id}, {timezone:this.value})`)}">
            ${(state.timezone_options || []).map(option => `<option value="${escapeHtml(option.value)}" ${option.value === profile.timezone ? 'selected' : ''}>${escapeHtml(getCalendarTimezoneLabel(option.value, option.label))}</option>`).join('')}
        </select></label>`;
    const moduleEditor = canEditModules ? `<fieldset class="calendar-modules">
        <legend>${escapeHtml(t('schedule.calendar.modules.editorTitle', 'Choose modules'))}</legend>
        ${available.map((module, index) => `<label><input type="checkbox" data-calendar-focus="module-${index}" ${draft.has(module) ? 'checked' : ''}
            onchange="${escapeHtml(`setCalendarPresetModuleDraft(${id}, ${JSON.stringify(module)}, this.checked)`)}"><span>${escapeHtml(module)}</span></label>`).join('')}
        <div class="calendar-actions">
            ${calendarButton('schedule.calendar.modules.save', 'Save modules', `saveCalendarProfileModuleDraft(${id})`)}
            ${calendarButton('schedule.calendar.modules.useAll', 'Select all', `selectAllCalendarPresetModules(${id})`, 'calendar-link')}
            ${calendarButton('schedule.calendar.modules.resetDraft', 'Reset', `resetCalendarProfileModuleDraft(${id})`, 'calendar-link')}
        </div></fieldset>` : custom ? `<p class="calendar-note">${escapeHtml(t('schedule.calendar.modules.openScheduleHint', 'Open this schedule to edit modules.'))}</p>
            ${calendarButton('schedule.calendar.modules.openSchedule', 'Open schedule', `openCalendarPresetSchedule(${id})`)}` : '';
    return `<div class="calendar-settings">
        ${custom ? `<div class="calendar-fields">${mode}${timezone}</div>${moduleEditor}
        <div class="calendar-actions">${calendarButton('schedule.calendar.rename', 'Rename', `renameCalendarSubscriptionProfile(${id})`, 'calendar-link')}
        ${isCalendarProfileOnCurrentEntity(profile) ? calendarButton('schedule.calendar.updateModules', 'Use current filters', `updateCalendarSubscriptionProfile(${id}, {modules:window.getCalendarCurrentViewModules()})`, 'calendar-link') : ''}</div>`
        : `<p>${escapeHtml(t('schedule.calendar.dialog.combinedHint', 'This subscription combines your saved schedules. Manage its sources below or in Telegram.'))}</p>
            <p class="calendar-note">${escapeHtml(getCalendarTimezoneLabel(profile.timezone, profile.timezone_label))}</p>`}
    </div>`;
}

function renderCalendarSubscription() {
    if (!document.getElementById('calendarSubscriptionSection')) return;
    if (!isCalendarSyncPanelOpen) { setCalendarDrawerVisibility(false); return; }
    setCalendarDrawerVisibility(true);
    const state = calendarSubscriptionState;
    const profiles = state.profiles || [];
    const profile = window.getSelectedCalendarProfile?.() || profiles[0];
    const message = (text, action = '', error = false) => `<div class="calendar-dialog-body"><div class="calendar-message ${error ? 'is-error' : ''}" role="${error ? 'alert' : 'status'}"><p>${escapeHtml(text)}</p>${action}</div></div>`;
    if (state.loading) {
        renderCalendarDialog(message(t('schedule.calendar.loading', 'Loading your subscription…')));
        return;
    }
    if (!scheduleAuthUser) {
        const miniApp = window.mpbTelegramWebApp?.isActive;
        const pending = miniApp && window.mpbTelegramAuthState?.pending;
        const key = pending ? 'schedule.calendar.telegramAuthPending' : miniApp ? 'schedule.calendar.telegramAuthUnavailable' : 'schedule.calendar.authRequired';
        const signIn = miniApp ? '' : `<a class="calendar-button calendar-primary" href="/login?next=${encodeURIComponent(location.pathname + location.search)}">${escapeHtml(t('schedule.calendar.signIn', 'Sign in'))}</a>`;
        renderCalendarDialog(message(t(key, 'Sign in to manage your calendar subscriptions.'), `${signIn}${pending ? '' : renderCalendarBotLink('calendar-button')}`));
        return;
    }
    if (state.hasError) {
        renderCalendarDialog(message(t('schedule.calendar.error', 'Could not load your subscriptions.'), calendarButton('schedule.action.retry', 'Retry', 'refreshCalendarSubscription()', 'calendar-primary'), true));
        return;
    }
    const ready = Boolean(state.enabled && state.sync_enabled && profile?.links?.http_url);
    const id = JSON.stringify(profile?.id || '');
    const source = profile ? `<details id="calendar-source" class="calendar-source">
        <summary data-calendar-focus="source"><span><strong>${escapeHtml(getCalendarProfileTitle(profile))}</strong><span class="calendar-source-caption">${escapeHtml(getCalendarProfileDescription(profile))}</span></span>
        <span class="calendar-change">${escapeHtml(t('schedule.calendar.dialog.editSource', 'Change selection'))}</span></summary>
        ${renderCalendarSourceSettings(profile, state)}
    </details>` : '';
    const primary = calendarPlatform === 'apple'
        ? calendarButton('schedule.calendar.dialog.openApple', 'Open Apple Calendar', "openCalendarProfileLink('webcal')", 'calendar-primary', 'connect')
        : calendarButton('schedule.calendar.dialog.copySubscription', 'Copy subscription link', 'copyCalendarSubscriptionLink(event)', 'calendar-primary', 'connect');
    const connection = ready ? `<div class="calendar-connection">
        <h3>${escapeHtml(t('schedule.calendar.dialog.chooseApp', 'Where would you like to add it?'))}</h3>
        <div class="calendar-apps" role="group" aria-label="${escapeHtml(t('schedule.calendar.dialog.chooseApp', 'Calendar app'))}">
            ${[['apple', 'schedule.calendar.platform.apple', 'Apple Calendar'], ['google', 'schedule.calendar.platform.google', 'Google Calendar'], ['outlook', 'schedule.calendar.platform.outlook', 'Outlook / other']].map(([app, key, fallback]) => `<button type="button" data-calendar-focus="app-${app}" aria-pressed="${app === calendarPlatform}" onclick="setCalendarPlatform('${app}')">${escapeHtml(t(key, fallback))}</button>`).join('')}
        </div>
        <p class="calendar-guide">${escapeHtml(t(`schedule.calendar.platform.${calendarPlatform === 'apple' ? 'appleHint' : calendarPlatform === 'google' ? 'googleHint' : 'outlookHint'}`, 'Add this subscription in your calendar app.'))}</p>
        ${primary}<p class="calendar-footnote">${escapeHtml(t('schedule.calendar.dialog.updates', 'A subscription receives future schedule changes.'))}</p>
        <p id="calendar-action-feedback" class="calendar-feedback" role="status" hidden></p>
    </div>` : `<div class="calendar-message" role="status"><p>${escapeHtml(t(!state.sync_enabled ? 'schedule.calendar.dialog.paused' : !state.eligibility?.has_telegram_link ? 'schedule.calendar.dialog.linkRequired' : 'schedule.calendar.dialog.empty', 'Set up a subscription to continue.'))}</p>
        ${!state.sync_enabled ? calendarButton('schedule.calendar.enable', 'Enable', 'toggleCalendarSync(true)', 'calendar-primary') : !state.eligibility?.has_telegram_link ? `<a class="calendar-button calendar-primary" href="/account">${escapeHtml(t('schedule.calendar.dialog.linkAccount', 'Link Telegram'))}</a>` : ''}</div>`;
    const currentView = currentEntity?.id ? `<div class="calendar-current-view">
        <h4>${escapeHtml(t('schedule.calendar.dialog.currentSchedule', 'Currently open schedule'))}</h4>
        <p class="calendar-note">${window.getCalendarCurrentViewSummary()}</p>
        <div class="calendar-fields"><label class="calendar-field">${escapeHtml(t('schedule.calendar.meta.mode', 'Classes'))}<select data-calendar-focus="new-mode" onchange="window.calendarCurrentViewMode=this.value">
            <option value="all" ${window.calendarCurrentViewMode !== 'exams_only' ? 'selected' : ''}>${escapeHtml(t('schedule.calendar.mode.all', 'All classes'))}</option>
            <option value="exams_only" ${window.calendarCurrentViewMode === 'exams_only' ? 'selected' : ''}>${escapeHtml(t('schedule.calendar.mode.exams', 'Exams only'))}</option>
        </select></label></div>
        ${calendarButton('schedule.calendar.dialog.saveCurrent', 'Create subscription from this schedule', 'createCalendarProfileFromCurrentView()')}
    </div>` : '';
    const saved = `<details id="calendar-profiles" class="calendar-disclosure" ${!profile ? 'open' : ''}>
        <summary data-calendar-focus="profiles">${escapeHtml(t('schedule.calendar.dialog.mySubscriptions', 'My subscriptions'))}</summary>
        <div class="calendar-profile-list">${profiles.map(item => `<button type="button" class="calendar-profile" data-calendar-focus="profile-${escapeHtml(item.id)}" aria-pressed="${item.id === profile?.id}"
            onclick="${escapeHtml(`selectCalendarSubscriptionProfile(${JSON.stringify(item.id)})`)}">
            <span><strong>${escapeHtml(getCalendarProfileTitle(item))}</strong><span>${escapeHtml(getCalendarProfileDescription(item))}</span></span>
            ${item.id === profile?.id ? `<span class="calendar-selection">${escapeHtml(t('schedule.calendar.dialog.selected', 'Selected'))}</span>` : ''}
        </button>`).join('')}</div>${state.eligibility?.has_telegram_link ? currentView : ''}
    </details>`;
    const health = profile?.health || {};
    const shownUrl = profile && (revealedCalendarProfileIds.has(profile.id) ? profile.links?.http_url : profile.links?.masked_http_url);
    const extra = `<details id="calendar-options" class="calendar-disclosure">
        <summary data-calendar-focus="options">${escapeHtml(t('schedule.calendar.dialog.other', 'Other options and settings'))}</summary>
        <div class="calendar-settings">
        ${ready ? `<section><h4>${escapeHtml(t('schedule.calendar.dialog.oneTime', 'One-time copy'))}</h4>
            <p class="calendar-note">${escapeHtml(t('schedule.calendar.dialog.oneTimeHint', 'An .ics file is a snapshot. It does not receive later changes.'))}</p>
            ${calendarButton('schedule.calendar.download', 'Download one-time .ics file', "openCalendarProfileLink('download')", 'calendar-link')}
        </section><section><h4>${escapeHtml(t('schedule.calendar.linkReady', 'Subscription link ready'))}</h4>
            <div class="calendar-url"><input readonly aria-label="${escapeHtml(t('schedule.calendar.dialog.privateLink', 'Private subscription link'))}" value="${escapeHtml(shownUrl || t('schedule.calendar.dialog.hiddenLink', 'Private link hidden'))}">
            ${calendarButton(revealedCalendarProfileIds.has(profile.id) ? 'schedule.calendar.hide' : 'schedule.calendar.reveal', 'Show', `toggleCalendarProfileReveal(${id})`, '', 'reveal')}</div>
            <div class="calendar-actions">${calendarButton('schedule.calendar.copy', 'Copy link', 'copyCalendarSubscriptionLink(event)', '', 'copy-extra')}
            ${calendarButton('schedule.calendar.preview', 'Check feed', "openCalendarProfileLink('preview')", 'calendar-link')}</div>
        </section>` : ''}
        ${profile ? `<section><h4>${escapeHtml(t('schedule.calendar.dialog.sourceStatus', 'Schedule source'))}</h4><dl class="calendar-health">
            <div><dt>${escapeHtml(t('schedule.calendar.health.events', 'Events'))}</dt><dd>${escapeHtml(String(health.event_count ?? 0))}</dd></div>
            <div><dt>${escapeHtml(t('schedule.calendar.health.next', 'Next class'))}</dt><dd>${health.next_event_at ? formatCalendarDateTime(health.next_event_at, '') : escapeHtml(t('schedule.calendar.noNextEvent', 'No upcoming class'))}</dd></div>
            <div><dt>${escapeHtml(t('schedule.calendar.dialog.checked', 'Schedule checked'))}</dt><dd>${health.source_updated_at ? formatCalendarDateTime(health.source_updated_at, '') : escapeHtml(t('schedule.calendar.notUpdatedYet', 'Not checked yet'))}</dd></div>
        </dl></section>` : ''}
        ${renderCalendarBotLink('calendar-button calendar-link')}
        ${profile ? `<section class="calendar-danger"><h4>${escapeHtml(t('schedule.calendar.dialog.manage', 'Manage subscription'))}</h4>
            <p class="calendar-note">${escapeHtml(t('schedule.calendar.dangerDescription', 'Changing the link or disabling subscriptions affects external calendar apps.'))}</p>
            <div class="calendar-actions">${calendarButton('schedule.calendar.reset', 'Reset link', 'resetCalendarSubscription()', 'calendar-danger-button')}
            ${calendarButton(state.sync_enabled ? 'schedule.calendar.disable' : 'schedule.calendar.enable', 'Enable', `toggleCalendarSync(${!state.sync_enabled})`)}
            ${profile.can_delete ? calendarButton('schedule.calendar.delete', 'Delete subscription', `deleteCalendarSubscriptionProfile(${id})`, 'calendar-danger-button') : ''}</div>
        </section>` : ''}
        </div>
    </details>`;
    renderCalendarDialog(`<div class="calendar-dialog-body">${source}${connection}${state.justReset ? `<p class="calendar-feedback" role="status">${escapeHtml(t('schedule.calendar.dialog.resetDone', 'The link has changed. Add the new link in your calendar app.'))}</p>` : ''}</div>
        <footer class="calendar-dialog-footer">${saved}${extra}</footer>`);
}

window.renderCalendarSubscription = renderCalendarSubscription;
window._renderCalendarSubscriptionImpl = renderCalendarSubscription;
window.addEventListener('mpb-telegram-auth-settled', () => { if (!scheduleAuthUser) renderCalendarSubscription(); });


window.getSelectedCalendarProfile = function() {
    return (calendarSubscriptionState.profiles ||[]).find((profile) => profile.selected) || null;
}

window.toggleCalendarProfileReveal = function(profileId) {
    if (!profileId) return;
    if (revealedCalendarProfileIds.has(profileId)) revealedCalendarProfileIds.delete(profileId);
    else revealedCalendarProfileIds.add(profileId);
    persistRevealedCalendarProfileIds();
    renderCalendarSubscription();
}

window.setCalendarPresetModuleDraft = function(profileId, moduleName, checked) {
    if (!profileId || !moduleName) return;
    const selectedProfile = window.getSelectedCalendarProfile();
    if (!selectedProfile || selectedProfile.id !== profileId) return;
    const draft = getCalendarProfileModuleDraft(selectedProfile);
    if (checked) draft.add(moduleName);
    else if (draft.size > 1) draft.delete(moduleName);
    calendarProfileModuleDrafts.set(profileId, draft);
    renderCalendarSubscription();
}

window.selectAllCalendarPresetModules = function(profileId) {
    const selectedProfile = window.getSelectedCalendarProfile();
    if (!profileId || !selectedProfile || selectedProfile.id !== profileId) return;
    calendarProfileModuleDrafts.set(profileId, new Set(getCalendarAvailableModulesForProfile(selectedProfile)));
    renderCalendarSubscription();
}

window.resetCalendarProfileModuleDraft = function(profileId) {
    if (!profileId) return;
    calendarProfileModuleDrafts.delete(profileId);
    renderCalendarSubscription();
}

window.saveCalendarProfileModuleDraft = async function(profileId) {
    const selectedProfile = window.getSelectedCalendarProfile();
    if (!profileId || !selectedProfile || selectedProfile.id !== profileId) return;
    const modules = getCalendarProfileModulePayload(selectedProfile);
    await window.updateCalendarSubscriptionProfile(profileId, { modules });
}

async function applyCalendarProfileToSchedule(profile, { urlMode = 'push' } = {}) {
    if (!profile) return;
    const lessonMode = profile.lesson_mode === 'exams_only' ? 'exams_only' : 'all';
    const currentState = window.getSchedulePageState?.() || null;
    const keepViewMode = lessonMode === 'all' && currentState?.viewMode !== 'exams';
    const targetDate = currentState?.date || null;
    window.calendarCurrentViewMode = lessonMode;

    if (profile.entity_type && profile.entity_id && typeof loadSchedule === 'function') {
        const profileModules = Array.isArray(profile.modules) ? profile.modules.filter(Boolean) : [];
        if (typeof selectedModules !== 'undefined') {
            selectedModules = profileModules.length ? new Set(profileModules) : new Set();
        }
        await loadSchedule(profile.entity_type, profile.entity_id, profile.entity_name || profile.name || '', targetDate, {
            preserveModules: profileModules.length > 0,
            calendarProfileId: profile.id,
            urlMode
        });
        window.setScheduleLessonMode?.(lessonMode, { keepViewMode });
        return;
    }

    window.setScheduleLessonMode?.(lessonMode, { keepViewMode });
    window.setScheduleCalendarProfile?.(profile.id, { updateUrl: true });
}

window.openCalendarPresetSchedule = async function(profileId) {
    const profile = (calendarSubscriptionState.profiles || []).find((item) => item.id === profileId);
    if (!profile) return;
    await applyCalendarProfileToSchedule(profile, { urlMode: 'push' });
}

function formatCalendarDateTime(value, fallback) {
    if (!value) return escapeHtml(fallback);
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return escapeHtml(value);
    return escapeHtml(
        formatUiDateCapitalized(parsed, {
            day: 'numeric',
            month: 'short',
            hour: '2-digit',
            minute: '2-digit'
        })
    );
}

window.getCalendarCurrentViewModules = function() {
    if (currentEntity?.type !== 'group') return[];
    return Array.from(selectedModules ||[]);
}

window.getCalendarCurrentViewSummary = function() {
    if (!currentEntity?.id) {
        return escapeHtml(t('schedule.calendar.currentView.empty', 'Open a schedule to save this page as a separate feed.'));
    }
    const modules = window.getCalendarCurrentViewModules();
    const modulesLabel = allAvailableModules.length === 0
        ? escapeHtml(t('schedule.calendar.currentView.noModules', 'No module filter'))
        : modules.length === allAvailableModules.length
            ? escapeHtml(t('schedule.calendar.currentView.allModules', 'All modules'))
            : escapeHtml(
                t(
                    'schedule.calendar.currentView.someModules',
                    'Selected modules: {count}',
                    { count: modules.length }
                )
            );
    return `${escapeHtml(currentEntity.name)} - ${modulesLabel}`;
}

async function parseCalendarError(response) {
    try {
        const data = await response.json();
        return data?.detail || `HTTP ${response.status}`;
    } catch (error) {
        return `HTTP ${response.status}`;
    }
}

window.refreshCalendarSubscription = async function() {
    if (!scheduleAuthUser) {
        calendarSubscriptionState = createDefaultCalendarSubscriptionState();
        renderCalendarSubscription();
        return;
    }
    const token = localStorage.getItem('jwt_token');
    if (!token) {
        scheduleAuthUser = null;
        calendarSubscriptionState = createDefaultCalendarSubscriptionState();
        renderCalendarSubscription();
        return;
    }
    calendarSubscriptionState = { ...calendarSubscriptionState, loading: true, hasError: false, justReset: false };
    renderCalendarSubscription();
    try {
        const response = await fetch(`${API_BASE}/cal/subscription`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        if (response.status === 401) {
            scheduleAuthUser = null;
            calendarSubscriptionState = createDefaultCalendarSubscriptionState();
            renderCalendarSubscription();
            return;
        }
        if (!response.ok) throw new Error(await parseCalendarError(response));
        const data = await response.json();
        calendarSubscriptionState = {
            ...createDefaultCalendarSubscriptionState(),
            ...data,
            loading: false,
            hasError: false,
            justReset: false
        };
        calendarProfileModuleDrafts.clear();
    } catch (error) {
        console.error('Failed to load calendar subscription', error);
        calendarSubscriptionState = { ...createDefaultCalendarSubscriptionState(), hasError: true };
    }
    renderCalendarSubscription();
}

function showCalendarActionFeedback(key, fallback) {
    const feedback = document.getElementById('calendar-action-feedback');
    if (!feedback) return;
    feedback.textContent = t(key, fallback);
    feedback.hidden = false;
}

window.copyCalendarSubscriptionLink = async function() {
    const selectedProfile = window.getSelectedCalendarProfile();
    if (!selectedProfile?.links?.http_url || !calendarSubscriptionState.sync_enabled) return;
    try {
        await navigator.clipboard.writeText(selectedProfile.links.http_url);
        window.MpbUI?.finish('calendar_connected');
        showCalendarActionFeedback('schedule.calendar.dialog.copied', 'Link copied. Add it as a subscription in your calendar app.');
    } catch {
        showCalendarActionFeedback('schedule.calendar.dialog.copyFailed', 'Could not copy. Open Other options, reveal the link and copy it manually.');
    }
}

window.openCalendarProfileLink = function(kind) {
    const selectedProfile = window.getSelectedCalendarProfile();
    if (!selectedProfile?.links || !calendarSubscriptionState.sync_enabled) return;
    const targetUrl = kind === 'download'
        ? selectedProfile.links.download_url
        : kind === 'webcal'
            ? selectedProfile.links.webcal_url
            : selectedProfile.links.preview_url;
    if (!targetUrl) return;
    if (kind === 'webcal') {
        window.MpbUI?.finish('calendar_connected');
        showCalendarActionFeedback('schedule.calendar.dialog.appleNext', 'Confirm the subscription in Apple Calendar.');
        window.location.href = targetUrl;
    }
    else window.open(targetUrl, '_blank', 'noopener');
}

async function performCalendarMutation(url, options = {}, { justReset = false } = {}) {
    const token = localStorage.getItem('jwt_token');
    if (!token) {
        scheduleAuthUser = null;
        calendarSubscriptionState = createDefaultCalendarSubscriptionState();
        renderCalendarSubscription();
        return null;
    }
    calendarSubscriptionState = { ...calendarSubscriptionState, loading: true, hasError: false, justReset: false };
    renderCalendarSubscription();
    try {
        const response = await fetch(url, {
            ...options,
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`,
                ...(options.headers || {})
            }
        });
        if (response.status === 401) {
            scheduleAuthUser = null;
            calendarSubscriptionState = createDefaultCalendarSubscriptionState();
            renderCalendarSubscription();
            return null;
        }
        if (!response.ok) {
            const detail = await parseCalendarError(response);
            throw new Error(detail);
        }
        const data = await response.json();
        calendarSubscriptionState = {
            ...createDefaultCalendarSubscriptionState(),
            ...data,
            loading: false,
            hasError: false,
            justReset
        };
        calendarProfileModuleDrafts.clear();
        renderCalendarSubscription();
        return calendarSubscriptionState;
    } catch (error) {
        console.error('Calendar mutation failed', error);
        calendarSubscriptionState = { ...createDefaultCalendarSubscriptionState(), hasError: true };
        renderCalendarSubscription();
        window.mpbPopup?.(error.message || t('schedule.calendar.error', 'Failed to load the calendar subscription.'), { type: 'error' });
        return null;
    }
}

window.resetCalendarSubscription = async function() {
    if (!window.confirm(t('schedule.calendar.confirmReset', 'Reset the private link? The previous URL will stop working immediately.'))) return;
    await performCalendarMutation(`${API_BASE}/cal/subscription/reset`, { method: 'POST' }, { justReset: true });
}

window.toggleCalendarSync = async function(enabled) {
    const confirmKey = enabled ? 'schedule.calendar.confirmEnable' : 'schedule.calendar.confirmDisable';
    const fallback = enabled
        ? 'Enable calendar sync again?'
        : 'Disable calendar sync? External subscriptions will stop updating.';
    if (!window.confirm(t(confirmKey, fallback))) return;
    await performCalendarMutation(`${API_BASE}/cal/subscription/toggle`, {
        method: 'POST',
        body: JSON.stringify({ enabled })
    });
}

window.selectCalendarSubscriptionProfile = async function(profileId) {
    if (!profileId || profileId === calendarSubscriptionState.selected_profile_id) return;
    await performCalendarMutation(`${API_BASE}/cal/subscription/select`, {
        method: 'POST',
        body: JSON.stringify({ profile_id: profileId })
    });
}

window.createCalendarProfileFromCurrentView = async function() {
    if (!currentEntity?.id) return;
    await performCalendarMutation(`${API_BASE}/cal/subscription/profiles`, {
        method: 'POST',
        body: JSON.stringify({
            entity_type: currentEntity.type,
            entity_id: currentEntity.id,
            entity_name: currentEntity.name,
            lesson_mode: window.calendarCurrentViewMode,
            modules: window.getCalendarCurrentViewModules(),
            timezone: window.getSelectedCalendarProfile?.()?.timezone || 'Europe/Moscow'
        })
    });
}

window.updateCalendarSubscriptionProfile = async function(profileId, payload) {
    if (!profileId || !payload || typeof payload !== 'object') return;
    await performCalendarMutation(`${API_BASE}/cal/subscription/profiles/${encodeURIComponent(profileId)}`, {
        method: 'PATCH',
        body: JSON.stringify(payload)
    });
}

window.renameCalendarSubscriptionProfile = async function(profileId) {
    const selectedProfile = window.getSelectedCalendarProfile();
    if (!profileId || !selectedProfile || selectedProfile.id !== profileId) return;
    const nextName = window.prompt(
        t('schedule.calendar.renamePrompt', 'Preset name'),
        selectedProfile.name || ''
    );
    if (nextName === null) return;
    const trimmed = nextName.trim();
    if (!trimmed) return;
    await window.updateCalendarSubscriptionProfile(profileId, { name: trimmed });
}

window.deleteCalendarSubscriptionProfile = async function(profileId) {
    if (!window.confirm(t('schedule.calendar.confirmDelete', 'Delete this preset?'))) return;
    await performCalendarMutation(`${API_BASE}/cal/subscription/profiles/${encodeURIComponent(profileId)}`, {
        method: 'DELETE'
    });
}

const originalLoadSchedule = loadSchedule;
loadSchedule = async function(...args) {
    try {
        return await originalLoadSchedule(...args);
    } finally {
        renderCalendarSubscription();
    }
};
const originalToggleModule = window.toggleModule;
window.toggleModule = function(...args) {
    originalToggleModule?.(...args);
    renderCalendarSubscription();
};
const originalSelectAllModules = window.selectAllModules;
window.selectAllModules = function(...args) {
    originalSelectAllModules?.(...args);
    renderCalendarSubscription();
};
const originalClearAllModules = window.clearAllModules;
window.clearAllModules = function(...args) {
    originalClearAllModules?.(...args);
    renderCalendarSubscription();
};

document.addEventListener('DOMContentLoaded', () => {
    installCalendarSyncHandle();
    const label = t('schedule.calendar.handleTooltip', 'Calendar sync');
    document.querySelectorAll('[data-calendar-sync-trigger]').forEach((button) => {
        button.setAttribute('title', label);
        button.setAttribute('aria-label', label);
    });
});
