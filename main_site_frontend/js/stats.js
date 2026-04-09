const API_BASE = window.getMpbApiBase ? window.getMpbApiBase() : "/api";
const token = localStorage.getItem("jwt_token");

if (!token) {
    window.location.href = "/login";
}

const RANGE_LABELS = {
    today: "Today",
    "7d": "Last 7 days",
    "30d": "Last 30 days",
    custom: "Custom",
};

const DEFAULT_STATE = {
    sortBy: "actions_count",
    sortOrder: "desc",
    page: 1,
    pageSize: 10,
    range: "today",
    from: "",
    to: "",
};

const state = {
    ...DEFAULT_STATE,
    leaderboard: [],
    activity: [],
    totalActions: 0,
    ws: null,
    wsConnected: false,
    wsBackoffMs: 1000,
    wsReconnects: 0,
    lastUpdated: "",
    lastSyncSource: "-",
    failedRequests: 0,
    lastError: "-",
    apiLatencies: [],
    lastLatencyMs: null,
    chart: null,
    widgetHealth: {
        leaderboard: "idle",
        activity: "idle",
    },
};

const elements = {
    totalActions: document.getElementById("totalActions"),
    visibleUsers: document.getElementById("visibleUsers"),
    currentRangeLabel: document.getElementById("currentRangeLabel"),
    leaderboardBody: document.getElementById("leaderboardBody"),
    leaderboardStatus: document.getElementById("leaderboardStatus"),
    activityStatus: document.getElementById("activityStatus"),
    retryLeaderboardBtn: document.getElementById("retryLeaderboardBtn"),
    retryActivityBtn: document.getElementById("retryActivityBtn"),
    retryAllBtn: document.getElementById("retryAllBtn"),
    retryAllBtnMobile: document.getElementById("retryAllBtnMobile"),
    leaderboardMeta: document.getElementById("leaderboardMeta"),
    leaderboardPrev: document.getElementById("leaderboardPrev"),
    leaderboardNext: document.getElementById("leaderboardNext"),
    leaderboardPageInfo: document.getElementById("leaderboardPageInfo"),
    leaderboardPageSize: document.getElementById("leaderboardPageSize"),
    sortButtons: Array.from(document.querySelectorAll(".table-sort-btn")),
    rangeButtons: Array.from(document.querySelectorAll(".range-btn")),
    rangeFrom: document.getElementById("rangeFrom"),
    rangeTo: document.getElementById("rangeTo"),
    applyCustomRange: document.getElementById("applyCustomRange"),
    connectionDot: document.getElementById("connectionDot"),
    connectionText: document.getElementById("connectionText"),
    lastUpdated: document.getElementById("lastUpdated"),
    activityCanvas: document.getElementById("activityChart"),
    activitySkeleton: document.getElementById("activitySkeleton"),
    globalErrorBanner: document.getElementById("globalErrorBanner"),
    globalErrorText: document.getElementById("globalErrorText"),
    dismissGlobalError: document.getElementById("dismissGlobalError"),
    partialDegradationBanner: document.getElementById("partialDegradationBanner"),
    partialDegradationText: document.getElementById("partialDegradationText"),
    dismissPartialDegradation: document.getElementById("dismissPartialDegradation"),
    toastContainer: document.getElementById("toastContainer"),
    diagnosticsPanel: document.getElementById("diagnosticsPanel"),
    toggleDiagnosticsBtn: document.getElementById("toggleDiagnosticsBtn"),
    diagLastLatency: document.getElementById("diagLastLatency"),
    diagAvgLatency: document.getElementById("diagAvgLatency"),
    diagFailedRequests: document.getElementById("diagFailedRequests"),
    diagWsReconnects: document.getElementById("diagWsReconnects"),
    diagLastSyncSource: document.getElementById("diagLastSyncSource"),
    diagLastError: document.getElementById("diagLastError"),
};

