/* Lesson details and all cached occurrences of their discipline. */
(() => {
    'use strict';
    const text = value => typeof value === 'string' ? value.trim() : typeof value === 'number' ? String(value) : '';
    const first = (...values) => values.map(text).find(Boolean) || '';
    const canonical = value => text(value).normalize('NFKC').toLocaleLowerCase().replace(/\s+/g, ' ');
    const t = (key, params = {}) => window.mpbI18n.t(`schedule.details.${key}`, key, params);
    const locale = () => window.mpbI18n.getLanguage() === 'ru' ? 'ru-RU' : 'en-GB';
    function isoDate(value) {
        const parts = /^(\d{4})[.-](\d{2})[.-](\d{2})$/.exec(text(value));
        if (!parts) return '';
        const result = `${parts[1]}-${parts[2]}-${parts[3]}`;
        const date = new Date(`${result}T12:00:00Z`);
        return !Number.isNaN(date.getTime()) && date.toISOString().slice(0, 10) === result ? result : '';
    }
    const clock = value => /^([01]\d|2[0-3]):[0-5]\d$/.test(text(value)) ? text(value) : '';
    function safeUrl(value) {
        try {
            const url = new URL(text(value));
            return ['https:', 'http:'].includes(url.protocol) && !url.username && !url.password ? url.href : '';
        } catch { return ''; }
    }
    function normalizeLesson(raw, entity = {}) {
        const date = isoDate(raw.date), start = clock(raw.beginLesson), end = clock(raw.endLesson);
        const startAt = date && start ? Date.parse(`${date}T${start}:00+03:00`) : null;
        const endAt = date && end ? Date.parse(`${date}T${end}:00+03:00`) : null;
        const teacherName = first(raw.lecturer_title, raw.lecturer_name, raw.teacher_name);
        const teacherFallback = text(raw.lecturer);
        const teacher = (teacherName || (/^[\p{L}\s._'-]+$/u.test(teacherFallback) ? teacherFallback : '')).replace(/_/g, ' ');
        const room = first(raw.auditorium, raw.auditorium_title);
        const building = first(raw.building, raw.buildingAddress, raw.address);
        const emails = [...new Set(first(raw.lecturerEmail, raw.lecturer_email).split(/[;,\s]+/).filter(value => /^[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+$/.test(value)))];
        const links = [...new Set([raw.url, raw.url1, raw.url2, raw.lessonUrl, raw.onlineUrl, raw.streamUrl].map(safeUrl).filter(Boolean))];
        const group = first(raw.group, entity.type === 'group' ? entity.name : '');
        return {
            raw, date, start, end, startAt, endAt,
            duration: startAt !== null && endAt !== null && endAt > startAt ? (endAt - startAt) / 60000 : null,
            title: first(raw.discipline_full, raw.discipline, raw.discipline_short),
            disciplineId: first(raw.disciplineOid, raw.discipline_id),
            kind: text(raw.kindOfWork), module: text(raw.module), teacher, emails, links,
            teacherId: first(raw.lecturer_id, raw.lecturerOid, /^\d+$/.test(teacherFallback) ? teacherFallback : ''),
            room, roomId: first(raw.auditorium_id, raw.auditoriumOid),
            building: building && !canonical(room).includes(canonical(building)) ? building : '',
            group,
            groupId: first(raw.groupOid, raw.group_id, entity.type === 'group' && canonical(group) === canonical(entity.name) ? entity.id : ''),
            subgroup: first(raw.subGroup, raw.subgroup, raw.subgroupName),
            notes: first(raw.note, raw.notes, raw.comment, raw.description),
        };
    }
    function occurrenceKey(item) {
        // Different rooms/teachers/subgroups remain distinct even if an upstream ID is reused.
        return JSON.stringify([item.date || text(item.raw.date), item.start, item.end, item.title,
            item.kind, item.module, item.room, item.roomId, item.building, item.teacher, item.teacherId,
            item.group, item.groupId, item.subgroup, item.emails, item.links, item.notes]);
    }
    function curriculumContext(item, entity = {}) {
        // A teacher or room ID must never be interpreted as the student's group.
        const currentGroup = entity.type === 'group' && canonical(item.group) === canonical(entity.name);
        const groupId = currentGroup ? text(entity.id) : item.groupId;
        if (!/^[1-9]\d*$/.test(groupId) || !item.title || !item.date) return null;
        return { group_id: groupId, discipline: item.title, lesson_date: item.date };
    }
    function curriculumSnapshotUrl(value) {
        const path = text(value);
        if (!/^\/api\/schedule\/curriculum\/documents\/[1-9]\d*\/[a-f0-9]{64}\.pdf$/.test(path)) return '';
        try {
            const base = text(window.getMpbApiBase?.() || '/api').replace(/\/+$/, '');
            return safeUrl(new URL(`${base}${path.slice(4)}`, window.location.origin).href);
        } catch { return ''; }
    }
    function normalizeCurriculum(data, groupId) {
        const statuses = ['confirmed', 'unmapped', 'unavailable', 'not_found', 'needs_review'];
        const kinds = ['exam', 'pass', 'graded_pass', 'coursework', 'course_project'];
        const semester = value => Number.isInteger(value) && value > 0 && value <= 30 ? value : null;
        if (!data || !statuses.includes(data.status) || text(data.group_id) !== groupId || !Array.isArray(data.assessments)) return null;
        const assessments = [];
        for (const item of data.assessments) {
            if (!item || !kinds.includes(item.kind) || !semester(item.semester)) return null;
            const sourceUrl = safeUrl(item.source_url);
            if (!sourceUrl) return null;
            const url = new URL(sourceUrl);
            if (url.protocol !== 'https:' || !(url.hostname === 'fa.ru' || url.hostname.endsWith('.fa.ru'))) return null;
            const page = Number.isInteger(item.page) && item.page > 0 ? item.page : null;
            if (page) url.hash = `page=${page}`;
            const snapshot = curriculumSnapshotUrl(item.snapshot_url);
            assessments.push({ kind: item.kind, semester: item.semester, sourceUrl: url.href,
                snapshotUrl: snapshot ? `${snapshot}${page ? `#page=${page}` : ''}` : '',
                sourceTitle: text(item.source_title), page });
        }
        if (data.status === 'confirmed' && (!assessments.length || !semester(data.semester))) return null;
        return { status: data.status, semester: semester(data.semester), assessments,
            program: text(data.program), admissionYear: text(data.admission_year),
            checkedAt: text(data.checked_at), stale: data.stale === true };
    }
    function relatedLessons(selected, schedule, entity, includeSelected = true) {
        const seen = new Set();
        const records = includeSelected ? [selected.raw, ...(schedule || [])] : schedule || [];
        return records.map(raw => normalizeLesson(raw, entity)).filter(item => {
            const same = selected.disciplineId && item.disciplineId
                ? selected.disciplineId === item.disciplineId
                : Boolean(selected.title && canonical(selected.title) === canonical(item.title))
                    && canonical(selected.module) === canonical(item.module);
            const key = occurrenceKey(item);
            if ((!same && item.raw !== selected.raw) || seen.has(key)) return false;
            seen.add(key);
            return true;
        }).sort((a, b) => (a.startAt ?? Infinity) - (b.startAt ?? Infinity) || a.room.localeCompare(b.room));
    }
    function dateLabel(date, options = {}) {
        if (!date) return t('dateMissing');
        return new Intl.DateTimeFormat(locale(), { timeZone: 'UTC', day: 'numeric', month: 'long', year: 'numeric', ...options }).format(new Date(`${date}T12:00:00Z`));
    }
    const timeLabel = item => item.start && item.end ? `${item.start} — ${item.end}` : item.start || item.end || t('timeMissing');
    const node = (tag, className = '', value) => {
        const element = document.createElement(tag);
        if (className) element.className = className;
        if (value !== undefined) element.textContent = value;
        return element;
    };
    function button(label, handler, className = 'ld-button') {
        const result = node('button', className, label);
        result.type = 'button'; result.addEventListener('click', handler);
        return result;
    }
    function externalLink(label, href) {
        const link = node('a', 'ld-text-link', label);
        link.href = href; link.target = '_blank'; link.rel = 'noopener noreferrer';
        return link;
    }
    let active = null;
    function open(raw, context = {}, trigger = document.activeElement) {
        if (!raw) return;
        if (active) { active.dialog.close(); active.cleanup(); }
        const dialog = node('dialog', 'lesson-details-dialog');
        dialog.id = 'lessonDetailsDialog'; dialog.setAttribute('aria-labelledby', 'lessonDetailsTitle');
        let selected = normalizeLesson(raw, context.entity), tab = 'lesson';
        const original = selected;
        let occurrences = relatedLessons(original, context.schedule, context.entity);
        let cacheState = 'idle', cacheSnapshot = null, cacheController = null, selectedFromCache = false;
        let curriculumState = 'idle', curriculumData = null, curriculumController = null;
        const sourceOpen = new Set();
        const previousOverflow = document.documentElement.style.overflow;
        const scroll = { left: window.scrollX, top: window.scrollY };
        const grid = document.querySelector('.schedule-table-viewport');
        const gridScroll = grid ? { left: grid.scrollLeft, top: grid.scrollTop } : null;
        let closed = false;
        function cleanup() {
            if (closed) return;
            closed = true;
            cacheController?.abort();
            curriculumController?.abort();
            document.documentElement.style.overflow = previousOverflow;
            window.removeEventListener('mpb-language-change', languageChanged);
            dialog.remove();
            if (trigger?.isConnected) trigger.focus?.({ preventScroll: true });
            window.scrollTo({ ...scroll, behavior: 'instant' });
            if (grid?.isConnected && gridScroll) grid.scrollTo(gridScroll);
            if (active?.dialog === dialog) active = null;
        }
        function row(dl, label, value, extra) {
            const dd = node('dd');
            if (value instanceof Node) dd.append(value); else dd.textContent = value;
            if (extra) dd.append(extra);
            dl.append(node('dt', '', label), dd);
        }
        function disclosure(id, label) {
            const details = node('details'); details.dataset.disclosure = id;
            details.open = sourceOpen.has(id);
            details.append(node('summary', '', label));
            details.addEventListener('toggle', () => { if (details.isConnected) { if (details.open) sourceOpen.add(id); else sourceOpen.delete(id); } });
            return details;
        }
        function rangeLabel(bounds = context.bounds) {
            const start = isoDate(bounds?.start), end = isoDate(bounds?.end);
            return start && end ? `${dateLabel(start)} — ${dateLabel(end)}` : t('rangeUnknown');
        }
        function cachedRangeLabel() {
            const dates = occurrences.map(item => item.date).filter(Boolean).sort();
            return dates.length ? t('cachedRange', { range: rangeLabel({ start: dates[0], end: dates.at(-1) }) }) : '';
        }
        function checkedLabel(value) {
            const checked = value && new Date(value);
            return checked && !Number.isNaN(checked.getTime()) ? t('checked', {
                time: new Intl.DateTimeFormat(locale(), { timeZone: 'Europe/Moscow', day: 'numeric', month: 'long', year: 'numeric', hour: '2-digit', minute: '2-digit' }).format(checked),
            }) : t('checkedUnknown');
        }
        function updateCourse() {
            const panel = dialog.querySelector('.ld-course-classes');
            const hadFocus = panel.contains(document.activeElement);
            panel.replaceWith(renderCourseClasses());
            if (hadFocus) dialog.querySelector('[data-tab="course"]').focus({ preventScroll: true });
        }
        function updateCurriculum() {
            const panel = dialog.querySelector('.ld-curriculum');
            const hadFocus = panel.contains(document.activeElement);
            panel.replaceWith(renderCurriculum());
            if (hadFocus) dialog.querySelector('[data-tab="course"]').focus({ preventScroll: true });
        }
        async function loadCurriculum() {
            if (closed || curriculumState === 'loading' || curriculumState === 'ready') return;
            const request = curriculumContext(selected, context.entity);
            if (!request) { curriculumState = 'ready'; updateCurriculum(); return; }
            curriculumState = 'loading'; updateCurriculum();
            const controller = new AbortController(); curriculumController = controller;
            const timeout = setTimeout(() => controller.abort(), 12000);
            try {
                const response = await window.ScheduleApi.loadCurriculumData({ ...request, signal: controller.signal });
                if (closed || curriculumController !== controller) return;
                if (controller.signal.aborted) throw new Error('Curriculum request timed out');
                const data = normalizeCurriculum(response, request.group_id);
                if (!data) throw new Error('Invalid curriculum response');
                curriculumData = data; curriculumState = 'ready';
            } catch {
                if (closed || curriculumController !== controller) return;
                curriculumState = 'error';
            } finally {
                clearTimeout(timeout);
                if (!closed && curriculumController === controller) {
                    curriculumController = null; updateCurriculum();
                }
            }
        }
        async function loadCourse() {
            if (closed || cacheState === 'loading' || cacheState === 'ready') return;
            cacheState = 'loading'; updateCourse();
            cacheController = new AbortController();
            const controller = cacheController;
            const timeout = setTimeout(() => controller.abort(), 12000);
            try {
                if (!context.entity?.type || !context.entity?.id) throw new Error('Missing entity');
                const data = await window.ScheduleApi.loadCachedScheduleData({ ...context.entity, signal: controller.signal });
                if (closed) return;
                if (controller.signal.aborted) throw new Error('Cache request timed out');
                if (!Array.isArray(data?.schedule) || data.schedule.some(item => !item || typeof item !== 'object' || Array.isArray(item))) throw new Error('Invalid cached schedule');
                const schedule = context.prepareLesson ? data.schedule.map(context.prepareLesson) : data.schedule;
                occurrences = relatedLessons(original, schedule, context.entity, false);
                cacheSnapshot = data;
                cacheState = 'ready';
            } catch {
                if (closed) return;
                cacheState = 'error';
            } finally {
                clearTimeout(timeout);
                if (cacheController === controller) cacheController = null;
                if (!closed) updateCourse();
            }
        }
        function showTab(next, focusTab = false) {
            tab = next;
            dialog.querySelectorAll('[data-tab]').forEach(el => {
                el.setAttribute('aria-selected', String(el.dataset.tab === tab));
                el.tabIndex = el.dataset.tab === tab ? 0 : -1;
            });
            dialog.querySelector('#lessonDetailsOccurrence').hidden = tab !== 'lesson';
            dialog.querySelector('#lessonDetailsCourse').hidden = tab !== 'course';
            dialog.querySelector('[data-course]').textContent = t(tab === 'lesson' ? 'allClasses' : 'backToLesson');
            dialog.querySelector('.ld-copy').hidden = true;
            if (focusTab) dialog.querySelector(`[data-tab="${tab}"]`).focus({ preventScroll: true });
            if (tab === 'course' && cacheState === 'idle') void loadCourse();
            if (tab === 'course' && curriculumState === 'idle') void loadCurriculum();
        }
        async function navigate(type, id, label) {
            dialog.close(); cleanup();
            await window.openLessonEntitySchedule(type, id, label);
        }
        function copyText() {
            const lines = [selected.title || t('titleMissing'), selected.kind,
                `${dateLabel(selected.date)} · ${timeLabel(selected)} · ${t('moscow')}`];
            for (const [key, value] of [['room', [selected.room, selected.building].filter(Boolean).join(', ')],
                ['teacher', selected.teacher], ['email', selected.emails.join(', ')], ['group', selected.group],
                ['subgroup', selected.subgroup], ['module', selected.module], ['notes', selected.notes]]) {
                if (value) lines.push(`${t(key)}: ${value}`);
            }
            return [...lines, ...selected.links].filter(Boolean).join('\n');
        }
        function sourceDetails() {
            const details = disclosure('source', t('source'));
            const contents = node('div', 'ld-source');
            contents.append(node('span', '', t('university')));
            contents.append(node('span', '', checkedLabel(selectedFromCache ? cacheSnapshot.source_checked_at : context.sourceUpdatedAt)));
            if (selectedFromCache || context.offline || context.freshness === 'stale_fallback') contents.append(node('span', 'ld-warning', t('cached')));
            if (!selectedFromCache && context.refreshing) contents.append(node('span', '', t('refreshing')));
            contents.append(node('span', '', selectedFromCache ? t('allCached') : t('loadedRange', { range: rangeLabel() })));
            details.append(contents);
            return details;
        }
        function renderOccurrence() {
            const body = node('div', 'ld-body'); body.id = 'lessonDetailsOccurrence';
            body.setAttribute('role', 'tabpanel'); body.setAttribute('aria-labelledby', 'lessonDetailsLessonTab');
            body.append(node('div', 'ld-date', dateLabel(selected.date, { weekday: 'long' })));
            const time = node('div'); time.append(node('span', 'ld-time', timeLabel(selected)));
            time.append(node('span', 'ld-duration', [selected.duration ? t('duration', { count: selected.duration }) : '', t('moscow')].filter(Boolean).join(' · ')));
            body.append(time);
            const dl = node('dl');
            row(dl, t('room'), selected.room || t('roomMissing'), selected.building ? node('span', 'ld-small', selected.building) : null);
            const teacher = node('div', '', selected.teacher || t('teacherMissing'));
            selected.emails.forEach(email => { const link = node('a', 'ld-email', email); link.href = `mailto:${email}`; teacher.append(link); });
            row(dl, t('teacher'), teacher);
            if (selected.group) row(dl, t('group'), selected.group);
            if (selected.subgroup) row(dl, t('subgroup'), selected.subgroup);
            if (selected.module) row(dl, t('module'), selected.module);
            if (selected.notes) row(dl, t('notes'), node('span', 'ld-notes', selected.notes));
            if (selected.links.length) {
                const links = node('div', 'ld-links');
                selected.links.forEach((url, index) => links.append(externalLink(t('sourceLink', { count: index + 1 }), url)));
                row(dl, t('links'), links);
            }
            body.append(dl, node('hr', 'ld-divider'), sourceDetails());
            const actions = disclosure('actions', t('actions'));
            const items = node('div', 'ld-extra-actions');
            if (selected.duration) items.append(button(t('ics'), () => window.ScheduleRender.downloadSingleLessonIcs({
                ...selected.raw, date: selected.date, discipline_short: selected.title,
                auditorium: [selected.room, selected.building].filter(Boolean).join(', '), lecturer_title: selected.teacher,
            }, 'lesson')));
            if (selected.teacher || selected.teacherId) items.append(button(t('teacherSchedule'), () => navigate('person', selected.teacherId, selected.teacher)));
            if (selected.room || selected.roomId) items.append(button(t('roomSchedule'), () => navigate('auditorium', selected.roomId, selected.room)));
            if (selected.group || selected.groupId) items.append(button(t('groupSchedule'), () => navigate('group', selected.groupId, selected.group)));
            if (items.children.length) { actions.append(items); body.append(actions); }
            return body;
        }
        function renderCurriculum() {
            const panel = node('section', 'ld-curriculum');
            panel.setAttribute('aria-labelledby', 'lessonDetailsCurriculumTitle');
            const heading = node('h3', '', t('curriculum.heading')); heading.id = 'lessonDetailsCurriculumTitle';
            panel.append(heading);
            const request = curriculumContext(selected, context.entity);
            if (!request) {
                panel.append(node('p', 'ld-curriculum-hint', t('curriculum.noGroup')));
                return panel;
            }
            const status = node('div'); status.setAttribute('role', 'status');
            if (curriculumState !== 'ready') {
                status.append(node('p', 'ld-curriculum-hint', t(curriculumState === 'error' ? 'curriculum.error' : 'curriculum.loading')));
                if (curriculumState === 'error') status.append(button(t('retry'), () => void loadCurriculum()));
                panel.append(status); return panel;
            }
            const data = curriculumData;
            const group = selected.group || text(context.entity?.name) || request.group_id;
            panel.append(node('p', 'ld-curriculum-context', [group, data?.semester ? t('curriculum.semester', { number: data.semester }) : ''].filter(Boolean).join(' · ')));
            if (!data || data.status !== 'confirmed') {
                status.append(node('p', 'ld-curriculum-hint', t(`curriculum.${data?.status || 'unavailable'}`)));
                panel.append(status); return panel;
            }
            panel.classList.add('ld-curriculum-confirmed');
            const current = data.assessments.filter(item => item.semester === data.semester);
            const other = data.assessments.filter(item => item.semester !== data.semester);
            function renderAssessments(items) {
                const terms = new Map();
                items.forEach(item => {
                    if (!terms.has(item.semester)) terms.set(item.semester, []);
                    terms.get(item.semester).push(item);
                });
                const list = node('div', 'ld-assessment-terms');
                [...terms].sort(([a], [b]) => a - b).forEach(([term, records]) => {
                    const block = node('div', 'ld-assessment-term');
                    if (term !== data.semester) block.append(node('p', 'ld-curriculum-context', t('curriculum.semester', { number: term })));
                    const badges = node('div', 'ld-assessment-badges');
                    [...new Set(records.map(item => item.kind))].forEach(kind => badges.append(node('span', 'ld-assessment-kind', t(`curriculum.kind.${kind}`))));
                    block.append(badges);
                    const sources = node('div', 'ld-assessment-sources');
                    const seen = new Set();
                    records.forEach(item => {
                        const key = item.snapshotUrl || item.sourceUrl;
                        if (seen.has(key)) return;
                        seen.add(key);
                        if (item.snapshotUrl) {
                            const copy = externalLink(item.page ? t('curriculum.snapshotPage', { page: item.page }) : t('curriculum.snapshot'), item.snapshotUrl);
                            if (item.sourceTitle) { copy.title = item.sourceTitle; copy.setAttribute('aria-label', `${copy.textContent} · ${item.sourceTitle}`); }
                            sources.append(copy);
                        }
                        const label = item.page ? t('curriculum.sourcePage', { page: item.page }) : t('curriculum.source');
                        const link = externalLink(label, item.sourceUrl);
                        if (item.sourceTitle) { link.title = item.sourceTitle; link.setAttribute('aria-label', `${label} · ${item.sourceTitle}`); }
                        sources.append(link);
                    });
                    block.append(sources); list.append(block);
                });
                return list;
            }
            if (current.length) panel.append(renderAssessments(current));
            else panel.append(node('p', 'ld-curriculum-hint', t('curriculum.noCurrent')));
            panel.append(node('p', 'ld-curriculum-hint', t('curriculum.plannedHint')));
            if (other.length) {
                const details = disclosure('curriculum-other', t('curriculum.otherSemesters'));
                details.append(renderAssessments(other)); panel.append(details);
            }
            const provenance = node('div', 'ld-curriculum-provenance');
            const program = [data.program, data.admissionYear ? t('curriculum.admissionYear', { year: data.admissionYear }) : ''].filter(Boolean).join(' · ');
            if (program) provenance.append(node('span', '', program));
            provenance.append(node('span', '', checkedLabel(data.checkedAt)));
            if (data.stale) provenance.append(node('span', 'ld-warning', t('curriculum.stale')));
            panel.append(provenance);
            return panel;
        }
        function renderCourseClasses() {
            const body = node('div', 'ld-course-classes');
            body.append(node('h3', '', t('courseClasses')));
            body.append(node('p', 'ld-subtitle', [text(context.entity?.name), cacheState === 'ready' ? t('allCached') : t('loadedRange', { range: rangeLabel() })].filter(Boolean).join(' · ')));
            const status = node('div', 'ld-subtitle'); status.setAttribute('role', 'status');
            if (cacheState === 'ready') {
                status.append(node('span', 'ld-small', cachedRangeLabel()), node('span', 'ld-small', checkedLabel(cacheSnapshot.source_checked_at)));
                status.append(node('span', 'ld-small', t('cacheScope')));
            } else {
                status.append(node('p', '', t(cacheState === 'error' ? 'cacheError' : 'cacheLoading')));
                if (cacheState === 'error') status.append(button(t('retry'), () => void loadCourse()));
            }
            body.append(status);
            const counts = new Map();
            occurrences.forEach(item => counts.set(item.kind || t('kindUnknown'), (counts.get(item.kind || t('kindUnknown')) || 0) + 1));
            body.append(node('div', 'ld-count', [t(cacheState === 'ready' ? 'classCount' : 'partialCount', { count: occurrences.length }), [...counts].map(([kind, count]) => `${kind}: ${count}`).join(' · ')].filter(Boolean).join(' · ')));
            if (cacheState === 'ready' && !occurrences.length) body.append(node('p', 'ld-small', t('cacheEmpty')));
            const list = node('div', 'ld-occurrences');
            occurrences.forEach(item => {
                const entry = button('', () => {
                    const changed = JSON.stringify(curriculumContext(selected, context.entity)) !== JSON.stringify(curriculumContext(item, context.entity));
                    if (changed) {
                        curriculumController?.abort(); curriculumController = null;
                        curriculumState = 'idle'; curriculumData = null;
                    }
                    selected = item; selectedFromCache = cacheState === 'ready'; tab = 'lesson'; render();
                    dialog.querySelector('[data-tab="lesson"]').focus({ preventScroll: true });
                }, 'ld-occurrence');
                const date = node('span'); date.append(node('b', '', dateLabel(item.date, { month: 'short', year: undefined })), node('span', 'ld-small', item.date ? dateLabel(item.date, { day: undefined, month: undefined, year: undefined, weekday: 'long' }) : ''));
                if (item.date && item.date.slice(0, 4) !== original.date.slice(0, 4)) date.append(node('span', 'ld-small', item.date.slice(0, 4)));
                const summary = node('span'); summary.append(node('b', '', timeLabel(item)), node('span', 'ld-small', [item.kind, item.room].filter(Boolean).join(' · ')));
                summary.append(node('span', 'ld-small', [item.teacher, item.group, item.subgroup ? `${t('subgroup')}: ${item.subgroup}` : ''].filter(Boolean).join(' · ')));
                if (occurrenceKey(item) === occurrenceKey(selected)) entry.setAttribute('aria-current', 'true');
                const arrow = node('span', 'ld-arrow'); arrow.setAttribute('aria-hidden', 'true');
                arrow.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="m9 5 7 7-7 7" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>';
                entry.append(date, summary, arrow); list.append(entry);
            });
            body.append(list);
            return body;
        }
        function renderCourse() {
            const body = node('div', 'ld-body'); body.id = 'lessonDetailsCourse';
            body.setAttribute('role', 'tabpanel'); body.setAttribute('aria-labelledby', 'lessonDetailsCourseTab');
            body.append(renderCurriculum(), renderCourseClasses());
            return body;
        }
        function render() {
            const position = dialog.scrollTop;
            dialog.replaceChildren();
            const header = node('header', 'ld-header');
            const heading = node('div', 'ld-heading');
            heading.append(node('span', 'ld-kind', selected.kind || t('kindUnknown')));
            const title = node('h2', '', selected.title || t('titleMissing')); title.id = 'lessonDetailsTitle'; heading.append(title);
            const close = button('', () => dialog.close(), 'ld-close'); close.setAttribute('aria-label', t('close')); close.autofocus = true;
            close.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18" stroke-width="1.8" stroke-linecap="round"/></svg>';
            header.append(heading, close);
            const tabs = node('div', 'ld-tabs'); tabs.setAttribute('role', 'tablist'); tabs.setAttribute('aria-label', t('tabs'));
            [['lesson', 'lessonTab', 'lessonDetailsLessonTab', 'lessonDetailsOccurrence'], ['course', 'courseTab', 'lessonDetailsCourseTab', 'lessonDetailsCourse']].forEach(([key, label, id, panelId]) => {
                const tabButton = button(t(label), () => showTab(key), ''); tabButton.id = id; tabButton.dataset.tab = key;
                tabButton.setAttribute('role', 'tab'); tabButton.setAttribute('aria-controls', panelId); tabs.append(tabButton);
            });
            tabs.addEventListener('keydown', event => {
                if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
                event.preventDefault(); showTab(event.key === 'Home' ? 'lesson' : event.key === 'End' ? 'course' : tab === 'lesson' ? 'course' : 'lesson', true);
            });
            const footer = node('footer', 'ld-footer');
            const courseButton = button('', () => showTab(tab === 'lesson' ? 'course' : 'lesson', true), 'ld-button ld-primary'); courseButton.dataset.course = '';
            const copy = node('div', 'ld-copy'); copy.hidden = true;
            const feedback = node('p', 'ld-subtitle'); feedback.setAttribute('role', 'status');
            const area = node('textarea'); area.readOnly = true; area.setAttribute('aria-label', t('copyLabel')); copy.append(feedback, area);
            footer.append(courseButton, button(t('copy'), async () => {
                const value = copyText(); copy.hidden = false; area.value = value;
                try { await navigator.clipboard.writeText(value); if (closed) return; feedback.textContent = t('copied'); area.hidden = true; }
                catch { if (closed) return; feedback.textContent = t('copyFallback'); area.hidden = false; area.focus(); area.select(); }
                copy.scrollIntoView({ block: 'nearest' });
            }));
            dialog.append(header, tabs, renderOccurrence(), renderCourse(), footer, copy);
            showTab(tab); dialog.scrollTop = position;
        }
        function languageChanged() { const focusedTab = document.activeElement?.dataset.tab; render(); (focusedTab ? dialog.querySelector(`[data-tab="${focusedTab}"]`) : dialog.querySelector('.ld-close')).focus({ preventScroll: true }); }
        dialog.addEventListener('close', cleanup, { once: true });
        dialog.addEventListener('keydown', event => {
            event.stopPropagation();
            if (event.key !== 'Tab') return;
            const focusable = [...dialog.querySelectorAll('button,a[href],summary,textarea,[tabindex]')]
                .filter(el => {
                    const closedDetails = el.closest('details:not([open])');
                    return !el.disabled && el.tabIndex >= 0 && el.getClientRects().length > 0
                        && (!closedDetails || el === closedDetails.querySelector('summary'));
                });
            const first = focusable[0], last = focusable.at(-1);
            if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
            else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
        });
        let pressedBackdrop = false;
        dialog.addEventListener('pointerdown', event => { pressedBackdrop = event.target === dialog && outside(event); });
        dialog.addEventListener('click', event => { if (pressedBackdrop && event.target === dialog && outside(event)) dialog.close(); pressedBackdrop = false; });
        function outside(event) { const rect = dialog.getBoundingClientRect(); return event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom; }
        window.addEventListener('mpb-language-change', languageChanged);
        document.body.append(dialog); render();
        document.documentElement.style.overflow = 'hidden';
        dialog.showModal();
        active = { dialog, cleanup };
    }
    window.MpbLessonDetails = { open, normalizeLesson, relatedLessons, curriculumContext, normalizeCurriculum };
})();
