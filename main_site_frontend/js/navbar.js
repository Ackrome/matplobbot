const NAV_API_BASE = "https://api.ivantishchenko.ru/api";
const UI_LANG_KEY = "mpb_ui_lang";

const I18N = {
    en: {
        "nav.home": "Home",
        "nav.projects": "Projects",
        "nav.schedule": "Schedule",
        "nav.studio": "Studio",
        "nav.admin": "Admin",
        "nav.signIn": "Sign In",
        "nav.profile": "Profile",
        "nav.logout": "Log out",
        "nav.logoutAccount": "Log out of account",
        "nav.menu": "Toggle menu",
        "lang.en": "EN",
        "lang.ru": "RU",
        "palette.title": "Command Palette",
        "palette.placeholder": "Type a command...",
        "palette.empty": "No commands found",
        "palette.openHelp": "Open shortcut help",
        "palette.toggleLang": "Toggle UI language",
        "palette.refresh": "Refresh current page",
        "help.title": "Keyboard Shortcuts",
        "help.palette": "Open command palette",
        "help.focusSearch": "Focus search field",
        "help.refresh": "Refresh widgets/page",
        "help.nextPage": "Next table page",
        "help.prevPage": "Previous table page",
        "help.close": "Close dialogs",
        "help.open": "Open shortcuts help",
        "help.hint": "Shortcuts work when a text input is not focused."
    },
    ru: {
        "nav.home": "Главная",
        "nav.projects": "Проекты",
        "nav.schedule": "Расписание",
        "nav.studio": "Студия",
        "nav.admin": "Админ",
        "nav.signIn": "Войти",
        "nav.profile": "Профиль",
        "nav.logout": "Выйти",
        "nav.logoutAccount": "Выйти из аккаунта",
        "nav.menu": "Открыть меню",
        "lang.en": "EN",
        "lang.ru": "RU",
        "palette.title": "Палитра команд",
        "palette.placeholder": "Введите команду...",
        "palette.empty": "Команды не найдены",
        "palette.openHelp": "Открыть справку по клавишам",
        "palette.toggleLang": "Переключить язык интерфейса",
        "palette.refresh": "Обновить текущую страницу",
        "help.title": "Горячие клавиши",
        "help.palette": "Открыть палитру команд",
        "help.focusSearch": "Фокус на поле поиска",
        "help.refresh": "Обновить виджеты/страницу",
        "help.nextPage": "Следующая страница таблицы",
        "help.prevPage": "Предыдущая страница таблицы",
        "help.close": "Закрыть диалоги",
        "help.open": "Открыть справку по клавишам",
        "help.hint": "Сочетания работают, если курсор не в поле ввода."
    }
};

const NAV_ITEMS = [
    { href: "/", key: "nav.home" },
    { href: "/#projects", key: "nav.projects" },
    { href: "/schedule", key: "nav.schedule" },
    { href: "/studio", key: "nav.studio" },
    { href: "/stats", key: "nav.admin", adminOnly: true }
];

const navState = {
    lang: "en",
    user: null,
    paletteOpen: false,
    helpOpen: false,
    commandQuery: "",
    selectedCommandIndex: 0
};

function getStoredLanguage() {
    const saved = localStorage.getItem(UI_LANG_KEY);
    if (saved === "ru" || saved === "en") return saved;
    const htmlLang = (document.documentElement.lang || "").toLowerCase();
    return htmlLang.startsWith("ru") ? "ru" : "en";
}

function translate(key, fallback = "", params = {}) {
    const source = I18N[navState.lang] || I18N.en;
    const template = source[key] || I18N.en[key] || fallback || key;
    return template.replace(/\{(\w+)\}/g, (_, param) => String(params[param] ?? ""));
}

function setLanguage(lang, { broadcast = true } = {}) {
    if (lang !== "ru" && lang !== "en") return;
    navState.lang = lang;
    localStorage.setItem(UI_LANG_KEY, lang);
    document.documentElement.lang = lang;
    renderNavbar();
    applyTranslations();
    if (broadcast) {
        window.dispatchEvent(new CustomEvent("mpb-language-change", { detail: { lang } }));
    }
}