function parseStateFromUrl() {
    const params = new URLSearchParams(window.location.search);

    const sortBy = params.get("sort");
    if (["rank", "full_name", "actions_count", "last_action_time"].includes(sortBy)) {
        state.sortBy = sortBy;
    }

    const sortOrder = params.get("order");
    if (["asc", "desc"].includes(sortOrder)) {
        state.sortOrder = sortOrder;
    }

    const page = Number(params.get("page"));
    if (Number.isInteger(page) && page > 0) {
        state.page = page;
    }

    const pageSize = Number(params.get("page_size"));
    if ([5, 10, 20, 50].includes(pageSize)) {
        state.pageSize = pageSize;
    }

    const range = params.get("range");
    if (["today", "7d", "30d", "custom"].includes(range)) {
        state.range = range;
    }

    const from = params.get("from");
    const to = params.get("to");
    if (from) state.from = from;
    if (to) state.to = to;
}

function syncStateToUrl() {
    const params = new URLSearchParams();
    params.set("sort", state.sortBy);
    params.set("order", state.sortOrder);
    params.set("page", String(state.page));
    params.set("page_size", String(state.pageSize));
    params.set("range", state.range);

    if (state.range === "custom") {
        if (state.from) params.set("from", state.from);
        if (state.to) params.set("to", state.to);
    }

    const query = params.toString();
    const nextUrl = `${window.location.pathname}${query ? `?${query}` : ""}`;
    window.history.replaceState({}, "", nextUrl);
}

function formatDateTime(value) {
    if (!value) return "-";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "-";
    return date.toLocaleString();
}

function formatLatency(ms) {
    if (typeof ms !== "number") return "-";
    return `${Math.round(ms)} ms`;
}

function showToast(type, message) {
    if (!elements.toastContainer || !message) return;

    const colors = {
        success: "bg-emerald-600",
        warning: "bg-amber-500",
        error: "bg-red-600",
        info: "bg-blue-600",
    };

    const toast = document.createElement("div");
    toast.className = `pointer-events-auto max-w-sm rounded-xl px-4 py-2 text-sm text-white shadow-lg ${colors[type] || colors.info}`;
    toast.textContent = message;
    elements.toastContainer.appendChild(toast);

    window.setTimeout(() => {
        toast.remove();
    }, 3800);
}

function showGlobalError(message) {
    if (!elements.globalErrorBanner || !elements.globalErrorText) return;
    elements.globalErrorText.textContent = message;
    elements.globalErrorBanner.classList.remove("hidden");
}

function hideGlobalError() {
    if (!elements.globalErrorBanner) return;
    elements.globalErrorBanner.classList.add("hidden");
}

function hidePartialDegradation() {
    if (!elements.partialDegradationBanner) return;
    elements.partialDegradationBanner.classList.add("hidden");
}

function showPartialDegradation(message) {
    if (!elements.partialDegradationBanner || !elements.partialDegradationText) return;
    elements.partialDegradationText.textContent = message;
    elements.partialDegradationBanner.classList.remove("hidden");
}

function getFailedWidgets() {
    return Object.entries(state.widgetHealth)
        .filter(([, status]) => status === "error")
        .map(([widget]) => widget);
}

function updateDashboardHealthState() {
    const failedWidgets = getFailedWidgets();
    if (failedWidgets.length === 0) {
        hidePartialDegradation();
        if (state.wsConnected) {
            setConnectionState("online", "Live updates");
        } else {
            setConnectionState("warning", "REST mode");
        }
        return;
    }

    const labels = failedWidgets.map((widget) => (widget === "leaderboard" ? "Leaderboard" : "Activity"));
    const healthyCount = Object.keys(state.widgetHealth).length - failedWidgets.length;
    const message = healthyCount > 0
        ? `Partial degradation: failed widget(s): ${labels.join(", ")}. Showing available data for the rest.`
        : `Dashboard degraded: all widgets failed (${labels.join(", ")}).`;
    showPartialDegradation(message);
    setConnectionState("warning", "Partial degradation");
}

