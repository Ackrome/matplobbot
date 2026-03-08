// js/stats.js
const API_URL = "https://api.ivantishchenko.ru/api";
const token = localStorage.getItem('jwt_token');

function logout() {
    localStorage.removeItem('jwt_token');
    window.location.href = '/login';
}

async function fetchWithAuth(endpoint) {
    const response = await fetch(`${API_URL}${endpoint}`, {
        headers: { 'Authorization': `Bearer ${token}` }
    });
    if (response.status === 401) logout();
    return response.json();
}

async function loadDashboard() {
    try {
        // Загружаем данные параллельно
        const [leaderboard, activity] = await Promise.all([
            fetchWithAuth("/stats/leaderboard"),
            fetchWithAuth("/stats/activity")
        ]);

        // 1. KPI
        const total = leaderboard.reduce((sum, u) => sum + u.actions_count, 0);
        document.getElementById('totalActions').innerText = total.toLocaleString();

        // 2. Таблица лидеров
        const tbody = document.getElementById('leaderboardBody');
        tbody.innerHTML = leaderboard.slice(0, 10).map((user, index) => `
            <tr class="border-b border-slate-50 last:border-none group hover:bg-slate-50 transition-colors">
                <td class="py-4 flex items-center gap-3">
                    <span class="text-xs font-bold text-slate-300 w-4">${index + 1}</span>
                    <div class="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-500 to-indigo-600 text-white flex items-center justify-center font-bold shadow-sm">
                        ${user.full_name[0]}
                    </div>
                    <div>
                        <div class="font-bold text-slate-800">${user.full_name}</div>
                        <div class="text-[10px] text-slate-400 uppercase tracking-tighter">${user.username || 'no username'}</div>
                    </div>
                </td>
                <td class="py-4 text-right font-mono font-black text-blue-600">${user.actions_count}</td>
            </tr>
        `).join('');

        // 3. График активности (Chart.js)
        const ctx = document.getElementById('activityChart').getContext('2d');
        new Chart(ctx, {
            type: 'line',
            data: {
                labels: activity.map(d => d.period_start),
                datasets: [{
                    label: 'Действия',
                    data: activity.map(d => d.actions_count),
                    borderColor: '#2563eb',
                    backgroundColor: 'rgba(37, 99, 235, 0.1)',
                    fill: true,
                    tension: 0.4,
                    borderWidth: 3,
                    pointRadius: 0
                }]
            },
            options: {
                plugins: { legend: { display: false } },
                scales: {
                    y: { beginAtZero: true, grid: { display: false } },
                    x: { grid: { display: false } }
                }
            }
        });

    } catch (err) {
        console.error("Dashboard error:", err);
    }
}

loadDashboard();