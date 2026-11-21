(() => {
    const trigger = document.getElementById("scheduleSessionOpen");
    const dialog = document.getElementById("scheduleSession");
    const group = document.getElementById("scheduleSessionGroup");
    const controls = document.getElementById("scheduleSessionControls");
    const term = document.getElementById("scheduleSessionTerm");
    const status = document.getElementById("scheduleSessionStatus");
    const checkedLabel = document.getElementById("scheduleSessionChecked");
    const calendar = document.getElementById("scheduleSessionCalendar");
    const content = document.getElementById("scheduleSessionContent");
    const translate = (key, params = {}) => window.mpbI18n.t(`schedule.session.${key}`, key, params);
    const kindLabel = kind => window.mpbI18n.t(`schedule.details.curriculum.kind.${kind}`, kind);
    let entity;
    let referenceDate;
    let controller;
    let plan;
    let dates;

    function node(tag, text, className) {
        const element = document.createElement(tag);
        if (text) element.textContent = text;
        if (className) element.className = className;
        return element;
    }

    function dateLabel(value) {
        return new Intl.DateTimeFormat(window.mpbI18n.getLanguage(), {
            day: "numeric", month: "short", timeZone: "UTC",
        }).format(new Date(`${value}T00:00:00Z`));
    }

    function verificationLabel(value) {
        if (!value) return "";
        const checked = new Date(value);
        if (Number.isNaN(checked.getTime())) return "";
        return new Intl.DateTimeFormat(window.mpbI18n.getLanguage(), {
            dateStyle: "medium", timeStyle: "short", timeZone: "Europe/Moscow",
        }).format(checked);
    }

    function scheduleLink(event) {
        const query = new URLSearchParams({
            type: "group", id: entity.id, name: entity.name || entity.id,
            date: event.date, lesson_date: event.date,
        });
        if (event.lesson_id) query.set("lesson", event.lesson_id);
        const view = window.getSchedulePageState().viewMode;
        if (view === "table" || view === "cards") query.set("view", view);
        const link = node("a", "", "session-event-link");
        link.href = `/schedule?${query}`;
        link.title = translate(event.lesson_id ? "openLesson" : "openDay");
        return link;
    }

    function selectTerms() {
        term.replaceChildren(...plan.terms.map(item => {
            const range = `${dateLabel(item.start_date)} – ${dateLabel(item.end_date)}`;
            const option = node("option", translate("term", { number: item.semester, range }));
            option.value = item.semester;
            return option;
        }));
        if (plan.term) term.value = plan.term.semester;
        controls.hidden = !plan.terms.length;
    }

    function sourceLink(record) {
        if (!/^\/api\/schedule\/curriculum\/documents\/[1-9]\d*\/[a-f0-9]{64}\.pdf$/.test(record.snapshot_url)) return null;
        const anchor = node("a", translate("source", { page: record.page }), "session-source");
        const base = (window.getMpbApiBase?.() || "/api").replace(/\/+$/, "");
        anchor.href = `${base}${record.snapshot_url.slice(4)}#page=${record.page}`;
        anchor.title = record.source_title;
        anchor.target = "_blank";
        anchor.rel = "noopener noreferrer";
        return anchor;
    }

    const rowKey = row => JSON.stringify([row.source_document_id, row.discipline_code, row.discipline_name]);

    function render() {
        content.replaceChildren();
        if (!plan) return;
        selectTerms();
        if (plan.status !== "confirmed") {
            status.textContent = translate(plan.status === "unmapped" ? "unmapped" : "unavailable");
            return;
        }
        const dateState = {
            checked: "checked", partial: "datesPartial", stale: "datesStale",
            unavailable: "datesUnavailable", unchecked: "unchecked",
        }[dates?.dates_status];
        status.textContent = translate(plan.assessments.length ? dateState || "checking" : "empty");
        if (plan.stale) content.append(node("p", translate("stale"), "session-warning"));
        if (!plan.assessments.length) return;

        const lastChecked = verificationLabel(dates?.dates_checked_at);
        if (checkedLabel) checkedLabel.textContent = lastChecked ? translate("lastChecked", { checked: lastChecked }) : "";
        if (calendar) calendar.hidden = !plan.assessments.some(row => ["exam", "pass", "graded_pass"].includes(row.kind));
        const records = new Map();
        for (const row of plan.assessments) {
            const key = rowKey(row);
            if (!records.has(key)) records.set(key, []);
            records.get(key).push(row);
        }
        const dated = new Map();
        for (const event of dates?.events || []) {
            const key = rowKey(event);
            if (!dated.has(key)) dated.set(key, []);
            dated.get(key).push(event);
        }
        const list = node("ul", null, "session-list");
        const firstDate = key => dated.has(key) ? `${dated.get(key)[0].date}T${dated.get(key)[0].start}` : "9999";
        const rows = [...records.entries()].sort(([keyA, a], [keyB, b]) =>
            firstDate(keyA).localeCompare(firstDate(keyB)) ||
            a[0].discipline_name.localeCompare(b[0].discipline_name, window.mpbI18n.getLanguage()));
        for (const [key, forms] of rows) {
            const item = node("li", null, "session-row");
            const current = forms[0];
            const details = node("div");
            details.append(node("h3", current.discipline_name));
            const types = node("div", null, "session-types");
            const kinds = new Set(forms.map(row => row.kind));
            for (const kind of kinds) {
                const badge = node("span", kindLabel(kind), "session-kind");
                badge.dataset.kind = kind;
                types.append(badge);
            }
            details.append(types);
            for (const row of new Map(forms.map(form => [form.page, form])).values()) {
                const anchor = sourceLink(row);
                if (anchor) details.append(anchor);
            }
            const timing = node("div", null, "session-timing");
            for (const event of dated.get(key) || []) {
                const block = node("div", null, "session-event");
                if (kinds.size > 1) block.append(node("span", kindLabel(event.kind)));
                const time = node("time", `${dateLabel(event.date)} · ${event.start}`);
                time.dateTime = `${event.date}T${event.start}:00+03:00`;
                const link = scheduleLink(event);
                link.append(time);
                block.append(link);
                if (event.room) block.append(node("span", event.room));
                if (dates.dates_status === "partial" || dates.dates_status === "stale") {
                    const range = dates.dates_coverage?.find(item => item.start_date <= event.date && event.date <= item.end_date);
                    const checked = verificationLabel(range?.checked_at);
                    if (checked && checked !== lastChecked) {
                        block.append(node("span", translate("lastChecked", { checked }), "session-event-check"));
                    }
                }
                timing.append(block);
            }
            if (!timing.children.length && dates?.dates_status === "checked") {
                timing.append(node("span", translate("noDate")));
            } else if (!timing.children.length && ["partial", "stale"].includes(dates?.dates_status)) {
                timing.append(node("span", translate("dateUnverified")));
            }
            item.append(details, timing);
            list.append(item);
        }
        content.append(list);
    }

    async function fetchSession(semester, includeDates, signal) {
        const query = new URLSearchParams({ group_id: entity.id });
        if (referenceDate) query.set("reference_date", referenceDate);
        if (semester) query.set("semester", semester);
        if (includeDates) query.set("include_dates", "true");
        const response = await fetch(`${window.getMpbApiBase?.() || "/api"}/schedule/session?${query}`, { signal });
        if (!response.ok) throw new Error("Session endpoint unavailable");
        return response.json();
    }

    async function load(semester) {
        controller?.abort();
        const request = new AbortController();
        controller = request;
        plan = dates = null;
        content.replaceChildren();
        if (checkedLabel) checkedLabel.textContent = "";
        if (calendar) calendar.hidden = true;
        status.textContent = translate("loading");
        try {
            const data = await fetchSession(semester, false, request.signal);
            if (request.signal.aborted) return;
            plan = data;
            render();
            if (plan.status !== "confirmed" || !plan.assessments.length) return;
            const dated = await fetchSession(plan.term.semester, true, request.signal);
            if (request.signal.aborted) return;
            dates = dated;
            render();
        } catch {
            if (request.signal.aborted) return;
            status.textContent = translate(plan ? "datesError" : "error");
            const retry = node("button", translate("retry"), "session-retry");
            retry.type = "button";
            retry.addEventListener("click", () => load(semester));
            content.prepend(retry);
        }
    }

    function updateTrigger() {
        const state = window.getSchedulePageState();
        trigger.hidden = state.entity?.type !== "group" || !state.entity.id;
    }

    trigger.addEventListener("click", async () => {
        await window.mpbI18n.ready;
        const state = window.getSchedulePageState();
        if (state.entity?.type !== "group" || !state.entity.id || dialog.open) return;
        entity = state.entity;
        referenceDate = state.date;
        group.textContent = entity.name || entity.id;
        controls.hidden = true;
        dialog.showModal();
        load();
    });
    calendar?.addEventListener("click", () => {
        dialog.close();
        window.openCalendarSyncPanel?.({ lessonMode: "exams_only" });
    });
    term.addEventListener("change", () => load(term.value));
    dialog.addEventListener("close", () => controller?.abort());
    window.addEventListener("mpb-schedule-state-change", updateTrigger);
    window.addEventListener("mpb-language-change", () => { if (dialog.open) render(); });
    updateTrigger();
})();
