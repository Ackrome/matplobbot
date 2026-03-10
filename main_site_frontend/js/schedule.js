// js/schedule.js
const API_BASE = "https://api.ivantishchenko.ru/api";
const STORAGE_KEY = "mpb_user_preferences";

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



// Обновляем загрузку списка (теперь кнопки внутри Dropdown)
// [INIT] Автозагрузка при старте страницы
document.addEventListener('DOMContentLoaded', async () => {
    // 1. Загружаем список "Истории" (Оффлайн кэш)
    await initOfflineHistory(); 
    
    // 2. Восстанавливаем настройки из localStorage
    const savedPrefs = localStorage.getItem(STORAGE_KEY);
    if (savedPrefs) {
        try {
            const prefs = JSON.parse(savedPrefs);
            console.log("Восстановление настроек:", prefs);
            
            // Восстанавливаем чекбокс
            if (prefs.useShortNames !== undefined) {
                document.getElementById('useShortNames').checked = prefs.useShortNames;
            }
            
            // Если была выбрана группа/препод — загружаем
            if (prefs.entity && prefs.entity.id) {
                // ПРЕДЗАГРУЗКА выбранных модулей из памяти
                if (prefs.modules && prefs.modules.length > 0) {
                    selectedModules = new Set(prefs.modules);
                }
                
                // Вызываем загрузку
                await loadSchedule(prefs.entity.type, prefs.entity.id, prefs.entity.name);
            }
        } catch (e) {
            console.error("Ошибка при чтении localStorage:", e);
        }
    }
});

// Выносим загрузку истории в отдельную функцию, чтобы не ломать основной поток
async function initOfflineHistory() {
    try {
        const res = await fetch(`${API_BASE}/schedule/cached_list`);
        if (res.ok) {
            const list = await res.json();
            const container = document.getElementById('cachedEntitiesList');
            if (list.length === 0) {
                container.innerHTML = `<div class="p-6 text-center text-xs text-slate-400 italic">История пуста</div>`;
                return;
            }
            container.innerHTML = list.map(item => `
                <button onclick="loadSchedule('${item.type}', '${item.id}', '${item.label}'); closeOfflinePanel();" 
                        class="group w-full text-left px-4 py-3 bg-white hover:bg-blue-50 rounded-xl transition-all flex items-center justify-between border border-transparent hover:border-blue-100">
                    <div>
                        <div class="text-xs font-black text-slate-700 group-hover:text-blue-700">${item.label}</div>
                        <div class="text-[9px] text-slate-400 uppercase tracking-tighter mt-0.5">Сохранено локально</div>
                    </div>
                    <svg class="w-3 h-3 text-slate-300 group-hover:text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M9 5l7 7-7 7" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg>
                </button>
            `).join('');
        }
    } catch (e) {
        console.warn("Не удалось загрузить список кэша:", e);
    }
}

function savePreferences() {
    const prefs = {
        entity: currentEntity,
        modules: Array.from(selectedModules), // Set в Array для JSON
        useShortNames: document.getElementById('useShortNames').checked
    };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs));
}

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

