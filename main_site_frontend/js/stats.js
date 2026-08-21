const API_BASE = window.getMpbApiBase ? window.getMpbApiBase() : "/api";
const token = localStorage.getItem("jwt_token");

if (!token) {
    window.location.href = "/login";
}

const STATS_I18N = {
    en: {
        "stats.meta.title": "Stats Dashboard | ITISHCHENKO",
        "stats.connection.connecting": "Connecting...",
        "stats.connection.connected": "Live updates",
        "stats.connection.disconnected": "Disconnected",
        "stats.connection.rest": "REST mode",
        "stats.connection.warning": "Connection error",
        "stats.connection.partial": "Partial degradation",
        "stats.lastUpdated": "Last updated:",
        "stats.timezone": "Timezone",
        "stats.timezone.local": "Local",
        "stats.density.default": "Density: Default",
        "stats.density.compact": "Density: Compact",
        "stats.columns": "Columns",
        "stats.columns.visible": "Visible columns",
        "stats.resetFilters": "Reset filters",
        "stats.refreshScheduleCache": "Refresh schedule cache",
        "stats.refreshScheduleCache.mobile": "Schedule cache",
        "stats.refreshing": "Refreshing...",
        "stats.retry": "Retry",
        "stats.diagnostics": "Diagnostics",
        "stats.filters": "Filters",
        "stats.refresh": "Refresh",
        "stats.clear": "Clear",
        "stats.close": "Close",
        "stats.dismiss": "Dismiss",
        "stats.hide": "Hide",
        "stats.docs": "Docs",
        "stats.reset": "Reset",
        "stats.range.presets": "Date range presets",
        "stats.range.today": "Today",
        "stats.range.last7": "Last 7 days",
        "stats.range.last30": "Last 30 days",
        "stats.range.custom": "Custom",
        "stats.range.from": "From date",
        "stats.range.to": "To date",
        "stats.range.apply": "Apply",
        "stats.tabs.aria": "Stats dashboard sections",
        "stats.views.dashboard": "Dashboard",
        "stats.views.modules": "Modules",
        "stats.errors.requestFailed": "Request failed.",
        "stats.errors.partial": "Some dashboard widgets are unavailable.",
        "stats.diagnostics.title": "Admin Diagnostics",
        "stats.diagnostics.lastApiLatency": "Last API latency",
        "stats.diagnostics.avgApiLatency": "Avg API latency",
        "stats.diagnostics.failedRequests": "Failed requests",
        "stats.diagnostics.retriesUsed": "Retries used",
        "stats.diagnostics.failedWidgets": "Failed widget loads",
        "stats.diagnostics.ttfd": "Time to first data",
        "stats.diagnostics.wsReconnects": "WS reconnects",
        "stats.diagnostics.lastSyncSource": "Last sync source",
        "stats.diagnostics.lastSyncError": "Last sync error",
        "stats.proxy.title": "Proxy Diagnostics",
        "stats.proxy.loading": "Loading proxy summary...",
        "stats.proxy.notRequested": "Proxy summary has not been requested yet.",
        "stats.proxy.lastFetched": "Last fetched:",
        "stats.proxy.telegramNode": "Telegram selected node",
        "stats.proxy.openaiNode": "OpenAI selected node",
        "stats.proxy.inventory": "Build inventory",
        "stats.proxy.source": "Summary source",
        "stats.proxy.route": "Route",
        "stats.proxy.server": "Server",
        "stats.proxy.latency": "Latency",
        "stats.proxy.alive": "Alive",
        "stats.proxy.selected": "Selected",
        "stats.proxy.waiting": "Waiting for proxy summary...",
        "stats.proxy.noActiveNode": "No active node",
        "stats.proxy.availableNoCandidates": "Proxy summary is available, but there are no ranked candidates yet.",
        "stats.proxy.unavailable": "Proxy summary unavailable",
        "stats.proxy.rowsLoaded": "{count} proxy candidate rows loaded from {source}.",
        "stats.proxy.current": "Current",
        "stats.proxy.yes": "Yes",
        "stats.proxy.no": "No",
        "stats.proxy.unknown": "Unknown",
        "stats.proxy.route.telegram": "Telegram",
        "stats.proxy.route.openai": "OpenAI",
        "stats.kpi.totalActions": "Total actions",
        "stats.kpi.visibleUsers": "Visible leaderboard users",
        "stats.kpi.currentRange": "Current range",
        "stats.activity.title": "User activity",
        "stats.activity.zoomIn": "Zoom +",
        "stats.activity.zoomOut": "Zoom -",
        "stats.activity.resetZoom": "Reset zoom",
        "stats.activity.loading": "Loading...",
        "stats.activity.noData": "No activity in selected range",
        "stats.activity.points": "Points: {count}",
        "stats.activity.empty": "No activity data for current filters.",
        "stats.activity.chartAria": "Activity chart",
        "stats.activity.dataset": "Actions",
        "stats.activity.tooltip": "Actions: {count}",
        "stats.activity.tooltipDelta": "Actions: {count} ({delta} vs prev)",
        "stats.leaderboard.title": "Leaderboard",
        "stats.leaderboard.caption": "Leaderboard with sorting and pagination",
        "stats.leaderboard.user": "User",
        "stats.leaderboard.actions": "Actions",
        "stats.leaderboard.lastActive": "Last active",
        "stats.leaderboard.rows": "Rows",
        "stats.leaderboard.prev": "Prev",
        "stats.leaderboard.next": "Next",
        "stats.leaderboard.loading": "Loading...",
        "stats.leaderboard.noData": "No leaderboard data for current filters.",
        "stats.leaderboard.noStatus": "No data",
        "stats.leaderboard.loaded": "Loaded {count} users",
        "stats.leaderboard.results": "{count} results",
        "stats.leaderboard.showing": "Showing {start}-{end} of {total}",
        "stats.user.unknown": "Unknown user",
        "stats.modules.eyebrow": "Schedule modules",
        "stats.modules.title": "Manual module mappings",
        "stats.modules.description": "Create and maintain discipline-to-module rules used by schedule filters. These rules mirror `/set_module Discipline | Module`.",
        "stats.modules.form.title": "Create or update",
        "stats.modules.form.new": "New mapping",
        "stats.modules.form.editing": "Editing: {discipline}",
        "stats.modules.discipline": "Discipline",
        "stats.modules.module": "Module",
        "stats.modules.actions": "Actions",
        "stats.modules.search": "Search",
        "stats.modules.searchPlaceholder": "Discipline or module",
        "stats.modules.filter": "Module filter",
        "stats.modules.all": "All modules",
        "stats.modules.save": "Save mapping",
        "stats.modules.saveChanges": "Save changes",
        "stats.modules.openToLoad": "Open the Modules tab to load mappings.",
        "stats.modules.status.notLoaded": "Not loaded",
        "stats.modules.status.loading": "Loading mappings...",
        "stats.modules.status.loaded": "Loaded {count} mappings",
        "stats.modules.status.failed": "Failed to load mappings",
        "stats.modules.status.saving": "Saving mapping...",
        "stats.modules.status.saved": "Mapping saved",
        "stats.modules.status.saveFailed": "Save failed",
        "stats.modules.empty": "No manual mappings match current filters.",
        "stats.modules.meta.adminOnly": "Mappings are loaded only for admins.",
        "stats.modules.meta.partial": "Showing {shown} of {total} matching mappings. Narrow the search to find older rows.",
        "stats.modules.meta.loaded": "{count} mappings loaded.",
        "stats.modules.edit": "Edit",
        "stats.modules.delete": "Delete",
        "stats.modules.confirmDelete": "Delete mapping for \"{discipline}\"?",
        "stats.modules.deleted": "Mapping deleted",
        "stats.modules.failed": "Module mappings failed: {message}",
        "stats.modules.deleteFailed": "Delete failed: {message}",
        "stats.modules.fillBoth": "Fill both discipline and module",
        "stats.modules.oldNotRemoved": "Saved new mapping, but old discipline name was not removed.",
        "stats.modules.savedToast": "Saved: {discipline}",
        "stats.modules.saveFailedToast": "Save failed: {message}",
        "stats.mobileFilters.title": "Mobile filters",
        "stats.mobileFilters.range": "Range",
        "stats.mobileFilters.sort": "Sort",
        "stats.mobileFilters.rowsPerPage": "Rows per page",
        "stats.sort.actionsDesc": "Actions desc",
        "stats.sort.actionsAsc": "Actions asc",
        "stats.sort.userAsc": "User A-Z",
        "stats.sort.userDesc": "User Z-A",
        "stats.sort.lastActiveDesc": "Last active desc",
        "stats.sort.lastActiveAsc": "Last active asc",
        "stats.toast.retryRequested": "Retry requested",
        "stats.toast.activityReload": "Activity reload requested",
        "stats.toast.leaderboardReload": "Leaderboard reload requested",
        "stats.toast.liveConnected": "Live stats connected",
        "stats.toast.liveIssue": "Live data issue. Retrying...",
        "stats.toast.liveLost": "Live connection lost. Reconnecting...",
        "stats.toast.pickDates": "Pick both custom dates",
        "stats.toast.dateOrder": "From date must be earlier than To date",
        "stats.dashboard.failed": "Failed to load dashboard: {message}",
        "stats.dashboard.loadFailed": "Dashboard load failed: {message}",
        "stats.dashboard.loadingFailed": "Failed. Retry required.",
        "stats.dashboard.partial": "Partial degradation detected. {message}",
        "stats.scheduleCache.done": "Schedule cache refresh finished.",
        "stats.scheduleCache.summary": "Schedule cache refresh finished: {parts}.",
        "stats.scheduleCache.refreshed": "{count} refreshed",
        "stats.scheduleCache.remapped": "{count} ids remapped",
        "stats.scheduleCache.failed": "{count} failed",
        "stats.scheduleCache.skipped": "{count} skipped",
        "stats.scheduleCache.error": "Schedule cache refresh failed: {message}",
        "stats.column.rank": "Rank",
        "stats.column.full_name": "User",
        "stats.column.actions_count": "Actions",
        "stats.column.last_action_time": "Last active",
    },
    ru: {
        "stats.meta.title": "Статистика | ITISHCHENKO",
        "stats.connection.connecting": "Подключение...",
        "stats.connection.connected": "Live-обновления",
        "stats.connection.disconnected": "Отключено",
        "stats.connection.rest": "REST-режим",
        "stats.connection.warning": "Ошибка соединения",
        "stats.connection.partial": "Частичная деградация",
        "stats.lastUpdated": "Обновлено:",
        "stats.timezone": "Часовой пояс",
        "stats.timezone.local": "Локально",
        "stats.density.default": "Плотность: обычная",
        "stats.density.compact": "Плотность: компактная",
        "stats.columns": "Колонки",
        "stats.columns.visible": "Видимые колонки",
        "stats.resetFilters": "Сбросить фильтры",
        "stats.refreshScheduleCache": "Обновить кеш расписаний",
        "stats.refreshScheduleCache.mobile": "Кеш расписаний",
        "stats.refreshing": "Обновляю...",
        "stats.retry": "Повторить",
        "stats.diagnostics": "Диагностика",
        "stats.filters": "Фильтры",
        "stats.refresh": "Обновить",
        "stats.clear": "Очистить",
        "stats.close": "Закрыть",
        "stats.dismiss": "Скрыть",
        "stats.hide": "Скрыть",
        "stats.docs": "Документация",
        "stats.reset": "Сброс",
        "stats.range.presets": "Быстрый выбор периода",
        "stats.range.today": "Сегодня",
        "stats.range.last7": "Последние 7 дней",
        "stats.range.last30": "Последние 30 дней",
        "stats.range.custom": "Свой",
        "stats.range.from": "Дата начала",
        "stats.range.to": "Дата конца",
        "stats.range.apply": "Применить",
        "stats.tabs.aria": "Разделы статистики",
        "stats.views.dashboard": "Дашборд",
        "stats.views.modules": "Модули",
        "stats.errors.requestFailed": "Запрос не выполнен.",
        "stats.errors.partial": "Часть виджетов временно недоступна.",
        "stats.diagnostics.title": "Диагностика админа",
        "stats.diagnostics.lastApiLatency": "Последняя задержка API",
        "stats.diagnostics.avgApiLatency": "Средняя задержка API",
        "stats.diagnostics.failedRequests": "Ошибок запросов",
        "stats.diagnostics.retriesUsed": "Повторов",
        "stats.diagnostics.failedWidgets": "Ошибок виджетов",
        "stats.diagnostics.ttfd": "Время до первых данных",
        "stats.diagnostics.wsReconnects": "WS-переподключений",
        "stats.diagnostics.lastSyncSource": "Последний источник синхронизации",
        "stats.diagnostics.lastSyncError": "Последняя ошибка",
        "stats.proxy.title": "Диагностика прокси",
        "stats.proxy.loading": "Загружаю сводку прокси...",
        "stats.proxy.notRequested": "Сводка прокси еще не запрашивалась.",
        "stats.proxy.lastFetched": "Получено:",
        "stats.proxy.telegramNode": "Узел Telegram",
        "stats.proxy.openaiNode": "Узел OpenAI",
        "stats.proxy.inventory": "Состав сборки",
        "stats.proxy.source": "Источник сводки",
        "stats.proxy.route": "Маршрут",
        "stats.proxy.server": "Сервер",
        "stats.proxy.latency": "Задержка",
        "stats.proxy.alive": "Живой",
        "stats.proxy.selected": "Выбран",
        "stats.proxy.waiting": "Ожидаю сводку прокси...",
        "stats.proxy.noActiveNode": "Нет активного узла",
        "stats.proxy.availableNoCandidates": "Сводка прокси доступна, но кандидатов в рейтинге пока нет.",
        "stats.proxy.unavailable": "Сводка прокси недоступна",
        "stats.proxy.rowsLoaded": "Загружено строк прокси: {count}. Источник: {source}.",
        "stats.proxy.current": "Текущий",
        "stats.proxy.yes": "Да",
        "stats.proxy.no": "Нет",
        "stats.proxy.unknown": "Неизвестно",
        "stats.proxy.route.telegram": "Telegram",
        "stats.proxy.route.openai": "OpenAI",
        "stats.kpi.totalActions": "Всего действий",
        "stats.kpi.visibleUsers": "Пользователей в рейтинге",
        "stats.kpi.currentRange": "Текущий период",
        "stats.activity.title": "Активность пользователей",
        "stats.activity.zoomIn": "Приблизить",
        "stats.activity.zoomOut": "Отдалить",
        "stats.activity.resetZoom": "Сбросить зум",
        "stats.activity.loading": "Загрузка...",
        "stats.activity.noData": "Нет активности в выбранном периоде",
        "stats.activity.points": "Точек: {count}",
        "stats.activity.empty": "Нет данных активности для текущих фильтров.",
        "stats.activity.chartAria": "График активности",
        "stats.activity.dataset": "Действия",
        "stats.activity.tooltip": "Действий: {count}",
        "stats.activity.tooltipDelta": "Действий: {count} ({delta} к предыдущей точке)",
        "stats.leaderboard.title": "Рейтинг",
        "stats.leaderboard.caption": "Рейтинг с сортировкой и пагинацией",
        "stats.leaderboard.user": "Пользователь",
        "stats.leaderboard.actions": "Действия",
        "stats.leaderboard.lastActive": "Последняя активность",
        "stats.leaderboard.rows": "Строк",
        "stats.leaderboard.prev": "Назад",
        "stats.leaderboard.next": "Вперед",
        "stats.leaderboard.loading": "Загрузка...",
        "stats.leaderboard.noData": "Нет данных рейтинга для текущих фильтров.",
        "stats.leaderboard.noStatus": "Нет данных",
        "stats.leaderboard.loaded": "Загружено пользователей: {count}",
        "stats.leaderboard.results": "Результатов: {count}",
        "stats.leaderboard.showing": "Показано {start}-{end} из {total}",
        "stats.user.unknown": "Неизвестный пользователь",
        "stats.modules.eyebrow": "Модули расписания",
        "stats.modules.title": "Ручные правила модулей",
        "stats.modules.description": "Создание и поддержка правил «дисциплина -> модуль», которые используют фильтры расписания. Это тот же источник данных, что и `/set_module Discipline | Module`.",
        "stats.modules.form.title": "Создать или изменить",
        "stats.modules.form.new": "Новое правило",
        "stats.modules.form.editing": "Редактируется: {discipline}",
        "stats.modules.discipline": "Дисциплина",
        "stats.modules.module": "Модуль",
        "stats.modules.actions": "Действия",
        "stats.modules.search": "Поиск",
        "stats.modules.searchPlaceholder": "Дисциплина или модуль",
        "stats.modules.filter": "Фильтр по модулю",
        "stats.modules.all": "Все модули",
        "stats.modules.save": "Сохранить правило",
        "stats.modules.saveChanges": "Сохранить изменения",
        "stats.modules.openToLoad": "Откройте вкладку модулей, чтобы загрузить правила.",
        "stats.modules.status.notLoaded": "Не загружено",
        "stats.modules.status.loading": "Загружаю правила...",
        "stats.modules.status.loaded": "Загружено правил: {count}",
        "stats.modules.status.failed": "Не удалось загрузить правила",
        "stats.modules.status.saving": "Сохраняю правило...",
        "stats.modules.status.saved": "Правило сохранено",
        "stats.modules.status.saveFailed": "Не удалось сохранить",
        "stats.modules.empty": "Под текущие фильтры ручных правил нет.",
        "stats.modules.meta.adminOnly": "Правила загружаются только для админов.",
        "stats.modules.meta.partial": "Показано {shown} из {total}. Уточните поиск, чтобы найти старые строки.",
        "stats.modules.meta.loaded": "Загружено правил: {count}.",
        "stats.modules.edit": "Изменить",
        "stats.modules.delete": "Удалить",
        "stats.modules.confirmDelete": "Удалить правило для «{discipline}»?",
        "stats.modules.deleted": "Правило удалено",
        "stats.modules.failed": "Ошибка правил модулей: {message}",
        "stats.modules.deleteFailed": "Удаление не выполнено: {message}",
        "stats.modules.fillBoth": "Заполните дисциплину и модуль",
        "stats.modules.oldNotRemoved": "Новое правило сохранено, но старое имя дисциплины не удалилось.",
        "stats.modules.savedToast": "Сохранено: {discipline}",
        "stats.modules.saveFailedToast": "Сохранение не выполнено: {message}",
        "stats.mobileFilters.title": "Фильтры",
        "stats.mobileFilters.range": "Период",
        "stats.mobileFilters.sort": "Сортировка",
        "stats.mobileFilters.rowsPerPage": "Строк на странице",
        "stats.sort.actionsDesc": "Действия по убыванию",
        "stats.sort.actionsAsc": "Действия по возрастанию",
        "stats.sort.userAsc": "Пользователь А-Я",
        "stats.sort.userDesc": "Пользователь Я-А",
        "stats.sort.lastActiveDesc": "Недавние сначала",
        "stats.sort.lastActiveAsc": "Давние сначала",
        "stats.toast.retryRequested": "Повторный запрос отправлен",
        "stats.toast.activityReload": "Обновляю активность",
        "stats.toast.leaderboardReload": "Обновляю рейтинг",
        "stats.toast.liveConnected": "Live-статистика подключена",
        "stats.toast.liveIssue": "Проблема с live-данными. Переподключаюсь...",
        "stats.toast.liveLost": "Live-соединение потеряно. Переподключаюсь...",
        "stats.toast.pickDates": "Выберите обе даты",
        "stats.toast.dateOrder": "Дата начала должна быть раньше даты конца",
        "stats.dashboard.failed": "Не удалось загрузить дашборд: {message}",
        "stats.dashboard.loadFailed": "Ошибка загрузки дашборда: {message}",
        "stats.dashboard.loadingFailed": "Ошибка. Нужен повтор.",
        "stats.dashboard.partial": "Обнаружена частичная деградация. {message}",
        "stats.scheduleCache.done": "Обновление кеша расписаний завершено.",
        "stats.scheduleCache.summary": "Обновление кеша расписаний завершено: {parts}.",
        "stats.scheduleCache.refreshed": "обновлено: {count}",
        "stats.scheduleCache.remapped": "пересопоставлено id: {count}",
        "stats.scheduleCache.failed": "ошибок: {count}",
        "stats.scheduleCache.skipped": "пропущено: {count}",
        "stats.scheduleCache.error": "Ошибка обновления кеша расписаний: {message}",
        "stats.column.rank": "Место",
        "stats.column.full_name": "Пользователь",
        "stats.column.actions_count": "Действия",
        "stats.column.last_action_time": "Последняя активность",
    },
};