function applyDegradedWidgetStatuses() {
    if (state.widgetHealth.leaderboard === "error") {
        const hasLeaderboardData = state.leaderboard.length > 0;
        setBlockStatus(
            elements.leaderboardStatus,
            hasLeaderboardData ? "Degraded: showing last leaderboard snapshot" : "Leaderboard unavailable",
            hasLeaderboardData ? "warning" : "error"
        );
    }

    if (state.widgetHealth.activity === "error") {
        const hasActivityData = getFilteredActivity().length > 0;
        setBlockStatus(
            elements.activityStatus,
            hasActivityData ? "Degraded: showing last activity snapshot" : "Activity widget unavailable",
            hasActivityData ? "warning" : "error"
        );
    }
}

function setConnectionState(status, label) {
    if (!elements.connectionDot || !elements.connectionText) return;

    elements.connectionDot.classList.remove("status-online", "status-connecting", "status-offline", "status-warning");

    if (status === "online") {
        elements.connectionDot.classList.add("status-online");
    } else if (status === "connecting") {
        elements.connectionDot.classList.add("status-connecting");
    } else if (status === "warning") {
        elements.connectionDot.classList.add("status-warning");
    } else {
        elements.connectionDot.classList.add("status-offline");
    }

    elements.connectionText.textContent = label;
}

function setBlockStatus(element, message, kind = "info") {
    if (!element) return;

    element.classList.remove("text-slate-500", "text-red-600", "text-emerald-600", "text-amber-600");

    if (kind === "error") {
        element.classList.add("text-red-600");
    } else if (kind === "ok") {
        element.classList.add("text-emerald-600");
    } else if (kind === "warning") {
        element.classList.add("text-amber-600");
    } else {
        element.classList.add("text-slate-500");
    }

    element.textContent = message;
}

function updateDiagnostics() {
    const avgLatency =
        state.apiLatencies.length > 0
            ? state.apiLatencies.reduce((sum, value) => sum + value, 0) / state.apiLatencies.length
            : null;

    if (elements.diagLastLatency) elements.diagLastLatency.textContent = formatLatency(state.lastLatencyMs);
    if (elements.diagAvgLatency) elements.diagAvgLatency.textContent = formatLatency(avgLatency);
    if (elements.diagFailedRequests) elements.diagFailedRequests.textContent = String(state.failedRequests);
    if (elements.diagWsReconnects) elements.diagWsReconnects.textContent = String(state.wsReconnects);
    if (elements.diagLastSyncSource) {
        const syncText = state.lastUpdated ? `${state.lastSyncSource} @ ${formatDateTime(state.lastUpdated)}` : state.lastSyncSource;
        elements.diagLastSyncSource.textContent = syncText;
    }
    if (elements.diagLastError) elements.diagLastError.textContent = state.lastError || "-";
}

function recordLatency(startTime) {
    const elapsed = performance.now() - startTime;
    state.lastLatencyMs = elapsed;
    state.apiLatencies.push(elapsed);
    if (state.apiLatencies.length > 25) {
        state.apiLatencies.shift();
    }
    updateDiagnostics();
}

function markSynced(syncSource, timestamp) {
    state.lastSyncSource = syncSource;
    state.lastUpdated = timestamp || new Date().toISOString();

    if (elements.lastUpdated) {
        elements.lastUpdated.textContent = formatDateTime(state.lastUpdated);
    }

    updateDiagnostics();
}

function normalizeLeaderboard(list) {
    if (!Array.isArray(list)) return [];

    return list.map((user, index) => ({
        rank: index + 1,
        user_id: user.user_id,
        full_name: (user.full_name || "Unknown user").trim(),
        username: user.username || "",
        actions_count: Number(user.actions_count) || 0,
        last_action_time: user.last_action_time || "",
        avatar_pic_url: user.avatar_pic_url || "",
    }));
}

function normalizeActivity(list) {
    if (!Array.isArray(list)) return [];

    return list
        .map((item) => {
            const periodLabel = item.period_start || item.period || item.date || "";
            return {
                period: periodLabel,
                count: Number(item.actions_count ?? item.count ?? 0),
            };
        })
        .filter((item) => item.period);
}