async function loadSchedule(type, id, name, targetDate = null) {
    resultsBox.classList.add('hidden');
    groupInput.value = name;
    currentEntity = { type, id, name };
    
    document.getElementById('defaultState').classList.add('hidden');
    document.getElementById('scheduleControls').classList.remove('hidden'); // Показываем блок управления
    
    // Скелетон на всю ширину внутри блока
    document.getElementById('desktopSchedule').innerHTML = `<div class="p-8"><div class="skeleton h-64 w-full rounded-3xl"></div></div>`;
    document.getElementById('mobileSchedule').innerHTML = `<div class="skeleton h-64 w-full rounded-3xl"></div>`;

    let url = `${API_BASE}/schedule/data/${type}/${id}`;
    if (targetDate) url += `?base_date=${targetDate}`;
    
    // [SAVE] Сохраняем сущность при загрузке
    savePreferences();

    try {
        const res = await fetch(url);
        const data = await res.json();
        
        fullSchedule = data.schedule || [];
        allAvailableModules = data.available_modules || []; 
        loadedBounds = data.loaded_bounds || {start: "2000-01-01", end: "2099-01-01"};
        
        // [MODIFIED] Модули сбрасываем, только если их НЕТ в памяти (первый заход)
        if (!targetDate && selectedModules.size === 0) {
            selectedModules = new Set(allAvailableModules);
        }
        
        if (!targetDate) currentWeekStart = getMonday(new Date()); 
        
        isOfflineMode = data.is_offline || false; 
        
        renderModuleFilters();
        filterAndRender();

    } catch (err) {
        document.getElementById('desktopSchedule').innerHTML = `<div class="p-10 text-center text-red-500 font-bold">Ошибка загрузки.</div>`;
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
    savePreferences(); // Сохраняем выбор модулей
}

function selectAllModules() { 
    selectedModules = new Set(allAvailableModules); 
    renderModuleFilters(); 
    filterAndRender(); 
    savePreferences(); // Сохраняем
}

function clearAllModules() { 
    selectedModules.clear(); 
    renderModuleFilters(); 
    filterAndRender(); 
    savePreferences(); // Сохраняем
}

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
    <div class="overflow-hidden relative"> <!-- Убрали лишние скругления и бордеры здесь -->
        <table class="w-full table-fixed border-collapse text-left">
            <thead class="bg-slate-50/50 border-b border-slate-100">
                <tr>
                    <th class="w-16 sm:w-20 p-3 text-center text-xs font-bold text-slate-400 border-r border-slate-200">Время</th>`;
                    
    weekDates.forEach(d => {
        const isToday = isSameDay(d, now);
        html += `<th class="p-3 border-r border-slate-200 last:border-r-0 ${isToday ? 'bg-blue-50/70' : ''} relative">
            ${isToday ? '<div class="absolute top-0 left-0 w-full h-1 bg-blue-500"></div>' : ''}
            <div class="flex flex-col items-center gap-0.5">
                <!-- УВЕЛИЧЕН ШРИФТ И КОНТРАСТ ЗДЕСЬ -->
                <span class="text-xs uppercase tracking-widest font-bold ${isToday ? 'text-blue-600' : 'text-slate-500'}">${d.toLocaleDateString('ru', {weekday: 'short'})}</span>
                <span class="text-xl font-black ${isToday ? 'text-blue-700' : 'text-slate-800'}">${d.getDate()}</span>
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
        container.innerHTML = `<div class="text-center py-10 text-slate-400 text-sm">Нет занятий на этой неделе.</div>`;
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
        
        // Ключевое изменение: Белый фон и высокая плотность
        html += `
        <div class="relative">
            <div class="sticky top-[56px] md:top-[64px] z-20 bg-white px-4 py-3 border-b border-slate-100 flex items-center justify-between">
                <div class="font-black text-slate-800 capitalize">${d.toLocaleDateString('ru', {weekday: 'long'})}</div>
                <div class="text-xs font-bold ${isToday ? 'text-blue-600' : 'text-slate-400'}">${d.toLocaleDateString('ru', {day: 'numeric', month: 'long'})}</div>
            </div>
            
            <div class="flex flex-col divide-y divide-slate-50">
                ${byDate[dateStr].sort((a,b) => a.beginLesson.localeCompare(b.beginLesson)).map(l => renderCard(l, false)).join('')}
            </div>
        </div>`;
    });
    container.innerHTML = html;
}

/**
 * Рендерит карточку занятия.
 * @param {Object} l - Объект занятия из API.
 * @param {Boolean} isDesktop - Флаг: true для сетки ПК, false для ленты мобильных.
 */
