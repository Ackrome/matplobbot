const totalActionsValueElement = document.getElementById('total-actions-value');
const leaderboardBodyElement = document.getElementById('leaderboard-body');
const popularActionsStatusElement = document.getElementById('popular-actions-status');
const actionTypesStatusElement = document.getElementById('action-types-status');
const activityOverTimeStatusElement = document.getElementById('activity-over-time-status');
const newUsersStatusElement = document.getElementById('new-users-status');
const botLogContentElement = document.getElementById('bot-log-content');
const botLogStatusElement = document.getElementById('bot-log-status');
const lastUpdatedContainer = document.getElementById('last-updated-container');
const lastUpdatedValueElement = document.getElementById('last-updated-value');

let popularActionsChartInstance;
let actionTypesChartInstance;
let activityOverTimeChartInstance;
let newUsersChartInstance;

const wsProtocol = window.location.protocol === "https:" ? "wss:" : "ws:";
const wsHost = window.location.host;
const statsWsUrl = `${wsProtocol}//${wsHost}/ws/stats/total_actions`;
const logWsUrl = `${wsProtocol}//${wsHost}/ws/bot_log`;

const chartDataStore = {};

class WebSocketManager {
    constructor(url, { onOpen, onMessage, onClose, onError }) {
        this.url = url;
        this.onOpen = onOpen;
        this.onMessage = onMessage;
        this.onClose = onClose;
        this.onError = onError;
        
        this.socket = null;
        this.reconnectTimeoutId = null;
        this.retryCount = 0;
        this.maxRetryCount = 8;
    }

    connect() {
        if (this.socket && this.socket.readyState === WebSocket.OPEN) return;

        console.log(`Connecting to ${this.url}...`);
        this.socket = new WebSocket(this.url);

        this.socket.onopen = (event) => {
            console.log(`Connected to ${this.url}.`);
            this.retryCount = 0;
            if (this.onOpen) this.onOpen(event);
        };

        this.socket.onmessage = (event) => {
            if (this.onMessage) this.onMessage(event);
        };

        this.socket.onerror = (error) => {
            console.error(`WebSocket error on ${this.url}:`, error);
            if (this.onError) this.onError(error);
        };

        this.socket.onclose = (event) => {
            console.log(`WebSocket to ${this.url} closed. Code: ${event.code}.`);
            if (this.onClose) this.onClose(event);
            this.reconnect();
        };
    }

    reconnect() {
        if (this.reconnectTimeoutId) clearTimeout(this.reconnectTimeoutId);
        const delay = Math.min(1000 * (2 ** this.retryCount), 60000);
        this.reconnectTimeoutId = setTimeout(() => {
            if (this.retryCount < this.maxRetryCount) this.retryCount++;
            this.connect();
        }, delay);
    }
}

function handleStatsSocketOpen() {
    totalActionsValueElement.textContent = "Обновление...";
    const statusDot = document.querySelector("#connection-status span");
    if(statusDot) {
        statusDot.classList.remove('bg-red-500');
        statusDot.classList.add('bg-green-500');
    }
}

