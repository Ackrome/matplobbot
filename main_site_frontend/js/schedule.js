// main_site_frontend/js/schedule.js
const API_BASE = window.getMpbApiBase ? window.getMpbApiBase() : "/api";
const STORAGE_KEY = "mpb_user_preferences";
const CALENDAR_SECTION_COLLAPSED_KEY = "mpb_calendar_sync_collapsed";
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
let scheduleAuthUser = null;
let calendarSubscriptionState = createDefaultCalendarSubscriptionState();
let isCalendarSubscriptionCollapsed = loadCalendarSectionCollapsed();
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
function createDefaultCalendarSubscriptionState() {
    return {
        loading: false,
        enabled: false,
        httpUrl: '',
        webcalUrl: '',
        hasError: false,
        justReset: false
    };
}
function loadCalendarSectionCollapsed() {
    try {
        return localStorage.getItem(CALENDAR_SECTION_COLLAPSED_KEY) === 'true';
    } catch (error) {
        return false;
    }
}
function setCalendarSectionCollapsed(nextValue) {
    isCalendarSubscriptionCollapsed = Boolean(nextValue);
    try {
        localStorage.setItem(CALENDAR_SECTION_COLLAPSED_KEY, isCalendarSubscriptionCollapsed ? 'true' : 'false');
    } catch (error) {}
}
function toggleCalendarSubscriptionSection() {
    setCalendarSectionCollapsed(!isCalendarSubscriptionCollapsed);
    renderCalendarSubscription();
}
window.addEventListener('mpb-auth-ready', (event) => {
    scheduleAuthUser = event.detail?.user || null;
    if (!scheduleAuthUser) {
        calendarSubscriptionState = createDefaultCalendarSubscriptionState();
        renderCalendarSubscription();
        return;
    }
    refreshCalendarSubscription();
});
document.addEventListener('DOMContentLoaded', async () => {
    await initOfflineHistory();
    await loadInitialPreferences();
    window.mpbI18n?.registerTranslator?.(() => {
        renderOfflineHistory();
        if (!resultsBox.classList.contains('hidden')) {
            renderSearchResults(latestSearchResults);
        }
        if (currentEntity?.id || fullSchedule.length > 0 || allAvailableModules.length > 0) {
            renderModuleFilters();
            filterAndRender();
        }
        renderCalendarSubscription();
    });
});
function renderOfflineHistory(list = cachedOfflineEntities) {
    const container = document.getElementById('cachedEntitiesList');
    if (!container) return;
    if (!Array.isArray(list) || list.length === 0) {
        container.innerHTML = `<div class="p-6 text-center text-xs text-slate-400 italic">${escapeHtml(t('schedule.history.empty', 'History is empty'))}</div>`;
        return;
    }
    container.innerHTML = list.map(item => {
        const itemType = escapeJsString(item.type);
        const itemId = escapeJsString(item.id);
        const itemLabel = escapeJsString(item.label);
        const labelText = escapeHtml(item.label);
        const savedText = escapeHtml(t('schedule.history.saved', 'Saved offline'));
        return `
            <button onclick="loadSchedule('${itemType}', '${itemId}', '${itemLabel}'); closeOfflinePanel();"
                    class="group w-full text-left px-4 py-3 bg-white hover:bg-blue-50 rounded-xl transition-all flex items-center justify-between border border-transparent hover:border-blue-100">
                <div>
                    <div class="text-xs font-black text-slate-700 group-hover:text-blue-700">${labelText}</div>
                    <div class="text-[9px] text-slate-400 uppercase tracking-tighter mt-0.5">${savedText}</div>
                </div>
                <svg class="w-3 h-3 text-slate-300 group-hover:text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M9 5l7 7-7 7" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg>
            </button>
        `;
    }).join('');
}
async function initOfflineHistory() {
    try {
        const res = await fetch(`${API_BASE}/schedule/cached_list`);
        if (res.ok) {
            cachedOfflineEntities = await res.json();
            renderOfflineHistory();
        }
    } catch (e) {
        console.warn("Не удалось загрузить список кэша:", e);
    }
}
async function loadInitialPreferences() {
    const token = localStorage.getItem('jwt_token');
    let remotePrefs = null;
    let localPrefs = null;
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
        if (prefsToApply.useShortNames !== undefined) {
            document.getElementById('useShortNames').checked = prefsToApply.useShortNames;
        }
        if (prefsToApply.showFullLecturerName !== undefined) {
            document.getElementById('showFullLecturerName').checked = prefsToApply.showFullLecturerName;
        }
        if (prefsToApply.entity && prefsToApply.entity.id) {
            if (prefsToApply.modules && prefsToApply.modules.length > 0) {
                selectedModules = new Set(prefsToApply.modules);
            }
            await loadSchedule(prefsToApply.entity.type, prefsToApply.entity.id, prefsToApply.entity.name);
        }
    }
}
async function savePreferences() {
    const prefs = {
        entity: currentEntity,
        modules: Array.from(selectedModules),
        useShortNames: document.getElementById('useShortNames').checked,
        showFullLecturerName: document.getElementById('showFullLecturerName').checked
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

// Заглушка для внешнего calendar_sync.js, чтобы не сломать если он загрузится позже
function renderCalendarSubscription() {
    if (window._renderCalendarSubscriptionImpl) {
        window._renderCalendarSubscriptionImpl();
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
        await loadSchedule(currentEntity.type, currentEntity.id, currentEntity.name, targetDateStr);
    } else {
        filterAndRender();
    }
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
groupInput.addEventListener('input', debounce(async (e) => {
    const query = e.target.value.trim();
    if (query.length < 2) {
        latestSearchResults =[];
        resultsBox.classList.add('hidden');
        return;
    }
    try {
        const res = await fetch(`${API_BASE}/schedule/search?term=${encodeURIComponent(query)}&type=all`);
        if (!res.ok) throw new Error("API Error");
        const data = await res.json();
        renderSearchResults(data);
    } catch (err) {
        resultsBox.innerHTML = `<div class="px-6 py-4 text-sm text-red-500 text-center font-medium">${escapeHtml(t('schedule.search.error', 'Ошибка поиска или сервер недоступен.'))}</div>`;
        resultsBox.classList.remove('hidden');
    }
}, 300));
function getSearchResultTypeMeta(type) {
    const normalizedType = String(type || 'group').toLowerCase();
    if (normalizedType === 'person') {
        return {
            label: t('schedule.search.type.person', 'Преподаватель'),
            badgeClass: 'bg-sky-100 text-sky-700'
        };
    }
    if (normalizedType === 'auditorium') {
        return {
            label: t('schedule.search.type.auditorium', 'Аудитория'),
            badgeClass: 'bg-emerald-100 text-emerald-700'
        };
    }
    return {
        label: t('schedule.search.type.group', 'Группа'),
        badgeClass: 'bg-violet-100 text-violet-700'
    };
}
function renderSearchResults(results) {
    const normalizedResults = Array.isArray(results) ? results :[];
    latestSearchResults = normalizedResults;
    if (normalizedResults.length === 0) {
        resultsBox.innerHTML = `<div class="px-6 py-4 text-sm text-slate-500 text-center">${escapeHtml(t('schedule.search.empty', 'Ничего не найдено'))}</div>`;
    } else {
        resultsBox.innerHTML = normalizedResults.map(item => {
            const typeMeta = getSearchResultTypeMeta(item.type);
            const offlineBadge = item.is_offline
                ? `<span class="ml-2 px-2 py-0.5 rounded text-[10px] font-bold bg-orange-100 text-orange-600">${escapeHtml(t('schedule.search.cacheBadge', 'КЭШ'))}</span>`
                : '';
            const itemType = escapeJsString(item.type || 'group');
            const itemId = escapeJsString(item.id);
            const itemLabel = escapeJsString(item.label);
            const labelText = escapeHtml(item.label);
            const descriptionText = escapeHtml(item.description || typeMeta.label);
            return `
            <div class="px-6 py-3 hover:bg-blue-50 cursor-pointer border-b border-slate-100 last:border-none"
                 onclick="loadSchedule('${itemType}', '${itemId}', '${itemLabel}')">
                <div class="font-bold text-slate-800 flex items-center flex-wrap gap-2">
                    <span>${labelText}</span>
                    <span class="px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wide ${typeMeta.badgeClass}">${escapeHtml(typeMeta.label)}</span>
                    ${offlineBadge}
                </div>
                <div class="text-xs text-slate-400 mt-0.5">${descriptionText}</div>
            </div>`;
        }).join('');
    }
    resultsBox.classList.remove('hidden');
}
async function loadSchedule(type, id, name, targetDate = null) {
    resultsBox.classList.add('hidden');
    groupInput.value = name;
    currentEntity = { type, id, name };
    document.getElementById('defaultState').classList.add('hidden');
    document.getElementById('scheduleControls').classList.remove('hidden');
    document.getElementById('desktopSchedule').innerHTML = `<div class="p-8"><div class="skeleton h-64 w-full rounded-3xl"></div></div>`;
    document.getElementById('mobileSchedule').innerHTML = `<div class="skeleton h-64 w-full rounded-3xl"></div>`;
    sourceUpdatedAt = null;
    let url = `${API_BASE}/schedule/data/${type}/${id}`;
    if (targetDate) url += `?base_date=${targetDate}`;
    savePreferences();
    try {
        const res = await fetch(url);
        const data = await res.json();
        fullSchedule = data.schedule || [];
        allAvailableModules = data.available_modules ||[];
        loadedBounds = data.loaded_bounds || {start: "2000-01-01", end: "2099-01-01"};
        sourceUpdatedAt = data.source_updated_at || null;
        if (!targetDate && selectedModules.size === 0) {
            selectedModules = new Set(allAvailableModules);
        }
        if (!targetDate) currentWeekStart = getMonday(new Date());
        isOfflineMode = data.is_offline || false;
        renderModuleFilters();
        filterAndRender();
    } catch (err) {
        const errorText = escapeHtml(t('schedule.error.load', 'Ошибка загрузки.'));
        document.getElementById('desktopSchedule').innerHTML = `<div class="p-10 text-center text-red-500 font-bold">${errorText}</div>`;
        document.getElementById('mobileSchedule').innerHTML = `<div class="p-10 text-center text-red-500 font-bold">${errorText}</div>`;
    }
}
function renderModuleFilters() {
    const container = document.getElementById('moduleContainer');
    const section = document.getElementById('moduleFilterSection');
    if (allAvailableModules.length === 0) {
        section.classList.add('hidden');
        return;
    }
    section.classList.remove('hidden');
    const selected = allAvailableModules.filter((mod) => selectedModules.has(mod));
    const available = allAvailableModules.filter((mod) => !selectedModules.has(mod));
    function renderModuleChip(mod, isSelected) {
        return `
            <button onclick="toggleModule('${escapeJsString(mod)}')"
                class="inline-flex max-w-full items-center gap-2 rounded-xl border px-3 py-2 text-xs sm:text-sm font-bold transition-all duration-200
                ${isSelected
                    ? 'bg-slate-900 border-slate-900 text-white shadow-lg shadow-slate-900/15'
                    : 'bg-slate-50 border-slate-200 text-slate-500 hover:bg-white hover:border-blue-200 hover:text-slate-700'}">
                ${isSelected ? '<span class="inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-white/15 text-[10px]">ON</span>' : ''}
                <span class="truncate">${escapeHtml(mod)}</span>
            </button>
        `;
    }
    function renderModuleGroup(labelKey, fallback, items, toneClass) {
        if (items.length === 0) return '';
        return `
            <section class="rounded-2xl border ${toneClass} p-3">
                <div class="mb-3 flex items-center gap-2 text-[11px] font-black uppercase tracking-[0.18em] text-slate-400">
                    <span>${escapeHtml(t(labelKey, fallback))}</span>
                    <span class="rounded-full bg-white px-2 py-0.5 text-[10px] text-slate-500 shadow-sm">${items.length}</span>
                </div>
                <div class="flex flex-wrap gap-2">
                    ${items.map((mod) => renderModuleChip(mod, labelKey === 'schedule.filters.selected')).join('')}
                </div>
            </section>
        `;
    }
    container.innerHTML = `
        <div class="space-y-3">
            ${renderModuleGroup('schedule.filters.selected', 'Активные', selected, 'border-slate-200 bg-slate-50/80')}
            ${renderModuleGroup('schedule.filters.available', 'Доступные', available, 'border-blue-100 bg-blue-50/40')}
        </div>
    `;
}
function toggleModule(mod) {
    if (selectedModules.has(mod)) selectedModules.delete(mod);
    else selectedModules.add(mod);
    renderModuleFilters();
    filterAndRender();
    savePreferences();
}
function selectAllModules() {
    selectedModules = new Set(allAvailableModules);
    renderModuleFilters();
    filterAndRender();
    savePreferences();
}
function clearAllModules() {
    selectedModules.clear();
    renderModuleFilters();
    filterAndRender();
    savePreferences();
}
function filterAndRender() {
    if (isOfflineMode) document.getElementById('offlineWarning').classList.remove('hidden');
    else document.getElementById('offlineWarning').classList.add('hidden');
    const weekEnd = new Date(currentWeekStart);
    weekEnd.setDate(weekEnd.getDate() + 6);
    document.getElementById('weekRangeDisplay').innerText =
        `${formatUiDate(currentWeekStart, {day:'numeric', month:'short'})} - ${formatUiDate(weekEnd, {day:'numeric', month:'short'})}`;
    const filteredLessons = fullSchedule.filter(lesson => {
        if (lesson.module && !selectedModules.has(lesson.module)) return false;
        const lessonDate = parseDate(lesson.date);
        if (lessonDate < currentWeekStart || lessonDate > weekEnd) return false;
        return true;
    });
    renderDesktopGrid(filteredLessons);
    renderMobileFeed(filteredLessons);
}
function renderDesktopGrid(lessons) {
    const container = document.getElementById('desktopSchedule');
    const weekDates =[];
    for(let i=0; i<7; i++) {
        const d = new Date(currentWeekStart);
        d.setDate(d.getDate() + i);
        weekDates.push(d);
    }
    const gridData = {};
    lessons.forEach(l => {
        const normDate = getISODateStr(parseDate(l.date));
        if (!gridData[normDate]) gridData[normDate] = {};
        if (!gridData[normDate][l.beginLesson]) gridData[normDate][l.beginLesson] =[];
        gridData[normDate][l.beginLesson].push(l);
    });
    const now = new Date();
    const currentMinutes = now.getHours() * 60 + now.getMinutes();
    let html = `
    <div class="overflow-hidden relative">
        <table class="w-full table-fixed border-collapse text-left">
            <thead class="bg-slate-50/50 border-b border-slate-100">
                <tr>
                    <th class="w-16 sm:w-20 p-3 text-center text-xs font-bold text-slate-400 border-r border-slate-200">${escapeHtml(t('schedule.table.time', 'Время'))}</th>`;
    weekDates.forEach(d => {
        const isToday = isSameDay(d, now);
        html += `<th class="p-3 border-r border-slate-200 last:border-r-0 ${isToday ? 'bg-blue-50/70' : ''} relative">
            ${isToday ? '<div class="absolute top-0 left-0 w-full h-1 bg-blue-500"></div>' : ''}
            <div class="flex flex-col items-center gap-0.5">
                <span class="text-xs uppercase tracking-widest font-bold ${isToday ? 'text-blue-600' : 'text-slate-500'}">${escapeHtml(formatUiDate(d, {weekday: 'short'}))}</span>
                <span class="text-xl font-black ${isToday ? 'text-blue-700' : 'text-slate-800'}">${d.getDate()}</span>
            </div>
        </th>`;
    });
    html += `</tr></thead><tbody class="divide-y divide-slate-100 relative">`;
    FIXED_TIMES.forEach(timeSlot => {
        const timeStr = timeSlot.start;
        const [hStart, mStart] = timeSlot.start.split(':').map(Number);
        const[hEnd, mEnd] = timeSlot.end.split(':').map(Number);
        const slotStartMins = hStart * 60 + mStart;
        const slotEndMins = hEnd * 60 + mEnd;
        const isCurrentSlot = (currentMinutes >= slotStartMins && currentMinutes <= slotEndMins);

        html += `<tr>
            <td class="p-2 border-r border-slate-100 align-top text-center bg-slate-50/30 relative">
                <div class="text-xs font-black ${isCurrentSlot ? 'text-red-500' : 'text-slate-500'}">${timeSlot.start}</div>
                <div class="text-[10px] font-medium text-slate-400">${timeSlot.end}</div>
                ${isCurrentSlot ? '<div class="absolute top-1/2 right-[-5px] w-2 h-2 rounded-full bg-red-500 z-20 transform -translate-y-1/2 shadow-[0_0_8px_rgba(239,68,68,0.8)]"></div>' : ''}
            </td>`;
        weekDates.forEach(d => {
            const dateStr = getISODateStr(d);
            const slotLessons = gridData[dateStr]?.[timeStr] ||[];
            const isToday = isSameDay(d, now);
            html += `<td class="p-1.5 border-r border-slate-100 last:border-r-0 align-top ${isToday ? 'bg-blue-50/30' : ''} hover:bg-slate-50 transition-colors relative">
                ${isToday && isCurrentSlot ? '<div class="absolute top-1/2 left-0 w-full h-[2px] bg-red-400 z-10 pointer-events-none opacity-50"></div>' : ''}
                <div class="flex flex-col gap-1.5 h-full">
                    ${slotLessons.map(l => renderCard(l, true)).join('')}
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
        if(!byDate[normDate]) byDate[normDate] = [];
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
function getShortKind(kind) {
    if (!kind) return '';
    const k = kind.toLowerCase();
    if (k.includes('лекц') || k.includes('lecture')) return 'Лекция';
    if (k.includes('практ') || k.includes('семин') || k.includes('seminar')) return 'Семинар';
    if (k.includes('экзам') || k.includes('зачет') || k.includes('аттест') || k.includes('exam')) return 'Экзамен';
    if (k.includes('лаборат')) return 'Лабораторная';
    if (k.includes('консульт')) return 'Консультация';
    return kind;
}
function renderCard(l, isDesktop) {
    const color = getBadgeColor(l.kindOfWork);
    const useShort = document.getElementById('useShortNames').checked;
    const showFullLecturerName = document.getElementById('showFullLecturerName').checked;
    const discName = useShort ? l.discipline_short : l.discipline_full;
    const safeKind = escapeHtml(getShortKind(l.kindOfWork));
    const safeModule = escapeHtml(l.module || '');
    const safeDiscipline = escapeHtml(discName || '');
    const safeAuditorium = escapeHtml(l.auditorium || '');
    const safeAuditoriumJs = escapeJsString(l.auditorium || '');
    const safeLecturer = escapeHtml(l.lecturer_title || '');
    const safeLecturerJs = escapeJsString(l.lecturer_title || '');
    const roomTitle = escapeHtml(t('schedule.copy.room', 'Копировать аудиторию'));
    const teacherTitle = escapeHtml(t('schedule.copy.teacher', 'Копировать преподавателя'));

    if (isDesktop) {
        const teacherTokens = String(l.lecturer_title || '').split(' ').filter(Boolean);
        const teacherShort = teacherTokens.length > 2
            ? `${teacherTokens[0]} ${teacherTokens[1][0]}.${teacherTokens[2][0]}.`
            : l.lecturer_title;
        const teacherLabel = showFullLecturerName ? l.lecturer_title : teacherShort;
        const safeTeacherLabel = escapeHtml(teacherLabel || '');
        return `
        <div class="p-2.5 sm:p-3 rounded-2xl border ${color.border} ${color.bg} shadow-sm transition-transform hover:-translate-y-0.5 hover:shadow-md flex flex-col h-full min-h-[110px]">
            <div class="flex justify-between items-start gap-1 mb-1.5">
                <div class="text-[10px] font-black uppercase tracking-wider ${color.text} truncate" title="${safeKind}">
                    ${safeKind}
                </div>
                ${l.module ? `
                    <span class="px-1.5 py-0.5 rounded text-[8px] font-bold bg-white text-slate-600 truncate max-w-[60px] border border-slate-100 shadow-sm" title="${safeModule}">
                        ${safeModule}
                    </span>` : ''}
            </div>
            <div class="font-bold text-slate-800 text-[13px] leading-snug line-clamp-3 mb-2 flex-grow" title="${safeDiscipline}">
                ${safeDiscipline}
            </div>
            <div class="flex flex-col gap-1">
                <div class="flex items-center gap-1 text-[10px] font-medium text-slate-700 hover:text-blue-600 cursor-pointer transition-colors"
                     onclick="copyToClipboard('${safeAuditoriumJs}', event)" title="${roomTitle}">
                    <svg class="w-3 h-3 shrink-0 opacity-50" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z"></path><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 11a3 3 0 11-6 0 3 3 0 016 0z"></path></svg>
                    <span class="truncate">${safeAuditorium}</span>
                </div>
                ${teacherLabel ? `
                <div class="flex items-center gap-1 text-[10px] font-medium text-slate-700 hover:text-blue-600 cursor-pointer transition-colors"
                     onclick="copyToClipboard('${safeLecturerJs}', event)" title="${teacherTitle}">
                    <svg class="w-3 h-3 shrink-0 opacity-50" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"></path></svg>
                    <span class="truncate">${safeTeacherLabel}</span>
                </div>` : ''}
            </div>
        </div>`;
    }
    const mobileBadgeBg = color.bg.includes('/') ? color.bg.split('/')[0] : color.bg;
    return `
    <article class="schedule-feed-card">
        <div class="schedule-feed-card-head">
            <div class="schedule-feed-card-time">
                <span class="schedule-feed-card-start">${escapeHtml(l.beginLesson || '')}</span>
                <span class="schedule-feed-card-end">${escapeHtml(l.endLesson || '')}</span>
            </div>
            <span class="schedule-feed-card-kind px-2 py-0.5 rounded-md text-[10px] font-black tracking-wider ${color.text} ${mobileBadgeBg} border ${color.border}">
                ${safeKind}
            </span>
        </div>
        <div class="schedule-feed-card-body">
            <div class="schedule-feed-card-title">${safeDiscipline}</div>
            ${l.module ? `
                <span class="schedule-feed-card-module inline-flex w-fit max-w-full rounded-md border border-slate-200 bg-slate-100 px-2 py-1 text-[10px] font-bold text-slate-500">
                    ${safeModule}
                </span>` : ''}
        </div>
        <div class="schedule-feed-card-meta">
            <div class="schedule-feed-card-meta-item cursor-pointer active:text-blue-600"
                 onclick="copyToClipboard('${safeAuditoriumJs}', event)"
                 title="${roomTitle}">
                <svg class="w-3.5 h-3.5 opacity-40 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z"></path><path d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" stroke-width="2"></path></svg>
                <span>${safeAuditorium}</span>
            </div>
            <div class="schedule-feed-card-meta-item cursor-pointer active:text-blue-600"
                 onclick="copyToClipboard('${safeLecturerJs}', event)"
                 title="${teacherTitle}">
                <svg class="w-3.5 h-3.5 opacity-40 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" stroke-width="2"></path></svg>
                <span>${safeLecturer}</span>
            </div>
        </div>
    </article>`;
}
function getBadgeColor(kind) {
    if (!kind) return { bg: 'bg-slate-50', border: 'border-slate-200', text: 'text-slate-600' };
    const k = kind.toLowerCase();
    const isLecture = k.includes('\u043b\u0435\u043a\u0446') || k.includes('lecture');
    const isPractice =
        k.includes('практ') ||
        k.includes('семин') ||
        k.includes('practice') ||
        k.includes('seminar') ||
        k.includes('практ') ||
        k.includes('семин');
    const isExamLike =
        k.includes('экзам') ||
        k.includes('зачет') ||
        k.includes('аттест') ||
        k.includes('exam') ||
        k.includes('credit') ||
        k.includes('test') ||
        k.includes('экзамен') ||
        k.includes('зачет') ||
        k.includes('аттест');
    if (isLecture) return { bg: 'bg-emerald-50/60', border: 'border-emerald-200', text: 'text-emerald-700' };
    if (isPractice) return { bg: 'bg-amber-50/60', border: 'border-amber-200', text: 'text-amber-700' };
    if (isExamLike) return { bg: 'bg-rose-50/60', border: 'border-rose-200', text: 'text-rose-700' };
    return { bg: 'bg-blue-50/60', border: 'border-blue-200', text: 'text-blue-700' };
}
function debounce(func, timeout = 300){
    let timer;
    return (...args) => { clearTimeout(timer); timer = setTimeout(() => { func.apply(this, args); }, timeout); };
}
function isSameDay(d1, d2) {
    return d1.getFullYear() === d2.getFullYear() && d1.getMonth() === d2.getMonth() && d1.getDate() === d2.getDate();
}
function toggleOfflinePanel(event) {
    if (event) event.stopPropagation();
    const dropdown = document.getElementById('offlineDropdown');
    const arrow = document.getElementById('offlineArrow');
    const isHidden = dropdown.classList.contains('hidden');
    if (isHidden) {
        dropdown.classList.remove('hidden');
        setTimeout(() => {
            dropdown.classList.remove('opacity-0', 'translate-y-2');
            dropdown.classList.add('opacity-100', 'translate-y-0');
        }, 10);
        arrow.classList.add('rotate-180');
    } else {
        closeOfflinePanel();
    }
}
function closeOfflinePanel() {
    const dropdown = document.getElementById('offlineDropdown');
    const arrow = document.getElementById('offlineArrow');
    dropdown.classList.add('opacity-0', 'translate-y-2');
    dropdown.classList.remove('opacity-100', 'translate-y-0');
    arrow.classList.remove('rotate-180');
    setTimeout(() => dropdown.classList.add('hidden'), 200);
}
document.addEventListener('click', (e) => {
    if (!searchContainer.contains(e.target)) resultsBox.classList.add('hidden');
    const offlineContainer = document.getElementById('offlinePanelContainer');
    if (offlineContainer && !offlineContainer.contains(e.target)) {
        closeOfflinePanel();
    }
});
function toggleFiltersMobile() {
    window.toggleScheduleFilters?.();
}
// Экспортируем функцию для UI Utils
window._renderCalendarSubscriptionImpl = function() {
    const container = document.getElementById('calendarSubscriptionSection');
    if (!container) return;
    if (!scheduleAuthUser) {
        container.classList.add('hidden');
        container.innerHTML = '';
        return;
    }
    container.classList.remove('hidden');
    const selectedProfile = window.getSelectedCalendarProfile ? window.getSelectedCalendarProfile() : null;
    const isProfileRevealed = selectedProfile && window.revealedCalendarProfileIds ? window.revealedCalendarProfileIds.has(selectedProfile.id) : false;
    const syncReady = Boolean(calendarSubscriptionState.enabled);
    const syncPaused = !calendarSubscriptionState.sync_enabled;
    const title = escapeHtml(t('schedule.calendar.title', 'Подписка на календарь'));
    const summary = syncReady
        ? escapeHtml(t('schedule.calendar.summaryReady', 'Приватные iCal-ленты для ваших профилей синхронизации на сайте.'))
        : syncPaused
            ? escapeHtml(t('schedule.calendar.summaryPaused', 'Ссылки календаря на паузе.'))
            : escapeHtml(t('schedule.calendar.summarySetup', 'Настройте приватные ленты расписания.'));
    const badgeText = syncReady
        ? escapeHtml(t('schedule.calendar.statusReady', 'Готово'))
        : syncPaused
            ? escapeHtml(t('schedule.calendar.statusPaused', 'На паузе'))
            : escapeHtml(t('schedule.calendar.statusSetup', 'Настройка'));
    const badgeClass = syncReady
        ? 'border-emerald-200 bg-emerald-100 text-emerald-700'
        : syncPaused
            ? 'border-slate-200 bg-slate-200 text-slate-700'
            : 'border-amber-200 bg-amber-100 text-amber-700';
    const toggleText = escapeHtml(
        t(
            isCalendarSubscriptionCollapsed ? 'schedule.calendar.expand' : 'schedule.calendar.collapse',
            isCalendarSubscriptionCollapsed ? 'Развернуть' : 'Свернуть'
        )
    );
    const toggleIconClass = isCalendarSubscriptionCollapsed ? '' : 'rotate-180';

    if (calendarSubscriptionState.loading) {
        container.innerHTML = `
            <div class="rounded-2xl border border-slate-200 bg-white p-4 md:p-5 shadow-sm">
                <div class="flex items-center gap-4 text-left">
                    <div class="flex items-center justify-center w-10 h-10 rounded-full bg-blue-50 text-blue-600 shrink-0">
                        <svg class="w-5 h-5 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"></path></svg>
                    </div>
                    <div>
                        <h2 class="text-base font-bold text-slate-900">${title}</h2>
                        <p class="text-xs text-slate-500 mt-0.5">${escapeHtml(t('schedule.calendar.loading', 'Загружаем данные...'))}</p>
                    </div>
                </div>
            </div>
        `;
        return;
    }

    const eligibilityNotice = calendarSubscriptionState.hasError
        ? `<div class="rounded-2xl border border-red-100 bg-red-50 px-4 py-3 text-sm text-red-600 mb-3">${escapeHtml(t('schedule.calendar.error', 'Ошибка загрузки подписки.'))}</div>`
        : !calendarSubscriptionState.eligibility?.available
            ? `<div class="rounded-2xl border border-amber-100 bg-amber-50 px-4 py-3 text-sm text-amber-700 mb-3">${escapeHtml(calendarSubscriptionState.eligibility?.detail || t('schedule.calendar.unavailable', 'Подписка на календарь доступна после привязки Telegram-аккаунта.'))}</div>`
            : syncPaused
                ? `<div class="rounded-2xl border border-slate-200 bg-slate-100 px-4 py-3 text-sm text-slate-700 mb-3">${escapeHtml(t('schedule.calendar.pausedNotice', 'Синхронизация на паузе.'))}</div>`
                : calendarSubscriptionState.justReset
                    ? `<div class="rounded-2xl border border-emerald-100 bg-emerald-50 px-4 py-3 text-sm text-emerald-700 mb-3">${escapeHtml(t('schedule.calendar.resetDone', 'Ссылка обновлена.'))}</div>`
                    : '';

    const profileButtons = (calendarSubscriptionState.profiles ||[]).map((profile) => `
        <button type="button"
                onclick="window.selectCalendarSubscriptionProfile('${escapeJsString(profile.id)}')"
                class="inline-flex items-center gap-2 rounded-full border px-3 py-2 text-xs font-bold transition-colors ${profile.selected ? 'border-slate-900 bg-slate-900 text-white' : 'border-slate-200 bg-white text-slate-600 hover:border-blue-200 hover:text-blue-600'}">
            <span>${escapeHtml(profile.name)}</span>
            <span class="rounded-full px-2 py-0.5 text-[10px] uppercase tracking-[0.15em] ${profile.selected ? 'bg-white/15 text-white' : 'bg-slate-100 text-slate-400'}">${escapeHtml(profile.kind === 'custom' ? t('schedule.calendar.profile.custom', 'Пресет') : t('schedule.calendar.profile.builtin', 'Базовый'))}</span>
        </button>
    `).join('');

    const visibleLink = selectedProfile
        ? (isProfileRevealed ? selectedProfile.links.http_url : selectedProfile.links.masked_http_url)
        : '';
    const modulesLabel = selectedProfile?.modules?.length
        ? escapeHtml(selectedProfile.modules.join(', '))
        : escapeHtml(t('schedule.calendar.meta.modulesAll', 'Все модули'));

    const profileDetailsHtml = selectedProfile
        ? `
            <div class="grid gap-3 md:grid-cols-2 xl:grid-cols-3 mb-4">
                <div class="rounded-2xl border border-slate-200 bg-slate-50/50 p-4">
                    <div class="text-[10px] font-black uppercase tracking-wider text-slate-400">${escapeHtml(t('schedule.calendar.urlLabel', 'URL подписки'))}</div>
                    <code class="mt-1 block break-all text-xs font-medium text-slate-700">${escapeHtml(visibleLink || '')}</code>
                </div>
                <div class="rounded-2xl border border-slate-200 bg-slate-50/50 p-4">
                    <div class="text-[10px] font-black uppercase tracking-wider text-slate-400">${escapeHtml(t('schedule.calendar.meta.scope', 'Состав'))}</div>
                    <div class="mt-1 text-sm font-bold text-slate-800">${escapeHtml(selectedProfile.scope_label || selectedProfile.name)}</div>
                </div>
                <div class="rounded-2xl border border-slate-200 bg-slate-50/50 p-4">
                    <div class="text-[10px] font-black uppercase tracking-wider text-slate-400">${escapeHtml(t('schedule.calendar.meta.modules', 'Модули'))}</div>
                    <div class="mt-1 text-sm font-bold text-slate-800">${modulesLabel}</div>
                </div>
            </div>
        `
        : '';

    const canUseLinks = Boolean(calendarSubscriptionState.sync_enabled && selectedProfile?.links?.http_url);
    const actionButtonsHtml = selectedProfile ? `
        <div class="flex flex-col gap-2 sm:flex-row sm:flex-wrap mb-4 border-t border-slate-100 pt-4">
            <button type="button" ${canUseLinks ? '' : 'disabled'}
                    onclick="window.copyCalendarSubscriptionLink(event)"
                    class="inline-flex items-center justify-center rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-semibold transition-colors ${canUseLinks ? 'text-slate-700 hover:border-blue-200 hover:text-blue-600' : 'cursor-not-allowed text-slate-400'}">
                ${escapeHtml(t('schedule.calendar.copy', 'Копировать'))}
            </button>
            <button type="button"
                    onclick="window.toggleCalendarProfileReveal('${escapeJsString(selectedProfile.id)}')"
                    class="inline-flex items-center justify-center rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-700 transition-colors hover:border-blue-200 hover:text-blue-600">
                ${escapeHtml(isProfileRevealed ? t('schedule.calendar.hide', 'Скрыть') : t('schedule.calendar.reveal', 'Показать'))}
            </button>
            <button type="button" ${canUseLinks ? '' : 'disabled'}
                    onclick="window.openCalendarProfileLink('webcal')"
                    class="inline-flex items-center justify-center rounded-xl border border-blue-200 bg-blue-600 px-4 py-2 text-sm font-bold text-white transition-colors ${canUseLinks ? 'hover:bg-blue-700' : 'cursor-not-allowed opacity-60'}">
                ${escapeHtml(t('schedule.calendar.apple', 'Настроить (iOS / Mac)'))}
            </button>
            <button type="button"
                    onclick="window.toggleCalendarSync(!calendarSubscriptionState.sync_enabled)"
                    class="inline-flex items-center justify-center rounded-xl border border-slate-200 bg-slate-100 px-4 py-2 text-sm font-semibold text-slate-700 transition-colors hover:border-slate-300 hover:bg-slate-200">
                ${escapeHtml(calendarSubscriptionState.sync_enabled ? t('schedule.calendar.disable', 'Выключить') : t('schedule.calendar.enable', 'Включить'))}
            </button>
            <button type="button"
                    onclick="window.resetCalendarSubscription()"
                    class="inline-flex items-center justify-center rounded-xl border border-slate-200 bg-slate-100 px-4 py-2 text-sm font-semibold text-slate-700 transition-colors hover:border-slate-300 hover:bg-slate-200">
                ${escapeHtml(t('schedule.calendar.reset', 'Сбросить'))}
            </button>
        </div>
    ` : '';

    const currentViewCardHtml = `
        <div class="rounded-2xl border border-blue-100 bg-blue-50/50 p-4 border-dashed mt-4">
            <div class="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
                <div class="min-w-0">
                    <div class="text-[10px] font-black uppercase tracking-wider text-blue-400">${escapeHtml(t('schedule.calendar.currentView.title', 'Пресет текущей страницы'))}</div>
                    <div class="mt-1 text-sm font-bold text-slate-800">${window.getCalendarCurrentViewSummary ? window.getCalendarCurrentViewSummary() : ''}</div>
                    <p class="mt-1 text-xs text-slate-500">${escapeHtml(t('schedule.calendar.currentView.description', 'Сохранить эту страницу как iCal-ленту.'))}</p>
                </div>
                <div class="flex flex-col gap-2 sm:flex-row sm:items-center">
                    <select id="calendarCurrentViewMode" onchange="window.calendarCurrentViewMode=this.value" class="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 outline-none focus:border-blue-400">
                        <option value="all" ${window.calendarCurrentViewMode === 'all' ? 'selected' : ''}>${escapeHtml(t('schedule.calendar.mode.all', 'Все занятия'))}</option>
                        <option value="exams_only" ${window.calendarCurrentViewMode === 'exams_only' ? 'selected' : ''}>${escapeHtml(t('schedule.calendar.mode.exams', 'Только экзамены'))}</option>
                    </select>
                    <button type="button" ${currentEntity?.id ? '' : 'disabled'}
                            onclick="window.createCalendarProfileFromCurrentView()"
                            class="inline-flex items-center justify-center rounded-xl border border-blue-200 bg-blue-50 px-4 py-2 text-sm font-bold transition-colors ${currentEntity?.id ? 'text-blue-700 hover:bg-blue-100' : 'cursor-not-allowed text-slate-400'}">
                        ${escapeHtml(t('schedule.calendar.currentView.save', 'Сохранить'))}
                    </button>
                </div>
            </div>
        </div>
    `;

    const panelBodyHtml = isCalendarSubscriptionCollapsed ? '' : `
        <div class="mt-4 flex flex-col border-t border-slate-100 pt-4 animate-fade-in-up">
            ${eligibilityNotice}
            <div class="text-[10px] font-black uppercase tracking-wider text-slate-400 mb-3">Ваши пресеты (Профили синхронизации)</div>
            <div class="flex flex-wrap gap-2 mb-4">${profileButtons}</div>
            ${profileDetailsHtml}
            ${actionButtonsHtml}
            ${currentViewCardHtml}
        </div>
    `;

    container.innerHTML = `
        <div class="rounded-2xl border border-slate-200 bg-white p-4 md:p-5 shadow-sm">
            <button type="button" onclick="toggleCalendarSubscriptionSection()" class="flex w-full items-center justify-between gap-4 text-left group">
                <div class="flex items-center gap-3">
                    <div class="flex items-center justify-center w-10 h-10 rounded-full bg-slate-50 group-hover:bg-blue-50 text-slate-400 group-hover:text-blue-600 shrink-0 transition-colors">
                        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"></path></svg>
                    </div>
                    <div>
                        <div class="flex items-center gap-2">
                            <div class="text-[10px] font-black uppercase tracking-wider text-emerald-500">СИНХРОНИЗАЦИЯ</div>
                        </div>
                        <div class="flex items-center gap-2 mt-0.5">
                            <h2 class="text-lg font-black tracking-tight text-slate-900">${title}</h2>
                            <span class="inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider ${statusBadgeClass}">
                                ${statusBadge}
                            </span>
                        </div>
                        <p class="text-xs text-slate-500 mt-1 hidden sm:block">${summary}</p>
                    </div>
                </div>
                <span class="inline-flex shrink-0 items-center justify-center w-8 h-8 md:w-auto md:h-auto md:px-3 md:py-1.5 md:rounded-xl rounded-full border border-slate-200 bg-white text-xs font-bold text-slate-600 shadow-sm hover:bg-slate-50 transition-colors">
                    <span class="hidden md:inline mr-2">${toggleText}</span>
                    <svg class="h-4 w-4 transition-transform ${toggleIconClass}" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"></path>
                    </svg>
                </span>
            </button>
            ${panelBodyHtml}
        </div>
    `;
};