const RANGE_LABEL_KEYS = {
    today: "stats.range.today",
    "7d": "stats.range.last7",
    "30d": "stats.range.last30",
    custom: "stats.range.custom",
};

function interpolateText(template, params = {}) {
    return String(template || "").replace(/\{(\w+)\}/g, (_, key) => String(params[key] ?? ""));
}

function getStatsLanguage() {
    const source =
        window.mpbI18n?.getLanguage?.() ||
        localStorage.getItem("mpb_ui_lang") ||
        document.documentElement.lang ||
        "ru";
    return String(source).toLowerCase().startsWith("ru") ? "ru" : "en";
}

function getStatsLocale() {
    return getStatsLanguage() === "ru" ? "ru-RU" : "en-US";
}

function t(key, fallback = "", params = {}) {
    const fromNavbar = window.mpbI18n?.t?.(key, "", params);
    if (fromNavbar && fromNavbar !== key) return fromNavbar;
    const lang = getStatsLanguage();
    const template = STATS_I18N[lang]?.[key] || STATS_I18N.en[key] || fallback || key;
    return interpolateText(template, params);
}

function getRangeLabel(range) {
    return t(RANGE_LABEL_KEYS[range] || "stats.range.custom", "Custom");
}

function applyStatsTranslations() {
    document.documentElement.lang = getStatsLanguage();
    document.title = t("stats.meta.title", "Stats Dashboard | ITISHCHENKO");
    document.querySelectorAll("[data-stats-i18n]").forEach((element) => {
        const key = element.getAttribute("data-stats-i18n");
        if (!key) return;
        element.textContent = t(key, element.textContent || "");
    });
    document.querySelectorAll("[data-stats-placeholder]").forEach((element) => {
        const key = element.getAttribute("data-stats-placeholder");
        if (!key) return;
        element.setAttribute("placeholder", t(key, element.getAttribute("placeholder") || ""));
    });
    document.querySelectorAll("[data-stats-title]").forEach((element) => {
        const key = element.getAttribute("data-stats-title");
        if (!key) return;
        element.setAttribute("title", t(key, element.getAttribute("title") || ""));
    });
    document.querySelectorAll("[data-stats-aria-label]").forEach((element) => {
        const key = element.getAttribute("data-stats-aria-label");
        if (!key) return;
        element.setAttribute("aria-label", t(key, element.getAttribute("aria-label") || ""));
    });
}

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
    proxyDiagnostics: null,
    ws: null,
    wsConnected: false,
    wsBackoffMs: 1000,
    wsReconnects: 0,
    lastUpdated: "",
    lastSyncSource: "-",
    failedRequests: 0,
    lastError: "-",
    isScheduleCacheRefreshing: false,
    activeStatsView: window.location.hash === "#modules" ? "modules" : "dashboard",
    moduleMappings: [],
    moduleMappingModules: [],
    moduleMappingsTotal: 0,
    moduleMappingsLoaded: false,
    moduleMappingsLoading: false,
    moduleMappingsPendingReload: false,
    moduleMappingsStatusKey: "stats.modules.status.notLoaded",
    moduleMappingsStatusFallback: "Not loaded",
    moduleMappingsStatusParams: {},
    moduleMappingsStatusKind: "info",
    moduleMappingsQuery: "",
    moduleMappingsModule: "",
    moduleMappingEditingDiscipline: "",
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
    refreshScheduleCacheBtn: document.getElementById("refreshScheduleCacheBtn"),
    refreshScheduleCacheBtnMobile: document.getElementById("refreshScheduleCacheBtnMobile"),
    mobileActionDiagnostics: document.getElementById("mobileActionDiagnostics"),
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
    proxyDiagnosticsStatus: document.getElementById("proxyDiagnosticsStatus"),
    proxyDiagnosticsFetchedAt: document.getElementById("proxyDiagnosticsFetchedAt"),
    proxyTelegramSelected: document.getElementById("proxyTelegramSelected"),
    proxyOpenaiSelected: document.getElementById("proxyOpenaiSelected"),
    proxyBuildInventory: document.getElementById("proxyBuildInventory"),
    proxyDiagnosticsSource: document.getElementById("proxyDiagnosticsSource"),
    proxyDiagnosticsTableBody: document.getElementById("proxyDiagnosticsTableBody"),
    proxyDiagnosticsError: document.getElementById("proxyDiagnosticsError"),
    statsViewButtons: Array.from(document.querySelectorAll("[data-stats-view]")),
    statsDashboardSection: document.getElementById("statsDashboardSection"),
    modulesAdminSection: document.getElementById("modulesAdminSection"),
    moduleMappingsStatus: document.getElementById("moduleMappingsStatus"),
    moduleMappingsRefreshBtn: document.getElementById("moduleMappingsRefreshBtn"),
    moduleMappingForm: document.getElementById("moduleMappingForm"),
    moduleDisciplineInput: document.getElementById("moduleDisciplineInput"),
    moduleNameInput: document.getElementById("moduleNameInput"),
    moduleNameOptions: document.getElementById("moduleNameOptions"),
    moduleMappingFormMode: document.getElementById("moduleMappingFormMode"),
    moduleMappingSaveBtn: document.getElementById("moduleMappingSaveBtn"),
    moduleMappingResetBtn: document.getElementById("moduleMappingResetBtn"),
    moduleMappingSearchInput: document.getElementById("moduleMappingSearchInput"),
    moduleMappingFilterSelect: document.getElementById("moduleMappingFilterSelect"),
    moduleMappingsTableBody: document.getElementById("moduleMappingsTableBody"),
    moduleMappingsMeta: document.getElementById("moduleMappingsMeta"),
};