function getRangeBounds() {
    const now = new Date();
    now.setHours(23, 59, 59, 999);

    const startOfToday = new Date(now);
    startOfToday.setHours(0, 0, 0, 0);

    if (state.range === "today") {
        return { from: startOfToday, to: now };
    }

    if (state.range === "7d") {
        const from = new Date(startOfToday);
        from.setDate(from.getDate() - 6);
        return { from, to: now };
    }

    if (state.range === "30d") {
        const from = new Date(startOfToday);
        from.setDate(from.getDate() - 29);
        return { from, to: now };
    }

    if (state.range === "custom") {
        const from = state.from ? new Date(`${state.from}T00:00:00`) : null;
        const to = state.to ? new Date(`${state.to}T23:59:59`) : null;

        if (from && to && !Number.isNaN(from.getTime()) && !Number.isNaN(to.getTime()) && from <= to) {
            return { from, to };
        }
    }

    return null;
}

function getFilteredActivity() {
    const normalized = normalizeActivity(state.activity);
    if (normalized.length === 0) return [];

    const withDates = normalized
        .map((item) => ({
            ...item,
            dateObj: new Date(item.period),
        }))
        .filter((item) => !Number.isNaN(item.dateObj.getTime()));

    if (withDates.length === 0) {
        return normalized;
    }

    const bounds = getRangeBounds();
    if (!bounds) {
        return withDates
            .sort((a, b) => a.dateObj - b.dateObj)
            .map((item) => ({ period: item.period, count: item.count }));
    }

    return withDates
        .filter((item) => item.dateObj >= bounds.from && item.dateObj <= bounds.to)
        .sort((a, b) => a.dateObj - b.dateObj)
        .map((item) => ({ period: item.period, count: item.count }));
}

function getSortedLeaderboard() {
    const rows = [...state.leaderboard];

    const getComparable = (entry) => {
        if (state.sortBy === "full_name") {
            return entry.full_name.toLowerCase();
        }
        if (state.sortBy === "last_action_time") {
            const dt = entry.last_action_time ? new Date(entry.last_action_time) : null;
            return dt && !Number.isNaN(dt.getTime()) ? dt.getTime() : 0;
        }

        if (state.sortBy === "rank" || state.sortBy === "actions_count") {
            return Number(entry.actions_count) || 0;
        }

        return Number(entry.actions_count) || 0;
    };

    rows.sort((a, b) => {
        const av = getComparable(a);
        const bv = getComparable(b);

        if (typeof av === "string" || typeof bv === "string") {
            return state.sortOrder === "asc" ? String(av).localeCompare(String(bv)) : String(bv).localeCompare(String(av));
        }

        return state.sortOrder === "asc" ? av - bv : bv - av;
    });

    return rows;
}

function getPaginatedRows(rows) {
    const totalPages = Math.max(1, Math.ceil(rows.length / state.pageSize));
    if (state.page > totalPages) {
        state.page = totalPages;
    }

    const start = (state.page - 1) * state.pageSize;
    const end = start + state.pageSize;
    return {
        rows: rows.slice(start, end),
        totalPages,
        totalRows: rows.length,
        startIndex: rows.length === 0 ? 0 : start + 1,
        endIndex: Math.min(end, rows.length),
    };
}

function renderSortIndicators() {
    elements.sortButtons.forEach((button) => {
        const field = button.dataset.sort;
        const icon = button.querySelector(".table-sort-icon");
        const th = button.closest("th");

        if (field === state.sortBy) {
            const arrow = state.sortOrder === "asc" ? "↑" : "↓";
            if (icon) icon.textContent = arrow;
            if (th) th.setAttribute("aria-sort", state.sortOrder === "asc" ? "ascending" : "descending");
        } else {
            if (icon) icon.textContent = "-";
            if (th) th.setAttribute("aria-sort", "none");
        }
    });
}

