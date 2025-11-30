document.addEventListener('DOMContentLoaded', function() {
    const pathParts = window.location.pathname.split('/');
    const userId = pathParts[pathParts.length - 1];

    // --- DOM Elements ---
    const profileHeaderElement = document.getElementById('user-profile-header');
    const actionsBodyElement = document.getElementById('actions-body');
    const loadingStatusElement = document.getElementById('loading-status');
    const pageTitle = document.querySelector('title');
    const paginationControlsElement = document.getElementById('pagination-controls');
    const searchInput = document.getElementById('search-input');
    
    const messageForm = document.getElementById('send-message-form');
    const messageInput = document.getElementById('message-input');
    const sendBtn = document.getElementById('send-btn');

    if (!userId) {
        actionsBodyElement.innerHTML = `<div class="text-red-500 text-center w-full mt-4">ID пользователя не найден в URL.</div>`;
        return;
    }

    // --- State Variables ---
    let isFirstLoad = true;
    let currentSortBy = 'timestamp';
    let currentSortOrder = 'desc'; // Получаем от API: [Новые ... Старые]
    let lastDateRendered = null;   // Для группировки сообщений по датам
    let socket = null;

    // =========================================================================
    // 1. WEBSOCKET CONNECTION (Real-time updates)
    // =========================================================================
    function connectWebSocket() {
        const wsProtocol = window.location.protocol === "https:" ? "wss:" : "ws:";
        const wsUrl = `${wsProtocol}//${window.location.host}/ws/users/${userId}`;
        
        console.log(`Connecting to WebSocket: ${wsUrl}`);
        socket = new WebSocket(wsUrl);

        socket.onopen = function() {
            console.log("WebSocket connected.");
        };

        socket.onmessage = function(event) {
            try {
                const action = JSON.parse(event.data);
                // Добавляем сообщение и скроллим вниз
                appendSingleMessage(action, true); 
            } catch (e) {
                console.error("Error parsing WebSocket message:", e);
            }
        };

        socket.onclose = function(e) {
            console.log('WebSocket closed. Reconnecting in 3s...');
            setTimeout(connectWebSocket, 3000);
        };

        socket.onerror = function(err) {
            console.error('WebSocket error:', err);
            socket.close();
        };
    }

    // Запускаем подключение
    connectWebSocket();


    // =========================================================================
    // 2. DATA FETCHING (History)
    // =========================================================================
    function fetchAndRenderPage(page = 1) {
        loadingStatusElement.textContent = 'Загрузка...';
        // Легкая прозрачность при загрузке
        actionsBodyElement.classList.add('opacity-50'); 

        fetch(`/api/users/${userId}/profile?page=${page}&sort_by=${currentSortBy}&sort_order=${currentSortOrder}`)
            .then(response => {
                if (!response.ok) {
                    if (response.status === 404) throw new Error('Пользователь не найден.');
                    throw new Error(`Ошибка сети: ${response.statusText}`);
                }
                return response.json();
            })
            .then(data => {
                actionsBodyElement.classList.remove('opacity-50');
                loadingStatusElement.textContent = '';

                if (isFirstLoad) {
                    renderUserProfile(data.user_details);
                    isFirstLoad = false;
                }

                // Очищаем чат перед рендерингом страницы истории
                actionsBodyElement.innerHTML = '';
                lastDateRendered = null;

                renderChatHistory(data.actions);
                renderPaginationControls(data.pagination);
                
                // Применяем фильтр поиска (если там что-то введено)
                applySearchFilter();
            })
            .catch(error => {
                console.error('Fetch Error:', error);
                loadingStatusElement.textContent = `Ошибка: ${error.message}`;
                actionsBodyElement.innerHTML = `<div class="text-red-500 text-center w-full p-4">Не удалось загрузить данные.</div>`;
                actionsBodyElement.classList.remove('opacity-50');
            });
    }

    // =========================================================================
    // 3. RENDERING LOGIC
    // =========================================================================

    function renderUserProfile(user) {
        pageTitle.textContent = `${user.full_name} | Чат`;

        let avatarHtml = '';
        if (user.avatar_pic_url) {
            avatarHtml = `<img src="${user.avatar_pic_url}" alt="Avatar" class="w-10 h-10 rounded-full object-cover border border-gray-300 dark:border-gray-600">`;
        } else {
            const initial = (user.full_name && user.full_name.trim().length > 0) ? user.full_name.trim()[0].toUpperCase() : '?';
            avatarHtml = `<div class="fallback-avatar w-10 h-10 text-base">${initial}</div>`;
        }

        const usernameText = user.username && user.username !== 'Нет username' 
            ? `<a href="https://t.me/${user.username}" target="_blank" class="text-blue-500 hover:underline">@${user.username}</a>` 
            : `<span class="text-gray-400">ID: ${user.user_id}</span>`;

        profileHeaderElement.innerHTML = `
            ${avatarHtml}
            <div class="leading-tight">
                <h1 class="font-bold text-gray-900 dark:text-white text-lg line-clamp-1">${user.full_name}</h1>
                <div class="text-sm text-gray-500 dark:text-gray-400">${usernameText}</div>
            </div>
        `;
    }

    function renderChatHistory(actions) {
        if (actions.length === 0) {
            actionsBodyElement.innerHTML = `<div class="w-full text-center text-gray-500 mt-10">История действий пуста.</div>`;
            return;
        }

        // API возвращает данные от Новых к Старым (DESC).
        // Для чата нам нужно рендерить от Старых к Новым (сверху вниз).
        // Поэтому переворачиваем массив.
        const chronoActions = [...actions].reverse();

        chronoActions.forEach(action => {
            appendSingleMessage(action, false); // false = не скроллить на каждом сообщении
        });

        // Скроллим в самый низ после рендера всей истории
        scrollToBottom();
    }

    /**
     * Создает и добавляет одно сообщение в DOM.
     * Используется и при загрузке истории, и при получении сообщения по WebSocket.
     */
    function appendSingleMessage(action, shouldScroll = false) {
        const dateObj = new Date(action.timestamp);
        const dateStr = dateObj.toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' });
        const timeStr = dateObj.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });

        // --- Date Pill Logic ---
        // Если дата изменилась по сравнению с предыдущим сообщением, вставляем разделитель
        if (dateStr !== lastDateRendered) {
            const datePill = document.createElement('div');
            datePill.className = 'date-pill sticky top-2 z-10 shadow-sm backdrop-blur-sm self-center';
            datePill.textContent = dateStr;
            actionsBodyElement.appendChild(datePill);
            lastDateRendered = dateStr;
        }

        // --- Bubble Logic ---
        const bubble = document.createElement('div');
        
        // Определяем тип сообщения
        const isCommand = action.action_type === 'command';
        const isAdminMessage = action.action_type === 'admin_message'; 
        
        // outgoing = справа (синие/зеленые), остальные = слева (белые/серые)
        bubble.className = `message-bubble ${isCommand ? 'command' : ''} ${isAdminMessage ? 'outgoing' : ''}`;

        // Если это новое сообщение (через сокет), добавим анимацию
        if (shouldScroll) {
            bubble.classList.add('animate-fade-in-up'); // Убедитесь, что класс есть в CSS или Tailwind
        }

        let contentHtml = '';
        let icon = '';

        if (isAdminMessage) {
            // Сообщение от Админа (исходящее)
            icon = '';
            contentHtml = `<span class="whitespace-pre-wrap">${action.action_details}</span>`;
        } else if (isCommand) {
            icon = '🤖';
            contentHtml = `<span class="font-mono text-blue-600 dark:text-blue-400 font-semibold">${action.action_details}</span>`;
        } else if (action.action_type === 'text_message') {
            icon = '💬';
            contentHtml = `<span class="whitespace-pre-wrap">${action.action_details || 'Empty message'}</span>`;
        } else if (action.action_type === 'callback_query') {
            icon = '👆';
            contentHtml = `<span class="italic text-gray-500">Нажал:</span> <span class="font-mono bg-gray-200 dark:bg-gray-700 px-1 rounded text-xs">${action.action_details}</span>`;
        } else {
            icon = '⚡';
            contentHtml = `<span class="text-sm">${action.action_type}: ${action.action_details}</span>`;
        }

        // Иконку показываем только для входящих сообщений
        const iconHtml = icon && !isAdminMessage ? `<span class="text-lg select-none mr-2">${icon}</span>` : '';

        // Ставим галочку для исходящих (имитация статуса)
        const checkMark = isAdminMessage ? '<span class="ml-1 text-blue-400">✓</span>' : '';

        bubble.innerHTML = `
            <div class="flex items-start">
                ${iconHtml}
                <div class="flex-grow text-sm break-words min-w-0">${contentHtml}</div>
            </div>
            <div class="message-meta flex justify-end items-center">
                <span>${timeStr}</span>
                ${checkMark}
            </div>
        `;

        actionsBodyElement.appendChild(bubble);

        if (shouldScroll) {
            scrollToBottom();
        }
    }

    function scrollToBottom() {
        // Используем requestAnimationFrame для плавности
        requestAnimationFrame(() => {
            actionsBodyElement.scrollTo({
                top: actionsBodyElement.scrollHeight,
                behavior: 'smooth'
            });
        });
    }

    // =========================================================================
    // 4. FORM HANDLING (Send Message)
    // =========================================================================

    // Auto-resize Textarea
    messageInput.addEventListener('input', function() {
        this.style.height = 'auto';
        this.style.height = (this.scrollHeight) + 'px';
        if(this.value === '') this.style.height = '46px';
    });

    // Ctrl + Enter to submit
    messageInput.addEventListener('keydown', function(e) {
        if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
            e.preventDefault();
            messageForm.dispatchEvent(new Event('submit'));
        }
    });

    messageForm.addEventListener('submit', function(e) {
        e.preventDefault();
        const text = messageInput.value.trim();
        if (!text) return;

        // Сохраняем состояние кнопки
        const originalBtnContent = sendBtn.innerHTML; 
        
        // Показываем спиннер
        sendBtn.innerHTML = '<svg class="animate-spin h-5 w-5 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>';
        sendBtn.disabled = true;
        messageInput.disabled = true;

        fetch(`/api/users/${userId}/send_message`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text: text })
        })
        .then(response => {
            if (!response.ok) return response.json().then(err => { throw new Error(err.detail || 'Ошибка отправки') });
            return response.json();
        })
        .then(data => {
            // Успех: Очищаем поле ввода
            messageInput.value = '';
            messageInput.style.height = '46px'; // Сброс высоты
            messageInput.focus();
            
            // ВАЖНО: Мы НЕ добавляем сообщение вручную в DOM.
            // Мы ждем, пока оно придет через WebSocket (это гарантирует, что оно сохранено).
            // Это происходит очень быстро (<100мс).
        })
        .catch(error => {
            alert(`Не удалось отправить сообщение: ${error.message}`);
        })
        .finally(() => {
            // Возвращаем кнопку в исходное состояние
            sendBtn.innerHTML = originalBtnContent;
            sendBtn.disabled = false;
            messageInput.disabled = false;
            // Фокус возвращаем только если не было ошибки, чтобы пользователь мог исправить текст
            if (!messageInput.value) messageInput.focus();
        });
    });

    // =========================================================================
    // 5. PAGINATION & HELPERS
    // =========================================================================

    function renderPaginationControls(pagination) {
        paginationControlsElement.innerHTML = '';
        if (pagination.total_pages <= 1) return;

        const { current_page, total_pages } = pagination;

        const createButton = (text, page, isActive = false) => {
            const btn = document.createElement('button');
            btn.innerHTML = text;
            btn.className = `px-3 py-1 rounded transition text-xs border ${isActive 
                ? 'bg-blue-100 text-blue-700 border-blue-200 font-bold dark:bg-blue-900 dark:text-blue-200 dark:border-blue-800' 
                : 'bg-white text-gray-600 border-gray-300 hover:bg-gray-50 dark:bg-gray-700 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-600'}`;
            
            if (!isActive) {
                btn.addEventListener('click', (e) => {
                    e.preventDefault();
                    fetchAndRenderPage(page);
                });
            } else {
                btn.disabled = true;
            }
            return btn;
        };

        if (current_page > 1) {
            paginationControlsElement.appendChild(createButton('←', current_page - 1));
        }
        
        paginationControlsElement.appendChild(createButton(current_page, current_page, true));

        if (current_page < total_pages) {
            paginationControlsElement.appendChild(createButton('→', current_page + 1));
        }
    }

    function applySearchFilter() {
        const term = searchInput.value.toLowerCase().trim();
        const bubbles = actionsBodyElement.querySelectorAll('.message-bubble');
        
        bubbles.forEach(bubble => {
            const text = bubble.textContent.toLowerCase();
            if (!term || text.includes(term)) {
                bubble.style.display = 'block';
            } else {
                bubble.style.display = 'none';
            }
        });

        // Скрываем даты, если идет поиск, чтобы не мешались
        const dates = actionsBodyElement.querySelectorAll('.date-pill');
        dates.forEach(d => d.style.display = term ? 'none' : 'block');
    }
    
    // Debounce для поиска
    function debounce(func, delay) {
        let timeout;
        return function(...args) {
            clearTimeout(timeout);
            timeout = setTimeout(() => func.apply(this, args), delay);
        };
    }

    searchInput.addEventListener('input', debounce(applySearchFilter, 300));
    
    // Экспорт CSV
    document.getElementById('download-all-csv-btn').addEventListener('click', () => {
       window.location.href = `/api/users/${userId}/export_actions`;
    });

    // --- INITIALIZATION ---
    fetchAndRenderPage(1);
});