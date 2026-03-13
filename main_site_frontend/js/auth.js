// main_site_frontend/js/auth.js
const API_BASE = "https://api.ivantishchenko.ru/api";

const loginForm = document.getElementById('loginForm');
const registerForm = document.getElementById('registerForm');

function getErrorMessage(errData, defaultMsg) {
    if (errData && Array.isArray(errData.detail)) {
        return errData.detail[0].msg;
    } else if (errData && errData.detail) {
        return errData.detail;
    }
    return defaultMsg;
}

// --- НОВАЯ ФУНКЦИЯ: Обработка входа через Telegram ---
window.handleTelegramLogin = async function(telegramUser) {
    const errorEl = document.getElementById('error');
    if(errorEl) errorEl.classList.add('hidden');

    try {
        const response = await fetch(`${API_BASE}/auth/telegram`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(telegramUser)
        });

        if (response.ok) {
            const data = await response.json();
            localStorage.setItem('jwt_token', data.access_token);
            // Если всё ок, кидаем на главную страницу (или на расписание)
            window.location.href = '/schedule'; 
        } else {
            const errData = await response.json();
            if(errorEl) {
                errorEl.innerText = getErrorMessage(errData, "Ошибка авторизации через Telegram");
                errorEl.classList.remove('hidden');
            } else {
                alert("Ошибка авторизации через Telegram");
            }
        }
    } catch (err) {
        console.error(err);
        if(errorEl) {
            errorEl.innerText = "Сервер API недоступен";
            errorEl.classList.remove('hidden');
        }
    }
};

// --- СТАНДАРТНАЯ АВТОРИЗАЦИЯ ПО ПАРОЛЮ ---
if (loginForm) {
    loginForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const errorEl = document.getElementById('error');
        const btn = e.target.querySelector('button');
        const username = document.getElementById('username').value;
        const password = document.getElementById('password').value;

        errorEl.classList.add('hidden');
        btn.disabled = true;
        btn.innerText = "Вход...";

        const formData = new URLSearchParams();
        formData.append('username', username);
        formData.append('password', password);

        try {
            const response = await fetch(`${API_BASE}/auth/login`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                body: formData
            });

            if (response.ok) {
                const data = await response.json();
                localStorage.setItem('jwt_token', data.access_token);
                window.location.href = '/stats'; // Админов кидаем в статистику
            } else {
                const errData = await response.json();
                errorEl.innerText = getErrorMessage(errData, "Ошибка входа");
                errorEl.classList.remove('hidden');
            }
        } catch (err) {
            errorEl.innerText = "Сервер API недоступен";
            errorEl.classList.remove('hidden');
        } finally {
            btn.disabled = false;
            btn.innerText = "Войти по паролю";
        }
    });
}

if (registerForm) {
    registerForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const errorEl = document.getElementById('reg_error');
        const successEl = document.getElementById('reg_success');
        const btn = e.target.querySelector('button');
        const username = document.getElementById('reg_username').value;
        const password = document.getElementById('reg_password').value;

        errorEl.classList.add('hidden');
        successEl.classList.add('hidden');
        btn.disabled = true;
        btn.innerText = "Регистрация...";

        try {
            const response = await fetch(`${API_BASE}/auth/register`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username: username, password: password })
            });

            if (response.ok) {
                successEl.classList.remove('hidden');
                const formData = new URLSearchParams();
                formData.append('username', username);
                formData.append('password', password);
                
                const loginResponse = await fetch(`${API_BASE}/auth/login`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                    body: formData
                });
                
                if (loginResponse.ok) {
                    const data = await loginResponse.json();
                    localStorage.setItem('jwt_token', data.access_token);
                    setTimeout(() => { window.location.href = '/stats'; }, 1000);
                }
            } else {
                const errData = await response.json();
                errorEl.innerText = getErrorMessage(errData, "Ошибка регистрации");
                errorEl.classList.remove('hidden');
                btn.disabled = false;
                btn.innerText = "Зарегистрироваться";
            }
        } catch (err) {
            console.error(err);
            errorEl.innerText = "Сервер API недоступен";
            errorEl.classList.remove('hidden');
            btn.disabled = false;
            btn.innerText = "Зарегистрироваться";
        }
    });
}