function renderLeaderboard() {
    if (!elements.leaderboardBody) return;

    const sorted = getSortedLeaderboard();
    const pageData = getPaginatedRows(sorted);

    if (pageData.totalRows === 0) {
        elements.leaderboardBody.innerHTML = `
            <tr>
                <td colspan="4" class="px-4 py-6 text-sm text-slate-500">No leaderboard data for current filters.</td>
            </tr>
        `;
        setBlockStatus(elements.leaderboardStatus, "No data", "warning");
    } else {
        elements.leaderboardBody.innerHTML = pageData.rows
            .map((user, index) => {
                const rankLabel = pageData.startIndex + index;
                const initial = user.full_name ? user.full_name[0].toUpperCase() : "?";
                const username = user.username ? `@${user.username}` : "-";
                const lastActive = user.last_action_time ? formatDateTime(user.last_action_time) : "-";

                return `
                    <tr class="border-b border-slate-100 hover:bg-slate-50 transition-colors">
                        <td class="px-4 py-3 text-slate-400 font-semibold">${rankLabel}</td>
                        <td class="px-4 py-3">
                            <div class="flex items-center gap-3">
                                <div class="w-9 h-9 rounded-xl bg-gradient-to-br from-blue-500 to-indigo-600 text-white flex items-center justify-center font-bold text-sm">${initial}</div>
                                <div class="min-w-0">
                                    <div class="font-semibold text-slate-800 truncate">${user.full_name}</div>
                                    <div class="text-xs text-slate-500 truncate">${username}</div>
                                </div>
                            </div>
                        </td>
                        <td class="px-4 py-3 text-right font-mono font-bold text-blue-600">${user.actions_count}</td>
                        <td class="px-4 py-3 text-xs text-slate-500 whitespace-nowrap">${lastActive}</td>
                    </tr>
                `;
            })
            .join("");

        setBlockStatus(elements.leaderboardStatus, `Loaded ${pageData.totalRows} users`, "ok");
    }

    if (elements.leaderboardMeta) {
        elements.leaderboardMeta.textContent =
            pageData.totalRows === 0
                ? "0 results"
                : `Showing ${pageData.startIndex}-${pageData.endIndex} of ${pageData.totalRows}`;
    }

    if (elements.leaderboardPageInfo) {
        elements.leaderboardPageInfo.textContent = `${state.page} / ${pageData.totalPages}`;
    }

    if (elements.leaderboardPrev) {
        elements.leaderboardPrev.disabled = state.page <= 1;
        elements.leaderboardPrev.classList.toggle("opacity-50", state.page <= 1);
    }

    if (elements.leaderboardNext) {
        elements.leaderboardNext.disabled = state.page >= pageData.totalPages;
        elements.leaderboardNext.classList.toggle("opacity-50", state.page >= pageData.totalPages);
    }

    renderSortIndicators();
}

function renderActivityChart() {
    if (!elements.activityCanvas) return;

    const filtered = getFilteredActivity();

    if (filtered.length === 0) {
        setBlockStatus(elements.activityStatus, "No activity in selected range", "warning");
    } else {
        setBlockStatus(elements.activityStatus, `Points: ${filtered.length}`, "ok");
    }

    const labels = filtered.map((entry) => entry.period);
    const values = filtered.map((entry) => entry.count);

    if (state.chart) {
        state.chart.destroy();
    }

    state.chart = new Chart(elements.activityCanvas.getContext("2d"), {
        type: "line",
        data: {
            labels,
            datasets: [
                {
                    label: "Actions",
                    data: values,
                    borderColor: "#2563eb",
                    backgroundColor: "rgba(37, 99, 235, 0.12)",
                    borderWidth: 2,
                    tension: 0.35,
                    fill: true,
                    pointRadius: 2,
                    pointHoverRadius: 4,
                },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: false,
                },
                tooltip: {
                    mode: "index",
                    intersect: false,
                },
            },
            interaction: {
                mode: "index",
                intersect: false,
            },
            scales: {
                y: {
                    beginAtZero: true,
                    grid: {
                        color: "rgba(148, 163, 184, 0.2)",
                    },
                },
                x: {
                    grid: {
                        display: false,
                    },
                },
            },
        },
    });
}