let moduleMappingsSearchTimer = 0;

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

    const hashView = window.location.hash.replace("#", "");
    if (["dashboard", "modules"].includes(hashView)) {
        state.activeStatsView = hashView;
    }
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
    const hash = state.activeStatsView === "modules" ? "#modules" : "";
    const nextUrl = `${window.location.pathname}${query ? `?${query}` : ""}${hash}`;
    window.history.replaceState({}, "", nextUrl);
}

function formatDateTime(value) {
    if (!value) return "-";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "-";
    return new Intl.DateTimeFormat(getStatsLocale(), { dateStyle: "medium", timeStyle: "short" }).format(date);
}

function formatLatency(ms) {
    if (typeof ms !== "number") return "-";
    return `${Math.round(ms)} ms`;
}

function isDarkTheme() {
    return document.documentElement.classList.contains("dark");
}

function getChartPalette() {
    if (isDarkTheme()) {
        return {
            line: "#60a5fa",
            fill: "rgba(96, 165, 250, 0.16)",
            grid: "rgba(148, 163, 184, 0.18)",
            tick: "#94a3b8",
            tooltipBg: "#0f172a",
            tooltipText: "#e2e8f0",
            tooltipBorder: "rgba(71, 85, 105, 0.8)",
        };
    }

    return {
        line: "#2563eb",
        fill: "rgba(37, 99, 235, 0.12)",
        grid: "rgba(148, 163, 184, 0.2)",
        tick: "#64748b",
        tooltipBg: "#ffffff",
        tooltipText: "#0f172a",
        tooltipBorder: "rgba(226, 232, 240, 0.95)",
    };
}

