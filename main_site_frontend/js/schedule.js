const API_BASE = "https://api.ivantishchenko.ru/api";
let fullSchedule = [];
let selectedModules = new Set();

// 1. Поиск группы с задержкой (Debounce)
const groupInput = document.getElementById('groupSearch');
const resultsBox = document.getElementById('searchResults');

groupInput.addEventListener('input', debounce(async (e) => {
    const query = e.target.value;
    if (query.length < 2) {
        resultsBox.classList.add('hidden');
        return;
    }

    const res = await fetch(`${API_BASE}/schedule/search?term=${encodeURIComponent(query)}`);
    const data = await res.json();
    
    renderSearchResults(data);
}, 300));

function renderSearchResults(results) {
    resultsBox.innerHTML = results.map(item => `
        <div class="px-6 py-4 hover:bg-blue-50 cursor-pointer border-b border-slate-50 last:border-none" 
             onclick="loadSchedule('${item.id}', '${item.label}')">
            <span class="font-bold text-slate-800">${item.label}</span>
            <span class="text-xs text-slate-400 ml-2">${item.description || ''}</span>
        </div>
    `).join('');
    resultsBox.classList.remove('hidden');
}

// 2. Загрузка данных расписания
async function loadSchedule(id, name) {
    resultsBox.classList.add('hidden');
    groupInput.value = name;
    
    const res = await fetch(`${API_BASE}/schedule/data/group/${id}`);
    const data = await res.json();
    
    fullSchedule = data.schedule;
    selectedModules = new Set(data.available_modules); // По умолчанию выбраны все
    
    renderModuleFilters(data.available_modules);
    filterAndRender();
}

// 3. Отрисовка фильтров (Чипсы)
function renderModuleFilters(modules) {
    const container = document.getElementById('moduleContainer');
    const section = document.getElementById('moduleFilterSection');
    
    if (modules.length === 0) {
        section.classList.add('hidden');
        return;
    }
    
    section.classList.remove('hidden');
    container.innerHTML = modules.map(mod => `
        <button onclick="toggleModule('${mod}')" id="mod-${mod}" 
            class="px-4 py-2 rounded-full border text-sm font-medium transition-all shadow-sm
            ${selectedModules.has(mod) ? 'bg-blue-600 border-blue-600 text-white' : 'bg-white border-slate-200 text-slate-600'}">
            ${mod}
        </button>
    `).join('');
}

function toggleModule(mod) {
    if (selectedModules.has(mod)) selectedModules.delete(mod);
    else selectedModules.add(mod);
    
    renderModuleFilters(Array.from(new Set(fullSchedule.map(l => getModuleName(l.group)).filter(Boolean))));
    filterAndRender();
}

// Вспомогательные функции
function getModuleName(groupStr) {
    if (!groupStr) return null;
    const match = groupStr.match(/Модуль\s+["«](.+?)["»]/) || groupStr.match(/(\([А-Яа-яA-Za-z0-9_]+\)-\d+)/);
    return match ? match[1] : null;
}

function debounce(func, timeout = 300){
    let timer;
    return (...args) => {
        clearTimeout(timer);
        timer = setTimeout(() => { func.apply(this, args); }, timeout);
    };
}


const TIME_SLOTS = [
    "08:30", "10:10", "11:50", "14:00", "15:40", "17:20", "18:55", "20:30"
];

function filterAndRender() {
    const container = document.getElementById('scheduleGrid');
    container.innerHTML = ''; // Очищаем

    // 1. Группируем пары по дням и времени
    const gridData = {}; // { '2024-03-10': { '09:00': [lessons] } }

    fullSchedule.forEach(lesson => {
        const mod = lesson.module;
        // КОРРЕКТНАЯ ФИЛЬТРАЦИЯ: 
        // Если у пары есть модуль, показываем её только если он ВЫБРАН.
        // Если модуля нет - показываем ВСЕГДА.
        if (mod && !selectedModules.has(mod)) return;

        if (!gridData[lesson.date]) gridData[lesson.date] = {};
        if (!gridData[lesson.date][lesson.beginLesson]) gridData[lesson.date][lesson.beginLesson] = [];
        
        gridData[lesson.date][lesson.beginLesson].push(lesson);
    });

    // 2. Получаем список уникальных дат из расписания (сортируем)
    const sortedDates = Object.keys(gridData).sort();

    // 3. Строим HTML Таблицы
    let html = `
        <div class="overflow-x-auto rounded-3xl border border-slate-200 shadow-xl bg-white">
            <table class="w-full border-collapse min-w-[1000px]">
                <thead>
                    <tr class="bg-slate-50">
                        <th class="p-4 border-b border-r text-slate-400 font-bold text-xs uppercase w-20">Время</th>
                        ${sortedDates.map(dateStr => {
                            const d = new Date(dateStr);
                            return `
                                <th class="p-4 border-b border-r last:border-r-0">
                                    <div class="text-xs uppercase text-blue-600 font-black">${d.toLocaleDateString('ru', {weekday: 'short'})}</div>
                                    <div class="text-lg font-bold text-slate-900">${d.getDate()} ${d.toLocaleDateString('ru', {month: 'short'})}</div>
                                </th>
                            `;
                        }).join('')}
                    </tr>
                </thead>
                <tbody>
                    ${TIME_SLOTS.map(time => `
                        <tr>
                            <td class="p-4 border-b border-r bg-slate-50/50 align-top">
                                <span class="text-sm font-black text-slate-400">${time}</span>
                            </td>
                            ${sortedDates.map(dateStr => {
                                const lessons = gridData[dateStr][time] || [];
                                return `
                                    <td class="p-2 border-b border-r last:border-r-0 align-top transition-colors hover:bg-slate-50/30">
                                        ${lessons.map(l => renderLessonMiniCard(l)).join('')}
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

function renderLessonMiniCard(l) {
    const color = getBadgeColor(l.kindOfWork);
    return `
        <div class="lesson-entry p-3 rounded-2xl mb-2 last:mb-0 shadow-sm border-l-4 ${color.border} ${color.bg} group cursor-default">
            <div class="text-[10px] font-black uppercase opacity-50 mb-1">${l.kindOfWork}</div>
            <div class="font-bold text-slate-800 mb-1 leading-tight">${l.discipline_display}</div>
            <div class="flex items-center gap-1 text-[10px] text-slate-500">
                <span>📍 ${l.auditorium}</span>
                <span class="opacity-30">|</span>
                <span class="truncate italic">${l.lecturer_title.split(' ')[0]}</span>
            </div>
        </div>
    `;
}

// Расширенные цвета для таймлайна
function getBadgeColor(kind) {
    if (kind.includes('Лекц')) return { bg: 'bg-emerald-50', border: 'border-emerald-500', text: 'text-emerald-700' };
    if (kind.includes('Практ') || kind.includes('Семин')) return { bg: 'bg-amber-50', border: 'border-amber-400', text: 'text-amber-700' };
    if (kind.includes('Экзамен')) return { bg: 'bg-rose-50', border: 'border-rose-500', text: 'text-rose-700' };
    return { bg: 'bg-blue-50', border: 'border-blue-400', text: 'text-blue-700' };
}