function renderKpis() {
    if (elements.totalActions) {
        const fallbackTotal = state.leaderboard.reduce((sum, item) => sum + (item.actions_count || 0), 0);
        const total = state.totalActions > 0 ? state.totalActions : fallbackTotal;
        elements.totalActions.textContent = total.toLocaleString();
    }

    if (elements.visibleUsers) {
        elements.visibleUsers.textContent = String(state.leaderboard.length);
    }

    if (elements.currentRangeLabel) {
        elements.currentRangeLabel.textContent = RANGE_LABELS[state.range] || "Custom";
    }
}

function renderAll() {
    renderKpis();
    renderLeaderboard();
    renderActivityChart();
    updateDiagnostics();
}

function setRetryButtonsVisible(visible) {
    if (elements.retryActivityBtn) {
        elements.retryActivityBtn.classList.toggle("hidden", !visible);
    }
    if (elements.retryLeaderboardBtn) {
        elements.retryLeaderboardBtn.classList.toggle("hidden", !visible);
    }
}

function setLoading(isLoading) {
    if (elements.activitySkeleton) {
        elements.activitySkeleton.classList.toggle("hidden", !isLoading);
    }

    if (!elements.leaderboardBody) return;

    if (isLoading) {
        elements.leaderboardBody.innerHTML = Array.from({ length: 5 }, () => `
            <tr>
                <td colspan="4" class="px-4 py-4"><div class="h-4 w-full skeleton rounded"></div></td>
            </tr>
        `).join("");
    }
}

async function fetchWithAuth(endpoint) {
    const startTime = performance.now();

    const response = await fetch(`${API_BASE}${endpoint}`, {
        headers: {
            Authorization: `Bearer ${token}`,
        },
    });

    recordLatency(startTime);

    if (response.status === 401) {
        window.performLogout();
        throw new Error("Session expired");
    }

    let body = null;
    try {
        body = await response.json();
    } catch {
        body = null;
    }

    if (!response.ok) {
        const detail = body && body.detail ? body.detail : `Request failed (${response.status})`;
        throw new Error(detail);
    }

    return body;
}

function registerFailure(errorMessage) {
    state.failedRequests += 1;
    state.lastError = errorMessage;
    updateDiagnostics();
}

async function refreshFromRest({ silent = false } = {}) {
    if (!silent) {
        setLoading(true);
        setBlockStatus(elements.leaderboardStatus, "Loading...", "info");
        setBlockStatus(elements.activityStatus, "Loading...", "info");
    }

    const [leaderboardResult, activityResult] = await Promise.allSettled([
        fetchWithAuth("/stats/leaderboard"),
        fetchWithAuth("/stats/activity"),
    ]);

    let successCount = 0;
    let failureCount = 0;
    const failureMessages = [];

    if (leaderboardResult.status === "fulfilled") {
        state.leaderboard = normalizeLeaderboard(leaderboardResult.value);
        state.totalActions = state.leaderboard.reduce((sum, user) => sum + (user.actions_count || 0), 0);
        state.widgetHealth.leaderboard = "ok";
        successCount += 1;
    } else {
        const message = leaderboardResult.reason instanceof Error
            ? leaderboardResult.reason.message
            : "Leaderboard request failed";
        registerFailure(message);
        state.widgetHealth.leaderboard = "error";
        failureMessages.push(`Leaderboard: ${message}`);
        failureCount += 1;
    }

    if (activityResult.status === "fulfilled") {
        state.activity = normalizeActivity(activityResult.value);
        state.widgetHealth.activity = "ok";
        successCount += 1;
    } else {
        const message = activityResult.reason instanceof Error
            ? activityResult.reason.message
            : "Activity request failed";
        registerFailure(message);
        state.widgetHealth.activity = "error";
        failureMessages.push(`Activity: ${message}`);
        failureCount += 1;
    }

    if (successCount > 0) {
        hideGlobalError();
        setRetryButtonsVisible(failureCount > 0);
        renderAll();
        applyDegradedWidgetStatuses();
        markSynced("REST", new Date().toISOString());
        updateDashboardHealthState();

        if (failureCount > 0) {
            showToast("warning", `Partial degradation detected. ${failureMessages.join(" | ")}`);
        }
    } else {
        const combinedError = failureMessages.join(" | ") || "Unknown REST error";
        showGlobalError(`Failed to load dashboard: ${combinedError}`);
        setRetryButtonsVisible(true);
        setBlockStatus(elements.leaderboardStatus, "Failed. Retry required.", "error");
        setBlockStatus(elements.activityStatus, "Failed. Retry required.", "error");
        showToast("error", `Dashboard load failed: ${combinedError}`);
        updateDashboardHealthState();
    }

    setLoading(false);
}

