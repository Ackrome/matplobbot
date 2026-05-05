(() => {
    function getBaseUrl() {
        return window.getMpbApiBase ? window.getMpbApiBase() : "/api";
    }

    async function requestJson(url, options = {}) {
        const response = await fetch(url, options);
        let payload = null;
        try {
            payload = await response.json();
        } catch {
            payload = null;
        }
        if (!response.ok) {
            const error = new Error(payload?.detail || response.statusText || "Request failed");
            error.status = response.status;
            error.payload = payload;
            throw error;
        }
        return payload;
    }

    function searchEntities(term, type = "all") {
        const params = new URLSearchParams({
            term: String(term || ""),
            type: String(type || "all"),
        });
        return requestJson(`${getBaseUrl()}/schedule/search?${params.toString()}`);
    }

    function getCachedSchedules() {
        return requestJson(`${getBaseUrl()}/schedule/cached_list`);
    }

    function loadScheduleData({ type, id, baseDate, refresh = false }) {
        const params = new URLSearchParams();
        if (baseDate) params.set("base_date", baseDate);
        if (refresh) params.set("refresh", "1");
        const suffix = params.toString() ? `?${params.toString()}` : "";
        return requestJson(`${getBaseUrl()}/schedule/data/${type}/${encodeURIComponent(id)}${suffix}`);
    }

    window.ScheduleApi = {
        getCachedSchedules,
        loadScheduleData,
        requestJson,
        searchEntities,
    };
})();
