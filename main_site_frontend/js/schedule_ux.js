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

    function ensureContextBar() {
        const controls = document.getElementById("scheduleControls");
        if (!controls || document.getElementById("scheduleContextBar")) return;

        const contextBar = document.createElement("div");
        contextBar.id = "scheduleContextBar";
        contextBar.className = "border-b border-slate-100 bg-white/95 px-3 py-3 shadow-[0_12px_32px_-24px_rgba(15,23,42,0.25)] md:px-4";
        contextBar.innerHTML = `
            <div class="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
                <div class="text-xs md:text-sm text-slate-600">
                    <span class="font-bold text-slate-800" id="contextEntity">-</span>
                    <span class="mx-2 text-slate-300">|</span>
                    <span id="contextWeek">-</span>
                    <span class="mx-2 text-slate-300">|</span>
                    <span id="contextRange">-</span>
                </div>
                <div class="flex items-center gap-2">
                    <button type="button" class="schedule-touch-btn rounded-xl border border-slate-300 bg-white text-xs font-semibold text-slate-700 hover:bg-slate-100" id="scheduleResetContextBtn"></button>
                </div>
            </div>
            <div class="mt-2 flex flex-wrap gap-2">
                <button type="button" class="schedule-touch-btn rounded-xl border border-slate-300 bg-white text-xs font-semibold text-slate-700 hover:bg-slate-100" id="jumpTodayBtn"></button>
                <button type="button" class="schedule-touch-btn rounded-xl border border-slate-300 bg-white text-xs font-semibold text-slate-700 hover:bg-slate-100" id="jumpTomorrowBtn"></button>
                <button type="button" class="schedule-touch-btn rounded-xl border border-slate-300 bg-white text-xs font-semibold text-slate-700 hover:bg-slate-100" id="jumpThisWeekBtn"></button>
                <button type="button" class="schedule-touch-btn rounded-xl border border-slate-300 bg-white text-xs font-semibold text-slate-700 hover:bg-slate-100" id="jumpNextWeekBtn"></button>
                <div class="ml-auto flex items-center rounded-xl border border-slate-300 bg-white p-1 text-xs">
                    <button type="button" id="viewAutoBtn" class="rounded-lg px-2 py-1 font-semibold text-slate-700"></button>
                    <button type="button" id="viewTableBtn" class="rounded-lg px-2 py-1 font-semibold text-slate-700"></button>
                    <button type="button" id="viewCardsBtn" class="rounded-lg px-2 py-1 font-semibold text-slate-700"></button>
                </div>
            </div>
        `;

        controls.prepend(contextBar);
    }

    function applyFilterVisibility() {
        const section = document.getElementById("moduleFilterSection");
        const content = document.getElementById("filterContent");
        const arrow = document.getElementById("filterArrow");
        const button = document.getElementById("filterToggleBtn");
        if (!content || !arrow || !button) return;

        const collapsed = uiState.filtersCollapsed;
        content.classList.toggle("hidden", collapsed);
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
            scheduleResetContextBtn: ["schedule.context.reset", "Reset"],
            jumpTodayBtn: ["schedule.action.today", "Today"],
            jumpTomorrowBtn: ["schedule.action.tomorrow", "Tomorrow"],
            jumpThisWeekBtn: ["schedule.action.thisWeek", "This week"],
            jumpNextWeekBtn: ["schedule.action.nextWeek", "Next week"],
            viewAutoBtn: ["schedule.view.auto", "Auto"],
            viewTableBtn: ["schedule.view.table", "Table"],
            viewCardsBtn: ["schedule.view.cards", "Cards"],
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
        const weekEl = document.getElementById("contextWeek");
        const rangeEl = document.getElementById("contextRange");
        if (!entityEl || !weekEl || !rangeEl) return;

        const weekEnd = new Date(currentWeekStart);
        weekEnd.setDate(weekEnd.getDate() + 6);

        entityEl.textContent = currentEntity?.name || t("schedule.context.none", "No group selected");
        weekEl.textContent = `${formatUiDate(currentWeekStart, { day: "numeric", month: "short", year: "numeric" })} — ${formatUiDate(weekEnd, { day: "numeric", month: "short", year: "numeric" })}`;
        const loadedRangeText = t("schedule.context.loadedRange", "Loaded {start} — {end}", {
            start: formatLoadedBound(loadedBounds.start),
            end: formatLoadedBound(loadedBounds.end),
        });
        const parsedDate = sourceUpdatedAt ? new Date(sourceUpdatedAt) : null;
        const parsedValue = parsedDate && !Number.isNaN(parsedDate.getTime())
            ? formatUiDate(parsedDate, {
                day: "numeric",
                month: "short",
                year: "numeric",
                hour: "2-digit",
                minute: "2-digit",
            })
            : t("schedule.context.parsedUnknown", "Parsed time unknown");
        const parsedText = t("schedule.context.parsedAt", "Parsed: {value}", {
            value: parsedValue,
        });
        rangeEl.textContent = `${loadedRangeText} | ${parsedText}`;
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
                    <button type="button" data-schedule-action="retry">${t("schedule.action.retry", "Retry")}</button>
                    <button type="button" data-schedule-action="clear">${t("schedule.action.clearFilters", "Clear filters")}</button>
                    <button type="button" data-schedule-action="reset">${t("schedule.action.changeGroup", "Change group")}</button>
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
            renderEmptyStateWithCta(container, t("schedule.state.emptyPeriod", "No classes for this period."));
        }
    };

    const rawRenderDesktopGrid = renderDesktopGrid;
    renderDesktopGrid = function patchedDesktopGrid(lessons) {
        rawRenderDesktopGrid(lessons);
        enhanceDesktopTableOverflow();
        const container = document.getElementById("desktopSchedule");
        if (!container) return;
        if (!Array.isArray(lessons) || lessons.length === 0) {
            renderEmptyStateWithCta(container, t("schedule.state.emptyPeriod", "No classes for this period."));
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
        document.getElementById("jumpTodayBtn")?.addEventListener("click", () => setTodayWeek());
        document.getElementById("jumpTomorrowBtn")?.addEventListener("click", async () => {
            const tomorrow = new Date();
            tomorrow.setDate(tomorrow.getDate() + 1);
            currentWeekStart = getMonday(tomorrow);
            await changeWeek(0);
        });
        document.getElementById("jumpThisWeekBtn")?.addEventListener("click", async () => {
            currentWeekStart = getMonday(new Date());
            await changeWeek(0);
        });
        document.getElementById("jumpNextWeekBtn")?.addEventListener("click", async () => {
            const nextWeek = new Date();
            nextWeek.setDate(nextWeek.getDate() + 7);
            currentWeekStart = getMonday(nextWeek);
            await changeWeek(0);
        });
        document.getElementById("scheduleResetContextBtn")?.addEventListener("click", () => {
            selectedModules = new Set(allAvailableModules);
            currentWeekStart = getMonday(new Date());
            renderModuleFilters();
            filterAndRender();
            savePreferences();
        });
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
        ensureContextBar();
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
