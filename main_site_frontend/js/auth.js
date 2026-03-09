const API_BASE = "https://api.ivantishchenko.ru/api";
// const API_BASE = "http://api.localhost/api";
document.getElementById('loginForm').addEventListener('submit', async (e) => {
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
            // Сохраняем токен в localStorage
            localStorage.setItem('jwt_token', data.access_token);
            
            // Успех! Перенаправляем на страницу статистики
            // Мы сделаем её по адресу ivantishchenko.ru/stats
            window.location.href = '/stats';
        } else {
            const errData = await response.json();
            errorEl.innerText = errData.detail || "Ошибка входа";
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