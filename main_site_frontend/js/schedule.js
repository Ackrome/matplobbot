// js/schedule.js
const API_BASE = "https://api.ivantishchenko.ru/api";

// Глобальное состояние
let fullSchedule = [];
let allAvailableModules =[]; // Храним оригинальный список от админа/бэкенда!
let selectedModules = new Set();
let isOfflineMode = false;

// Элементы DOM
const groupInput = document.getElementById('groupSearch');
const resultsBox = document.getElementById('searchResults');
const searchContainer = document.getElementById('searchContainer');

// Закрытие поиска при клике вне его
document.addEventListener('click', (e) => {
    if (!searchContainer.contains(e.target)) {
        resultsBox.classList.add('hidden');
    }
});

// 1. Поиск (Debounce)
// 1. Поиск (Debounce)
groupInput.addEventListener('input', debounce(async (e) => {
    const query = e.target.value.trim();
    if (query.length < 2) {
        resultsBox.classList.add('hidden');
        return;
    }

    try {
        const res = await fetch(`${API_BASE}/schedule/search?term=${encodeURIComponent(query)}`);
        
        // Если сервер вернул 503 (ВУЗ лежит) или другую ошибку
        if (!res.ok) {
            let errorMsg = "Ошибка при поиске";
            try {
                const errData = await res.json();
                if (errData.detail) errorMsg = errData.detail;
            } catch (e) {} // Если сервер вернул не JSON
            
            resultsBox.innerHTML = `<div class="px-6 py-4 text-sm text-red-500 text-center font-medium">⚠️ ${errorMsg}</div>`;
            resultsBox.classList.remove('hidden');
            return;
        }

        const data = await res.json();
        renderSearchResults(data);
    } catch (err) {
        console.error("Search error", err);
        resultsBox.innerHTML = `<div class="px-6 py-4 text-sm text-red-500 text-center font-medium">❌ Ошибка сети. Проверьте подключение.</div>`;
        resultsBox.classList.remove('hidden');
    }
}, 300));

function renderSearchResults(results) {
    if (results.length === 0) {
        resultsBox.innerHTML = `<div class="px-6 py-4 text-sm text-slate-500 text-center">Ничего не найдено</div>`;
    } else {
        resultsBox.innerHTML = results.map(item => {
            // Если пришел флаг оффлайна - рисуем яркий бейджик!
            const offlineBadge = item.is_offline 
                ? `<span class="ml-2 px-2 py-0.5 rounded text-[10px] font-bold bg-orange-100 text-orange-600 border border-orange-200 shadow-sm">⚡ ОФФЛАЙН</span>` 
                : '';
                
            return `
            <div class="px-6 py-3 hover:bg-blue-50 cursor-pointer border-b border-slate-100 last:border-none transition-colors" 
                 onclick="loadSchedule('${item.type || 'group'}', '${item.id}', '${item.label.replace(/'/g, "\\'")}')">
                <div class="font-bold text-slate-800 flex items-center">${item.label} ${offlineBadge}</div>
                <div class="text-xs text-slate-400 mt-0.5">${item.description || (item.type === 'person' ? 'Преподаватель' : 'Группа')}</div>
            </div>
            `;
        }).join('');
    }
    resultsBox.classList.remove('hidden');
}

// 2. Загрузка данных
async function loadSchedule(type, id, name) {
    resultsBox.classList.add('hidden');
    groupInput.value = name;
    groupInput.blur(); // Убираем фокус с инпута
    
    document.getElementById('scheduleGrid').innerHTML = `
        <div class="flex justify-center items-center py-20 text-blue-500">
            <svg class="animate-spin h-10 w-10" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>
        </div>
    `;

    try {
        const res = await fetch(`${API_BASE}/schedule/data/${type}/${id}`);
        const data = await res.json();
        
        fullSchedule = data.schedule;
        allAvailableModules = data.available_modules ||[]; 
        selectedModules = new Set(allAvailableModules);
        
        isOfflineMode = data.is_offline || false; 
        
        renderModuleFilters();
        filterAndRender();
    } catch (err) {
        console.error("Load error", err);
        document.getElementById('scheduleGrid').innerHTML = `<div class="text-center text-red-500 py-10 font-medium">Ошибка загрузки расписания.</div>`;
    }
}

