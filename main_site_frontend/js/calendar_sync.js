const CALENDAR_PLATFORM_KEY = "mpb_calendar_sync_platform";
const CALENDAR_REVEALED_PROFILES_KEY = "mpb_calendar_sync_revealed_profiles";
const CALENDAR_PANEL_COLLAPSED_KEY = "mpb_calendar_sync_collapsed";
const CALENDAR_BOT_DEEPLINK =
    window.__MPB_BOT_DEEPLINK__ || "https://t.me/matplobbot?start=calendar_sync";
const calendarSyncLaunchParams = new URLSearchParams(window.location.search);
const shouldFocusCalendarSyncPanel =
    calendarSyncLaunchParams.get('calendar') === '1' ||
    calendarSyncLaunchParams.get('panel') === 'calendar';
let calendarPlatform = loadCalendarPlatform();
let revealedCalendarProfileIds = loadRevealedCalendarProfileIds();
let isCalendarPanelCollapsed = true;
let hasUserToggledCalendarPanel = false;
let hasFocusedCalendarSyncPanel = false;
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
function loadCalendarPanelCollapsed() {
    try {
        const saved = localStorage.getItem(CALENDAR_PANEL_COLLAPSED_KEY);
        if (saved === 'false') return false;
        if (saved === 'true') return true;
    } catch (error) {}
    return true;
}
function persistCalendarPanelCollapsed() {
    try {
        localStorage.setItem(CALENDAR_PANEL_COLLAPSED_KEY, String(isCalendarPanelCollapsed));
    } catch (error) {}
}

