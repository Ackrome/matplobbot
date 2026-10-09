/* Pinned inert HTML manifest -> on-demand, retryable library loading. */
(() => {
    const loads = new Map();
    const groups = { layout: ['split'], markdown: ['purify', 'marked', 'katex-css', 'katex', 'katex-auto'], mermaid: ['purify', 'mermaid'] };
    async function load(name) {
        if (loads.has(name)) return loads.get(name);
        const task = new Promise((resolve, reject) => {
            const source = document.getElementById('studio-library-manifest')?.content.querySelector(`[data-library="${name}"]`);
            if (!source) { reject(new Error(`Missing library: ${name}`)); return; }
            const node = source.cloneNode(true);
            let timer;
            const finish = (error) => {
                clearTimeout(timer);
                node.onload = node.onerror = null;
                if (error) { node.remove(); loads.delete(name); reject(error); }
                else resolve();
            };
            node.onload = () => finish();
            node.onerror = () => finish(new Error(`Library failed: ${name}`));
            timer = setTimeout(() => finish(new Error(`Library timeout: ${name}`)), 12000);
            document.head.appendChild(node);
        });
        loads.set(name, task);
        return task;
    }
    window.mpbStudioLibraries = { async ensure(group) {
        // Sequential ordering is intentional: sanitizer before parser, KaTeX before auto-render.
        for (const name of groups[group] || []) await load(name);
    } };
})();
