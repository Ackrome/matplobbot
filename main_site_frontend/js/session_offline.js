(() => {
    const key = "mpb_public_session_v1";
    const moduleUrl = document.currentScript?.src;
    const maxBytes = 250000;
    const kinds = new Set(["exam", "pass", "graded_pass", "coursework", "course_project"]);
    const isoDay = value => {
        if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
        const date = new Date(`${value}T00:00:00Z`);
        return !Number.isNaN(date.getTime()) && date.toISOString().slice(0, 10) === value;
    };
    const stamp = value => typeof value === "string" && value.length <= 40 && !Number.isNaN(Date.parse(value)) ? value : null;
    const text = (value, max) => typeof value === "string" && value.length <= max ? value : "";
    const inTerm = (value, term) => isoDay(value) && value >= term.start_date && value <= term.end_date;
    const identity = row => JSON.stringify([row.source_document_id, row.discipline_code, row.discipline_name, row.kind]);

    function project(plan, dated, savedAt) {
        if (plan?.status !== "confirmed" || !Array.isArray(plan.assessments) || plan.assessments.length > 500) return null;
        const groupId = text(plan.group_id, 128);
        const groupName = text(plan.group_name, 255);
        if (!groupId || !groupName || /[/\\?#\u0000]/.test(groupId) || !stamp(savedAt)) return null;
        const { semester, start_date, end_date } = plan.term || {};
        if (!Number.isInteger(semester) || semester < 1 || semester > 16 || !isoDay(start_date) || !isoDay(end_date)
            || start_date > end_date || Date.parse(end_date) - Date.parse(start_date) > 400 * 86400000) return null;
        const term = { semester, start_date, end_date };
        const assessments = [];
        for (const row of plan.assessments) {
            if (!row || !kinds.has(row.kind) || row.semester !== semester || !Number.isInteger(row.source_document_id)
                || row.source_document_id < 1 || !Number.isInteger(row.page) || row.page < 1
                || !text(row.discipline_code, 100) || !text(row.discipline_name, 500)) return null;
            const snapshot = text(row.snapshot_url, 160);
            assessments.push({
                semester, discipline_code: row.discipline_code, discipline_name: row.discipline_name, kind: row.kind,
                page: row.page, source_document_id: row.source_document_id, source_title: text(row.source_title, 500),
                snapshot_url: /^\/api\/schedule\/curriculum\/documents\/[1-9]\d*\/[a-f0-9]{64}\.pdf$/.test(snapshot) ? snapshot : "",
            });
        }
        let dates = null;
        const statuses = new Set(["unchecked", "unavailable", "partial", "stale", "checked"]);
        if (dated) {
            if (!Array.isArray(dated.events) || dated.events.length > 1000 || !statuses.has(dated.dates_status)) return null;
            const identities = new Set(assessments.map(identity));
            const events = dated.events.filter(row => row && identities.has(identity(row)) && inTerm(row.date, term)
                && /^(?:[01]\d|2[0-3]):[0-5]\d$/.test(row.start)).map(row => ({
                date: row.date, start: row.start, room: text(row.room, 255), lesson_id: /^[1-9]\d{0,24}$/.test(row.lesson_id) ? row.lesson_id : null,
                discipline_code: row.discipline_code, discipline_name: row.discipline_name, kind: row.kind, source_document_id: row.source_document_id,
            }));
            const ranges = Array.isArray(dated.dates_coverage) ? dated.dates_coverage.slice(0, 16) : [];
            dates = {
                dates_status: dated.dates_status,
                dates_checked_at: stamp(dated.dates_checked_at),
                dates_coverage: ranges.filter(range => range && inTerm(range.start_date, term) && inTerm(range.end_date, term)
                    && range.start_date <= range.end_date && stamp(range.checked_at)).map(range => ({
                    start_date: range.start_date, end_date: range.end_date, checked_at: range.checked_at,
                })),
                events,
            };
        }
        return {
            version: 1, saved_at: savedAt, dates,
            plan: { status: "confirmed", group_id: groupId, group_name: groupName, term, terms: [term], assessments, stale: Boolean(plan.stale) },
        };
    }

    function read() {
        try {
            const raw = localStorage.getItem(key);
            if (!raw || raw.length > maxBytes) return null;
            const saved = JSON.parse(raw);
            return saved.version === 1 ? project(saved.plan, saved.dates, saved.saved_at) : null;
        } catch {
            return null;
        }
    }

    function save(plan, dates) {
        const data = project(plan, dates, new Date().toISOString());
        const raw = data && JSON.stringify(data);
        if (!raw || raw.length > maxBytes) return false;
        try {
            localStorage.setItem(key, raw);
            return true;
        } catch {
            return false;
        }
    }

    async function available() {
        try {
            return Boolean(navigator.serviceWorker?.controller && moduleUrl
                && await caches.match("/schedule") && await caches.match(moduleUrl));
        } catch {
            return false;
        }
    }

    function remove() {
        try {
            localStorage.removeItem(key);
            return true;
        } catch {
            return false;
        }
    }

    function url(saved) {
        const { group_id, group_name, term } = saved.plan;
        return `/schedule?${new URLSearchParams({ type: "group", id: group_id, name: group_name, date: term.start_date,
            session: term.semester, saved_session: "1" })}`;
    }

    window.MpbSessionOffline = { available, read, save, remove, url };
})();
