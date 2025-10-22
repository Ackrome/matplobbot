const totalActionsValueElement = document.getElementById('total-actions-value');
const leaderboardBodyElement = document.getElementById('leaderboard-body');
const popularCommandsStatusElement = document.getElementById('popular-commands-status');
const popularMessagesStatusElement = document.getElementById('popular-messages-status');
const actionTypesStatusElement = document.getElementById('action-types-status');
const activityOverTimeStatusElement = document.getElementById('activity-over-time-status');
const botLogContentElement = document.getElementById('bot-log-content');
const botLogStatusElement = document.getElementById('bot-log-status');

let popularCommandsChartInstance; // Для хранения экземпляра графика
let popularMessagesChartInstance; // Для графика популярных сообщений
let actionTypesChartInstance; // Для графика типов действий
let activityOverTimeChartInstance; // Для графика активности по времени

let statsSocket;
let logSocket;

// Определяем URL для WebSocket. Если используется HTTPS, нужен wss://
const wsProtocol = window.location.protocol === "https:" ? "wss:" : "ws:";
const wsHost = window.location.host; // localhost:9583 или ваш домен
const statsWsUrl = `${wsProtocol}//${wsHost}/ws/stats/total_actions`;
const logWsUrl = `${wsProtocol}//${wsHost}/ws/bot_log`;

