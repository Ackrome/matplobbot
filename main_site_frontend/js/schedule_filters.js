(() => {
    function getWeekEnd(weekStart) {
        const weekEnd = new Date(weekStart);
        weekEnd.setDate(weekEnd.getDate() + 6);
        return weekEnd;
    }

    function isLessonInPeriod(lesson, weekStart, parseDate) {
        const lessonDate = parseDate(lesson?.date || "");
        const weekEnd = getWeekEnd(weekStart);
        return lessonDate >= weekStart && lessonDate <= weekEnd;
    }

    function isLessonVisible(lesson, options) {
        if (!lesson) return false;
        if (!isLessonInPeriod(lesson, options.weekStart, options.parseDate)) return false;
        if (options.lessonMode === "exams_only" && !options.isExamLikeKind(lesson.kindOfWork)) return false;
        if (options.includeModuleFilter !== false && lesson.module && !options.selectedModules.has(lesson.module)) return false;
        return true;
    }

    window.ScheduleFilters = {
        getWeekEnd,
        isLessonInPeriod,
        isLessonVisible,
    };
})();
