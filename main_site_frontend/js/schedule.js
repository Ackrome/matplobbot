// js/schedule.js
const API_BASE = "https://api.ivantishchenko.ru/api";

// Фиксированная шкала времени для сетки ПК
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
let currentEntity = { type: null, id: null, name: null };

let allAvailableModules =[];
let selectedModules = new Set();
let isOfflineMode = false;
let currentWeekStart = getMonday(new Date());

const groupInput = document.getElementById('groupSearch');
const resultsBox = document.getElementById('searchResults');
const searchContainer = document.getElementById('searchContainer');

document.addEventListener('click', (e) => {
    if (!searchContainer.contains(e.target)) resultsBox.classList.add('hidden');
});

// Загрузка оффлайн-списка при старте страницы
document.addEventListener('DOMContentLoaded', async () => {
    try {
        const res = await fetch(`${API_BASE}/schedule/cached_list`);
        if (res.ok) {
            const list = await res.json();
            const container = document.getElementById('cachedEntitiesList');
            container.innerHTML = list.map(item => `
                <button onclick="loadSchedule('${item.type}', '${item.id}', '${item.label}')" 
                        class="px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-bold rounded-xl transition-colors border border-slate-200">
                    ${item.label}
                </button>
            `).join('');
        }
    } catch (e) {
        document.getElementById('cachedEntitiesList').innerHTML = `<span class="text-xs text-slate-400">Нет данных</span>`;
    }
});

// Утилиты
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

// Навигация с дозагрузкой!
async function changeWeek(offset) {
    currentWeekStart.setDate(currentWeekStart.getDate() + offset * 7);
    
    // Проверяем, вышли ли мы за пределы загруженных данных
    const weekEnd = new Date(currentWeekStart);
    weekEnd.setDate(weekEnd.getDate() + 6);
    
    const loadedStart = parseDate(loadedBounds.start);
    const loadedEnd = parseDate(loadedBounds.end);

    if (currentWeekStart < loadedStart || weekEnd > loadedEnd) {
        // Делаем новый фетч на запрошенную дату
        const targetDateStr = getISODateStr(currentWeekStart);
        await loadSchedule(currentEntity.type, currentEntity.id, currentEntity.name, targetDateStr);
    } else {
        filterAndRender();
    }
}

async function setTodayWeek() {
    currentWeekStart = getMonday(new Date());
    await changeWeek(0); // Используем логику проверки кэша
}

// Копирование в буфер
function copyToClipboard(text, event) {
    navigator.clipboard.writeText(text).then(() => {
        const el = event.currentTarget;
        const originalHtml = el.innerHTML;
        el.innerHTML = `<span class="text-green-500 font-bold">Скопировано!</span>`;
        setTimeout(() => el.innerHTML = originalHtml, 1500);
    });
}

// Поиск
groupInput.addEventListener('input', debounce(async (e) => {
    const query = e.target.value.trim();
    if (query.length < 2) { resultsBox.classList.add('hidden'); return; }

    try {
        const res = await fetch(`${API_BASE}/schedule/search?term=${encodeURIComponent(query)}`);
        if (!res.ok) throw new Error("API Error");
        const data = await res.json();
        renderSearchResults(data);
    } catch (err) {
        resultsBox.innerHTML = `<div class="px-6 py-4 text-sm text-red-500 text-center font-medium">⚠️ Ошибка поиска или сервер недоступен.</div>`;
        resultsBox.classList.remove('hidden');
    }
}, 300));

function renderSearchResults(results) {
    if (results.length === 0) {
        resultsBox.innerHTML = `<div class="px-6 py-4 text-sm text-slate-500 text-center">Ничего не найдено</div>`;
    } else {
        resultsBox.innerHTML = results.map(item => {
            const offlineBadge = item.is_offline ? `<span class="ml-2 px-2 py-0.5 rounded text-[10px] font-bold bg-orange-100 text-orange-600">⚡ КЭШ</span>` : '';
            return `
            <div class="px-6 py-3 hover:bg-blue-50 cursor-pointer border-b border-slate-100 last:border-none" 
                 onclick="loadSchedule('${item.type || 'group'}', '${item.id}', '${item.label.replace(/'/g, "\\'")}')">
                <div class="font-bold text-slate-800 flex items-center">${item.label} ${offlineBadge}</div>
                <div class="text-xs text-slate-400 mt-0.5">${item.description || ''}</div>
            </div>`;
        }).join('');
    }
    resultsBox.classList.remove('hidden');
}

