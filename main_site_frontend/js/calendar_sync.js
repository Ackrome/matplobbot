const CALENDAR_PLATFORM_KEY = "mpb_calendar_sync_platform";
const CALENDAR_REVEALED_PROFILES_KEY = "mpb_calendar_sync_revealed_profiles";
let calendarPlatform = loadCalendarPlatform();
let revealedCalendarProfileIds = loadRevealedCalendarProfileIds();
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
calendarSubscriptionState = createDefaultCalendarSubscriptionState();

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
        return escapeHtml(t('schedule.calendar.currentView.empty', 'Откройте расписание, чтобы сохранить страницу как отдельную ленту.'));
    }
    const modules = window.getCalendarCurrentViewModules();
    const modulesLabel = allAvailableModules.length === 0
        ? escapeHtml(t('schedule.calendar.currentView.noModules', 'Нет фильтра по модулям'))
        : modules.length === allAvailableModules.length
            ? escapeHtml(t('schedule.calendar.currentView.allModules', 'Все модули'))
            : escapeHtml(
                t(
                    'schedule.calendar.currentView.someModules',
                    'Выбрано модулей: {count}',
                    { count: modules.length }
                )
            );
    return `${escapeHtml(currentEntity.name)} - ${modulesLabel}`;
}

function getCalendarCacheStatusLabel(status) {
    if (status === 'cached') return escapeHtml(t('schedule.calendar.health.cached', 'Кэш готов'));
    if (status === 'partial-cache') return escapeHtml(t('schedule.calendar.health.partial', 'Частичный кэш'));
    return escapeHtml(t('schedule.calendar.health.empty', 'Нет закэшированных занятий'));
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
        window.mpbPopup?.(error.message || t('schedule.calendar.error', 'Ошибка загрузки.'), { type: 'error' });
        return null;
    }
}

window.resetCalendarSubscription = async function() {
    if (!window.confirm(t('schedule.calendar.confirmReset', 'Сбросить приватную ссылку?'))) return;
    await performCalendarMutation(`${API_BASE}/cal/subscription/reset`, { method: 'POST' }, { justReset: true });
}

window.toggleCalendarSync = async function(enabled) {
    const confirmKey = enabled ? 'schedule.calendar.confirmEnable' : 'schedule.calendar.confirmDisable';
    const fallback = enabled
        ? 'Включить синхронизацию?'
        : 'Выключить синхронизацию?';
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
    if (!window.confirm(t('schedule.calendar.confirmDelete', 'Удалить пресет?'))) return;
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
const originalToggleModule = toggleModule;
toggleModule = function(...args) {
    originalToggleModule(...args);
    renderCalendarSubscription();
};
const originalSelectAllModules = selectAllModules;
selectAllModules = function(...args) {
    originalSelectAllModules(...args);
    renderCalendarSubscription();
};
const originalClearAllModules = clearAllModules;
clearAllModules = function(...args) {
    originalClearAllModules(...args);
    renderCalendarSubscription();
};