function applyStatsPayload(payload) {
    if (!payload || typeof payload !== "object") return;

    if (Array.isArray(payload.leaderboard)) {
        state.leaderboard = normalizeLeaderboard(payload.leaderboard);
    }

    if (payload.total_actions !== undefined && payload.total_actions !== null) {
        state.totalActions = Number(payload.total_actions) || 0;
    }

    if (payload.activity_over_time && Array.isArray(payload.activity_over_time.day)) {
        state.activity = normalizeActivity(payload.activity_over_time.day);
    } else if (Array.isArray(payload.activity)) {
        state.activity = normalizeActivity(payload.activity);
    }

    if (state.totalActions <= 0 && state.leaderboard.length > 0) {
        state.totalActions = state.leaderboard.reduce((sum, user) => sum + (user.actions_count || 0), 0);
    }

    state.widgetHealth.leaderboard = "ok";
    state.widgetHealth.activity = "ok";
    hideGlobalError();
    hidePartialDegradation();
    setRetryButtonsVisible(false);
    renderAll();

    markSynced("WebSocket", payload.last_updated || new Date().toISOString());
    updateDashboardHealthState();
}

function scheduleWsReconnect() {
    state.wsReconnects += 1;
    updateDiagnostics();

    const waitMs = Math.min(state.wsBackoffMs, 30000);
    state.wsBackoffMs = Math.min(state.wsBackoffMs * 2, 30000);

    window.setTimeout(() => {
        connectWebSocket();
    }, waitMs);
}

function connectWebSocket() {
    if (!token) return;

    const protocol = window.location.protocol === "https:" ? "wss" : "ws";
    const wsUrl = `${protocol}://${window.location.host}/ws/stats/total_actions?token=${encodeURIComponent(token)}`;

    setConnectionState("connecting", "Connecting...");

    const socket = new WebSocket(wsUrl);
    state.ws = socket;

    socket.addEventListener("open", () => {
        state.wsConnected = true;
        state.wsBackoffMs = 1000;
        updateDashboardHealthState();
        showToast("success", "Live stats connected");
    });

    socket.addEventListener("message", (event) => {
        try {
            const payload = JSON.parse(event.data);
            if (payload && payload.error) {
                throw new Error(payload.error);
            }
            applyStatsPayload(payload);
        } catch (error) {
            const message = error instanceof Error ? error.message : "Invalid live payload";
            registerFailure(message);
            showGlobalError(`Live data error: ${message}`);
            setRetryButtonsVisible(true);
            setConnectionState("warning", "Live payload warning");
            showToast("warning", "Live data issue. Retrying... ");
        }
    });

    socket.addEventListener("close", () => {
        if (state.ws !== socket) return;

        state.wsConnected = false;
        setConnectionState("offline", "Disconnected");
        setRetryButtonsVisible(true);
        showToast("warning", "Live connection lost. Reconnecting...");
        scheduleWsReconnect();
    });

    socket.addEventListener("error", () => {
        setConnectionState("warning", "Connection error");
    });
}

