// --- Theme Switcher Logic ---

function getChartThemeColors(theme) {
    const isDark = theme === 'dark';
    return {
        // Светло-серый для тиков в темной теме, темно-серый в светлой
        tickColor: isDark ? '#9ca3af' : '#4b5563', 
        gridColor: isDark ? 'rgba(255, 255, 255, 0.05)' : 'rgba(0, 0, 0, 0.05)',
        legendColor: isDark ? '#e5e7eb' : '#1f2937', 
        titleColor: isDark ? '#e5e7eb' : '#1f2937'
    };
}

function updateIcons() {
    const lightIcon = document.getElementById('theme-toggle-light-icon');
    const darkIcon = document.getElementById('theme-toggle-dark-icon');
    const isDark = document.documentElement.classList.contains('dark');

    if (!lightIcon || !darkIcon) return;

    if (isDark) {
        lightIcon.classList.remove('hidden');
        darkIcon.classList.add('hidden');
    } else {
        lightIcon.classList.add('hidden');
        darkIcon.classList.remove('hidden');
    }
}

document.addEventListener('DOMContentLoaded', function() {
    const toggleBtn = document.getElementById('theme-toggle-button');
    
    // 1. Инициализация
    if (localStorage.getItem('theme') === 'dark' || (!('theme' in localStorage) && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
        document.documentElement.classList.add('dark');
        document.documentElement.setAttribute('data-theme', 'dark'); // Legacy support
    } else {
        document.documentElement.classList.remove('dark');
        document.documentElement.setAttribute('data-theme', 'light'); // Legacy support
    }
    updateIcons();

    // 2. Клик
    if (toggleBtn) {
        toggleBtn.addEventListener('click', function() {
            document.documentElement.classList.toggle('dark');
            
            const isDark = document.documentElement.classList.contains('dark');
            if (isDark) {
                localStorage.setItem('theme', 'dark');
                document.documentElement.setAttribute('data-theme', 'dark');
            } else {
                localStorage.setItem('theme', 'light');
                document.documentElement.setAttribute('data-theme', 'light');
            }
            
            updateIcons();
        });
    }
});