function focusCalendarSyncPanelIfRequested(container) {
    if (!shouldFocusCalendarSyncPanel || hasFocusedCalendarSyncPanel || !container) return;
    hasFocusedCalendarSyncPanel = true;
    window.requestAnimationFrame(() => {
        container.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
}

function renderCalendarButton(labelKey, fallback, className, attributes = '') {
    return `
        <button type="button" ${attributes}
            class="inline-flex items-center justify-center rounded-xl px-3 py-2 text-xs font-bold transition-colors ${className}">
            ${escapeHtml(t(labelKey, fallback))}
        </button>
    `;
}

function renderCalendarBotLink(className = '') {
    return `
        <a href="${escapeHtml(CALENDAR_BOT_DEEPLINK)}" target="_blank" rel="noopener"
            class="inline-flex items-center justify-center rounded-xl px-3 py-2 text-xs font-bold transition-colors ${className}">
            ${escapeHtml(t('schedule.calendar.botManage', 'Open in bot'))}
        </a>
    `;
}

function getCalendarProfileKindLabel(profile) {
    return profile?.kind === 'custom'
        ? t('schedule.calendar.profile.custom', 'Preset')
        : t('schedule.calendar.profile.builtin', 'Built-in');
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

function renderCalendarModuleChips(modules, emptyKey = 'schedule.calendar.currentView.allModules', emptyFallback = 'All modules') {
    const normalized = Array.isArray(modules) ? modules.filter(Boolean) : [];
    if (!normalized.length) {
        return `
            <span class="inline-flex w-fit rounded-full bg-slate-100 px-2.5 py-1 text-[10px] font-black uppercase tracking-wide text-slate-500 dark:bg-slate-800 dark:text-slate-300">
                ${escapeHtml(t(emptyKey, emptyFallback))}
            </span>
        `;
    }
    return normalized.map((module) => `
        <span class="inline-flex max-w-full rounded-full bg-white px-2.5 py-1 text-[10px] font-black text-slate-600 ring-1 ring-slate-200 dark:bg-slate-900/60 dark:text-slate-200 dark:ring-slate-700">
            <span class="truncate">${escapeHtml(module)}</span>
        </span>
    `).join('');
}

function getCalendarProfileDescription(profile) {
    if (!profile) return t('schedule.calendar.summary', 'Personal calendar feed for your active schedule subscriptions and filters.');
    const parts = [
        profile.scope_label || profile.entity_name || profile.name,
        getCalendarLessonModeLabel(profile),
        getCalendarModulesLabel(profile)
    ].filter(Boolean);
    return parts.join(' - ');
}

function renderCalendarValueCard(label, valueHtml, className = '') {
    return `
        <div class="rounded-2xl border border-slate-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-900/40 ${className}">
            <div class="text-[10px] font-black uppercase tracking-[0.16em] text-slate-400">${escapeHtml(label)}</div>
            <div class="mt-1 line-clamp-2 text-xs font-bold text-slate-700 dark:text-slate-200">${valueHtml}</div>
        </div>
    `;
}

function renderCalendarPlatformTab(platform, labelKey, fallback) {
    const active = calendarPlatform === platform;
    return `
        <button type="button" onclick="setCalendarPlatform('${escapeJsString(platform)}')"
            class="rounded-xl px-3 py-2 text-xs font-black transition-colors ${active
                ? 'bg-blue-600 text-white shadow-sm shadow-blue-500/20'
                : 'border border-slate-200 bg-white text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800'}">
            ${escapeHtml(t(labelKey, fallback))}
        </button>
    `;
}

function renderCalendarDisclosureChevron() {
    return `
        <svg class="h-3.5 w-3.5 transition-transform group-open:rotate-180" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path d="M19 9l-7 7-7-7" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"></path>
        </svg>
    `;
}

window.toggleCalendarSubscriptionPanel = function() {
    hasUserToggledCalendarPanel = true;
    isCalendarPanelCollapsed = !isCalendarPanelCollapsed;
    persistCalendarPanelCollapsed();
    renderCalendarSubscription();
}

function renderTelegramCalendarAuthPlaceholder(container) {
    if (!hasUserToggledCalendarPanel) isCalendarPanelCollapsed = true;
    const authState = window.mpbTelegramAuthState || {};
    const isPending = Boolean(authState.pending);
    const statusKey = isPending ? 'schedule.calendar.statusSetup' : 'schedule.calendar.statusUnavailable';
    const statusFallback = getUiLanguage() === 'ru' ? (isPending ? 'Настройка' : 'Недоступно') : (isPending ? 'Setup' : 'Unavailable');
    const statusClass = isPending
        ? 'bg-amber-100 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300'
        : 'bg-rose-100 text-rose-700 dark:bg-rose-950/40 dark:text-rose-300';
    const toggleLabel = isCalendarPanelCollapsed
        ? t('schedule.calendar.expand', 'Expand')
        : t('schedule.calendar.collapse', 'Collapse');
    const detail = isPending
        ? t('schedule.calendar.telegramAuthPending', getUiLanguage() === 'ru' ? 'Входим через Telegram...' : 'Signing in through Telegram...')
        : t(
            'schedule.calendar.telegramAuthUnavailable',
            getUiLanguage() === 'ru'
                ? 'Для синхронизации нужен вход через Telegram Mini App. Откройте страницу кнопкой Web App из бота.'
                : 'Calendar sync needs Telegram Mini App sign-in. Open this page from the bot Web App button.'
        );
    const bodyHtml = isCalendarPanelCollapsed
        ? ''
        : `
            <div id="calendarSubscriptionBody" class="mt-5 rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm font-medium text-amber-700 dark:border-amber-900/60 dark:bg-amber-950/30 dark:text-amber-300">
                ${escapeHtml(detail)}
            </div>
        `;

    container.innerHTML = `
        <div class="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-700 dark:bg-slate-800">
            <div class="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                <div>
                    <div class="mb-1 text-xs font-black uppercase tracking-[0.2em] text-blue-500 dark:text-blue-300">${escapeHtml(t('schedule.calendar.eyebrow', 'Sync'))}</div>
                    <h2 class="text-xl font-black text-slate-900 dark:text-slate-100">${escapeHtml(t('schedule.calendar.title', 'Calendar subscription'))}</h2>
                    <p class="mt-1 max-w-3xl text-sm text-slate-600 dark:text-slate-300">${escapeHtml(t('schedule.calendar.description', 'Connect your personal ICS feed to Apple Calendar, Google Calendar, or any other calendar app.'))}</p>
                </div>
                <div class="flex flex-wrap items-center gap-2">
                    <span class="rounded-full px-3 py-1 text-xs font-black ${statusClass}">${escapeHtml(t(statusKey, statusFallback))}</span>
                    ${renderCalendarBotLink('border border-blue-200 bg-blue-50 text-blue-700 hover:bg-blue-100 dark:border-blue-800 dark:bg-blue-950/40 dark:text-blue-200 dark:hover:bg-blue-900/50')}
                    <button type="button" onclick="toggleCalendarSubscriptionPanel()"
                        aria-expanded="${String(!isCalendarPanelCollapsed)}"
                        aria-controls="calendarSubscriptionBody"
                        aria-label="${escapeHtml(toggleLabel)}"
                        class="inline-flex items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-bold text-slate-600 transition-colors hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700">
                        <span>${escapeHtml(toggleLabel)}</span>
                        <svg class="h-3.5 w-3.5 transition-transform ${isCalendarPanelCollapsed ? '' : 'rotate-180'}" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path d="M19 9l-7 7-7-7" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"></path>
                        </svg>
                    </button>
                </div>
            </div>
            ${bodyHtml}
        </div>
    `;
    focusCalendarSyncPanelIfRequested(container);
}

function renderCalendarSubscription() {
    const container = document.getElementById('calendarSubscriptionSection');
    if (!container) return;

    container.classList.remove('hidden');
    const state = calendarSubscriptionState || createDefaultCalendarSubscriptionState();
    const selectedProfile = window.getSelectedCalendarProfile?.() || state.profiles?.[0] || null;
    const isReady = Boolean(state.enabled && state.sync_enabled && selectedProfile?.links?.http_url);
    const statusKey = state.sync_enabled
        ? (state.eligibility?.available ? 'schedule.calendar.statusReady' : 'schedule.calendar.statusSetup')
        : 'schedule.calendar.statusPaused';
    const statusFallback = state.sync_enabled
        ? (state.eligibility?.available ? 'Ready' : 'Setup')
        : 'Paused';
    const statusClass = isReady
        ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300'
        : (!state.sync_enabled
            ? 'bg-slate-100 text-slate-600 dark:bg-slate-900 dark:text-slate-300'
            : 'bg-amber-100 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300');

    if (state.loading) {
        container.innerHTML = `
            <div class="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-700 dark:bg-slate-800">
                <div class="flex items-center gap-3 text-sm font-bold text-slate-600 dark:text-slate-300">
                    <span class="h-4 w-4 animate-spin rounded-full border-2 border-blue-200 border-t-blue-600"></span>
                    ${escapeHtml(t('schedule.calendar.loading', 'Loading your personal subscription link...'))}
                </div>
            </div>
        `;
        return;
    }

    if (state.hasError) {
        container.innerHTML = `
            <div class="rounded-3xl border border-rose-200 bg-rose-50 p-5 shadow-sm dark:border-rose-900/60 dark:bg-rose-950/30">
                <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                    <div>
                        <div class="text-sm font-black text-rose-700 dark:text-rose-300">${escapeHtml(t('schedule.calendar.error', 'Failed to load the calendar subscription.'))}</div>
                        <div class="mt-1 text-xs text-rose-600/80 dark:text-rose-200/80">${escapeHtml(t('schedule.action.retry', 'Retry'))}</div>
                    </div>
                    ${renderCalendarButton('schedule.action.retry', 'Retry', 'bg-rose-600 text-white hover:bg-rose-700', 'onclick="refreshCalendarSubscription()"')}
                </div>
            </div>
        `;
        return;
    }

    if (!scheduleAuthUser) {
        if (window.mpbTelegramWebApp?.isActive) {
            renderTelegramCalendarAuthPlaceholder(container);
        } else {
            container.innerHTML = '';
            container.classList.add('hidden');
        }
        return;
    }

    const profiles = Array.isArray(state.profiles) ? state.profiles :[];
    const health = selectedProfile?.health || {};
    const eventCount = Number.isFinite(Number(health.event_count)) ? Number(health.event_count) : 0;
    const eventCountLabel = t('schedule.calendar.eventsCount', '{count} events', { count: eventCount });
    const nextEventLabel = health.next_event_at
        ? formatCalendarDateTime(health.next_event_at, health.next_event_label || '')
        : escapeHtml(t('schedule.calendar.noNextEvent', 'No upcoming event'));
    const updatedAtLabel = health.source_updated_at
        ? formatCalendarDateTime(health.source_updated_at, '')
        : escapeHtml(t('schedule.calendar.notUpdatedYet', 'Not updated yet'));
    const selectedProfileDescription = getCalendarProfileDescription(selectedProfile);
    const profileKindLabel = getCalendarProfileKindLabel(selectedProfile);
    const lessonModeLabel = getCalendarLessonModeLabel(selectedProfile);
    const modulesLabel = getCalendarModulesLabel(selectedProfile);
    const unavailableMessage = state.eligibility?.detail || t('schedule.calendar.unavailable', 'Calendar subscription requires a linked Telegram account.');
    const urlValue = selectedProfile?.links?.http_url || state.http_url || '';
    const maskedUrl = selectedProfile?.links?.masked_http_url || state.masked_http_url || urlValue;
    const isRevealed = selectedProfile?.id && revealedCalendarProfileIds.has(selectedProfile.id);
    const shownUrl = isRevealed ? urlValue : maskedUrl;
    const canUpdateModulesFromCurrentView = isCalendarProfileOnCurrentEntity(selectedProfile);
    const selectedProfileModules = getCalendarProfileModules(selectedProfile);
    const availableProfileModules = getCalendarAvailableModulesForProfile(selectedProfile);
    const moduleDraft = getCalendarProfileModuleDraft(selectedProfile);
    const moduleDraftCount = moduleDraft.size;
    const moduleEditorCanSave = Boolean(selectedProfile?.kind === 'custom' && canUpdateModulesFromCurrentView && availableProfileModules.length);
    const profileButtons = profiles.map((profile) => {
        const active = profile.selected;
        return `
            <button type="button" onclick="selectCalendarSubscriptionProfile('${escapeJsString(profile.id)}')"
                class="group min-w-0 rounded-2xl border p-4 text-left transition-all ${active
                    ? 'border-blue-300 bg-blue-50 text-blue-800 shadow-sm shadow-blue-500/10 dark:border-blue-800 dark:bg-blue-950/40 dark:text-blue-100'
                    : 'border-slate-200 bg-white text-slate-600 hover:-translate-y-0.5 hover:border-blue-200 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900/50 dark:text-slate-300 dark:hover:border-blue-800 dark:hover:bg-slate-800'}">
                <div class="flex items-start justify-between gap-3">
                    <div class="min-w-0">
                        <div class="truncate text-sm font-black">${escapeHtml(profile.name)}</div>
                        <div class="mt-1 text-[10px] font-black uppercase tracking-[0.14em] opacity-70">${escapeHtml(getCalendarProfileKindLabel(profile))}</div>
                    </div>
                    <span class="flex h-6 w-6 shrink-0 items-center justify-center rounded-full ${active ? 'bg-blue-600 text-white' : 'bg-slate-100 text-slate-400 dark:bg-slate-800'}">
                        ${active ? '<svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M5 13l4 4L19 7" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"></path></svg>' : ''}
                    </span>
                </div>
                <p class="mt-3 line-clamp-2 text-xs font-medium opacity-80">${escapeHtml(getCalendarProfileDescription(profile))}</p>
                <div class="mt-3 flex flex-wrap gap-1.5">
                    <span class="rounded-full bg-white/80 px-2 py-1 text-[10px] font-black uppercase tracking-wide text-slate-500 ring-1 ring-slate-200 dark:bg-slate-900/60 dark:text-slate-300 dark:ring-slate-700">${escapeHtml(getCalendarLessonModeLabel(profile))}</span>
                    <span class="rounded-full bg-white/80 px-2 py-1 text-[10px] font-black uppercase tracking-wide text-slate-500 ring-1 ring-slate-200 dark:bg-slate-900/60 dark:text-slate-300 dark:ring-slate-700">${escapeHtml(getCalendarModulesLabel(profile))}</span>
                </div>
            </button>
        `;
    }).join('');

    const currentViewSave = currentEntity?.id
        ? `
            <div class="rounded-2xl border border-blue-100 bg-blue-50/70 p-4 dark:border-blue-900/60 dark:bg-blue-950/20">
                <div class="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
                    <div class="min-w-0">
                        <div class="text-xs font-black uppercase tracking-[0.18em] text-blue-500 dark:text-blue-300">${escapeHtml(t('schedule.calendar.currentView.title', 'Current page preset'))}</div>
                        <div class="mt-1 text-sm font-black text-slate-900 dark:text-slate-100">${window.getCalendarCurrentViewSummary()}</div>
                        <p class="mt-1 text-xs font-medium text-slate-500 dark:text-slate-400">${escapeHtml(t('schedule.calendar.currentView.description', 'Save this page as an iCal feed.'))}</p>
                    </div>
                    <div class="grid gap-2 sm:flex sm:shrink-0 sm:items-center">
                        <select onchange="window.calendarCurrentViewMode=this.value; renderCalendarSubscription();"
                            class="rounded-xl border border-blue-100 bg-white px-3 py-2 text-xs font-bold text-slate-700 outline-none dark:border-blue-900/60 dark:bg-slate-900 dark:text-slate-100">
                            <option value="all" ${window.calendarCurrentViewMode === 'all' ? 'selected' : ''}>${escapeHtml(t('schedule.calendar.mode.all', 'All classes'))}</option>
                            <option value="exams_only" ${window.calendarCurrentViewMode === 'exams_only' ? 'selected' : ''}>${escapeHtml(t('schedule.calendar.mode.exams', 'Exams only'))}</option>
                        </select>
                        ${renderCalendarButton('schedule.calendar.currentView.save', 'Save', 'bg-blue-600 text-white hover:bg-blue-700 dark:hover:bg-blue-500', 'onclick="createCalendarProfileFromCurrentView()"')}
                    </div>
                </div>
            </div>
        `
        : '';

    const healthRows = selectedProfile ? [
        [t('schedule.calendar.health.cached', 'Cache'), getCalendarCacheStatusLabel(health.cache_status)],
        [t('schedule.calendar.meta.scope', 'Scope'), escapeHtml(selectedProfile.scope_label || selectedProfile.entity_name || selectedProfile.name)],
        [t('schedule.calendar.health.events', 'Events'), escapeHtml(eventCountLabel)],
        [t('schedule.calendar.health.next', 'Next'), nextEventLabel],
        [t('schedule.calendar.health.updated', 'Cache updated'), updatedAtLabel]
    ] : [];
    const compactSummary = selectedProfile
        ? `
            <div class="mt-4 hidden gap-2 md:grid md:grid-cols-3">
                ${renderCalendarValueCard(t('schedule.calendar.activePreset', 'Active preset'), escapeHtml(selectedProfile.name), 'bg-slate-50 dark:bg-slate-900/40')}
                ${renderCalendarValueCard(t('schedule.calendar.health.events', 'Events'), escapeHtml(eventCountLabel), 'bg-slate-50 dark:bg-slate-900/40')}
                ${renderCalendarValueCard(t('schedule.calendar.health.next', 'Next'), nextEventLabel, 'bg-slate-50 dark:bg-slate-900/40')}
            </div>
        `
        : '';

    const moduleDetailsPanel = selectedProfile
        ? `
            <div class="mt-4 rounded-2xl border border-slate-200 bg-slate-50 p-4 dark:border-slate-700 dark:bg-slate-900/60">
                <div class="flex flex-col gap-2 lg:flex-row lg:items-start lg:justify-between">
                    <div class="min-w-0">
                        <div class="text-xs font-black uppercase tracking-[0.18em] text-slate-400">${escapeHtml(t('schedule.calendar.modules.title', 'Preset modules'))}</div>
                        <p class="mt-1 text-sm font-medium text-slate-600 dark:text-slate-300">${escapeHtml(selectedProfileModules.length
                            ? t('schedule.calendar.modules.selectedDescription', 'Only these modules are included in the feed.')
                            : t('schedule.calendar.modules.allDescription', 'This preset includes every module for this schedule.'))}</p>
                    </div>
                    <span class="w-fit rounded-full bg-white px-2.5 py-1 text-[10px] font-black uppercase tracking-wide text-slate-500 ring-1 ring-slate-200 dark:bg-slate-900 dark:text-slate-300 dark:ring-slate-700">
                        ${escapeHtml(modulesLabel)}
                    </span>
                </div>
                <div class="mt-3 flex max-h-32 flex-wrap gap-1.5 overflow-y-auto pr-1">
                    ${renderCalendarModuleChips(selectedProfileModules)}
                </div>
                ${selectedProfile.kind === 'custom' ? `
                    ${moduleEditorCanSave ? `
                        <div class="mt-4 rounded-2xl border border-blue-100 bg-white p-3 dark:border-blue-900/60 dark:bg-slate-900/60">
                            <div class="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                                <div>
                                    <div class="text-xs font-black text-slate-900 dark:text-slate-100">${escapeHtml(t('schedule.calendar.modules.editorTitle', 'Edit modules'))}</div>
                                    <p class="mt-0.5 text-xs text-slate-500 dark:text-slate-400">${escapeHtml(t('schedule.calendar.modules.editorDescription', 'Pick modules from the currently opened schedule and save the preset.'))}</p>
                                </div>
                                <div class="flex flex-wrap gap-2">
                                    ${renderCalendarButton('schedule.calendar.modules.useAll', 'Use all modules', 'border border-slate-200 bg-white text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700', `onclick="selectAllCalendarPresetModules('${escapeJsString(selectedProfile.id)}')"`) }
                                    ${renderCalendarButton('schedule.calendar.modules.resetDraft', 'Reset', 'border border-slate-200 bg-white text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700', `onclick="resetCalendarProfileModuleDraft('${escapeJsString(selectedProfile.id)}')"`) }
                                </div>
                            </div>
                            <div class="mt-3 grid max-h-52 gap-2 overflow-y-auto pr-1 sm:grid-cols-2 xl:grid-cols-3">
                                ${availableProfileModules.map((module) => {
                                    const checked = moduleDraft.has(module);
                                    return `
                                        <label class="flex cursor-pointer items-center gap-2 rounded-xl border px-3 py-2 text-xs font-bold transition-colors ${checked
                                            ? 'border-blue-200 bg-blue-50 text-blue-700 dark:border-blue-800 dark:bg-blue-950/40 dark:text-blue-200'
                                            : 'border-slate-200 bg-white text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800'}">
                                            <input type="checkbox" ${checked ? 'checked' : ''}
                                                onchange="setCalendarPresetModuleDraft('${escapeJsString(selectedProfile.id)}', '${escapeJsString(module)}', this.checked)"
                                                class="h-4 w-4 shrink-0 rounded border-slate-300 text-blue-600 focus:ring-blue-500">
                                            <span class="min-w-0 flex-1 truncate">${escapeHtml(module)}</span>
                                        </label>
                                    `;
                                }).join('')}
                            </div>
                            <div class="mt-3 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                                <div class="text-xs font-medium text-slate-500 dark:text-slate-400">
                                    ${escapeHtml(t('schedule.calendar.modules.draftCount', 'Selected now: {count}', { count: moduleDraftCount }))}
                                </div>
                                ${renderCalendarButton('schedule.calendar.modules.save', 'Save modules', 'bg-blue-600 text-white hover:bg-blue-700 dark:hover:bg-blue-500', `onclick="saveCalendarProfileModuleDraft('${escapeJsString(selectedProfile.id)}')"`) }
                            </div>
                        </div>
                    ` : `
                        <div class="mt-4 flex flex-col gap-3 rounded-2xl border border-amber-200 bg-amber-50 p-3 text-xs font-medium text-amber-700 dark:border-amber-900/60 dark:bg-amber-950/30 dark:text-amber-300 sm:flex-row sm:items-center sm:justify-between">
                            <span>${escapeHtml(t('schedule.calendar.modules.openScheduleHint', 'Open this preset schedule page to edit its module checklist.'))}</span>
                            ${selectedProfile.entity_type && selectedProfile.entity_id
                                ? renderCalendarButton('schedule.calendar.modules.openSchedule', 'Open schedule', 'border border-amber-200 bg-white text-amber-700 hover:bg-amber-100 dark:border-amber-900/70 dark:bg-slate-900 dark:text-amber-300 dark:hover:bg-amber-950/40', `onclick="openCalendarPresetSchedule('${escapeJsString(selectedProfile.id)}')"`)
                                : ''}
                        </div>
                    `}
                ` : ''}
            </div>
        `
        : '';

    const profileSettings = selectedProfile
        ? `
            <div class="rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900/40">
                <div class="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                    <div class="min-w-0">
                        <div class="text-xs font-black uppercase tracking-[0.18em] text-slate-400">${escapeHtml(t('schedule.calendar.profileSettings', 'Profile settings'))}</div>
                        <div class="mt-1 text-base font-black text-slate-900 dark:text-slate-100">${escapeHtml(selectedProfile.name)}</div>
                        <p class="mt-1 text-sm text-slate-500 dark:text-slate-400">${escapeHtml(selectedProfileDescription)}</p>
                    </div>
                    ${selectedProfile.kind === 'custom' ? `
                        <div class="flex flex-wrap gap-2">
                            ${renderCalendarButton('schedule.calendar.rename', 'Rename', 'border border-slate-200 bg-white text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700', `onclick="renameCalendarSubscriptionProfile('${escapeJsString(selectedProfile.id)}')"`) }
                            ${canUpdateModulesFromCurrentView ? renderCalendarButton('schedule.calendar.updateModules', 'Use current filters', 'border border-blue-200 bg-blue-50 text-blue-700 hover:bg-blue-100 dark:border-blue-800 dark:bg-blue-950/40 dark:text-blue-200 dark:hover:bg-blue-900/50', `onclick="updateCalendarSubscriptionProfile('${escapeJsString(selectedProfile.id)}', { modules: window.getCalendarCurrentViewModules() })"`) : ''}
                        </div>
                    ` : ''}
                </div>
                <div class="mt-4 grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
                    <div class="rounded-xl bg-slate-50 p-3 dark:bg-slate-800/70">
                        <div class="text-[10px] font-black uppercase tracking-[0.16em] text-slate-400">${escapeHtml(t('schedule.calendar.meta.type', 'Type'))}</div>
                        <div class="mt-1 text-xs font-bold text-slate-700 dark:text-slate-200">${escapeHtml(profileKindLabel)}</div>
                    </div>
                    <div class="rounded-xl bg-slate-50 p-3 dark:bg-slate-800/70">
                        <div class="text-[10px] font-black uppercase tracking-[0.16em] text-slate-400">${escapeHtml(t('schedule.calendar.meta.mode', 'Mode'))}</div>
                        ${selectedProfile.kind === 'custom' ? `
                            <select onchange="updateCalendarSubscriptionProfile('${escapeJsString(selectedProfile.id)}', { lesson_mode: this.value })"
                                class="mt-1 w-full rounded-lg border border-slate-200 bg-white px-2 py-1 text-xs font-bold text-slate-700 outline-none dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200">
                                <option value="all" ${selectedProfile.lesson_mode === 'all' ? 'selected' : ''}>${escapeHtml(t('schedule.calendar.mode.all', 'All classes'))}</option>
                                <option value="exams_only" ${selectedProfile.lesson_mode === 'exams_only' ? 'selected' : ''}>${escapeHtml(t('schedule.calendar.mode.exams', 'Exams only'))}</option>
                            </select>
                        ` : `<div class="mt-1 text-xs font-bold text-slate-700 dark:text-slate-200">${escapeHtml(lessonModeLabel)}</div>`}
                    </div>
                    <div class="rounded-xl bg-slate-50 p-3 dark:bg-slate-800/70">
                        <div class="text-[10px] font-black uppercase tracking-[0.16em] text-slate-400">${escapeHtml(t('schedule.calendar.meta.modules', 'Modules'))}</div>
                        <div class="mt-1 text-xs font-bold text-slate-700 dark:text-slate-200">${escapeHtml(modulesLabel)}</div>
                    </div>
                    <div class="rounded-xl bg-slate-50 p-3 dark:bg-slate-800/70">
                        <div class="text-[10px] font-black uppercase tracking-[0.16em] text-slate-400">${escapeHtml(t('schedule.calendar.meta.subscriptions', 'Subscriptions'))}</div>
                        <div class="mt-1 text-xs font-bold text-slate-700 dark:text-slate-200">${escapeHtml(String(selectedProfile.subscription_count ?? 0))}</div>
                    </div>
                </div>
                ${moduleDetailsPanel}
            </div>
        `
        : '';

    const platformGuideKey = calendarPlatform === 'google'
        ? 'schedule.calendar.platform.googleHint'
        : calendarPlatform === 'outlook'
            ? 'schedule.calendar.platform.outlookHint'
            : 'schedule.calendar.platform.appleHint';
    const platformGuideFallback = calendarPlatform === 'google'
        ? 'Copy the HTTPS URL and add it in Google Calendar from Other calendars -> From URL.'
        : calendarPlatform === 'outlook'
            ? 'Copy the HTTPS URL and add it as an internet calendar in Outlook or another calendar app.'
            : 'Use the iOS / Mac button to open the subscription directly in Apple Calendar.';
    const platformPrimaryAction = calendarPlatform === 'apple'
        ? renderCalendarButton('schedule.calendar.apple', 'Open on iOS / Mac', 'bg-blue-600 text-white hover:bg-blue-700 dark:hover:bg-blue-500', `onclick="openCalendarProfileLink('webcal')"`)
        : renderCalendarButton('schedule.calendar.copy', 'Copy link', 'bg-slate-900 text-white hover:bg-slate-800 dark:bg-blue-600 dark:hover:bg-blue-500', 'onclick="copyCalendarSubscriptionLink(event)"');
    const connectionPanel = state.eligibility?.available
        ? `
            <div class="rounded-2xl border border-slate-200 bg-slate-50 p-4 dark:border-slate-700 dark:bg-slate-900/60">
                <div class="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                    <div class="min-w-0">
                        <div class="text-xs font-black uppercase tracking-[0.18em] text-slate-400">${escapeHtml(t('schedule.calendar.connectionTitle', 'Connection'))}</div>
                        <div class="mt-1 text-base font-black text-slate-900 dark:text-slate-100">${escapeHtml(isReady ? t('schedule.calendar.connectionReady', 'Subscription link is ready') : t('schedule.calendar.connectionNeedsSetup', 'Subscription needs attention'))}</div>
                        <p class="mt-1 text-sm text-slate-500 dark:text-slate-400">${escapeHtml(t('schedule.calendar.connectionDescription', 'Choose the target calendar app, then copy or open the private URL.'))}</p>
                    </div>
                    ${isReady ? `<span class="w-fit rounded-full bg-emerald-100 px-3 py-1 text-xs font-black text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300">${escapeHtml(t('schedule.calendar.linkReady', 'Link ready'))}</span>` : ''}
                </div>
                ${isReady ? `
                    <div class="mt-4 grid gap-2 xl:grid-cols-[minmax(0,1fr)_auto]">
                        <input readonly value="${escapeHtml(shownUrl)}"
                            class="min-w-0 rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-mono text-slate-600 outline-none dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
                        <div class="grid gap-2 sm:flex sm:flex-wrap">
                            ${renderCalendarButton(isRevealed ? 'schedule.calendar.hide' : 'schedule.calendar.reveal', isRevealed ? 'Hide' : 'Show', 'border border-slate-200 bg-white text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700', `onclick="toggleCalendarProfileReveal('${escapeJsString(selectedProfile.id)}')"`) }
                            ${renderCalendarButton('schedule.calendar.copy', 'Copy link', 'bg-slate-900 text-white hover:bg-slate-800 dark:bg-blue-600 dark:hover:bg-blue-500', 'onclick="copyCalendarSubscriptionLink(event)"')}
                        </div>
                    </div>
                    <div class="mt-4 rounded-2xl border border-slate-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-900/50">
                        <div class="flex flex-wrap gap-2">
                            ${renderCalendarPlatformTab('apple', 'schedule.calendar.platform.apple', 'iOS / Mac')}
                            ${renderCalendarPlatformTab('google', 'schedule.calendar.platform.google', 'Google')}
                            ${renderCalendarPlatformTab('outlook', 'schedule.calendar.platform.outlook', 'Outlook / other')}
                        </div>
                        <div class="mt-3 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                            <p class="text-sm font-medium text-slate-600 dark:text-slate-300">${escapeHtml(t(platformGuideKey, platformGuideFallback))}</p>
                            <div class="grid gap-2 sm:flex sm:shrink-0 sm:flex-wrap">
                                ${platformPrimaryAction}
                                ${renderCalendarButton('schedule.calendar.preview', 'Preview feed', 'border border-slate-200 bg-white text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700', `onclick="openCalendarProfileLink('preview')"`) }
                                ${renderCalendarButton('schedule.calendar.download', 'Download ICS', 'border border-slate-200 bg-white text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700', `onclick="openCalendarProfileLink('download')"`) }
                            </div>
                        </div>
                    </div>
                ` : `
                    <div class="mt-4 flex flex-col gap-3 rounded-xl bg-amber-50 px-3 py-3 text-sm font-medium text-amber-700 dark:bg-amber-950/40 dark:text-amber-300 sm:flex-row sm:items-center sm:justify-between">
                        <span>${escapeHtml(unavailableMessage)}</span>
                        ${!state.sync_enabled ? renderCalendarButton('schedule.calendar.enable', 'Enable', 'bg-amber-600 text-white hover:bg-amber-700', `onclick="toggleCalendarSync(true)"`) : ''}
                    </div>
                `}
            </div>
        `
        : `
            <div class="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm font-medium text-amber-700 dark:border-amber-900/60 dark:bg-amber-950/30 dark:text-amber-300">
                ${escapeHtml(t('schedule.calendar.unavailable', unavailableMessage))}
            </div>
        `;

    const diagnosticsPanel = selectedProfile
        ? `
            <details class="group rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900/40">
                <summary class="flex cursor-pointer list-none items-center justify-between gap-3 text-sm font-black text-slate-800 dark:text-slate-100">
                    <span>${escapeHtml(t('schedule.calendar.diagnostics', 'Diagnostics and management'))}</span>
                    ${renderCalendarDisclosureChevron()}
                </summary>
                <div class="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-5">
                    ${healthRows.map(([label, value]) => renderCalendarValueCard(label, value)).join('')}
                </div>
                <div class="mt-4 rounded-2xl border border-rose-100 bg-rose-50/50 p-4 dark:border-rose-900/50 dark:bg-rose-950/20">
                    <div class="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                        <div>
                            <div class="text-xs font-black uppercase tracking-[0.16em] text-rose-500 dark:text-rose-300">${escapeHtml(t('schedule.calendar.dangerZone', 'Danger zone'))}</div>
                            <p class="mt-1 text-sm font-medium text-rose-700 dark:text-rose-200">${escapeHtml(t('schedule.calendar.dangerDescription', 'Resetting or disabling affects all external calendar apps using this link.'))}</p>
                        </div>
                        <div class="grid gap-2 sm:flex sm:flex-wrap sm:justify-end">
                            ${renderCalendarButton('schedule.calendar.reset', 'Reset link', 'border border-rose-200 bg-white text-rose-600 hover:bg-rose-50 dark:border-rose-900/70 dark:bg-slate-800 dark:text-rose-300 dark:hover:bg-rose-950/30', 'onclick="resetCalendarSubscription()"')}
                            ${renderCalendarButton(state.sync_enabled ? 'schedule.calendar.disable' : 'schedule.calendar.enable', state.sync_enabled ? 'Disable' : 'Enable', 'border border-slate-200 bg-white text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700', `onclick="toggleCalendarSync(${state.sync_enabled ? 'false' : 'true'})"`)}
                            ${selectedProfile.can_delete ? renderCalendarButton('schedule.calendar.delete', 'Delete preset', 'border border-rose-200 bg-white text-rose-600 hover:bg-rose-50 dark:border-rose-900/70 dark:bg-slate-800 dark:text-rose-300 dark:hover:bg-rose-950/30', `onclick="deleteCalendarSubscriptionProfile('${escapeJsString(selectedProfile.id)}')"`) : ''}
                        </div>
                    </div>
                </div>
            </details>
        `
        : '';
    const toggleLabel = isCalendarPanelCollapsed
        ? t('schedule.calendar.expand', 'Expand')
        : t('schedule.calendar.collapse', 'Collapse');
    const bodyHtml = isCalendarPanelCollapsed
        ? ''
        : `
            <div id="calendarSubscriptionBody" class="mt-5 space-y-4">
                ${profiles.length ? `
                    <section class="space-y-3">
                        <div class="flex items-center justify-between gap-3">
                            <h3 class="text-sm font-black text-slate-900 dark:text-slate-100">${escapeHtml(t('schedule.calendar.presetsTitle', 'Presets'))}</h3>
                            <span class="rounded-full bg-slate-100 px-2.5 py-1 text-[10px] font-black uppercase tracking-wide text-slate-500 dark:bg-slate-900 dark:text-slate-300">${escapeHtml(t('schedule.calendar.presetsCount', '{count} profiles', { count: profiles.length }))}</span>
                        </div>
                        <div class="grid gap-2 lg:grid-cols-3">${profileButtons}</div>
                    </section>
                ` : ''}
                ${currentViewSave}
                ${profileSettings}
                ${connectionPanel}
                ${diagnosticsPanel}
                <p class="text-xs text-slate-500 dark:text-slate-400">${escapeHtml(t('schedule.calendar.instructions', 'Use the iOS / Mac button for Apple Calendar. For Google Calendar, copy the HTTPS URL and add it from URL in the web version.'))}</p>
            </div>
        `;

    container.innerHTML = `
        <div class="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-700 dark:bg-slate-800">
            <div class="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
                <div class="min-w-0">
                    <div class="flex flex-wrap items-center gap-2">
                        <div class="text-xs font-black uppercase tracking-[0.2em] text-blue-500 dark:text-blue-300">${escapeHtml(t('schedule.calendar.eyebrow', 'Sync'))}</div>
                        <span class="rounded-full px-3 py-1 text-xs font-black ${statusClass}">${escapeHtml(t(statusKey, statusFallback))}</span>
                    </div>
                    <h2 class="mt-1 text-xl font-black text-slate-900 dark:text-slate-100">${escapeHtml(t('schedule.calendar.title', 'Calendar subscription'))}</h2>
                    <p class="mt-1 max-w-3xl text-sm text-slate-600 dark:text-slate-300">${escapeHtml(selectedProfile ? selectedProfileDescription : t('schedule.calendar.description', 'Connect your personal ICS feed to Apple Calendar, Google Calendar, or any other calendar app.'))}</p>
                    ${selectedProfile ? `
                        <div class="mt-3 flex flex-wrap gap-1.5">
                            <span class="rounded-full bg-slate-100 px-2.5 py-1 text-[10px] font-black text-slate-600 dark:bg-slate-900 dark:text-slate-300">${escapeHtml(selectedProfile.name)}</span>
                            <span class="rounded-full bg-slate-100 px-2.5 py-1 text-[10px] font-black uppercase tracking-wide text-slate-600 dark:bg-slate-900 dark:text-slate-300">${escapeHtml(eventCountLabel)}</span>
                            <span class="rounded-full bg-slate-100 px-2.5 py-1 text-[10px] font-black uppercase tracking-wide text-slate-600 dark:bg-slate-900 dark:text-slate-300">${escapeHtml(modulesLabel)}</span>
                        </div>
                    ` : ''}
                </div>
                <div class="grid gap-2 sm:flex sm:flex-wrap sm:items-center sm:justify-end xl:shrink-0">
                    ${isReady ? renderCalendarButton('schedule.calendar.copy', 'Copy link', 'bg-slate-900 text-white hover:bg-slate-800 dark:bg-blue-600 dark:hover:bg-blue-500', 'onclick="copyCalendarSubscriptionLink(event)"') : ''}
                    ${!state.sync_enabled ? renderCalendarButton('schedule.calendar.enable', 'Enable', 'bg-blue-600 text-white hover:bg-blue-700 dark:hover:bg-blue-500', `onclick="toggleCalendarSync(true)"`) : ''}
                    ${renderCalendarBotLink('border border-blue-200 bg-blue-50 text-blue-700 hover:bg-blue-100 dark:border-blue-800 dark:bg-blue-950/40 dark:text-blue-200 dark:hover:bg-blue-900/50')}
                    <button type="button" onclick="toggleCalendarSubscriptionPanel()"
                        aria-expanded="${String(!isCalendarPanelCollapsed)}"
                        aria-controls="calendarSubscriptionBody"
                        aria-label="${escapeHtml(toggleLabel)}"
                        class="inline-flex items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-bold text-slate-600 transition-colors hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700">
                        <span>${escapeHtml(toggleLabel)}</span>
                        <svg class="h-3.5 w-3.5 transition-transform ${isCalendarPanelCollapsed ? '' : 'rotate-180'}" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path d="M19 9l-7 7-7-7" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"></path>
                        </svg>
                    </button>
                </div>
            </div>
            ${isCalendarPanelCollapsed ? compactSummary : bodyHtml}
        </div>
    `;
    focusCalendarSyncPanelIfRequested(container);
}

window.renderCalendarSubscription = renderCalendarSubscription;
window._renderCalendarSubscriptionImpl = renderCalendarSubscription;

window.addEventListener('mpb-telegram-auth-settled', () => {
    if (!scheduleAuthUser) renderCalendarSubscription();
});

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

window.openCalendarPresetSchedule = async function(profileId) {
    const profile = (calendarSubscriptionState.profiles || []).find((item) => item.id === profileId);
    if (!profile?.entity_type || !profile?.entity_id || typeof loadSchedule !== 'function') return;
    const profileModules = Array.isArray(profile.modules) ? profile.modules.filter(Boolean) : [];
    if (profileModules.length && typeof selectedModules !== 'undefined') {
        selectedModules = new Set(profileModules);
    }
    await loadSchedule(profile.entity_type, profile.entity_id, profile.entity_name || profile.name || '', null, {
        preserveModules: profileModules.length > 0,
        calendarProfileId: profile.id,
        urlMode: 'push'
    });
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

function getCalendarCacheStatusLabel(status) {
    if (status === 'cached') return escapeHtml(t('schedule.calendar.health.cached', 'Cache ready'));
    if (status === 'partial-cache') return escapeHtml(t('schedule.calendar.health.partial', 'Partial cache'));
    return escapeHtml(t('schedule.calendar.health.empty', 'No cached classes'));
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

window.copyCalendarSubscriptionLink = function(event) {
    const selectedProfile = window.getSelectedCalendarProfile();
    if (!selectedProfile?.links?.http_url || !calendarSubscriptionState.sync_enabled) return;
    copyToClipboard(selectedProfile.links.http_url, event);
}

window.openCalendarProfileLink = function(kind) {
    const selectedProfile = window.getSelectedCalendarProfile();
    if (!selectedProfile || !calendarSubscriptionState.sync_enabled) return;
    const targetUrl = kind === 'download'
        ? selectedProfile.links.download_url
        : kind === 'webcal'
            ? selectedProfile.links.webcal_url
            : selectedProfile.links.preview_url;
    if (!targetUrl) return;
    if (kind === 'webcal') window.location.href = targetUrl;
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
            modules: window.getCalendarCurrentViewModules()
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