function connectWebSocket() {
    statsSocket = new WebSocket(statsWsUrl);

    statsSocket.onopen = function(event) {
        console.log("WebSocket соединение установлено.");
        totalActionsValueElement.textContent = "Ожидание данных...";
    };
    statsSocket.onmessage = function(event) {
        try {
            const data = JSON.parse(event.data);
            if (data.error) {
                console.error("WebSocket Server Error:", data.error); // Ошибка от сервера
                totalActionsValueElement.textContent = `Ошибка: ${data.error}`;
                leaderboardBodyElement.innerHTML = `<tr><td colspan="6" style="text-align:center;">Ошибка: ${data.error}</td></tr>`;
                popularCommandsStatusElement.textContent = `Ошибка загрузки графика: ${data.error}`;
                if (popularCommandsChartInstance) { popularCommandsChartInstance.destroy(); popularCommandsChartInstance = null; }
                popularMessagesStatusElement.textContent = `Ошибка загрузки графика: ${data.error}`;
                if (popularMessagesChartInstance) { popularMessagesChartInstance.destroy(); popularMessagesChartInstance = null; }
                actionTypesStatusElement.textContent = `Ошибка загрузки графика: ${data.error}`;
                if (actionTypesChartInstance) { actionTypesChartInstance.destroy(); actionTypesChartInstance = null; }
                activityOverTimeStatusElement.textContent = `Ошибка загрузки графика: ${data.error}`;
                if (activityOverTimeChartInstance) { activityOverTimeChartInstance.destroy(); activityOverTimeChartInstance = null; }
            } else if (data.total_actions !== undefined) {
                totalActionsValueElement.textContent = data.total_actions;
            }

            if (data.leaderboard && Array.isArray(data.leaderboard)) {
                leaderboardBodyElement.innerHTML = ''; // Очищаем предыдущие данные
                if (data.leaderboard.length === 0) {
                    leaderboardBodyElement.innerHTML = `<tr><td colspan="6" style="text-align:center;">Нет данных для отображения.</td></tr>`;
                } else {
                    data.leaderboard.forEach((user, index) => {
                        const row = leaderboardBodyElement.insertRow();
                        row.insertCell().textContent = index + 1;
                        const avatarCell = row.insertCell();
                        avatarCell.style.width = '76px'; // 60px (image) + 2*8px (padding)
                        avatarCell.style.height = '76px'; // 60px (image) + 2*8px (padding)
                        avatarCell.style.borderRight = 'none';
                        avatarCell.style.textAlign = 'center';
                        avatarCell.style.verticalAlign = 'middle';

                            const profileLink = document.createElement('a');
                            profileLink.href = `/users/${user.user_id}`;

                        if (user.avatar_pic_url) {
                            const img = document.createElement('img');
                            img.src = user.avatar_pic_url;
                            img.alt = `Аватар ${user.full_name || user.username}`;
                                img.style.width = '60px';
                                img.style.height = '60px';
                            img.style.borderRadius = '50%';
                                profileLink.appendChild(img);
                        } else {
                            const fallbackAvatar = document.createElement('div');
                                // Inline styles for structure, class for theming
                                Object.assign(fallbackAvatar.style, { width: '60px', height: '60px', borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '30px', fontWeight: 'bold', textTransform: 'uppercase' });
                            fallbackAvatar.classList.add('fallback-avatar'); // Добавляем класс для стилизации темной темы
                                const initial = (user.full_name && user.full_name.trim().length > 0) ? user.full_name.trim()[0] : '?';
                            fallbackAvatar.textContent = initial;
                                profileLink.appendChild(fallbackAvatar);
                        }
                            avatarCell.appendChild(profileLink);

                        const fullNameCell = row.insertCell();
                        fullNameCell.style.borderLeft = 'none';
                        // Проверяем, есть ли username и не является ли он заглушкой "Нет username"
                        if (user.username && user.username !== 'Нет username') {
                            const link = document.createElement('a');
                            link.href = `https://t.me/${user.username}`;
                            link.textContent = user.full_name;
                            link.target = '_blank'; // Открывать в новой вкладке
                            fullNameCell.appendChild(link);
                        } else {
                                // If no public username, link the name to the profile page as well
                                const profilePageLink = document.createElement('a');
                                profilePageLink.href = `/users/${user.user_id}`;
                                profilePageLink.textContent = user.full_name;
                                fullNameCell.appendChild(profilePageLink);
                        }
                        row.insertCell().textContent = user.username; // SQL уже обработал NULL
                        row.insertCell().textContent = user.actions_count;
                        row.insertCell().textContent = user.last_action_time;
                    });
                }
            }

            if (data.popular_commands && Array.isArray(data.popular_commands)) {
                if (data.popular_commands.length === 0) {
                    popularCommandsStatusElement.textContent = "Нет данных о командах для отображения.";
                    if (popularCommandsChartInstance) { popularCommandsChartInstance.destroy(); popularCommandsChartInstance = null; }
                } else {
                    popularCommandsStatusElement.textContent = ""; // Очищаем статус, если есть данные
                    updatePopularCommandsChart(data.popular_commands);
                }
            }
            
            if (data.popular_messages && Array.isArray(data.popular_messages)) {
                if (data.popular_messages.length === 0) {
                    popularMessagesStatusElement.textContent = "Нет данных о сообщениях для отображения.";
                    if (popularMessagesChartInstance) { popularMessagesChartInstance.destroy(); popularMessagesChartInstance = null; }
                } else {
                    popularMessagesStatusElement.textContent = ""; // Очищаем статус
                    updatePopularMessagesChart(data.popular_messages);
                }
            }

            if (data.action_types_distribution && Array.isArray(data.action_types_distribution)) {
                if (data.action_types_distribution.length === 0) {
                    actionTypesStatusElement.textContent = "Нет данных о типах действий.";
                    if (actionTypesChartInstance) { actionTypesChartInstance.destroy(); actionTypesChartInstance = null; }
                } else {
                    actionTypesStatusElement.textContent = "";
                    updateActionTypesChart(data.action_types_distribution);
                }
            }

            if (data.activity_over_time && Array.isArray(data.activity_over_time)) {
                if (data.activity_over_time.length === 0) {
                    activityOverTimeStatusElement.textContent = "Нет данных об активности для отображения.";
                    if (activityOverTimeChartInstance) { activityOverTimeChartInstance.destroy(); activityOverTimeChartInstance = null; }
                } else {
                    activityOverTimeStatusElement.textContent = "";
                    updateActivityOverTimeChart(data.activity_over_time);
                }
            }

        } catch (e) {
            console.error("Ошибка парсинга WebSocket данных:", e, "Данные:", event.data);
            totalActionsValueElement.textContent = "Ошибка обработки данных";
            leaderboardBodyElement.innerHTML = `<tr><td colspan="6" style="text-align:center;">Ошибка обработки данных.</td></tr>`;
            popularCommandsStatusElement.textContent = "Ошибка обработки данных для графика.";
            popularMessagesStatusElement.textContent = "Ошибка обработки данных для графика.";
            actionTypesStatusElement.textContent = "Ошибка обработки данных для графика.";
            activityOverTimeStatusElement.textContent = "Ошибка обработки данных для графика.";
            }
    };

    statsSocket.onerror = function(error) {
        console.error("WebSocket ошибка:", error);
        totalActionsValueElement.textContent = "Ошибка соединения WebSocket";
        leaderboardBodyElement.innerHTML = `<tr><td colspan="6" style="text-align:center;">Ошибка соединения WebSocket.</td></tr>`;
        popularCommandsStatusElement.textContent = "Ошибка соединения WebSocket для графика.";
        popularMessagesStatusElement.textContent = "Ошибка соединения WebSocket для графика.";
        actionTypesStatusElement.textContent = "Ошибка соединения WebSocket для графика.";
        activityOverTimeStatusElement.textContent = "Ошибка соединения WebSocket для графика.";
        if (popularCommandsChartInstance) { popularCommandsChartInstance.destroy(); popularCommandsChartInstance = null; }
        if (popularMessagesChartInstance) { popularMessagesChartInstance.destroy(); popularMessagesChartInstance = null; }
        if (actionTypesChartInstance) { actionTypesChartInstance.destroy(); actionTypesChartInstance = null; }
        if (activityOverTimeChartInstance) { activityOverTimeChartInstance.destroy(); activityOverTimeChartInstance = null; }
    };

    statsSocket.onclose = function(event) {
        console.log("WebSocket соединение закрыто. Код:", event.code, "Причина:", event.reason);
        totalActionsValueElement.textContent = "Соединение потеряно. Попытка переподключения через 5с...";
        // Попытка переподключения через некоторое время
        leaderboardBodyElement.innerHTML = `<tr><td colspan="6" style="text-align:center;">Соединение потеряно. Попытка переподключения...</td></tr>`;
        popularCommandsStatusElement.textContent = "Соединение для графика потеряно. Попытка переподключения...";
        popularMessagesStatusElement.textContent = "Соединение для графика потеряно. Попытка переподключения...";
        actionTypesStatusElement.textContent = "Соединение для графика потеряно. Попытка переподключения...";
        activityOverTimeStatusElement.textContent = "Соединение для графика потеряно. Попытка переподключения...";
        if (popularCommandsChartInstance) { popularCommandsChartInstance.destroy(); popularCommandsChartInstance = null; }
        if (popularMessagesChartInstance) { popularMessagesChartInstance.destroy(); popularMessagesChartInstance = null; }
        if (actionTypesChartInstance) { actionTypesChartInstance.destroy(); actionTypesChartInstance = null; }
        if (activityOverTimeChartInstance) { activityOverTimeChartInstance.destroy(); activityOverTimeChartInstance = null; }
        setTimeout(connectWebSocket, 5000);
    };
}