function handleStatsSocketMessage(event) {
    try {
        const data = JSON.parse(event.data);
        
        if (data.total_actions !== undefined) {
            totalActionsValueElement.textContent = data.total_actions.toLocaleString();
            if (data.last_updated) {
                const date = new Date(data.last_updated);
                lastUpdatedValueElement.textContent = date.toLocaleTimeString();
                lastUpdatedContainer.classList.remove('hidden');
            }
        }

        if (data.leaderboard && Array.isArray(data.leaderboard)) {
            leaderboardBodyElement.innerHTML = '';
            if (data.leaderboard.length === 0) {
                leaderboardBodyElement.innerHTML = `<tr><td colspan="5" class="px-6 py-4 text-center">Нет данных.</td></tr>`;
            } else {
                data.leaderboard.forEach((user, index) => {
                    const tr = document.createElement('tr');
                    // Используем theme-card вместо жестких цветов
                    tr.className = "theme-card border-b border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors";
                    const tdRank = document.createElement('td');
                    tdRank.className = "px-6 py-4 font-medium text-gray-900 whitespace-nowrap dark:text-white";
                    tdRank.textContent = index + 1;
                    tr.appendChild(tdRank);

                    const tdUser = document.createElement('td');
                    tdUser.className = "px-6 py-4 flex items-center space-x-3";
                    
                    let avatarHtml = '';
                    if (user.avatar_pic_url) {
                        avatarHtml = `<img class="w-8 h-8 rounded-full object-cover" src="${user.avatar_pic_url}" alt="Avatar">`;
                    } else {
                        const initial = (user.full_name && user.full_name.trim().length > 0) ? user.full_name.trim()[0] : '?';
                        avatarHtml = `<div class="fallback-avatar">${initial}</div>`;
                    }
                    
                    const nameLink = `<a href="/users/${user.user_id}" class="font-medium text-blue-600 dark:text-blue-400 hover:underline">${user.full_name}</a>`;
                    tdUser.innerHTML = `${avatarHtml} <div>${nameLink}</div>`;
                    tr.appendChild(tdUser);

                    const tdTag = document.createElement('td');
                    tdTag.className = "px-6 py-4";
                    if (user.username && user.username !== 'Нет username') {
                        tdTag.innerHTML = `<span class="bg-gray-100 text-gray-800 text-xs font-medium px-2.5 py-0.5 rounded dark:bg-gray-700 dark:text-gray-300">@${user.username}</span>`;
                    } else {
                        tdTag.innerHTML = `<span class="text-gray-400 text-xs">-</span>`;
                    }
                    tr.appendChild(tdTag);

                    const tdActions = document.createElement('td');
                    tdActions.className = "px-6 py-4 font-bold text-gray-700 dark:text-gray-300";
                    tdActions.textContent = user.actions_count;
                    tr.appendChild(tdActions);

                    const tdTime = document.createElement('td');
                    tdTime.className = "px-6 py-4 text-xs text-gray-500 dark:text-gray-400";
                    tdTime.textContent = user.last_action_time ? new Date(user.last_action_time).toLocaleString() : 'N/A';
                    tr.appendChild(tdTime);

                    leaderboardBodyElement.appendChild(tr);
                });
            }
        }

        if (data.popular_commands) chartDataStore.popularCommands = data.popular_commands;
        if (data.popular_messages) chartDataStore.popularMessages = data.popular_messages;
        if (chartDataStore.popularCommands || chartDataStore.popularMessages) updateCombinedPopularActionsChart();

        if (data.action_types_distribution) {
            chartDataStore.actionTypes = data.action_types_distribution;
            updateActionTypesChart(data.action_types_distribution);
        }

        if (data.activity_over_time) {
            chartDataStore.activityOverTime = data.activity_over_time;
            updateActivityOverTimeChart();
        }

        if (data.new_users_per_day) {
            chartDataStore.newUsers = data.new_users_per_day;
            updateNewUsersChart(data.new_users_per_day);
        }

    } catch (e) {
        console.error("Error parsing WS stats:", e);
    }
}

function handleStatsSocketClose() {
    const statusDot = document.querySelector("#connection-status span");
    if(statusDot) {
        statusDot.classList.remove('bg-green-500');
        statusDot.classList.add('bg-red-500');
    }
}

