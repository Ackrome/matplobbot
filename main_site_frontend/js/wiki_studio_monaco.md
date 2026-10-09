# Monaco frame bootstrap

`studio_monaco.js` runs only in `studio-editor.html`. It configures the pinned Monaco AMD module
path and exposes `window.mpbStudioMonacoReady`, a promise the parent awaits before constructing
the editor. No document contents, tokens, or API requests are handled by this bootstrap.

The frame separates Monaco's global `define` from lazily loaded UMD preview libraries in the
parent. Dependencies: the SRI-pinned AMD loader in the frame and its pinned CDN modules. Network
or loader failure rejects readiness; `studio.js` retains its textarea and offers Retry.

Keep the frame same-origin, CSP enforced, and Monaco versions aligned with the manifest. Do not
move the AMD loader back into the parent without testing Markdown and Mermaid after editor load.
