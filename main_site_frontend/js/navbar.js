// main_site_frontend/js/navbar.js
const NAV_API_BASE = "https://api.ivantishchenko.ru/api";

// Глобальная функция выхода
window.performLogout = function() {
    localStorage.removeItem('jwt_token');
    window.location.href = '/login'; 
}

async function checkAuthAndRenderNavbar() {
    const token = localStorage.getItem('jwt_token');
    if (!token) return;

    try {
        const res = await fetch(`${NAV_API_BASE}/auth/me`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });

        if (res.ok) {
            const user = await res.json();
            const desktopContainer = document.getElementById('desktop-auth-container');
            const mobileContainer = document.getElementById('mobile-auth-container');

            const profileLink = user.role === "telegram" ? "/schedule" : "/stats";
            
            let avatarHtml = `<div class="w-6 h-6 rounded-full bg-blue-600 text-white flex items-center justify-center text-xs font-bold shrink-0">${user.username[0].toUpperCase()}</div>`;
            if (user.avatar_url) {
                avatarHtml = `<img src="${user.avatar_url}" class="w-6 h-6 rounded-full object-cover shrink-0 border border-slate-200">`;
            }
            
            let mobileAvatarHtml = `<div class="w-8 h-8 rounded-full bg-blue-600 text-white flex items-center justify-center text-sm font-bold shrink-0">${user.username[0].toUpperCase()}</div>`;
            if (user.avatar_url) {
                mobileAvatarHtml = `<img src="${user.avatar_url}" class="w-8 h-8 rounded-full object-cover shrink-0 border border-slate-200">`;
            }

            if(desktopContainer) {
                desktopContainer.innerHTML = `
                    <a href="${profileLink}" class="flex items-center gap-2 px-4 py-2 rounded-full border border-slate-200 hover:border-blue-400 hover:bg-blue-50 transition-colors max-w-[200px]">
                        ${avatarHtml}
                        <span class="text-sm font-bold text-slate-700 truncate">${user.username}</span>
                    </a>
                    <button onclick="performLogout()" class="text-sm font-medium text-slate-400 hover:text-red-500 transition-colors">Выйти</button>
                `;
            }

            if(mobileContainer) {
                mobileContainer.innerHTML = `
                    <div class="mt-4 pt-4 border-t border-slate-100">
                        <a href="${profileLink}" class="flex items-center gap-3 px-3 py-3 rounded-lg hover:bg-slate-50 transition-colors">
                            ${mobileAvatarHtml}
                            <div class="overflow-hidden">
                                <div class="text-sm font-bold text-slate-900 truncate">${user.username}</div>
                                <div class="text-xs text-slate-500">Личный кабинет</div>
                            </div>
                        </a>
                        <button onclick="performLogout()" class="w-full text-left mt-2 px-3 py-3 rounded-lg text-red-500 font-medium hover:bg-red-50 transition-colors">Выйти из аккаунта</button>
                    </div>
                `;
            }
        } else {
            // Если токен невалиден
            localStorage.removeItem('jwt_token');
            if (window.location.pathname === '/stats') {
                window.location.href = '/login';
            }
        }
    } catch (e) {
        console.error("Auth check failed", e);
    }
}

document.addEventListener('DOMContentLoaded', () => {
    checkAuthAndRenderNavbar();

    // Логика мобильного меню
    const btn = document.getElementById('mobile-menu-button');
    const menu = document.getElementById('mobile-menu');

    if(btn && menu) {
        btn.addEventListener('click', () => {
            menu.classList.toggle('hidden');
        });

        document.querySelectorAll('#mobile-menu a').forEach(link => {
            link.addEventListener('click', () => {
                menu.classList.add('hidden');
            });
        });
    }

    // Анимация скрытия шапки при скролле
    let lastScrollY = window.scrollY;
    let ticking = false;
    const navbar = document.getElementById('navbar');
    const scrollThreshold = 100;

    function updateNavbar() {
        if(!navbar) return;
        const currentScrollY = window.scrollY;
        if (currentScrollY > scrollThreshold) {
            if (currentScrollY > lastScrollY && currentScrollY > 200) {
                navbar.classList.add('nav-hidden');
                navbar.classList.remove('nav-visible');
            } else {
                navbar.classList.remove('nav-hidden');
                navbar.classList.add('nav-visible');
            }
        } else {
            navbar.classList.remove('nav-hidden');
            navbar.classList.add('nav-visible');
        }
        if (currentScrollY > 20) {
            navbar.classList.add('shadow-md');
        } else {
            navbar.classList.remove('shadow-md');
        }
        lastScrollY = currentScrollY;
        ticking = false;
    }

    window.addEventListener('scroll', () => {
        if (!ticking) {
            window.requestAnimationFrame(updateNavbar);
            ticking = true;
        }
    }, { passive: true });
});