function handleLogSocketMessage(event) {
    const newLogEntry = document.createElement('div');
    newLogEntry.className = "log-entry"; // Basic CSS class from styles.css
    const logText = event.data;

    const logRegex = /^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) - (INFO|WARNING|ERROR|CRITICAL|DEBUG) - ([a-zA-Z0-9_.]+) - ([a-zA-Z0-9_<>.]+)\.([a-zA-Z0-9_<>]+):(\d+) - (.*)$/;
    const match = logText.match(logRegex);

    if (match) {
        const [, timestamp, level, loggerName, moduleName, funcName, lineNo, message] = match;
        const levelClass = `level-${level.toLowerCase()}`;
        newLogEntry.innerHTML = `
            <span class="timestamp">${timestamp}</span>
            <span class="${levelClass}">[${level}]</span>
            <span class="text-gray-500 dark:text-gray-400 ml-1 text-[10px]">${loggerName}</span>
            <span class="message ml-2">${message}</span>
        `;
    } else {
        newLogEntry.textContent = logText;
        if (logText.includes("ERROR")) newLogEntry.classList.add("text-red-400");
    }
    
    botLogContentElement.appendChild(newLogEntry);
    if (botLogContentElement.childElementCount > 200) {
        botLogContentElement.removeChild(botLogContentElement.firstChild);
    }
    botLogContentElement.scrollTop = botLogContentElement.scrollHeight;
    
    if (botLogStatusElement.textContent) botLogStatusElement.textContent = '';
}

function updateCombinedPopularActionsChart() {
    const filter = document.querySelector('input[name="actionFilter"]:checked').value;
    const commands = (chartDataStore.popularCommands || []).map(d => ({ label: d.command, count: d.count, type: 'command' }));
    const messages = (chartDataStore.popularMessages || []).map(d => ({ label: d.message, count: d.count, type: 'message' }));

    let combinedData = [];
    if (filter === 'all') combinedData = [...commands, ...messages];
    else if (filter === 'commands') combinedData = commands;
    else if (filter === 'messages') combinedData = messages;

    combinedData.sort((a, b) => b.count - a.count);
    const topData = combinedData.slice(0, 10); 

    popularActionsChartInstance = updateChart({
        instance: popularActionsChartInstance,
        ctx: document.getElementById('popularActionsChart').getContext('2d'),
        data: topData, type: 'bar', labelKey: 'label', countKey: 'count',
        datasetLabel: 'Count',
        backgroundColor: topData.map(d => d.type === 'command' ? 'rgba(59, 130, 246, 0.7)' : 'rgba(16, 185, 129, 0.7)'), 
        borderColor: topData.map(d => d.type === 'command' ? 'rgb(59, 130, 246)' : 'rgb(16, 185, 129)'),
        extraOptions: {
            onClick: (event, elements, chart) => handleChartClick(event, chart, topData),
            borderRadius: 4,
            indexAxis: 'y'
        }
    });
}

const updateActivityOverTimeChart = () => {
    const filter = document.querySelector('input[name="timeFilter"]:checked').value;
    const data = chartDataStore.activityOverTime ? chartDataStore.activityOverTime[filter] : [];

    activityOverTimeChartInstance = updateChart({
        instance: activityOverTimeChartInstance,
        ctx: document.getElementById('activityOverTimeChart').getContext('2d'),
        data, type: 'line', labelKey: 'period', countKey: 'count',
        datasetLabel: 'Actions',
        borderColor: 'rgb(99, 102, 241)', 
        backgroundColor: 'rgba(99, 102, 241, 0.1)',
        extraOptions: { fill: true, tension: 0.3 }
    });
};

const updateNewUsersChart = (data) => {
    newUsersChartInstance = updateChart({
        instance: newUsersChartInstance,
        ctx: document.getElementById('newUsersChart').getContext('2d'),
        data, type: 'bar', labelKey: 'date', countKey: 'count',
        datasetLabel: 'New Users',
        backgroundColor: 'rgba(236, 72, 153, 0.7)', 
        borderColor: 'rgb(236, 72, 153)',
        extraOptions: { borderRadius: 4 }
    });
};

const updateActionTypesChart = (data) => {
    const colors = [
        'rgba(59, 130, 246, 0.8)', 
        'rgba(16, 185, 129, 0.8)', 
        'rgba(245, 158, 11, 0.8)', 
        'rgba(239, 68, 68, 0.8)',  
        'rgba(139, 92, 246, 0.8)'  
    ];
    
    actionTypesChartInstance = updateChart({
        instance: actionTypesChartInstance,
        ctx: document.getElementById('actionTypesChart').getContext('2d'),
        data, type: 'doughnut', labelKey: 'action_type', countKey: 'count',
        datasetLabel: 'Distribution',
        backgroundColor: data.map((_, i) => colors[i % colors.length]),
        extraOptions: { 
            cutout: '65%',
            plugins: { legend: { position: 'right' } }
        }
    });
};

