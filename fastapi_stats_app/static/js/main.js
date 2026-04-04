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
const leaderboardStatusElement = document.getElementById('leaderboard-status');
const leaderboardRetryButtonElement = document.getElementById('leaderboard-retry-btn');
const connectionStatusElement = document.getElementById('connection-status');
const connectionDotElement = document.getElementById('connection-dot');
const connectionTextElement = document.getElementById('connection-text');
const connectionLastSyncElement = document.getElementById('connection-last-sync');
const statsRetryButtonElement = document.getElementById('stats-retry-btn');
const toastContainerElement = document.getElementById('toast-container');

let popularActionsChartInstance;
let actionTypesChartInstance;
let activityOverTimeChartInstance;
let newUsersChartInstance;
let statsSocketManager;

const wsProtocol = window.location.protocol === "https:" ? "wss:" : "ws:";
const wsHost = window.location.host;
const statsWsUrl = `${wsProtocol}//${wsHost}/ws/stats/total_actions`;
const logWsUrl = `${wsProtocol}//${wsHost}/ws/bot_log`;

const chartDataStore = {};
let lastSyncDate = null;

function renderLeaderboardSkeleton(rows = 6) {
    if (!leaderboardBodyElement) return;

    leaderboardBodyElement.innerHTML = Array.from({ length: rows }, () => `
        <tr class="border-b border-gray-200 dark:border-gray-700 animate-pulse">
            <td class="px-6 py-4"><div class="h-3 w-6 bg-gray-200 dark:bg-gray-700 rounded"></div></td>
            <td class="px-6 py-4">
                <div class="flex items-center gap-3">
                    <div class="w-8 h-8 rounded-full bg-gray-200 dark:bg-gray-700"></div>
                    <div class="h-3 w-28 bg-gray-200 dark:bg-gray-700 rounded"></div>
                </div>
            </td>
            <td class="px-6 py-4"><div class="h-3 w-16 bg-gray-200 dark:bg-gray-700 rounded"></div></td>
            <td class="px-6 py-4"><div class="h-3 w-10 bg-gray-200 dark:bg-gray-700 rounded"></div></td>
            <td class="px-6 py-4"><div class="h-3 w-24 bg-gray-200 dark:bg-gray-700 rounded"></div></td>
        </tr>
    `).join('');
}

function setConnectionState(state, text) {
    if (!connectionStatusElement || !connectionDotElement || !connectionTextElement) return;

    connectionTextElement.textContent = text;
    connectionDotElement.classList.remove('bg-red-500', 'bg-yellow-500', 'bg-green-500');

    if (state === 'online') {
        connectionDotElement.classList.add('bg-green-500');
        if (statsRetryButtonElement) statsRetryButtonElement.classList.add('hidden');
    } else if (state === 'connecting') {
        connectionDotElement.classList.add('bg-yellow-500');
    } else {
        connectionDotElement.classList.add('bg-red-500');
        if (statsRetryButtonElement) statsRetryButtonElement.classList.remove('hidden');
    }
}

function updateLastSync(timestamp) {
    if (!timestamp || !connectionLastSyncElement) return;
    lastSyncDate = new Date(timestamp);
    connectionLastSyncElement.textContent = `Р В РЎвЂєР В Р’В±Р В Р вЂ¦Р В РЎвЂўР В Р вЂ Р В Р’В»Р В Р’ВµР В Р вЂ¦Р В РЎвЂў ${lastSyncDate.toLocaleTimeString()}`;
}

function setWidgetStatus(element, state, message) {
    if (!element) return;
    element.textContent = message;
    element.classList.remove('text-red-500', 'text-yellow-600', 'text-green-600', 'text-gray-500');
    if (state === 'error') {
        element.classList.add('text-red-500');
    } else if (state === 'empty') {
        element.classList.add('text-yellow-600');
    } else if (state === 'ok') {
        element.classList.add('text-green-600');
    } else {
        element.classList.add('text-gray-500');
    }
}

