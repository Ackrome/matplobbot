(function statsUxEnhancements() {
    if (typeof state === "undefined" || typeof elements === "undefined") return;

    const STORAGE = {
        density: "mpb_stats_density",
        columns: "mpb_stats_columns",
        timezone: "mpb_stats_timezone",
        telemetry: "mpb_stats_telemetry",
    };
    const COLUMNS = ["rank", "full_name", "actions_count", "last_action_time"];
    const columnToIndex = { rank: 1, full_name: 2, actions_count: 3, last_action_time: 4 };

    const refs = {
        table: document.getElementById("leaderboardTable"),
        tableDensityBtn: document.getElementById("tableDensityBtn"),
        columnVisibilityBtn: document.getElementById("columnVisibilityBtn"),
        columnVisibilityPanel: document.getElementById("columnVisibilityPanel"),
        columnVisibilityList: document.getElementById("columnVisibilityList"),
        timezoneSelect: document.getElementById("timezoneSelect"),
        chartZoomInBtn: document.getElementById("chartZoomInBtn"),
        chartZoomOutBtn: document.getElementById("chartZoomOutBtn"),
        chartResetZoomBtn: document.getElementById("chartResetZoomBtn"),
        resetFiltersBtn: document.getElementById("resetFiltersBtn"),
        mobileFilterOpenBtn: document.getElementById("mobileFilterOpenBtn"),
        mobileFilterSheet: document.getElementById("mobileFilterSheet"),
        mobileFilterCloseBtn: document.getElementById("mobileFilterCloseBtn"),
        mobileRangeSelect: document.getElementById("mobileRangeSelect"),
        mobileSortSelect: document.getElementById("mobileSortSelect"),
        mobilePageSizeSelect: document.getElementById("mobilePageSizeSelect"),
        mobileTimezoneSelect: document.getElementById("mobileTimezoneSelect"),
        mobileFilterApplyBtn: document.getElementById("mobileFilterApplyBtn"),
        mobileFilterResetBtn: document.getElementById("mobileFilterResetBtn"),
        mobileActionRetry: document.getElementById("mobileActionRetry"),
        mobileActionReset: document.getElementById("mobileActionReset"),
        mobileActionDiagnostics: document.getElementById("mobileActionDiagnostics"),
        activityEmptyState: document.getElementById("activityEmptyState"),
        activityEmptyRetry: document.getElementById("activityEmptyRetry"),
        activityEmptyReset: document.getElementById("activityEmptyReset"),
        diagRetriesUsed: document.getElementById("diagRetriesUsed"),
        diagFailedWidgets: document.getElementById("diagFailedWidgets"),
        diagTtfd: document.getElementById("diagTtfd"),
    };

    state.tableDensity = localStorage.getItem(STORAGE.density) || "default";
    state.visibleColumns = JSON.parse(localStorage.getItem(STORAGE.columns) || "null") || [...COLUMNS];
    state.timezone = localStorage.getItem(STORAGE.timezone) || "local";
    state.chartZoom = state.chartZoom || { windowSize: null };
    state.telemetry = state.telemetry || { retriesUsed: 0, failedWidgetLoads: 0, ttfdMs: null, startedMs: performance.now() };
    state.telemetry.startedMs = state.telemetry.startedMs || performance.now();

    const crosshairPlugin = {
        id: "mpbCrosshairLocal",
        afterDatasetsDraw(chart) {
            const active = chart.tooltip?.getActiveElements?.() || [];
            if (!active.length) return;
            const x = active[0].element.x;
            const { ctx, chartArea } = chart;
            ctx.save();
            ctx.beginPath();
            ctx.moveTo(x, chartArea.top);
            ctx.lineTo(x, chartArea.bottom);
            ctx.lineWidth = 1;
            ctx.strokeStyle = "rgba(59,130,246,.35)";
            ctx.stroke();
            ctx.restore();
        },
    };
    if (window.Chart && !Chart.registry.plugins.get("mpbCrosshairLocal")) {
        Chart.register(crosshairPlugin);
    }

    const style = document.createElement("style");
    style.textContent = `
        #leaderboardTable.mpb-compact td,#leaderboardTable.mpb-compact th{padding-top:.45rem;padding-bottom:.45rem}
    `;
    document.head.appendChild(style);

    const rawFormatDateTime = formatDateTime;
    formatDateTime = function patchedDateTime(value) {
        if (!value) return "-";
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) return rawFormatDateTime(value);
        const opts = { dateStyle: "medium", timeStyle: "short" };
        if (state.timezone && state.timezone !== "local") opts.timeZone = state.timezone;
        try {
            return new Intl.DateTimeFormat((window.mpbI18n?.getLanguage?.() || "en") === "ru" ? "ru-RU" : "en-US", opts).format(date);
        } catch {
            return rawFormatDateTime(value);
        }
    };

    const rawUpdateDiagnostics = updateDiagnostics;
    updateDiagnostics = function patchedDiagnostics() {
        rawUpdateDiagnostics();
        if (refs.diagRetriesUsed) refs.diagRetriesUsed.textContent = String(state.telemetry.retriesUsed || 0);
        if (refs.diagFailedWidgets) refs.diagFailedWidgets.textContent = String(state.telemetry.failedWidgetLoads || 0);
        if (refs.diagTtfd) refs.diagTtfd.textContent = state.telemetry.ttfdMs ? `${Math.round(state.telemetry.ttfdMs)} ms` : "-";
    };

    const rawRegisterFailure = registerFailure;
    registerFailure = function patchedRegisterFailure(message) {
        rawRegisterFailure(message);
        state.telemetry.failedWidgetLoads = (state.telemetry.failedWidgetLoads || 0) + 1;
        localStorage.setItem(STORAGE.telemetry, JSON.stringify(state.telemetry));
        updateDiagnostics();
    };

    const rawRefreshFromRest = refreshFromRest;
    refreshFromRest = async function patchedRefresh(...args) {
        const result = await rawRefreshFromRest(...args);
        if (!state.telemetry.ttfdMs && (state.leaderboard.length > 0 || state.activity.length > 0)) {
            state.telemetry.ttfdMs = performance.now() - state.telemetry.startedMs;
        }
        localStorage.setItem(STORAGE.telemetry, JSON.stringify(state.telemetry));
        updateDiagnostics();
        return result;
    };

    const rawRenderLeaderboard = renderLeaderboard;
    renderLeaderboard = function patchedLeaderboard() {
        rawRenderLeaderboard();
        if (state.leaderboard.length === 0 && elements.leaderboardBody) {
            elements.leaderboardBody.innerHTML = `
                <tr>
                    <td colspan="4" class="px-4 py-4">
                        <div class="rounded-2xl border border-slate-200 bg-slate-50 p-4 text-center">
                            <p class="mb-2 text-sm font-semibold text-slate-700">No leaderboard data for current filters.</p>
                            <div class="flex items-center justify-center gap-2">
                                <button type="button" data-empty-action="retry" class="rounded-lg bg-blue-600 px-3 py-2 text-xs font-semibold text-white hover:bg-blue-700">Retry</button>
                                <button type="button" data-empty-action="reset" class="rounded-lg border border-slate-300 px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-100">Reset filters</button>
                                <a href="https://github.com/Ackrome/matplobbot#readme" target="_blank" rel="noreferrer" class="rounded-lg border border-slate-300 px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-100">Docs</a>
                            </div>
                        </div>
                    </td>
                </tr>
            `;
        }
        const sorted = typeof getSortedLeaderboard === "function" ? getSortedLeaderboard() : [];
        const nextStart = state.page * state.pageSize;
        if (Array.isArray(sorted) && nextStart < sorted.length) {
            state.prefetchedNextPage = sorted.slice(nextStart, nextStart + state.pageSize);
        } else {
            state.prefetchedNextPage = [];
        }
        if (refs.table) {
            refs.table.classList.toggle("mpb-compact", state.tableDensity === "compact");
        }
        applyColumnVisibility();
    };

    const rawRenderActivityChart = renderActivityChart;
    renderActivityChart = function patchedActivity() {
        rawRenderActivityChart();
        refs.activityEmptyState?.classList.toggle("hidden", getFilteredActivity().length > 0);
        if (state.chart?.options?.plugins?.tooltip) {
            state.chart.options.plugins.tooltip.callbacks = {
                label(context) {
                    const current = context.parsed.y;
                    const prev = context.dataIndex > 0 ? context.dataset.data[context.dataIndex - 1] : null;
                    if (typeof prev !== "number") return `Actions: ${current}`;
                    const delta = current - prev;
                    return `Actions: ${current} (${delta >= 0 ? "+" : ""}${delta} vs prev)`;
                },
            };
        }
        applyChartZoom();
    };

    function persistPrefs() {
        localStorage.setItem(STORAGE.density, state.tableDensity);
        localStorage.setItem(STORAGE.columns, JSON.stringify(state.visibleColumns));
        localStorage.setItem(STORAGE.timezone, state.timezone);
    }

    function applyColumnVisibility() {
        COLUMNS.forEach((column) => {
            const isVisible = state.visibleColumns.includes(column);
            const idx = columnToIndex[column];
            document.querySelectorAll(`#leaderboardTable tr > *:nth-child(${idx})`).forEach((cell) => {
                cell.classList.toggle("hidden", !isVisible);
            });
        });
    }

    function renderColumnControls() {
        if (!refs.columnVisibilityList) return;
        refs.columnVisibilityList.innerHTML = COLUMNS.map((column) => `
            <label class="flex items-center gap-2 text-sm text-slate-700">
                <input type="checkbox" data-col="${column}" ${state.visibleColumns.includes(column) ? "checked" : ""}>
                <span>${column.replace("_", " ")}</span>
            </label>
        `).join("");
    }

    function syncMobileSheet() {
        if (refs.mobileRangeSelect) refs.mobileRangeSelect.value = state.range;
        if (refs.mobileSortSelect) refs.mobileSortSelect.value = `${state.sortBy}:${state.sortOrder}`;
        if (refs.mobilePageSizeSelect) refs.mobilePageSizeSelect.value = String(state.pageSize);
        if (refs.mobileTimezoneSelect) refs.mobileTimezoneSelect.value = state.timezone;
    }

    function applyChartZoom() {
        if (!state.chart || !state.chart.data?.labels) return;
        const total = state.chart.data.labels.length;
        if (!state.chartZoom.windowSize || state.chartZoom.windowSize >= total) {
            state.chart.options.scales.x.min = undefined;
            state.chart.options.scales.x.max = undefined;
        } else {
            state.chart.options.scales.x.min = 0;
            state.chart.options.scales.x.max = state.chartZoom.windowSize - 1;
        }
        state.chart.update("none");
        refs.chartResetZoomBtn?.classList.toggle("opacity-50", !state.chartZoom.windowSize || state.chartZoom.windowSize >= total);
    }

    function registerRetry() {
        state.telemetry.retriesUsed = (state.telemetry.retriesUsed || 0) + 1;
        localStorage.setItem(STORAGE.telemetry, JSON.stringify(state.telemetry));
        updateDiagnostics();
    }

    document.addEventListener("click", (event) => {
        const target = event.target;
        if (!(target instanceof HTMLElement)) return;
        const action = target.getAttribute("data-empty-action");
        if (action === "retry") {
            registerRetry();
            refreshFromRest({ silent: false });
            return;
        }
        if (action === "reset") {
            refs.resetFiltersBtn?.click();
            return;
        }
        if (!refs.columnVisibilityPanel || !refs.columnVisibilityBtn) return;
        if (!refs.columnVisibilityPanel.contains(target) && !refs.columnVisibilityBtn.contains(target)) {
            refs.columnVisibilityPanel.classList.add("hidden");
        }
    });

    document.addEventListener("DOMContentLoaded", () => {
        persistPrefs();
        renderColumnControls();
        applyColumnVisibility();
        syncMobileSheet();
        refs.timezoneSelect && (refs.timezoneSelect.value = state.timezone);
        updateDiagnostics();

        fetchWithAuth("/stats/leaderboard").catch(() => {});
        fetchWithAuth("/stats/activity").catch(() => {});

        refs.tableDensityBtn?.addEventListener("click", () => {
            state.tableDensity = state.tableDensity === "compact" ? "default" : "compact";
            refs.tableDensityBtn.textContent = state.tableDensity === "compact" ? "Density: Compact" : "Density: Default";
            persistPrefs();
            renderLeaderboard();
        });
        refs.columnVisibilityBtn?.addEventListener("click", () => refs.columnVisibilityPanel?.classList.toggle("hidden"));
        refs.columnVisibilityList?.addEventListener("change", (event) => {
            const target = event.target;
            if (!(target instanceof HTMLInputElement)) return;
            const key = target.getAttribute("data-col");
            if (!key) return;
            if (target.checked) state.visibleColumns = [...new Set([...state.visibleColumns, key])];
            else state.visibleColumns = state.visibleColumns.filter((entry) => entry !== key);
            if (state.visibleColumns.length === 0) state.visibleColumns = ["full_name"];
            persistPrefs();
            renderLeaderboard();
        });
        refs.timezoneSelect?.addEventListener("change", (event) => {
            state.timezone = event.target.value || "local";
            persistPrefs();
            renderLeaderboard();
            renderActivityChart();
        });

        refs.chartZoomInBtn?.addEventListener("click", () => {
            state.chartZoom.windowSize = state.chart ? Math.max(3, Math.floor((state.chartZoom.windowSize || state.chart.data.labels.length) * 0.75)) : null;
            applyChartZoom();
        });
        refs.chartZoomOutBtn?.addEventListener("click", () => {
            if (!state.chart) return;
            const total = state.chart.data.labels.length;
            state.chartZoom.windowSize = Math.min(total, Math.ceil((state.chartZoom.windowSize || total) * 1.35));
            if (state.chartZoom.windowSize >= total) state.chartZoom.windowSize = null;
            applyChartZoom();
        });
        refs.chartResetZoomBtn?.addEventListener("click", () => {
            state.chartZoom.windowSize = null;
            applyChartZoom();
        });

        refs.resetFiltersBtn?.addEventListener("click", () => {
            Object.assign(state, { sortBy: "actions_count", sortOrder: "desc", range: "today", page: 1, pageSize: 10, from: "", to: "" });
            syncStateToUrl();
            renderAll();
            syncMobileSheet();
        });

        refs.mobileFilterOpenBtn?.addEventListener("click", () => refs.mobileFilterSheet?.classList.remove("hidden"));
        refs.mobileFilterCloseBtn?.addEventListener("click", () => refs.mobileFilterSheet?.classList.add("hidden"));
        refs.mobileFilterApplyBtn?.addEventListener("click", () => {
            const [sortBy, sortOrder] = (refs.mobileSortSelect?.value || "actions_count:desc").split(":");
            state.sortBy = sortBy;
            state.sortOrder = sortOrder;
            state.range = refs.mobileRangeSelect?.value || "today";
            state.pageSize = Number(refs.mobilePageSizeSelect?.value) || 10;
            state.timezone = refs.mobileTimezoneSelect?.value || "local";
            refs.mobileFilterSheet?.classList.add("hidden");
            persistPrefs();
            syncStateToUrl();
            renderAll();
        });
        refs.mobileFilterResetBtn?.addEventListener("click", () => refs.resetFiltersBtn?.click());
        refs.mobileActionRetry?.addEventListener("click", registerRetry);
        refs.activityEmptyRetry?.addEventListener("click", registerRetry);
        refs.activityEmptyReset?.addEventListener("click", () => refs.resetFiltersBtn?.click());

        window.addEventListener("mpb-auth-ready", (event) => {
            const isAdmin = event.detail?.user?.role === "admin";
            elements.toggleDiagnosticsBtn?.classList.toggle("hidden", !isAdmin);
            refs.mobileActionDiagnostics?.classList.toggle("hidden", !isAdmin);
            if (!isAdmin) elements.diagnosticsPanel?.classList.add("hidden");
        });

        window.addEventListener("mpb-shortcut-refresh", () => {
            registerRetry();
            refreshFromRest({ silent: false });
        });
        window.addEventListener("mpb-shortcut-pagination", (event) => {
            if (event.detail?.direction === "next") elements.leaderboardNext?.click();
            if (event.detail?.direction === "prev") elements.leaderboardPrev?.click();
        });
    });
})();