// Загрузка
async function loadSchedule(type, id, name, targetDate = null) {
    resultsBox.classList.add('hidden');
    groupInput.value = name;
    groupInput.blur();
    currentEntity = { type, id, name };
    
    document.getElementById('defaultState').classList.add('hidden');
    
    // Показываем скелетоны
    const skeletonHtml = `<div class="bg-white rounded-2xl border border-slate-200 p-4 h-96 flex flex-col gap-4">
        <div class="skeleton h-12 w-full rounded-xl"></div>
        <div class="skeleton h-full w-full rounded-xl"></div>
    </div>`;
    document.getElementById('desktopSchedule').innerHTML = skeletonHtml;
    document.getElementById('mobileSchedule').innerHTML = skeletonHtml;
    document.getElementById('desktopSchedule').classList.remove('hidden');
    document.getElementById('mobileSchedule').classList.remove('hidden');
    
    document.getElementById('offlineWarning').classList.add('hidden');
    document.getElementById('weekNav').classList.add('hidden');

    let url = `${API_BASE}/schedule/data/${type}/${id}`;
    if (targetDate) url += `?base_date=${targetDate}`;

    try {
        const res = await fetch(url);
        if(!res.ok) throw new Error("Load Error");
        const data = await res.json();
        
        fullSchedule = data.schedule || [];
        allAvailableModules = data.available_modules ||[]; 
        loadedBounds = data.loaded_bounds || {start: "2000-01-01", end: "2099-01-01"};
        
        // Модули обновляем только при первой загрузке (когда targetDate == null)
        if (!targetDate) {
            selectedModules = new Set(allAvailableModules);
            currentWeekStart = getMonday(new Date()); 
        }
        
        isOfflineMode = data.is_offline || false; 
        
        renderModuleFilters();
        filterAndRender();
    } catch (err) {
        document.getElementById('desktopSchedule').innerHTML = `<div class="text-center text-red-500 py-10 font-bold">Ошибка загрузки.</div>`;
        document.getElementById('mobileSchedule').innerHTML = `<div class="text-center text-red-500 py-10 font-bold">Ошибка загрузки.</div>`;
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
    container.innerHTML = allAvailableModules.map(mod => `
        <button onclick="toggleModule('${mod}')" 
            class="px-3 py-1.5 rounded-xl border text-xs sm:text-sm font-bold transition-all duration-200 
            ${selectedModules.has(mod) ? 'bg-slate-800 border-slate-800 text-white shadow-md' : 'bg-white border-slate-200 text-slate-400 hover:border-slate-300'}">
            ${selectedModules.has(mod) ? '✓ ' : ''}${mod}
        </button>
    `).join('');
}

function toggleModule(mod) {
    if (selectedModules.has(mod)) selectedModules.delete(mod);
    else selectedModules.add(mod);
    renderModuleFilters();
    filterAndRender();
}

function selectAllModules() { selectedModules = new Set(allAvailableModules); renderModuleFilters(); filterAndRender(); }
function clearAllModules() { selectedModules.clear(); renderModuleFilters(); filterAndRender(); }

// Главный рендер
function filterAndRender() {
    if (isOfflineMode) document.getElementById('offlineWarning').classList.remove('hidden');
    else document.getElementById('offlineWarning').classList.add('hidden');

    document.getElementById('weekNav').classList.remove('hidden');
    
    const weekEnd = new Date(currentWeekStart);
    weekEnd.setDate(weekEnd.getDate() + 6);
    
    document.getElementById('weekRangeDisplay').innerText = 
        `${currentWeekStart.toLocaleDateString('ru', {day:'numeric', month:'short'})} — ${weekEnd.toLocaleDateString('ru', {day:'numeric', month:'short'})}`;

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
    
    // Массив из 7 дней недели
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
        if (!gridData[normDate][l.beginLesson]) gridData[normDate][l.beginLesson] = [];
        gridData[normDate][l.beginLesson].push(l);
    });

    // Индикатор текущего времени
    const now = new Date();
    const currentMinutes = now.getHours() * 60 + now.getMinutes();

    let html = `
    <div class="bg-white rounded-3xl border border-slate-200 shadow-sm overflow-hidden relative">
        <table class="w-full table-fixed border-collapse text-left">
            <thead class="bg-slate-50 border-b border-slate-200">
                <tr>
                    <th class="w-16 sm:w-20 p-3 text-center text-xs font-bold text-slate-400 border-r border-slate-200">Время</th>`;
                    
    weekDates.forEach(d => {
        const isToday = isSameDay(d, now);
        html += `<th class="p-3 border-r border-slate-200 last:border-r-0 ${isToday ? 'bg-blue-50/70' : ''} relative">
            ${isToday ? '<div class="absolute top-0 left-0 w-full h-1 bg-blue-500"></div>' : ''}
            <div class="flex flex-col items-center">
                <span class="text-[10px] uppercase tracking-widest ${isToday ? 'text-blue-600 font-bold' : 'text-slate-400'}">${d.toLocaleDateString('ru', {weekday: 'short'})}</span>
                <span class="text-lg font-black ${isToday ? 'text-blue-700' : 'text-slate-800'}">${d.getDate()}</span>
            </div>
        </th>`;
    });
    html += `</tr></thead><tbody class="divide-y divide-slate-100 relative">`;

    // ИСПОЛЬЗУЕМ ФИКСИРОВАННОЕ ВРЕМЯ (FIXED_TIMES)
    FIXED_TIMES.forEach(timeSlot => {
        const timeStr = timeSlot.start;
        
        // Линия текущего времени (упрощенная логика: если текущее время попадает в слот)
        const [hStart, mStart] = timeSlot.start.split(':').map(Number);
        const[hEnd, mEnd] = timeSlot.end.split(':').map(Number);
        const slotStartMins = hStart * 60 + mStart;
        const slotEndMins = hEnd * 60 + mEnd;
        const isCurrentSlot = (currentMinutes >= slotStartMins && currentMinutes <= slotEndMins);

        html += `<tr>
            <td class="p-2 border-r border-slate-100 align-top text-center bg-slate-50/30 relative">
                <div class="text-xs font-black ${isCurrentSlot ? 'text-red-500' : 'text-slate-500'}">${timeSlot.start}</div>
                <div class="text-[10px] font-medium text-slate-400">${timeSlot.end}</div>
            </td>`;
            
        weekDates.forEach(d => {
            const dateStr = getISODateStr(d);
            const slotLessons = gridData[dateStr]?.[timeStr] ||[];
            const isToday = isSameDay(d, now);
            
            html += `<td class="p-1.5 border-r border-slate-100 last:border-r-0 align-top ${isToday ? 'bg-blue-50/10' : ''} hover:bg-slate-50 transition-colors relative">
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
        container.innerHTML = `<div class="text-center py-10 bg-white rounded-3xl border border-slate-200"><p class="text-slate-500">Нет занятий на этой неделе.</p></div>`;
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
        
        // НОВЫЙ ДИЗАЙН: Монолитный заголовок дня без прозрачности
        html += `
        <div class="mb-6 relative">
            <div class="sticky top-[64px] z-20 bg-slate-50 py-3 mb-3 border-b border-slate-200 flex items-end justify-between shadow-[0_4px_6px_-1px_rgba(248,250,252,1)]">
                <div class="font-black text-lg text-slate-800 capitalize leading-none">${d.toLocaleDateString('ru', {weekday: 'long'})}</div>
                <div class="text-sm font-bold ${isToday ? 'text-white bg-blue-600 px-3 py-1 rounded-full' : 'text-slate-500'}">${d.toLocaleDateString('ru', {day: 'numeric', month: 'long'})}</div>
            </div>
            
            <div class="flex flex-col gap-4 px-1">
                ${byDate[dateStr].sort((a,b) => a.beginLesson.localeCompare(b.beginLesson)).map(l => renderCard(l, false)).join('')}
            </div>
        </div>`;
    });
    container.innerHTML = html;
}

function renderCard(l, isDesktop) {
    const color = getBadgeColor(l.kindOfWork);
    const useShort = document.getElementById('useShortNames').checked;
    const discName = useShort ? l.discipline_short : l.discipline_full;
    
    // Для мобилки время пишем прямо внутри карточки сверху, для десктопа слева общая шкала
    const timeBlock = !isDesktop ? `
        <div class="flex items-center gap-2 mb-2 pb-2 border-b border-slate-100">
            <span class="font-black text-slate-800 bg-white px-2 py-0.5 rounded shadow-sm border border-slate-100">${l.beginLesson}</span>
            <span class="text-xs font-bold text-slate-400 line-through">${l.endLesson}</span>
        </div>` : '';

    const textClass = isDesktop ? "text-[11px] leading-snug line-clamp-3" : "text-sm";
    const iconSize = isDesktop ? "w-3 h-3" : "w-4 h-4";
    const detailClass = isDesktop ? "text-[10px]" : "text-xs";
    
    const teacherTokens = (l.lecturer_title || '').split(' ');
    const teacherShort = (isDesktop && teacherTokens.length > 2) 
        ? `${teacherTokens[0]} ${teacherTokens[1][0]}.${teacherTokens[2][0]}.` 
        : l.lecturer_title;

    return `
    <div class="p-2.5 sm:p-3 rounded-2xl border ${color.border} ${color.bg} shadow-sm transition-transform hover:-translate-y-0.5 hover:shadow-md flex flex-col h-full">
        ${timeBlock}
        <div class="flex justify-between items-start gap-1 mb-1.5">
            <div class="text-[9px] font-black uppercase tracking-wider ${color.text} truncate" title="${l.kindOfWork}">${l.kindOfWork}</div>
            ${l.module ? `<span class="px-1.5 py-0.5 rounded text-[8px] font-bold bg-white text-slate-600 truncate max-w-[60px] border border-slate-100" title="${l.module}">${l.module}</span>` : ''}
        </div>
        
        <div class="font-bold text-slate-800 ${textClass} mb-2 flex-grow" title="${discName}">${discName}</div>
        
        <div class="flex flex-col gap-1">
            <div class="flex items-center gap-1 ${detailClass} font-medium text-slate-600 hover:text-blue-600 cursor-pointer transition-colors" onclick="copyToClipboard('${l.auditorium}', event)" title="Копировать аудиторию">
                <svg class="${iconSize} shrink-0 opacity-50" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z"></path><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 11a3 3 0 11-6 0 3 3 0 016 0z"></path></svg>
                <span class="truncate">${l.auditorium}</span>
            </div>
            ${teacherShort ? `
            <div class="flex items-center gap-1 ${detailClass} font-medium text-slate-600 hover:text-blue-600 cursor-pointer transition-colors" onclick="copyToClipboard('${l.lecturer_title}', event)" title="Копировать ФИО">
                <svg class="${iconSize} shrink-0 opacity-50" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"></path></svg>
                <span class="truncate">${teacherShort}</span>
            </div>` : ''}
        </div>
    </div>`;
}

function getBadgeColor(kind) {
    if (!kind) return { bg: 'bg-slate-50', border: 'border-slate-200', text: 'text-slate-600' };
    const k = kind.toLowerCase();
    if (k.includes('лекц')) return { bg: 'bg-emerald-50/60', border: 'border-emerald-200', text: 'text-emerald-700' };
    if (k.includes('практ') || k.includes('семин')) return { bg: 'bg-amber-50/60', border: 'border-amber-200', text: 'text-amber-700' };
    if (k.includes('экзамен') || k.includes('зачет') || k.includes('аттест')) return { bg: 'bg-rose-50/60', border: 'border-rose-200', text: 'text-rose-700' };
    return { bg: 'bg-blue-50/60', border: 'border-blue-200', text: 'text-blue-700' };
}

function debounce(func, timeout = 300){
    let timer;
    return (...args) => { clearTimeout(timer); timer = setTimeout(() => { func.apply(this, args); }, timeout); };
}

function isSameDay(d1, d2) {
    return d1.getFullYear() === d2.getFullYear() && d1.getMonth() === d2.getMonth() && d1.getDate() === d2.getDate();
}