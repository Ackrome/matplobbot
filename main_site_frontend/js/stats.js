const API_URL = "https://api.ivantishchenko.ru/api";
const token = localStorage.getItem('jwt_token');

// Функция для выхода
function logout() {
    localStorage.removeItem('jwt_token');
    window.location.href = '/login';
}

// Универсальная функция запроса к API с токеном
async function fetchWithAuth(endpoint) {
    const response = await fetch(`${API_URL}${endpoint}`, {
        headers: {
            'Authorization': `Bearer ${token}`
        }
    });
    
    if (response.status === 401) {
        logout(); // Если токен протух — на выход
    }
    return response.json();
}

async function loadDashboard() {
    try {
        // 1. Загружаем таблицу лидеров (она содержит и общее кол-во действий)
        const leaderboard = await fetchWithAuth("/stats/leaderboard"); // Предполагаем такой эндпоинт
        
        // Отрисовка KPI
        const total = leaderboard.reduce((sum, u) => sum + u.actions_count, 0);
        document.getElementById('totalActions').innerText = total.toLocaleString();

        // Отрисовка таблицы
        const tbody = document.getElementById('leaderboardBody');
        tbody.innerHTML = leaderboard.slice(0, 10).map(user => `
            <tr class="border-b border-slate-50 last:border-none">
                <td class="py-4 flex items-center gap-3">
                    <div class="w-8 h-8 rounded-full bg-blue-50 text-blue-600 flex items-center justify-center font-bold text-xs">
                        ${user.full_name[0]}
                    </div>
                    <span class="font-semibold text-slate-800">${user.full_name}</span>
                </td>
                <td class="py-4 text-right font-mono font-bold text-blue-600">${user.actions_count}</td>
            </tr>
        `).join('');

    } catch (err) {
        console.error("Ошибка загрузки данных:", err);
    }
}

loadDashboard();