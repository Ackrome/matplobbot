const API_BASE = "https://api.ivantishchenko.ru/api";
// const API_BASE = "http://api.localhost/api";

const loginForm = document.getElementById('loginForm');
const registerForm = document.getElementById('registerForm');

// Вспомогательная функция для извлечения понятного текста ошибки из FastAPI
function getErrorMessage(errData, defaultMsg) {
    if (errData && Array.isArray(errData.detail)) {
        // Ошибка валидации Pydantic (например, короткий пароль)
        return errData.detail[0].msg;
    } else if (errData && errData.detail) {
        // Обычная HTTPException
        return errData.detail;
    }
    return defaultMsg;
}

if (loginForm) {
    loginForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const errorEl = document.getElementById('error');
        const btn = e.target.querySelector('button');
        const username = document.getElementById('username').value;
        const password = document.getElementById('password').value;

        // Сброс ошибок и индикация загрузки
        errorEl.classList.add('hidden');
        btn.disabled = true;
        btn.innerText = "Вход...";

        // Подготовка данных в формате Form Data (как требует FastAPI OAuth2)
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
                window.location.href = '/stats';
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
            btn.innerText = "Войти в систему";
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
                // После успешной регистрации сразу логиним пользователя
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