// js/schedule.js
const API_BASE = "https://api.ivantishchenko.ru/api";

let fullSchedule = [];
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

// Безопасная работа с датами (сброс времени в 00:00:00 локальной зоны)
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

function changeWeek(offset) {
    currentWeekStart.setDate(currentWeekStart.getDate() + offset * 7);
    filterAndRender();
}

function setTodayWeek() {
    currentWeekStart = getMonday(new Date());
    filterAndRender();
}

groupInput.addEventListener('input', debounce(async (e) => {
    const query = e.target.value.trim();
    if (query.length < 2) {
        resultsBox.classList.add('hidden');
        return;
    }

    try {
        const res = await fetch(`${API_BASE}/schedule/search?term=${encodeURIComponent(query)}`);
        if (!res.ok) {
            let errorMsg = "API ВУЗа временно недоступно";
            try { const errData = await res.json(); if (errData.detail) errorMsg = errData.detail; } catch (e) {}
            resultsBox.innerHTML = `<div class="px-6 py-4 text-sm text-red-500 text-center font-medium">⚠️ ${errorMsg}</div>`;
            resultsBox.classList.remove('hidden');
            return;
        }
        const data = await res.json();
        renderSearchResults(data);
    } catch (err) {
        resultsBox.innerHTML = `<div class="px-6 py-4 text-sm text-red-500 text-center font-medium">❌ Ошибка сети или сервер недоступен.</div>`;
        resultsBox.classList.remove('hidden');
    }
}, 300));

function renderSearchResults(results) {
    if (results.length === 0) {
        resultsBox.innerHTML = `<div class="px-6 py-4 text-sm text-slate-500 text-center">Ничего не найдено</div>`;
    } else {
        resultsBox.innerHTML = results.map(item => {
            const offlineBadge = item.is_offline ? `<span class="ml-2 px-2 py-0.5 rounded text-[10px] font-bold bg-orange-100 text-orange-600 border border-orange-200">⚡ ОФФЛАЙН</span>` : '';
            return `
            <div class="px-6 py-3 hover:bg-blue-50 cursor-pointer border-b border-slate-100 last:border-none transition-colors" 
                 onclick="loadSchedule('${item.type || 'group'}', '${item.id}', '${item.label.replace(/'/g, "\\'")}')">
                <div class="font-bold text-slate-800 flex items-center">${item.label} ${offlineBadge}</div>
                <div class="text-xs text-slate-400 mt-0.5">${item.description || (item.type === 'person' ? 'Преподаватель' : 'Группа')}</div>
            </div>`;
        }).join('');
    }
    resultsBox.classList.remove('hidden');
}

