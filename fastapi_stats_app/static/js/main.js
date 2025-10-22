const totalActionsValueElement = document.getElementById('total-actions-value');
const leaderboardBodyElement = document.getElementById('leaderboard-body');
const popularActionsStatusElement = document.getElementById('popular-actions-status');
const actionTypesStatusElement = document.getElementById('action-types-status');
const activityOverTimeStatusElement = document.getElementById('activity-over-time-status');
const botLogContentElement = document.getElementById('bot-log-content');
const botLogStatusElement = document.getElementById('bot-log-status');
const lastUpdatedContainer = document.getElementById('last-updated-container');
const lastUpdatedValueElement = document.getElementById('last-updated-value');
const downloadButtons = {
};

let popularActionsChartInstance; // Для нового комбинированного графика
let actionTypesChartInstance; // Для графика типов действий
let activityOverTimeChartInstance; // Для графика активности по времени

// Определяем URL для WebSocket. Если используется HTTPS, нужен wss://
const wsProtocol = window.location.protocol === "https:" ? "wss:" : "ws:";
const wsHost = window.location.host; // localhost:9583 или ваш домен
const statsWsUrl = `${wsProtocol}//${wsHost}/ws/stats/total_actions`;
const logWsUrl = `${wsProtocol}//${wsHost}/ws/bot_log`;

/**
 * A map to store the latest data for each chart, used for CSV downloads.
 */
const chartDataStore = {};

/**
 * A resilient WebSocket connection manager with exponential backoff.
 */
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
        this.maxRetryCount = 8; // After this, the delay will be fixed at the max
    }

    connect() {
        if (this.socket && this.socket.readyState === WebSocket.OPEN) {
            console.log(`WebSocket to ${this.url} is already open.`);
            return;
        }

        console.log(`Attempting to connect to ${this.url}...`);
        this.socket = new WebSocket(this.url);

        this.socket.onopen = (event) => {
            console.log(`WebSocket connection established to ${this.url}.`);
            this.retryCount = 0; // Reset retry counter on successful connection
            if (this.onOpen) this.onOpen(event);
        };

        this.socket.onmessage = (event) => {
            if (this.onMessage) this.onMessage(event);
        };

        this.socket.onerror = (error) => {
            console.error(`WebSocket error on ${this.url}:`, error);
            if (this.onError) this.onError(error);
            // The 'onclose' event will be fired next, where we handle reconnection.
        };

        this.socket.onclose = (event) => {
            console.log(`WebSocket to ${this.url} closed. Code: ${event.code}.`);
            if (this.onClose) this.onClose(event);
            this.reconnect();
        };
    }

    reconnect() {
        if (this.reconnectTimeoutId) {
            clearTimeout(this.reconnectTimeoutId);
        }

        // Exponential backoff: 1s, 2s, 4s, 8s, ..., up to a max of ~60s
        const delay = Math.min(1000 * (2 ** this.retryCount), 60000);
        console.log(`Will attempt to reconnect to ${this.url} in ${delay / 1000} seconds.`);
        
        this.reconnectTimeoutId = setTimeout(() => {
            if (this.retryCount < this.maxRetryCount) {
                this.retryCount++;
            }
            this.connect();
        }, delay);
    }
}

function handleStatsSocketOpen() {
        console.log("WebSocket соединение установлено.");
        totalActionsValueElement.textContent = "Ожидание данных...";
    };

