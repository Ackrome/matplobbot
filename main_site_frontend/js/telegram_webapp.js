(function telegramWebAppAdapter() {
    const webApp = window.Telegram?.WebApp;
    const params = new URLSearchParams(window.location.search);
    const isTelegramLaunch = Boolean(
        webApp && (webApp.initData || params.get("tg") === "1" || params.has("tgWebAppStartParam"))
    );
    const apiBase = window.getMpbApiBase ? window.getMpbApiBase() : "/api";

    window.mpbTelegramWebApp = {
        isActive: isTelegramLaunch,
        webApp: webApp || null,
    };

    function setCssVar(name, value) {
        if (value) document.documentElement.style.setProperty(name, value);
    }

    function applyTelegramTheme() {
        if (!webApp) return;
        const theme = webApp.themeParams || {};
        setCssVar("--tg-theme-bg-color", theme.bg_color);
        setCssVar("--tg-theme-text-color", theme.text_color);
        setCssVar("--tg-theme-hint-color", theme.hint_color);
        setCssVar("--tg-theme-link-color", theme.link_color);
        setCssVar("--tg-theme-button-color", theme.button_color);
        setCssVar("--tg-theme-button-text-color", theme.button_text_color);
        setCssVar("--tg-theme-secondary-bg-color", theme.secondary_bg_color);
        document.documentElement.classList.toggle("dark", webApp.colorScheme === "dark");
        document.documentElement.dataset.theme = webApp.colorScheme === "dark" ? "dark" : "light";
    }

    async function exchangeInitData() {
        if (!isTelegramLaunch || !webApp?.initData) return null;

        const response = await fetch(`${apiBase}/auth/telegram/webapp`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ init_data: webApp.initData }),
        });
        if (!response.ok) {
            throw new Error("Telegram Mini App auth failed");
        }

        const data = await response.json();
        localStorage.setItem("jwt_token", data.access_token);
        window.dispatchEvent(new CustomEvent("mpb-auth-token-changed"));
        return data.access_token;
    }

    window.mpbTelegramAuthReady = exchangeInitData().catch((error) => {
        console.warn(error);
        return null;
    });

    if (!isTelegramLaunch || !webApp) return;

    document.documentElement.classList.add("tg-webapp");
    document.addEventListener("DOMContentLoaded", () => {
        document.body?.classList.add("tg-webapp-body");
    });

    try {
        applyTelegramTheme();
        webApp.ready();
        webApp.expand();
        webApp.setHeaderColor?.("secondary_bg_color");
        webApp.setBackgroundColor?.(webApp.themeParams?.bg_color || "#ffffff");
        webApp.onEvent?.("themeChanged", applyTelegramTheme);
        webApp.BackButton?.onClick(() => {
            if (window.history.length > 1) {
                window.history.back();
            } else {
                webApp.close();
            }
        });
        webApp.BackButton?.show();
    } catch (error) {
        console.warn("Telegram WebApp initialization failed", error);
    }
})();