function connectLogWebSocket() {
    logSocket = new WebSocket(logWsUrl);
    botLogContentElement.innerHTML = ''; // Очищаем при новом подключении
    botLogStatusElement.textContent = 'Подключение к логу...';

    logSocket.onopen = function(event) {
        console.log("Log WebSocket соединение установлено.");
        botLogStatusElement.textContent = 'Соединение с логом установлено. Ожидание данных...';
    };

    logSocket.onmessage = function(event) {
        const newLogEntry = document.createElement('div');
        newLogEntry.classList.add('log-entry');
        newLogEntry.style.lineHeight = '1.4'; // Немного увеличим межстрочный интервал для читаемости
        const logText = event.data;

        // Регулярное выражение для парсинга стандартной строки лога Python
        // Формат: %(asctime)s - %(levelname)s - %(name)s - %(module)s.%(funcName)s:%(lineno)d - %(message)s
        const logRegex = /^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) - (INFO|WARNING|ERROR|CRITICAL|DEBUG) - ([a-zA-Z0-9_.]+) - ([a-zA-Z0-9_<>.]+)\.([a-zA-Z0-9_<>]+):(\d+) - (.*)$/;
        const match = logText.match(logRegex);

        if (match) {
            const [, timestamp, level, loggerName, moduleName, funcName, lineNo, message] = match;

            const timestampSpan = document.createElement('span');
            timestampSpan.textContent = timestamp + " ";
            timestampSpan.classList.add('timestamp');

            const levelSpan = document.createElement('span');
            levelSpan.textContent = level;
            levelSpan.classList.add('level', `level-${level.toLowerCase()}`);

            const messageSpan = document.createElement('span');
            messageSpan.textContent = `- ${loggerName} - ${moduleName}.${funcName}:${lineNo} - ${message}`;
            messageSpan.classList.add('message', `message-${level.toLowerCase()}`);

            // Specific styles not easily covered by pure CSS class inheritance (like background for critical)
            // can still be applied or refined here if needed, or add more specific CSS classes.
            // For now, the CSS classes should handle most of it.

            newLogEntry.appendChild(timestampSpan);
            newLogEntry.appendChild(levelSpan);
            newLogEntry.appendChild(messageSpan);

        } else {
            newLogEntry.textContent = logText;
            // Add classes for unparsed errors/warnings for theming
            if (logText.startsWith("ОШИБКА")) {
                newLogEntry.classList.add('log-error-unparsed');
            } else if (logText.startsWith("ПРЕДУПРЕЖДЕНИЕ:")) {
                // Could add a .log-warning-unparsed if specific styling is needed
            }
        }
        botLogContentElement.appendChild(newLogEntry);
        // Автопрокрутка вниз
        botLogContentElement.scrollTop = botLogContentElement.scrollHeight;
        if (botLogStatusElement.textContent.includes('Ожидание данных')) {
            botLogStatusElement.textContent = ''; // Убираем сообщение об ожидании
        }
    };

    logSocket.onerror = function(error) {
        console.error("Log WebSocket ошибка:", error);
        botLogStatusElement.textContent = 'Ошибка соединения с логом WebSocket.';
        const errorEntry = document.createElement('div');
        errorEntry.textContent = `ОШИБКА СОЕДИНЕНИЯ: ${error}`;
        errorEntry.style.color = 'red';
        botLogContentElement.appendChild(errorEntry);
    };

    logSocket.onclose = function(event) {
        console.log("Log WebSocket соединение закрыто. Код:", event.code, "Причина:", event.reason);
        botLogStatusElement.textContent = 'Соединение с логом потеряно. Попытка переподключения через 5с...';
        setTimeout(connectLogWebSocket, 5000);
    };
}

