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

    // --- State Management ---
    let isFirstLoad = true;
    let currentSortBy = 'timestamp';
    let currentSortOrder = 'desc';

    // --- Main data fetching and rendering function ---
    function fetchAndRenderPage(page = 1) {
        loadingStatusElement.textContent = ''; // Clear previous errors
        paginationControlsElement.innerHTML = '';
        updateSortIndicators();

        fetch(`/api/users/${userId}/profile?page=${page}&sort_by=${currentSortBy}&sort_order=${currentSortOrder}`)
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

    function renderPaginationControls(pagination, contextPages = 2) {
        paginationControlsElement.innerHTML = '';
        if (pagination.total_pages <= 1) return;

        const { current_page, total_pages } = pagination;

        const createButton = (text, page, isDisabled = false, isActive = false) => {
            const button = document.createElement('button');
            button.innerHTML = text;
            button.className = 'pagination-button';
            if (isActive) button.classList.add('active');
            button.disabled = isDisabled || isActive;
            if (!isDisabled && !isActive) {
                button.addEventListener('click', () => fetchAndRenderPage(page));
            }
            return button;
        };

        const createEllipsis = () => {
            const span = document.createElement('span');
            span.textContent = '...';
            span.className = 'pagination-ellipsis';
            return span;
        };

        // "First" and "Previous" buttons
        paginationControlsElement.appendChild(createButton('«', 1, current_page === 1));
        const prevButton = document.createElement('button');

        // Generate page number buttons
        const pagesToShow = new Set();
        pagesToShow.add(1);
        pagesToShow.add(total_pages);

        for (let i = 0; i <= contextPages; i++) {
            if (current_page - i > 0) pagesToShow.add(current_page - i);
            if (current_page + i <= total_pages) pagesToShow.add(current_page + i);
        }

        const sortedPages = Array.from(pagesToShow).sort((a, b) => a - b);

        let lastPage = 0;
        for (const pageNum of sortedPages) {
            if (lastPage > 0 && pageNum - lastPage > 1) {
                paginationControlsElement.appendChild(createEllipsis());
            }
            paginationControlsElement.appendChild(
                createButton(pageNum, pageNum, false, pageNum === current_page)
            );
            lastPage = pageNum;
        }

        // "Next" and "Last" buttons
        paginationControlsElement.appendChild(createButton('»', total_pages, current_page === total_pages));
    }

    function handleSortClick(event) {
        const newSortBy = event.target.dataset.sortBy;
        if (!newSortBy) return;

        if (newSortBy === currentSortBy) {
            // If clicking the same column, reverse the order
            currentSortOrder = currentSortOrder === 'asc' ? 'desc' : 'asc';
        } else {
            // If clicking a new column, set it and default to 'desc'
            currentSortBy = newSortBy;
            currentSortOrder = 'desc';
        }
        // Fetch data for the first page with the new sorting
        fetchAndRenderPage(1);
    }

    function updateSortIndicators() {
        document.querySelectorAll('#actions-table th.sortable').forEach(th => {
            th.classList.remove('sort-asc', 'sort-desc');
            if (th.dataset.sortBy === currentSortBy) {
                th.classList.add(currentSortOrder === 'asc' ? 'sort-asc' : 'sort-desc');
            }
        });
    }

    // --- Debounce Utility ---
    function debounce(func, delay) {
        let timeoutId;
        return function(...args) {
            clearTimeout(timeoutId);
            timeoutId = setTimeout(() => {
                func.apply(this, args);
            }, delay);
        };
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

    searchInput.addEventListener('input', debounce(applySearchFilter, 300));

    // --- Attach Event Listeners ---
    document.querySelector('#actions-table thead').addEventListener('click', handleSortClick);

    // --- Back to Top Button Logic ---
    const backToTopButton = document.getElementById('back-to-top-btn');

    window.onscroll = function() {
        scrollFunction();
    };

    function scrollFunction() {
        if (document.body.scrollTop > 100 || document.documentElement.scrollTop > 100) {
            backToTopButton.style.display = "block";
        } else {
            backToTopButton.style.display = "none";
        }
    }

    backToTopButton.addEventListener('click', function() {
        // For Safari
        document.body.scrollTop = 0;
        // For Chrome, Firefox, IE and Opera
        document.documentElement.scrollTop = 0;
    });


    // --- Initial Load ---
    fetchAndRenderPage(1);
});