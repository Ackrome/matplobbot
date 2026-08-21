(function scheduleUxEnhancements() {
    if (typeof loadSchedule === "undefined" || typeof filterAndRender === "undefined") return;
    const UI_PREFS_KEY = "mpb_schedule_ui_prefs";
    function getDefaultUiViewMode() {
        return window.innerWidth >= 1024 ? "table" : "cards";
    }
    const uiState = {
        viewMode: getDefaultUiViewMode(),
        filtersCollapsed: true,
    };
    const SCHEDULE_UI_VIEW_MODES = ["cards", "compact", "table", "exams", "auto"];
    let isRenderingForViewMode = false;
    let tableResizeFrame = null;
    function normalizeUiViewMode(mode) {
        if (mode === "auto") return getDefaultUiViewMode();
        return SCHEDULE_UI_VIEW_MODES.includes(mode) ? mode : getDefaultUiViewMode();
    }
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
            uiState.viewMode = typeof payload.view_mode === "string"
                ? normalizeUiViewMode(payload.view_mode)
                : getDefaultUiViewMode();
            if (typeof payload.filters_collapsed === "boolean") {
                uiState.filtersCollapsed = payload.filters_collapsed;
            } else {
                uiState.filtersCollapsed = true;
            }
            if (payload.week_start) {
                const parsed = parseDate(payload.week_start);
                if (!Number.isNaN(parsed.getTime())) {
                    currentWeekStart = getMonday(parsed);
                }
            }
        } catch {
            uiState.viewMode = getDefaultUiViewMode();
            uiState.filtersCollapsed = true;
        }
        syncUiStateFromPageState();
    }
    function syncUiStateFromPageState() {
        const state = window.getSchedulePageState?.();
        if (!state) return;
        uiState.viewMode = normalizeUiViewMode(state.viewMode);
        if (state.date) {
            const parsed = parseDate(state.date);
            if (!Number.isNaN(parsed.getTime())) {
                currentWeekStart = getMonday(parsed);
            }
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
            #scheduleControls{position:relative;z-index:5;background:var(--schedule-panel)}
            #scheduleGridContent{min-height:0;transition:opacity .2s ease}
            .schedule-table-shell{min-height:0;background:var(--schedule-grid-bg);color:var(--schedule-grid-text)}
            .schedule-table-summary{position:sticky;top:0;z-index:28;display:flex;align-items:center;justify-content:space-between;gap:1rem;border-bottom:1px solid var(--schedule-grid-border);background:color-mix(in srgb,var(--schedule-grid-head) 90%,var(--schedule-panel) 10%);padding:.72rem 1rem;box-shadow:0 16px 28px -28px rgba(15,23,42,.35)}
            .schedule-table-summary-main{display:flex;min-width:0;align-items:center;gap:.65rem;font-size:.9rem;color:var(--schedule-grid-text)}
            .schedule-table-summary-main strong{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:1rem;font-weight:900}
            .schedule-table-summary-main span:not(.schedule-table-mode-label){color:var(--schedule-grid-muted);font-weight:800;white-space:nowrap}
            .schedule-table-mode-label{border:1px solid color-mix(in srgb,var(--lesson-default-border) 45%,var(--schedule-grid-border));border-radius:999px;background:color-mix(in srgb,var(--lesson-default-bg) 72%,var(--schedule-panel));color:var(--lesson-default-text);padding:.32rem .6rem;font-size:.68rem;font-weight:900;text-transform:uppercase;letter-spacing:.12em}
            .schedule-table-summary-meta{display:flex;flex-wrap:wrap;justify-content:flex-end;gap:.4rem}
            .schedule-table-summary-meta span{border:1px solid var(--schedule-grid-border);border-radius:999px;background:color-mix(in srgb,var(--schedule-panel) 82%,transparent);color:var(--schedule-grid-muted);padding:.35rem .58rem;font-size:.7rem;font-weight:900;white-space:nowrap}
            .schedule-table-viewport{height:calc(100vh - 18rem);max-height:none;min-height:20rem;overflow:auto;overscroll-behavior:contain;scrollbar-gutter:stable both-edges;isolation:isolate;background:var(--schedule-grid-bg)}
            .schedule-table-viewport.is-scrollable{overflow:auto}
            .schedule-desktop-table{min-width:1320px}
            .schedule-table-head th{position:sticky;top:0;z-index:34;background:var(--schedule-grid-head)}
            .schedule-sticky-corner{left:0;z-index:52;background:var(--schedule-grid-head);box-shadow:1px 0 0 var(--schedule-grid-border),10px 0 22px -20px rgba(15,23,42,.55)}
            .schedule-sticky-day{z-index:34;background:var(--schedule-grid-head)}
            .schedule-day-head-inner{display:flex;flex-direction:column;align-items:center;gap:.12rem}
            .schedule-day-count{margin-top:.15rem;border-radius:999px;background:color-mix(in srgb,var(--schedule-panel) 84%,transparent);color:var(--schedule-grid-muted);padding:.18rem .45rem;font-size:.62rem;font-weight:900;text-transform:uppercase;letter-spacing:.08em}
            .schedule-day-head.is-today .schedule-day-count{background:color-mix(in srgb,var(--lesson-default-bg) 70%,var(--schedule-panel));color:var(--lesson-default-text)}
            .schedule-sticky-time{position:sticky;left:0;z-index:44;box-shadow:1px 0 0 var(--schedule-grid-border),14px 0 24px -22px rgba(15,23,42,.65);background:var(--schedule-grid-time);background-clip:padding-box}
            .schedule-slot-cell{min-width:11rem}
            .schedule-timeline-card{z-index:12;min-width:0}
            .schedule-timeline-card:hover{z-index:30}
            .lesson-card--table{min-height:92px;overflow:hidden;padding:.62rem .66rem .58rem .88rem;border-radius:.85rem;box-shadow:0 14px 24px -24px rgba(15,23,42,.42)}
            .lesson-card--table:hover{box-shadow:0 18px 32px -23px rgba(15,23,42,.48)}
            .lesson-card--table:has(details[open]){overflow:visible;z-index:60}
            .lesson-table-accent{position:absolute;inset:.5rem auto .5rem .36rem;width:.22rem;border-radius:999px;background:var(--lesson-default-text);opacity:.92}
            .lesson-card--lecture .lesson-table-accent{background:var(--lesson-lecture-text)}
            .lesson-card--seminar .lesson-table-accent{background:var(--lesson-seminar-text)}
            .lesson-card--consultation .lesson-table-accent{background:var(--lesson-consultation-text)}
            .lesson-card--exam .lesson-table-accent{background:var(--lesson-exam-text)}
            .lesson-table-topline{display:flex;min-width:0;align-items:flex-start;justify-content:space-between;gap:.35rem}
            .lesson-table-kind{font-size:.55rem;font-weight:900;line-height:1.1;letter-spacing:0;text-transform:uppercase}
            .lesson-table-module{max-width:3rem;border-radius:.45rem;padding:.16rem .32rem;font-size:.52rem;font-weight:900;line-height:1.05;box-shadow:0 8px 18px -14px rgba(15,23,42,.4)}
            .lesson-table-title{margin-top:.38rem;display:-webkit-box;min-height:2rem;overflow:hidden;-webkit-box-orient:vertical;-webkit-line-clamp:2;font-size:.8rem;font-weight:900;line-height:1.2;color:var(--schedule-grid-text);overflow-wrap:anywhere}
            .lesson-table-time{margin-top:.35rem;width:max-content;max-width:100%;border:1px solid color-mix(in srgb,var(--schedule-grid-border) 60%,transparent);border-radius:999px;background:color-mix(in srgb,var(--schedule-panel) 70%,transparent);padding:.22rem .45rem;font-size:.58rem;font-weight:900;color:var(--schedule-grid-muted);letter-spacing:.08em}
            .lesson-table-meta{display:grid;gap:.2rem;margin-top:auto;padding-top:.48rem;min-width:0}
            .lesson-table-meta.has-actions{padding-right:1.95rem}
            .lesson-table-meta-item{display:flex;min-width:0;align-items:center;gap:.28rem;font-size:.62rem;font-weight:800;line-height:1.15;color:var(--schedule-grid-muted);transition:color .16s ease}
            .lesson-table-meta-item:hover{color:var(--lesson-default-text)}
            .lesson-table-meta-icon{width:.72rem;height:.72rem;flex:0 0 auto;opacity:.55}
            .lesson-card--table .lesson-actions-panel--launcher{right:.42rem;bottom:.42rem}
            .lesson-card--table .lesson-action-overflow-toggle{min-width:1.5rem;min-height:1.5rem;border-radius:.6rem;padding:.22rem;background:color-mix(in srgb,var(--schedule-panel) 94%,transparent)}
            .lesson-card--table .lesson-action-overflow-menu{bottom:calc(100% + .35rem)}
            .schedule-timeline-card.is-split .lesson-card--table{padding-right:.56rem}
            .schedule-timeline-card.is-split .lesson-table-title{-webkit-line-clamp:3;font-size:.76rem}
            .schedule-timeline-card.is-narrow .lesson-card--table,.schedule-timeline-card.is-pinched .lesson-card--table{padding:.52rem .42rem .48rem .7rem}
            .schedule-timeline-card.is-narrow .lesson-table-module,.schedule-timeline-card.is-pinched .lesson-table-module{display:none}
            .schedule-timeline-card.is-narrow .lesson-table-title{-webkit-line-clamp:3;font-size:.72rem;line-height:1.14}
            .schedule-timeline-card.is-pinched .lesson-table-kind{font-size:.48rem;white-space:nowrap}
            .schedule-timeline-card.is-pinched .lesson-table-title{-webkit-line-clamp:3;font-size:.68rem;line-height:1.12}
            .schedule-timeline-card.is-pinched .lesson-table-meta{display:none}
            .schedule-timeline-card.is-pinched .lesson-card--table .lesson-actions-panel--launcher{right:.25rem;bottom:.25rem;transform:scale(.9);transform-origin:right bottom}
            .schedule-touch-btn{min-height:44px;padding:.7rem 1rem}
            .schedule-empty-card{border:1px solid var(--schedule-panel-border);background:var(--schedule-panel-soft);border-radius:1.25rem;padding:1.25rem;text-align:center;box-shadow:0 18px 48px -36px rgba(37,99,235,.45)}
            .schedule-empty-actions{display:flex;gap:.5rem;justify-content:center;flex-wrap:wrap;margin-top:.9rem}
            .schedule-empty-actions button,.schedule-empty-actions a{border:1px solid var(--schedule-panel-border);border-radius:.8rem;padding:.55rem .9rem;font-size:.75rem;font-weight:700;background:var(--schedule-panel);color:var(--schedule-text)}
            .schedule-cards-feed{padding:.75rem;background:var(--schedule-grid-bg)}
            .schedule-day-section{margin-bottom:1rem;border:1px solid var(--schedule-panel-border);border-radius:1.4rem;overflow:hidden;background:var(--schedule-panel);box-shadow:0 24px 40px -34px rgba(37,99,235,.35)}
            .schedule-day-header{position:relative;display:flex;align-items:flex-start;justify-content:space-between;gap:1rem;padding:1rem 1.15rem;border-bottom:1px solid var(--schedule-panel-border);background:var(--schedule-grid-head)}
            .schedule-day-header--today{background:var(--schedule-grid-today)}
            .schedule-day-header-label{text-transform:uppercase;letter-spacing:.12em;font-size:.68rem;font-weight:800;color:var(--schedule-muted)}
            .schedule-day-header-title{margin-top:.35rem;font-size:1.35rem;line-height:1.1;font-weight:900;color:var(--schedule-text)}
            .schedule-day-pill{padding:.38rem .7rem;border-radius:999px;background:#1d4ed8;color:#fff;font-size:.72rem;font-weight:700;box-shadow:0 10px 20px -16px rgba(29,78,216,.7)}
            .schedule-day-lessons{display:flex;flex-direction:column;background:var(--schedule-panel)}
            .schedule-feed-card{display:flex;flex-direction:column;gap:.8rem;padding:1rem;background:var(--schedule-panel);transition:transform .18s ease,box-shadow .18s ease,background-color .18s ease}
            .schedule-feed-card + .schedule-feed-card{border-top:1px solid var(--schedule-panel-border)}
            .schedule-feed-card:hover{background:var(--schedule-panel-soft)}
            .schedule-feed-card-head{display:flex;align-items:flex-start;justify-content:space-between;gap:.75rem}
            .schedule-feed-card-time{display:flex;align-items:baseline;gap:.45rem;min-width:0}
            .schedule-feed-card-start{font-size:1.35rem;line-height:1;font-weight:900;color:var(--schedule-text)}
            .schedule-feed-card-end{font-size:.8rem;font-weight:700;color:var(--schedule-muted);text-decoration:line-through;text-decoration-color:var(--schedule-panel-border)}
            .schedule-feed-card-kind{flex-shrink:0}
            .schedule-feed-card-body{display:flex;flex-direction:column;gap:.55rem;min-width:0}
            .schedule-feed-card-title{font-size:1rem;line-height:1.35;font-weight:800;color:var(--schedule-text);overflow-wrap:anywhere}
            .schedule-feed-card-module{overflow-wrap:anywhere}
            .schedule-feed-card-meta{display:grid;grid-template-columns:minmax(0,1fr);gap:.55rem}
            .schedule-feed-card-meta-item{display:flex;align-items:flex-start;gap:.55rem;min-width:0;font-size:.88rem;line-height:1.35;font-weight:600;color:var(--schedule-muted)}
            .schedule-feed-card-meta-item span{min-width:0;overflow-wrap:anywhere}
            .schedule-cards-feed.schedule-cards-compact{padding:.5rem}
            .schedule-cards-feed.schedule-cards-compact .schedule-day-section{margin-bottom:.65rem;border-radius:1rem}
            .schedule-cards-feed.schedule-cards-compact .schedule-day-header{padding:.65rem .85rem}
            .schedule-cards-feed.schedule-cards-compact .schedule-day-header-label{font-size:.6rem}
            .schedule-cards-feed.schedule-cards-compact .schedule-day-header-title{margin-top:.2rem;font-size:1rem}
            .schedule-cards-feed.schedule-cards-compact .schedule-day-pill{padding:.25rem .5rem;font-size:.62rem}
            .schedule-cards-feed.schedule-cards-compact .schedule-feed-card{gap:.45rem;padding:.7rem .85rem}
            .schedule-cards-feed.schedule-cards-compact .schedule-feed-card-head{gap:.5rem}
            .schedule-cards-feed.schedule-cards-compact .schedule-feed-card-start{font-size:1.05rem}
            .schedule-cards-feed.schedule-cards-compact .schedule-feed-card-end{font-size:.72rem}
            .schedule-cards-feed.schedule-cards-compact .schedule-feed-card-title{font-size:.88rem;line-height:1.25}
            .schedule-cards-feed.schedule-cards-compact .schedule-feed-card-meta{gap:.35rem}
            .schedule-cards-feed.schedule-cards-compact .schedule-feed-card-meta-item{font-size:.78rem;line-height:1.25}
            .schedule-cards-feed.schedule-cards-exams .schedule-day-header{background:linear-gradient(135deg,var(--lesson-exam-bg),var(--schedule-grid-head))}
            .schedule-cards-feed.schedule-cards-exams .schedule-day-pill{background:#be123c}
            @media (max-width:1023px){.schedule-day-header-title{font-size:1.15rem}}
            @media (min-width:1024px){
                body[data-schedule-view="table"] main{padding-bottom:1rem}
                body[data-schedule-view="table"] #mainScheduleBlock{min-height:0}
                body[data-schedule-view="table"] #scheduleGridContent{flex-grow:0}
                body[data-schedule-view="table"] #scheduleControls{box-shadow:0 12px 28px -30px rgba(15,23,42,.45)}
                body[data-schedule-view="table"] .schedule-table-viewport{max-height:none}
                body[data-schedule-view="table"] .schedule-control-panel > .schedule-control-band:first-child{padding-top:1rem;padding-bottom:1rem}
                .schedule-cards-feed.schedule-cards-desktop{padding:1rem}
                .schedule-cards-feed.schedule-cards-desktop .schedule-day-section{margin-bottom:1.25rem}
                .schedule-cards-feed.schedule-cards-desktop .schedule-day-header{position:static;padding:1.15rem 1.35rem}
                .schedule-cards-feed.schedule-cards-desktop .schedule-day-lessons{display:grid;grid-template-columns:repeat(auto-fit,minmax(360px,1fr));gap:1rem;padding:1rem;background:transparent}
                .schedule-cards-feed.schedule-cards-desktop .schedule-feed-card{min-height:15rem;border:1px solid var(--schedule-panel-border);border-radius:1rem;padding:1.1rem 1.15rem;box-shadow:0 20px 35px -30px rgba(15,23,42,.35)}
                .schedule-cards-feed.schedule-cards-desktop .schedule-feed-card + .schedule-feed-card{border-top:none}
                .schedule-cards-feed.schedule-cards-desktop .schedule-feed-card-title{font-size:1.04rem}
                .schedule-cards-feed.schedule-cards-desktop .schedule-feed-card-meta{gap:.65rem}
            }
            @media (max-width:767px){
                .schedule-table-summary{position:static;align-items:flex-start;flex-direction:column;padding:.75rem}
                .schedule-table-summary-meta{justify-content:flex-start}
            }
        `;
        document.head.appendChild(style);
    }

    function applyFilterVisibility() {
        const section = document.getElementById("moduleFilterSection");
        const content = document.getElementById("filterContent");
        const arrow = document.getElementById("filterArrow");
        const button = document.getElementById("filterToggleBtn");
        document.body?.classList.toggle("schedule-has-entity", Boolean(currentEntity?.id));
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
        scheduleDesktopTableViewportResize();
        saveUiPrefs();
    }
    function syncContextBarLabels() {
        const labels = {
            viewCardsBtn:["schedule.view.cards", "Карточки"],
            viewCompactBtn:["schedule.view.compact", "Компактно"],
            viewTableBtn:["schedule.view.table", "Таблица"],
            viewExamsBtn:["schedule.view.exams", "Экзамены"],
        };
        Object.entries(labels).forEach(([id, [key, fallback]]) => {
            const element = document.getElementById(id);
            if (element) {
                element.textContent = t(key, fallback);
            }
        });
    }
    function setViewMode(mode) {
        const requestedMode = normalizeUiViewMode(mode);
        const previousLessonMode = window.getSchedulePageState?.().lessonMode;
        const isDesktopViewport = window.innerWidth >= 1024;
        const effectiveMode = requestedMode === "table" && !isDesktopViewport ? "cards" : requestedMode;
        uiState.viewMode = requestedMode;
        window.setScheduleViewModeState?.(requestedMode, { updateUrl: true });
        const desktop = document.getElementById("desktopSchedule");
        const mobile = document.getElementById("mobileSchedule");
        if (!desktop || !mobile) return;
        const auto = effectiveMode === "auto";
        const table = effectiveMode === "table";
        const cards = effectiveMode === "cards";
        const compact = effectiveMode === "compact";
        const exams = effectiveMode === "exams";
        const showDesktop = table || (auto && isDesktopViewport);
        const showCardsFeed = cards || compact || exams || (auto && !isDesktopViewport);
        desktop.style.display = showDesktop ? "block" : "none";
        mobile.style.display = showCardsFeed ? "flex" : "none";
        document.body?.setAttribute("data-schedule-view", effectiveMode);
        document.getElementById("scheduleGridContent")?.setAttribute("data-schedule-view", effectiveMode);
        desktop.classList.toggle("hidden", !showDesktop);
        mobile.classList.toggle("hidden", !showCardsFeed);
        mobile.classList.toggle("schedule-cards-desktop", cards && isDesktopViewport);
        mobile.classList.toggle("schedule-cards-compact", compact || exams);
        mobile.classList.toggle("schedule-cards-exams", exams);
        if (table) {
            enhanceDesktopTableOverflow();
        }
        const isActive = (id, active) => {
            const btn = document.getElementById(id);
            if (!btn) return;
            btn.classList.toggle("schedule-view-active", active);
            btn.classList.toggle("schedule-view-idle", !active);
        };
        const tableBtn = document.getElementById("viewTableBtn");
        if (tableBtn) {
            tableBtn.disabled = !isDesktopViewport;
            tableBtn.classList.toggle("cursor-not-allowed", !isDesktopViewport);
            tableBtn.classList.toggle("opacity-50", !isDesktopViewport);
            tableBtn.title = !isDesktopViewport
                ? t("schedule.view.tableDesktopOnly", "Таблица доступна на более широких экранах")
                : "";
        }
        isActive("viewTableBtn", table);
        isActive("viewCardsBtn", cards);
        isActive("viewCompactBtn", compact);
        isActive("viewExamsBtn", exams);
        saveUiPrefs();
        const shouldRerenderForExamMode = !isRenderingForViewMode
            && ((requestedMode === "exams") !== (previousLessonMode === "exams_only"));
        if (shouldRerenderForExamMode) {
            isRenderingForViewMode = true;
            filterAndRender();
            isRenderingForViewMode = false;
        }
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
    function resizeDesktopTableViewport(tableWrap = document.querySelector("#desktopSchedule .schedule-table-viewport")) {
        if (!tableWrap || window.innerWidth < 1024) return;
        const rect = tableWrap.getBoundingClientRect();
        const bottomGap = 16;
        const availableHeight = Math.floor(window.innerHeight - rect.top - bottomGap);
        const nextHeight = Math.max(300, availableHeight);
        tableWrap.style.height = `${nextHeight}px`;
        tableWrap.style.maxHeight = "none";
        tableWrap.style.minHeight = "0px";
    }
    function scheduleDesktopTableViewportResize() {
        if (tableResizeFrame) cancelAnimationFrame(tableResizeFrame);
        tableResizeFrame = requestAnimationFrame(() => {
            tableResizeFrame = null;
            resizeDesktopTableViewport();
        });
    }
    function applyInitialTableScroll(tableWrap) {
        if (!tableWrap || tableWrap.dataset.autoScrollApplied === "1") return;
        tableWrap.dataset.autoScrollApplied = "1";
        const requestedTop = Number(tableWrap.dataset.initialScrollTop || 0);
        requestAnimationFrame(() => {
            const maxTop = Math.max(0, tableWrap.scrollHeight - tableWrap.clientHeight);
            tableWrap.scrollTop = Math.min(Math.max(0, requestedTop), maxTop);
        });
    }
    function enhanceDesktopTableOverflow() {
        const tableWrap = document.querySelector("#desktopSchedule .schedule-table-viewport");
        if (!tableWrap) return;
        tableWrap.classList.remove("overflow-hidden");
        tableWrap.classList.add("is-scrollable");
        resizeDesktopTableViewport(tableWrap);
        applyInitialTableScroll(tableWrap);
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
        document.getElementById("viewCardsBtn")?.addEventListener("click", () => setViewMode("cards"));
        document.getElementById("viewCompactBtn")?.addEventListener("click", () => setViewMode("compact"));
        document.getElementById("viewTableBtn")?.addEventListener("click", () => setViewMode("table"));
        document.getElementById("viewExamsBtn")?.addEventListener("click", () => setViewMode("exams"));
        window.addEventListener("resize", () => {
            setViewMode(uiState.viewMode);
            scheduleDesktopTableViewportResize();
        });
        window.addEventListener("mpb-schedule-state-change", (event) => {
            const nextMode = event.detail?.state?.viewMode;
            if (SCHEDULE_UI_VIEW_MODES.includes(nextMode) && nextMode !== uiState.viewMode) {
                uiState.viewMode = nextMode;
                setViewMode(nextMode);
            }
        });
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
        window.scheduleResizeDesktopTableViewport = scheduleDesktopTableViewportResize;
    });
})();