function applyTranslations() {
    document.querySelectorAll("[data-i18n]").forEach((element) => {
        const key = element.getAttribute("data-i18n");
        if (!key) return;
        element.textContent = translate(key, element.textContent || "");
    });
    document.querySelectorAll("[data-i18n-placeholder]").forEach((element) => {
        const key = element.getAttribute("data-i18n-placeholder");
        if (!key) return;
        element.setAttribute("placeholder", translate(key, element.getAttribute("placeholder") || ""));
    });
    document.querySelectorAll("[data-i18n-title]").forEach((element) => {
        const key = element.getAttribute("data-i18n-title");
        if (!key) return;
        element.setAttribute("title", translate(key, element.getAttribute("title") || ""));
    });
    document.querySelectorAll("[data-i18n-aria-label]").forEach((element) => {
        const key = element.getAttribute("data-i18n-aria-label");
        if (!key) return;
        element.setAttribute("aria-label", translate(key, element.getAttribute("aria-label") || ""));
    });
}

function normalizePath(path) {
    if (!path) return "/";
    return path.endsWith("/") && path !== "/" ? path.slice(0, -1) : path;
}

function isActiveNavItem(item) {
    const pathname = normalizePath(window.location.pathname);
    if (item.href === "/#projects") {
        return pathname === "/" && window.location.hash === "#projects";
    }
    return pathname === normalizePath(item.href);
}