function updatePopularCommandsChart(commandsData) {
    const ctx = document.getElementById('popularCommandsChart').getContext('2d');
    const labels = commandsData.map(item => item.command);
    const counts = commandsData.map(item => item.count);
    const currentTheme = document.documentElement.getAttribute('data-theme') || 'light';
    const themeColors = getChartThemeColors(currentTheme);

    const chartOptions = {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
            y: {
                beginAtZero: true,
                ticks: { color: themeColors.tickColor },
                grid: { color: themeColors.gridColor }
            },
            x: {
                ticks: { color: themeColors.tickColor },
                grid: { color: themeColors.gridColor, drawOnChartArea: false }
            }
        },
        plugins: {
            legend: {
                labels: { color: themeColors.legendColor }
            }
        }
    };

    if (popularCommandsChartInstance) {
        popularCommandsChartInstance.data.labels = labels;
        popularCommandsChartInstance.data.datasets[0].data = counts;
        Object.assign(popularCommandsChartInstance.options, chartOptions); // Update all options
        popularCommandsChartInstance.update();
    } else {
        popularCommandsChartInstance = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Количество вызовов',
                    data: counts,
                    backgroundColor: 'rgba(54, 162, 235, 0.5)',
                    borderColor: 'rgba(54, 162, 235, 1)',
                    borderWidth: 1
                }]
            },
            options: chartOptions
        });
    }
}

