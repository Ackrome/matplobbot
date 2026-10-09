/* Treat repository Markdown as untrusted content, including cached copies. */
(() => {
    const repo = 'Ackrome/matplobbot';
    const article = document.getElementById('readme-content');
    const status = document.getElementById('readme-status');
    const retry = document.getElementById('readme-retry');
    const toc = document.getElementById('readme-toc');
    const navigation = document.querySelector('.readme-navigation');
    const narrow = matchMedia('(max-width:640px)');
    const t = key => window.mpbI18n.t(`ux.${key}`, key);
    const filename = language => language === 'ru' ? 'README.ru.md' : 'README.md';
    const cacheKey = language => `mpb-readme-v2:${language}`;
    const fitContents = () => { navigation.open = !narrow.matches; };
    fitContents();
    narrow.addEventListener('change', fitContents);
    let sequence = 0;
    let activeController;
    let displayed;

    function validDocument(data, language) {
        if (!data || data.language !== language || typeof data.markdown !== 'string'
            || data.markdown.length > 1500000 || typeof data.html_url !== 'string') return false;
        try {
            const url = new URL(data.html_url);
            return url.origin === 'https://github.com'
                && url.pathname.startsWith(`/${repo}/blob/`)
                && url.pathname.endsWith('/' + filename(language));
        } catch { return false; }
    }

    function cachedDocument(language) {
        try {
            const data = JSON.parse(localStorage.getItem(cacheKey(language)));
            return validDocument(data, language) ? data : null;
        } catch { return null; }
    }

    function setStatus(key) { status.textContent = t(key); }

    function render(data, requestedLanguage) {
        if (!window.marked || !window.DOMPurify) throw new Error('renderer');
        article.innerHTML = DOMPurify.sanitize(marked.parse(data.markdown), {
            USE_PROFILES: {html: true},
            FORBID_TAGS: ['style', 'form', 'input', 'button', 'iframe', 'object', 'embed'],
            FORBID_ATTR: ['style', 'srcset', 'id', 'name'],
            ALLOW_DATA_ATTR: false,
        });
        article.lang = data.language;
        const base = data.html_url.replace(/[^/]+$/, '');
        const raw = base.replace('github.com/', 'raw.githubusercontent.com/').replace('/blob/', '/');
        toc.replaceChildren();
        const ids = new Map();
        article.querySelectorAll('h1,h2,h3').forEach(node => {
            const slug = node.textContent.toLowerCase().trim()
                .replace(/[^\p{L}\p{N}\s_-]/gu, '').replace(/\s+/g, '-') || 'section';
            const n = ids.get(slug) || 0;
            ids.set(slug, n + 1);
            node.id = slug + (n ? `-${n}` : '');
            if (node.tagName !== 'H3') {
                const link = document.createElement('a');
                link.href = `#${node.id}`;
                link.textContent = node.textContent;
                toc.append(link);
            }
        });
        article.querySelectorAll('a[href],img[src]').forEach(node => {
            const isImage = node.tagName === 'IMG';
            const attr = isImage ? 'src' : 'href';
            const value = node.getAttribute(attr);
            if (value.startsWith('#')) return;
            try {
                const url = new URL(value, isImage ? raw : base);
                if (!['https:', 'http:'].includes(url.protocol)) {
                    node.removeAttribute(attr);
                    return;
                }
                node.setAttribute(attr, url.href);
                if (isImage) {
                    node.loading = 'lazy';
                    node.referrerPolicy = 'no-referrer';
                    node.addEventListener('error', () => {
                        const label = document.createElement('span');
                        label.className = 'readme-image-fallback';
                        label.textContent = node.alt || t('imageUnavailable');
                        node.replaceWith(label);
                    }, {once: true});
                } else {
                    node.target = '_blank';
                    node.rel = 'noopener noreferrer';
                    const language = ['en', 'ru'].find(lang => url.href === base + filename(lang));
                    if (language) {
                        if (language === data.language) node.setAttribute('aria-current', 'true');
                        node.addEventListener('click', event => {
                            if (event.button || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
                            event.preventDefault();
                            window.mpbI18n.setLanguage(language);
                        });
                    }
                }
            } catch { node.removeAttribute(attr); }
        });
        article.querySelectorAll('pre').forEach(pre => {
            const button = document.createElement('button');
            button.className = 'ui-button';
            button.textContent = t('copy');
            const text = pre.textContent;
            button.addEventListener('click', async () => {
                try { await navigator.clipboard.writeText(text); button.textContent = t('copied'); }
                catch { button.textContent = t('copyFailed'); }
            });
            pre.after(button);
        });
        displayed = {data, requestedLanguage};
    }

    async function fetchDocument(language, signal) {
        const response = await fetch(`https://api.github.com/repos/${repo}/contents/${filename(language)}`, {
            headers: {Accept: 'application/vnd.github+json'}, signal,
        });
        if (!response.ok) {
            const error = new Error('github');
            error.status = response.status;
            throw error;
        }
        const body = await response.json();
        if (body.encoding !== 'base64' || body.size > 1500000 || typeof body.content !== 'string'
            || body.content.length > 2100000) throw new Error('format');
        const bytes = Uint8Array.from(atob(body.content.replace(/\s/g, '')), char => char.charCodeAt(0));
        const data = {
            markdown: new TextDecoder('utf-8', {fatal: true}).decode(bytes),
            html_url: body.html_url, language, savedAt: Date.now(),
        };
        if (!validDocument(data, language)) throw new Error('format');
        return data;
    }

    async function load(force = false) {
        const request = ++sequence;
        activeController?.abort();
        await window.mpbI18n.ready;
        if (request !== sequence) return;
        const language = window.mpbI18n.getLanguage() === 'ru' ? 'ru' : 'en';
        const controller = new AbortController();
        activeController = controller;
        const timeout = setTimeout(() => controller.abort(), 12000);
        retry.disabled = true;
        article.setAttribute('aria-busy', 'true');
        const cached = cachedDocument(language);
        const previous = displayed?.requestedLanguage === language ? displayed.data : null;
        if (!cached && !previous) {
            article.replaceChildren();
            toc.replaceChildren();
            displayed = null;
        }
        setStatus('readmeLoading');
        try {
            if (cached) {
                render(cached, language);
                setStatus('readmeCached');
                const age = Date.now() - cached.savedAt;
                if (!force && age >= 0 && age < 600000) return;
            }
            let data;
            try { data = await fetchDocument(language, controller.signal); }
            catch (error) {
                if (language !== 'ru' || error.status !== 404) throw error;
                data = await fetchDocument('en', controller.signal);
            }
            if (request !== sequence) return;
            render(data, language);
            try { localStorage.setItem(cacheKey(data.language), JSON.stringify(data)); } catch {}
            setStatus(data.language === language ? 'readmeReady' : 'readmeFallback');
        } catch {
            if (request !== sequence) return;
            if (displayed?.requestedLanguage === language) {
                setStatus(displayed.data.language === language ? 'readmeCached' : 'readmeFallbackCached');
            } else { setStatus('readmeFailed'); }
        } finally {
            clearTimeout(timeout);
            if (request === sequence) {
                retry.disabled = false;
                article.setAttribute('aria-busy', 'false');
            }
        }
    }

    retry.addEventListener('click', () => load(true));
    window.addEventListener('mpb-language-change', () => load());
    load();
})();
