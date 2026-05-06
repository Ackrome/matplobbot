const API_BASE = window.getMpbApiBase ? window.getMpbApiBase() : "/api";
const STORAGE_KEY = "mpb_user_preferences";
const SCHEDULE_SNAPSHOTS_KEY = "mpb_schedule_snapshots";
const SCHEDULE_ENTITY_TYPES = new Set(['group', 'person', 'auditorium']);
const SCHEDULE_VIEW_MODES = new Set(['auto', 'table', 'cards', 'compact', 'exams']);
const SCHEDULE_LESSON_MODES = new Set(['all', 'exams_only']);
const MODULE_PRESET_LIMIT = 12;
const FIXED_TIMES =[
    { start: '08:30', end: '10:00' },
    { start: '10:10', end: '11:40' },
    { start: '11:50', end: '13:20' },
    { start: '14:00', end: '15:30' },
    { start: '15:40', end: '17:10' },
    { start: '17:20', end: '18:50' },
    { start: '18:55', end: '20:25' },
    { start: '20:30', end: '22:00' }
];
const TABLE_SLOT_ROW_HEIGHT_PX = 144;
const TABLE_TIMELINE_VERTICAL_INSET_PX = 6;
const TABLE_TIMELINE_LANE_GAP_PX = 8;
let fixedTimeSlotRangesCache = null;

let fullSchedule =[];
let loadedBounds = { start: null, end: null };
let sourceUpdatedAt = null;
let currentEntity = { type: null, id: null, name: null };
let allAvailableModules =[];
let selectedModules = new Set();
let isOfflineMode = false;
let currentWeekStart = getMonday(new Date());
let cachedOfflineEntities = [];
let latestSearchResults =[];
let latestSearchQuery = '';
let searchCategory = 'all';
let searchRequestSeq = 0;
let moduleFilterQuery = '';
let modulePresets = [];
let scheduleChangeSummary = null;
let lessonActionMap = new Map();
let isRefreshingScheduleCache = false;

function createDefaultSchedulePageState() {
    return {
        entity: { type: null, id: null, name: null },
        date: getISODateStr(new Date()),
        viewMode: 'cards',
        selectedModules: [],
        lessonMode: 'all',
        offline: false,
        calendarProfileId: null,
        showChanges: false
    };
}

let schedulePageState = createDefaultSchedulePageState();
window.schedulePageState = schedulePageState;

function normalizeScheduleEntity(entity) {
    const type = SCHEDULE_ENTITY_TYPES.has(String(entity?.type || '').toLowerCase())
        ? String(entity.type).toLowerCase()
        : null;
    const id = entity?.id === undefined || entity?.id === null ? null : String(entity.id);
    const name = entity?.name === undefined || entity?.name === null ? null : String(entity.name);
    return type && id ? { type, id, name: name || id } : { type: null, id: null, name: null };
}

function getScheduleEntityKey(entity) {
    const normalized = normalizeScheduleEntity(entity);
    return normalized.type && normalized.id ? `${normalized.type}:${normalized.id}` : '';
}

function normalizeScheduleDate(value) {
    const raw = String(value || '').trim();
    if (!/^\d{4}-\d{2}-\d{2}$/.test(raw)) return null;
    const parsed = new Date(`${raw}T00:00:00`);
    return Number.isNaN(parsed.getTime()) ? null : raw;
}

function normalizeScheduleModules(value) {
    if (!Array.isArray(value)) return [];
    return Array.from(new Set(value.map((module) => String(module).trim()).filter(Boolean)));
}

function normalizeScheduleViewMode(value) {
    const mode = String(value || '').trim();
    return SCHEDULE_VIEW_MODES.has(mode) ? mode : 'cards';
}

function normalizeScheduleLessonMode(value) {
    const mode = String(value || '').trim();
    return SCHEDULE_LESSON_MODES.has(mode) ? mode : 'all';
}

function setSchedulePageState(patch = {}) {
    schedulePageState = {
        entity: patch.entity !== undefined
            ? normalizeScheduleEntity(patch.entity)
            : normalizeScheduleEntity(schedulePageState.entity),
        date: normalizeScheduleDate(patch.date) || schedulePageState.date || getISODateStr(new Date()),
        viewMode: normalizeScheduleViewMode(patch.viewMode ?? schedulePageState.viewMode),
        selectedModules: patch.selectedModules !== undefined
            ? normalizeScheduleModules(patch.selectedModules)
            : normalizeScheduleModules(schedulePageState.selectedModules),
        lessonMode: normalizeScheduleLessonMode(patch.lessonMode ?? schedulePageState.lessonMode),
        offline: Boolean(patch.offline ?? schedulePageState.offline),
        calendarProfileId: patch.calendarProfileId === undefined
            ? schedulePageState.calendarProfileId
            : (patch.calendarProfileId ? String(patch.calendarProfileId) : null),
        showChanges: Boolean(patch.showChanges ?? schedulePageState.showChanges)
    };
    window.schedulePageState = schedulePageState;
    window.dispatchEvent(new CustomEvent('mpb-schedule-state-change', { detail: { state: window.getSchedulePageState() } }));
    return schedulePageState;
}

window.getSchedulePageState = function() {
    return {
        ...schedulePageState,
        entity: { ...schedulePageState.entity },
        selectedModules: [...schedulePageState.selectedModules]
    };
}

function parseScheduleStateFromUrl() {
    const params = new URLSearchParams(window.location.search);
    const entity = normalizeScheduleEntity({
        type: params.get('type'),
        id: params.get('id'),
        name: params.get('name')
    });
    const modulesParam = params.get('modules');
    const modules = modulesParam && modulesParam !== 'all' && modulesParam !== 'none'
        ? modulesParam.split(',').map((item) => item.trim())
        : [];
    return {
        entity,
        date: normalizeScheduleDate(params.get('date')) || getISODateStr(new Date()),
        viewMode: normalizeScheduleViewMode(params.get('view')),
        selectedModules: normalizeScheduleModules(modules),
        lessonMode: normalizeScheduleLessonMode(params.get('mode')),
        offline: params.get('offline') === '1',
        calendarProfileId: params.get('profile') || null,
        showChanges: params.get('changes') === '1',
        hasEntity: Boolean(entity.id),
        hasModules: Boolean(modulesParam && modulesParam !== 'all'),
        hasEmptyModules: modulesParam === 'none'
    };
}

function buildScheduleStateFromPreferences(prefs = {}) {
    const state = {
        entity: normalizeScheduleEntity(prefs.entity),
        date: normalizeScheduleDate(prefs.date || prefs.scheduleState?.date) || getISODateStr(new Date()),
        viewMode: normalizeScheduleViewMode(prefs.viewMode || prefs.scheduleState?.viewMode),
        selectedModules: normalizeScheduleModules(prefs.modules || prefs.scheduleState?.selectedModules),
        lessonMode: normalizeScheduleLessonMode(prefs.lessonMode || prefs.scheduleState?.lessonMode),
        offline: false,
        calendarProfileId: prefs.calendarProfileId || prefs.scheduleState?.calendarProfileId || null,
        showChanges: Boolean(prefs.showChanges || prefs.scheduleState?.showChanges)
    };
    return { ...state, hasEntity: Boolean(state.entity.id), hasModules: state.selectedModules.length > 0 };
}

const initialUrlScheduleState = parseScheduleStateFromUrl();
setSchedulePageState(initialUrlScheduleState);

function syncScheduleUrl(mode = 'replace') {
    if (!window.history?.replaceState) return;
    const url = new URL(window.location.href);
    const params = url.searchParams;
    if (schedulePageState.entity?.id) {
        params.set('type', schedulePageState.entity.type);
        params.set('id', schedulePageState.entity.id);
        params.set('name', schedulePageState.entity.name || schedulePageState.entity.id);
        params.set('date', schedulePageState.date || getISODateStr(currentWeekStart));
    } else {
        ['type', 'id', 'name', 'date'].forEach((key) => params.delete(key));
    }
    if (allAvailableModules.length > 0 && schedulePageState.selectedModules.length === 0) {
        params.set('modules', 'none');
    } else if (schedulePageState.selectedModules.length > 0 && allAvailableModules.length > 0 && schedulePageState.selectedModules.length < allAvailableModules.length) {
        params.set('modules', schedulePageState.selectedModules.join(','));
    } else {
        params.delete('modules');
    }
    if (schedulePageState.viewMode !== 'cards') params.set('view', schedulePageState.viewMode);
    else params.delete('view');
    if (schedulePageState.lessonMode !== 'all') params.set('mode', schedulePageState.lessonMode);
    else params.delete('mode');
    if (schedulePageState.calendarProfileId) params.set('profile', schedulePageState.calendarProfileId);
    else params.delete('profile');
    if (schedulePageState.showChanges) params.set('changes', '1');
    else params.delete('changes');
    params.delete('offline');
    const nextUrl = `${url.pathname}${params.toString() ? `?${params.toString()}` : ''}${url.hash}`;
    const method = mode === 'push' ? 'pushState' : 'replaceState';
    window.history[method]({ schedule: true, state: window.getSchedulePageState() }, '', nextUrl);
}

function commitScheduleState({ urlMode = 'replace', updateUrl = true } = {}) {
    setSchedulePageState({
        entity: currentEntity,
        date: getISODateStr(currentWeekStart),
        selectedModules: Array.from(selectedModules),
        offline: isOfflineMode
    });
    if (updateUrl) syncScheduleUrl(urlMode);
    renderScheduleHome();
    renderScheduleChangesPanel();
}

window.setScheduleViewModeState = function(mode, { updateUrl = true } = {}) {
    const nextMode = normalizeScheduleViewMode(mode);
    const nextLessonMode = nextMode === 'exams'
        ? 'exams_only'
        : (schedulePageState.viewMode === 'exams' ? 'all' : schedulePageState.lessonMode);
    setSchedulePageState({
        viewMode: nextMode,
        lessonMode: nextLessonMode
    });
    window.calendarCurrentViewMode = schedulePageState.lessonMode === 'exams_only' ? 'exams_only' : 'all';
    if (updateUrl) syncScheduleUrl('replace');
    renderScheduleHome();
    renderScheduleChangesPanel();
}

window.setScheduleLessonMode = function(mode, options = {}) {
    const nextMode = normalizeScheduleLessonMode(mode);
    setSchedulePageState({
        lessonMode: nextMode,
        viewMode: nextMode === 'exams_only' && !options.keepViewMode
            ? 'exams'
            : (schedulePageState.viewMode === 'exams' && !options.keepViewMode ? 'cards' : schedulePageState.viewMode)
    });
    window.calendarCurrentViewMode = nextMode === 'exams_only' ? 'exams_only' : 'all';
    filterAndRender();
    savePreferences();
    if (window._renderCalendarSubscriptionImpl) window._renderCalendarSubscriptionImpl();
}

window.setScheduleCalendarProfile = function(profileId, { updateUrl = true } = {}) {
    setSchedulePageState({ calendarProfileId: profileId || null });
    if (updateUrl) syncScheduleUrl('replace');
}

window.toggleScheduleChanges = function(forceOpen = null) {
    const nextValue = typeof forceOpen === 'boolean' ? forceOpen : !schedulePageState.showChanges;
    setSchedulePageState({ showChanges: nextValue });
    syncScheduleUrl('replace');
    renderScheduleHome();
    renderScheduleChangesPanel();
    savePreferences();
}

// Делаем юзера глобальным, чтобы calendar_sync.js тоже его видел
window.scheduleAuthUser = null;

const groupInput = document.getElementById('groupSearch');
const resultsBox = document.getElementById('searchResults');
const searchContainer = document.getElementById('searchContainer');

function getUiLanguage() {
    const source = window.mpbI18n?.getLanguage?.() || document.documentElement.lang || 'ru';
    return String(source).toLowerCase().startsWith('ru') ? 'ru' : 'en';
}

function getUiLocale() {
    return getUiLanguage() === 'ru' ? 'ru-RU' : 'en-US';
}

function t(key, fallback = '', params = {}) {
    return window.mpbI18n?.t?.(key, fallback, params) || fallback || key;
}

function formatUiDate(date, options) {
    return new Intl.DateTimeFormat(getUiLocale(), options).format(date);
}

function formatUiDateCapitalized(date, options) {
    const value = formatUiDate(date, options);
    return value ? `${value[0].toUpperCase()}${value.slice(1)}` : value;
}

