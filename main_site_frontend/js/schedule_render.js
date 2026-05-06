(() => {
    function escapeHtml(value) {
        return String(value ?? "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    function icon(name) {
        const icons = {
            copy: '<path d="M8 8h10v10H8z"></path><path d="M6 16H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>',
            teacher: '<path d="M16 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0z"></path><path d="M4 21a8 8 0 0 1 16 0"></path>',
            room: '<path d="M12 21s7-5.2 7-11a7 7 0 1 0-14 0c0 5.8 7 11 7 11z"></path><path d="M12 10.5h.01"></path>',
            calendar: '<path d="M8 2v4"></path><path d="M16 2v4"></path><path d="M3 10h18"></path><path d="M5 4h14a2 2 0 0 1 2 2v13a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z"></path>',
            module: '<path d="M4 7h16"></path><path d="M4 12h16"></path><path d="M4 17h10"></path>',
            hide: '<path d="M3 3l18 18"></path><path d="M10.6 10.6a2 2 0 0 0 2.8 2.8"></path><path d="M9.9 5.1A10.8 10.8 0 0 1 12 5c6 0 9 7 9 7a13.2 13.2 0 0 1-2.1 3.1"></path><path d="M6.6 6.6C3.8 8.4 2 12 2 12s3 7 10 7a10.8 10.8 0 0 0 4.1-.8"></path>',
            actions: '<path d="M4 7h16"></path><path d="M4 12h10"></path><path d="M4 17h7"></path>',
            more: '<circle cx="5" cy="12" r="1.5"></circle><circle cx="12" cy="12" r="1.5"></circle><circle cx="19" cy="12" r="1.5"></circle>',
            chevron: '<path d="m6 9 6 6 6-6"></path>',
        };
        return `<svg class="h-3.5 w-3.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${icons[name] || icons.copy}</svg>`;
    }

    function renderActionButton(action, lessonId, label, iconName, options = {}) {
        const normalizedOptions = typeof options === "boolean" ? { disabled: options } : options;
        const disabled = Boolean(normalizedOptions.disabled);
        const iconOnly = Boolean(normalizedOptions.iconOnly);
        return `
            <button type="button"
                data-lesson-action="${escapeHtml(action)}"
                data-lesson-id="${escapeHtml(lessonId)}"
                ${disabled ? "disabled" : `onclick="runLessonAction('${action}', '${lessonId}', event)"`}
                title="${escapeHtml(label)}"
                aria-label="${escapeHtml(label)}"
                class="lesson-action-btn inline-flex min-h-8 items-center justify-center gap-1.5 rounded-lg border ${iconOnly ? "px-2.5" : "px-2"} py-1 text-[10px] font-black transition-colors ${disabled
                    ? "cursor-not-allowed border-slate-200 bg-slate-50 text-slate-300 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-600"
                    : "border-slate-200 bg-white text-slate-600 hover:border-blue-200 hover:bg-blue-50 hover:text-blue-700 dark:border-slate-700 dark:bg-slate-900/70 dark:text-slate-300 dark:hover:border-blue-800 dark:hover:bg-blue-950/40 dark:hover:text-blue-200"}">
                ${icon(iconName)}
                ${iconOnly
                    ? `<span class="sr-only">${escapeHtml(label)}</span>`
                    : `<span class="hidden sm:inline">${escapeHtml(label)}</span>`}
            </button>
        `;
    }

    function renderInlineActionOverflow(lessonId, labels, actionItems) {
        if (!actionItems.length) return "";
        const overflowLabel = labels.actionsMore || labels.actionsToggle || "More actions";
        const renderedButtons = actionItems
            .map(([action, label, iconName, disabled]) => renderActionButton(action, lessonId, label, iconName, {
                disabled,
                iconOnly: false,
            }))
            .join("");
        return `
            <details class="lesson-action-overflow">
                <summary class="lesson-action-btn lesson-action-overflow-toggle" title="${escapeHtml(overflowLabel)}" aria-label="${escapeHtml(overflowLabel)}">
                    ${icon("more")}
                    <span class="sr-only">${escapeHtml(overflowLabel)}</span>
                </summary>
                <div class="lesson-action-overflow-menu">
                    ${renderedButtons}
                </div>
            </details>
        `;
    }

    function renderInlineActionLauncher(lessonId, labels, actionItems) {
        if (!actionItems.length) return "";
        const launcherLabel = labels.actionsToggle || "Actions";
        const renderedButtons = actionItems
            .map(([action, label, iconName, disabled]) => renderActionButton(action, lessonId, label, iconName, {
                disabled,
                iconOnly: false,
            }))
            .join("");
        return `
            <div class="lesson-actions-panel lesson-actions-panel--launcher">
                <details class="lesson-action-overflow lesson-action-overflow--launcher">
                    <summary class="lesson-action-btn lesson-action-overflow-toggle" title="${escapeHtml(launcherLabel)}" aria-label="${escapeHtml(launcherLabel)}">
                        ${icon("actions")}
                        <span class="sr-only">${escapeHtml(launcherLabel)}</span>
                    </summary>
                    <div class="lesson-action-overflow-menu lesson-action-overflow-menu--launcher">
                        ${renderedButtons}
                    </div>
                </details>
            </div>
        `;
    }

    function renderLessonActions(lessonId, labels, options = {}) {
        const compact = Boolean(options.compact);
        const inline = Boolean(options.inline);
        const iconOnly = Boolean(options.iconOnly);
        const className = compact
            ? "lesson-actions lesson-actions--compact"
            : "lesson-actions";
        const actionToggleLabel = labels.actionsToggle || "Actions";
        const actionHideLabel = labels.actionsHide || actionToggleLabel;
        const actionItems = [
            ["copyRoom", labels.copyRoom, "copy", !options.hasRoom],
            ["openTeacher", labels.openTeacher, "teacher", !options.hasTeacher],
            ["openRoom", labels.openRoom, "room", !options.hasRoom],
            ["singleIcs", labels.singleIcs, "calendar", false],
            ["onlyModule", labels.onlyModule, "module", !options.hasModule],
            ["hideModule", labels.hideModule, "hide", !options.hasModule],
        ];
        if (inline) {
            const enabledActions = actionItems.filter(([, , , disabled]) => !disabled);
            if (iconOnly) {
                return renderInlineActionLauncher(lessonId, labels, enabledActions);
            }
            const primaryActions = actionItems
                .filter(([action, , , disabled]) => !disabled && ["copyRoom", "openTeacher", "openRoom", "singleIcs"].includes(action))
                .map(([action, label, iconName, disabled]) => renderActionButton(action, lessonId, label, iconName, {
                    disabled,
                    iconOnly,
                }))
                .join("");
            const secondaryActions = actionItems
                .filter(([action, , , disabled]) => !disabled && ["onlyModule", "hideModule"].includes(action));
            const overflowHtml = renderInlineActionOverflow(lessonId, labels, secondaryActions);
            const inlineHtml = `${primaryActions}${overflowHtml}`;
            if (!inlineHtml) return "";
            return `<div class="lesson-actions-panel lesson-actions-panel--inline">${inlineHtml}</div>`;
        }
        const renderedButtons = actionItems
            .map(([action, label, iconName, disabled]) => renderActionButton(action, lessonId, label, iconName, {
                disabled,
                iconOnly,
            }))
            .join("");
        if (!renderedButtons) return "";
        return `
            <details class="${className}">
                <summary class="lesson-actions-toggle" title="${escapeHtml(actionToggleLabel)}">
                    ${icon("actions")}
                    <span class="lesson-actions-closed-label">${escapeHtml(actionToggleLabel)}</span>
                    <span class="lesson-actions-open-label">${escapeHtml(actionHideLabel)}</span>
                    <span class="lesson-actions-chevron">${icon("chevron")}</span>
                </summary>
                <div class="lesson-actions-panel">
                    ${renderedButtons}
                </div>
            </details>
        `;
    }

    function formatIcsDate(dateValue, timeValue) {
        const date = String(dateValue || "").replace(/\./g, "-");
        const [year, month, day] = date.split("-");
        const [hour = "00", minute = "00"] = String(timeValue || "00:00").split(":");
        return `${year}${month}${day}T${hour.padStart(2, "0")}${minute.padStart(2, "0")}00`;
    }

    function escapeIcs(value) {
        return String(value || "")
            .replace(/\\/g, "\\\\")
            .replace(/\n/g, "\\n")
            .replace(/,/g, "\\,")
            .replace(/;/g, "\\;");
    }

    function downloadSingleLessonIcs(lesson, filePrefix = "lesson") {
        const uid = `${Date.now()}-${Math.random().toString(36).slice(2)}@matplobbot`;
        const title = lesson.discipline_short || lesson.discipline_full || lesson.discipline || "Schedule lesson";
        const description = [
            lesson.kindOfWork,
            lesson.module,
            lesson.lecturer_title,
        ].filter(Boolean).join(" | ");
        const ics = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//matplobbot//schedule//EN",
            "CALSCALE:GREGORIAN",
            "METHOD:PUBLISH",
            "BEGIN:VEVENT",
            `UID:${uid}`,
            `DTSTAMP:${new Date().toISOString().replace(/[-:]/g, "").replace(/\.\d{3}Z$/, "Z")}`,
            `DTSTART;TZID=Europe/Moscow:${formatIcsDate(lesson.date, lesson.beginLesson)}`,
            `DTEND;TZID=Europe/Moscow:${formatIcsDate(lesson.date, lesson.endLesson || lesson.beginLesson)}`,
            `SUMMARY:${escapeIcs(title)}`,
            `LOCATION:${escapeIcs(lesson.auditorium || "")}`,
            `DESCRIPTION:${escapeIcs(description)}`,
            "END:VEVENT",
            "END:VCALENDAR",
        ].join("\r\n");
        const blob = new Blob([ics], { type: "text/calendar;charset=utf-8" });
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = `${filePrefix}-${String(lesson.date || "lesson")}.ics`;
        document.body.appendChild(link);
        link.click();
        link.remove();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
    }

    window.ScheduleRender = {
        downloadSingleLessonIcs,
        renderLessonActions,
    };
})();