function renderCard(l, isDesktop) {
    const color = getBadgeColor(l.kindOfWork);
    
    // 1. Логика интерактивных сокращений
    const useShort = document.getElementById('useShortNames').checked;
    const discName = useShort ? l.discipline_short : l.discipline_full;
    
    // 2. Дизайн для ПК (Сетка)
    if (isDesktop) {
        // Сокращаем ФИО преподавателя только для ПК-версии (Фамилия И.И.)
        const teacherTokens = (l.lecturer_title || '').split(' ');
        const teacherShort = teacherTokens.length > 2 
            ? `${teacherTokens[0]} ${teacherTokens[1][0]}.${teacherTokens[2][0]}.` 
            : l.lecturer_title;

        return `
        <div class="p-2.5 sm:p-3 rounded-2xl border ${color.border} ${color.bg} shadow-sm transition-transform hover:-translate-y-0.5 hover:shadow-md flex flex-col h-full min-h-[110px]">
            <!-- Верхняя строка: Тип пары + Модуль -->
            <div class="flex justify-between items-start gap-1 mb-1.5">
                <div class="text-[9px] font-black uppercase tracking-wider ${color.text} truncate" title="${l.kindOfWork}">
                    ${l.kindOfWork}
                </div>
                ${l.module ? `
                    <span class="px-1.5 py-0.5 rounded text-[8px] font-bold bg-white text-slate-600 truncate max-w-[60px] border border-slate-100 shadow-sm" title="${l.module}">
                        ${l.module}
                    </span>` : ''}
            </div>
            
            <!-- Название дисциплины (Line-clamp ограничивает до 3 строк) -->
            <div class="font-bold text-slate-800 text-[13px] leading-snug line-clamp-3 mb-2 flex-grow" title="${discName}">
                ${discName}
            </div>
            
            <!-- Инфо: Аудитория и Преподаватель -->
            <div class="flex flex-col gap-1">
                <div class="flex items-center gap-1 text-[10px] font-medium text-slate-600 hover:text-blue-600 cursor-pointer transition-colors" 
                     onclick="copyToClipboard('${l.auditorium}', event)" title="Копировать аудиторию">
                    <svg class="w-3 h-3 shrink-0 opacity-50" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z"></path><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 11a3 3 0 11-6 0 3 3 0 016 0z"></path></svg>
                    <span class="truncate">${l.auditorium}</span>
                </div>
                ${teacherShort ? `
                <div class="flex items-center gap-1 text-[10px] font-medium text-slate-600 hover:text-blue-600 cursor-pointer transition-colors" 
                     onclick="copyToClipboard('${l.lecturer_title}', event)" title="Копировать ФИО">
                    <svg class="w-3 h-3 shrink-0 opacity-50" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"></path></svg>
                    <span class="truncate">${teacherShort}</span>
                </div>` : ''}
            </div>
        </div>`;
    }

    // 3. Дизайн для МОБИЛЬНЫХ (Лента)
    // Убираем прозрачность бейджей для лучшей читаемости на телефоне
    const mobileBadgeBg = color.bg.includes('/') ? color.bg.split('/')[0] : color.bg;

    return `
    <div class="p-4 bg-white hover:bg-slate-50 transition-colors flex flex-col gap-2">
        <!-- Верхняя строка: Время + Бейдж типа пары -->
        <div class="flex items-center justify-between gap-2">
            <div class="flex items-center gap-2">
                <span class="font-black text-sm text-slate-900">${l.beginLesson}</span>
                <span class="text-[10px] font-bold text-slate-300 line-through decoration-slate-200">${l.endLesson}</span>
            </div>
            <span class="px-2 py-0.5 rounded-md text-[9px] font-black uppercase tracking-wider ${color.text} ${mobileBadgeBg} border ${color.border}">
                ${l.kindOfWork}
            </span>
        </div>

        <!-- Тело: Название + Тег модуля -->
        <div>
            <div class="font-bold text-slate-900 text-sm leading-snug mb-1">${discName}</div>
            ${l.module ? `
                <span class="inline-block px-1.5 py-0.5 rounded text-[9px] font-bold bg-slate-100 text-slate-500 border border-slate-200">
                    ${l.module}
                </span>` : ''}
        </div>

        <!-- Подвал: Аудитория и Преподаватель в две колонки -->
        <div class="grid grid-cols-2 gap-2 mt-1">
            <div class="flex items-center gap-1.5 text-[11px] font-medium text-slate-500 truncate cursor-pointer active:text-blue-600" 
                 onclick="copyToClipboard('${l.auditorium}', event)">
                <svg class="w-3.5 h-3.5 opacity-40 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z"></path><path d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" stroke-width="2"></path></svg>
                <span class="truncate">${l.auditorium}</span>
            </div>
            <div class="flex items-center gap-1.5 text-[11px] font-medium text-slate-500 truncate cursor-pointer active:text-blue-600" 
                 onclick="copyToClipboard('${l.lecturer_title}', event)">
                <svg class="w-3.5 h-3.5 opacity-40 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" stroke-width="2"></path></svg>
                <span class="truncate">${l.lecturer_title}</span>
            </div>
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

// УПРАВЛЕНИЕ ПАНЕЛЬЮ ОФФЛАЙН
function toggleOfflinePanel(event) {
    if (event) event.stopPropagation();
    const dropdown = document.getElementById('offlineDropdown');
    const arrow = document.getElementById('offlineArrow');
    const isHidden = dropdown.classList.contains('hidden');

    if (isHidden) {
        // Открываем
        dropdown.classList.remove('hidden');
        setTimeout(() => {
            dropdown.classList.remove('opacity-0', 'translate-y-2');
            dropdown.classList.add('opacity-100', 'translate-y-0');
        }, 10);
        arrow.classList.add('rotate-180');
    } else {
        // Закрываем
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


// Добавляем закрытие при клике снаружи в общий обработчик
document.addEventListener('click', (e) => {
    // Для поиска (уже было)
    if (!searchContainer.contains(e.target)) resultsBox.classList.add('hidden');
    
    // ДЛЯ ИСТОРИИ
    const offlineContainer = document.getElementById('offlinePanelContainer');
    if (offlineContainer && !offlineContainer.contains(e.target)) {
        closeOfflinePanel();
    }
});

// Добавляем функцию для мобильных фильтров
function toggleFiltersMobile() {
    const content = document.getElementById('filterContent');
    const arrow = document.getElementById('filterArrow');
    const isHidden = content.classList.contains('hidden');
    
    if (isHidden) {
        content.classList.remove('hidden');
        arrow.classList.add('rotate-180');
    } else {
        content.classList.add('hidden');
        arrow.classList.remove('rotate-180');
    }
}