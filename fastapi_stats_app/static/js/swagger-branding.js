(function () {
    function decorateDocs() {
        const infoBlock = document.querySelector(".swagger-ui .information-container .info");
        if (infoBlock && !infoBlock.querySelector(".mpb-docs-note")) {
            const note = document.createElement("section");
            note.className = "mpb-docs-note";
            note.innerHTML =
                "<strong>Auth quick start</strong>" +
                "<span>Use the Authorize button for username/password login, or paste a JWT from /api/auth/telegram when testing Telegram-authenticated flows.</span>";
            infoBlock.appendChild(note);
        }
    }

    const observer = new MutationObserver(decorateDocs);
    observer.observe(document.documentElement, { childList: true, subtree: true });
    decorateDocs();
})();
