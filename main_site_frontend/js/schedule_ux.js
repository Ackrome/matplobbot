(function scheduleUxEnhancements() {
    if (typeof loadSchedule === "undefined" || typeof filterAndRender === "undefined") return;

    const UI_PREFS_KEY = "mpb_schedule_ui_prefs";
    const uiState = {
        viewMode: "auto",
    };

    function loadUiPrefs() {
        try {
            const payload = JSON.parse(localStorage.getItem(UI_PREFS_KEY) || "{}");
            if (["auto", "table", "cards"].includes(payload.view_mode)) {
                uiState.viewMode = payload.view_mode;
            }
            if (payload.week_start) {
                const parsed = parseDate(payload.week_start);
                if (!Number.isNaN(parsed.getTime())) {
                    currentWeekStart = getMonday(parsed);
                }
            }
        } catch {
            uiState.viewMode = "auto";
        }
    }

    function saveUiPrefs() {
        localStorage.setItem(
            UI_PREFS_KEY,
            JSON.stringify({
                view_mode: uiState.viewMode,
                week_start: getISODateStr(currentWeekStart),
                entity: currentEntity,
            })
        );
    }

    function injectEnhancementStyles() {
        const style = document.createElement("style");
        style.textContent = `
            #scheduleControls{position:sticky;top:5rem;z-index:35;background:#fff}
            #scheduleGridContent{transition:opacity .2s ease}
            .schedule-touch-btn{min-height:44px;padding:.7rem 1rem}
            .schedule-mobile-card{line-height:1.35}
            .schedule-empty-card{border:1px solid #e2e8f0;background:#f8fafc;border-radius:1rem;padding:1rem;text-align:center}
            .schedule-empty-actions{display:flex;gap:.5rem;justify-content:center;flex-wrap:wrap;margin-top:.75rem}
            .schedule-empty-actions button,.schedule-empty-actions a{border:1px solid #cbd5e1;border-radius:.7rem;padding:.5rem .75rem;font-size:.75rem;font-weight:700}
        `;
        document.head.appendChild(style);
    }

    function ensureContextBar() {
        const controls = document.getElementById("scheduleControls");
        if (!controls || document.getElementById("scheduleContextBar")) return;

        const contextBar = document.createElement("div");
        contextBar.id = "scheduleContextBar";
        contextBar.className = "border-b border-slate-100 bg-white/95 px-3 py-3 md:px-4";
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
                    <button type="button" class="schedule-touch-btn rounded-xl border border-slate-300 bg-white text-xs font-semibold text-slate-700 hover:bg-slate-100" id="scheduleResetContextBtn">Reset</button>
                </div>
            </div>
            <div class="mt-2 flex flex-wrap gap-2">
                <button type="button" class="schedule-touch-btn rounded-xl border border-slate-300 bg-white text-xs font-semibold text-slate-700 hover:bg-slate-100" id="jumpTodayBtn">Today</button>
                <button type="button" class="schedule-touch-btn rounded-xl border border-slate-300 bg-white text-xs font-semibold text-slate-700 hover:bg-slate-100" id="jumpTomorrowBtn">Tomorrow</button>
                <button type="button" class="schedule-touch-btn rounded-xl border border-slate-300 bg-white text-xs font-semibold text-slate-700 hover:bg-slate-100" id="jumpThisWeekBtn">This week</button>
                <button type="button" class="schedule-touch-btn rounded-xl border border-slate-300 bg-white text-xs font-semibold text-slate-700 hover:bg-slate-100" id="jumpNextWeekBtn">Next week</button>
                <div class="ml-auto flex items-center rounded-xl border border-slate-300 bg-white p-1 text-xs">
                    <button type="button" id="viewAutoBtn" class="rounded-lg px-2 py-1 font-semibold text-slate-700">Auto</button>
                    <button type="button" id="viewTableBtn" class="rounded-lg px-2 py-1 font-semibold text-slate-700">Table</button>
                    <button type="button" id="viewCardsBtn" class="rounded-lg px-2 py-1 font-semibold text-slate-700">Cards</button>
                </div>
            </div>
        `;

        controls.prepend(contextBar);
    }

    function setViewMode(mode) {
        uiState.viewMode = mode;
        const desktop = document.getElementById("desktopSchedule");
        const mobile = document.getElementById("mobileSchedule");
        if (!desktop || !mobile) return;

        const auto = mode === "auto";
        const table = mode === "table";
        const cards = mode === "cards";

        desktop.classList.toggle("hidden", cards || (auto && window.innerWidth < 1024));
        desktop.classList.toggle("block", table);
        mobile.classList.toggle("hidden", table || (auto && window.innerWidth >= 1024));
        mobile.classList.toggle("block", cards);

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

        entityEl.textContent = currentEntity?.name || "No group selected";
        weekEl.textContent = `${currentWeekStart.toLocaleDateString()} - ${weekEnd.toLocaleDateString()}`;
        rangeEl.textContent = `${loadedBounds.start || "-"} to ${loadedBounds.end || "-"}`;
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
                    <button type="button" data-schedule-action="retry">Retry</button>
                    <button type="button" data-schedule-action="clear">Clear filters</button>
                    <button type="button" data-schedule-action="reset">Change group</button>
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
            renderEmptyStateWithCta(container, "No classes for this period.");
        }
    };

    const rawRenderDesktopGrid = renderDesktopGrid;
    renderDesktopGrid = function patchedDesktopGrid(lessons) {
        rawRenderDesktopGrid(lessons);
        enhanceDesktopTableOverflow();
        const container = document.getElementById("desktopSchedule");
        if (!container) return;
        if (!Array.isArray(lessons) || lessons.length === 0) {
            renderEmptyStateWithCta(container, "No classes for this period.");
        }
    };

    const rawFilterAndRender = filterAndRender;
    filterAndRender = function patchedFilterAndRender(...args) {
        const content = document.getElementById("scheduleGridContent");
        content?.classList.add("opacity-60");
        rawFilterAndRender(...args);
        setTimeout(() => content?.classList.remove("opacity-60"), 120);
        updateContextBar();
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
                document.getElementById("groupSearch").focus();
                document.getElementById("groupSearch").select();
            }
        });
    }

    function bindToolbar() {
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
        setViewMode(uiState.viewMode);
        saveUiPrefs();
    };

    document.addEventListener("DOMContentLoaded", () => {
        loadUiPrefs();
        injectEnhancementStyles();
        ensureContextBar();
        bindToolbar();
        bindGlobalActions();
        updateContextBar();
        setViewMode(uiState.viewMode);
    });
})();