function showToast(type, message) {
    if (!toastContainerElement || !message) return;

    const colorClassByType = {
        error: 'bg-red-600',
        warning: 'bg-yellow-600',
        success: 'bg-green-600',
        info: 'bg-blue-600',
    };

    const toast = document.createElement('div');
    toast.className = `pointer-events-auto text-white text-sm px-3 py-2 rounded shadow-lg ${colorClassByType[type] || colorClassByType.info}`;
    toast.textContent = message;
    toastContainerElement.appendChild(toast);

    setTimeout(() => {
        toast.remove();
    }, 4500);
}

function setLeaderboardState(state, text) {
    if (!leaderboardStatusElement || !leaderboardRetryButtonElement) return;

    setWidgetStatus(leaderboardStatusElement, state, text);

    if (state === 'error') {
        leaderboardRetryButtonElement.classList.remove('hidden');
    } else if (state === 'empty') {
        leaderboardRetryButtonElement.classList.add('hidden');
    } else if (state === 'ok') {
        leaderboardRetryButtonElement.classList.add('hidden');
    } else {
        leaderboardRetryButtonElement.classList.add('hidden');
    }
}

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
    totalActionsValueElement.textContent = "Р С›Р В±Р Р…Р С•Р Р†Р В»Р ВµР Р…Р С‘Р Вµ...";
    setConnectionState('online', 'Р С›Р Р…Р В»Р В°Р в„–Р Р…');
    setLeaderboardState('loading', 'Р вЂ”Р В°Р С–РЎР‚РЎС“Р В·Р С”Р В°...');
    setWidgetStatus(popularActionsStatusElement, 'loading', 'Р С›Р В¶Р С‘Р Т‘Р В°Р Р…Р С‘Р Вµ Р Т‘Р В°Р Р…Р Р…РЎвЂ№РЎвЂ¦...');
    setWidgetStatus(activityOverTimeStatusElement, 'loading', 'Р С›Р В¶Р С‘Р Т‘Р В°Р Р…Р С‘Р Вµ Р Т‘Р В°Р Р…Р Р…РЎвЂ№РЎвЂ¦...');
    setWidgetStatus(newUsersStatusElement, 'loading', 'Р С›Р В¶Р С‘Р Т‘Р В°Р Р…Р С‘Р Вµ Р Т‘Р В°Р Р…Р Р…РЎвЂ№РЎвЂ¦...');
    setWidgetStatus(actionTypesStatusElement, 'loading', 'Р С›Р В¶Р С‘Р Т‘Р В°Р Р…Р С‘Р Вµ Р Т‘Р В°Р Р…Р Р…РЎвЂ№РЎвЂ¦...');
    renderLeaderboardSkeleton();
}
function handleStatsSocketMessage(event) {
    try {
        const data = JSON.parse(event.data);

        if (data.error) {
            setLeaderboardState('error', 'Р С›РЎв‚¬Р С‘Р В±Р С”Р В° Р Т‘Р В°Р Р…Р Р…РЎвЂ№РЎвЂ¦');
            setWidgetStatus(popularActionsStatusElement, 'error', 'Р С›РЎв‚¬Р С‘Р В±Р С”Р В° Р Т‘Р В°Р Р…Р Р…РЎвЂ№РЎвЂ¦');
            setWidgetStatus(activityOverTimeStatusElement, 'error', 'Р С›РЎв‚¬Р С‘Р В±Р С”Р В° Р Т‘Р В°Р Р…Р Р…РЎвЂ№РЎвЂ¦');
            setWidgetStatus(newUsersStatusElement, 'error', 'Р С›РЎв‚¬Р С‘Р В±Р С”Р В° Р Т‘Р В°Р Р…Р Р…РЎвЂ№РЎвЂ¦');
            setWidgetStatus(actionTypesStatusElement, 'error', 'Р С›РЎв‚¬Р С‘Р В±Р С”Р В° Р Т‘Р В°Р Р…Р Р…РЎвЂ№РЎвЂ¦');
            showToast('error', 'Р С›РЎв‚¬Р С‘Р В±Р С”Р В° Р В·Р В°Р С–РЎР‚РЎС“Р В·Р С”Р С‘ РЎРѓРЎвЂљР В°РЎвЂљР С‘РЎРѓРЎвЂљР С‘Р С”Р С‘');
            return;
        }

        if (data.total_actions !== undefined) {
            totalActionsValueElement.textContent = data.total_actions.toLocaleString();
            if (data.last_updated) {
                const date = new Date(data.last_updated);
                lastUpdatedValueElement.textContent = date.toLocaleTimeString();
                lastUpdatedContainer.classList.remove('hidden');
                updateLastSync(data.last_updated);
            }
        }

        if (data.leaderboard && Array.isArray(data.leaderboard)) {
            leaderboardBodyElement.innerHTML = '';
            if (data.leaderboard.length === 0) {
                setLeaderboardState('empty', 'Р СњР ВµРЎвЂљ Р Т‘Р В°Р Р…Р Р…РЎвЂ№РЎвЂ¦');
                leaderboardBodyElement.innerHTML = `<tr><td colspan="5" class="px-6 py-4 text-center">Р СњР ВµРЎвЂљ Р Т‘Р В°Р Р…Р Р…РЎвЂ№РЎвЂ¦.</td></tr>`;
            } else {
                setLeaderboardState('ok', 'Р вЂќР В°Р Р…Р Р…РЎвЂ№Р Вµ Р С•Р В±Р Р…Р С•Р Р†Р В»РЎРЏРЎР‹РЎвЂљРЎРѓРЎРЏ');
                data.leaderboard.forEach((user, index) => {
                    const tr = document.createElement('tr');
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
                    if (user.username && user.username !== 'Р СњР ВµРЎвЂљ username') {
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
        setLeaderboardState('error', 'Р С›РЎв‚¬Р С‘Р В±Р С”Р В° Р Т‘Р В°Р Р…Р Р…РЎвЂ№РЎвЂ¦');
        setConnectionState('offline', 'Р С›РЎв‚¬Р С‘Р В±Р С”Р В° Р Т‘Р В°Р Р…Р Р…РЎвЂ№РЎвЂ¦');
        showToast('error', 'Р СњР Вµ РЎС“Р Т‘Р В°Р В»Р С•РЎРѓРЎРЉ Р С•Р В±РЎР‚Р В°Р В±Р С•РЎвЂљР В°РЎвЂљРЎРЉ Р Т‘Р В°Р Р…Р Р…РЎвЂ№Р Вµ РЎРѓРЎвЂљР В°РЎвЂљР С‘РЎРѓРЎвЂљР С‘Р С”Р С‘');
    }
}
function handleStatsSocketClose() {
    setLeaderboardState('error', 'Р СњР ВµРЎвЂљ РЎРѓР С•Р ВµР Т‘Р С‘Р Р…Р ВµР Р…Р С‘РЎРЏ');
    setConnectionState('offline', 'Р СњР ВµРЎвЂљ РЎРѓР С•Р ВµР Т‘Р С‘Р Р…Р ВµР Р…Р С‘РЎРЏ');
    showToast('warning', 'WebSocket Р С•РЎвЂљР С”Р В»РЎР‹РЎвЂЎР ВµР Р…, Р С‘Р Т‘Р ВµРЎвЂљ Р С—Р ВµРЎР‚Р ВµР С—Р С•Р Т‘Р С”Р В»РЎР‹РЎвЂЎР ВµР Р…Р С‘Р Вµ');
}

function handleStatsSocketError() {
    setLeaderboardState('error', 'Р С›РЎв‚¬Р С‘Р В±Р С”Р В° РЎРѓР С•Р ВµР Т‘Р С‘Р Р…Р ВµР Р…Р С‘РЎРЏ');
    setConnectionState('offline', 'Р С›РЎв‚¬Р С‘Р В±Р С”Р В° РЎРѓР С•Р ВµР Т‘Р С‘Р Р…Р ВµР Р…Р С‘РЎРЏ');
    showToast('error', 'Р С›РЎв‚¬Р С‘Р В±Р С”Р В° РЎРѓР С•Р ВµР Т‘Р С‘Р Р…Р ВµР Р…Р С‘РЎРЏ РЎРѓР С• РЎРѓРЎвЂљР В°РЎвЂљР С‘РЎРѓРЎвЂљР С‘Р С”Р С•Р в„–');
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

    if (topData.length === 0) {
        setWidgetStatus(popularActionsStatusElement, 'empty', 'Р СњР ВµРЎвЂљ Р Т‘Р В°Р Р…Р Р…РЎвЂ№РЎвЂ¦ Р С—Р С• Р Р†РЎвЂ№Р В±РЎР‚Р В°Р Р…Р Р…Р С•Р СРЎС“ РЎвЂћР С‘Р В»РЎРЉРЎвЂљРЎР‚РЎС“');
    } else {
        setWidgetStatus(popularActionsStatusElement, 'ok', `Р СџР С•Р С”Р В°Р В·Р В°Р Р…Р С•: ${topData.length}`);
    }

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

    if (!data || data.length === 0) {
        setWidgetStatus(activityOverTimeStatusElement, 'empty', 'Р СњР ВµРЎвЂљ Р Т‘Р В°Р Р…Р Р…РЎвЂ№РЎвЂ¦ Р В·Р В° Р Р†РЎвЂ№Р В±РЎР‚Р В°Р Р…Р Р…РЎвЂ№Р в„– Р С—Р ВµРЎР‚Р С‘Р С•Р Т‘');
    } else {
        setWidgetStatus(activityOverTimeStatusElement, 'ok', `Р СџР ВµРЎР‚Р С‘Р С•Р Т‘: ${filter}`);
    }

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
    if (!data || data.length === 0) {
        setWidgetStatus(newUsersStatusElement, 'empty', 'Р СњР ВµРЎвЂљ Р Т‘Р В°Р Р…Р Р…РЎвЂ№РЎвЂ¦ Р С• Р Р…Р С•Р Р†РЎвЂ№РЎвЂ¦ Р С—Р С•Р В»РЎРЉР В·Р С•Р Р†Р В°РЎвЂљР ВµР В»РЎРЏРЎвЂ¦');
    } else {
        setWidgetStatus(newUsersStatusElement, 'ok', `Р вЂ”Р В°Р С—Р С‘РЎРѓР ВµР в„–: ${data.length}`);
    }

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
    if (!data || data.length === 0) {
        setWidgetStatus(actionTypesStatusElement, 'empty', 'Р СњР ВµРЎвЂљ Р Т‘Р В°Р Р…Р Р…РЎвЂ№РЎвЂ¦ Р С—Р С• РЎвЂљР С‘Р С—Р В°Р С Р Т‘Р ВµР в„–РЎРѓРЎвЂљР Р†Р С‘Р в„–');
    } else {
        setWidgetStatus(actionTypesStatusElement, 'ok', `Р С™Р В°РЎвЂљР ВµР С–Р С•РЎР‚Р С‘Р в„–: ${data.length}`);
    }

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
    modalBody.innerHTML = '<div class="p-4 text-center">Р—Р°РіСЂСѓР·РєР°...</div>';

    fetch(`/api/stats/action_users?action_type=${type}&action_details=${encodeURIComponent(label)}&page=${page}`)
        .then(res => {
            if (!res.ok) {
                throw new Error(`HTTP ${res.status}`);
            }
            return res.json();
        })
        .then(data => {
            if (!data.users || data.users.length === 0) {
                modalBody.innerHTML = '<div class="p-4 text-center text-gray-500">РџРѕР»СЊР·РѕРІР°С‚РµР»Рё РЅРµ РЅР°Р№РґРµРЅС‹.</div>';
                return;
            }

            const table = document.createElement('table');
            table.className = "w-full text-sm text-left text-gray-500 dark:text-gray-400";
            table.innerHTML = `
                <thead class="text-xs text-gray-700 uppercase bg-gray-50 dark:bg-gray-700 dark:text-gray-300">
                    <tr>
                        <th class="px-6 py-3">ID</th>
                        <th class="px-6 py-3">РРјСЏ</th>
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
                    prevBtn.textContent = 'В« РќР°Р·Р°Рґ';
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
                    nextBtn.textContent = 'Р’РїРµСЂРµРґ В»';
                    nextBtn.className = "px-3 py-1 text-sm bg-gray-200 rounded hover:bg-gray-300 dark:bg-gray-700 dark:hover:bg-gray-600 dark:text-white";
                    nextBtn.onclick = () => fetchUsersForModal(label, type, page + 1);
                    controls.appendChild(nextBtn);
                }
            }
        })
        .catch(err => {
            console.error(err);
            showToast('error', 'РќРµ СѓРґР°Р»РѕСЃСЊ Р·Р°РіСЂСѓР·РёС‚СЊ СЃРїРёСЃРѕРє РїРѕР»СЊР·РѕРІР°С‚РµР»РµР№');
            modalBody.innerHTML = `
                <div class="p-4 text-center text-red-500">РћС€РёР±РєР° Р·Р°РіСЂСѓР·РєРё.</div>
                <div class="pb-4 text-center">
                    <button id="modal-retry-btn" class="px-3 py-1 text-sm rounded bg-blue-600 text-white hover:bg-blue-700 transition">
                        РџРѕРІС‚РѕСЂРёС‚СЊ
                    </button>
                </div>
            `;
            const retryButton = document.getElementById('modal-retry-btn');
            if (retryButton) {
                retryButton.addEventListener('click', () => fetchUsersForModal(label, type, page));
            }
        });
}

document.addEventListener('DOMContentLoaded', function() {
    setConnectionState('connecting', 'РџРѕРґРєР»СЋС‡РµРЅРёРµ...');
    renderLeaderboardSkeleton();
    setWidgetStatus(popularActionsStatusElement, 'loading', 'РћР¶РёРґР°РЅРёРµ РґР°РЅРЅС‹С…...');
    setWidgetStatus(activityOverTimeStatusElement, 'loading', 'РћР¶РёРґР°РЅРёРµ РґР°РЅРЅС‹С…...');
    setWidgetStatus(newUsersStatusElement, 'loading', 'РћР¶РёРґР°РЅРёРµ РґР°РЅРЅС‹С…...');
    setWidgetStatus(actionTypesStatusElement, 'loading', 'РћР¶РёРґР°РЅРёРµ РґР°РЅРЅС‹С…...');

    statsSocketManager = new WebSocketManager(statsWsUrl, {
        onOpen: handleStatsSocketOpen,
        onMessage: handleStatsSocketMessage,
        onClose: handleStatsSocketClose,
        onError: handleStatsSocketError
    });
    statsSocketManager.connect();

    const reconnectStats = () => {
        setConnectionState('connecting', 'РџРµСЂРµРїРѕРґРєР»СЋС‡РµРЅРёРµ...');
        setLeaderboardState('loading', 'РџРѕРІС‚РѕСЂРЅРѕРµ РїРѕРґРєР»СЋС‡РµРЅРёРµ...');
        renderLeaderboardSkeleton();
        statsSocketManager.connect();
    };

    if (leaderboardRetryButtonElement) {
        leaderboardRetryButtonElement.addEventListener('click', reconnectStats);
    }
    if (statsRetryButtonElement) {
        statsRetryButtonElement.addEventListener('click', reconnectStats);
    }

    const logSocketManager = new WebSocketManager(logWsUrl, {
        onOpen: () => {
            botLogStatusElement.textContent = 'Connected';
        },
        onMessage: handleLogSocketMessage,
        onClose: () => {
            botLogStatusElement.textContent = 'Disconnected';
        },
        onError: () => {
            botLogStatusElement.textContent = 'Connection error';
        },
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
