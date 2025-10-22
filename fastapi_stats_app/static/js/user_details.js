document.addEventListener('DOMContentLoaded', function() {
    const pathParts = window.location.pathname.split('/');
    const userId = pathParts[pathParts.length - 1];

    // --- DOM Elements ---
    const profileHeaderElement = document.getElementById('user-profile-header');
    const actionsBodyElement = document.getElementById('actions-body');
    const loadingStatusElement = document.getElementById('loading-status');
    const pageTitle = document.querySelector('title');
    const actionsTableTitle = document.getElementById('actions-table-title');
    const paginationControlsElement = document.getElementById('pagination-controls');
    const searchInput = document.getElementById('search-input');

    if (!userId) {
        actionsBodyElement.innerHTML = `<tr><td colspan="4" style="text-align:center; color: red;">ID пользователя не найден в URL.</td></tr>`;
        return;
    }

    let isFirstLoad = true;

    // --- Main data fetching and rendering function ---
    function fetchAndRenderPage(page = 1) {
        loadingStatusElement.textContent = 'Загрузка данных...';
        actionsBodyElement.innerHTML = `<tr><td colspan="4" style="text-align:center;">Загрузка...</td></tr>`;
        paginationControlsElement.innerHTML = '';

        fetch(`/api/users/${userId}/profile?page=${page}`)
            .then(response => {
                if (!response.ok) {
                    if (response.status === 404) throw new Error('Пользователь не найден.');
                    throw new Error(`Ошибка сети: ${response.statusText}`);
                }
                return response.json();
            })
            .then(data => {
                loadingStatusElement.textContent = '';

                // Update user profile header only on the first load
                if (isFirstLoad) {
                    renderUserProfile(data.user_details);
                    isFirstLoad = false;
                }

                renderActionsTable(data.actions);
                renderPaginationControls(data.pagination);
                
                // Apply current search filter to the new page content
                applySearchFilter();
            })
            .catch(error => {
                console.error('Ошибка при загрузке данных пользователя:', error);
                loadingStatusElement.textContent = `Ошибка: ${error.message}`;
                actionsBodyElement.innerHTML = `<tr><td colspan="4" style="text-align:center; color: red;">Не удалось загрузить данные.</td></tr>`;
            });
    }

    function renderUserProfile(user) {
        pageTitle.textContent = `Профиль: ${user.full_name}`;
        actionsTableTitle.textContent = `Действия пользователя: ${user.full_name}`;

        let avatarHtml = '';
        if (user.avatar_pic_url) {
            avatarHtml = `<img src="${user.avatar_pic_url}" alt="Аватар ${user.full_name}" style="width: 80px; height: 80px; border-radius: 50%;">`;
        } else {
            const initial = (user.full_name && user.full_name.trim().length > 0) ? user.full_name.trim()[0].toUpperCase() : '?';
            avatarHtml = `<div class="fallback-avatar" style="width: 80px; height: 80px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 40px; font-weight: bold;">${initial}</div>`;
        }

        let userNameHtml = `<h2>${user.full_name}</h2>`;
        if (user.username && user.username !== 'Нет username') {
            userNameHtml += `<p><a href="https://t.me/${user.username}" target="_blank" rel="noopener noreferrer">@${user.username}</a></p>`;
        } else {
            userNameHtml += `<p>ID: ${user.user_id}</p>`;
        }

        profileHeaderElement.innerHTML = `
            <div>${avatarHtml}</div>
            <div>${userNameHtml}</div>
        `;
    }

    function renderActionsTable(actions) {
        actionsBodyElement.innerHTML = ''; // Clear loading message
        if (actions.length === 0) {
            actionsBodyElement.innerHTML = `<tr><td colspan="4" style="text-align:center;">У этого пользователя нет записанных действий.</td></tr>`;
        } else {
            actions.forEach(action => {
                const row = actionsBodyElement.insertRow();
                row.insertCell().textContent = action.id;
                row.insertCell().textContent = action.action_type;
                const detailsCell = row.insertCell();
                detailsCell.textContent = action.action_details;
                detailsCell.style.maxWidth = '400px';
                detailsCell.style.wordBreak = 'break-word';
                row.insertCell().textContent = action.timestamp;
            });
        }
    }

    function renderPaginationControls(pagination) {
        paginationControlsElement.innerHTML = '';
        if (pagination.total_pages <= 1) return;

        const { current_page, total_pages } = pagination;

        // "Previous" button
        const prevButton = document.createElement('button');
        prevButton.textContent = '« Назад';
        prevButton.className = 'pagination-button';
        prevButton.disabled = current_page === 1;
        prevButton.addEventListener('click', () => fetchAndRenderPage(current_page - 1));
        paginationControlsElement.appendChild(prevButton);

        // Page number display
        const pageInfo = document.createElement('span');
        pageInfo.textContent = `Страница ${current_page} из ${total_pages}`;
        paginationControlsElement.appendChild(pageInfo);

        // "Next" button
        const nextButton = document.createElement('button');
        nextButton.textContent = 'Вперед »';
        nextButton.className = 'pagination-button';
        nextButton.disabled = current_page === total_pages;
        nextButton.addEventListener('click', () => fetchAndRenderPage(current_page + 1));
        paginationControlsElement.appendChild(nextButton);
    }

    // --- Search/Filter Logic ---
    function applySearchFilter() {
        const searchTerm = searchInput.value.toLowerCase().trim();
        if (!searchTerm) { // If search is empty, ensure all rows are visible
            for (const row of actionsBodyElement.getElementsByTagName('tr')) {
                row.style.display = '';
            }
            loadingStatusElement.textContent = '';
            return;
        }

        const rows = actionsBodyElement.getElementsByTagName('tr');
        let visibleRows = 0;

        for (const row of rows) {
            if (row.cells.length > 1) {
                const actionType = row.cells[1].textContent.toLowerCase();
                const actionDetails = row.cells[2].textContent.toLowerCase();

                if (actionType.includes(searchTerm) || actionDetails.includes(searchTerm)) {
                    row.style.display = '';
                    visibleRows++;
                } else {
                    row.style.display = 'none';
                }
            }
        }

        loadingStatusElement.textContent = (visibleRows === 0) ? 'Нет действий на этой странице, соответствующих вашему фильтру.' : '';
    }

    searchInput.addEventListener('input', applySearchFilter);

    // --- Initial Load ---
    fetchAndRenderPage(1);
});