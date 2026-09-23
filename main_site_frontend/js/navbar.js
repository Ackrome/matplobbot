(() => {
const NAV_API_BASE = window.getMpbApiBase ? window.getMpbApiBase() : "/api";
const NAV_ITEMS =[
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
    selectedCommandIndex: 0,
    activeSection: ""
};
function isDarkTheme() {
    return document.documentElement.classList.contains("dark");
}
function getThemeIcon(isDark = isDarkTheme()) {
    return isDark
        ? `<svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" aria-hidden="true"><path d="M21 12.8A8.5 8.5 0 1111.2 3a6.5 6.5 0 009.8 9.8z" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>`
        : `<svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" aria-hidden="true"><path d="M12 3v2m0 14v2m9-9h-2M5 12H3m15.36-6.36l-1.42 1.42M7.06 16.94l-1.42 1.42m12.72 0l-1.42-1.42M7.06 7.06L5.64 5.64M16 12a4 4 0 11-8 0 4 4 0 018 0z" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
}
function refreshThemeToggleButtons() {
    const icon = getThemeIcon();
    document.querySelectorAll("[data-theme-toggle]").forEach((button) => {
        button.innerHTML = icon;
        button.setAttribute("aria-label", translate("palette.toggleTheme"));
        button.setAttribute("title", translate("palette.toggleTheme"));
    });
}
function setTheme(isDark) {
    document.documentElement.classList.toggle("dark", isDark);
    document.documentElement.dataset.theme = isDark ? "dark" : "light";
    localStorage.setItem("theme", isDark ? "dark" : "light");
    refreshThemeToggleButtons();
    window.dispatchEvent(new CustomEvent("mpb-theme-change", { detail: { isDark } }));
}
function toggleTheme() {
    setTheme(!isDarkTheme());
}
function translate(key, fallback = "", params = {}) {
    return window.mpbI18n?.t?.(key, fallback, params) || fallback || key;
}
function setLanguage(lang) {
    window.mpbI18n?.setLanguage?.(lang);
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
    if (item.href === "/") {
        return pathname === "/" && window.location.hash !== "#projects" && navState.activeSection !== "projects";
    }
    if (item.href === "/#projects") {
        return pathname === "/" && (window.location.hash === "#projects" || navState.activeSection === "projects");
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
        return `<img src="${escapeHtml(navState.user.avatar_url)}" class="${sizeClass} rounded-full object-cover shrink-0 border border-slate-200 dark:border-slate-700" alt="${escapeHtml(username)}">`;
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
        <a href="${getProfileLink()}" class="flex items-center gap-2 px-4 py-2 rounded-full border border-slate-200 hover:border-blue-400 hover:bg-blue-50 transition-colors max-w-[220px] dark:border-slate-700 dark:hover:bg-slate-800 dark:hover:border-blue-500">
            ${getAvatarHtml("w-6 h-6", "text-xs")}
            <span class="text-sm font-bold text-slate-700 truncate dark:text-slate-200">${escapeHtml(navState.user.username || "")}</span>
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
        <div class="mt-4 pt-4 border-t border-slate-100 dark:border-slate-800">
            <a href="${getProfileLink()}" class="flex items-center gap-3 px-3 py-3 rounded-lg hover:bg-slate-50 transition-colors dark:hover:bg-slate-800">
                ${getAvatarHtml("w-8 h-8", "text-sm")}
                <div class="overflow-hidden">
                    <div class="text-sm font-bold text-slate-900 truncate dark:text-slate-100">${escapeHtml(navState.user.username || "")}</div>
                    <div class="text-xs text-slate-500 dark:text-slate-400">${translate("nav.profile")}</div>
                </div>
            </a>
            <button type="button" data-logout-btn class="w-full text-left mt-2 px-3 py-3 rounded-lg text-red-500 font-medium hover:bg-red-50 transition-colors dark:text-red-300 dark:hover:bg-red-950/40">
                ${translate("nav.logoutAccount")}
            </button>
        </div>
    `;
}
function renderLanguageToggle(isMobile = false) {
    const base = isMobile
        ? "mt-3 w-full flex items-center gap-2 rounded-xl bg-slate-100 p-1 dark:bg-slate-800"
        : "hidden lg:flex items-center gap-1 rounded-full bg-slate-100 p-1 dark:bg-slate-800";
    return `
        <div class="${base}">
            <button type="button" data-lang="en" aria-pressed="${navState.lang === "en"}" class="js-lang-switch px-3 py-1.5 rounded-full text-xs font-semibold transition-colors ${navState.lang === "en" ? "bg-white text-slate-900 shadow-sm dark:bg-slate-700 dark:text-slate-100" : "text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200"}">${translate("lang.en")}</button>
            <button type="button" data-lang="ru" aria-pressed="${navState.lang === "ru"}" class="js-lang-switch px-3 py-1.5 rounded-full text-xs font-semibold transition-colors ${navState.lang === "ru" ? "bg-white text-slate-900 shadow-sm dark:bg-slate-700 dark:text-slate-100" : "text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200"}">${translate("lang.ru")}</button>
        </div>
    `;
}
function renderThemeToggle(isMobile = false) {
    const buttonId = isMobile ? "theme-toggle-btn-mobile" : "theme-toggle-btn";
    const base = isMobile
        ? "mt-3 flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-slate-200 bg-white text-slate-600 transition-colors hover:bg-slate-50 hover:text-blue-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700 dark:hover:text-blue-300"
        : "hidden lg:inline-flex h-9 w-9 items-center justify-center rounded-full border border-slate-200 bg-white text-slate-600 transition-colors hover:bg-slate-50 hover:text-blue-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700 dark:hover:text-blue-300";
    return `
        <button id="${buttonId}" type="button" data-theme-toggle aria-label="${translate("palette.toggleTheme")}" title="${translate("palette.toggleTheme")}" class="${base}">
            ${getThemeIcon()}
        </button>
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
                    ? "text-blue-700 bg-blue-50 border border-blue-200 dark:border-blue-800 dark:bg-blue-950/40 dark:text-blue-200"
                    : "text-slate-600 hover:text-blue-600 hover:bg-blue-50 border border-transparent dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-blue-300";
                return `<a href="${item.href}" class="px-3 py-2 rounded-xl text-sm font-semibold transition-colors ${classes}">${translate(item.key)}</a>`;
            })
            .join("");
        desktopRoot.innerHTML = `
            ${linksHtml}
            <div id="desktop-auth-container" class="flex items-center gap-3">${renderDesktopAuth()}</div>
            ${renderLanguageToggle(false)}
            ${renderThemeToggle(false)}
        `;
    }
    if (mobileRoot) {
        const mobileLinksHtml = links
            .map((item) => {
                const active = isActiveNavItem(item);
                const classes = active
                    ? "text-blue-700 bg-blue-50 border border-blue-200 dark:border-blue-800 dark:bg-blue-950/40 dark:text-blue-200"
                    : "text-slate-700 hover:text-blue-600 hover:bg-blue-50 border border-transparent dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-blue-300";
                return `<a href="${item.href}" class="block px-3 py-3 rounded-lg text-base font-medium transition-colors ${classes}">${translate(item.key)}</a>`;
            })
            .join("");
        mobileRoot.innerHTML = `
            ${mobileLinksHtml}
            <div class="grid grid-cols-[1fr_auto] gap-3">
                ${renderLanguageToggle(true)}
                ${renderThemeToggle(true)}
            </div>
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
    button.setAttribute("aria-controls", "mobile-menu");
    button.setAttribute("aria-expanded", "false");
    button.addEventListener("click", () => {
        menu.classList.toggle("hidden");
        button.setAttribute("aria-expanded", String(!menu.classList.contains("hidden")));
    });
    menu.addEventListener("click", (event) => {
        const target = event.target;
        if (target instanceof HTMLElement && target.closest("a")) {
            menu.classList.add("hidden");
            button.setAttribute("aria-expanded", "false");
        }
    });
}
function setupHomeSectionSpy() {
    if (normalizePath(window.location.pathname) !== "/") return;
    const projectsSection = document.getElementById("projects");
    if (!(projectsSection instanceof HTMLElement)) return;
    const observer = new IntersectionObserver(
        (entries) => {
            const nextSection = entries.some((entry) => entry.isIntersecting && entry.intersectionRatio >= 0.35)
                ? "projects"
                : "";
            if (navState.activeSection !== nextSection && window.location.hash !== "#projects") {
                navState.activeSection = nextSection;
                renderNavbar();
            }
        },
        {
            threshold: [0.2, 0.35, 0.6],
            rootMargin: "-120px 0px -35% 0px",
        }
    );
    observer.observe(projectsSection);
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
    const commands =[
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
            id: "toggle-theme",
            label: translate("palette.toggleTheme"),
            run: toggleTheme
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
            <div class="mx-auto mt-20 w-full max-w-2xl rounded-2xl border border-slate-200 bg-white shadow-2xl dark:border-slate-700 dark:bg-slate-800">
                <div class="border-b border-slate-100 p-4 dark:border-slate-700">
                    <p class="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400" data-i18n="palette.title"></p>
                    <input id="mpbCommandInput" type="text" class="w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 outline-none focus:ring-2 focus:ring-blue-500 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100" data-i18n-placeholder="palette.placeholder" placeholder="">
                </div>
                <div id="mpbCommandList" class="max-h-[22rem] overflow-y-auto p-2"></div>
            </div>
        </div>
        <div id="mpbShortcutHelp" class="hidden fixed inset-0 z-[120] bg-slate-900/50 backdrop-blur-sm px-4">
            <div class="mx-auto mt-24 w-full max-w-xl rounded-2xl border border-slate-200 bg-white shadow-2xl dark:border-slate-700 dark:bg-slate-800">
                <div class="flex items-center justify-between border-b border-slate-100 px-5 py-4 dark:border-slate-700">
                    <h2 class="text-lg font-bold text-slate-900 dark:text-slate-100" data-i18n="help.title"></h2>
                    <button type="button" data-close-help class="rounded-lg px-3 py-1 text-sm text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-700">Esc</button>
                </div>
                <div class="space-y-3 px-5 py-4 text-sm text-slate-700 dark:text-slate-300">
                    <div class="flex items-center justify-between"><span data-i18n="help.palette"></span><kbd class="rounded bg-slate-100 px-2 py-1 text-xs dark:bg-slate-700 dark:text-slate-200">Ctrl/Cmd + K</kbd></div>
                    <div class="flex items-center justify-between"><span data-i18n="help.focusSearch"></span><kbd class="rounded bg-slate-100 px-2 py-1 text-xs dark:bg-slate-700 dark:text-slate-200">/</kbd></div>
                    <div class="flex items-center justify-between"><span data-i18n="help.refresh"></span><kbd class="rounded bg-slate-100 px-2 py-1 text-xs dark:bg-slate-700 dark:text-slate-200">R</kbd></div>
                    <div class="flex items-center justify-between"><span data-i18n="help.nextPage"></span><kbd class="rounded bg-slate-100 px-2 py-1 text-xs dark:bg-slate-700 dark:text-slate-200">N</kbd></div>
                    <div class="flex items-center justify-between"><span data-i18n="help.prevPage"></span><kbd class="rounded bg-slate-100 px-2 py-1 text-xs dark:bg-slate-700 dark:text-slate-200">P</kbd></div>
                    <div class="flex items-center justify-between"><span data-i18n="help.open"></span><kbd class="rounded bg-slate-100 px-2 py-1 text-xs dark:bg-slate-700 dark:text-slate-200">?</kbd></div>
                    <div class="flex items-center justify-between"><span data-i18n="help.close"></span><kbd class="rounded bg-slate-100 px-2 py-1 text-xs dark:bg-slate-700 dark:text-slate-200">Esc</kbd></div>
                    <p class="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-400" data-i18n="help.hint"></p>
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
        list.innerHTML = `<div class="rounded-xl px-3 py-3 text-sm text-slate-500 dark:text-slate-400">${translate("palette.empty")}</div>`;
        return;
    }
    list.innerHTML = commands
        .map((command, index) => {
            const selected = index === navState.selectedCommandIndex;
            return `
                <button type="button" data-command-id="${command.id}" class="w-full rounded-xl px-3 py-2 text-left text-sm transition-colors ${selected ? "bg-blue-50 text-blue-700 dark:bg-blue-950/40 dark:text-blue-200" : "text-slate-700 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-700"}">
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
        if (!(target instanceof Element)) return;
        const langButton = target.closest(".js-lang-switch");
        if (langButton instanceof HTMLElement) {
            const lang = langButton.getAttribute("data-lang");
            if (lang) setLanguage(lang);
            return;
        }
        if (target.closest("[data-theme-toggle]")) {
            toggleTheme();
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
            const mobileMenuButton = document.getElementById("mobile-menu-button");
            if (mobileMenu && !mobileMenu.classList.contains("hidden")) {
                mobileMenu.classList.add("hidden");
                mobileMenuButton?.setAttribute("aria-expanded", "false");
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
            return;
        }
        if (event.altKey && event.key.toLowerCase() === "l") {
            event.preventDefault();
            setLanguage(navState.lang === "ru" ? "en" : "ru");
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
function registerServiceWorker() {
    if (!("serviceWorker" in navigator) || window.location.protocol === "file:") return;
    window.addEventListener("load", () => {
        navigator.serviceWorker.register("/service-worker.js")
            .then((registration) => registration.update())
            .catch((error) => {
                console.warn("Service worker registration failed", error);
            });
    });
}
window.mpbRefreshAuth = checkAuthAndRenderNavbar;
document.addEventListener("DOMContentLoaded", async () => {
    await window.mpbI18n?.ready;
    navState.lang = window.mpbI18n?.getLanguage?.() || "en";
    document.documentElement.lang = navState.lang;
    registerServiceWorker();
    setupMobileMenu();
    setupNavbarScrollBehavior();
    setupHomeSectionSpy();
    registerGlobalHandlers();
    ensureOverlays();
    window.mpbI18n?.registerTranslator?.((lang) => {
        navState.lang = lang;
        renderNavbar();
        applyTranslations();
    });
    checkAuthAndRenderNavbar();
    applyTranslations();
    window.addEventListener("hashchange", renderNavbar);
    window.addEventListener("popstate", renderNavbar);
    window.addEventListener("storage", (event) => {
        if (event.key === "jwt_token") {
            checkAuthAndRenderNavbar();
        }
    });
    window.addEventListener("mpb-auth-token-changed", checkAuthAndRenderNavbar);
});
})();
