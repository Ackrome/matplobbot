(() => {
    const RECENT_KEY = "mpb_schedule_recent_entities";
    const FAVORITES_KEY = "mpb_schedule_favorite_entities";
    const MAX_RECENT = 10;
    const MAX_FAVORITES = 30;
    const ENTITY_TYPES = new Set(["group", "person", "auditorium"]);

    function normalizeModules(value) {
        if (!Array.isArray(value)) return null;
        return Array.from(new Set(value.map((module) => String(module).trim()).filter(Boolean)));
    }

    function normalizeEntity(entity) {
        const type = ENTITY_TYPES.has(String(entity?.type || "").toLowerCase())
            ? String(entity.type).toLowerCase()
            : null;
        const id = entity?.id === undefined || entity?.id === null ? null : String(entity.id);
        const label = entity?.label ?? entity?.name ?? entity?.entity_name ?? id;
        const name = label === undefined || label === null ? null : String(label);
        if (!type || !id) return null;
        const modules = normalizeModules(entity?.modules ?? entity?.selectedModules);
        const normalized = {
            type,
            id,
            label: name || id,
            name: name || id,
            description: entity?.description ? String(entity.description) : "",
            is_offline: Boolean(entity?.is_offline),
            updated_at: entity?.updated_at || entity?.opened_at || null,
        };
        if (modules !== null) normalized.modules = modules;
        return normalized;
    }

    function entityKey(entity) {
        const normalized = normalizeEntity(entity);
        return normalized ? `${normalized.type}:${normalized.id}` : "";
    }

    function readList(key) {
        try {
            const payload = JSON.parse(localStorage.getItem(key) || "[]");
            return Array.isArray(payload)
                ? payload.map(normalizeEntity).filter(Boolean)
                : [];
        } catch {
            return [];
        }
    }

    function writeList(key, list, limit) {
        const normalized = [];
        const seen = new Set();
        (Array.isArray(list) ? list : []).forEach((item) => {
            const entity = normalizeEntity(item);
            const keyValue = entityKey(entity);
            if (!entity || !keyValue || seen.has(keyValue)) return;
            seen.add(keyValue);
            normalized.push(entity);
        });
        localStorage.setItem(key, JSON.stringify(normalized.slice(0, limit)));
        return normalized.slice(0, limit);
    }

    function getRecent() {
        return readList(RECENT_KEY);
    }

    function getFavorites() {
        return readList(FAVORITES_KEY);
    }

    function addRecent(entity) {
        const normalized = normalizeEntity(entity);
        if (!normalized) return getRecent();
        const keyValue = entityKey(normalized);
        const next = [
            { ...normalized, opened_at: new Date().toISOString() },
            ...getRecent().filter((item) => entityKey(item) !== keyValue),
        ];
        return writeList(RECENT_KEY, next, MAX_RECENT);
    }

    function isFavorite(entity) {
        const keyValue = entityKey(entity);
        return Boolean(keyValue && getFavorites().some((item) => entityKey(item) === keyValue));
    }

    function getFavorite(entity) {
        const keyValue = entityKey(entity);
        return keyValue ? getFavorites().find((item) => entityKey(item) === keyValue) || null : null;
    }

    function toggleFavorite(entity) {
        const normalized = normalizeEntity(entity);
        if (!normalized) return { active: false, items: getFavorites() };
        const keyValue = entityKey(normalized);
        const favorites = getFavorites();
        const active = !favorites.some((item) => entityKey(item) === keyValue);
        const next = active
            ? [{ ...normalized, favorited_at: new Date().toISOString() }, ...favorites]
            : favorites.filter((item) => entityKey(item) !== keyValue);
        return { active, items: writeList(FAVORITES_KEY, next, MAX_FAVORITES) };
    }

    function updateFavorite(entity, patch = {}) {
        const favorites = getFavorites();
        const keyValue = entityKey(entity);
        const existing = favorites.find((item) => entityKey(item) === keyValue);
        if (!existing) return { active: false, items: favorites };
        const normalized = normalizeEntity({ ...existing, ...entity, ...patch });
        if (!normalized) return { active: false, items: favorites };
        const next = [
            {
                ...existing,
                ...normalized,
                favorited_at: existing.favorited_at || new Date().toISOString(),
                updated_at: new Date().toISOString(),
            },
            ...favorites.filter((item) => entityKey(item) !== keyValue),
        ];
        return { active: true, items: writeList(FAVORITES_KEY, next, MAX_FAVORITES) };
    }

    function levenshtein(a, b) {
        const left = String(a || "").toLowerCase();
        const right = String(b || "").toLowerCase();
        if (!left) return right.length;
        if (!right) return left.length;
        const row = Array.from({ length: right.length + 1 }, (_, index) => index);
        for (let i = 1; i <= left.length; i += 1) {
            let prev = row[0];
            row[0] = i;
            for (let j = 1; j <= right.length; j += 1) {
                const temp = row[j];
                row[j] = Math.min(
                    row[j] + 1,
                    row[j - 1] + 1,
                    prev + (left[i - 1] === right[j - 1] ? 0 : 1)
                );
                prev = temp;
            }
        }
        return row[right.length];
    }

    function fuzzyScore(query, entity) {
        const normalizedQuery = String(query || "").trim().toLowerCase();
        if (!normalizedQuery) return 1;
        const haystack = [
            entity?.label,
            entity?.name,
            entity?.description,
            entity?.id,
        ].filter(Boolean).join(" ").toLowerCase();
        if (!haystack) return 0;
        if (haystack.includes(normalizedQuery)) return 1;
        const tokens = haystack.split(/\s+/).filter(Boolean);
        let bestDistance = Infinity;
        tokens.forEach((token) => {
            bestDistance = Math.min(bestDistance, levenshtein(normalizedQuery, token));
        });
        const threshold = normalizedQuery.length <= 4 ? 1 : 2;
        if (bestDistance <= threshold) return 0.75;
        let cursor = 0;
        for (const char of haystack) {
            if (char === normalizedQuery[cursor]) cursor += 1;
            if (cursor >= normalizedQuery.length) return 0.45;
        }
        return 0;
    }

    function mergeEntities(lists) {
        const merged = [];
        const seen = new Set();
        lists.flat().forEach((item) => {
            const normalized = normalizeEntity(item);
            const keyValue = entityKey(normalized);
            if (!normalized || !keyValue || seen.has(keyValue)) return;
            seen.add(keyValue);
            merged.push(normalized);
        });
        return merged;
    }

    function filterLocalEntities(query, items, type = "all") {
        return (Array.isArray(items) ? items : [])
            .map(normalizeEntity)
            .filter(Boolean)
            .filter((item) => type === "all" || item.type === type)
            .map((item) => ({ item, score: fuzzyScore(query, item) }))
            .filter(({ score }) => score > 0)
            .sort((a, b) => b.score - a.score || a.item.label.localeCompare(b.item.label))
            .map(({ item }) => item);
    }

    window.ScheduleState = {
        addRecent,
        entityKey,
        filterLocalEntities,
        getFavorite,
        getFavorites,
        getRecent,
        isFavorite,
        mergeEntities,
        normalizeEntity,
        toggleFavorite,
        updateFavorite,
    };
})();