function updatePopularMessagesChart(messagesData) {
    const ctx = document.getElementById('popularMessagesChart').getContext('2d');
    const labels = messagesData.map(item => item.message);
    const counts = messagesData.map(item => item.count);
    const currentTheme = document.documentElement.getAttribute('data-theme') || 'light';
    const themeColors = getChartThemeColors(currentTheme);

    const chartOptions = {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
            y: {
                beginAtZero: true,
                ticks: { color: themeColors.tickColor },
                grid: { color: themeColors.gridColor }
            },
            x: {
                ticks: { color: themeColors.tickColor },
                grid: { color: themeColors.gridColor, drawOnChartArea: false }
            }
        },
        plugins: {
            legend: { labels: { color: themeColors.legendColor } }
        }
    };

    if (popularMessagesChartInstance) {
        popularMessagesChartInstance.data.labels = labels;
        popularMessagesChartInstance.data.datasets[0].data = counts;
        Object.assign(popularMessagesChartInstance.options, chartOptions);
        popularMessagesChartInstance.update();
    } else {
        popularMessagesChartInstance = new Chart(ctx, {
            type: 'bar', // Вертикальный бар-чарт
            data: {
                labels: labels,
                datasets: [{
                    label: 'Количество сообщений',
                    data: counts,
                    backgroundColor: 'rgba(75, 192, 192, 0.5)',
                    borderColor: 'rgba(75, 192, 192, 1)',
                    borderWidth: 1
                }]
            },
            options: chartOptions
        });
    }
}

function updateActionTypesChart(actionTypesData) {
    const ctx = document.getElementById('actionTypesChart').getContext('2d');
    const labels = actionTypesData.map(item => item.action_type);
    const counts = actionTypesData.map(item => item.count);
    const currentTheme = document.documentElement.getAttribute('data-theme') || 'light';
    const themeColors = getChartThemeColors(currentTheme);

    const chartOptions = {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
            legend: {
                position: 'top',
                labels: { color: themeColors.legendColor }
            },
            tooltip: {
                callbacks: { /* existing callbacks */ }
            }
            // title: { display: true, text: 'Распределение типов действий', color: themeColors.titleColor } // Example title
        }
    };

    // Генерация случайных цветов для круговой диаграммы
    const backgroundColors = actionTypesData.map(() => 
        `rgba(${Math.floor(Math.random() * 255)}, ${Math.floor(Math.random() * 255)}, ${Math.floor(Math.random() * 255)}, 0.7)`);

    if (actionTypesChartInstance) {
        actionTypesChartInstance.data.labels = labels;
        actionTypesChartInstance.data.datasets[0].data = counts;
        actionTypesChartInstance.data.datasets[0].backgroundColor = backgroundColors;
        Object.assign(actionTypesChartInstance.options, chartOptions);
        actionTypesChartInstance.update();
    } else {
        actionTypesChartInstance = new Chart(ctx, {
            type: 'pie', // Тип диаграммы - круговая
            data: {
                labels: labels,
                datasets: [{
                    label: 'Распределение типов действий',
                    data: counts,
                    backgroundColor: backgroundColors,
                    hoverOffset: 4
                }]
            },
            options: chartOptions
        });
    }
}

