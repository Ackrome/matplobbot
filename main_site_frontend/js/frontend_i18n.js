(() => {
    const STORAGE_KEY = "mpb_ui_lang";
    // Keep the dictionary revision in sync with the service-worker precache.
    const LOCALE_VERSION = "20261122-1";
    const SUPPORTED_LANGUAGES = new Set(["en", "ru"]);
    const dictionaries = {};
    const translators = new Set();
    const transientStatuses = new Set([408, 429, 500, 502, 503, 504]);
    const retryDelays = [120, 350];
    // This small status remains readable even when neither locale file can be fetched.
    const boot = {
        en: { loading: "Loading translations…", unavailable: "Translations are unavailable. Check your connection and try again.", retry: "Retry", close: "Close", session: "Assessments" },
        ru: { loading: "Загружаем переводы…", unavailable: "Переводы недоступны. Проверьте подключение и повторите попытку.", retry: "Повторить", close: "Закрыть", session: "Сессия" },
    };
    let pending = null;

    function detectLanguage() {
        const saved = localStorage.getItem(STORAGE_KEY);
        if (SUPPORTED_LANGUAGES.has(saved)) return saved;
        const htmlLanguage = String(document.documentElement.lang || "").toLowerCase();
        return htmlLanguage.startsWith("ru") ? "ru" : "en";
    }

    let language = detectLanguage();

    function interpolate(template, params = {}) {
        return String(template || "").replace(
            /\{(\w+)\}/g,
            (_, key) => String(params[key] ?? ""),
        );
    }

    function translate(key, fallback = "", params = {}) {
        const template = dictionaries[language]?.[key] || dictionaries.en?.[key] || dictionaries.ru?.[key] || fallback || key;
        return interpolate(template, params);
    }

    function notifyTranslators() {
        translators.forEach((translator) => {
            try {
                translator(language, translate);
            } catch (error) {
                console.warn("Frontend translator failed", error);
            }
        });
    }

    async function loadDictionary(locale) {
        for (let attempt = 0; ; attempt++) {
            try {
                const signal = globalThis.AbortSignal?.timeout?.(2800);
                const response = await fetch(`/locales/${locale}.json?v=${LOCALE_VERSION}`, { cache: "no-cache", signal });
                if (!response.ok) {
                    throw Object.assign(new Error(`Locale ${locale} failed with HTTP ${response.status}`),
                        { temporary: transientStatuses.has(response.status) });
                }
                const payload = await response.json();
                if (!payload || typeof payload !== "object" || Array.isArray(payload) || !Object.keys(payload).length) {
                    throw new Error(`Locale ${locale} is not a nonempty JSON object`);
                }
                dictionaries[locale] = payload;
                return;
            } catch (error) {
                if (attempt >= retryDelays.length || !(error.temporary || ["TypeError", "TimeoutError"].includes(error.name))) throw error;
                await new Promise(resolve => setTimeout(resolve, retryDelays[attempt]));
            }
        }
    }

    function retry() {
        if (pending) return pending;
        const missing = [...SUPPORTED_LANGUAGES].filter(locale => !dictionaries[locale]);
        if (!missing.length) return Promise.resolve();
        pending = Promise.allSettled(missing.map(loadDictionary)).then(results => {
            pending = null;
            results.filter(result => result.status === "rejected").forEach(result => {
                console.error("Frontend locale failed to load", result.reason);
            });
            document.documentElement.lang = language;
            notifyTranslators();
            window.dispatchEvent(new CustomEvent("mpb-locales-ready"));
        });
        return pending;
    }

    const ready = retry();
    window.addEventListener?.("online", retry);

    function setLanguage(nextLanguage, { broadcast = true } = {}) {
        if (!SUPPORTED_LANGUAGES.has(nextLanguage)) return false;
        language = nextLanguage;
        localStorage.setItem(STORAGE_KEY, nextLanguage);
        document.documentElement.lang = nextLanguage;
        notifyTranslators();
        if (broadcast) {
            window.dispatchEvent(
                new CustomEvent("mpb-language-change", { detail: { lang: nextLanguage } }),
            );
        }
        return true;
    }

    window.mpbI18n = {
        ready,
        retry,
        available: () => Boolean(dictionaries.en || dictionaries.ru),
        bootText: key => boot[language][key],
        getLanguage: () => language,
        setLanguage,
        t: translate,
        registerTranslator: (translator) => {
            if (typeof translator !== "function") return () => {};
            translators.add(translator);
            try {
                translator(language, translate);
            } catch (error) {
                console.warn("Frontend translator registration failed", error);
            }
            return () => translators.delete(translator);
        },
        unregisterTranslator: (translator) => translators.delete(translator),
    };
})();