// 3. Управление фильтрами (Модули)
function renderModuleFilters() {
    const container = document.getElementById('moduleContainer');
    const section = document.getElementById('moduleFilterSection');
    
    if (allAvailableModules.length === 0) {
        section.classList.add('hidden');
        return;
    }
    
    section.classList.remove('hidden');
    
    // Рендерим кнопки на основе глобального allAvailableModules!
    container.innerHTML = allAvailableModules.map(mod => `
        <button onclick="toggleModule('${mod}')" 
            class="px-4 py-2 rounded-xl border text-sm font-bold transition-all duration-200 
            ${selectedModules.has(mod) 
                ? 'bg-slate-800 border-slate-800 text-white shadow-md transform scale-100' 
                : 'bg-white border-slate-200 text-slate-400 hover:border-slate-300 hover:text-slate-600 transform scale-95'}">
            ${selectedModules.has(mod) ? '✓ ' : ''}${mod}
        </button>
    `).join('');
}

function toggleModule(mod) {
    if (selectedModules.has(mod)) selectedModules.delete(mod);
    else selectedModules.add(mod);
    
    renderModuleFilters(); // Вызываем просто так, без передачи пересчитанных аргументов!
    filterAndRender();
}

function selectAllModules() {
    selectedModules = new Set(allAvailableModules);
    renderModuleFilters();
    filterAndRender();
}

function clearAllModules() {
    selectedModules.clear();
    renderModuleFilters();
    filterAndRender();
}

