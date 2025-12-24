/* bot/templates/report.js */

document.addEventListener("DOMContentLoaded", function() {
    
    // 1. Initialize Mermaid
    if (typeof mermaid !== 'undefined') {
        mermaid.initialize({ startOnLoad: true, theme: 'default' });
    }

    // 2. Render LaTeX using Auto-render extension
    // Мы настроим delimiters так, чтобы $$...$$ всегда были display: true
    if (typeof renderMathInElement !== 'undefined') {
        renderMathInElement(document.body, {
            delimiters: [
                {left: "$$", right: "$$", display: true},  // Block math
                {left: "$", right: "$", display: false},   // Inline math
                {left: "\\(", right: "\\)", display: false},
                {left: "\\[", right: "\\]", display: true}
            ],
            // Игнорируем теги, где математика не должна рендериться
            ignoredTags: ["script", "noscript", "style", "textarea", "pre", "code", "option"]
        });
    }
});