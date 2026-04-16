// main_site_frontend/js/auth.js
const API_BASE = window.getMpbApiBase ? window.getMpbApiBase() : "/api";

const loginForm = document.getElementById("loginForm");
const registerForm = document.getElementById("registerForm");

const AUTH_TEXT = {
    en: {
        telegramAuthError: "Telegram authorization failed",
        apiUnavailable: "API server is unavailable",
        loginError: "Login failed",
        loginLoading: "Signing in...",
        loginButton: "Sign in with password",
        registerError: "Registration failed",
        registerLoading: "Registering...",
        registerButton: "Create account",
        popupWarningTitle: "Warning",
    },
    ru: {
        telegramAuthError: "Ошибка авторизации через Telegram",
        apiUnavailable: "Сервер API недоступен",
        loginError: "Ошибка входа",
        loginLoading: "Вход...",
        loginButton: "Войти по паролю",
        registerError: "Ошибка регистрации",
        registerLoading: "Регистрация...",
        registerButton: "Зарегистрироваться",
        popupWarningTitle: "Внимание",
    },
};

function getUiLanguage() {
    const source = window.mpbI18n?.getLanguage?.() || document.documentElement.lang || "ru";
    return String(source).toLowerCase().startsWith("ru") ? "ru" : "en";
}

function authT(key) {
    const lang = getUiLanguage();
    return AUTH_TEXT[lang]?.[key] || AUTH_TEXT.ru[key] || key;
}

function getErrorMessage(errData, defaultMsg) {
    if (errData && Array.isArray(errData.detail) && errData.detail.length > 0) {
        return errData.detail[0].msg;
    }
    if (errData && errData.detail) {
        return errData.detail;
    }
    return defaultMsg;
}

window.handleTelegramLogin = async function handleTelegramLogin(telegramUser) {
    const errorEl = document.getElementById("error");
    if (errorEl) errorEl.classList.add("hidden");

    try {
        const response = await fetch(`${API_BASE}/auth/telegram`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(telegramUser),
        });

        if (response.ok) {
            const data = await response.json();
            localStorage.setItem("jwt_token", data.access_token);
            window.dispatchEvent(new CustomEvent("mpb-auth-token-changed"));
            window.location.href = "/schedule";
            return;
        }

        const errData = await response.json();
        const message = getErrorMessage(errData, authT("telegramAuthError"));
        if (errorEl) {
            errorEl.innerText = message;
            errorEl.classList.remove("hidden");
        } else {
            window.mpbPopup?.(message, {
                type: "warning",
                title: authT("popupWarningTitle"),
            });
        }
    } catch (err) {
        console.error(err);
        const message = authT("apiUnavailable");
        if (errorEl) {
            errorEl.innerText = message;
            errorEl.classList.remove("hidden");
        } else {
            window.mpbPopup?.(message, { type: "error" });
        }
    }
};

if (loginForm) {
    loginForm.addEventListener("submit", async (e) => {
        e.preventDefault();

        const errorEl = document.getElementById("error");
        const btn = e.target.querySelector("button");
        const username = document.getElementById("username").value;
        const password = document.getElementById("password").value;

        errorEl.classList.add("hidden");
        btn.disabled = true;
        btn.innerText = authT("loginLoading");

        const formData = new URLSearchParams();
        formData.append("username", username);
        formData.append("password", password);

        try {
            const response = await fetch(`${API_BASE}/auth/login`, {
                method: "POST",
                headers: { "Content-Type": "application/x-www-form-urlencoded" },
                body: formData,
            });

            if (response.ok) {
                const data = await response.json();
                localStorage.setItem("jwt_token", data.access_token);
                window.dispatchEvent(new CustomEvent("mpb-auth-token-changed"));
                window.location.href = "/stats";
                return;
            }

            const errData = await response.json();
            errorEl.innerText = getErrorMessage(errData, authT("loginError"));
            errorEl.classList.remove("hidden");
        } catch (err) {
            errorEl.innerText = authT("apiUnavailable");
            errorEl.classList.remove("hidden");
            window.mpbPopup?.(authT("apiUnavailable"), { type: "error" });
        } finally {
            btn.disabled = false;
            btn.innerText = authT("loginButton");
        }
    });
}

if (registerForm) {
    registerForm.addEventListener("submit", async (e) => {
        e.preventDefault();

        const errorEl = document.getElementById("reg_error");
        const successEl = document.getElementById("reg_success");
        const btn = e.target.querySelector("button");
        const username = document.getElementById("reg_username").value;
        const password = document.getElementById("reg_password").value;

        errorEl.classList.add("hidden");
        successEl.classList.add("hidden");
        btn.disabled = true;
        btn.innerText = authT("registerLoading");

        try {
            const response = await fetch(`${API_BASE}/auth/register`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ username, password }),
            });

            if (response.ok) {
                successEl.classList.remove("hidden");
                const formData = new URLSearchParams();
                formData.append("username", username);
                formData.append("password", password);

                const loginResponse = await fetch(`${API_BASE}/auth/login`, {
                    method: "POST",
                    headers: { "Content-Type": "application/x-www-form-urlencoded" },
                    body: formData,
                });

                if (loginResponse.ok) {
                    const data = await loginResponse.json();
                    localStorage.setItem("jwt_token", data.access_token);
                    window.dispatchEvent(new CustomEvent("mpb-auth-token-changed"));
                    setTimeout(() => {
                        window.location.href = "/stats";
                    }, 1000);
                }
                return;
            }

            const errData = await response.json();
            errorEl.innerText = getErrorMessage(errData, authT("registerError"));
            errorEl.classList.remove("hidden");
            btn.disabled = false;
            btn.innerText = authT("registerButton");
        } catch (err) {
            console.error(err);
            errorEl.innerText = authT("apiUnavailable");
            errorEl.classList.remove("hidden");
            btn.disabled = false;
            btn.innerText = authT("registerButton");
            window.mpbPopup?.(authT("apiUnavailable"), { type: "error" });
        }
    });
}