function escapeHtml(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
}

function formatProxySourceLabel(value) {
    if (!value) return "-";
    try {
        const url = new URL(value);
        return `${url.host}${url.pathname}`;
    } catch {
        return value;
    }
}

function normalizeProxyCandidate(candidate, selectedName) {
    if (!candidate || typeof candidate !== "object") {
        return null;
    }

    const name = String(candidate.name || "").trim();
    if (!name) return null;

    return {
        name,
        alive: typeof candidate.alive === "boolean" ? candidate.alive : null,
        delay: typeof candidate.delay === "number" ? candidate.delay : null,
        selected: Boolean(candidate.selected) || name === selectedName,
    };
}

function normalizeProxyGroup(group, fallbackGroup) {
    const selectedName = typeof group?.selected === "string" && group.selected.trim()
        ? group.selected.trim()
        : null;
    const topCandidates = Array.isArray(group?.top_candidates)
        ? group.top_candidates
            .map((candidate) => normalizeProxyCandidate(candidate, selectedName))
            .filter(Boolean)
        : [];

    return {
        group: typeof group?.group === "string" && group.group.trim() ? group.group.trim() : fallbackGroup,
        selected: selectedName,
        candidate_count: Number.isInteger(group?.candidate_count) ? group.candidate_count : topCandidates.length,
        top_candidates: topCandidates,
    };
}

function normalizeProxyDiagnostics(payload) {
    return {
        available: Boolean(payload?.available),
        source_url: typeof payload?.source_url === "string" ? payload.source_url : "",
        fetched_at: typeof payload?.fetched_at === "string" ? payload.fetched_at : "",
        error: typeof payload?.error === "string" ? payload.error : "",
        last_build: {
            merged_entries: typeof payload?.last_build?.merged_entries === "number" ? payload.last_build.merged_entries : null,
            outline_entries: typeof payload?.last_build?.outline_entries === "number" ? payload.last_build.outline_entries : null,
            subscription_entries: typeof payload?.last_build?.subscription_entries === "number" ? payload.last_build.subscription_entries : null,
        },
        telegram: normalizeProxyGroup(payload?.telegram, "TELEGRAM-AUTO"),
        openai: normalizeProxyGroup(payload?.openai, "OPENAI-AUTO"),
    };
}

function setProxyDiagnosticsStatus(message, kind = "info") {
    if (!elements.proxyDiagnosticsStatus) return;

    elements.proxyDiagnosticsStatus.classList.remove(
        "text-slate-500",
        "text-red-600",
        "text-emerald-600",
        "text-amber-600"
    );

    if (kind === "error") {
        elements.proxyDiagnosticsStatus.classList.add("text-red-600");
    } else if (kind === "ok") {
        elements.proxyDiagnosticsStatus.classList.add("text-emerald-600");
    } else if (kind === "warning") {
        elements.proxyDiagnosticsStatus.classList.add("text-amber-600");
    } else {
        elements.proxyDiagnosticsStatus.classList.add("text-slate-500");
    }

    elements.proxyDiagnosticsStatus.textContent = message;
}