function escapeHtml(value) {
    return String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function escapeJsString(value) {
    return String(value ?? '')
        .replace(/\\/g, '\\\\')
        .replace(/'/g, "\\'");
}

function areLessonActionsVisible() {
    return document.getElementById('showLessonActions')?.checked ?? true;
}

function getPreferredDisciplineName(lesson) {
    const useShort = document.getElementById('useShortNames')?.checked ?? true;
    const shortName = String(lesson?.discipline_short || '').trim();
    const fullName = String(lesson?.discipline_full || lesson?.discipline || '').trim();
    return useShort
        ? (shortName || fullName || '-')
        : (fullName || shortName || '-');
}

function getCompactLecturerName(value) {
    const tokens = String(value || '').trim().split(/\s+/).filter(Boolean);
    if (!tokens.length) return '';
    if (tokens.length === 1) return tokens[0];
    const [surname, ...rest] = tokens;
    const initials = rest.map((token) => token[0]).filter(Boolean).slice(0, 2);
    return initials.length ? `${surname} ${initials.map((char) => `${char}.`).join('')}` : surname;
}

function getPreferredLecturerName(value) {
    const fullName = String(value || '').trim();
    if (!fullName) return '';
    return (document.getElementById('showFullLecturerName')?.checked ?? false)
        ? fullName
        : getCompactLecturerName(fullName);
}

window.addEventListener('mpb-auth-ready', (event) => {
    window.scheduleAuthUser = event.detail?.user || null;
    renderScheduleHome();
    // Вызываем функцию из calendar_sync.js, если она уже загрузилась
    if (window.refreshCalendarSubscription) {
        window.refreshCalendarSubscription();
    }
});

document.addEventListener('DOMContentLoaded', async () => {
    await initOfflineHistory();
    await loadInitialPreferences();
    window.mpbI18n?.registerTranslator?.(() => {
        renderOfflineHistory();
        if (!resultsBox.classList.contains('hidden')) {
            if (latestSearchQuery.length < 2) renderSearchHome();
            else renderSearchResults(latestSearchResults, { query: latestSearchQuery, networkState: latestSearchResults.length ? 'ok' : 'empty' });
        }
        if (currentEntity?.id || fullSchedule.length > 0 || allAvailableModules.length > 0) {
            renderModuleFilters();
            filterAndRender();
        }
        if (window._renderCalendarSubscriptionImpl) window._renderCalendarSubscriptionImpl();
    });
});

function formatRelativeDateTime(value) {
    if (!value) return t('schedule.context.parsedUnknown', 'Parsed time unknown');
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return String(value);
    const diffMs = Date.now() - parsed.getTime();
    const absMs = Math.abs(diffMs);
    const minute = 60 * 1000;
    const hour = 60 * minute;
    const day = 24 * hour;
    if (absMs < minute) return t('schedule.time.justNow', 'just now');
    if (absMs < hour) {
        return t('schedule.time.minutesAgo', '{count} min ago', { count: Math.max(1, Math.round(absMs / minute)) });
    }
    if (absMs < day) {
        return t('schedule.time.hoursAgo', '{count} h ago', { count: Math.max(1, Math.round(absMs / hour)) });
    }
    return formatUiDate(parsed, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
}

function isScheduleCacheStale(value) {
    if (!value) return false;
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return false;
    return Date.now() - parsed.getTime() > 24 * 60 * 60 * 1000;
}

function renderOfflineHistory(list = cachedOfflineEntities) {
    const container = document.getElementById('cachedEntitiesList');
    if (!container) return;
    const normalizedList = Array.isArray(list) ? list : [];
    const newestUpdatedAt = normalizedList
        .map((item) => item.updated_at)
        .filter(Boolean)
        .sort()
        .at(-1);
    const currentUpdatedAt = sourceUpdatedAt || newestUpdatedAt || null;
    const currentCacheLabel = currentUpdatedAt
        ? formatRelativeDateTime(currentUpdatedAt)
        : t('schedule.offline.updatedUnknown', 'Update time unknown');
    const refreshDisabled = !currentEntity?.id || isRefreshingScheduleCache;
    const headerHtml = `
        <div class="space-y-2 p-2">
            <div class="rounded-xl bg-slate-50 p-3 text-xs font-semibold text-slate-600 dark:bg-slate-900/70 dark:text-slate-300">
                <div class="text-[10px] font-black uppercase tracking-[0.16em] text-slate-400">${escapeHtml(t('schedule.offline.lastUpdated', 'Cache updated'))}</div>
                <div class="mt-1">${escapeHtml(currentCacheLabel)}</div>
            </div>
            <button type="button" onclick="refreshCurrentScheduleCache()"
                ${refreshDisabled ? 'disabled' : ''}
                class="w-full rounded-xl border px-3 py-2 text-xs font-black transition-colors ${refreshDisabled
                    ? 'cursor-not-allowed border-slate-200 bg-slate-50 text-slate-300 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-600'
                    : 'border-blue-200 bg-blue-50 text-blue-700 hover:bg-blue-100 dark:border-blue-800 dark:bg-blue-950/40 dark:text-blue-200 dark:hover:bg-blue-900/50'}">
                ${escapeHtml(isRefreshingScheduleCache ? t('schedule.offline.refreshing', 'Refreshing...') : t('schedule.offline.refresh', 'Refresh cache'))}
            </button>
        </div>
    `;
    if (normalizedList.length === 0) {
        container.innerHTML = `${headerHtml}<div class="p-6 text-center text-xs text-slate-400 italic">${escapeHtml(t('schedule.history.empty', 'History is empty'))}</div>`;
        return;
    }
    container.innerHTML = headerHtml + normalizedList.map(item => {
        const itemType = escapeJsString(item.type);
        const itemId = escapeJsString(item.id);
        const itemLabel = escapeJsString(item.label || item.name || item.id);
        const labelText = escapeHtml(item.label || item.name || item.id);
        const typeMeta = getSearchResultTypeMeta(item.type);
        const savedText = item.updated_at
            ? escapeHtml(formatRelativeDateTime(item.updated_at))
            : escapeHtml(t('schedule.history.saved', 'Saved offline'));
        return `
            <button onclick="loadSchedule('${itemType}', '${itemId}', '${itemLabel}'); closeOfflinePanel();"
                    class="group w-full text-left px-4 py-3 bg-white hover:bg-blue-50 rounded-xl transition-all flex items-center justify-between border border-transparent hover:border-blue-100 dark:bg-slate-800 dark:hover:bg-slate-700 dark:hover:border-slate-600">
                <div>
                    <div class="flex items-center gap-2 text-xs font-black text-slate-700 group-hover:text-blue-700 dark:text-slate-200 dark:group-hover:text-blue-300">
                        <span>${labelText}</span>
                        <span class="rounded bg-slate-100 px-1.5 py-0.5 text-[9px] uppercase tracking-wide text-slate-500 dark:bg-slate-900 dark:text-slate-400">${escapeHtml(typeMeta.label)}</span>
                    </div>
                    <div class="text-[9px] text-slate-400 uppercase tracking-tighter mt-0.5">${savedText}</div>
                </div>
                <svg class="w-3 h-3 text-slate-300 group-hover:text-blue-400 dark:text-slate-500 dark:group-hover:text-blue-300" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M9 5l7 7-7 7" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg>
            </button>
        `;
    }).join('');
}

function getCurrentEntityKey() {
    return currentEntity?.type && currentEntity?.id
        ? `${currentEntity.type}:${currentEntity.id}`
        : '';
}

function normalizeModulePresetList(value) {
    if (!Array.isArray(value)) return [];
    return value.map((preset) => ({
        id: String(preset.id || `preset-${Date.now().toString(36)}`),
        name: String(preset.name || '').trim() || t('schedule.modules.presetFallback', 'Module preset'),
        entity_type: preset.entity_type || preset.entity?.type || null,
        entity_id: preset.entity_id === undefined || preset.entity_id === null
            ? null
            : String(preset.entity_id),
        entity_name: preset.entity_name || preset.entity?.name || '',
        modules: normalizeScheduleModules(preset.modules),
        created_at: preset.created_at || new Date().toISOString()
    })).filter((preset) => preset.entity_type && preset.entity_id && preset.modules.length > 0).slice(0, MODULE_PRESET_LIMIT);
}

function getCurrentEntityModulePresets() {
    const entityKey = getCurrentEntityKey();
    return modulePresets.filter((preset) => `${preset.entity_type}:${preset.entity_id}` === entityKey);
}

function getCurrentWeekEnd() {
    return window.ScheduleFilters?.getWeekEnd?.(currentWeekStart) || (() => {
        const weekEnd = new Date(currentWeekStart);
        weekEnd.setDate(weekEnd.getDate() + 6);
        return weekEnd;
    })();
}

function isLessonInCurrentPeriod(lesson) {
    return window.ScheduleFilters?.isLessonInPeriod?.(lesson, currentWeekStart, parseDate)
        ?? (() => {
            const lessonDate = parseDate(lesson?.date || '');
            const weekEnd = getCurrentWeekEnd();
            return lessonDate >= currentWeekStart && lessonDate <= weekEnd;
        })();
}

function isLessonAllowedByLessonMode(lesson) {
    return schedulePageState.lessonMode !== 'exams_only' || isExamFocusedKind(lesson?.kindOfWork);
}

function isLessonAllowedByModuleFilter(lesson) {
    return !lesson?.module || selectedModules.has(lesson.module);
}

function isLessonInCurrentDisplayedScope(lesson, { includeModuleFilter = true } = {}) {
    return window.ScheduleFilters?.isLessonVisible?.(lesson, {
        includeModuleFilter,
        isExamLikeKind: isExamFocusedKind,
        lessonMode: schedulePageState.lessonMode,
        parseDate,
        selectedModules,
        weekStart: currentWeekStart,
    }) ?? (
        Boolean(lesson) &&
        isLessonInCurrentPeriod(lesson) &&
        isLessonAllowedByLessonMode(lesson) &&
        (!includeModuleFilter || isLessonAllowedByModuleFilter(lesson))
    );
}

function getCurrentWeekModuleSet() {
    return new Set((Array.isArray(fullSchedule) ? fullSchedule : [])
        .filter((lesson) => isLessonInCurrentPeriod(lesson) && lesson.module)
        .map((lesson) => lesson.module));
}

function getCurrentDisplayedModuleSet() {
    return new Set((Array.isArray(fullSchedule) ? fullSchedule : [])
        .filter((lesson) => isLessonInCurrentDisplayedScope(lesson, { includeModuleFilter: false }) && lesson.module)
        .map((lesson) => lesson.module));
}

function getModuleDisplayStatus(moduleName, displayedModules, weekModules) {
    if (displayedModules.has(moduleName)) {
        return { active: true, label: '' };
    }
    if (weekModules.has(moduleName)) {
        return {
            active: false,
            label: t('schedule.modules.notInCurrentView', 'Not in current view')
        };
    }
    return {
        active: false,
        label: t('schedule.modules.notThisWeek', 'Not this week')
    };
}

function getModuleSearchMatch(moduleName) {
    const query = moduleFilterQuery.trim().toLowerCase();
    return !query || String(moduleName || '').toLowerCase().includes(query);
}

function persistModuleSelection() {
    renderModuleFilters();
    filterAndRender();
    syncCurrentFavoriteModules();
    savePreferences();
    if (window._renderCalendarSubscriptionImpl) window._renderCalendarSubscriptionImpl();
}

function getSelectedModulesForStorage() {
    return Array.from(selectedModules).filter((module) => allAvailableModules.includes(module));
}

function syncCurrentFavoriteModules() {
    if (!currentEntity?.id || !window.ScheduleState?.isFavorite?.(currentEntity)) return;
    window.ScheduleState.updateFavorite(currentEntity, { modules: getSelectedModulesForStorage() });
}

window.setModuleFilterQuery = function(value) {
    moduleFilterQuery = String(value || '');
    renderModuleFilters();
}

window.selectOnlyModule = function(moduleName) {
    selectedModules = moduleName ? new Set([moduleName]) : new Set();
    persistModuleSelection();
}

window.selectAllExceptModule = function(moduleName) {
    selectedModules = new Set(allAvailableModules.filter((module) => module !== moduleName));
    persistModuleSelection();
}

window.saveCurrentModulePreset = function() {
    if (!currentEntity?.id) return;
    const modules = Array.from(selectedModules).filter((module) => allAvailableModules.includes(module));
    if (!modules.length) {
        window.mpbPopup?.(t('schedule.modules.emptyPresetError', 'Select at least one module first.'), { type: 'warning' });
        return;
    }
    const defaultName = t('schedule.modules.presetDefaultName', '{entity}: {count} modules', {
        entity: currentEntity.name || currentEntity.id,
        count: modules.length
    });
    const name = window.prompt(t('schedule.modules.presetNamePrompt', 'Preset name'), defaultName);
    if (!name) return;
    const entityKey = getCurrentEntityKey();
    const nextPreset = {
        id: `modules-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`,
        name: name.trim() || defaultName,
        entity_type: currentEntity.type,
        entity_id: String(currentEntity.id),
        entity_name: currentEntity.name || '',
        modules,
        created_at: new Date().toISOString()
    };
    const others = modulePresets.filter((preset) => `${preset.entity_type}:${preset.entity_id}` !== entityKey);
    const sameEntity = getCurrentEntityModulePresets().filter((preset) => preset.name !== nextPreset.name);
    modulePresets = normalizeModulePresetList([nextPreset, ...sameEntity, ...others]);
    savePreferences();
    renderModuleFilters();
}

window.applyModulePreset = function(presetId) {
    const preset = modulePresets.find((item) => item.id === presetId);
    if (!preset) return;
    const availableSet = new Set(allAvailableModules);
    selectedModules = new Set(preset.modules.filter((module) => availableSet.has(module)));
    persistModuleSelection();
}

window.deleteModulePreset = function(presetId) {
    modulePresets = modulePresets.filter((item) => item.id !== presetId);
    savePreferences();
    renderModuleFilters();
}

function getSnapshotEntityKey(entity = currentEntity) {
    return entity?.type && entity?.id ? `${entity.type}:${entity.id}` : '';
}

function loadScheduleSnapshots() {
    try {
        const payload = JSON.parse(localStorage.getItem(SCHEDULE_SNAPSHOTS_KEY) || '{}');
        return payload && typeof payload === 'object' ? payload : {};
    } catch {
        return {};
    }
}

function persistScheduleSnapshot(entityKey, schedule, updatedAt) {
    if (!entityKey) return;
    const snapshots = loadScheduleSnapshots();
    snapshots[entityKey] = {
        captured_at: new Date().toISOString(),
        source_updated_at: updatedAt || null,
        lessons: (Array.isArray(schedule) ? schedule : []).map(normalizeLessonForSnapshot)
    };
    localStorage.setItem(SCHEDULE_SNAPSHOTS_KEY, JSON.stringify(snapshots));
}

function normalizeLessonForSnapshot(lesson) {
    return {
        identity: getLessonIdentity(lesson),
        date: String(lesson.date || ''),
        beginLesson: String(lesson.beginLesson || ''),
        endLesson: String(lesson.endLesson || ''),
        discipline: String(lesson.discipline_full || lesson.discipline || lesson.discipline_short || ''),
        kindOfWork: String(lesson.kindOfWork || ''),
        module: String(lesson.module || ''),
        auditorium: String(lesson.auditorium || ''),
        lecturer_title: String(lesson.lecturer_title || '')
    };
}

function normalizeSnapshotText(value) {
    return String(value || '').toLowerCase().replace(/\s+/g, ' ').trim();
}

function getLessonIdentity(lesson) {
    return [
        normalizeSnapshotText(lesson.discipline_full || lesson.discipline || lesson.discipline_short),
        normalizeSnapshotText(lesson.kindOfWork),
        normalizeSnapshotText(lesson.module)
    ].join('|');
}

function buildLessonChangeLabel(lesson) {
    return [
        lesson.discipline || '-',
        lesson.module,
        lesson.date,
        lesson.beginLesson
    ].filter(Boolean).join(' · ');
}

function buildScheduleChangeSummary(previousSnapshot, currentSchedule, updatedAt) {
    const currentLessons = (Array.isArray(currentSchedule) ? currentSchedule : []).map(normalizeLessonForSnapshot);
    const baseSummary = {
        hasPrevious: Boolean(previousSnapshot?.lessons?.length),
        previousCapturedAt: previousSnapshot?.captured_at || null,
        previousSourceUpdatedAt: previousSnapshot?.source_updated_at || null,
        sourceUpdatedAt: updatedAt || null,
        newLessons: [],
        removedLessons: [],
        movedLessons: [],
        roomChanges: [],
        teacherChanges: []
    };
    if (!baseSummary.hasPrevious) return baseSummary;

    const previousByIdentity = new Map();
    previousSnapshot.lessons.forEach((lesson) => {
        if (!previousByIdentity.has(lesson.identity)) previousByIdentity.set(lesson.identity, []);
        previousByIdentity.get(lesson.identity).push(lesson);
    });
    const currentByIdentity = new Map();
    currentLessons.forEach((lesson) => {
        if (!currentByIdentity.has(lesson.identity)) currentByIdentity.set(lesson.identity, []);
        currentByIdentity.get(lesson.identity).push(lesson);
    });

    currentByIdentity.forEach((currentItems, identity) => {
        const previousItems = previousByIdentity.get(identity) || [];
        if (!previousItems.length) {
            baseSummary.newLessons.push(...currentItems.map((lesson) => ({ lesson, label: buildLessonChangeLabel(lesson) })));
            return;
        }
        currentItems.forEach((lesson, index) => {
            const previous = previousItems[Math.min(index, previousItems.length - 1)];
            if (!previous) return;
            if (lesson.date !== previous.date || lesson.beginLesson !== previous.beginLesson || lesson.endLesson !== previous.endLesson) {
                baseSummary.movedLessons.push({
                    lesson,
                    previous,
                    label: buildLessonChangeLabel(lesson),
                    from: `${previous.date} ${previous.beginLesson}-${previous.endLesson}`.trim(),
                    to: `${lesson.date} ${lesson.beginLesson}-${lesson.endLesson}`.trim()
                });
            }
            if (lesson.auditorium !== previous.auditorium) {
                baseSummary.roomChanges.push({
                    lesson,
                    previous,
                    label: buildLessonChangeLabel(lesson),
                    from: previous.auditorium || '-',
                    to: lesson.auditorium || '-'
                });
            }
            if (lesson.lecturer_title !== previous.lecturer_title) {
                baseSummary.teacherChanges.push({
                    lesson,
                    previous,
                    label: buildLessonChangeLabel(lesson),
                    from: previous.lecturer_title || '-',
                    to: lesson.lecturer_title || '-'
                });
            }
        });
    });
    previousByIdentity.forEach((previousItems, identity) => {
        if (!currentByIdentity.has(identity)) {
            baseSummary.removedLessons.push(...previousItems.map((lesson) => ({ lesson, label: buildLessonChangeLabel(lesson) })));
        }
    });
    return baseSummary;
}

function getLessonDateTime(lesson) {
    const datePart = getISODateStr(parseDate(lesson.date || ''));
    const timePart = String(lesson.beginLesson || '00:00').padStart(5, '0');
    const parsed = new Date(`${datePart}T${timePart}:00`);
    return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function isLessonVisibleInScheduleState(lesson) {
    if (lesson.module && !selectedModules.has(lesson.module)) return false;
    if (schedulePageState.lessonMode === 'exams_only' && !isExamFocusedKind(lesson.kindOfWork)) return false;
    return true;
}

function getScheduleHomeLessons() {
    return (Array.isArray(fullSchedule) ? fullSchedule : [])
        .filter(isLessonVisibleInScheduleState)
        .sort((a, b) => {
            const left = getLessonDateTime(a)?.getTime() || 0;
            const right = getLessonDateTime(b)?.getTime() || 0;
            return left - right;
        });
}

function getNextScheduleLesson(lessons) {
    const now = new Date();
    return lessons.find((lesson) => {
        const lessonDate = getLessonDateTime(lesson);
        return lessonDate && lessonDate >= now;
    }) || null;
}

function renderScheduleHomeLessonRow(lesson) {
    const lessonDate = getLessonDateTime(lesson);
    const timeLabel = `${lesson.beginLesson || ''}${lesson.endLesson ? ` - ${lesson.endLesson}` : ''}`;
    const dateLabel = lessonDate
        ? formatUiDate(lessonDate, { day: 'numeric', month: 'short', weekday: 'short' })
        : '';
    const discipline = lesson.discipline_short || lesson.discipline_full || lesson.discipline || '-';
    const meta = [lesson.auditorium, lesson.lecturer_title].filter(Boolean).join(' · ');
    return `
        <div class="flex min-w-0 items-start gap-3 border-t border-slate-200 py-3 first:border-t-0 first:pt-0 last:pb-0 dark:border-slate-700">
            <div class="w-20 shrink-0">
                <div class="text-sm font-black text-slate-900 dark:text-slate-100">${escapeHtml(lesson.beginLesson || '-')}</div>
                <div class="mt-0.5 text-[10px] font-bold uppercase tracking-wide text-slate-400">${escapeHtml(dateLabel)}</div>
            </div>
            <div class="min-w-0 flex-1">
                <div class="truncate text-sm font-black text-slate-800 dark:text-slate-100">${escapeHtml(discipline)}</div>
                <div class="mt-1 truncate text-xs font-medium text-slate-500 dark:text-slate-400">${escapeHtml(meta || timeLabel)}</div>
                ${lesson.module ? `<div class="mt-1 w-fit max-w-full truncate rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-black text-slate-500 dark:bg-slate-800 dark:text-slate-300">${escapeHtml(lesson.module)}</div>` : ''}
            </div>
        </div>
    `;
}

function renderScheduleHome() {
    const container = document.getElementById('scheduleHomePanel');
    if (!container) return;
    const hasEntity = Boolean(currentEntity?.id);
    const hasUser = Boolean(window.scheduleAuthUser);
    if (!hasEntity && !hasUser) {
        container.classList.add('hidden');
        container.innerHTML = '';
        return;
    }

    const lessons = getScheduleHomeLessons();
    const todayStr = getISODateStr(new Date());
    const todayLessons = lessons.filter((lesson) => getISODateStr(parseDate(lesson.date || '')) === todayStr);
    const nextLesson = getNextScheduleLesson(lessons);
    const nextLessonDate = nextLesson ? getLessonDateTime(nextLesson) : null;
    const nextDiscipline = nextLesson
        ? (nextLesson.discipline_short || nextLesson.discipline_full || nextLesson.discipline || '-')
        : t('schedule.home.noNext', 'No upcoming classes');
    const nextMeta = nextLesson
        ? [
            nextLessonDate ? formatUiDate(nextLessonDate, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : '',
            nextLesson.auditorium
        ].filter(Boolean).join(' · ')
        : t('schedule.home.pickSchedule', 'Pick a schedule to build your personal view');
    const activeLabel = hasEntity
        ? currentEntity.name
        : t('schedule.home.noActive', 'No active schedule');
    const activeType = hasEntity
        ? getSearchResultTypeMeta(currentEntity.type).label
        : t('schedule.home.activeTypeEmpty', 'Search');
    const todayPreview = todayLessons.length
        ? todayLessons.slice(0, 4).map(renderScheduleHomeLessonRow).join('')
        : `<div class="py-4 text-sm font-semibold text-slate-400">${escapeHtml(t('schedule.home.noToday', 'No classes today'))}</div>`;
    const lessonModeButtonKey = schedulePageState.lessonMode === 'exams_only'
        ? 'schedule.home.allClasses'
        : 'schedule.home.examsOnly';
    const lessonModeButtonFallback = schedulePageState.lessonMode === 'exams_only'
        ? 'All classes'
        : 'Exams only';
    const lessonModeTarget = schedulePageState.lessonMode === 'exams_only' ? 'all' : 'exams_only';
    const changeCount = getScheduleChangeCount();
    const changesButtonKey = schedulePageState.showChanges ? 'schedule.changes.hide' : 'schedule.changes.show';
    const changesButtonFallback = schedulePageState.showChanges ? 'Hide changes' : 'Show changes';
    const isFavorite = hasEntity && window.ScheduleState?.isFavorite?.(currentEntity);

    container.classList.remove('hidden');
    container.innerHTML = `
        <div class="rounded-3xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-700 dark:bg-slate-800 md:p-5">
            <div class="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
                <div class="min-w-0">
                    <div class="text-xs font-black uppercase tracking-[0.2em] text-blue-500 dark:text-blue-300">${escapeHtml(t('schedule.home.eyebrow', 'My schedule'))}</div>
                    <h2 class="mt-1 text-xl font-black text-slate-900 dark:text-slate-100">${escapeHtml(activeLabel)}</h2>
                    <p class="mt-1 text-sm font-medium text-slate-500 dark:text-slate-400">${escapeHtml(activeType)}</p>
                </div>
                <div class="grid gap-2 sm:flex sm:flex-wrap sm:justify-end">
                    ${hasEntity ? `<button type="button" onclick="setTodayWeek()" class="rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-black text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800">${escapeHtml(t('schedule.home.thisWeek', 'This week'))}</button>` : ''}
                    ${hasEntity ? `<button type="button" onclick="toggleCurrentScheduleFavorite()" class="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs font-black text-amber-700 hover:bg-amber-100 dark:border-amber-900/60 dark:bg-amber-950/30 dark:text-amber-200 dark:hover:bg-amber-950/50">${isFavorite ? '★' : '☆'} ${escapeHtml(t(isFavorite ? 'schedule.search.favorited' : 'schedule.search.favorite', isFavorite ? 'Favorite' : 'Favorite'))}</button>` : ''}
                    ${hasEntity ? `<button type="button" onclick="setScheduleLessonMode('${lessonModeTarget}')" class="rounded-xl border border-blue-200 bg-blue-50 px-3 py-2 text-xs font-black text-blue-700 hover:bg-blue-100 dark:border-blue-800 dark:bg-blue-950/40 dark:text-blue-200 dark:hover:bg-blue-900/50">${escapeHtml(t(lessonModeButtonKey, lessonModeButtonFallback))}</button>` : ''}
                    ${hasEntity ? `<button type="button" onclick="toggleScheduleChanges()" class="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs font-black text-amber-700 hover:bg-amber-100 dark:border-amber-900/60 dark:bg-amber-950/30 dark:text-amber-200 dark:hover:bg-amber-950/50">${escapeHtml(t(changesButtonKey, changesButtonFallback))}${changeCount ? ` (${escapeHtml(String(changeCount))})` : ''}</button>` : ''}
                    ${hasEntity ? `<button type="button" onclick="copyScheduleShareLink(event)" class="rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-black text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800">${escapeHtml(t('schedule.home.copyLink', 'Copy link'))}</button>` : ''}
                    <button type="button" onclick="openCalendarSyncFromScheduleHome()" class="rounded-xl bg-slate-900 px-3 py-2 text-xs font-black text-white hover:bg-slate-800 dark:bg-blue-600 dark:hover:bg-blue-500">${escapeHtml(t('schedule.home.calendar', 'Calendar'))}</button>
                    <button type="button" onclick="focusScheduleSearch()" class="rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-black text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800">${escapeHtml(t('schedule.home.changeSchedule', 'Change schedule'))}</button>
                </div>
            </div>
            ${isOfflineMode ? `
                <div class="mt-4 rounded-2xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs font-bold text-amber-700 dark:border-amber-900/60 dark:bg-amber-950/30 dark:text-amber-300">
                    ${escapeHtml(t('schedule.offline.warning', 'University service is unavailable. Loaded a cached copy.'))}
                </div>
            ` : ''}
            <div class="mt-4 grid gap-3 lg:grid-cols-[minmax(0,0.85fr)_minmax(0,1.15fr)]">
                <section class="rounded-2xl border border-slate-200 bg-slate-50 p-4 dark:border-slate-700 dark:bg-slate-900/60">
                    <div class="text-[10px] font-black uppercase tracking-[0.18em] text-slate-400">${escapeHtml(t('schedule.home.nextTitle', 'Next class'))}</div>
                    <div class="mt-2 line-clamp-2 text-lg font-black text-slate-900 dark:text-slate-100">${escapeHtml(nextDiscipline)}</div>
                    <div class="mt-2 text-sm font-semibold text-slate-500 dark:text-slate-400">${escapeHtml(nextMeta)}</div>
                </section>
                <section class="rounded-2xl border border-slate-200 bg-slate-50 p-4 dark:border-slate-700 dark:bg-slate-900/60">
                    <div class="flex items-center justify-between gap-3">
                        <div class="text-[10px] font-black uppercase tracking-[0.18em] text-slate-400">${escapeHtml(t('schedule.home.todayTitle', 'Today'))}</div>
                        <span class="rounded-full bg-white px-2 py-0.5 text-[10px] font-black text-slate-500 ring-1 ring-slate-200 dark:bg-slate-900 dark:text-slate-300 dark:ring-slate-700">${escapeHtml(String(todayLessons.length))}</span>
                    </div>
                    <div class="mt-3">${todayPreview}</div>
                </section>
            </div>
        </div>
    `;
}

function syncScheduleToolbarActions({ hasEntity, isFavorite, changeCount }) {
    const favoriteBtn = document.getElementById('scheduleFavoriteBtn');
    const shareBtn = document.getElementById('scheduleShareBtn');
    const changesBtn = document.getElementById('scheduleChangesToggleBtn');
    const todayBtn = document.getElementById('scheduleTodayBtn');
    const favoriteIcon = document.getElementById('scheduleFavoriteIcon');
    const favoriteLabel = document.getElementById('scheduleFavoriteBtnLabel');
    const shareLabel = document.getElementById('scheduleShareBtnLabel');
    const changesLabel = document.getElementById('scheduleChangesToggleBtnLabel');
    const changesBadge = document.getElementById('scheduleChangesCountBadge');

    const favoriteText = t(
        isFavorite ? 'schedule.search.favorited' : 'schedule.search.favorite',
        isFavorite ? 'Saved' : 'Favorite'
    );
    const shareText = t('schedule.home.copyLink', 'Copy link');
    const changesText = `${t(
        schedulePageState.showChanges ? 'schedule.changes.hide' : 'schedule.changes.show',
        schedulePageState.showChanges ? 'Hide changes' : 'Show changes'
    )}${changeCount ? ` (${changeCount})` : ''}`;

    if (favoriteBtn) {
        favoriteBtn.disabled = !hasEntity;
        favoriteBtn.classList.toggle('is-favorite', hasEntity && isFavorite);
        favoriteBtn.classList.toggle('opacity-50', !hasEntity);
        favoriteBtn.setAttribute('title', favoriteText);
        favoriteBtn.setAttribute('aria-label', favoriteText);
        if (favoriteLabel) favoriteLabel.textContent = favoriteText;
        if (favoriteIcon) {
            favoriteIcon.classList.toggle('fill-current', hasEntity && isFavorite);
            favoriteIcon.classList.toggle('fill-none', !(hasEntity && isFavorite));
        }
    }

    if (shareBtn) {
        shareBtn.disabled = !hasEntity;
        shareBtn.classList.toggle('opacity-50', !hasEntity);
        shareBtn.setAttribute('title', shareText);
        shareBtn.setAttribute('aria-label', shareText);
        if (shareLabel) shareLabel.textContent = shareText;
    }

    if (changesBtn) {
        changesBtn.disabled = !hasEntity;
        changesBtn.classList.toggle('is-active', hasEntity && (schedulePageState.showChanges || changeCount > 0));
        changesBtn.classList.toggle('opacity-50', !hasEntity);
        changesBtn.setAttribute('title', changesText);
        changesBtn.setAttribute('aria-label', changesText);
        if (changesLabel) changesLabel.textContent = changesText;
        if (changesBadge) {
            changesBadge.textContent = changeCount > 99 ? '99+' : String(changeCount || '');
            changesBadge.classList.toggle('hidden', !changeCount);
        }
    }

    if (todayBtn) {
        todayBtn.disabled = !hasEntity;
        todayBtn.classList.toggle('opacity-50', !hasEntity);
    }
}

renderScheduleHome = function renderScheduleToolbarOnly() {
    const container = document.getElementById('scheduleHomePanel');
    const hasEntity = Boolean(currentEntity?.id);
    const changeCount = getScheduleChangeCount();
    const isFavorite = hasEntity && window.ScheduleState?.isFavorite?.(currentEntity);

    syncScheduleToolbarActions({ hasEntity, isFavorite, changeCount });
    if (!container) return;
    container.classList.add('hidden');
    container.innerHTML = '';
}

window.focusScheduleSearch = function() {
    const input = document.getElementById('groupSearch');
    input?.focus();
    input?.select();
}

window.copyScheduleShareLink = function(event) {
    commitScheduleState({ urlMode: 'replace' });
    copyToClipboard(window.location.href, event);
}

window.toggleCurrentScheduleFavorite = function() {
    if (!currentEntity?.id) return;
    window.ScheduleState?.toggleFavorite?.({
        ...currentEntity,
        modules: getSelectedModulesForStorage()
    });
    renderScheduleHome();
    if (!resultsBox.classList.contains('hidden')) {
        renderSearchResults(latestSearchResults, { query: latestSearchQuery, networkState: latestSearchResults.length ? 'ok' : 'empty' });
    }
}

window.openCalendarSyncFromScheduleHome = function() {
    if (window.openCalendarSyncPanel) {
        window.openCalendarSyncPanel();
        return;
    }
    const panel = document.getElementById('calendarSubscriptionSection');
    if (!panel) return;
    panel.scrollIntoView({ behavior: 'smooth', block: 'start' });
    const toggle = panel.querySelector('button[aria-controls="calendarSubscriptionBody"]');
    if (toggle?.getAttribute('aria-expanded') === 'false') {
        setTimeout(() => toggle.click(), 150);
    }
}

function formatScheduleSnapshotDate(value) {
    if (!value) return t('schedule.changes.never', 'No previous snapshot');
    const parsed = new Date(value);
    return Number.isNaN(parsed.getTime())
        ? value
        : formatUiDate(parsed, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
}

function isScheduleChangeVisible(item) {
    return isLessonInCurrentDisplayedScope(item?.lesson, { includeModuleFilter: true })
        || isLessonInCurrentDisplayedScope(item?.previous, { includeModuleFilter: true });
}

function getFilteredScheduleChangeSummary(summary = scheduleChangeSummary) {
    if (!summary) return null;
    return {
        ...summary,
        newLessons: (summary.newLessons || []).filter(isScheduleChangeVisible),
        removedLessons: (summary.removedLessons || []).filter(isScheduleChangeVisible),
        movedLessons: (summary.movedLessons || []).filter(isScheduleChangeVisible),
        roomChanges: (summary.roomChanges || []).filter(isScheduleChangeVisible),
        teacherChanges: (summary.teacherChanges || []).filter(isScheduleChangeVisible)
    };
}

function getScheduleChangeCount(summary = getFilteredScheduleChangeSummary()) {
    if (!summary) return 0;
    return [
        summary.newLessons,
        summary.removedLessons,
        summary.movedLessons,
        summary.roomChanges,
        summary.teacherChanges
    ].reduce((total, items) => total + (Array.isArray(items) ? items.length : 0), 0);
}

function renderScheduleChangeList(titleKey, fallback, items, toneClass, formatter = null) {
    const normalized = Array.isArray(items) ? items : [];
    return `
        <section class="rounded-2xl border ${toneClass} p-3">
            <div class="flex items-center justify-between gap-3">
                <div class="text-[10px] font-black uppercase tracking-[0.16em] text-slate-500 dark:text-slate-300">${escapeHtml(t(titleKey, fallback))}</div>
                <span class="rounded-full bg-white px-2 py-0.5 text-[10px] font-black text-slate-500 ring-1 ring-slate-200 dark:bg-slate-900 dark:text-slate-300 dark:ring-slate-700">${normalized.length}</span>
            </div>
            <div class="mt-3 space-y-2">
                ${normalized.length
                    ? normalized.slice(0, 6).map((item) => `
                        <div class="rounded-xl bg-white px-3 py-2 text-xs font-semibold text-slate-700 ring-1 ring-slate-200 dark:bg-slate-900/70 dark:text-slate-200 dark:ring-slate-700">
                            <div class="line-clamp-2">${escapeHtml(item.label)}</div>
                            ${formatter ? `<div class="mt-1 text-[11px] font-medium text-slate-500 dark:text-slate-400">${escapeHtml(formatter(item))}</div>` : ''}
                        </div>
                    `).join('')
                    : `<div class="text-xs font-medium text-slate-400">${escapeHtml(t('schedule.changes.noneInGroup', 'No items'))}</div>`}
            </div>
        </section>
    `;
}

function renderScheduleChangesPanel() {
    const container = document.getElementById('scheduleChangesPanel');
    if (!container) return;
    if (!currentEntity?.id || !schedulePageState.showChanges) {
        container.classList.add('hidden');
        container.innerHTML = '';
        return;
    }
    const rawSummary = scheduleChangeSummary;
    const summary = getFilteredScheduleChangeSummary(rawSummary);
    const total = getScheduleChangeCount(summary);
    const parsedLabel = sourceUpdatedAt
        ? formatScheduleSnapshotDate(sourceUpdatedAt)
        : t('schedule.context.parsedUnknown', 'Parsed time unknown');
    const previousLabel = formatScheduleSnapshotDate(rawSummary?.previousSourceUpdatedAt || rawSummary?.previousCapturedAt);
    container.classList.remove('hidden');
    container.innerHTML = `
        <div class="rounded-3xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-700 dark:bg-slate-800 md:p-5">
            <div class="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                <div class="min-w-0">
                    <div class="text-xs font-black uppercase tracking-[0.2em] text-blue-500 dark:text-blue-300">${escapeHtml(t('schedule.changes.eyebrow', 'Changes'))}</div>
                    <h2 class="mt-1 text-xl font-black text-slate-900 dark:text-slate-100">${escapeHtml(t('schedule.changes.title', 'Schedule changes'))}</h2>
                    <p class="mt-1 text-sm font-medium text-slate-500 dark:text-slate-400">
                        ${escapeHtml(t('schedule.changes.subtitle', 'Compared with the previous local snapshot and current filters.'))}
                    </p>
                </div>
                <div class="grid gap-2 sm:flex sm:flex-wrap sm:justify-end">
                    <span class="rounded-xl bg-slate-100 px-3 py-2 text-xs font-black text-slate-600 dark:bg-slate-900 dark:text-slate-300">${escapeHtml(t('schedule.changes.total', 'Changes: {count}', { count: total }))}</span>
                    <button type="button" onclick="toggleScheduleChanges(false)" class="rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-black text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800">${escapeHtml(t('schedule.changes.hide', 'Hide'))}</button>
                </div>
            </div>
            <div class="mt-4 grid gap-2 sm:grid-cols-2">
                <div class="rounded-2xl bg-slate-50 p-3 text-xs font-semibold text-slate-600 dark:bg-slate-900/60 dark:text-slate-300">
                    <div class="text-[10px] font-black uppercase tracking-[0.16em] text-slate-400">${escapeHtml(t('schedule.changes.sourceUpdated', 'Parsed'))}</div>
                    <div class="mt-1">${escapeHtml(parsedLabel)}</div>
                </div>
                <div class="rounded-2xl bg-slate-50 p-3 text-xs font-semibold text-slate-600 dark:bg-slate-900/60 dark:text-slate-300">
                    <div class="text-[10px] font-black uppercase tracking-[0.16em] text-slate-400">${escapeHtml(t('schedule.changes.previous', 'Previous snapshot'))}</div>
                    <div class="mt-1">${escapeHtml(previousLabel)}</div>
                </div>
            </div>
            ${summary?.hasPrevious ? `
                ${total === 0 ? `
                    <div class="mt-4 rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm font-bold text-emerald-700 dark:border-emerald-900/60 dark:bg-emerald-950/30 dark:text-emerald-300">
                        ${escapeHtml(t('schedule.changes.none', 'No schedule changes since the previous snapshot.'))}
                    </div>
                ` : `
                    <div class="mt-4 grid gap-3 xl:grid-cols-5">
                        ${renderScheduleChangeList('schedule.changes.new', 'New', summary.newLessons, 'border-emerald-200 bg-emerald-50/70 dark:border-emerald-900/60 dark:bg-emerald-950/20')}
                        ${renderScheduleChangeList('schedule.changes.removed', 'Cancelled', summary.removedLessons, 'border-rose-200 bg-rose-50/70 dark:border-rose-900/60 dark:bg-rose-950/20')}
                        ${renderScheduleChangeList('schedule.changes.moved', 'Moved', summary.movedLessons, 'border-amber-200 bg-amber-50/70 dark:border-amber-900/60 dark:bg-amber-950/20', (item) => `${item.from} -> ${item.to}`)}
                        ${renderScheduleChangeList('schedule.changes.rooms', 'Room', summary.roomChanges, 'border-blue-200 bg-blue-50/70 dark:border-blue-900/60 dark:bg-blue-950/20', (item) => `${item.from} -> ${item.to}`)}
                        ${renderScheduleChangeList('schedule.changes.teachers', 'Lecturer', summary.teacherChanges, 'border-violet-200 bg-violet-50/70 dark:border-violet-900/60 dark:bg-violet-950/20', (item) => `${item.from} -> ${item.to}`)}
                    </div>
                `}
            ` : `
                <div class="mt-4 rounded-2xl border border-blue-200 bg-blue-50 px-4 py-3 text-sm font-bold text-blue-700 dark:border-blue-900/60 dark:bg-blue-950/30 dark:text-blue-300">
                    ${escapeHtml(t('schedule.changes.firstSnapshot', 'Snapshot saved. Future loads of this schedule will show changes here.'))}
                </div>
            `}
        </div>
    `;
}

async function initOfflineHistory() {
    try {
        cachedOfflineEntities = await (window.ScheduleApi?.getCachedSchedules?.() || fetch(`${API_BASE}/schedule/cached_list`).then((res) => res.ok ? res.json() : []));
        renderOfflineHistory();
    } catch (e) {
        console.warn("Не удалось загрузить список кэша:", e);
        renderOfflineHistory([]);
    }
}

async function loadInitialPreferences() {
    const token = localStorage.getItem('jwt_token');
    let remotePrefs = null;
    let localPrefs = null;
    const urlState = parseScheduleStateFromUrl();
    try {
        const saved = localStorage.getItem(STORAGE_KEY);
        if (saved) localPrefs = JSON.parse(saved);
    } catch (e) {}

    if (token) {
        try {
            const res = await fetch(`${API_BASE}/auth/me`, {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            if (res.ok) {
                const user = await res.json();
                window.scheduleAuthUser = user;
                remotePrefs = user.preferences;
            }
        } catch (e) {
            console.error("Ошибка загрузки настроек с сервера", e);
        }
    }

    let prefsToApply = null;
    if (remotePrefs && Object.keys(remotePrefs).length > 0) {
        prefsToApply = remotePrefs;
        localStorage.setItem(STORAGE_KEY, JSON.stringify(prefsToApply));
    } else if (localPrefs) {
        prefsToApply = localPrefs;
        if (token) pushPreferencesToAPI(prefsToApply, token);
    }

    if (prefsToApply) {
        modulePresets = normalizeModulePresetList(prefsToApply.modulePresets || prefsToApply.scheduleState?.modulePresets || []);
        if (prefsToApply.useShortNames !== undefined) {
            const el = document.getElementById('useShortNames');
            if (el) el.checked = prefsToApply.useShortNames;
        }
        if (prefsToApply.showFullLecturerName !== undefined) {
            const el = document.getElementById('showFullLecturerName');
            if (el) el.checked = prefsToApply.showFullLecturerName;
        }
        if (prefsToApply.showLessonActions !== undefined) {
            const el = document.getElementById('showLessonActions');
            if (el) el.checked = prefsToApply.showLessonActions;
        }
    }

    const prefState = buildScheduleStateFromPreferences(prefsToApply || {});
    const urlMatchesPrefEntity = getScheduleEntityKey(urlState.entity) === getScheduleEntityKey(prefState.entity);
    const initialModules = urlState.hasEmptyModules
        ? []
        : (urlState.hasModules ? urlState.selectedModules : (urlMatchesPrefEntity ? prefState.selectedModules : []));
    const initialState = urlState.hasEntity
        ? { ...prefState, ...urlState, selectedModules: initialModules }
        : (prefState.hasEntity ? prefState : { ...schedulePageState, ...urlState });
    setSchedulePageState(initialState);
    window.calendarCurrentViewMode = schedulePageState.lessonMode === 'exams_only' ? 'exams_only' : 'all';
    if (initialState.selectedModules.length > 0) {
        selectedModules = new Set(initialState.selectedModules);
    } else {
        selectedModules.clear();
    }
    renderScheduleHome();
    if (initialState.entity?.id) {
        await loadSchedule(
            initialState.entity.type,
            initialState.entity.id,
            initialState.entity.name,
            initialState.date,
            { urlMode: 'replace', preserveModules: initialState.selectedModules.length > 0 || urlState.hasEmptyModules, keepEmptyModules: urlState.hasEmptyModules }
        );
    } else {
        syncScheduleUrl('replace');
    }
}

async function savePreferences() {
    commitScheduleState({ updateUrl: false });
    const prefs = {
        entity: currentEntity,
        modules: Array.from(selectedModules),
        date: schedulePageState.date,
        viewMode: schedulePageState.viewMode,
        lessonMode: schedulePageState.lessonMode,
        calendarProfileId: schedulePageState.calendarProfileId,
        showChanges: schedulePageState.showChanges,
        modulePresets,
        scheduleState: window.getSchedulePageState(),
        useShortNames: document.getElementById('useShortNames')?.checked ?? true,
        showFullLecturerName: document.getElementById('showFullLecturerName')?.checked ?? false,
        showLessonActions: document.getElementById('showLessonActions')?.checked ?? true
    };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs));
    const token = localStorage.getItem('jwt_token');
    if (token) {
        pushPreferencesToAPI(prefs, token);
    }
}

async function pushPreferencesToAPI(prefs, token) {
    try {
        await fetch(`${API_BASE}/auth/preferences`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify({ preferences: prefs })
        });
    } catch (e) {
        console.error("Ошибка сохранения настроек в облако", e);
    }
}

function parseDate(dateStr) {
    const [y, m, d] = dateStr.replace(/\./g, '-').split('-');
    return new Date(parseInt(y), parseInt(m) - 1, parseInt(d));
}

function getISODateStr(d) {
    const year = d.getFullYear();
    const month = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
}

function parseTimeToMinutes(timeStr) {
    const match = String(timeStr || '').trim().match(/^(\d{1,2}):(\d{2})$/);
    if (!match) return null;
    const hours = Number(match[1]);
    const minutes = Number(match[2]);
    if (!Number.isFinite(hours) || !Number.isFinite(minutes)) return null;
    return hours * 60 + minutes;
}

function getFixedTimeSlotRanges() {
    if (!fixedTimeSlotRangesCache) {
        fixedTimeSlotRangesCache = FIXED_TIMES.map((slot) => ({
            ...slot,
            startMinutes: parseTimeToMinutes(slot.start),
            endMinutes: parseTimeToMinutes(slot.end)
        }));
    }
    return fixedTimeSlotRangesCache;
}

function findFixedSlotIndexForMinute(minute, mode = 'start') {
    const slots = getFixedTimeSlotRanges();
    if (!slots.length || !Number.isFinite(minute)) return -1;
    if (minute <= slots[0].startMinutes) return 0;

    for (let index = 0; index < slots.length; index += 1) {
        const slot = slots[index];
        if (minute >= slot.startMinutes && minute < slot.endMinutes) return index;
        if (mode === 'end' && minute === slot.endMinutes) return index;

        const nextSlot = slots[index + 1];
        if (!nextSlot) continue;
        if (mode === 'start' && minute >= slot.endMinutes && minute < nextSlot.startMinutes) {
            return index + 1;
        }
        if (mode === 'end' && minute > slot.endMinutes && minute <= nextSlot.startMinutes) {
            return index;
        }
    }

    return slots.length - 1;
}

function getFixedSlotOffsetPx(minute, slotIndex) {
    const slot = getFixedTimeSlotRanges()[slotIndex];
    if (!slot) return 0;
    if (minute <= slot.startMinutes) return 0;
    if (minute >= slot.endMinutes) return TABLE_SLOT_ROW_HEIGHT_PX;
    return ((minute - slot.startMinutes) / Math.max(1, slot.endMinutes - slot.startMinutes)) * TABLE_SLOT_ROW_HEIGHT_PX;
}

function getLessonTimelinePlacement(lesson) {
    const startMinutes = parseTimeToMinutes(lesson?.beginLesson);
    if (!Number.isFinite(startMinutes)) return null;

    let endMinutes = parseTimeToMinutes(lesson?.endLesson);
    if (!Number.isFinite(endMinutes) || endMinutes <= startMinutes) {
        const exactSlot = getFixedTimeSlotRanges().find((slot) => slot.start === lesson?.beginLesson);
        endMinutes = exactSlot?.endMinutes || (startMinutes + 90);
    }

    const startSlotIndex = findFixedSlotIndexForMinute(startMinutes, 'start');
    const endSlotIndex = findFixedSlotIndexForMinute(endMinutes, 'end');
    if (startSlotIndex < 0 || endSlotIndex < 0) return null;

    const anchorSlot = getFixedTimeSlotRanges()[startSlotIndex];
    const topPx = getFixedSlotOffsetPx(startMinutes, startSlotIndex);
    const endOffsetPx = getFixedSlotOffsetPx(endMinutes, endSlotIndex);
    const rawHeightPx = ((endSlotIndex - startSlotIndex) * TABLE_SLOT_ROW_HEIGHT_PX) + endOffsetPx - topPx;

    return {
        anchorTime: anchorSlot.start,
        startMinutes,
        endMinutes,
        topPx: topPx + TABLE_TIMELINE_VERTICAL_INSET_PX,
        heightPx: Math.max(78, rawHeightPx - (TABLE_TIMELINE_VERTICAL_INSET_PX * 2))
    };
}

function usesOffSlotTimeLabel(lesson) {
    const begin = String(lesson?.beginLesson || '').trim();
    const end = String(lesson?.endLesson || '').trim();
    if (!begin || !end) return false;
    const startsOnGrid = FIXED_TIMES.some((slot) => slot.start === begin);
    const endsOnGrid = FIXED_TIMES.some((slot) => slot.end === end);
    return !(startsOnGrid && endsOnGrid);
}

function buildDayTimelineLayout(dayLessons) {
    const items = (dayLessons || [])
        .map((lesson) => {
            const placement = getLessonTimelinePlacement(lesson);
            return placement ? { lesson, placement } : null;
        })
        .filter(Boolean)
        .sort((left, right) => (
            left.placement.startMinutes - right.placement.startMinutes ||
            right.placement.endMinutes - left.placement.endMinutes
        ));

    const positioned = [];
    let active = [];
    let currentCluster = [];
    let currentClusterMaxLanes = 0;

    const flushCluster = () => {
        currentCluster.forEach((item) => {
            item.laneCount = Math.max(1, currentClusterMaxLanes);
        });
        currentCluster = [];
        currentClusterMaxLanes = 0;
    };

    items.forEach((item) => {
        active = active.filter((activeItem) => activeItem.endMinutes > item.placement.startMinutes);
        if (!active.length && currentCluster.length) {
            flushCluster();
        }

        let lane = 0;
        const usedLanes = new Set(active.map((activeItem) => activeItem.lane));
        while (usedLanes.has(lane)) lane += 1;

        item.lane = lane;
        active.push({ lane, endMinutes: item.placement.endMinutes });
        currentCluster.push(item);
        currentClusterMaxLanes = Math.max(currentClusterMaxLanes, active.length);
        positioned.push(item);
    });

    flushCluster();
    return positioned;
}

function getMonday(d) {
    const date = new Date(d);
    const day = date.getDay();
    const diff = date.getDate() - day + (day === 0 ? -6 : 1);
    date.setDate(diff);
    date.setHours(0, 0, 0, 0);
    return date;
}

async function changeWeek(offset) {
    currentWeekStart.setDate(currentWeekStart.getDate() + offset * 7);
    const weekEnd = new Date(currentWeekStart);
    weekEnd.setDate(weekEnd.getDate() + 6);
    const loadedStart = parseDate(loadedBounds.start);
    const loadedEnd = parseDate(loadedBounds.end);
    if (currentWeekStart < loadedStart || weekEnd > loadedEnd) {
        const targetDateStr = getISODateStr(currentWeekStart);
        await loadSchedule(currentEntity.type, currentEntity.id, currentEntity.name, targetDateStr, { urlMode: 'replace', preserveModules: true });
    } else {
        filterAndRender();
    }
    savePreferences();
}

async function setTodayWeek() {
    currentWeekStart = getMonday(new Date());
    await changeWeek(0);
}

function copyToClipboard(text, event) {
    navigator.clipboard.writeText(text).then(() => {
        const el = event.currentTarget;
        const originalHtml = el.innerHTML;
        el.innerHTML = `<span class="text-green-500 font-bold">${escapeHtml(t('schedule.copy.done', 'Скопировано!'))}</span>`;
        setTimeout(() => el.innerHTML = originalHtml, 1500);
    });
}

function getSearchResultTypeMeta(type) {
    const normalizedType = String(type || 'group').toLowerCase();
    if (normalizedType === 'person') {
        return { label: t('schedule.search.type.person', 'Преподаватель'), badgeClass: 'bg-sky-100 text-sky-700' };
    }
    if (normalizedType === 'auditorium') {
        return { label: t('schedule.search.type.auditorium', 'Аудитория'), badgeClass: 'bg-emerald-100 text-emerald-700' };
    }
    return { label: t('schedule.search.type.group', 'Группа'), badgeClass: 'bg-violet-100 text-violet-700' };
}

function getSearchCategoryButtons() {
    const items = [
        ['all', 'schedule.search.category.all', 'All'],
        ['group', 'schedule.search.type.group', 'Group'],
        ['person', 'schedule.search.type.person', 'Lecturer'],
        ['auditorium', 'schedule.search.type.auditorium', 'Auditorium'],
    ];
    return `
        <div class="flex gap-1 overflow-x-auto p-2">
            ${items.map(([type, key, fallback]) => `
                <button type="button" onclick="setScheduleSearchCategory('${type}')"
                    class="shrink-0 rounded-lg px-2.5 py-1.5 text-[11px] font-black transition-colors ${searchCategory === type
                        ? 'bg-slate-900 text-white dark:bg-blue-600'
                        : 'bg-slate-100 text-slate-600 hover:bg-blue-50 hover:text-blue-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-700'}">
                    ${escapeHtml(t(key, fallback))}
                </button>
            `).join('')}
        </div>
    `;
}

function getSearchLocalSources(query = '') {
    const favorites = window.ScheduleState?.getFavorites?.() || [];
    const recent = window.ScheduleState?.getRecent?.() || [];
    const cached = (cachedOfflineEntities || []).map((item) => ({ ...item, is_offline: true }));
    const merged = window.ScheduleState?.mergeEntities?.([favorites, recent, cached]) || [...favorites, ...recent, ...cached];
    if (!query) {
        return { favorites, recent, cached, matches: [] };
    }
    return {
        favorites,
        recent,
        cached,
        matches: window.ScheduleState?.filterLocalEntities?.(query, merged, searchCategory) || []
    };
}

function renderSearchEntityRow(item, sourceLabel = '') {
    const normalized = window.ScheduleState?.normalizeEntity?.(item) || item;
    const typeMeta = getSearchResultTypeMeta(normalized.type);
    const favorite = window.ScheduleState?.isFavorite?.(normalized);
    const savedModules = Array.isArray(normalized.modules) ? normalized.modules : null;
    const offlineBadge = normalized.is_offline
        ? `<span class="rounded bg-orange-100 px-2 py-0.5 text-[10px] font-bold text-orange-600 dark:bg-orange-950/40 dark:text-orange-300">${escapeHtml(t('schedule.search.cacheBadge', 'CACHE'))}</span>`
        : '';
    const sourceBadge = sourceLabel
        ? `<span class="rounded bg-slate-100 px-2 py-0.5 text-[10px] font-bold text-slate-500 dark:bg-slate-900 dark:text-slate-300">${escapeHtml(sourceLabel)}</span>`
        : '';
    const modulesBadge = savedModules
        ? `<span class="rounded bg-blue-100 px-2 py-0.5 text-[10px] font-bold text-blue-600 dark:bg-blue-950/40 dark:text-blue-300">${escapeHtml(t('schedule.search.savedModules', '{count} modules', { count: savedModules.length }))}</span>`
        : '';
    const itemType = escapeJsString(normalized.type || 'group');
    const itemId = escapeJsString(normalized.id);
    const itemLabel = escapeJsString(normalized.label || normalized.name || normalized.id);
    return `
        <div class="group flex items-stretch border-b border-slate-100 last:border-none dark:border-slate-700">
            <button type="button" class="min-w-0 flex-1 px-4 py-3 text-left hover:bg-blue-50 dark:hover:bg-slate-700"
                onclick="openScheduleFromSearch('${itemType}', '${itemId}', '${itemLabel}')">
                <div class="flex flex-wrap items-center gap-2 font-bold text-slate-800 dark:text-slate-100">
                    <span class="truncate">${escapeHtml(normalized.label || normalized.name || normalized.id)}</span>
                    <span class="rounded px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide ${typeMeta.badgeClass}">${escapeHtml(typeMeta.label)}</span>
                    ${offlineBadge}
                    ${sourceBadge}
                    ${modulesBadge}
                </div>
                <div class="mt-0.5 truncate text-xs text-slate-400">${escapeHtml(normalized.description || typeMeta.label)}</div>
            </button>
            <button type="button" onclick="toggleSearchFavorite(event, '${itemType}', '${itemId}', '${itemLabel}')"
                class="flex w-11 items-center justify-center text-lg ${favorite ? 'text-amber-400' : 'text-slate-300 hover:text-amber-400'}"
                aria-label="${escapeHtml(t('schedule.search.favorite', 'Favorite'))}">
                ${favorite ? '★' : '☆'}
            </button>
        </div>
    `;
}

function renderSearchSection(titleKey, fallback, items, sourceLabel = '') {
    if (!items.length) return '';
    return `
        <section>
            <div class="px-4 pb-1 pt-3 text-[10px] font-black uppercase tracking-[0.18em] text-slate-400">${escapeHtml(t(titleKey, fallback))}</div>
            ${items.map((item) => renderSearchEntityRow(item, sourceLabel)).join('')}
        </section>
    `;
}

function renderSearchHome() {
    const { favorites, recent, cached } = getSearchLocalSources();
    resultsBox.innerHTML = `
        ${getSearchCategoryButtons()}
        ${renderSearchSection('schedule.search.favorites', 'Favorites', favorites.slice(0, 5), t('schedule.search.source.favorite', 'Favorite'))}
        ${renderSearchSection('schedule.search.recent', 'Recent', recent.slice(0, 5), t('schedule.search.source.recent', 'Recent'))}
        ${renderSearchSection('schedule.search.offlineList', 'Available offline', cached.slice(0, 8), t('schedule.search.cacheBadge', 'CACHE'))}
        ${(!favorites.length && !recent.length && !cached.length) ? `
            <div class="px-6 py-8 text-center text-sm font-semibold text-slate-400">${escapeHtml(t('schedule.search.startTyping', 'Start typing to search schedules.'))}</div>
        ` : ''}
    `;
    resultsBox.classList.remove('hidden');
}

function renderSearchLoading(query) {
    const localMatches = getSearchLocalSources(query).matches.slice(0, 5);
    resultsBox.innerHTML = `
        ${getSearchCategoryButtons()}
        ${renderSearchSection('schedule.search.localMatches', 'From your lists', localMatches, t('schedule.search.source.local', 'Local'))}
        <div class="space-y-2 p-4">
            <div class="skeleton h-12 rounded-xl"></div>
            <div class="skeleton h-12 rounded-xl"></div>
            <div class="skeleton h-12 rounded-xl"></div>
        </div>
    `;
    resultsBox.classList.remove('hidden');
}

function renderSearchResults(results, { query = latestSearchQuery, networkState = 'ok' } = {}) {
    const normalizedResults = Array.isArray(results) ? results :[];
    latestSearchResults = normalizedResults;
    const localMatches = getSearchLocalSources(query).matches;
    const localKeys = new Set(localMatches.map((item) => window.ScheduleState?.entityKey?.(item)));
    const remoteResults = normalizedResults.filter((item) => !localKeys.has(window.ScheduleState?.entityKey?.(item)));
    const networkHtml = networkState === 'network-error'
        ? `<div class="mx-3 my-3 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm font-bold text-rose-700 dark:border-rose-900/60 dark:bg-rose-950/30 dark:text-rose-300">${escapeHtml(t('schedule.search.networkError', 'Network error. Showing local matches if available.'))}</div>`
        : '';
    const emptyHtml = !localMatches.length && !remoteResults.length
        ? `<div class="px-6 py-8 text-center text-sm font-semibold text-slate-400">${escapeHtml(networkState === 'empty' ? t('schedule.search.empty', 'Nothing found') : t('schedule.search.emptyLocal', 'No matching saved schedules.'))}</div>`
        : '';
    resultsBox.innerHTML = `
        ${getSearchCategoryButtons()}
        ${networkHtml}
        ${renderSearchSection('schedule.search.localMatches', 'From your lists', localMatches.slice(0, 6), t('schedule.search.source.local', 'Local'))}
        ${renderSearchSection('schedule.search.results', 'Search results', remoteResults, '')}
        ${emptyHtml}
    `;
    resultsBox.classList.remove('hidden');
}

async function performScheduleSearch() {
    const query = groupInput.value.trim();
    latestSearchQuery = query;
    const requestId = ++searchRequestSeq;
    if (query.length < 2) {
        renderSearchHome();
        return;
    }
    renderSearchLoading(query);
    try {
        const data = await (window.ScheduleApi?.searchEntities?.(query, searchCategory) || fetch(`${API_BASE}/schedule/search?term=${encodeURIComponent(query)}&type=${encodeURIComponent(searchCategory)}`).then((res) => {
            if (!res.ok) throw new Error('API Error');
            return res.json();
        }));
        if (requestId !== searchRequestSeq) return;
        renderSearchResults(data, { query, networkState: data.length ? 'ok' : 'empty' });
    } catch (err) {
        if (requestId !== searchRequestSeq) return;
        renderSearchResults([], { query, networkState: 'network-error' });
    }
}

groupInput.addEventListener('input', debounce(() => {
    performScheduleSearch();
}, 250));

groupInput.addEventListener('focus', () => {
    if (groupInput.value.trim().length < 2) renderSearchHome();
});

window.setScheduleSearchCategory = function(type) {
    searchCategory = ['all', 'group', 'person', 'auditorium'].includes(type) ? type : 'all';
    performScheduleSearch();
}

window.toggleSearchFavorite = function(event, type, id, label) {
    event?.stopPropagation();
    const entity = { type, id, label };
    const isCurrent = getScheduleEntityKey(entity) === getScheduleEntityKey(currentEntity);
    window.ScheduleState?.toggleFavorite?.(isCurrent
        ? { ...entity, modules: getSelectedModulesForStorage() }
        : entity);
    renderSearchResults(latestSearchResults, { query: latestSearchQuery, networkState: latestSearchResults.length ? 'ok' : 'empty' });
    renderScheduleHome();
}

window.openScheduleFromSearch = function(type, id, label) {
    const favorite = window.ScheduleState?.getFavorite?.({ type, id, label });
    if (Array.isArray(favorite?.modules)) {
        selectedModules = new Set(favorite.modules);
        return loadSchedule(type, id, label, null, {
            preserveModules: true,
            keepEmptyModules: favorite.modules.length === 0
        });
    }
    return loadSchedule(type, id, label);
}

async function loadSchedule(type, id, name, targetDate = null, options = {}) {
    resultsBox.classList.add('hidden');
    groupInput.value = name || id || '';
    const previousEntityKey = getScheduleEntityKey(currentEntity);
    const nextEntity = normalizeScheduleEntity({ type, id, name });
    if (!nextEntity.id) return;
    const nextEntityKey = getScheduleEntityKey(nextEntity);
    const entityChanged = previousEntityKey !== nextEntityKey;
    if (entityChanged && !options.preserveModules) {
        selectedModules.clear();
    }
    currentEntity = nextEntity;
    const requestedDate = normalizeScheduleDate(targetDate) || getISODateStr(new Date());
    currentWeekStart = getMonday(parseDate(requestedDate));
    setSchedulePageState({
        entity: currentEntity,
        date: getISODateStr(currentWeekStart),
        selectedModules: Array.from(selectedModules),
        calendarProfileId: options.calendarProfileId ?? schedulePageState.calendarProfileId
    });
    document.getElementById('defaultState').classList.add('hidden');
    document.getElementById('scheduleControls').classList.remove('hidden');
    document.getElementById('desktopSchedule').innerHTML = `<div class="p-8"><div class="skeleton h-64 w-full rounded-3xl"></div></div>`;
    document.getElementById('mobileSchedule').innerHTML = `<div class="skeleton h-64 w-full rounded-3xl"></div>`;
    sourceUpdatedAt = null;
    renderScheduleHome();
    try {
        const data = await (window.ScheduleApi?.loadScheduleData?.({
            type: nextEntity.type,
            id: nextEntity.id,
            baseDate: requestedDate,
            refresh: Boolean(options.refresh)
        }) || fetch(`${API_BASE}/schedule/data/${nextEntity.type}/${encodeURIComponent(nextEntity.id)}?base_date=${requestedDate}${options.refresh ? '&refresh=1' : ''}`).then((res) => {
            if (!res.ok) throw new Error('API Error');
            return res.json();
        }));
        fullSchedule = data.schedule ||[];
        allAvailableModules = data.available_modules ||[];
        loadedBounds = data.loaded_bounds || {start: "2000-01-01", end: "2099-01-01"};
        sourceUpdatedAt = data.source_updated_at || null;
        window.ScheduleState?.addRecent?.(currentEntity);
        const snapshotKey = getSnapshotEntityKey(nextEntity);
        const previousSnapshot = loadScheduleSnapshots()[snapshotKey];
        scheduleChangeSummary = buildScheduleChangeSummary(previousSnapshot, fullSchedule, sourceUpdatedAt);
        persistScheduleSnapshot(snapshotKey, fullSchedule, sourceUpdatedAt);
        if (selectedModules.size > 0) {
            const availableSet = new Set(allAvailableModules);
            selectedModules = new Set(Array.from(selectedModules).filter((module) => availableSet.has(module)));
        }
        if (selectedModules.size === 0 && !options.keepEmptyModules) {
            selectedModules = new Set(allAvailableModules);
        }
        isOfflineMode = data.is_offline || false;
        renderModuleFilters();
        filterAndRender();
        savePreferences();
        syncScheduleUrl(options.urlMode || (entityChanged ? 'push' : 'replace'));
        // Вызываем обновление календаря, так как сменилась сущность
        if (window._renderCalendarSubscriptionImpl) window._renderCalendarSubscriptionImpl();
    } catch (err) {
        const errorText = escapeHtml(t('schedule.error.load', 'Ошибка загрузки расписания.'));
        document.getElementById('desktopSchedule').innerHTML = `<div class="p-10 text-center text-red-500 font-bold">${errorText}</div>`;
        document.getElementById('mobileSchedule').innerHTML = `<div class="p-10 text-center text-red-500 font-bold">${errorText}</div>`;
    }
}

async function applyScheduleStateFromUrl() {
    const urlState = parseScheduleStateFromUrl();
    setSchedulePageState(urlState);
    window.calendarCurrentViewMode = schedulePageState.lessonMode === 'exams_only' ? 'exams_only' : 'all';
    selectedModules = new Set(urlState.selectedModules || []);
    if (urlState.entity?.id) {
        await loadSchedule(
            urlState.entity.type,
            urlState.entity.id,
            urlState.entity.name,
            urlState.date,
            { urlMode: 'replace', preserveModules: urlState.hasModules, keepEmptyModules: urlState.hasEmptyModules }
        );
        return;
    }
    currentEntity = { type: null, id: null, name: null };
    fullSchedule = [];
    allAvailableModules = [];
    selectedModules.clear();
    scheduleChangeSummary = null;
    isOfflineMode = false;
    document.getElementById('scheduleControls')?.classList.remove('hidden');
    document.getElementById('defaultState')?.classList.remove('hidden');
    document.getElementById('desktopSchedule').innerHTML = '';
    document.getElementById('mobileSchedule').innerHTML = '';
    renderScheduleHome();
    renderScheduleChangesPanel();
}

window.addEventListener('popstate', () => {
    applyScheduleStateFromUrl();
});

function renderModuleFilters() {
    const container = document.getElementById('moduleContainer');
    const section = document.getElementById('moduleFilterSection');
    const summary = document.getElementById('moduleSelectionSummary');
    const quickControls = document.getElementById('moduleQuickControls');
    const selectionStatus = document.getElementById('moduleSelectionStatus');
    if (!container || !section) return;
    if (allAvailableModules.length === 0) {
        if (summary) summary.textContent = '';
        if (selectionStatus) selectionStatus.textContent = '';
        if (quickControls) quickControls.classList.add('hidden');
        container.innerHTML = `
            <div class="rounded-2xl border border-slate-200 bg-white/70 px-4 py-3 text-sm font-semibold text-slate-500 dark:border-slate-700 dark:bg-slate-900/60 dark:text-slate-400">
                ${escapeHtml(t('schedule.modules.emptyState', 'Для этого расписания нет отдельных модулей.'))}
            </div>
        `;
        return;
    }
    const selectedCount = allAvailableModules.filter((mod) => selectedModules.has(mod)).length;
    if (summary) {
        summary.textContent = t('schedule.modules.selectedCount', '{selected}/{total}', {
            selected: selectedCount,
            total: allAvailableModules.length
        });
    }
    if (selectionStatus) {
        selectionStatus.textContent = t('schedule.modules.toolbarSummary', 'Модулей выбрано: {count}', {
            count: selectedCount
        });
    }
    if (quickControls) quickControls.classList.remove('hidden');
    const weekModules = getCurrentWeekModuleSet();
    const displayedModules = getCurrentDisplayedModuleSet();
    const selected = allAvailableModules.filter((mod) => selectedModules.has(mod) && getModuleSearchMatch(mod));
    const available = allAvailableModules.filter((mod) => !selectedModules.has(mod) && getModuleSearchMatch(mod));
    const presets = getCurrentEntityModulePresets();

    function renderModuleChip(mod, isSelected) {
        const displayStatus = getModuleDisplayStatus(mod, displayedModules, weekModules);
        return `
            <div class="group/module flex max-w-full flex-wrap items-center gap-1 rounded-2xl border px-2.5 py-2 text-xs font-bold transition-all duration-200
                ${isSelected
                    ? (displayStatus.active
                        ? 'border-slate-900 bg-slate-900 text-white shadow-lg shadow-slate-900/10'
                        : 'border-amber-300 bg-amber-100 text-amber-800 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-200')
                    : (displayStatus.active
                        ? 'border-slate-200 bg-slate-50 text-slate-500 hover:bg-white hover:border-blue-200 hover:text-slate-700 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-400 dark:hover:bg-slate-700 dark:hover:border-blue-700 dark:hover:text-slate-200'
                        : 'border-amber-200 bg-white text-amber-600 hover:bg-amber-50 dark:border-amber-900/70 dark:bg-slate-900 dark:text-amber-300 dark:hover:bg-amber-950/30')}">
                <button type="button" onclick="window.toggleModule('${escapeJsString(mod)}')" class="inline-flex min-w-0 flex-1 items-center gap-2 text-left">
                    ${isSelected ? '<span class="inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-white/15 text-[10px]">ON</span>' : ''}
                    <span class="truncate">${escapeHtml(mod)}</span>
                    ${displayStatus.active ? '' : `<span class="shrink-0 rounded-full bg-amber-200/70 px-1.5 py-0.5 text-[9px] font-black uppercase tracking-wide text-amber-800 dark:bg-amber-900/50 dark:text-amber-200">${escapeHtml(displayStatus.label)}</span>`}
                </button>
                <button type="button" onclick="selectOnlyModule('${escapeJsString(mod)}')" class="rounded-lg bg-white/80 px-2 py-1 text-[10px] font-black text-slate-600 ring-1 ring-slate-200 hover:bg-blue-50 hover:text-blue-700 dark:bg-slate-900/70 dark:text-slate-300 dark:ring-slate-700">${escapeHtml(t('schedule.modules.only', 'Only'))}</button>
                <button type="button" onclick="selectAllExceptModule('${escapeJsString(mod)}')" class="rounded-lg bg-white/80 px-2 py-1 text-[10px] font-black text-slate-600 ring-1 ring-slate-200 hover:bg-rose-50 hover:text-rose-700 dark:bg-slate-900/70 dark:text-slate-300 dark:ring-slate-700">${escapeHtml(t('schedule.modules.except', 'Except'))}</button>
            </div>
        `;
    }

    function renderModuleGroup(labelKey, fallback, items, toneClass) {
        if (items.length === 0) return '';
        return `
            <section class="rounded-2xl border ${toneClass} p-3">
                <div class="mb-3 flex items-center gap-2 text-[11px] font-black uppercase tracking-[0.18em] text-slate-400">
                    <span>${escapeHtml(t(labelKey, fallback))}</span>
                    <span class="rounded-full bg-white px-2 py-0.5 text-[10px] text-slate-500 shadow-sm dark:bg-slate-800 dark:text-slate-400">${items.length}</span>
                </div>
                <div class="flex flex-wrap gap-2">
                    ${items.map((mod) => renderModuleChip(mod, labelKey === 'schedule.filters.selected')).join('')}
                </div>
            </section>
        `;
    }

    container.innerHTML = `
        <div class="space-y-4">
            <div class="grid gap-3 lg:grid-cols-[minmax(0,1fr)_auto]">
                <label class="relative block">
                    <span class="sr-only">${escapeHtml(t('schedule.modules.search', 'Search modules'))}</span>
                    <input value="${escapeHtml(moduleFilterQuery)}" oninput="setModuleFilterQuery(this.value)"
                        placeholder="${escapeHtml(t('schedule.modules.searchPlaceholder', 'Search modules...'))}"
                        class="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm font-semibold text-slate-700 outline-none focus:ring-2 focus:ring-blue-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100">
                </label>
                <div class="rounded-2xl border border-slate-200 bg-white px-3 py-2 text-[11px] font-black uppercase tracking-[0.14em] text-slate-400 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300">
                    ${escapeHtml(t('schedule.modules.selectedCount', '{selected}/{total}', {
                        selected: selectedCount,
                        total: allAvailableModules.length
                    }))}
                </div>
            </div>
            ${presets.length ? `
                <section class="rounded-2xl border border-blue-100 bg-blue-50/60 p-3 dark:border-blue-900/60 dark:bg-blue-950/20">
                    <div class="mb-3 flex items-center gap-2 text-[11px] font-black uppercase tracking-[0.18em] text-blue-500 dark:text-blue-300">
                        <span>${escapeHtml(t('schedule.modules.presets', 'Module presets'))}</span>
                        <span class="rounded-full bg-white px-2 py-0.5 text-[10px] text-slate-500 shadow-sm dark:bg-slate-900 dark:text-slate-300">${presets.length}</span>
                    </div>
                    <div class="flex flex-wrap gap-2">
                        ${presets.map((preset) => `
                            <div class="inline-flex max-w-full items-center overflow-hidden rounded-xl border border-blue-200 bg-white text-xs font-black text-blue-700 dark:border-blue-800 dark:bg-slate-900 dark:text-blue-200">
                                <button type="button" onclick="applyModulePreset('${escapeJsString(preset.id)}')" class="min-w-0 px-3 py-2 text-left hover:bg-blue-50 dark:hover:bg-blue-950/40">
                                    <span class="block truncate">${escapeHtml(preset.name)}</span>
                                    <span class="block text-[9px] font-bold uppercase tracking-wide text-slate-400">${escapeHtml(t('schedule.modules.selectedCount', '{selected}/{total}', { selected: preset.modules.length, total: allAvailableModules.length }))}</span>
                                </button>
                                <button type="button" onclick="deleteModulePreset('${escapeJsString(preset.id)}')" class="px-2 py-2 text-rose-500 hover:bg-rose-50 dark:hover:bg-rose-950/30" aria-label="${escapeHtml(t('schedule.modules.deletePreset', 'Delete preset'))}">x</button>
                            </div>
                        `).join('')}
                    </div>
                </section>
            ` : ''}
            ${moduleFilterQuery && !selected.length && !available.length ? `
                <div class="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-semibold text-slate-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-400">
                    ${escapeHtml(t('schedule.modules.noSearchResults', 'No modules match the search.'))}
                </div>
            ` : ''}
            ${renderModuleGroup('schedule.filters.selected', 'Active', selected, 'border-slate-200 bg-slate-50/80 dark:border-slate-700 dark:bg-slate-800/80')}
            ${renderModuleGroup('schedule.filters.available', 'Available', available, 'border-blue-100 bg-blue-50/40 dark:border-blue-900/60 dark:bg-blue-950/20')}
        </div>
    `;
}

// Делаем функции глобальными, чтобы onClick из HTML мог их дергать
window.toggleModule = function(mod) {
    if (selectedModules.has(mod)) selectedModules.delete(mod);
    else selectedModules.add(mod);
    persistModuleSelection();
}

window.selectAllModules = function() {
    selectedModules = new Set(allAvailableModules);
    persistModuleSelection();
}

window.clearAllModules = function() {
    selectedModules.clear();
    persistModuleSelection();
}

window.refreshCurrentScheduleCache = async function() {
    if (!currentEntity?.id || isRefreshingScheduleCache) return;
    isRefreshingScheduleCache = true;
    renderOfflineHistory();
    try {
        await loadSchedule(currentEntity.type, currentEntity.id, currentEntity.name, getISODateStr(currentWeekStart), {
            preserveModules: true,
            refresh: true,
            urlMode: 'replace'
        });
        await initOfflineHistory();
    } finally {
        isRefreshingScheduleCache = false;
        renderOfflineHistory();
    }
}

function filterAndRender() {
    const offlineWarning = document.getElementById('offlineWarning');
    const cacheIsStale = isScheduleCacheStale(sourceUpdatedAt);
    if (offlineWarning) {
        const warningText = offlineWarning.querySelector('[data-i18n="schedule.offline.warning"]');
        if (isOfflineMode || cacheIsStale) {
            offlineWarning.classList.remove('hidden');
            if (warningText) {
                warningText.textContent = isOfflineMode
                    ? t('schedule.offline.warningDetailed', 'University service is unavailable. Loaded cached data from {time}.', { time: formatRelativeDateTime(sourceUpdatedAt) })
                    : t('schedule.offline.staleWarning', 'Opened data may be outdated. Cache updated {time}.', { time: formatRelativeDateTime(sourceUpdatedAt) });
            }
        } else {
            offlineWarning.classList.add('hidden');
        }
    }

    const weekEnd = getCurrentWeekEnd();
    document.getElementById('weekRangeDisplay').innerText =
        `${formatUiDate(currentWeekStart, {day:'numeric', month:'short'})} - ${formatUiDate(weekEnd, {day:'numeric', month:'short'})}`;

    const filteredLessons = fullSchedule.filter(lesson => {
        return isLessonInCurrentDisplayedScope(lesson, { includeModuleFilter: true });
    });
    lessonActionMap = new Map();
    renderDesktopGrid(filteredLessons);
    renderMobileFeed(filteredLessons);
    commitScheduleState({ urlMode: 'replace' });
    renderModuleFilters();
}

function renderDesktopGrid(lessons) {
    const container = document.getElementById('desktopSchedule');
    const weekDates =[];
    for(let i=0; i<7; i++) {
        const d = new Date(currentWeekStart);
        d.setDate(d.getDate() + i);
        weekDates.push(d);
    }
    const dayLessonsMap = {};
    lessons.forEach((lesson) => {
        const normDate = getISODateStr(parseDate(lesson.date));
        if (!dayLessonsMap[normDate]) dayLessonsMap[normDate] = [];
        dayLessonsMap[normDate].push(lesson);
    });

    const dayTimelineMap = {};
    Object.entries(dayLessonsMap).forEach(([dateStr, dayLessons]) => {
        const slotGroups = {};
        buildDayTimelineLayout(dayLessons).forEach((item) => {
            if (!slotGroups[item.placement.anchorTime]) slotGroups[item.placement.anchorTime] = [];
            slotGroups[item.placement.anchorTime].push(item);
        });
        dayTimelineMap[dateStr] = slotGroups;
    });

    const now = new Date();
    const currentMinutes = now.getHours() * 60 + now.getMinutes();

    let html = `
    <div class="schedule-table-wrap overflow-hidden relative" style="--schedule-slot-row-height: ${TABLE_SLOT_ROW_HEIGHT_PX}px;">
        <table class="schedule-desktop-table w-full table-fixed border-collapse text-left">
            <thead class="schedule-table-head">
                <tr>
                    <th class="w-16 sm:w-20 p-3 text-center text-xs font-bold border-r">${escapeHtml(t('schedule.table.time', 'Время'))}</th>`;
    weekDates.forEach(d => {
        const isToday = isSameDay(d, now);
        html += `<th class="schedule-day-head p-3 border-r last:border-r-0 ${isToday ? 'is-today' : ''} relative">
            ${isToday ? '<div class="schedule-today-marker absolute top-0 left-0 w-full h-1"></div>' : ''}
            <div class="flex flex-col items-center gap-0.5">
                <span class="schedule-day-label text-xs uppercase tracking-widest font-bold">${escapeHtml(formatUiDate(d, {weekday: 'short'}))}</span>
                <span class="schedule-day-number text-xl font-black">${d.getDate()}</span>
            </div>
        </th>`;
    });
    html += `</tr></thead><tbody class="schedule-table-body relative">`;

    FIXED_TIMES.forEach(timeSlot => {
        const timeStr = timeSlot.start;
        const[hStart, mStart] = timeSlot.start.split(':').map(Number);
        const[hEnd, mEnd] = timeSlot.end.split(':').map(Number);
        const slotStartMins = hStart * 60 + mStart;
        const slotEndMins = hEnd * 60 + mEnd;
        const isCurrentSlot = (currentMinutes >= slotStartMins && currentMinutes <= slotEndMins);

        html += `<tr class="schedule-slot-row border-t">
            <td class="schedule-time-cell p-2 border-r align-top text-center relative">
                <div class="schedule-time-start text-xs font-black ${isCurrentSlot ? 'text-red-500' : ''}">${timeSlot.start}</div>
                <div class="schedule-time-end text-[10px] font-medium">${timeSlot.end}</div>
                ${isCurrentSlot ? '<div class="absolute top-1/2 right-[-5px] w-2 h-2 rounded-full bg-red-500 z-20 transform -translate-y-1/2 shadow-[0_0_8px_rgba(239,68,68,0.8)]"></div>' : ''}
            </td>`;
        weekDates.forEach(d => {
            const dateStr = getISODateStr(d);
            const slotLessons = dayTimelineMap[dateStr]?.[timeStr] ||[];
            const isToday = isSameDay(d, now);
            html += `<td class="schedule-slot-cell p-1.5 border-r last:border-r-0 align-top ${isToday ? 'is-today' : ''} transition-colors relative">
                ${isToday && isCurrentSlot ? '<div class="absolute top-1/2 left-0 w-full h-[2px] bg-red-400 z-10 pointer-events-none opacity-50"></div>' : ''}
                <div class="schedule-slot-surface h-full relative">
                    ${slotLessons.map(({ lesson, placement, lane, laneCount }) => {
                        const laneWidth = 100 / Math.max(1, laneCount || 1);
                        const leftPercent = lane * laneWidth;
                        return `
                            <div class="schedule-timeline-card absolute z-20"
                                 style="top:${placement.topPx}px;height:${placement.heightPx}px;left:calc(${leftPercent}% + ${TABLE_TIMELINE_LANE_GAP_PX / 2}px);width:calc(${laneWidth}% - ${TABLE_TIMELINE_LANE_GAP_PX}px);">
                                ${renderCard(lesson, true)}
                            </div>
                        `;
                    }).join('')}
                </div>
            </td>`;
        });
        html += `</tr>`;
    });
    html += `</tbody></table></div>`;
    container.innerHTML = html;
}

function renderMobileFeed(lessons) {
    const container = document.getElementById('mobileSchedule');
    if (lessons.length === 0) {
        container.innerHTML = `<div class="text-center py-10 text-slate-400 text-sm">${escapeHtml(t('schedule.state.emptyWeek', 'Нет занятий на этой неделе.'))}</div>`;
        return;
    }
    const byDate = {};
    lessons.forEach(l => {
        const normDate = getISODateStr(parseDate(l.date));
        if(!byDate[normDate]) byDate[normDate] =[];
        byDate[normDate].push(l);
    });
    const sortedDates = Object.keys(byDate).sort();
    let html = '';
    sortedDates.forEach(dateStr => {
        const d = parseDate(dateStr);
        const isToday = isSameDay(d, new Date());
        const dayTitle = formatUiDateCapitalized(d, {weekday: 'long'});
        const dayDate = formatUiDate(d, {day: 'numeric', month: 'long'});
        html += `
        <section class="schedule-day-section relative">
            <div class="schedule-day-header ${isToday ? 'schedule-day-header--today' : ''}">
                <div>
                    <div class="schedule-day-header-label">${escapeHtml(dayDate)}</div>
                    <div class="schedule-day-header-title">${escapeHtml(dayTitle)}</div>
                </div>
                ${isToday ? `<span class="schedule-day-pill">${escapeHtml(t('schedule.day.today', 'Сегодня'))}</span>` : ''}
            </div>
            <div class="schedule-day-lessons">
                ${byDate[dateStr].sort((a,b) => a.beginLesson.localeCompare(b.beginLesson)).map(l => renderCard(l, false)).join('')}
            </div>
        </section>`;
    });
    container.innerHTML = html;
}

function normalizeLessonKind(kind) {
    return String(kind || '')
        .toLowerCase()
        .replace(/\u0451/g, '\u0435')
        .replace(/\s+/g, ' ')
        .trim();
}

function hasLessonKeyword(kind, keywords) {
    return keywords.some(keyword => kind.includes(keyword));
}

const EXAM_KIND_KEYWORDS = [
    '\u044d\u043a\u0437\u0430\u043c',
    '\u0437\u0430\u0447\u0435\u0442',
    '\u0430\u0442\u0442\u0435\u0441\u0442',
    'exam',
    'credit',
    'test'
];
const CONSULTATION_KIND_KEYWORDS = ['\u043a\u043e\u043d\u0441\u0443\u043b\u044c\u0442', 'consult'];

function isLectureKind(kind) {
    const k = normalizeLessonKind(kind);
    return hasLessonKeyword(k, ['\u043b\u0435\u043a\u0446', 'lecture']);
}

function isPracticeKind(kind) {
    const k = normalizeLessonKind(kind);
    return hasLessonKeyword(k, [
        '\u043f\u0440\u0430\u043a\u0442',
        '\u0441\u0435\u043c\u0438\u043d',
        'practice',
        'seminar'
    ]);
}

function isLabKind(kind) {
    const k = normalizeLessonKind(kind);
    return hasLessonKeyword(k, ['\u043b\u0430\u0431\u043e\u0440\u0430\u0442', 'laboratory', 'lab']);
}

function isConsultationKind(kind) {
    const k = normalizeLessonKind(kind);
    return hasLessonKeyword(k, CONSULTATION_KIND_KEYWORDS);
}

function isPreExamConsultationKind(kind) {
    const k = normalizeLessonKind(kind);
    return isConsultationKind(k) && hasLessonKeyword(k, EXAM_KIND_KEYWORDS);
}

function isExamLikeKind(kind) {
    const k = normalizeLessonKind(kind);
    return !isConsultationKind(k) && hasLessonKeyword(k, EXAM_KIND_KEYWORDS);
}

function isExamFocusedKind(kind) {
    return isExamLikeKind(kind) || isPreExamConsultationKind(kind);
}

function getShortKind(kind) {
    if (!kind) return '';
    if (isPreExamConsultationKind(kind)) return '\u041a\u043e\u043d\u0441. \u043f\u0435\u0440\u0435\u0434 \u044d\u043a\u0437.';
    if (isExamLikeKind(kind)) {
        return isPracticeKind(kind)
            ? '\u0421\u0435\u043c\u0438\u043d\u0430\u0440+\u0437\u0430\u0447\u0435\u0442'
            : '\u042d\u043a\u0437\u0430\u043c\u0435\u043d';
    }
    if (isLectureKind(kind)) return '\u041b\u0435\u043a\u0446\u0438\u044f';
    if (isPracticeKind(kind)) return '\u0421\u0435\u043c\u0438\u043d\u0430\u0440';
    if (isLabKind(kind)) return '\u041b\u0430\u0431\u043e\u0440\u0430\u0442\u043e\u0440\u043d\u0430\u044f';
    if (isConsultationKind(kind)) return '\u041a\u043e\u043d\u0441\u0443\u043b\u044c\u0442\u0430\u0446\u0438\u044f';
    return kind;
}

function getLessonActionId(lesson) {
    const raw = [
        lesson.date,
        lesson.beginLesson,
        lesson.endLesson,
        lesson.discipline_full || lesson.discipline || lesson.discipline_short,
        lesson.module,
        lesson.auditorium,
        lesson.lecturer_title,
    ].map((part) => String(part || '')).join('|');
    let hash = 0;
    for (let index = 0; index < raw.length; index += 1) {
        hash = ((hash << 5) - hash) + raw.charCodeAt(index);
        hash |= 0;
    }
    const id = `lesson-${Math.abs(hash).toString(36)}`;
    lessonActionMap.set(id, lesson);
    return id;
}

function getLessonActionLabels() {
    return {
        copyRoom: t('schedule.lesson.copyRoom', 'Copy room'),
        openTeacher: t('schedule.lesson.openTeacher', 'Open lecturer'),
        openRoom: t('schedule.lesson.openRoom', 'Open room'),
        singleIcs: t('schedule.lesson.singleIcs', 'Add to calendar'),
        onlyModule: t('schedule.lesson.onlyModule', 'Only module'),
        hideModule: t('schedule.lesson.hideModule', 'Hide module'),
        actionsToggle: t('schedule.lesson.actionsToggle', 'Actions'),
        actionsHide: t('schedule.lesson.actionsHide', 'Hide actions'),
    };
}

async function openLessonEntitySchedule(type, id, label) {
    const cleanLabel = String(label || id || '').trim();
    const cleanId = String(id || '').trim();
    if (!cleanLabel && !cleanId) return;
    try {
        const results = cleanLabel
            ? await (window.ScheduleApi?.searchEntities?.(cleanLabel, type) || [])
            : [];
        const match = Array.isArray(results)
            ? results.find((item) => String(item.label || '').toLowerCase() === cleanLabel.toLowerCase()) || results[0]
            : null;
        if (match?.id) {
            await loadSchedule(match.type || type, match.id, match.label || cleanLabel);
            return;
        }
    } catch (error) {
        console.warn('Schedule entity lookup failed:', error);
    }
    await loadSchedule(type, cleanId || cleanLabel, cleanLabel || cleanId);
}

window.runLessonAction = async function(action, lessonId, event) {
    event?.stopPropagation();
    const lesson = lessonActionMap.get(lessonId);
    if (!lesson) return;
    if (action === 'copyRoom') {
        copyToClipboard(lesson.auditorium || '', event);
        return;
    }
    if (action === 'openTeacher') {
        await openLessonEntitySchedule('person', lesson.lecturer || lesson.lecturer_id, lesson.lecturer_title);
        return;
    }
    if (action === 'openRoom') {
        await openLessonEntitySchedule('auditorium', lesson.auditorium_id || lesson.auditorium, lesson.auditorium);
        return;
    }
    if (action === 'singleIcs') {
        window.ScheduleRender?.downloadSingleLessonIcs?.(lesson, currentEntity?.name || 'schedule');
        return;
    }
    if (action === 'onlyModule' && lesson.module) {
        window.selectOnlyModule(lesson.module);
        return;
    }
    if (action === 'hideModule' && lesson.module) {
        selectedModules.delete(lesson.module);
        persistModuleSelection();
    }
}

function renderCard(l, isDesktop) {
    const lessonActionId = getLessonActionId(l);
    const color = getBadgeColor(l.kindOfWork);
    const discName = getPreferredDisciplineName(l);
    const teacherLabel = getPreferredLecturerName(l.lecturer_title);
    const showLessonActions = areLessonActionsVisible();
    const safeKind = escapeHtml(getShortKind(l.kindOfWork));
    const safeModule = escapeHtml(l.module || '');
    const safeDiscipline = escapeHtml(discName || '');
    const safeAuditorium = escapeHtml(l.auditorium || '');
    const safeAuditoriumJs = escapeJsString(l.auditorium || '');
    const safeLecturer = escapeHtml(teacherLabel || '');
    const safeLecturerJs = escapeJsString(l.lecturer_title || '');
    const safeTimeRange = escapeHtml(`${l.beginLesson || ''}${l.endLesson ? ` - ${l.endLesson}` : ''}`.trim());
    const showOffSlotTimeLabel = isDesktop && usesOffSlotTimeLabel(l);
    const roomTitle = escapeHtml(t('schedule.copy.room', 'Копировать аудиторию'));
    const teacherTitle = escapeHtml(t('schedule.copy.teacher', 'Копировать преподавателя'));
    const actionHtml = showLessonActions
        ? (window.ScheduleRender?.renderLessonActions?.(lessonActionId, getLessonActionLabels(), {
            compact: isDesktop,
            inline: true,
            iconOnly: isDesktop,
            hasModule: Boolean(l.module),
            hasRoom: Boolean(l.auditorium),
            hasTeacher: Boolean(l.lecturer_title || l.lecturer || l.lecturer_id),
        }) || '')
        : '';

    if (isDesktop) {
        const safeTeacherLabel = escapeHtml(teacherLabel || '');
        return `
        <div class="lesson-card ${color.bg} p-2.5 sm:p-3 rounded-2xl border transition-transform hover:-translate-y-0.5 hover:shadow-md flex flex-col h-full min-h-[110px]">
            <div class="flex justify-between items-start gap-1 mb-1.5">
                <div class="lesson-kind text-[10px] font-black uppercase tracking-wider truncate" title="${safeKind}">
                    ${safeKind}
                </div>
                ${l.module ? `
                    <span class="lesson-module px-1.5 py-0.5 rounded text-[8px] font-bold truncate max-w-[60px] border shadow-sm" title="${safeModule}">
                        ${safeModule}
                    </span>` : ''}
            </div>
            <div class="lesson-title font-bold text-[13px] leading-snug line-clamp-3 mb-2 flex-grow" title="${safeDiscipline}">
                ${safeDiscipline}
            </div>
            ${showOffSlotTimeLabel ? `
            <div class="mb-2 inline-flex w-fit items-center gap-1 rounded-full border border-white/15 bg-slate-950/20 px-2 py-1 text-[9px] font-black tracking-[0.18em] text-slate-100/85">
                <span>${safeTimeRange}</span>
            </div>` : ''}
            <div class="flex flex-col gap-1">
                ${safeAuditorium ? `
                <div class="lesson-meta flex items-center gap-1 text-[10px] font-medium hover:text-blue-600 cursor-pointer transition-colors"
                     onclick="copyToClipboard('${safeAuditoriumJs}', event)" title="${roomTitle}">
                    <svg class="w-3 h-3 shrink-0 opacity-50" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z"></path><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 11a3 3 0 11-6 0 3 3 0 016 0z"></path></svg>
                    <span class="truncate">${safeAuditorium}</span>
                </div>` : ''}
                ${teacherLabel ? `
                <div class="lesson-meta flex items-center gap-1 text-[10px] font-medium hover:text-blue-600 cursor-pointer transition-colors"
                     onclick="copyToClipboard('${safeLecturerJs}', event)" title="${teacherTitle}">
                    <svg class="w-3 h-3 shrink-0 opacity-50" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"></path></svg>
                    <span class="truncate">${safeTeacherLabel}</span>
                </div>` : ''}
            </div>
            ${actionHtml}
        </div>`;
    }
    return `
    <article class="schedule-feed-card">
        <div class="schedule-feed-card-head">
            <div class="schedule-feed-card-time">
                <span class="schedule-feed-card-start">${escapeHtml(l.beginLesson || '')}</span>
                <span class="schedule-feed-card-end">${escapeHtml(l.endLesson || '')}</span>
            </div>
            <span class="schedule-feed-card-kind lesson-card ${color.bg} lesson-kind px-2 py-0.5 rounded-md text-[10px] font-black tracking-wider border">
                ${safeKind}
            </span>
        </div>
        <div class="schedule-feed-card-body">
            <div class="schedule-feed-card-title">${safeDiscipline}</div>
            ${l.module ? `
                <span class="schedule-feed-card-module lesson-module inline-flex w-fit max-w-full rounded-md border px-2 py-1 text-[10px] font-bold">
                    ${safeModule}
                </span>` : ''}
        </div>
        <div class="schedule-feed-card-meta">
            ${safeAuditorium ? `
                <div class="schedule-feed-card-meta-item cursor-pointer active:text-blue-600"
                     onclick="copyToClipboard('${safeAuditoriumJs}', event)"
                     title="${roomTitle}">
                    <svg class="w-3.5 h-3.5 opacity-40 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z"></path><path d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" stroke-width="2"></path></svg>
                    <span>${safeAuditorium}</span>
                </div>
            ` : ''}
            ${safeLecturer ? `
                <div class="schedule-feed-card-meta-item cursor-pointer active:text-blue-600"
                     onclick="copyToClipboard('${safeLecturerJs}', event)"
                     title="${teacherTitle}">
                    <svg class="w-3.5 h-3.5 opacity-40 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" stroke-width="2"></path></svg>
                    <span>${safeLecturer}</span>
                </div>
            ` : ''}
        </div>
        ${actionHtml}
    </article>`;
}

function getBadgeColor(kind) {
    if (!kind) return { bg: '', border: '', text: 'lesson-kind' };
    if (isExamLikeKind(kind)) return { bg: 'lesson-card--exam', border: '', text: 'lesson-kind' };
    if (isLectureKind(kind)) return { bg: 'lesson-card--lecture', border: '', text: 'lesson-kind' };
    if (isConsultationKind(kind)) return { bg: 'lesson-card--consultation', border: '', text: 'lesson-kind' };
    if (isPracticeKind(kind) || isLabKind(kind)) return { bg: 'lesson-card--seminar', border: '', text: 'lesson-kind' };
    return { bg: '', border: '', text: 'lesson-kind' };
}

function debounce(func, timeout = 300){
    let timer;
    return (...args) => { clearTimeout(timer); timer = setTimeout(() => { func.apply(this, args); }, timeout); };
}

function isSameDay(d1, d2) {
    return d1.getFullYear() === d2.getFullYear() && d1.getMonth() === d2.getMonth() && d1.getDate() === d2.getDate();
}

let offlinePanelHideTimer = null;

function setOfflinePanelOpenState(isOpen) {
    const dropdown = document.getElementById('offlineDropdown');
    const arrow = document.getElementById('offlineArrow');
    const toggle = document.getElementById('offlinePanelToggle');
    if (!dropdown) return;

    clearTimeout(offlinePanelHideTimer);

    if (isOpen) {
        dropdown.classList.remove('hidden');
        requestAnimationFrame(() => {
            dropdown.classList.remove('opacity-0', 'translate-y-2');
            dropdown.classList.add('opacity-100', 'translate-y-0');
        });
    } else {
        dropdown.classList.add('opacity-0', 'translate-y-2');
        dropdown.classList.remove('opacity-100', 'translate-y-0');
        offlinePanelHideTimer = setTimeout(() => dropdown.classList.add('hidden'), 200);
    }

    if (arrow) {
        arrow.classList.toggle('rotate-180', isOpen);
    }
    if (toggle) {
        toggle.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
    }
}

function toggleOfflinePanel(event) {
    if (event) event.stopPropagation();
    const dropdown = document.getElementById('offlineDropdown');
    if (!dropdown) return;
    const isHidden = dropdown.classList.contains('hidden');
    setOfflinePanelOpenState(isHidden);
}

function closeOfflinePanel() {
    setOfflinePanelOpenState(false);
}

document.addEventListener('click', (e) => {
    if (!searchContainer.contains(e.target)) resultsBox.classList.add('hidden');
    const offlineContainer = document.getElementById('offlinePanelContainer');
    if (offlineContainer && !offlineContainer.contains(e.target)) {
        closeOfflinePanel();
    }
});

document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        closeOfflinePanel();
    }
});

// Глобальная функция для вызова из HTML onClick
window.toggleFiltersMobile = function() {
    window.toggleScheduleFilters?.();
};