async function loadSchedule(type, id, name) {
    resultsBox.classList.add('hidden');
    groupInput.value = name;
    groupInput.blur();
    
    document.getElementById('desktopSchedule').innerHTML = `<div class="text-center py-20 text-blue-500">Загрузка...</div>`;
    document.getElementById('mobileSchedule').innerHTML = `<div class="text-center py-20 text-blue-500">Загрузка...</div>`;
    document.getElementById('offlineWarning').classList.add('hidden');
    document.getElementById('weekNav').classList.add('hidden');

    try {
        const res = await fetch(`${API_BASE}/schedule/data/${type}/${id}`);
        const data = await res.json();
        
        fullSchedule = data.schedule ||[];
        allAvailableModules = data.available_modules ||[]; 
        selectedModules = new Set(allAvailableModules);
        isOfflineMode = data.is_offline || false; 
        
        setTodayWeek(); // Сбрасываем на текущую неделю и рендерим
        renderModuleFilters();
    } catch (err) {
        console.error("Load error", err);
        document.getElementById('desktopSchedule').innerHTML = `<div class="text-center text-red-500 py-10 font-medium">Ошибка загрузки расписания.</div>`;
        document.getElementById('mobileSchedule').innerHTML = `<div class="text-center text-red-500 py-10 font-medium">Ошибка загрузки расписания.</div>`;
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

function filterAndRender() {
    if (isOfflineMode) document.getElementById('offlineWarning').classList.remove('hidden');
    else document.getElementById('offlineWarning').classList.add('hidden');

    if (fullSchedule.length === 0) return;

    document.getElementById('weekNav').classList.remove('hidden');

    // Границы недели
    const weekEnd = new Date(currentWeekStart);
    weekEnd.setDate(weekEnd.getDate() + 6);
    
    document.getElementById('weekRangeDisplay').innerText = 
        `${currentWeekStart.toLocaleDateString('ru', {day:'numeric', month:'short'})} — ${weekEnd.toLocaleDateString('ru', {day:'numeric', month:'short'})}`;

    // Фильтрация по модулям и датам недели
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
    if (lessons.length === 0) {
        container.innerHTML = `<div class="text-center py-20 bg-white rounded-3xl border border-slate-200"><p class="text-slate-500">Нет занятий на этой неделе.</p></div>`;
        return;
    }

    const timesSet = new Set();
    const gridData = {}; 

    lessons.forEach(l => {
        timesSet.add(l.beginLesson);
        const normDate = getISODateStr(parseDate(l.date));
        if (!gridData[normDate]) gridData[normDate] = {};
        if (!gridData[normDate][l.beginLesson]) gridData[normDate][l.beginLesson] =[];
        gridData[normDate][l.beginLesson].push(l);
    });

    const sortedTimes = Array.from(timesSet).sort();
    
    // 7 дней недели
    const weekDates =[];
    for(let i=0; i<7; i++) {
        const d = new Date(currentWeekStart);
        d.setDate(d.getDate() + i);
        weekDates.push(d);
    }

    // Строгая таблица (table-fixed, w-full), колонка времени узкая, остальные делят ширину
    let html = `
    <div class="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
        <table class="w-full table-fixed border-collapse text-left">
            <thead class="bg-slate-50/80 border-b border-slate-200">
                <tr>
                    <th class="w-14 sm:w-16 p-2 text-center text-[10px] sm:text-xs font-bold text-slate-400 border-r border-slate-200">Время</th>`;
                    
    weekDates.forEach(d => {
        const isToday = isSameDay(d, new Date());
        html += `<th class="p-2 border-r border-slate-200 last:border-r-0 ${isToday ? 'bg-blue-50/50' : ''}">
            <div class="flex flex-col items-center">
                <span class="text-[9px] sm:text-[10px] uppercase tracking-wider ${isToday ? 'text-blue-600' : 'text-slate-400'}">${d.toLocaleDateString('ru', {weekday: 'short'})}</span>
                <span class="text-sm sm:text-base font-black ${isToday ? 'text-blue-700' : 'text-slate-800'}">${d.getDate()}</span>
            </div>
        </th>`;
    });
    html += `</tr></thead><tbody class="divide-y divide-slate-100">`;

    sortedTimes.forEach(time => {
        html += `<tr class="group hover:bg-slate-50/50 transition-colors"><td class="p-2 border-r border-slate-100 align-top text-center bg-white group-hover:bg-slate-50">
            <span class="text-[10px] sm:text-xs font-bold text-slate-400">${time}</span>
        </td>`;
        weekDates.forEach(d => {
            const dateStr = getISODateStr(d);
            const slotLessons = gridData[dateStr]?.[time] ||[];
            const isToday = isSameDay(d, new Date());
            html += `<td class="p-1 border-r border-slate-100 last:border-r-0 align-top ${isToday ? 'bg-blue-50/10' : ''}">
                <div class="flex flex-col gap-1 h-full">
                    ${slotLessons.map(l => renderDesktopCard(l)).join('')}
                </div>
            </td>`;
        });
        html += `</tr>`;
    });
    html += `</tbody></table></div>`;
    container.innerHTML = html;
}

function renderDesktopCard(l) {
    const color = getBadgeColor(l.kindOfWork);
    const teacherTokens = (l.lecturer_title || '').split(' ');
    const teacherShort = teacherTokens.length > 2 ? `${teacherTokens[0]} ${teacherTokens[1][0]}.${teacherTokens[2][0]}.` : l.lecturer_title;

    // Сверхкомпактная карточка, текст обрезается (truncate / line-clamp) если не влезает
    return `
    <div class="p-1.5 rounded-lg border ${color.border} ${color.bg} shadow-sm overflow-hidden flex flex-col h-full min-h-[70px]">
        <div class="flex justify-between items-start gap-1 mb-0.5">
            <div class="text-[8px] font-bold uppercase tracking-wider ${color.text} truncate" title="${l.kindOfWork}">${l.kindOfWork}</div>
            ${l.module ? `<span class="px-1 py-0.5 rounded text-[7px] font-bold bg-white text-slate-600 truncate max-w-[40px] border border-slate-100" title="${l.module}">${l.module}</span>` : ''}
        </div>
        <div class="font-bold text-slate-800 text-[10px] sm:text-[11px] leading-tight mb-1 line-clamp-3 flex-grow" title="${l.discipline_display}">${l.discipline_display}</div>
        
        <div class="text-[9px] text-slate-600 flex items-center gap-0.5 truncate" title="${l.auditorium}">
            <svg class="w-2.5 h-2.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z"></path><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 11a3 3 0 11-6 0 3 3 0 016 0z"></path></svg>
            <span class="truncate">${l.auditorium}</span>
        </div>
        ${teacherShort ? `
        <div class="text-[9px] text-slate-600 flex items-center gap-0.5 truncate mt-[2px]" title="${l.lecturer_title}">
            <svg class="w-2.5 h-2.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"></path></svg>
            <span class="truncate">${teacherShort}</span>
        </div>` : ''}
    </div>`;
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
        if(!byDate[normDate]) byDate[normDate] =[];
        byDate[normDate].push(l);
    });
    
    const sortedDates = Object.keys(byDate).sort();
    let html = '';
    
    sortedDates.forEach(dateStr => {
        const d = parseDate(dateStr);
        const isToday = isSameDay(d, new Date());
        
        html += `
        <div class="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
            <div class="bg-slate-50 px-4 py-2.5 border-b border-slate-100 flex items-center justify-between sticky top-16 z-10">
                <div class="font-bold text-slate-800 capitalize">${d.toLocaleDateString('ru', {weekday: 'long'})}</div>
                <div class="text-sm font-medium ${isToday ? 'text-blue-600 font-bold' : 'text-slate-500'}">${d.toLocaleDateString('ru', {day: 'numeric', month: 'long'})}</div>
            </div>
            <div class="p-3 flex flex-col gap-3">
                ${byDate[dateStr].sort((a,b) => a.beginLesson.localeCompare(b.beginLesson)).map(l => renderMobileCard(l)).join('')}
            </div>
        </div>`;
    });
    container.innerHTML = html;
}

