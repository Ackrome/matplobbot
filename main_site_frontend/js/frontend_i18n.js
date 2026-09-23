(() => {
    const STORAGE_KEY = "mpb_ui_lang";
    const SUPPORTED_LANGUAGES = new Set(["en", "ru"]);
    const dictionaries = { en: {}, ru: {} };
    const translators = new Set();

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
        const activeDictionary = dictionaries[language] || dictionaries.en;
        const template = activeDictionary[key] || dictionaries.en[key] || fallback || key;
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
        const response = await fetch(`/locales/${locale}.json`, { cache: "no-cache" });
        if (!response.ok) {
            throw new Error(`Locale ${locale} failed with HTTP ${response.status}`);
        }
        const payload = await response.json();
        if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
            throw new Error(`Locale ${locale} is not a JSON object`);
        }
        dictionaries[locale] = payload;
    }

    const ready = Promise.all([...SUPPORTED_LANGUAGES].map(loadDictionary))
        .catch((error) => {
            console.error("Frontend locales failed to load", error);
        })
        .then(() => {
            document.documentElement.lang = language;
            notifyTranslators();
        });

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