function updateActivityOverTimeChart(activityData) {
    const ctx = document.getElementById('activityOverTimeChart').getContext('2d');
    const labels = activityData.map(item => item.period);
    const counts = activityData.map(item => item.count);
    const currentTheme = document.documentElement.getAttribute('data-theme') || 'light';
    const themeColors = getChartThemeColors(currentTheme);

    const chartOptions = {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
            y: {
                beginAtZero: true,
                ticks: { color: themeColors.tickColor },
                grid: { color: themeColors.gridColor }
            },
            x: {
                ticks: { color: themeColors.tickColor },
                grid: { color: themeColors.gridColor, drawOnChartArea: true } // Grid lines for time axis can be useful
            }
        },
        plugins: {
            legend: {
                labels: { color: themeColors.legendColor }
            }
        }
    };

    if (activityOverTimeChartInstance) {
        activityOverTimeChartInstance.data.labels = labels;
        activityOverTimeChartInstance.data.datasets[0].data = counts;
        Object.assign(activityOverTimeChartInstance.options, chartOptions);
        activityOverTimeChartInstance.update();
    } else {
        activityOverTimeChartInstance = new Chart(ctx, {
            type: 'line', // Тип графика - линейный
            data: {
                labels: labels,
                datasets: [{
                    label: 'Количество действий',
                    data: counts,
                    fill: false, // Не заполнять область под линией
                    borderColor: 'rgb(255, 99, 132)', // Цвет линии
                    tension: 0.1 // Сглаживание линии
                }]
            },
            options: chartOptions
        });
    }
}

function openTab(evt, tabName) {
    var i, tabcontent, tablinks;
    // Скрываем все элементы с классом "tab-content"
    tabcontent = document.getElementsByClassName("tab-content");
    for (i = 0; i < tabcontent.length; i++) {
        tabcontent[i].style.display = "none";
    }
    // Удаляем класс "active" у всех кнопок с классом "tab-button"
    tablinks = document.getElementsByClassName("tab-button");
    for (i = 0; i < tablinks.length; i++) {
        tablinks[i].className = tablinks[i].className.replace(" active", "");
    }
    // Показываем текущую вкладку и добавляем класс "active" к кнопке, открывшей вкладку
    document.getElementById(tabName).style.display = "block";
    evt.currentTarget.className += " active";

    // Может потребоваться перерисовка графиков при открытии вкладки, если они не отображаются корректно
}

document.addEventListener('DOMContentLoaded', function() {
    // Initial connections
    connectWebSocket();
    connectLogWebSocket();

    // Re-apply theme to charts when theme is changed
    const themeToggleButton = document.getElementById('theme-toggle-button');
    if (themeToggleButton) {
        themeToggleButton.addEventListener('click', function() {
            // The theme is already changed by theme.js, we just need to update the charts
            // A small delay ensures the 'data-theme' attribute is updated before we read it.
            setTimeout(() => {
                const newTheme = document.documentElement.getAttribute('data-theme');
                const newThemeColors = getChartThemeColors(newTheme);

                Chart.defaults.color = newThemeColors.legendColor;
                Chart.defaults.borderColor = newThemeColors.gridColor;

                [popularCommandsChartInstance, popularMessagesChartInstance, actionTypesChartInstance, activityOverTimeChartInstance].forEach(chart => {
                    if (chart) {
                        if (chart.options.scales) {
                            if (chart.options.scales.x) {
                                if(chart.options.scales.x.ticks) chart.options.scales.x.ticks.color = newThemeColors.tickColor;
                                if(chart.options.scales.x.grid) chart.options.scales.x.grid.color = newThemeColors.gridColor;
                            }
                            if (chart.options.scales.y) {
                                if(chart.options.scales.y.ticks) chart.options.scales.y.ticks.color = newThemeColors.tickColor;
                                if(chart.options.scales.y.grid) chart.options.scales.y.grid.color = newThemeColors.gridColor;
                            }
                        }
                        if (chart.options.plugins && chart.options.plugins.legend && chart.options.plugins.legend.labels) {
                            chart.options.plugins.legend.labels.color = newThemeColors.legendColor;
                        }
                        if (chart.options.plugins && chart.options.plugins.title && chart.options.plugins.title.display) {
                            chart.options.plugins.title.color = newThemeColors.titleColor;
                        }
                        chart.update();
                    }
                });
            }, 0);
        });
    }
});