function downloadCSV(headers, data, filename) {
    if (!data || data.length === 0) return;
    const csvContent = "data:text/csv;charset=utf-8," + [
        headers.join(','),
        ...data.map(row => {
            if (typeof row === 'object' && row !== null) {
                 return Object.values(row).map(val => `"${String(val).replace(/"/g, '""')}"`).join(',')
            } else {
                 return `"${String(row)}"`
            }
        })
    ].join('\n');
    
    const link = document.createElement("a");
    link.href = encodeURI(csvContent);
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
}

function updateChart({ instance, ctx, data, type, labelKey, countKey, datasetLabel, backgroundColor, borderColor, extraOptions }) {
    const labels = data.map(d => d[labelKey]);
    const counts = data.map(d => d[countKey]);
    const theme = document.documentElement.classList.contains('dark') ? 'dark' : 'light';
    const colors = getChartThemeColors(theme);

    const config = {
        type: type,
        data: {
            labels: labels,
            datasets: [{
                label: datasetLabel,
                data: counts,
                backgroundColor: backgroundColor,
                borderColor: borderColor,
                borderWidth: 1
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: type !== 'doughnut' ? {
                x: { ticks: { color: colors.tickColor }, grid: { color: colors.gridColor } },
                y: { ticks: { color: colors.tickColor }, grid: { color: colors.gridColor }, beginAtZero: true }
            } : {},
            plugins: {
                legend: { labels: { color: colors.legendColor } }
            },
            ...extraOptions
        }
    };

    if (instance) {
        instance.data = config.data;
        instance.options = { ...instance.options, ...config.options };
        instance.update('none');
        return instance;
    }
    return new Chart(ctx, config);
}

function handleChartClick(event, chart, data) {
    const points = chart.getElementsAtEventForMode(event, 'nearest', { intersect: true }, true);
    if (points.length) {
        const index = points[0].index;
        const item = data[index];
        const modal = document.getElementById('user-list-modal');
        modal.classList.remove('hidden');
        document.getElementById('modal-title').textContent = `Users for: ${item.label}`;
        fetchUsersForModal(item.label, item.type || 'command');
    }
}

function fetchUsersForModal(label, type, page = 1) {
    const modalBody = document.getElementById('modal-body');
    const controls = document.getElementById('modal-pagination-controls');
    modalBody.innerHTML = '<div class="p-4 text-center">Загрузка...</div>';
    
    fetch(`/api/stats/action_users?action_type=${type}&action_details=${encodeURIComponent(label)}&page=${page}`)
        .then(res => res.json())
        .then(data => {
            if(!data.users || data.users.length === 0) {
                modalBody.innerHTML = '<div class="p-4 text-center text-gray-500">Пользователи не найдены.</div>';
                return;
            }
            
            const table = document.createElement('table');
            table.className = "w-full text-sm text-left text-gray-500 dark:text-gray-400";
            table.innerHTML = `
                <thead class="text-xs text-gray-700 uppercase bg-gray-50 dark:bg-gray-700 dark:text-gray-300">
                    <tr>
                        <th class="px-6 py-3">ID</th>
                        <th class="px-6 py-3">Имя</th>
                        <th class="px-6 py-3">Username</th>
                    </tr>
                </thead>
                <tbody>
                    ${data.users.map(u => `
                        <tr class="bg-white border-b dark:bg-gray-800 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700">
                            <td class="px-6 py-4">${u.user_id}</td>
                            <td class="px-6 py-4"><a href="/users/${u.user_id}" target="_blank" class="text-blue-500 hover:underline">${u.full_name}</a></td>
                            <td class="px-6 py-4">${u.username}</td>
                        </tr>
                    `).join('')}
                </tbody>
            `;
            modalBody.innerHTML = '';
            modalBody.appendChild(table);
            
            controls.innerHTML = '';
            if (data.pagination.total_pages > 1) {
                if (page > 1) {
                    const prevBtn = document.createElement('button');
                    prevBtn.textContent = '« Назад';
                    prevBtn.className = "px-3 py-1 text-sm bg-gray-200 rounded hover:bg-gray-300 dark:bg-gray-700 dark:hover:bg-gray-600 dark:text-white";
                    prevBtn.onclick = () => fetchUsersForModal(label, type, page - 1);
                    controls.appendChild(prevBtn);
                }
                const pageInfo = document.createElement('span');
                pageInfo.className = "text-sm text-gray-500 self-center px-2 dark:text-gray-400";
                pageInfo.textContent = `${page} / ${data.pagination.total_pages}`;
                controls.appendChild(pageInfo);
                
                if (page < data.pagination.total_pages) {
                    const nextBtn = document.createElement('button');
                    nextBtn.textContent = 'Вперед »';
                    nextBtn.className = "px-3 py-1 text-sm bg-gray-200 rounded hover:bg-gray-300 dark:bg-gray-700 dark:hover:bg-gray-600 dark:text-white";
                    nextBtn.onclick = () => fetchUsersForModal(label, type, page + 1);
                    controls.appendChild(nextBtn);
                }
            }
        })
        .catch(err => {
            console.error(err);
            modalBody.innerHTML = '<div class="p-4 text-center text-red-500">Ошибка загрузки.</div>';
        });
}

document.addEventListener('DOMContentLoaded', function() {
    const statsSocketManager = new WebSocketManager(statsWsUrl, {
        onOpen: handleStatsSocketOpen,
        onMessage: handleStatsSocketMessage,
        onClose: handleStatsSocketClose
    });
    statsSocketManager.connect();

    const logSocketManager = new WebSocketManager(logWsUrl, {
        onOpen: () => botLogStatusElement.textContent = "Connected",
        onMessage: handleLogSocketMessage,
        onClose: () => botLogStatusElement.textContent = "Disconnected"
    });
    logSocketManager.connect();

    document.querySelectorAll('input[name="actionFilter"]').forEach(r => r.addEventListener('change', updateCombinedPopularActionsChart));
    document.querySelectorAll('input[name="timeFilter"]').forEach(r => r.addEventListener('change', updateActivityOverTimeChart));

    const themeBtn = document.getElementById('theme-toggle-button');
    if(themeBtn) {
        themeBtn.addEventListener('click', () => {
            setTimeout(() => {
                [popularActionsChartInstance, actionTypesChartInstance, activityOverTimeChartInstance, newUsersChartInstance].forEach(c => {
                    if(c) {
                        const colors = getChartThemeColors(document.documentElement.classList.contains('dark') ? 'dark' : 'light');
                        if (c.options.scales.x) c.options.scales.x.ticks.color = colors.tickColor;
                        if (c.options.scales.y) c.options.scales.y.ticks.color = colors.tickColor;
                        c.options.plugins.legend.labels.color = colors.legendColor;
                        c.update();
                    }
                });
            }, 50);
        });
    }
    
    document.querySelectorAll('.download-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const chartKey = e.target.dataset.chart;
            const format = e.target.dataset.format;
            const data = chartDataStore[chartKey];
            
            if(format === 'csv' && data) {
                downloadCSV(['Label', 'Count'], data, `${chartKey}.csv`);
            } else if (format === 'png') {
                const chartInstanceMap = {
                    popularActions: popularActionsChartInstance,
                    actionTypes: actionTypesChartInstance,
                    activityOverTime: activityOverTimeChartInstance,
                    newUsers: newUsersChartInstance
                };
                const chart = chartInstanceMap[chartKey];
                if (!chart) return;
                const link = document.createElement('a');
                link.href = chart.toBase64Image();
                link.download = `${chartKey}_chart.png`;
                link.click();
            }
        });
    });
    
    document.querySelector('.modal-close-btn').addEventListener('click', () => {
        document.getElementById('user-list-modal').classList.add('hidden');
    });
});