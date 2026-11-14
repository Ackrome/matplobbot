(() => {
    let state = null;
    let controller;
    const tr = (key, fallback, params) => window.mpbI18n?.t(`schedule.history.${key}`, fallback, params) ?? fallback;
    const classes = {
        panel: 'rounded-3xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-700 dark:bg-slate-800 md:p-5',
        button: 'rounded-xl border border-slate-200 px-3 py-2 text-xs font-bold text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-900',
        card: 'rounded-2xl border border-slate-200 p-3 dark:border-slate-700',
        subtle: 'text-xs text-slate-500 dark:text-slate-400',
    };
    const types = {
        added: ['Added', 'text-emerald-700 dark:text-emerald-300'],
        cancelled: ['Cancelled', 'text-rose-700 dark:text-rose-300'],
        moved: ['Moved', 'text-amber-700 dark:text-amber-300'],
        replaced: ['Replaced', 'text-blue-700 dark:text-blue-300'],
    };

    function element(tag, className, content) {
        const node = document.createElement(tag);
        if (className) node.className = className;
        if (content !== undefined) node.textContent = content;
        return node;
    }

    function dateLabel(value, timestamp = false) {
        if (!value) return '—';
        const date = new Date(timestamp ? value : `${value}T12:00:00+03:00`);
        if (Number.isNaN(date.valueOf())) return '—';
        return new Intl.DateTimeFormat(window.mpbI18n?.getLanguage?.() || 'en', {
            timeZone: 'Europe/Moscow',
            day: 'numeric',
            month: 'short',
            ...(timestamp ? { hour: '2-digit', minute: '2-digit' } : {}),
        }).format(date);
    }

    function renderLesson(label, item) {
        const box = element('div', 'min-w-0 break-words rounded-xl bg-slate-50 p-3 text-sm text-slate-700 dark:bg-slate-900 dark:text-slate-200');
        box.append(element('p', `font-bold ${classes.subtle}`, label));
        box.append(element('p', 'mt-1 font-bold', item.discipline));
        box.append(element('p', 'mt-1', `${dateLabel(item.date)} · ${item.begin}–${item.end}`));
        const place = [item.room, item.building].filter(Boolean).join(', ');
        const details = [place, item.teacher, item.group, item.kind].filter(Boolean).join(' · ');
        if (details) box.append(element('p', `mt-1 ${classes.subtle}`, details));
        return box;
    }

    function renderChange(change, entity, eventKey) {
        const record = element('li', classes.card);
        const [label, tone] = types[change.kind] || ['', ''];
        const meta = element('div', 'mb-2 flex flex-wrap items-center justify-between gap-2');
        meta.append(element('span', `text-sm font-bold ${tone}`, tr(change.kind, label)));
        const observed = element('time', classes.subtle, dateLabel(change.observed_at, true));
        observed.dateTime = change.observed_at;
        meta.append(observed);
        record.append(meta);
        const comparison = element('div', change.before && change.after ? 'grid gap-2 sm:grid-cols-2' : '');
        if (change.before) comparison.append(renderLesson(tr('before', 'Before'), change.before));
        if (change.after) comparison.append(renderLesson(tr('after', 'After'), change.after));
        record.append(comparison);

        const lesson = change.after || change.before;
        const opensLesson = Boolean(change.after && lesson.oid);
        const link = element('a', `mt-2 inline-flex ${classes.button}`, opensLesson
            ? tr('openLesson', 'Open class')
            : tr('openWeek', 'Open week'));
        const params = new URLSearchParams({
            type: entity.type, id: entity.id, name: entity.name, date: lesson.date, changes: '1',
        });
        if (eventKey) params.set('change_event', eventKey);
        if (opensLesson) {
            params.set('lesson', lesson.oid);
            params.set('lesson_date', lesson.date);
        }
        link.href = `/schedule?${params}`;
        record.append(link);
        return record;
    }

    function keyFor(entity, eventKey) {
        return JSON.stringify([entity?.type, entity?.id, eventKey]);
    }

    function reset() {
        controller?.abort();
        controller = undefined;
        state = null;
    }

    async function load(entity, eventKey, onChange) {
        reset();
        controller = new AbortController();
        const request = { key: keyFor(entity, eventKey), status: 'loading' };
        state = request;
        const base = window.getMpbApiBase ? window.getMpbApiBase() : '/api';
        const query = eventKey ? `?${new URLSearchParams({ event: eventKey })}` : '';
        const url = `${base}/schedule/history/${encodeURIComponent(entity.type)}/${encodeURIComponent(entity.id)}${query}`;
        try {
            const result = await window.ScheduleApi.requestJson(url, { signal: controller.signal, cache: 'no-store' });
            if (state !== request) return;
            if (!Array.isArray(result?.items)) throw new Error('Invalid schedule history');
            state = { ...request, status: 'ready', ...result };
        } catch (_) {
            if (state !== request) return;
            state = { ...request, status: 'error' };
        }
        onChange();
    }

    function render(container, { entity, eventKey, onClose, onChange }) {
        if (state?.key !== keyFor(entity, eventKey)) void load(entity, eventKey, onChange);
        const active = state;
        const focusWasInside = container.contains(document.activeElement);
        container.classList.remove('hidden');
        const panel = element('div', classes.panel);
        const header = element('div', 'flex flex-wrap items-start justify-between gap-3');
        header.append(element('h2', 'text-xl font-black text-slate-900 dark:text-slate-100', tr('title', 'Schedule history')));
        const close = element('button', classes.button, tr('hide', 'Hide history'));
        close.type = 'button';
        close.addEventListener('click', onClose);
        header.append(close);
        panel.append(header);
        const status = element('p', `mt-2 ${classes.subtle}`);
        status.setAttribute('role', 'status');
        if (active.status === 'loading') {
            status.textContent = tr('loading', 'Loading schedule changes…');
        } else if (active.status === 'error') {
            status.textContent = tr('error', 'Schedule history could not be loaded.');
            const retry = element('button', `mt-2 ${classes.button}`, tr('retry', 'Try again'));
            retry.addEventListener('click', () => { void load(entity, eventKey, onChange); onChange(); });
            panel.append(status, retry);
        } else {
            status.textContent = active.items.length
                ? tr('retention', 'Changes recorded in the last {days} days · Moscow time', { days: active.retention_days })
                : eventKey
                    ? tr('missingEvent', 'This change is no longer available. You can still open the full schedule.')
                    : active.tracked
                        ? tr('empty', 'No recent changes have been recorded for this schedule.')
                        : tr('untracked', 'History is collected for active schedule subscriptions. This schedule has no recorded changes yet.');
        }
        if (active.status !== 'error') panel.append(status);
        if (eventKey) {
            const all = element('a', `mt-2 inline-flex ${classes.button}`, tr('all', 'Show all changes'));
            const params = new URLSearchParams(window.location.search);
            ['change_event', 'lesson', 'lesson_date'].forEach(key => params.delete(key));
            all.href = `/schedule?${params}`;
            panel.append(all);
        }
        if (active.items?.length) {
            const entries = element('ol', 'mt-3 space-y-2');
            entries.append(...active.items.map(item => renderChange(item, entity, eventKey)));
            panel.append(entries);
            if (active.truncated) panel.append(element('p', `mt-2 ${classes.subtle}`, tr('truncated', 'Showing the 50 most recent changes.')));
        }
        container.replaceChildren(panel);
        if (focusWasInside) close.focus();
    }

    function count(entity, eventKey) {
        return state?.key === keyFor(entity, eventKey) ? state.items?.length || 0 : 0;
    }

    window.MpbScheduleHistory = { render, reset, count };
})();
