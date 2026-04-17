(function () {
    var root = document.documentElement;
    var isDark = false;

    try {
        var storedTheme = localStorage.getItem("theme");
        isDark =
            storedTheme === "dark" ||
            (storedTheme === null && window.matchMedia("(prefers-color-scheme: dark)").matches);
    } catch (error) {
        isDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    }

    root.dataset.theme = isDark ? "dark" : "light";
    root.classList.toggle("dark", isDark);
})();