function handleStatsSocketMessage(event) {
        try {
            const data = JSON.parse(event.data);
            if (data.error) {
                console.error("WebSocket Server Error:", data.error); // Ошибка от сервера
                totalActionsValueElement.textContent = `Ошибка: ${data.error}`;
                leaderboardBodyElement.innerHTML = `<tr><td colspan="6" style="text-align:center;">Ошибка: ${data.error}</td></tr>`;
                popularActionsStatusElement.textContent = `Ошибка загрузки графика: ${data.error}`;
                if (popularActionsChartInstance) { popularActionsChartInstance.destroy(); popularActionsChartInstance = null; }
                actionTypesStatusElement.textContent = `Ошибка загрузки графика: ${data.error}`;
                if (actionTypesChartInstance) { actionTypesChartInstance.destroy(); actionTypesChartInstance = null; }
                activityOverTimeStatusElement.textContent = `Ошибка загрузки графика: ${data.error}`;
                if (activityOverTimeChartInstance) { activityOverTimeChartInstance.destroy(); activityOverTimeChartInstance = null; }
            } else if (data.total_actions !== undefined) {
                if (data.last_updated) {
                    const date = new Date(data.last_updated);
                    lastUpdatedValueElement.textContent = date.toLocaleString('ru-RU');
                    lastUpdatedContainer.style.display = 'block';
                }

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

            // Store data for the combined chart
            if (data.popular_commands) chartDataStore.popularCommands = data.popular_commands;
            if (data.popular_messages) chartDataStore.popularMessages = data.popular_messages;

            // Update the combined chart if we have data for it
            if (chartDataStore.popularCommands || chartDataStore.popularMessages) {
                updateCombinedPopularActionsChart();
            }

            if (data.action_types_distribution && Array.isArray(data.action_types_distribution)) {
                if (data.action_types_distribution.length === 0) {
                    actionTypesStatusElement.textContent = "Нет данных о типах действий.";
                    document.querySelector('.download-csv-btn[data-chart="actionTypes"]').style.display = 'none'; // Keep this for other charts
                    if (actionTypesChartInstance) { actionTypesChartInstance.destroy(); actionTypesChartInstance = null; }
                } else {
                    actionTypesStatusElement.textContent = "";
                    chartDataStore.actionTypes = data.action_types_distribution; // Keep this
                    document.querySelector('.download-csv-btn[data-chart="actionTypes"]').style.display = 'inline-block';
                    updateActionTypesChart(data.action_types_distribution);
                }
            }

            if (data.activity_over_time) { // Now an object
                const dayData = data.activity_over_time.day || [];
                if (dayData.length === 0) {
                    activityOverTimeStatusElement.textContent = "Нет данных об активности для отображения.";
                    document.querySelector('.download-csv-btn[data-chart="activityOverTime"]').style.display = 'none'; // Keep this
                    if (activityOverTimeChartInstance) { activityOverTimeChartInstance.destroy(); activityOverTimeChartInstance = null; }
                } else {
                    activityOverTimeStatusElement.textContent = "";
                    chartDataStore.activityOverTime = data.activity_over_time; // Keep this
                    updateActivityOverTimeChart(); // Initial render with default 'day'
                }
            }

        } catch (e) {
            console.error("Ошибка парсинга WebSocket данных:", e, "Данные:", event.data);
            totalActionsValueElement.textContent = "Ошибка обработки данных";
            leaderboardBodyElement.innerHTML = `<tr><td colspan="6" style="text-align:center;">Ошибка обработки данных.</td></tr>`;
            popularActionsStatusElement.textContent = "Ошибка обработки данных для графика.";
            actionTypesStatusElement.textContent = "Ошибка обработки данных для графика.";
            activityOverTimeStatusElement.textContent = "Ошибка обработки данных для графика.";
            }
    };
function handleStatsSocketError(error) {
        console.error("WebSocket ошибка:", error);
        totalActionsValueElement.textContent = "Ошибка соединения WebSocket";
        leaderboardBodyElement.innerHTML = `<tr><td colspan="6" style="text-align:center;">Ошибка соединения.</td></tr>`;
        popularActionsStatusElement.textContent = "Ошибка соединения WebSocket для графика.";
        actionTypesStatusElement.textContent = "Ошибка соединения WebSocket для графика.";
        activityOverTimeStatusElement.textContent = "Ошибка соединения WebSocket для графика.";
        if (popularActionsChartInstance) { popularActionsChartInstance.destroy(); popularActionsChartInstance = null; }
        if (actionTypesChartInstance) { actionTypesChartInstance.destroy(); actionTypesChartInstance = null; }
        if (activityOverTimeChartInstance) { activityOverTimeChartInstance.destroy(); activityOverTimeChartInstance = null; }
    };
function handleStatsSocketClose() {
        // UI updates for reconnection attempt
        totalActionsValueElement.textContent = "Соединение потеряно. Попытка переподключения через 5с...";
        // Попытка переподключения через некоторое время
        leaderboardBodyElement.innerHTML = `<tr><td colspan="6" style="text-align:center;">Соединение потеряно. Попытка переподключения...</td></tr>`;
        popularActionsStatusElement.textContent = "Соединение для графика потеряно. Попытка переподключения...";
        actionTypesStatusElement.textContent = "Соединение для графика потеряно. Попытка переподключения...";
        activityOverTimeStatusElement.textContent = "Соединение для графика потеряно. Попытка переподключения...";
        if (popularActionsChartInstance) { popularActionsChartInstance.destroy(); popularActionsChartInstance = null; }
        if (actionTypesChartInstance) { actionTypesChartInstance.destroy(); actionTypesChartInstance = null; }
        if (activityOverTimeChartInstance) { activityOverTimeChartInstance.destroy(); activityOverTimeChartInstance = null; }
    };

function handleLogSocketOpen() {
    botLogContentElement.innerHTML = ''; // Очищаем при новом подключении
    botLogStatusElement.textContent = 'Соединение с логом установлено. Ожидание данных...';
};

function handleLogSocketMessage(event) {
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

function handleLogSocketError(error) {
        console.error("Log WebSocket ошибка:", error);
        botLogStatusElement.textContent = 'Ошибка соединения с логом WebSocket.';
        const errorEntry = document.createElement('div');
        errorEntry.textContent = `ОШИБКА СОЕДИНЕНИЯ: ${error}`;
        errorEntry.style.color = 'red';
        botLogContentElement.appendChild(errorEntry);
};

function handleLogSocketClose() {
        botLogStatusElement.textContent = 'Соединение с логом потеряно. Попытка переподключения через 5с...';
}

/**
 * Generates and triggers the download of a CSV file.
 * @param {string[]} headers - The column headers for the CSV.
 * @param {object[]} data - An array of objects representing the rows.
 * @param {string} filename - The desired name for the downloaded file.
 */
function downloadCSV(headers, data, filename) {
    if (!data || data.length === 0) {
        console.warn("No data available to download.");
        return;
    }

    const keys = Object.keys(data[0]);
    const csvRows = [
        headers.join(','), // Header row
        ...data.map(row => 
            keys.map(key => {
                let cell = row[key] === null || row[key] === undefined ? '' : String(row[key]);
                // Escape commas and quotes
                if (cell.includes(',') || cell.includes('"') || cell.includes('\n')) {
                    cell = `"${cell.replace(/"/g, '""')}"`;
                }
                return cell;
            }).join(',')
        )
    ];

    const csvContent = "data:text/csv;charset=utf-8," + csvRows.join('\n');
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", filename);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
}

/**
 * A generic function to create or update a Chart.js instance.
 * @param {object} config - The configuration for the chart.
 * @returns {Chart} The created or updated chart instance.
 */
function updateChart(config) {
    const {
        instance,
        ctx,
        data,
        type,
        labelKey,
        countKey,
        datasetLabel,
        backgroundColor,
        borderColor,
        extraOptions = {}
    } = config;

    const labels = data.map(item => item[labelKey]);
    const counts = data.map(item => item[countKey]);
    const currentTheme = document.documentElement.getAttribute('data-theme') || 'light';
    const themeColors = getChartThemeColors(currentTheme);

    // Base options, merged with any extra options provided
    const chartOptions = { ...{
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
            legend: {
                labels: { color: themeColors.legendColor }
            }
        }
    }, ...extraOptions };

    // Add scales for non-pie charts
    if (type !== 'pie') {
        chartOptions.scales = {
            y: { beginAtZero: true, ticks: { color: themeColors.tickColor }, grid: { color: themeColors.gridColor } },
            x: { ticks: { color: themeColors.tickColor }, grid: { color: themeColors.gridColor, drawOnChartArea: type !== 'bar' } }
        };
    }

    // Prepare dataset
    const dataset = {
        label: datasetLabel,
        data: counts,
        borderWidth: 1
    };

    // Type-specific dataset properties
    if (type === 'pie') {
        dataset.backgroundColor = data.map(() => `rgba(${Math.floor(Math.random() * 255)}, ${Math.floor(Math.random() * 255)}, ${Math.floor(Math.random() * 255)}, 0.7)`);
        dataset.hoverOffset = 4;
    } else if (type === 'line') {
        dataset.backgroundColor = backgroundColor;
        dataset.borderColor = borderColor;
        dataset.fill = false;
        dataset.tension = 0.1;
    } else {
        dataset.backgroundColor = backgroundColor;
        dataset.borderColor = borderColor;
    }

    if (instance) {
        instance.data.labels = labels;
        instance.data.datasets[0] = dataset;
        Object.assign(instance.options, chartOptions);
        instance.update();
        return instance;
    } else {
        return new Chart(ctx, { type, data: { labels, datasets: [dataset] }, options: chartOptions });
    }
}

function renderModalContent(title, data) {
    const modal = document.getElementById('user-list-modal');
    const modalTitle = document.getElementById('modal-title');
    const modalBody = document.getElementById('modal-body');
    const downloadBtn = document.getElementById('modal-download-csv-btn');
    const paginationControls = document.getElementById('modal-pagination-controls');

    modalTitle.textContent = `Пользователи для: "${title}"`;
    paginationControls.innerHTML = '';

    const renderHeaders = () => {
        const { sort_by, sort_order } = data.pagination;
        const headers = [
            { key: 'full_name', text: 'Полное имя' },
            { key: 'username', text: 'Тэг' },
            { key: 'user_id', text: 'ID' }
        ];

        return headers.map(h => {
            const isSorted = h.key === sort_by;
            const sortClass = isSorted ? (sort_order === 'asc' ? 'sort-asc' : 'sort-desc') : '';
            return `<th class="sortable ${sortClass}" data-sort-by="${h.key}">${h.text}</th>`;
        }).join('');
    };

    if (data.users.length === 0) {
        modalBody.innerHTML = '<p>Нет данных о пользователях для этого действия.</p>';
        downloadBtn.style.display = 'none';
    } else {
        const userRows = data.users.map(user => `
            <tr>
                <td><a href="/users/${user.user_id}" target="_blank">${user.full_name}</a></td>
                <td>${user.username}</td>
                <td>${user.user_id}</td>
            </tr>
        `).join('');

        modalBody.innerHTML = `<table><thead><tr>${renderHeaders()}</tr></thead><tbody>${userRows}</tbody></table>`;
        downloadBtn.style.display = 'inline-block';

        // --- CSV Download Logic ---
        const newDownloadBtn = downloadBtn.cloneNode(true);
        downloadBtn.parentNode.replaceChild(newDownloadBtn, downloadBtn);
        newDownloadBtn.addEventListener('click', () => {
            const headers = ['UserID', 'FullName', 'Username'];
            const dataToExport = data.users.map(u => ({ user_id: u.user_id, full_name: u.full_name, username: u.username }));
            const safeTitle = title.replace(/[^a-z0-9]/gi, '_').toLowerCase();
            downloadCSV(headers, dataToExport, `users_for_${safeTitle}.csv`);
        });

        // --- Pagination Controls Logic ---
        const { current_page, total_pages } = data.pagination;
        if (total_pages > 1) {
            const createButton = (text, page, isDisabled = false) => {
                const button = document.createElement('button');
                button.textContent = text;
                button.className = 'pagination-button';
                if (current_page === page) button.classList.add('active');
                button.disabled = isDisabled || current_page === page;
                if (!button.disabled) {
                    button.addEventListener('click', () => fetchUsersForModal(title, clickedActionType, page, data.pagination.sort_by, data.pagination.sort_order));
                }
                return button;
            };

            paginationControls.appendChild(createButton('«', current_page - 1, current_page === 1));
            const pageInfo = document.createElement('span');
            pageInfo.textContent = `${current_page} / ${total_pages}`;
            pageInfo.style.padding = '0 5px';
            paginationControls.appendChild(pageInfo);
            paginationControls.appendChild(createButton('»', current_page + 1, current_page === total_pages));

            // Add "go to page" input if there are many pages
            if (total_pages > 5) {
                const goToInput = document.createElement('input');
                goToInput.type = 'number';
                goToInput.min = 1;
                goToInput.max = total_pages;
                goToInput.placeholder = '...';
                goToInput.className = 'pagination-goto-input';
                paginationControls.appendChild(goToInput);

                const goButton = createButton('Перейти', -1);
                goButton.addEventListener('click', () => {
                    const page = parseInt(goToInput.value, 10);
                    if (page >= 1 && page <= total_pages) {
                        fetchUsersForModal(title, clickedActionType, page, data.pagination.sort_by, data.pagination.sort_order);
                    }
                });
                paginationControls.appendChild(goButton);
            }
        }

        // Add sort event listeners
        modalBody.querySelectorAll('th.sortable').forEach(th => {
            th.addEventListener('click', (event) => {
                const newSortBy = event.target.dataset.sortBy;
                let newSortOrder = 'asc';
                if (newSortBy === data.pagination.sort_by && data.pagination.sort_order === 'asc') {
                    newSortOrder = 'desc';
                }
                fetchUsersForModal(title, clickedActionType, 1, newSortBy, newSortOrder);
            });
        });
    }
}

let clickedActionType = ''; // Store the type of the clicked action

const modalUserListCache = new Map(); // Cache for user lists in the modal

function fetchUsersForModal(title, type, page = 1, sortBy = 'full_name', sortOrder = 'asc') {
    const modalBody = document.getElementById('modal-body');
    const cacheKey = `${type}:${title}:${page}:${sortBy}:${sortOrder}`;

    // Check cache first
    if (modalUserListCache.has(cacheKey)) {
        console.log(`Cache hit for user list: ${cacheKey}`);
        renderModalContent(title, modalUserListCache.get(cacheKey));
        return;
    }

    console.log(`Cache miss for user list: ${cacheKey}. Fetching...`);
    modalBody.innerHTML = 'Загрузка...';
    document.getElementById('modal-pagination-controls').innerHTML = '';
    document.getElementById('modal-download-csv-btn').style.display = 'none';

    fetch(`/api/stats/action_users?action_type=${type}&action_details=${encodeURIComponent(title)}&page=${page}&sort_by=${sortBy}&sort_order=${sortOrder}`)
        .then(response => {
            if (!response.ok) throw new Error('Network response was not ok');
            return response.json();
        })
        .then(data => {
            // Store in cache before rendering
            modalUserListCache.set(cacheKey, data);
            renderModalContent(title, data);
        })
        .catch(error => {
            console.error('Error fetching users for action:', error);
            modalBody.innerHTML = '<p style="color: red;">Не удалось загрузить список пользователей.</p>';
        });
}


function handleChartClick(event, chart, chartData) {
    const points = chart.getElementsAtEventForMode(event, 'nearest', { intersect: true }, true);

    if (points.length) {
        const firstPoint = points[0];
        const clickedData = chartData[firstPoint.index];
        if (!clickedData) return;

        const { label, type } = clickedData;
        clickedActionType = type; // Store for pagination clicks

        // Show modal immediately with loading state
        document.getElementById('user-list-modal').style.display = 'block';
        document.getElementById('modal-title').textContent = `Пользователи для: "${label}"`;
        
        // Fetch the first page of data
        fetchUsersForModal(label, type, 1);
    }
}

function updateCombinedPopularActionsChart() {
    const filter = document.querySelector('input[name="actionFilter"]:checked').value;
    const commands = (chartDataStore.popularCommands || []).map(d => ({ label: d.command, count: d.count, type: 'command' }));
    const messages = (chartDataStore.popularMessages || []).map(d => ({ label: d.message, count: d.count, type: 'message' }));

    let combinedData = [];
    if (filter === 'all') {
        combinedData = [...commands, ...messages];
    } else if (filter === 'commands') {
        combinedData = commands;
    } else if (filter === 'messages') {
        combinedData = messages;
    }

    combinedData.sort((a, b) => b.count - a.count);
    const topData = combinedData.slice(0, 15); // Show top 15 combined

    if (topData.length === 0) {
        popularActionsStatusElement.textContent = "Нет данных для отображения.";
        document.querySelector('.download-csv-btn[data-chart="popularActions"]').style.display = 'none';
        if (popularActionsChartInstance) { popularActionsChartInstance.destroy(); popularActionsChartInstance = null; }
        return;
    }

    popularActionsStatusElement.textContent = "";
    chartDataStore.popularActions = topData; // For CSV download
    document.querySelector('.download-csv-btn[data-chart="popularActions"]').style.display = 'inline-block';

    popularActionsChartInstance = updateChart({
        instance: popularActionsChartInstance,
        ctx: document.getElementById('popularActionsChart').getContext('2d'),
        data: topData, type: 'bar', labelKey: 'label', countKey: 'count',
        datasetLabel: 'Количество',
        backgroundColor: topData.map(d => d.type === 'command' ? 'rgba(54, 162, 235, 0.5)' : 'rgba(75, 192, 192, 0.5)'),
        borderColor: topData.map(d => d.type === 'command' ? 'rgba(54, 162, 235, 1)' : 'rgba(75, 192, 192, 1)'),
        extraOptions: {
            onClick: (event, elements, chart) => handleChartClick(event, chart, topData)
        }
    });
}

const updateActionTypesChart = (data) => {
    actionTypesChartInstance = updateChart({
        instance: actionTypesChartInstance,
        ctx: document.getElementById('actionTypesChart').getContext('2d'),
        data, type: 'pie', labelKey: 'action_type', countKey: 'count',
        datasetLabel: 'Распределение типов действий',
        extraOptions: { plugins: { legend: { position: 'top' } } }
    });
};

const updateActivityOverTimeChart = () => {
    const filter = document.querySelector('input[name="timeFilter"]:checked').value;
    const data = chartDataStore.activityOverTime ? chartDataStore.activityOverTime[filter] : [];

    // Update download button visibility based on filtered data
    document.querySelector('.download-csv-btn[data-chart="activityOverTime"]').style.display = data.length > 0 ? 'inline-block' : 'none';

    activityOverTimeChartInstance = updateChart({
        instance: activityOverTimeChartInstance,
        ctx: document.getElementById('activityOverTimeChart').getContext('2d'),
        data, type: 'line', labelKey: 'period', countKey: 'count',
        datasetLabel: 'Количество действий',
        borderColor: 'rgb(255, 99, 132)',
    });
};

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
    const statsSocketManager = new WebSocketManager(statsWsUrl, {
        onOpen: handleStatsSocketOpen,
        onMessage: handleStatsSocketMessage,
        onError: handleStatsSocketError,
        onClose: handleStatsSocketClose
    });
    statsSocketManager.connect();

    const logSocketManager = new WebSocketManager(logWsUrl, {
        onOpen: handleLogSocketOpen,
        onMessage: handleLogSocketMessage,
        onError: handleLogSocketError,
        onClose: handleLogSocketClose
    });
    logSocketManager.connect();

    // Add event listeners for all download buttons
    document.querySelectorAll('.download-csv-btn').forEach(button => {
        button.addEventListener('click', (event) => {
            const chartType = event.target.dataset.chart;
            const data = chartDataStore[chartType];
            if (!data) return;

            const headerMap = {
                popularActions: ['Action', 'Count', 'Type'],
                actionTypes: ['Action Type', 'Count'],
                // For activity, we need to know which period is active
                activityOverTime: ['Period', 'Count'] 
            };

            downloadCSV(headerMap[chartType], data, `${chartType}_export.csv`);
        });
    });

    // Add event listener for the new filter radio buttons
    document.querySelectorAll('input[name="actionFilter"]').forEach(radio => {
        radio.addEventListener('change', updateCombinedPopularActionsChart);
    });

    // Add event listener for the activity time filter
    document.querySelectorAll('input[name="timeFilter"]').forEach(radio => {
        radio.addEventListener('change', updateActivityOverTimeChart);
    });

    // Add event listeners for the modal
    const modal = document.getElementById('user-list-modal');
    const closeBtn = document.querySelector('.modal-close-btn');
    const closeModal = () => {
        modal.style.display = "none";
        // Clear the cache when the modal is closed to ensure fresh data next time
        modalUserListCache.clear();
        console.log("Modal user list cache cleared.");
    };

    closeBtn.onclick = closeModal;
    window.onclick = (event) => {
        if (event.target == modal) {
            closeModal();
        }
    };


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

                [popularActionsChartInstance, actionTypesChartInstance, activityOverTimeChartInstance].forEach(chart => {
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

    // --- Back to Top Button Logic ---
    const backToTopButton = document.getElementById('back-to-top-btn');

    if (backToTopButton) {
        window.onscroll = function() {
            if (document.body.scrollTop > 100 || document.documentElement.scrollTop > 100) {
                backToTopButton.style.display = "block";
            } else {
                backToTopButton.style.display = "none";
            }
        };

        backToTopButton.addEventListener('click', function() {
            // For Safari
            document.body.scrollTop = 0;
            // For Chrome, Firefox, IE and Opera
            document.documentElement.scrollTop = 0;
        });
    }
});