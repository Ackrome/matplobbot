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

// 4. Фильтрация и рендер карточек
function filterAndRender() {
    const grid = document.getElementById('scheduleGrid');
    
    const filtered = fullSchedule.filter(lesson => {
        const mod = getModuleName(lesson.group);
        // Показываем если: это общая пара (нет модуля) ИЛИ модуль выбран
        return !mod || selectedModules.has(mod);
    });

    grid.innerHTML = filtered.map(lesson => `
        <div class="bg-white p-6 rounded-3xl shadow-sm border border-slate-100 hover:shadow-md transition-all">
            <div class="flex justify-between items-start mb-4">
                <span class="text-xs font-bold px-3 py-1 rounded-full ${getBadgeColor(lesson.kindOfWork)}">
                    ${lesson.kindOfWork}
                </span>
                <span class="text-sm font-mono text-slate-400">${lesson.beginLesson} - ${lesson.endLesson}</span>
            </div>
            <h3 class="font-bold text-slate-900 mb-2 leading-tight">${lesson.discipline}</h3>
            <p class="text-sm text-slate-500 mb-4 flex items-center gap-2">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z"/><path d="M15 11a3 3 0 11-6 0 3 3 0 016 0z"/></svg>
                ${lesson.auditorium}
            </p>
            <div class="pt-4 border-t border-slate-50 flex items-center gap-3">
                <div class="w-8 h-8 rounded-full bg-slate-100 flex items-center justify-center text-[10px] font-bold text-slate-400 uppercase">
                    ${lesson.lecturer_title.split(' ').map(n => n[0]).join('')}
                </div>
                <span class="text-xs text-slate-600 font-medium">${lesson.lecturer_title}</span>
            </div>
        </div>
    `).join('');
}

// Вспомогательные функции
function getModuleName(groupStr) {
    if (!groupStr) return null;
    const match = groupStr.match(/Модуль\s+["«](.+?)["»]/) || groupStr.match(/(\([А-Яа-яA-Za-z0-9_]+\)-\d+)/);
    return match ? match[1] : null;
}

function getBadgeColor(kind) {
    if (kind.includes('Лекц')) return 'bg-green-100 text-green-700';
    if (kind.includes('Практ') || kind.includes('Семин')) return 'bg-yellow-100 text-yellow-700';
    if (kind.includes('Экзамен')) return 'bg-red-100 text-red-700';
    return 'bg-blue-100 text-blue-700';
}

function debounce(func, timeout = 300){
    let timer;
    return (...args) => {
        clearTimeout(timer);
        timer = setTimeout(() => { func.apply(this, args); }, timeout);
    };
}