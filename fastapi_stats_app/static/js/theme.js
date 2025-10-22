// --- Theme Switcher Logic (Shared) ---

function getChartThemeColors(theme) {
    const isDark = theme === 'dark';
    return {
        tickColor: isDark ? 'rgba(255, 255, 255, 0.7)' : '#555',
        gridColor: isDark ? 'rgba(255, 255, 255, 0.15)' : 'rgba(0, 0, 0, 0.1)',
        legendColor: isDark ? 'rgba(255, 255, 255, 0.9)' : '#333',
        titleColor: isDark ? 'rgba(255, 255, 255, 0.9)' : '#333'
    };
}

function applyTheme(theme) {
    const themeToggleButton = document.getElementById('theme-toggle-button');
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('theme', theme);
    if (themeToggleButton) {
        themeToggleButton.textContent = (theme === 'dark') ? 'Светлая тема' : 'Темная тема';
    }
}

document.addEventListener('DOMContentLoaded', function() {
    const themeToggleButton = document.getElementById('theme-toggle-button');

    // Initial theme setup
    let storedTheme = localStorage.getItem('theme');
    if (!storedTheme || (storedTheme !== 'light' && storedTheme !== 'dark')) {
        storedTheme = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    }
    applyTheme(storedTheme);

    if (themeToggleButton) {
        themeToggleButton.addEventListener('click', function() {
            let currentTheme = document.documentElement.getAttribute('data-theme');
            applyTheme((currentTheme === 'dark') ? 'light' : 'dark');
        });
    }
});