function renderMobileCard(l) {
    const color = getBadgeColor(l.kindOfWork);
    return `
    <div class="flex gap-3">
        <div class="flex flex-col items-center w-12 shrink-0 pt-1">
            <span class="text-sm font-black text-slate-700">${l.beginLesson}</span>
            <span class="text-xs font-medium text-slate-400">${l.endLesson}</span>
        </div>
        <div class="flex-grow p-3 rounded-xl border ${color.border} ${color.bg} shadow-sm">
            <div class="flex justify-between items-start mb-1.5 gap-2">
                <span class="text-[10px] font-black uppercase tracking-wider ${color.text} opacity-80 leading-none mt-0.5">${l.kindOfWork}</span>
                ${l.module ? `<span class="px-1.5 py-0.5 rounded text-[9px] font-bold bg-white text-slate-600 truncate max-w-[100px] shadow-sm border border-slate-100">${l.module}</span>` : ''}
            </div>
            <h4 class="font-bold text-slate-800 text-sm leading-tight mb-2">${l.discipline_display}</h4>
            <div class="flex flex-col gap-1.5 mt-auto">
                <div class="flex items-center gap-1.5 text-xs font-medium text-slate-600">
                    <svg class="w-3.5 h-3.5 opacity-60 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z"></path><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 11a3 3 0 11-6 0 3 3 0 016 0z"></path></svg>
                    <span class="truncate">${l.auditorium}</span>
                </div>
                ${l.lecturer_title ? `
                <div class="flex items-center gap-1.5 text-xs font-medium text-slate-600">
                    <svg class="w-3.5 h-3.5 opacity-60 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"></path></svg>
                    <span class="truncate">${l.lecturer_title}</span>
                </div>` : ''}
            </div>
        </div>
    </div>`;
}

function getBadgeColor(kind) {
    if (!kind) return { bg: 'bg-slate-50', border: 'border-slate-200', text: 'text-slate-600' };
    const k = kind.toLowerCase();
    if (k.includes('лекц')) return { bg: 'bg-emerald-50/50', border: 'border-emerald-200', text: 'text-emerald-700' };
    if (k.includes('практ') || k.includes('семин')) return { bg: 'bg-amber-50/50', border: 'border-amber-200', text: 'text-amber-700' };
    if (k.includes('экзамен') || k.includes('зачет') || k.includes('аттест')) return { bg: 'bg-rose-50/50', border: 'border-rose-200', text: 'text-rose-700' };
    return { bg: 'bg-blue-50/50', border: 'border-blue-200', text: 'text-blue-700' };
}

function debounce(func, timeout = 300){
    let timer;
    return (...args) => { clearTimeout(timer); timer = setTimeout(() => { func.apply(this, args); }, timeout); };
}

function isSameDay(d1, d2) {
    return d1.getFullYear() === d2.getFullYear() && d1.getMonth() === d2.getMonth() && d1.getDate() === d2.getDate();
}