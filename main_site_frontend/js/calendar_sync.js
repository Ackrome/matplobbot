const CALENDAR_PLATFORM_KEY = "mpb_calendar_sync_platform";
const CALENDAR_REVEALED_PROFILES_KEY = "mpb_calendar_sync_revealed_profiles";
const CALENDAR_PANEL_COLLAPSED_KEY = "mpb_calendar_sync_collapsed";
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
        : 'bg-amber-100 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300';

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
    const profileButtons = profiles.map((profile) => {
        const active = profile.selected;
        const typeLabel = profile.kind === 'custom'
            ? t('schedule.calendar.profile.custom', 'Preset')
            : t('schedule.calendar.profile.builtin', 'Built-in');
        return `
            <button type="button" onclick="selectCalendarSubscriptionProfile('${escapeJsString(profile.id)}')"
                class="min-w-0 rounded-2xl border px-3 py-2 text-left transition-colors ${active
                    ? 'border-blue-200 bg-blue-50 text-blue-700 dark:border-blue-800 dark:bg-blue-950/40 dark:text-blue-200'
                    : 'border-slate-200 bg-white text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700'}">
                <div class="truncate text-xs font-black">${escapeHtml(profile.name)}</div>
                <div class="mt-0.5 text-[10px] uppercase tracking-wide opacity-70">${escapeHtml(typeLabel)}</div>
            </button>
        `;
    }).join('');

    const currentViewSave = currentEntity?.id
        ? `
            <div class="rounded-2xl border border-blue-100 bg-blue-50/60 p-4 dark:border-blue-900/60 dark:bg-blue-950/20">
                <div class="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                    <div class="min-w-0">
                        <div class="text-xs font-black uppercase tracking-[0.18em] text-blue-500 dark:text-blue-300">${escapeHtml(t('schedule.calendar.currentView.title', 'Current page preset'))}</div>
                        <div class="mt-1 text-sm font-bold text-slate-800 dark:text-slate-100">${window.getCalendarCurrentViewSummary()}</div>
                    </div>
                    <div class="flex shrink-0 items-center gap-2">
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

    const urlValue = selectedProfile?.links?.http_url || state.http_url || '';
    const maskedUrl = selectedProfile?.links?.masked_http_url || state.masked_http_url || urlValue;
    const isRevealed = selectedProfile?.id && revealedCalendarProfileIds.has(selectedProfile.id);
    const shownUrl = isRevealed ? urlValue : maskedUrl;
    const health = selectedProfile?.health || {};
    const unavailableMessage = state.eligibility?.detail || t('schedule.calendar.unavailable', 'Calendar subscription requires a linked Telegram account.');
    const healthRows = selectedProfile ? [
        [t('schedule.calendar.health.cached', 'Cache'), getCalendarCacheStatusLabel(health.cache_status)],
        [t('schedule.calendar.meta.scope', 'Scope'), escapeHtml(selectedProfile.scope_label || selectedProfile.entity_name || selectedProfile.name)],
        [t('schedule.calendar.health.events', 'Events'), escapeHtml(String(health.event_count ?? 0))],
        [t('schedule.calendar.health.next', 'Next'), health.next_event_at ? formatCalendarDateTime(health.next_event_at, health.next_event_label || '') : escapeHtml('-')],
        [t('schedule.calendar.health.updated', 'Cache updated'), health.source_updated_at ? formatCalendarDateTime(health.source_updated_at, '') : escapeHtml('-')]
    ] : [];

    const urlPanel = state.eligibility?.available
        ? `
            <div class="rounded-2xl border border-slate-200 bg-slate-50 p-4 dark:border-slate-700 dark:bg-slate-900/60">
                <div class="mb-2 text-xs font-black uppercase tracking-[0.18em] text-slate-400">${escapeHtml(t('schedule.calendar.urlLabel', 'Subscription URL'))}</div>
                ${isReady ? `
                    <div class="flex flex-col gap-2 lg:flex-row">
                        <input readonly value="${escapeHtml(shownUrl)}"
                            class="min-w-0 flex-1 rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-mono text-slate-600 outline-none dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
                        <div class="flex flex-wrap gap-2">
                            ${renderCalendarButton(isRevealed ? 'schedule.calendar.hide' : 'schedule.calendar.reveal', isRevealed ? 'Hide' : 'Show', 'border border-slate-200 bg-white text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700', `onclick="toggleCalendarProfileReveal('${escapeJsString(selectedProfile.id)}')"`) }
                            ${renderCalendarButton('schedule.calendar.copy', 'Copy link', 'bg-slate-900 text-white hover:bg-slate-800 dark:bg-blue-600 dark:hover:bg-blue-500', 'onclick="copyCalendarSubscriptionLink(event)"')}
                            ${renderCalendarButton('schedule.calendar.apple', 'iOS / Mac', 'bg-blue-600 text-white hover:bg-blue-700 dark:hover:bg-blue-500', `onclick="openCalendarProfileLink('webcal')"`) }
                        </div>
                    </div>
                    <div class="mt-3 flex flex-wrap gap-2">
                        ${renderCalendarButton('schedule.calendar.preview', 'Preview feed', 'border border-slate-200 bg-white text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700', `onclick="openCalendarProfileLink('preview')"`) }
                        ${renderCalendarButton('schedule.calendar.download', 'Download ICS', 'border border-slate-200 bg-white text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700', `onclick="openCalendarProfileLink('download')"`) }
                        ${renderCalendarButton('schedule.calendar.reset', 'Reset link', 'border border-rose-200 bg-white text-rose-600 hover:bg-rose-50 dark:border-rose-900/70 dark:bg-slate-800 dark:text-rose-300 dark:hover:bg-rose-950/30', 'onclick="resetCalendarSubscription()"')}
                        ${renderCalendarButton(state.sync_enabled ? 'schedule.calendar.disable' : 'schedule.calendar.enable', state.sync_enabled ? 'Disable' : 'Enable', 'border border-slate-200 bg-white text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700', `onclick="toggleCalendarSync(${state.sync_enabled ? 'false' : 'true'})"`)}
                    </div>
                ` : `
                    <div class="rounded-xl bg-amber-50 px-3 py-2 text-sm font-medium text-amber-700 dark:bg-amber-950/40 dark:text-amber-300">${escapeHtml(unavailableMessage)}</div>
                `}
            </div>
        `
        : `
            <div class="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm font-medium text-amber-700 dark:border-amber-900/60 dark:bg-amber-950/30 dark:text-amber-300">
                ${escapeHtml(t('schedule.calendar.unavailable', unavailableMessage))}
            </div>
        `;

    const deleteButton = selectedProfile?.can_delete
        ? renderCalendarButton('schedule.calendar.delete', 'Delete preset', 'border border-rose-200 bg-white text-rose-600 hover:bg-rose-50 dark:border-rose-900/70 dark:bg-slate-800 dark:text-rose-300 dark:hover:bg-rose-950/30', `onclick="deleteCalendarSubscriptionProfile('${escapeJsString(selectedProfile.id)}')"`)
        : '';
    const toggleLabel = isCalendarPanelCollapsed
        ? t('schedule.calendar.expand', 'Expand')
        : t('schedule.calendar.collapse', 'Collapse');
    const bodyHtml = isCalendarPanelCollapsed
        ? ''
        : `
            <div id="calendarSubscriptionBody" class="mt-5 space-y-4">
                ${profiles.length ? `<div class="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">${profileButtons}</div>` : ''}
                ${currentViewSave}
                ${urlPanel}
                ${selectedProfile ? `
                    <div class="grid gap-2 sm:grid-cols-2 lg:grid-cols-5">
                        ${healthRows.map(([label, value]) => `
                            <div class="rounded-2xl border border-slate-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-900/40">
                                <div class="text-[10px] font-black uppercase tracking-[0.16em] text-slate-400">${escapeHtml(label)}</div>
                                <div class="mt-1 line-clamp-2 text-xs font-bold text-slate-700 dark:text-slate-200">${value}</div>
                            </div>
                        `).join('')}
                    </div>
                ` : ''}
                <p class="text-xs text-slate-500 dark:text-slate-400">${escapeHtml(t('schedule.calendar.instructions', 'Use the iOS / Mac button for Apple Calendar. For Google Calendar, copy the HTTPS URL and add it from URL in the web version.'))}</p>
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
                    ${isCalendarPanelCollapsed ? '' : deleteButton}
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