function escapeHtml(value) {
    return String(value ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
}

function shouldShowNavItem(item) {
    if (!item.adminOnly) return true;
    return navState.user?.role === "admin";
}

function getProfileLink() {
    if (!navState.user) return "/login";
    return navState.user.role === "admin" ? "/stats" : "/schedule";
}

function getAvatarHtml(sizeClass = "w-6 h-6", textClass = "text-xs") {
    const username = (navState.user?.username || "?").trim();
    const initial = username.length > 0 ? username[0].toUpperCase() : "?";
    if (navState.user?.avatar_url) {
        return `<img src="${escapeHtml(navState.user.avatar_url)}" class="${sizeClass} rounded-full object-cover shrink-0 border border-slate-200" alt="${escapeHtml(username)}">`;
    }
    return `<div class="${sizeClass} rounded-full bg-blue-600 text-white flex items-center justify-center ${textClass} font-bold shrink-0">${escapeHtml(initial)}</div>`;
}

function renderDesktopAuth() {
    if (!navState.user) {
        return `
            <a href="/login" class="group relative px-5 py-2.5 bg-slate-900 text-white rounded-full font-medium overflow-hidden shadow-lg shadow-slate-900/20 hover:shadow-slate-900/40 transition-all">
                <span class="relative z-10 flex items-center gap-2">${translate("nav.signIn")}</span>
                <span class="absolute inset-0 bg-gradient-to-r from-blue-600 to-indigo-600 opacity-0 group-hover:opacity-100 transition-opacity duration-300"></span>
            </a>
        `;
    }

    return `
        <a href="${getProfileLink()}" class="flex items-center gap-2 px-4 py-2 rounded-full border border-slate-200 hover:border-blue-400 hover:bg-blue-50 transition-colors max-w-[220px]">
            ${getAvatarHtml("w-6 h-6", "text-xs")}
            <span class="text-sm font-bold text-slate-700 truncate">${escapeHtml(navState.user.username || "")}</span>
        </a>
        <button type="button" data-logout-btn class="text-sm font-medium text-slate-400 hover:text-red-500 transition-colors">${translate("nav.logout")}</button>
    `;
}

function renderMobileAuth() {
    if (!navState.user) {
        return `
            <a href="/login" class="block mt-4 px-3 py-3 rounded-lg text-base font-medium text-center bg-blue-600 text-white hover:bg-blue-700 transition-colors">
                ${translate("nav.signIn")}
            </a>
        `;
    }

    return `
        <div class="mt-4 pt-4 border-t border-slate-100">
            <a href="${getProfileLink()}" class="flex items-center gap-3 px-3 py-3 rounded-lg hover:bg-slate-50 transition-colors">
                ${getAvatarHtml("w-8 h-8", "text-sm")}
                <div class="overflow-hidden">
                    <div class="text-sm font-bold text-slate-900 truncate">${escapeHtml(navState.user.username || "")}</div>
                    <div class="text-xs text-slate-500">${translate("nav.profile")}</div>
                </div>
            </a>
            <button type="button" data-logout-btn class="w-full text-left mt-2 px-3 py-3 rounded-lg text-red-500 font-medium hover:bg-red-50 transition-colors">
                ${translate("nav.logoutAccount")}
            </button>
        </div>
    `;
}

function renderLanguageToggle(isMobile = false) {
    const base = isMobile
        ? "mt-3 w-full flex items-center gap-2 rounded-xl bg-slate-100 p-1"
        : "hidden lg:flex items-center gap-1 rounded-full bg-slate-100 p-1";
    return `
        <div class="${base}">
            <button type="button" data-lang="en" class="js-lang-switch px-3 py-1.5 rounded-full text-xs font-semibold transition-colors ${navState.lang === "en" ? "bg-white text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-700"}">${translate("lang.en")}</button>
            <button type="button" data-lang="ru" class="js-lang-switch px-3 py-1.5 rounded-full text-xs font-semibold transition-colors ${navState.lang === "ru" ? "bg-white text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-700"}">${translate("lang.ru")}</button>
        </div>
    `;
}

function renderNavbar() {
    const desktopRoot = document.getElementById("desktop-nav-links");
    const mobileRoot = document.getElementById("mobile-nav-links");

    const links = NAV_ITEMS.filter(shouldShowNavItem);

    if (desktopRoot) {
        const linksHtml = links
            .map((item) => {
                const active = isActiveNavItem(item);
                const classes = active
                    ? "text-blue-700 bg-blue-50 border border-blue-200"
                    : "text-slate-600 hover:text-blue-600 hover:bg-blue-50 border border-transparent";
                return `<a href="${item.href}" class="px-3 py-2 rounded-xl text-sm font-semibold transition-colors ${classes}">${translate(item.key)}</a>`;
            })
            .join("");

        desktopRoot.innerHTML = `
            ${linksHtml}
            <div id="desktop-auth-container" class="flex items-center gap-3">${renderDesktopAuth()}</div>
            ${renderLanguageToggle(false)}
        `;
    }

    if (mobileRoot) {
        const mobileLinksHtml = links
            .map((item) => {
                const active = isActiveNavItem(item);
                const classes = active
                    ? "text-blue-700 bg-blue-50 border border-blue-200"
                    : "text-slate-700 hover:text-blue-600 hover:bg-blue-50 border border-transparent";
                return `<a href="${item.href}" class="block px-3 py-3 rounded-lg text-base font-medium transition-colors ${classes}">${translate(item.key)}</a>`;
            })
            .join("");

        mobileRoot.innerHTML = `
            ${mobileLinksHtml}
            ${renderLanguageToggle(true)}
            <div id="mobile-auth-container">${renderMobileAuth()}</div>
        `;
    }
}

window.performLogout = function performLogout() {
    localStorage.removeItem("jwt_token");
    window.location.href = "/login";
};

async function checkAuthAndRenderNavbar() {
    const token = localStorage.getItem("jwt_token");
    if (!token) {
        navState.user = null;
        renderNavbar();
        window.dispatchEvent(new CustomEvent("mpb-auth-ready", { detail: { user: null } }));
        return;
    }

    try {
        const response = await fetch(`${NAV_API_BASE}/auth/me`, {
            headers: { Authorization: `Bearer ${token}` }
        });
        if (response.ok) {
            navState.user = await response.json();
        } else {
            navState.user = null;
            localStorage.removeItem("jwt_token");
            if (normalizePath(window.location.pathname) === "/stats") {
                window.location.href = "/login";
            }
        }
    } catch (error) {
        console.error("Auth check failed", error);
        navState.user = null;
    }

    renderNavbar();
    window.dispatchEvent(new CustomEvent("mpb-auth-ready", { detail: { user: navState.user } }));
}

function setupMobileMenu() {
    const button = document.getElementById("mobile-menu-button");
    const menu = document.getElementById("mobile-menu");
    if (!button || !menu) return;

    button.setAttribute("aria-label", translate("nav.menu"));
    button.addEventListener("click", () => {
        menu.classList.toggle("hidden");
    });

    menu.addEventListener("click", (event) => {
        const target = event.target;
        if (target instanceof HTMLElement && target.closest("a")) {
            menu.classList.add("hidden");
        }
    });
}

function setupNavbarScrollBehavior() {
    const navbar = document.getElementById("navbar");
    if (!navbar) return;

    let lastScrollY = window.scrollY;
    let ticking = false;
    const scrollThreshold = 100;

    function updateNavbar() {
        const currentScrollY = window.scrollY;
        if (currentScrollY > scrollThreshold) {
            if (currentScrollY > lastScrollY && currentScrollY > 200) {
                navbar.classList.add("nav-hidden");
                navbar.classList.remove("nav-visible");
            } else {
                navbar.classList.remove("nav-hidden");
                navbar.classList.add("nav-visible");
            }
        } else {
            navbar.classList.remove("nav-hidden");
            navbar.classList.add("nav-visible");
        }

        navbar.classList.toggle("shadow-md", currentScrollY > 20);
        lastScrollY = currentScrollY;
        ticking = false;
    }

    window.addEventListener(
        "scroll",
        () => {
            if (!ticking) {
                window.requestAnimationFrame(updateNavbar);
                ticking = true;
            }
        },
        { passive: true }
    );
}

function getCommandPaletteCommands() {
    const commands = [
        { id: "go-home", label: translate("nav.home"), run: () => (window.location.href = "/") },
        { id: "go-projects", label: translate("nav.projects"), run: () => (window.location.href = "/#projects") },
        { id: "go-schedule", label: translate("nav.schedule"), run: () => (window.location.href = "/schedule") },
        { id: "go-studio", label: translate("nav.studio"), run: () => (window.location.href = "/studio") },
        {
            id: "refresh",
            label: translate("palette.refresh"),
            run: () => window.dispatchEvent(new CustomEvent("mpb-shortcut-refresh"))
        },
        {
            id: "toggle-language",
            label: translate("palette.toggleLang"),
            run: () => setLanguage(navState.lang === "ru" ? "en" : "ru")
        },
        {
            id: "open-help",
            label: translate("palette.openHelp"),
            run: () => toggleShortcutHelp(true)
        }
    ];

    if (navState.user?.role === "admin") {
        commands.splice(4, 0, {
            id: "go-admin",
            label: translate("nav.admin"),
            run: () => (window.location.href = "/stats")
        });
    }

    return commands;
}

function ensureOverlays() {
    if (document.getElementById("mpbCommandPalette")) return;

    const overlays = document.createElement("div");
    overlays.innerHTML = `
        <div id="mpbCommandPalette" class="hidden fixed inset-0 z-[120] bg-slate-900/50 backdrop-blur-sm px-4">
            <div class="mx-auto mt-20 w-full max-w-2xl rounded-2xl border border-slate-200 bg-white shadow-2xl">
                <div class="border-b border-slate-100 p-4">
                    <p class="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500" data-i18n="palette.title"></p>
                    <input id="mpbCommandInput" type="text" class="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-blue-500" data-i18n-placeholder="palette.placeholder" placeholder="">
                </div>
                <div id="mpbCommandList" class="max-h-[22rem] overflow-y-auto p-2"></div>
            </div>
        </div>
        <div id="mpbShortcutHelp" class="hidden fixed inset-0 z-[120] bg-slate-900/50 backdrop-blur-sm px-4">
            <div class="mx-auto mt-24 w-full max-w-xl rounded-2xl border border-slate-200 bg-white shadow-2xl">
                <div class="flex items-center justify-between border-b border-slate-100 px-5 py-4">
                    <h2 class="text-lg font-bold text-slate-900" data-i18n="help.title"></h2>
                    <button type="button" data-close-help class="rounded-lg px-3 py-1 text-sm text-slate-500 hover:bg-slate-100">Esc</button>
                </div>
                <div class="space-y-3 px-5 py-4 text-sm text-slate-700">
                    <div class="flex items-center justify-between"><span data-i18n="help.palette"></span><kbd class="rounded bg-slate-100 px-2 py-1 text-xs">Ctrl/Cmd + K</kbd></div>
                    <div class="flex items-center justify-between"><span data-i18n="help.focusSearch"></span><kbd class="rounded bg-slate-100 px-2 py-1 text-xs">/</kbd></div>
                    <div class="flex items-center justify-between"><span data-i18n="help.refresh"></span><kbd class="rounded bg-slate-100 px-2 py-1 text-xs">R</kbd></div>
                    <div class="flex items-center justify-between"><span data-i18n="help.nextPage"></span><kbd class="rounded bg-slate-100 px-2 py-1 text-xs">N</kbd></div>
                    <div class="flex items-center justify-between"><span data-i18n="help.prevPage"></span><kbd class="rounded bg-slate-100 px-2 py-1 text-xs">P</kbd></div>
                    <div class="flex items-center justify-between"><span data-i18n="help.open"></span><kbd class="rounded bg-slate-100 px-2 py-1 text-xs">?</kbd></div>
                    <div class="flex items-center justify-between"><span data-i18n="help.close"></span><kbd class="rounded bg-slate-100 px-2 py-1 text-xs">Esc</kbd></div>
                    <p class="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-500" data-i18n="help.hint"></p>
                </div>
            </div>
        </div>
    `;
    document.body.appendChild(overlays);
    applyTranslations();
}

function getVisibleCommands() {
    const query = navState.commandQuery.trim().toLowerCase();
    const commands = getCommandPaletteCommands();
    if (!query) return commands;
    return commands.filter((command) => command.label.toLowerCase().includes(query));
}

function renderCommandList() {
    const list = document.getElementById("mpbCommandList");
    if (!list) return;

    const commands = getVisibleCommands();
    navState.selectedCommandIndex = Math.min(navState.selectedCommandIndex, Math.max(commands.length - 1, 0));

    if (commands.length === 0) {
        list.innerHTML = `<div class="rounded-xl px-3 py-3 text-sm text-slate-500">${translate("palette.empty")}</div>`;
        return;
    }

    list.innerHTML = commands
        .map((command, index) => {
            const selected = index === navState.selectedCommandIndex;
            return `
                <button type="button" data-command-id="${command.id}" class="w-full rounded-xl px-3 py-2 text-left text-sm transition-colors ${selected ? "bg-blue-50 text-blue-700" : "text-slate-700 hover:bg-slate-100"}">
                    ${escapeHtml(command.label)}
                </button>
            `;
        })
        .join("");
}

function openCommandPalette() {
    ensureOverlays();
    const palette = document.getElementById("mpbCommandPalette");
    const input = document.getElementById("mpbCommandInput");
    if (!palette || !input) return;

    navState.paletteOpen = true;
    navState.commandQuery = "";
    navState.selectedCommandIndex = 0;
    palette.classList.remove("hidden");
    input.value = "";
    renderCommandList();
    window.setTimeout(() => input.focus(), 20);
}

function closeCommandPalette() {
    const palette = document.getElementById("mpbCommandPalette");
    if (!palette) return;
    navState.paletteOpen = false;
    palette.classList.add("hidden");
}

function runSelectedCommand() {
    const commands = getVisibleCommands();
    if (commands.length === 0) return;
    const selected = commands[navState.selectedCommandIndex] || commands[0];
    if (!selected) return;
    closeCommandPalette();
    selected.run();
}

function toggleShortcutHelp(forceOpen) {
    ensureOverlays();
    const modal = document.getElementById("mpbShortcutHelp");
    if (!modal) return;

    const shouldOpen = typeof forceOpen === "boolean" ? forceOpen : !navState.helpOpen;
    navState.helpOpen = shouldOpen;
    modal.classList.toggle("hidden", !shouldOpen);
}

function focusPrimarySearch() {
    const target = document.querySelector(
        '[data-search-input], #groupSearch, #leaderboardSearch, input[type="search"]'
    );
    if (!(target instanceof HTMLElement)) return;
    target.focus();
    if (target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement) {
        target.select?.();
    }
}

function registerGlobalHandlers() {
    document.body.addEventListener("click", (event) => {
        const target = event.target;
        if (!(target instanceof HTMLElement)) return;

        const langButton = target.closest(".js-lang-switch");
        if (langButton instanceof HTMLElement) {
            const lang = langButton.getAttribute("data-lang");
            if (lang) setLanguage(lang);
            return;
        }

        if (target.closest("[data-logout-btn]")) {
            window.performLogout();
            return;
        }

        const commandButton = target.closest("[data-command-id]");
        if (commandButton instanceof HTMLElement) {
            const commandId = commandButton.getAttribute("data-command-id");
            const command = getVisibleCommands().find((entry) => entry.id === commandId);
            if (command) {
                closeCommandPalette();
                command.run();
            }
            return;
        }

        if (target.closest("[data-close-help]")) {
            toggleShortcutHelp(false);
        }
    });

    document.addEventListener("keydown", (event) => {
        const isMetaK = (event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k";
        if (isMetaK) {
            event.preventDefault();
            if (navState.paletteOpen) {
                closeCommandPalette();
            } else {
                openCommandPalette();
            }
            return;
        }

        const activeTag = document.activeElement?.tagName || "";
        const isTypingContext =
            activeTag === "INPUT" ||
            activeTag === "TEXTAREA" ||
            document.activeElement?.getAttribute("contenteditable") === "true";

        if (navState.paletteOpen) {
            if (event.key === "Escape") {
                closeCommandPalette();
                return;
            }
            if (event.key === "ArrowDown") {
                event.preventDefault();
                const commands = getVisibleCommands();
                if (commands.length > 0) {
                    navState.selectedCommandIndex = Math.min(navState.selectedCommandIndex + 1, commands.length - 1);
                    renderCommandList();
                }
                return;
            }
            if (event.key === "ArrowUp") {
                event.preventDefault();
                navState.selectedCommandIndex = Math.max(navState.selectedCommandIndex - 1, 0);
                renderCommandList();
                return;
            }
            if (event.key === "Enter") {
                event.preventDefault();
                runSelectedCommand();
                return;
            }
        }

        if (event.key === "Escape") {
            const mobileMenu = document.getElementById("mobile-menu");
            if (mobileMenu && !mobileMenu.classList.contains("hidden")) {
                mobileMenu.classList.add("hidden");
            }
            toggleShortcutHelp(false);
            closeCommandPalette();
            return;
        }

        if (isTypingContext) return;

        if (event.key === "?" || (event.key === "/" && event.shiftKey)) {
            event.preventDefault();
            toggleShortcutHelp(true);
            return;
        }

        if (event.key === "/") {
            event.preventDefault();
            focusPrimarySearch();
            return;
        }

        if (event.key.toLowerCase() === "r") {
            window.dispatchEvent(new CustomEvent("mpb-shortcut-refresh"));
            return;
        }

        if (event.key.toLowerCase() === "n") {
            window.dispatchEvent(new CustomEvent("mpb-shortcut-pagination", { detail: { direction: "next" } }));
            return;
        }

        if (event.key.toLowerCase() === "p") {
            window.dispatchEvent(new CustomEvent("mpb-shortcut-pagination", { detail: { direction: "prev" } }));
        }
    });

    document.addEventListener("input", (event) => {
        const input = document.getElementById("mpbCommandInput");
        if (!input) return;
        if (event.target === input) {
            navState.commandQuery = input.value;
            navState.selectedCommandIndex = 0;
            renderCommandList();
        }
    });
}

function exposePublicI18nApi() {
    window.mpbI18n = {
        getLanguage: () => navState.lang,
        setLanguage: (lang) => setLanguage(lang),
        t: (key, fallback = "", params = {}) => translate(key, fallback, params),
        applyTranslations
    };
}

document.addEventListener("DOMContentLoaded", () => {
    navState.lang = getStoredLanguage();
    document.documentElement.lang = navState.lang;
    exposePublicI18nApi();

    setupMobileMenu();
    setupNavbarScrollBehavior();
    registerGlobalHandlers();
    checkAuthAndRenderNavbar();
    ensureOverlays();
    applyTranslations();
});