function updateRangeControls() {
    elements.rangeButtons.forEach((button) => {
        button.classList.toggle("active", button.dataset.range === state.range);
    });

    const isCustom = state.range === "custom";
    elements.rangeFrom.disabled = !isCustom;
    elements.rangeTo.disabled = !isCustom;
    elements.applyCustomRange.disabled = !isCustom;

    if (state.from) elements.rangeFrom.value = state.from;
    if (state.to) elements.rangeTo.value = state.to;
}

function applyRangePreset(range) {
    state.range = range;
    if (range !== "custom") {
        state.from = "";
        state.to = "";
    }

    state.page = 1;
    updateRangeControls();
    syncStateToUrl();
    renderKpis();
    renderActivityChart();
}

function applyCustomRange() {
    const from = elements.rangeFrom.value;
    const to = elements.rangeTo.value;

    if (!from || !to) {
        showToast("warning", "Pick both custom dates");
        return;
    }

    if (new Date(from) > new Date(to)) {
        showToast("warning", "From date must be earlier than To date");
        return;
    }

    state.range = "custom";
    state.from = from;
    state.to = to;
    state.page = 1;

    updateRangeControls();
    syncStateToUrl();
    renderKpis();
    renderActivityChart();
}

function changeSort(field) {
    if (state.sortBy === field) {
        state.sortOrder = state.sortOrder === "asc" ? "desc" : "asc";
    } else {
        state.sortBy = field;
        state.sortOrder = field === "full_name" ? "asc" : "desc";
    }

    state.page = 1;
    syncStateToUrl();
    renderLeaderboard();
}

function wireEvents() {
    elements.sortButtons.forEach((button) => {
        button.addEventListener("click", () => changeSort(button.dataset.sort));
    });

    elements.leaderboardPrev?.addEventListener("click", () => {
        state.page = Math.max(1, state.page - 1);
        syncStateToUrl();
        renderLeaderboard();
    });

    elements.leaderboardNext?.addEventListener("click", () => {
        state.page += 1;
        syncStateToUrl();
        renderLeaderboard();
    });

    elements.leaderboardPageSize?.addEventListener("change", (event) => {
        state.pageSize = Number(event.target.value) || 10;
        state.page = 1;
        syncStateToUrl();
        renderLeaderboard();
    });

    elements.rangeButtons.forEach((button) => {
        button.addEventListener("click", () => applyRangePreset(button.dataset.range));
    });

    elements.applyCustomRange?.addEventListener("click", applyCustomRange);

    elements.retryAllBtn?.addEventListener("click", async () => {
        await refreshFromRest({ silent: false });
        showToast("info", "Retry requested");
    });

    elements.retryAllBtnMobile?.addEventListener("click", async () => {
        await refreshFromRest({ silent: false });
        showToast("info", "Retry requested");
    });

    elements.retryActivityBtn?.addEventListener("click", async () => {
        await refreshFromRest({ silent: false });
        showToast("info", "Activity reload requested");
    });

    elements.retryLeaderboardBtn?.addEventListener("click", async () => {
        await refreshFromRest({ silent: false });
        showToast("info", "Leaderboard reload requested");
    });

    elements.dismissGlobalError?.addEventListener("click", hideGlobalError);
    elements.dismissPartialDegradation?.addEventListener("click", hidePartialDegradation);

    elements.toggleDiagnosticsBtn?.addEventListener("click", () => {
        elements.diagnosticsPanel?.classList.toggle("hidden");
    });
}

function applyInitialControls() {
    if (elements.leaderboardPageSize) {
        elements.leaderboardPageSize.value = String(state.pageSize);
    }

    updateRangeControls();
    syncStateToUrl();
}

document.addEventListener("DOMContentLoaded", async () => {
    parseStateFromUrl();
    applyInitialControls();
    wireEvents();

    setLoading(true);
    setConnectionState("connecting", "Connecting...");
    setBlockStatus(elements.activityStatus, "Loading...", "info");
    setBlockStatus(elements.leaderboardStatus, "Loading...", "info");

    await refreshFromRest({ silent: false });
    connectWebSocket();

    window.setInterval(() => {
        if (!state.wsConnected) {
            refreshFromRest({ silent: true });
        }
    }, 60000);
});