function renderProxyDiagnostics() {
    const payload = state.proxyDiagnostics;

    if (!payload) {
        setProxyDiagnosticsStatus(t("stats.proxy.notRequested", "Proxy summary has not been requested yet."), "info");
        return;
    }

    if (elements.proxyDiagnosticsFetchedAt) {
        elements.proxyDiagnosticsFetchedAt.textContent = payload.fetched_at
            ? formatDateTime(payload.fetched_at)
            : "-";
    }
    if (elements.proxyTelegramSelected) {
        elements.proxyTelegramSelected.textContent = payload.telegram.selected || t("stats.proxy.noActiveNode", "No active node");
    }
    if (elements.proxyOpenaiSelected) {
        elements.proxyOpenaiSelected.textContent = payload.openai.selected || t("stats.proxy.noActiveNode", "No active node");
    }
    if (elements.proxyBuildInventory) {
        const merged = payload.last_build.merged_entries ?? "-";
        const outline = payload.last_build.outline_entries ?? "-";
        const subscription = payload.last_build.subscription_entries ?? "-";
        elements.proxyBuildInventory.textContent = `${merged} merged / ${outline} outline / ${subscription} subscription`;
    }
    if (elements.proxyDiagnosticsSource) {
        elements.proxyDiagnosticsSource.textContent = formatProxySourceLabel(payload.source_url);
    }

    if (elements.proxyDiagnosticsError) {
        const errorMessage = payload.error || "";
        elements.proxyDiagnosticsError.textContent = errorMessage;
        elements.proxyDiagnosticsError.classList.toggle("hidden", !errorMessage);
    }

    const rows = [
        ...(payload.telegram.top_candidates || []).map((candidate) => ({ route: t("stats.proxy.route.telegram", "Telegram"), ...candidate })),
        ...(payload.openai.top_candidates || []).map((candidate) => ({ route: t("stats.proxy.route.openai", "OpenAI"), ...candidate })),
    ];

    if (elements.proxyDiagnosticsTableBody) {
        if (rows.length === 0) {
            elements.proxyDiagnosticsTableBody.innerHTML = `
                <tr>
                    <td colspan="5" class="px-4 py-4 text-sm text-slate-500">
                        ${payload.available
                            ? t("stats.proxy.availableNoCandidates", "Proxy summary is available, but there are no ranked candidates yet.")
                            : t("stats.proxy.unavailable", "Proxy summary unavailable")}
                    </td>
                </tr>
            `;
        } else {
            elements.proxyDiagnosticsTableBody.innerHTML = rows
                .map((row) => {
                    const delayLabel = row.delay === null ? "-" : `${Math.round(row.delay)} ms`;
                    const aliveLabel = row.alive === true
                        ? t("stats.proxy.yes", "Yes")
                        : row.alive === false
                            ? t("stats.proxy.no", "No")
                            : t("stats.proxy.unknown", "Unknown");
                    const aliveClass = row.alive === true
                        ? "text-emerald-700"
                        : row.alive === false
                            ? "text-red-700"
                            : "text-slate-500";
                    const selectedLabel = row.selected ? t("stats.proxy.current", "Current") : "-";
                    const rowClass = row.selected ? "bg-blue-50/60" : "";

                    return `
                        <tr class="border-b border-slate-100 last:border-b-0 ${rowClass}">
                            <td class="px-4 py-3 font-medium text-slate-700">${escapeHtml(row.route)}</td>
                            <td class="px-4 py-3 text-slate-800">${escapeHtml(row.name)}</td>
                            <td class="px-4 py-3 text-slate-600">${escapeHtml(delayLabel)}</td>
                            <td class="px-4 py-3 ${aliveClass}">${escapeHtml(aliveLabel)}</td>
                            <td class="px-4 py-3 ${row.selected ? "font-semibold text-blue-700" : "text-slate-500"}">${escapeHtml(selectedLabel)}</td>
                        </tr>
                    `;
                })
                .join("");
        }
    }

    if (!payload.available) {
        setProxyDiagnosticsStatus(t("stats.proxy.unavailable", "Proxy summary unavailable"), payload.error ? "warning" : "info");
        return;
    }

    const routeCount = rows.length;
    const sourceLabel = formatProxySourceLabel(payload.source_url);
    setProxyDiagnosticsStatus(
        t("stats.proxy.rowsLoaded", "{count} proxy candidate rows loaded from {source}.", {
            count: routeCount,
            source: sourceLabel,
        }),
        "ok"
    );
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
            setConnectionState("online", t("stats.connection.connected", "Live updates"));
        } else {
            setConnectionState("warning", t("stats.connection.rest", "REST mode"));
        }
        return;
    }

    const labels = failedWidgets.map((widget) => (
        widget === "leaderboard"
            ? t("stats.leaderboard.title", "Leaderboard")
            : t("stats.activity.title", "Activity")
    ));
    const healthyCount = Object.keys(state.widgetHealth).length - failedWidgets.length;
    const message = healthyCount > 0
        ? `Partial degradation: failed widget(s): ${labels.join(", ")}. Showing available data for the rest.`
        : `Dashboard degraded: all widgets failed (${labels.join(", ")}).`;
    showPartialDegradation(message);
    setConnectionState("warning", t("stats.connection.partial", "Partial degradation"));
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
        full_name: (user.full_name || t("stats.user.unknown", "Unknown user")).trim(),
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

function normalizePlainText(value) {
    return String(value ?? "").replace(/\s+/g, " ").trim();
}

function normalizeModuleMapping(item) {
    return {
        discipline_name: normalizePlainText(item?.discipline_name),
        module_name: normalizePlainText(item?.module_name),
    };
}

function setModuleMappingsStatus(message, kind = "info") {
    state.moduleMappingsStatusKey = "";
    state.moduleMappingsStatusFallback = message;
    state.moduleMappingsStatusParams = {};
    state.moduleMappingsStatusKind = kind;
    setBlockStatus(elements.moduleMappingsStatus, message, kind);
}

function setModuleMappingsStatusText(key, fallback, params = {}, kind = "info") {
    state.moduleMappingsStatusKey = key;
    state.moduleMappingsStatusFallback = fallback;
    state.moduleMappingsStatusParams = params;
    state.moduleMappingsStatusKind = kind;
    setBlockStatus(elements.moduleMappingsStatus, t(key, fallback, params), kind);
}

function refreshModuleMappingsStatus() {
    if (state.moduleMappingsStatusKey) {
        setBlockStatus(
            elements.moduleMappingsStatus,
            t(
                state.moduleMappingsStatusKey,
                state.moduleMappingsStatusFallback,
                state.moduleMappingsStatusParams
            ),
            state.moduleMappingsStatusKind
        );
        return;
    }
    setBlockStatus(elements.moduleMappingsStatus, state.moduleMappingsStatusFallback, state.moduleMappingsStatusKind);
}

function setModuleMappingsLoading(isLoading) {
    state.moduleMappingsLoading = isLoading;

    if (elements.moduleMappingsRefreshBtn) {
        elements.moduleMappingsRefreshBtn.disabled = isLoading;
        elements.moduleMappingsRefreshBtn.textContent = isLoading
            ? t("stats.refreshing", "Refreshing...")
            : t("stats.refresh", "Refresh");
    }
    if (elements.moduleMappingSaveBtn) {
        elements.moduleMappingSaveBtn.disabled = isLoading;
    }
}

function renderModuleMappingFilters() {
    const modules = [...state.moduleMappingModules].sort((a, b) => a.localeCompare(b));

    if (elements.moduleNameOptions) {
        elements.moduleNameOptions.innerHTML = modules
            .map((moduleName) => `<option value="${escapeHtml(moduleName)}"></option>`)
            .join("");
    }

    if (!elements.moduleMappingFilterSelect) return;

    const previousValue = state.moduleMappingsModule;
    elements.moduleMappingFilterSelect.innerHTML = `
        <option value="">${escapeHtml(t("stats.modules.all", "All modules"))}</option>
        ${modules
            .map((moduleName) => `<option value="${escapeHtml(moduleName)}">${escapeHtml(moduleName)}</option>`)
            .join("")}
    `;
    elements.moduleMappingFilterSelect.value = previousValue;
}

