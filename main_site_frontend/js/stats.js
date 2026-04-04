// js/stats.js
const API_BASE = "https://api.ivantishchenko.ru/api";
const token = localStorage.getItem("jwt_token");

function renderDashboardError(message) {
    const totalEl = document.getElementById("totalActions");
    const tbody = document.getElementById("leaderboardBody");
    const chartCanvas = document.getElementById("activityChart");

    if (totalEl) totalEl.innerText = "-";

    if (tbody) {
        tbody.innerHTML = `
            <tr>
                <td colspan="2" class="py-6 text-sm text-red-500">${message}</td>
            </tr>
        `;
    }

    if (chartCanvas && chartCanvas.parentElement) {
        const existing = chartCanvas.parentElement.querySelector(".dashboard-error");
        if (!existing) {
            const p = document.createElement("p");
            p.className = "dashboard-error mt-4 text-sm text-red-500";
            p.textContent = message;
            chartCanvas.parentElement.appendChild(p);
        }
    }
}

async function fetchWithAuth(endpoint) {
    const response = await fetch(`${API_BASE}${endpoint}`, {
        headers: { Authorization: `Bearer ${token}` },
    });

    if (response.status === 401) {
        window.performLogout();
        throw new Error("Session expired");
    }

    let data = null;
    try {
        data = await response.json();
    } catch {
        data = null;
    }

    if (!response.ok) {
        const detail = data && data.detail ? data.detail : `Request failed (${response.status})`;
        throw new Error(detail);
    }

    return data;
}

async function loadDashboard() {
    try {
        const [leaderboard, activity] = await Promise.all([
            fetchWithAuth("/stats/leaderboard"),
            fetchWithAuth("/stats/activity"),
        ]);

        if (!Array.isArray(leaderboard)) {
            throw new Error("Leaderboard response has invalid format.");
        }
        if (!Array.isArray(activity)) {
            throw new Error("Activity response has invalid format.");
        }

        const total = leaderboard.reduce((sum, user) => sum + (user.actions_count || 0), 0);
        const totalEl = document.getElementById("totalActions");
        if (totalEl) totalEl.innerText = total.toLocaleString();

        const tbody = document.getElementById("leaderboardBody");
        if (tbody) {
            if (leaderboard.length === 0) {
                tbody.innerHTML = `
                    <tr>
                        <td colspan="2" class="py-6 text-sm text-slate-500">No leaderboard data yet.</td>
                    </tr>
                `;
            } else {
                tbody.innerHTML = leaderboard
                    .slice(0, 10)
                    .map((user, index) => {
                        const fullName = (user.full_name || "Unknown User").trim();
                        const initial = fullName.length > 0 ? fullName[0].toUpperCase() : "?";
                        const username = user.username || "no username";

                        return `
                            <tr class="border-b border-slate-50 last:border-none group hover:bg-slate-50 transition-colors">
                                <td class="py-4 flex items-center gap-3">
                                    <span class="text-xs font-bold text-slate-300 w-4">${index + 1}</span>
                                    <div class="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-500 to-indigo-600 text-white flex items-center justify-center font-bold shadow-sm">
                                        ${initial}
                                    </div>
                                    <div>
                                        <div class="font-bold text-slate-800">${fullName}</div>
                                        <div class="text-[10px] text-slate-400 uppercase tracking-tighter">${username}</div>
                                    </div>
                                </td>
                                <td class="py-4 text-right font-mono font-black text-blue-600">${user.actions_count || 0}</td>
                            </tr>
                        `;
                    })
                    .join("");
            }
        }

        const chartCanvas = document.getElementById("activityChart");
        if (chartCanvas) {
            const ctx = chartCanvas.getContext("2d");
            new Chart(ctx, {
                type: "line",
                data: {
                    labels: activity.map((item) => item.period_start || item.period || ""),
                    datasets: [
                        {
                            label: "Actions",
                            data: activity.map((item) => item.actions_count ?? item.count ?? 0),
                            borderColor: "#2563eb",
                            backgroundColor: "rgba(37, 99, 235, 0.1)",
                            fill: true,
                            tension: 0.4,
                            borderWidth: 3,
                            pointRadius: 0,
                        },
                    ],
                },
                options: {
                    plugins: { legend: { display: false } },
                    scales: {
                        y: { beginAtZero: true, grid: { display: false } },
                        x: { grid: { display: false } },
                    },
                },
            });
        }
    } catch (err) {
        console.error("Dashboard error:", err);
        const message = err instanceof Error ? err.message : "Unknown error";
        renderDashboardError(`Failed to load stats: ${message}`);
    }
}

loadDashboard();
