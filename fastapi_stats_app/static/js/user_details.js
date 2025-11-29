document.addEventListener('DOMContentLoaded', function() {
    const pathParts = window.location.pathname.split('/');
    const userId = pathParts[pathParts.length - 1];

    const profileHeaderElement = document.getElementById('user-profile-header');
    const actionsBodyElement = document.getElementById('actions-body');
    const loadingStatusElement = document.getElementById('loading-status');
    const pageTitle = document.querySelector('title');
    const paginationControlsElement = document.getElementById('pagination-controls');
    const searchInput = document.getElementById('search-input');

    if (!userId) {
        actionsBodyElement.innerHTML = `<div class="text-red-500 text-center w-full">ID пользователя не найден.</div>`;
        return;
    }

    let isFirstLoad = true;
    let currentSortBy = 'timestamp';
    let currentSortOrder = 'desc'; // По умолчанию показываем свежие сверху (как лог), или можно asc для хронологии

    function fetchAndRenderPage(page = 1) {
        loadingStatusElement.textContent = '';
        actionsBodyElement.classList.add('opacity-50'); // Визуальный эффект загрузки

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

                if (isFirstLoad) {
                    renderUserProfile(data.user_details);
                    isFirstLoad = false;
                }

                renderChatMessages(data.actions);
                renderPaginationControls(data.pagination);
                applySearchFilter();
            })
            .catch(error => {
                console.error('Ошибка:', error);
                loadingStatusElement.textContent = `Ошибка: ${error.message}`;
                actionsBodyElement.innerHTML = `<div class="text-red-500 text-center w-full p-4">Не удалось загрузить историю.</div>`;
            });
    }

    function renderUserProfile(user) {
        pageTitle.textContent = `${user.full_name} | Matplobbot`;

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
                <h1 class="font-bold text-gray-900 dark:text-white text-lg">${user.full_name}</h1>
                <div class="text-sm text-gray-500 dark:text-gray-400">${usernameText}</div>
            </div>
        `;
    }

    function renderChatMessages(actions) {
        actionsBodyElement.innerHTML = '';
        
        if (actions.length === 0) {
            actionsBodyElement.innerHTML = `<div class="w-full text-center text-gray-500 mt-10">История действий пуста.</div>`;
            return;
        }

        let lastDate = null;

        // API возвращает данные отсортированными. Проходим и рендерим.
        actions.forEach(action => {
            const dateObj = new Date(action.timestamp);
            const dateStr = dateObj.toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' });
            const timeStr = dateObj.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });

            // Date Grouping (вставляем "таблетку" с датой, если день сменился)
            if (dateStr !== lastDate) {
                const datePill = document.createElement('div');
                datePill.className = 'date-pill sticky top-2 z-10 shadow-sm backdrop-blur-sm';
                datePill.textContent = dateStr;
                actionsBodyElement.appendChild(datePill);
                lastDate = dateStr;
            }

            // Message Bubble
            const bubble = document.createElement('div');
            // Добавляем класс command если это команда, для цветной полоски
            const isCommand = action.action_type === 'command';
            bubble.className = `message-bubble ${isCommand ? 'command' : ''}`;

            // Content logic
            let contentHtml = '';
            let icon = '';

            if (isCommand) {
                icon = '🤖';
                contentHtml = `<span class="font-mono text-blue-600 dark:text-blue-400 font-semibold">${action.action_details}</span>`;
            } else if (action.action_type === 'text_message') {
                icon = '💬';
                contentHtml = `<span class="whitespace-pre-wrap">${action.action_details || 'Empty message'}</span>`;
            } else if (action.action_type === 'callback_query') {
                icon = '👆';
                contentHtml = `<span class="italic text-gray-600 dark:text-gray-400">Нажал кнопку:</span> <span class="font-mono bg-gray-100 dark:bg-gray-700 px-1 rounded text-xs">${action.action_details}</span>`;
            } else {
                icon = '⚡';
                contentHtml = `<span class="text-sm">${action.action_type}: ${action.action_details}</span>`;
            }

            bubble.innerHTML = `
                <div class="flex items-start gap-2">
                    <span class="text-lg select-none">${icon}</span>
                    <div class="flex-grow text-sm break-words">${contentHtml}</div>
                </div>
                <div class="message-meta">
                    ${timeStr} <span class="text-xs opacity-50 ml-1">#${action.id}</span>
                </div>
            `;

            actionsBodyElement.appendChild(bubble);
        });
    }

    function renderPaginationControls(pagination) {
        paginationControlsElement.innerHTML = '';
        if (pagination.total_pages <= 1) return;

        const { current_page, total_pages } = pagination;

        const createButton = (text, page, isActive = false) => {
            const btn = document.createElement('button');
            btn.innerHTML = text;
            // Tailwind classes for buttons
            btn.className = `px-3 py-1 rounded transition border ${isActive 
                ? 'bg-blue-600 text-white border-blue-600 font-bold' 
                : 'bg-white dark:bg-gray-700 border-gray-300 dark:border-gray-600 hover:bg-gray-100 dark:hover:bg-gray-600 dark:text-white'}`;
            
            if (!isActive) {
                btn.addEventListener('click', () => fetchAndRenderPage(page));
            } else {
                btn.disabled = true;
            }
            return btn;
        };

        // Simple Pagination: Prev - Current - Next (to save space in footer)
        if (current_page > 1) {
            paginationControlsElement.appendChild(createButton('←', current_page - 1));
        }
        
        paginationControlsElement.appendChild(createButton(current_page, current_page, true));

        if (current_page < total_pages) {
            paginationControlsElement.appendChild(createButton('→', current_page + 1));
        }
    }

    // --- Search Logic (Client-side filtering for currently loaded page) ---
    function applySearchFilter() {
        const term = searchInput.value.toLowerCase().trim();
        const bubbles = actionsBodyElement.querySelectorAll('.message-bubble');
        let visibleCount = 0;

        bubbles.forEach(bubble => {
            const text = bubble.textContent.toLowerCase();
            if (!term || text.includes(term)) {
                bubble.style.display = 'block';
                visibleCount++;
            } else {
                bubble.style.display = 'none';
            }
        });
        
        // Hide date pills if no messages under them are visible? 
        // Simple heuristic: if term exists, just hide dates to avoid confusion of empty days
        const dates = actionsBodyElement.querySelectorAll('.date-pill');
        dates.forEach(d => d.style.display = term ? 'none' : 'block');
    }

    function debounce(func, delay) {
        let timeout;
        return function(...args) {
            clearTimeout(timeout);
            timeout = setTimeout(() => func.apply(this, args), delay);
        };
    }

    searchInput.addEventListener('input', debounce(applySearchFilter, 300));

    // --- CSV Export ---
    document.getElementById('download-all-csv-btn').addEventListener('click', () => {
        const btn = document.getElementById('download-all-csv-btn');
        const originalHtml = btn.innerHTML;
        btn.innerHTML = '⏳';
        btn.disabled = true;

        fetch(`/api/users/${userId}/export_actions`)
            .then(res => res.json())
            .then(data => {
                if(!data.actions) throw new Error("No data");
                const headers = ['ID', 'Type', 'Details', 'Timestamp'];
                const csvRows = [headers.join(',')];
                
                data.actions.forEach(row => {
                    const cleanDetails = (row.action_details || '').replace(/"/g, '""');
                    csvRows.push(`${row.id},${row.action_type},"${cleanDetails}",${row.timestamp}`);
                });

                const blob = new Blob([csvRows.join('\n')], { type: 'text/csv' });
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `user_${userId}_history.csv`;
                a.click();
                window.URL.revokeObjectURL(url);
            })
            .catch(err => alert('Ошибка экспорта: ' + err.message))
            .finally(() => {
                btn.innerHTML = originalHtml;
                btn.disabled = false;
            });
    });

    // Initial Load
    fetchAndRenderPage(1);
});