function renderModuleMappings() {
    renderModuleMappingFilters();

    if (elements.moduleMappingSearchInput && elements.moduleMappingSearchInput.value !== state.moduleMappingsQuery) {
        elements.moduleMappingSearchInput.value = state.moduleMappingsQuery;
    }
    if (elements.moduleMappingFilterSelect && elements.moduleMappingFilterSelect.value !== state.moduleMappingsModule) {
        elements.moduleMappingFilterSelect.value = state.moduleMappingsModule;
    }

    if (elements.moduleMappingsTableBody) {
        if (state.moduleMappingsLoading && !state.moduleMappingsLoaded) {
            elements.moduleMappingsTableBody.innerHTML = Array.from({ length: 4 }, () => `
                <tr>
                    <td colspan="3" class="px-4 py-4"><div class="h-4 w-full skeleton rounded"></div></td>
                </tr>
            `).join("");
        } else if (state.moduleMappings.length === 0) {
            const message = state.moduleMappingsLoaded
                ? t("stats.modules.empty", "No manual mappings match current filters.")
                : t("stats.modules.openToLoad", "Open the Modules tab to load mappings.");
            elements.moduleMappingsTableBody.innerHTML = `
                <tr>
                    <td colspan="3" class="px-4 py-5 text-sm text-slate-500">${message}</td>
                </tr>
            `;
        } else {
            elements.moduleMappingsTableBody.innerHTML = state.moduleMappings
                .map((mapping, index) => `
                    <tr class="border-b border-slate-100 align-top last:border-b-0 hover:bg-slate-50">
                        <td class="px-4 py-3">
                            <div class="max-w-2xl font-semibold leading-5 text-slate-900">${escapeHtml(mapping.discipline_name)}</div>
                        </td>
                        <td class="px-4 py-3">
                            <span class="inline-flex max-w-xs items-center rounded-full border border-blue-200 bg-blue-50 px-2.5 py-1 text-xs font-bold text-blue-700">
                                ${escapeHtml(mapping.module_name)}
                            </span>
                        </td>
                        <td class="px-4 py-3">
                            <div class="flex justify-end gap-2">
                                <button type="button" data-module-action="edit" data-index="${index}" class="focus-ring rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-xs font-bold text-slate-700 hover:bg-slate-100">${escapeHtml(t("stats.modules.edit", "Edit"))}</button>
                                <button type="button" data-module-action="delete" data-index="${index}" class="focus-ring rounded-lg border border-red-200 bg-red-50 px-2.5 py-1.5 text-xs font-bold text-red-700 hover:bg-red-100">${escapeHtml(t("stats.modules.delete", "Delete"))}</button>
                            </div>
                        </td>
                    </tr>
                `)
                .join("");
        }
    }

    if (elements.moduleMappingsMeta) {
        const loadedCount = state.moduleMappings.length;
        if (!state.moduleMappingsLoaded) {
            elements.moduleMappingsMeta.textContent = t("stats.modules.meta.adminOnly", "Mappings are loaded only for admins.");
        } else if (loadedCount < state.moduleMappingsTotal) {
            elements.moduleMappingsMeta.textContent = t(
                "stats.modules.meta.partial",
                "Showing {shown} of {total} matching mappings. Narrow the search to find older rows.",
                { shown: loadedCount, total: state.moduleMappingsTotal }
            );
        } else {
            elements.moduleMappingsMeta.textContent = t("stats.modules.meta.loaded", "{count} mappings loaded.", {
                count: loadedCount,
            });
        }
    }
}

async function loadModuleMappings({ silent = false } = {}) {
    if (state.moduleMappingsLoading) {
        state.moduleMappingsPendingReload = true;
        return;
    }

    const searchValue = elements.moduleMappingSearchInput
        ? elements.moduleMappingSearchInput.value
        : state.moduleMappingsQuery;
    const moduleFilterValue = elements.moduleMappingFilterSelect
        ? elements.moduleMappingFilterSelect.value
        : state.moduleMappingsModule;
    state.moduleMappingsQuery = normalizePlainText(searchValue);
    state.moduleMappingsModule = normalizePlainText(moduleFilterValue);

    if (!silent) {
        setModuleMappingsStatusText("stats.modules.status.loading", "Loading mappings...", {}, "info");
    }
    setModuleMappingsLoading(true);
    renderModuleMappings();

    const params = new URLSearchParams({ limit: "1000" });
    if (state.moduleMappingsQuery) params.set("query", state.moduleMappingsQuery);
    if (state.moduleMappingsModule) params.set("module_name", state.moduleMappingsModule);

    try {
        const payload = await fetchWithAuth(`/stats/modules?${params.toString()}`);
        state.moduleMappings = Array.isArray(payload?.items)
            ? payload.items.map(normalizeModuleMapping).filter((mapping) => mapping.discipline_name && mapping.module_name)
            : [];
        state.moduleMappingModules = Array.isArray(payload?.modules)
            ? payload.modules.map(normalizePlainText).filter(Boolean)
            : [];
        state.moduleMappingsTotal = Number(payload?.total) || state.moduleMappings.length;
        state.moduleMappingsLoaded = true;
        setModuleMappingsStatusText(
            "stats.modules.status.loaded",
            "Loaded {count} mappings",
            { count: state.moduleMappingsTotal },
            "ok"
        );
    } catch (error) {
        const message = error instanceof Error ? error.message : "Module mappings request failed";
        registerBackgroundFailure(message);
        state.moduleMappingsLoaded = true;
        setModuleMappingsStatusText("stats.modules.status.failed", "Failed to load mappings", {}, "error");
        showToast("error", t("stats.modules.failed", "Module mappings failed: {message}", { message }));
    } finally {
        setModuleMappingsLoading(false);
        renderModuleMappings();
        if (state.moduleMappingsPendingReload) {
            state.moduleMappingsPendingReload = false;
            void loadModuleMappings({ silent: true });
        }
    }
}

function queueModuleMappingsReload() {
    window.clearTimeout(moduleMappingsSearchTimer);
    moduleMappingsSearchTimer = window.setTimeout(() => {
        void loadModuleMappings({ silent: true });
    }, 180);
}

function setStatsView(view, { updateUrl = true, load = true } = {}) {
    const nextView = view === "modules" ? "modules" : "dashboard";
    state.activeStatsView = nextView;

    elements.statsDashboardSection?.classList.toggle("hidden", nextView !== "dashboard");
    elements.modulesAdminSection?.classList.toggle("hidden", nextView !== "modules");

    elements.statsViewButtons.forEach((button) => {
        const selected = button.dataset.statsView === nextView;
        button.setAttribute("aria-selected", selected ? "true" : "false");
        button.className = selected
            ? "focus-ring rounded-xl border border-slate-900 bg-slate-900 px-3 py-2 text-sm font-bold text-white"
            : "focus-ring rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm font-bold text-slate-700 hover:bg-slate-100";
    });

    if (updateUrl) {
        syncStateToUrl();
    }

    if (nextView === "modules" && load && !state.moduleMappingsLoaded) {
        void loadModuleMappings({ silent: false });
    }
}

function resetModuleMappingForm() {
    state.moduleMappingEditingDiscipline = "";
    if (elements.moduleDisciplineInput) elements.moduleDisciplineInput.value = "";
    if (elements.moduleNameInput) elements.moduleNameInput.value = "";
    if (elements.moduleMappingFormMode) {
        elements.moduleMappingFormMode.textContent = t("stats.modules.form.new", "New mapping");
    }
    if (elements.moduleMappingSaveBtn) {
        elements.moduleMappingSaveBtn.textContent = t("stats.modules.save", "Save mapping");
    }
}

function editModuleMapping(index) {
    const mapping = state.moduleMappings[index];
    if (!mapping) return;

    state.moduleMappingEditingDiscipline = mapping.discipline_name;
    if (elements.moduleDisciplineInput) {
        elements.moduleDisciplineInput.value = mapping.discipline_name;
        elements.moduleDisciplineInput.focus();
    }
    if (elements.moduleNameInput) {
        elements.moduleNameInput.value = mapping.module_name;
    }
    if (elements.moduleMappingFormMode) {
        elements.moduleMappingFormMode.textContent = t("stats.modules.form.editing", "Editing: {discipline}", {
            discipline: mapping.discipline_name,
        });
    }
    if (elements.moduleMappingSaveBtn) {
        elements.moduleMappingSaveBtn.textContent = t("stats.modules.saveChanges", "Save changes");
    }
}

async function deleteModuleMappingByDiscipline(
    disciplineName,
    { confirmDelete = true, reload = true, notify = true } = {}
) {
    const discipline = normalizePlainText(disciplineName);
    if (!discipline) return false;
    if (confirmDelete && !window.confirm(t("stats.modules.confirmDelete", "Delete mapping for \"{discipline}\"?", {
        discipline,
    }))) {
        return false;
    }

    try {
        await fetchWithAuth(`/stats/modules?discipline_name=${encodeURIComponent(discipline)}`, {
            method: "DELETE",
        });
        if (notify) {
            showToast("success", t("stats.modules.deleted", "Mapping deleted"));
        }
        if (state.moduleMappingEditingDiscipline === discipline) {
            resetModuleMappingForm();
        }
        if (reload) {
            await loadModuleMappings({ silent: true });
        }
        return true;
    } catch (error) {
        const message = error instanceof Error ? error.message : "Delete failed";
        registerBackgroundFailure(message);
        showToast("error", t("stats.modules.deleteFailed", "Delete failed: {message}", { message }));
        return false;
    }
}