// 4. Отрисовка расписания (Новая крутая сетка)
function filterAndRender() {
    const container = document.getElementById('scheduleGrid');
    
    const filteredLessons = fullSchedule.filter(lesson => {
        const mod = lesson.module;
        if (mod && !selectedModules.has(mod)) return false;
        return true;
    });

    let html = ''; // Начинаем собирать HTML

    // Плашка предупреждения, если расписание из кэша:
    if (isOfflineMode) {
        html += `
        <div class="mb-6 p-4 bg-orange-50 border border-orange-200 rounded-2xl flex items-start sm:items-center gap-3 text-orange-800 shadow-sm fade-in">
            <svg class="w-6 h-6 shrink-0 mt-0.5 sm:mt-0 text-orange-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"></path></svg>
            <div>
                <strong class="block text-sm sm:text-base">ВУЗ недоступен. Показана сохраненная копия расписания.</strong>
                <span class="text-xs sm:text-sm opacity-90 block mt-0.5">Данные могут быть не самыми свежими. Как только сервера ВУЗа поднимутся, мы автоматически обновим информацию.</span>
            </div>
        </div>`;
    }

    if (filteredLessons.length === 0) {
        html += `
            <div class="text-center py-20 bg-white rounded-3xl border border-slate-200 shadow-sm">
                <p class="text-slate-500 font-medium">Нет занятий с выбранными фильтрами.</p>
            </div>`;
        container.innerHTML = html;
        return;
    }

    // Собираем уникальные ДАТЫ и ВРЕМЕННЫЕ СЛОТЫ
    const datesSet = new Set();
    const timesSet = new Set();
    const gridData = {};  // { 'date': { 'time': [lessons] } }

    filteredLessons.forEach(l => {
        datesSet.add(l.date);
        timesSet.add(l.beginLesson);
        
        if (!gridData[l.date]) gridData[l.date] = {};
        if (!gridData[l.date][l.beginLesson]) gridData[l.date][l.beginLesson] = [];
        gridData[l.date][l.beginLesson].push(l);
    });

    const sortedDates = Array.from(datesSet).sort();
    const sortedTimes = Array.from(timesSet).sort(); // Динамическая шкала времени!

    // Узнаем "Сегодня" для подсветки колонки
    const todayStr = new Date().toLocaleDateString('ru-RU').split('.').reverse().join('-'); 
    // RUZ API отдает yyyy.mm.dd, поэтому нужна адаптация (если у вас YYYY-MM-DD, оставляем как есть)

    // Строим HTML
    html += `
        <div class="bg-white rounded-3xl border border-slate-200 shadow-xl overflow-hidden custom-scrollbar overflow-x-auto relative">
            <table class="w-full border-collapse text-left min-w-[800px]">
                <thead class="bg-slate-50/80 backdrop-blur-md sticky top-0 z-20 shadow-sm">
                    <tr>
                        <th class="p-4 border-b border-slate-200 w-24 sticky left-0 z-30 bg-slate-50/90 backdrop-blur-md"></th>
                        ${sortedDates.map(dateStr => {
                            const d = new Date(dateStr.replace(/\./g, '-')); // Поддержка формата YYYY.MM.DD и YYYY-MM-DD
                            const isToday = isSameDay(d, new Date());
                            const dayName = d.toLocaleDateString('ru', {weekday: 'short'});
                            const dayNum = d.getDate();
                            
                            return `
                                <th class="p-4 border-b border-l border-slate-200 min-w-[220px] ${isToday ? 'bg-blue-50/50' : ''}">
                                    <div class="flex flex-col items-center">
                                        <span class="text-xs font-bold uppercase tracking-widest ${isToday ? 'text-blue-600' : 'text-slate-400'}">${dayName}</span>
                                        <span class="text-2xl font-black ${isToday ? 'text-blue-700' : 'text-slate-800'}">${dayNum}</span>
                                    </div>
                                </th>
                            `;
                        }).join('')}
                    </tr>
                </thead>
                <tbody class="divide-y divide-slate-100">
                    ${sortedTimes.map(time => `
                        <tr class="group">
                            <td class="p-4 border-slate-100 align-top sticky left-0 z-10 bg-white group-hover:bg-slate-50 transition-colors">
                                <div class="text-sm font-black text-slate-400 text-center">${time}</div>
                            </td>
                            ${sortedDates.map(dateStr => {
                                const d = new Date(dateStr.replace(/\./g, '-'));
                                const isToday = isSameDay(d, new Date());
                                const lessons = gridData[dateStr][time] ||[];
                                
                                return `
                                    <td class="p-3 border-l border-slate-100 align-top ${isToday ? 'bg-blue-50/10' : ''} hover:bg-slate-50 transition-colors">
                                        <div class="flex flex-col gap-2 h-full">
                                            ${lessons.map(l => renderLessonCard(l)).join('')}
                                        </div>
                                    </td>
                                `;
                            }).join('')}
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        </div>
    `;

    container.innerHTML = html;
}

function renderLessonCard(l) {
    const color = getBadgeColor(l.kindOfWork);
    // Обрезаем ФИО преподавателя до фамилии и инициалов, если строка слишком длинная
    const teacherTokens = (l.lecturer_title || '').split(' ');
    const teacherShort = teacherTokens.length > 2 ? `${teacherTokens[0]} ${teacherTokens[1][0]}.${teacherTokens[2][0]}.` : l.lecturer_title;

    return `
        <div class="relative p-3.5 rounded-2xl border ${color.border} ${color.bg} shadow-sm transition-transform hover:-translate-y-0.5 hover:shadow-md cursor-default">
            <div class="flex justify-between items-start mb-2 gap-2">
                <span class="text-[10px] font-black uppercase tracking-wider ${color.text} opacity-80 leading-none">${l.kindOfWork}</span>
                ${l.module ? `<span class="px-1.5 py-0.5 rounded text-[9px] font-bold bg-white/60 text-slate-600 truncate max-w-[80px]" title="${l.module}">${l.module}</span>` : ''}
            </div>
            
            <h4 class="font-bold text-slate-800 text-sm leading-tight mb-3 line-clamp-3" title="${l.discipline_display}">
                ${l.discipline_display}
            </h4>
            
            <div class="flex flex-col gap-1 mt-auto">
                <div class="flex items-center gap-1.5 text-xs font-medium text-slate-600">
                    <svg class="w-3.5 h-3.5 opacity-60" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z"></path><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 11a3 3 0 11-6 0 3 3 0 016 0z"></path></svg>
                    <span class="truncate">${l.auditorium}</span>
                </div>
                ${teacherShort ? `
                <div class="flex items-center gap-1.5 text-xs font-medium text-slate-600">
                    <svg class="w-3.5 h-3.5 opacity-60" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"></path></svg>
                    <span class="truncate" title="${l.lecturer_title}">${teacherShort}</span>
                </div>` : ''}
            </div>
        </div>
    `;
}

// Улучшенная палитра для типов пар (Tailwind цвета)
function getBadgeColor(kind) {
    if (!kind) return { bg: 'bg-slate-50', border: 'border-slate-200', text: 'text-slate-600' };
    const k = kind.toLowerCase();
    
    if (k.includes('лекц')) return { bg: 'bg-emerald-50/50', border: 'border-emerald-200', text: 'text-emerald-700' };
    if (k.includes('практ') || k.includes('семин')) return { bg: 'bg-amber-50/50', border: 'border-amber-200', text: 'text-amber-700' };
    if (k.includes('экзамен') || k.includes('зачет') || k.includes('аттест')) return { bg: 'bg-rose-50/50', border: 'border-rose-200', text: 'text-rose-700' };
    
    return { bg: 'bg-blue-50/50', border: 'border-blue-200', text: 'text-blue-700' };
}

// Вспомогательные функции
function debounce(func, timeout = 300){
    let timer;
    return (...args) => {
        clearTimeout(timer);
        timer = setTimeout(() => { func.apply(this, args); }, timeout);
    };
}

function isSameDay(d1, d2) {
    return d1.getFullYear() === d2.getFullYear() &&
           d1.getMonth() === d2.getMonth() &&
           d1.getDate() === d2.getDate();
}