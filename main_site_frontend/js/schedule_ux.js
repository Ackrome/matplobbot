(function scheduleUxEnhancements() {
    if (typeof loadSchedule === "undefined" || typeof filterAndRender === "undefined") return;
    const UI_PREFS_KEY = "mpb_schedule_ui_prefs";
    const uiState = {
        viewMode: "auto",
        filtersCollapsed: window.innerWidth < 768,
    };
    function getUiLanguage() {
        const source = window.mpbI18n?.getLanguage?.() || document.documentElement.lang || "ru";
        return String(source).toLowerCase().startsWith("ru") ? "ru" : "en";
    }
    function getUiLocale() {
        return getUiLanguage() === "ru" ? "ru-RU" : "en-US";
    }
    function t(key, fallback = "", params = {}) {
        return window.mpbI18n?.t?.(key, fallback, params) || fallback || key;
    }
    function formatUiDate(date, options) {
        return new Intl.DateTimeFormat(getUiLocale(), options).format(date);
    }
    function formatLoadedBound(value) {
        if (!value) return "-";
        const parsed = parseDate(value);
        return Number.isNaN(parsed.getTime())
            ? value
            : formatUiDate(parsed, { day: "numeric", month: "short", year: "numeric" });
    }
    function loadUiPrefs() {
        try {
            const payload = JSON.parse(localStorage.getItem(UI_PREFS_KEY) || "{}");
            if (["auto", "table", "cards"].includes(payload.view_mode)) {
                uiState.viewMode = payload.view_mode;
            }
            if (typeof payload.filters_collapsed === "boolean") {
                uiState.filtersCollapsed = payload.filters_collapsed;
            } else {
                uiState.filtersCollapsed = window.innerWidth < 768;
            }
            if (payload.week_start) {
                const parsed = parseDate(payload.week_start);
                if (!Number.isNaN(parsed.getTime())) {
                    currentWeekStart = getMonday(parsed);
                }
            }
        } catch {
            uiState.viewMode = "auto";
            uiState.filtersCollapsed = window.innerWidth < 768;
        }
    }
    function saveUiPrefs() {
        localStorage.setItem(
            UI_PREFS_KEY,
            JSON.stringify({
                view_mode: uiState.viewMode,
                filters_collapsed: uiState.filtersCollapsed,
                week_start: getISODateStr(currentWeekStart),
                entity: currentEntity,
            })
        );
    }
    function injectEnhancementStyles() {
        const style = document.createElement("style");
        style.textContent = `
            #scheduleControls{position:relative;z-index:5;background:#fff}
            #scheduleGridContent{transition:opacity .2s ease}
            .schedule-touch-btn{min-height:44px;padding:.7rem 1rem}
            .schedule-empty-card{border:1px solid #dbeafe;background:linear-gradient(135deg,#eff6ff,#ffffff);border-radius:1.25rem;padding:1.25rem;text-align:center;box-shadow:0 18px 48px -36px rgba(37,99,235,.45)}
            .schedule-empty-actions{display:flex;gap:.5rem;justify-content:center;flex-wrap:wrap;margin-top:.9rem}
            .schedule-empty-actions button,.schedule-empty-actions a{border:1px solid #cbd5e1;border-radius:.8rem;padding:.55rem .9rem;font-size:.75rem;font-weight:700;background:#fff}
            .schedule-cards-feed{padding:.75rem;background:linear-gradient(180deg,#f8fbff 0%,#fff 22%)}
            .schedule-day-section{margin-bottom:1rem;border:1px solid #dbeafe;border-radius:1.4rem;overflow:hidden;background:linear-gradient(180deg,#eff6ff 0%,#fff 36%);box-shadow:0 24px 40px -34px rgba(37,99,235,.35)}
            .schedule-day-header{position:relative;display:flex;align-items:flex-start;justify-content:space-between;gap:1rem;padding:1rem 1.15rem;border-bottom:1px solid #dbeafe;background:linear-gradient(135deg,#dbeafe 0%,#eff6ff 55%,#f8fafc 100%)}
            .schedule-day-header--today{background:linear-gradient(135deg,#bfdbfe 0%,#dbeafe 45%,#eff6ff 100%)}
            .schedule-day-header-label{text-transform:uppercase;letter-spacing:.12em;font-size:.68rem;font-weight:800;color:#64748b}
            .schedule-day-header-title{margin-top:.35rem;font-size:1.35rem;line-height:1.1;font-weight:900;color:#0f172a}
            .schedule-day-pill{padding:.38rem .7rem;border-radius:999px;background:#1d4ed8;color:#fff;font-size:.72rem;font-weight:700;box-shadow:0 10px 20px -16px rgba(29,78,216,.7)}
            .schedule-day-lessons{display:flex;flex-direction:column;background:#fff}
            .schedule-feed-card{display:flex;flex-direction:column;gap:.8rem;padding:1rem;background:rgba(255,255,255,.96);transition:transform .18s ease,box-shadow .18s ease,background-color .18s ease}
            .schedule-feed-card + .schedule-feed-card{border-top:1px solid #e2e8f0}
            .schedule-feed-card:hover{background:#f8fbff}
            .schedule-feed-card-head{display:flex;align-items:flex-start;justify-content:space-between;gap:.75rem}
            .schedule-feed-card-time{display:flex;align-items:baseline;gap:.45rem;min-width:0}
            .schedule-feed-card-start{font-size:1.35rem;line-height:1;font-weight:900;color:#0f172a}
            .schedule-feed-card-end{font-size:.8rem;font-weight:700;color:#94a3b8;text-decoration:line-through;text-decoration-color:#cbd5e1}
            .schedule-feed-card-kind{flex-shrink:0}
            .schedule-feed-card-body{display:flex;flex-direction:column;gap:.55rem;min-width:0}
            .schedule-feed-card-title{font-size:1rem;line-height:1.35;font-weight:800;color:#0f172a;overflow-wrap:anywhere}
            .schedule-feed-card-module{overflow-wrap:anywhere}
            .schedule-feed-card-meta{display:grid;grid-template-columns:minmax(0,1fr);gap:.55rem}
            .schedule-feed-card-meta-item{display:flex;align-items:flex-start;gap:.55rem;min-width:0;font-size:.88rem;line-height:1.35;font-weight:600;color:#64748b}
            .schedule-feed-card-meta-item span{min-width:0;overflow-wrap:anywhere}
            @media (max-width:1023px){.schedule-day-header-title{font-size:1.15rem}}
            @media (min-width:1024px){
                .schedule-cards-feed.schedule-cards-desktop{padding:1rem}
                .schedule-cards-feed.schedule-cards-desktop .schedule-day-section{margin-bottom:1.25rem}
                .schedule-cards-feed.schedule-cards-desktop .schedule-day-header{position:static;padding:1.15rem 1.35rem}
                .schedule-cards-feed.schedule-cards-desktop .schedule-day-lessons{display:grid;grid-template-columns:repeat(auto-fit,minmax(360px,1fr));gap:1rem;padding:1rem;background:transparent}
                .schedule-cards-feed.schedule-cards-desktop .schedule-feed-card{min-height:15rem;border:1px solid #e2e8f0;border-radius:1rem;padding:1.1rem 1.15rem;box-shadow:0 20px 35px -30px rgba(15,23,42,.35)}
                .schedule-cards-feed.schedule-cards-desktop .schedule-feed-card + .schedule-feed-card{border-top:none}
                .schedule-cards-feed.schedule-cards-desktop .schedule-feed-card-title{font-size:1.04rem}
                .schedule-cards-feed.schedule-cards-desktop .schedule-feed-card-meta{gap:.65rem}
            }
        `;
        document.head.appendChild(style);
    }

    function applyFilterVisibility() {
        const section = document.getElementById("moduleFilterSection");
        const content = document.getElementById("filterContent");
        const arrow = document.getElementById("filterArrow");
        const button = document.getElementById("filterToggleBtn");
        if (!content || !arrow || !button) return;
        const collapsed = uiState.filtersCollapsed;
        section.classList.toggle("hidden", collapsed);
        arrow.classList.toggle("rotate-180", !collapsed);
        button.setAttribute("aria-expanded", String(!collapsed));
    }
    function toggleFilterSection(forceCollapsed) {
        uiState.filtersCollapsed = typeof forceCollapsed === "boolean"
            ? forceCollapsed
            : !uiState.filtersCollapsed;
        applyFilterVisibility();
        saveUiPrefs();
    }
    function syncContextBarLabels() {
        const labels = {
            viewAutoBtn: ["schedule.view.auto", "Авто"],
            viewTableBtn:["schedule.view.table", "Таблица"],
            viewCardsBtn:["schedule.view.cards", "Карточки"],
        };
        Object.entries(labels).forEach(([id, [key, fallback]]) => {
            const element = document.getElementById(id);
            if (element) {
                element.textContent = t(key, fallback);
            }
        });
    }
    function setViewMode(mode) {
        uiState.viewMode = mode;
        const desktop = document.getElementById("desktopSchedule");
        const mobile = document.getElementById("mobileSchedule");
        if (!desktop || !mobile) return;
        const auto = mode === "auto";
        const table = mode === "table";
        const cards = mode === "cards";
        const showDesktop = table || (auto && window.innerWidth >= 1024);
        const showCardsFeed = cards || (auto && window.innerWidth < 1024);
        desktop.style.display = showDesktop ? "block" : "none";
        mobile.style.display = showCardsFeed ? "flex" : "none";
        desktop.classList.toggle("hidden", !showDesktop);
        mobile.classList.toggle("hidden", !showCardsFeed);
        mobile.classList.toggle("schedule-cards-desktop", cards && window.innerWidth >= 1024);
        const isActive = (id, active) => {
            const btn = document.getElementById(id);
            if (!btn) return;
            btn.classList.toggle("bg-slate-900", active);
            btn.classList.toggle("text-white", active);
            btn.classList.toggle("text-slate-700", !active);
        };
        isActive("viewAutoBtn", auto);
        isActive("viewTableBtn", table);
        isActive("viewCardsBtn", cards);
        saveUiPrefs();
    }
    function updateContextBar() {
        const entityEl = document.getElementById("contextEntity");
        const rangeEl = document.getElementById("contextRange");
        const parsedEl = document.getElementById("contextParsed");

        if (entityEl) {
            entityEl.textContent = currentEntity?.name || t("schedule.context.none", "Группа не выбрана");
        }

        const loadedRangeText = t("schedule.context.loadedRange", "Загружено {start} - {end}", {
            start: formatLoadedBound(loadedBounds.start),
            end: formatLoadedBound(loadedBounds.end),
        });
        if (rangeEl) rangeEl.textContent = loadedRangeText;

        const parsedDate = sourceUpdatedAt ? new Date(sourceUpdatedAt) : null;
        const parsedValue = parsedDate && !Number.isNaN(parsedDate.getTime())
            ? formatUiDate(parsedDate, {
                day: "numeric",
                month: "short",
                hour: "2-digit",
                minute: "2-digit",
            })
            : t("schedule.context.parsedUnknown", "Время обновления неизвестно");

        if (parsedEl) {
            parsedEl.textContent = t("schedule.context.parsedAt", "Обновлено в вузе: {value}", {
                value: parsedValue,
            });
        }
    }
    function enhanceDesktopTableOverflow() {
        const tableWrap = document.querySelector("#desktopSchedule .overflow-hidden.relative");
        if (!tableWrap) return;
        tableWrap.classList.remove("overflow-hidden");
        tableWrap.classList.add("overflow-x-auto");
    }
    function renderEmptyStateWithCta(container, text) {
        container.innerHTML = `
            <div class="schedule-empty-card">
                <p class="text-sm font-semibold text-slate-700">${text}</p>
                <div class="schedule-empty-actions">
                    <button type="button" data-schedule-action="retry">${t("schedule.action.retry", "Повторить")}</button>
                    <button type="button" data-schedule-action="clear">${t("schedule.action.clearFilters", "Сбросить фильтры")}</button>
                    <button type="button" data-schedule-action="reset">${t("schedule.action.changeGroup", "Сменить группу")}</button>
                </div>
            </div>
        `;
    }
    const rawRenderMobileFeed = renderMobileFeed;
    renderMobileFeed = function patchedMobileFeed(lessons) {
        rawRenderMobileFeed(lessons);
        const container = document.getElementById("mobileSchedule");
        if (!container) return;
        if (!Array.isArray(lessons) || lessons.length === 0) {
            renderEmptyStateWithCta(container, t("schedule.state.emptyPeriod", "Нет занятий за выбранный период."));
        }
    };
    const rawRenderDesktopGrid = renderDesktopGrid;
    renderDesktopGrid = function patchedDesktopGrid(lessons) {
        rawRenderDesktopGrid(lessons);
        enhanceDesktopTableOverflow();
        const container = document.getElementById("desktopSchedule");
        if (!container) return;
        if (!Array.isArray(lessons) || lessons.length === 0) {
            renderEmptyStateWithCta(container, t("schedule.state.emptyPeriod", "Нет занятий за выбранный период."));
        }
    };
    const rawFilterAndRender = filterAndRender;
    filterAndRender = function patchedFilterAndRender(...args) {
        const content = document.getElementById("scheduleGridContent");
        content?.classList.add("opacity-60");
        rawFilterAndRender(...args);
        setTimeout(() => content?.classList.remove("opacity-60"), 120);
        updateContextBar();
        applyFilterVisibility();
        setViewMode(uiState.viewMode);
        saveUiPrefs();
    };
    function bindGlobalActions() {
        document.addEventListener("click", (event) => {
            const target = event.target;
            if (!(target instanceof HTMLElement)) return;
            const action = target.getAttribute("data-schedule-action");
            if (!action) return;
            if (action === "retry" && currentEntity?.id) {
                loadSchedule(currentEntity.type, currentEntity.id, currentEntity.name);
            }
            if (action === "clear") {
                selectedModules = new Set(allAvailableModules);
                renderModuleFilters();
                filterAndRender();
                savePreferences();
            }
            if (action === "reset") {
                document.getElementById("groupSearch")?.focus();
                document.getElementById("groupSearch")?.select();
            }
        });
    }
    function bindToolbar() {
        document.getElementById("filterToggleBtn")?.addEventListener("click", () => toggleFilterSection());
        document.getElementById("viewAutoBtn")?.addEventListener("click", () => setViewMode("auto"));
        document.getElementById("viewTableBtn")?.addEventListener("click", () => setViewMode("table"));
        document.getElementById("viewCardsBtn")?.addEventListener("click", () => setViewMode("cards"));
        window.addEventListener("resize", () => setViewMode(uiState.viewMode));
    }
    const rawLoadSchedule = loadSchedule;
    loadSchedule = async function patchedLoadSchedule(...args) {
        await rawLoadSchedule(...args);
        updateContextBar();
        applyFilterVisibility();
        setViewMode(uiState.viewMode);
        saveUiPrefs();
    };
    document.addEventListener("DOMContentLoaded", () => {
        loadUiPrefs();
        injectEnhancementStyles();
        syncContextBarLabels();
        bindToolbar();
        bindGlobalActions();
        updateContextBar();
        applyFilterVisibility();
        setViewMode(uiState.viewMode);
        window.mpbI18n?.registerTranslator?.(() => {
            syncContextBarLabels();
            updateContextBar();
            applyFilterVisibility();
            setViewMode(uiState.viewMode);
        });
        window.toggleScheduleFilters = () => toggleFilterSection();
    });
})();