async function saveModuleMapping(event) {
    event.preventDefault();

    const disciplineName = normalizePlainText(elements.moduleDisciplineInput?.value);
    const moduleName = normalizePlainText(elements.moduleNameInput?.value);
    if (!disciplineName || !moduleName) {
        showToast("warning", t("stats.modules.fillBoth", "Fill both discipline and module"));
        return;
    }

    const previousDiscipline = state.moduleMappingEditingDiscipline;
    setModuleMappingsLoading(true);
    setModuleMappingsStatusText("stats.modules.status.saving", "Saving mapping...", {}, "info");

    try {
        const saved = await fetchWithAuth("/stats/modules", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                discipline_name: disciplineName,
                module_name: moduleName,
            }),
        });

        if (previousDiscipline && previousDiscipline !== disciplineName) {
            const deletedPrevious = await deleteModuleMappingByDiscipline(previousDiscipline, {
                confirmDelete: false,
                reload: false,
                notify: false,
            });
            if (!deletedPrevious) {
                showToast("warning", t("stats.modules.oldNotRemoved", "Saved new mapping, but old discipline name was not removed."));
            }
        }

        resetModuleMappingForm();
        setModuleMappingsLoading(false);
        await loadModuleMappings({ silent: true });
        const savedMapping = normalizeModuleMapping(saved);
        showToast("success", t("stats.modules.savedToast", "Saved: {discipline}", {
            discipline: savedMapping.discipline_name || disciplineName,
        }));
        setModuleMappingsStatusText("stats.modules.status.saved", "Mapping saved", {}, "ok");
    } catch (error) {
        const message = error instanceof Error ? error.message : "Save failed";
        registerBackgroundFailure(message);
        setModuleMappingsStatusText("stats.modules.status.saveFailed", "Save failed", {}, "error");
        showToast("error", t("stats.modules.saveFailedToast", "Save failed: {message}", { message }));
    } finally {
        setModuleMappingsLoading(false);
        renderModuleMappings();
    }
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
                <td colspan="4" class="px-4 py-6 text-sm text-slate-500">${escapeHtml(t("stats.leaderboard.noData", "No leaderboard data for current filters."))}</td>
            </tr>
        `;
        setBlockStatus(elements.leaderboardStatus, t("stats.leaderboard.noStatus", "No data"), "warning");
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

        setBlockStatus(elements.leaderboardStatus, t("stats.leaderboard.loaded", "Loaded {count} users", {
            count: pageData.totalRows,
        }), "ok");
    }

    if (elements.leaderboardMeta) {
        elements.leaderboardMeta.textContent =
            pageData.totalRows === 0
                ? t("stats.leaderboard.results", "{count} results", { count: 0 })
                : t("stats.leaderboard.showing", "Showing {start}-{end} of {total}", {
                    start: pageData.startIndex,
                    end: pageData.endIndex,
                    total: pageData.totalRows,
                });
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
        setBlockStatus(elements.activityStatus, t("stats.activity.noData", "No activity in selected range"), "warning");
    } else {
        setBlockStatus(elements.activityStatus, t("stats.activity.points", "Points: {count}", {
            count: filtered.length,
        }), "ok");
    }

    const labels = filtered.map((entry) => entry.period);
    const values = filtered.map((entry) => entry.count);

    if (state.chart) {
        state.chart.destroy();
    }

    const chartPalette = getChartPalette();

    state.chart = new Chart(elements.activityCanvas.getContext("2d"), {
        type: "line",
        data: {
            labels,
            datasets: [
                {
                    label: t("stats.activity.dataset", "Actions"),
                    data: values,
                    borderColor: chartPalette.line,
                    backgroundColor: chartPalette.fill,
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
                    backgroundColor: chartPalette.tooltipBg,
                    titleColor: chartPalette.tooltipText,
                    bodyColor: chartPalette.tooltipText,
                    borderColor: chartPalette.tooltipBorder,
                    borderWidth: 1,
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
                        color: chartPalette.grid,
                    },
                    ticks: {
                        color: chartPalette.tick,
                    },
                },
                x: {
                    grid: {
                        display: false,
                    },
                    ticks: {
                        color: chartPalette.tick,
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
        elements.totalActions.textContent = total.toLocaleString(getStatsLocale());
    }

    if (elements.visibleUsers) {
        elements.visibleUsers.textContent = String(state.leaderboard.length);
    }

    if (elements.currentRangeLabel) {
        elements.currentRangeLabel.textContent = getRangeLabel(state.range);
    }
}

function renderAll() {
    renderKpis();
    renderLeaderboard();
    renderActivityChart();
    updateDiagnostics();
    renderProxyDiagnostics();
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

async function fetchWithAuth(endpoint, options = {}) {
    const startTime = performance.now();
    const headers = {
        ...(options.headers || {}),
        Authorization: `Bearer ${token}`,
    };

    const response = await fetch(`${API_BASE}${endpoint}`, {
        ...options,
        headers,
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

function setScheduleCacheRefreshVisible(isVisible) {
    [elements.refreshScheduleCacheBtn, elements.refreshScheduleCacheBtnMobile].forEach((button) => {
        button?.classList.toggle("hidden", !isVisible);
    });
}

function setScheduleCacheRefreshLoading(isLoading) {
    state.isScheduleCacheRefreshing = isLoading;
    [elements.refreshScheduleCacheBtn, elements.refreshScheduleCacheBtnMobile].forEach((button) => {
        if (!button) return;
        button.disabled = isLoading;
        button.textContent = isLoading
            ? t("stats.refreshing", "Refreshing...")
            : button.id === "refreshScheduleCacheBtnMobile"
                ? t("stats.refreshScheduleCache.mobile", "Schedule cache")
                : t("stats.refreshScheduleCache", "Refresh schedule cache");
    });
}

function formatScheduleCacheRefreshSummary(payload) {
    if (!payload || typeof payload !== "object") return t("stats.scheduleCache.done", "Schedule cache refresh finished.");
    const parts = [
        t("stats.scheduleCache.refreshed", "{count} refreshed", { count: Number(payload.refreshed) || 0 }),
        t("stats.scheduleCache.remapped", "{count} ids remapped", { count: Number(payload.remapped) || 0 }),
    ];
    const failed = Number(payload.failed) || 0;
    const skipped = Number(payload.skipped) || 0;
    if (failed > 0) parts.push(t("stats.scheduleCache.failed", "{count} failed", { count: failed }));
    if (skipped > 0) parts.push(t("stats.scheduleCache.skipped", "{count} skipped", { count: skipped }));
    return t("stats.scheduleCache.summary", "Schedule cache refresh finished: {parts}.", {
        parts: parts.join(", "),
    });
}

async function refreshAllScheduleSemesterCache() {
    if (state.isScheduleCacheRefreshing) return;
    setScheduleCacheRefreshLoading(true);
    try {
        const payload = await fetchWithAuth("/schedule/cache/refresh_all_semester", {
            method: "POST",
        });
        const hasFailures = (Number(payload?.failed) || 0) > 0;
        showToast(hasFailures ? "warning" : "success", formatScheduleCacheRefreshSummary(payload));
    } catch (error) {
        const message = error instanceof Error ? error.message : "Schedule cache refresh failed";
        registerBackgroundFailure(message);
        showToast("error", t("stats.scheduleCache.error", "Schedule cache refresh failed: {message}", { message }));
    } finally {
        setScheduleCacheRefreshLoading(false);
    }
}

function registerBackgroundFailure(errorMessage) {
    state.failedRequests += 1;
    state.lastError = errorMessage;
    updateDiagnostics();
}

async function refreshProxyDiagnostics({ silent = false } = {}) {
    if (!silent) {
        setProxyDiagnosticsStatus(t("stats.proxy.loading", "Loading proxy summary..."), "info");
    }

    try {
        const payload = await fetchWithAuth("/stats/proxy_diagnostics");
        state.proxyDiagnostics = normalizeProxyDiagnostics(payload);
    } catch (error) {
        const message = error instanceof Error ? error.message : "Proxy diagnostics request failed";
        registerBackgroundFailure(message);
        state.proxyDiagnostics = normalizeProxyDiagnostics({
            available: false,
            error: message,
        });
    }

    renderProxyDiagnostics();
}

function registerFailure(errorMessage) {
    state.failedRequests += 1;
    state.lastError = errorMessage;
    updateDiagnostics();
}

async function refreshFromRest({ silent = false } = {}) {
    void refreshProxyDiagnostics({ silent });

    if (!silent) {
        setLoading(true);
        setBlockStatus(elements.leaderboardStatus, t("stats.leaderboard.loading", "Loading..."), "info");
        setBlockStatus(elements.activityStatus, t("stats.activity.loading", "Loading..."), "info");
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
        failureMessages.push(`${t("stats.leaderboard.title", "Leaderboard")}: ${message}`);
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
        failureMessages.push(`${t("stats.activity.title", "Activity")}: ${message}`);
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
            showToast("warning", t("stats.dashboard.partial", "Partial degradation detected. {message}", {
                message: failureMessages.join(" | "),
            }));
        }
    } else {
        const combinedError = failureMessages.join(" | ") || "Unknown REST error";
        showGlobalError(t("stats.dashboard.failed", "Failed to load dashboard: {message}", {
            message: combinedError,
        }));
        setRetryButtonsVisible(true);
        setBlockStatus(elements.leaderboardStatus, t("stats.dashboard.loadingFailed", "Failed. Retry required."), "error");
        setBlockStatus(elements.activityStatus, t("stats.dashboard.loadingFailed", "Failed. Retry required."), "error");
        showToast("error", t("stats.dashboard.loadFailed", "Dashboard load failed: {message}", {
            message: combinedError,
        }));
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

    setConnectionState("connecting", t("stats.connection.connecting", "Connecting..."));

    const socket = new WebSocket(wsUrl);
    state.ws = socket;

    socket.addEventListener("open", () => {
        state.wsConnected = true;
        state.wsBackoffMs = 1000;
        updateDashboardHealthState();
        if (state.activeStatsView === "dashboard") {
            showToast("success", t("stats.toast.liveConnected", "Live stats connected"));
        }
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
            showGlobalError(t("stats.dashboard.failed", "Live data error: {message}", { message }));
            setRetryButtonsVisible(true);
            setConnectionState("warning", t("stats.connection.warning", "Connection error"));
            if (state.activeStatsView === "dashboard") {
                showToast("warning", t("stats.toast.liveIssue", "Live data issue. Retrying..."));
            }
        }
    });

    socket.addEventListener("close", () => {
        if (state.ws !== socket) return;

        state.wsConnected = false;
        setConnectionState("offline", t("stats.connection.disconnected", "Disconnected"));
        setRetryButtonsVisible(true);
        if (state.activeStatsView === "dashboard") {
            showToast("warning", t("stats.toast.liveLost", "Live connection lost. Reconnecting..."));
        }
        scheduleWsReconnect();
    });

    socket.addEventListener("error", () => {
        setConnectionState("warning", t("stats.connection.warning", "Connection error"));
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
        showToast("warning", t("stats.toast.pickDates", "Pick both custom dates"));
        return;
    }

    if (new Date(from) > new Date(to)) {
        showToast("warning", t("stats.toast.dateOrder", "From date must be earlier than To date"));
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

function refreshModuleMappingFormLabels() {
    if (elements.moduleMappingFormMode) {
        elements.moduleMappingFormMode.textContent = state.moduleMappingEditingDiscipline
            ? t("stats.modules.form.editing", "Editing: {discipline}", {
                discipline: state.moduleMappingEditingDiscipline,
            })
            : t("stats.modules.form.new", "New mapping");
    }
    if (elements.moduleMappingSaveBtn) {
        elements.moduleMappingSaveBtn.textContent = state.moduleMappingEditingDiscipline
            ? t("stats.modules.saveChanges", "Save changes")
            : t("stats.modules.save", "Save mapping");
    }
}

function refreshStatsLanguage() {
    applyStatsTranslations();
    setScheduleCacheRefreshLoading(state.isScheduleCacheRefreshing);
    refreshModuleMappingFormLabels();
    refreshModuleMappingsStatus();
    updateRangeControls();
    renderKpis();
    renderModuleMappings();
    renderProxyDiagnostics();
    if (state.leaderboard.length > 0 || state.widgetHealth.leaderboard !== "idle") {
        renderLeaderboard();
    }
    if (state.activity.length > 0 || state.widgetHealth.activity !== "idle") {
        renderActivityChart();
    }
    updateDiagnostics();
}

function registerStatsTranslations() {
    applyStatsTranslations();
    if (window.mpbI18n?.registerTranslator) {
        window.mpbI18n.registerTranslator(() => refreshStatsLanguage());
    } else {
        window.addEventListener("mpb-language-change", refreshStatsLanguage);
    }
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
        showToast("info", t("stats.toast.retryRequested", "Retry requested"));
    });

    elements.retryAllBtnMobile?.addEventListener("click", async () => {
        await refreshFromRest({ silent: false });
        showToast("info", t("stats.toast.retryRequested", "Retry requested"));
    });

    elements.refreshScheduleCacheBtn?.addEventListener("click", refreshAllScheduleSemesterCache);
    elements.refreshScheduleCacheBtnMobile?.addEventListener("click", refreshAllScheduleSemesterCache);

    elements.retryActivityBtn?.addEventListener("click", async () => {
        await refreshFromRest({ silent: false });
        showToast("info", t("stats.toast.activityReload", "Activity reload requested"));
    });

    elements.retryLeaderboardBtn?.addEventListener("click", async () => {
        await refreshFromRest({ silent: false });
        showToast("info", t("stats.toast.leaderboardReload", "Leaderboard reload requested"));
    });

    elements.dismissGlobalError?.addEventListener("click", hideGlobalError);
    elements.dismissPartialDegradation?.addEventListener("click", hidePartialDegradation);

    elements.toggleDiagnosticsBtn?.addEventListener("click", () => {
        elements.diagnosticsPanel?.classList.toggle("hidden");
    });

    elements.mobileActionDiagnostics?.addEventListener("click", () => {
        elements.diagnosticsPanel?.classList.toggle("hidden");
    });

    elements.statsViewButtons.forEach((button) => {
        button.addEventListener("click", () => {
            setStatsView(button.dataset.statsView);
        });
    });

    elements.moduleMappingsRefreshBtn?.addEventListener("click", () => {
        void loadModuleMappings({ silent: false });
    });

    elements.moduleMappingForm?.addEventListener("submit", saveModuleMapping);
    elements.moduleMappingResetBtn?.addEventListener("click", resetModuleMappingForm);

    elements.moduleMappingSearchInput?.addEventListener("input", (event) => {
        state.moduleMappingsQuery = event.target.value;
        queueModuleMappingsReload();
    });

    elements.moduleMappingFilterSelect?.addEventListener("change", (event) => {
        state.moduleMappingsModule = event.target.value;
        void loadModuleMappings({ silent: true });
    });

    elements.moduleMappingsTableBody?.addEventListener("click", (event) => {
        const target = event.target instanceof HTMLElement
            ? event.target.closest("[data-module-action]")
            : null;
        if (!(target instanceof HTMLElement)) return;

        const index = Number(target.getAttribute("data-index"));
        if (!Number.isInteger(index)) return;
        const action = target.getAttribute("data-module-action");
        if (action === "edit") {
            editModuleMapping(index);
        } else if (action === "delete") {
            const mapping = state.moduleMappings[index];
            if (mapping) {
                void deleteModuleMappingByDiscipline(mapping.discipline_name);
            }
        }
    });

    window.addEventListener("hashchange", () => {
        const hashView = window.location.hash.replace("#", "");
        setStatsView(hashView === "modules" ? "modules" : "dashboard", { updateUrl: false });
    });

    window.addEventListener("mpb-auth-ready", (event) => {
        setScheduleCacheRefreshVisible(event.detail?.user?.role === "admin");
    });

    window.addEventListener("mpb-theme-change", () => {
        renderActivityChart();
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
    registerStatsTranslations();
    wireEvents();
    setStatsView(state.activeStatsView, { updateUrl: false });

    setLoading(true);
    setConnectionState("connecting", t("stats.connection.connecting", "Connecting..."));
    setBlockStatus(elements.activityStatus, t("stats.activity.loading", "Loading..."), "info");
    setBlockStatus(elements.leaderboardStatus, t("stats.leaderboard.loading", "Loading..."), "info");
    renderProxyDiagnostics();

    await refreshFromRest({ silent: false });
    connectWebSocket();

    window.setInterval(() => {
        if (state.wsConnected) {
            void refreshProxyDiagnostics({ silent: true });
            return;
        }
        refreshFromRest({ silent: true });
    }, 60000);
});
