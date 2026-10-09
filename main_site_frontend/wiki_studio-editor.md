# Studio editor frame

`studio-editor.html` is a same-origin document used internally by Studio. It isolates Monaco's
AMD global namespace from the parent's lazy Markdown/Mermaid UMD libraries. It loads the shared
Studio stylesheet, an SRI-pinned Monaco loader, and `studio_monaco.js` readiness bootstrap.

The parent creates an accessible titled iframe, awaits readiness, then creates Monaco inside
`#monaco-container`. It controls text, theme, read-only state, and change callbacks. Opening this
route alone displays an empty editor host; it has no auth or document API logic.

Its CSP permits the same pinned editor runtime requirements (AMD evaluation and runtime styles)
as Studio but rejects inline script handlers. Keep it same-origin and include the frame and
bootstrap in the service-worker shell cache. Verify actual CDN loading, fallback/retry, shortcuts,
and screen-reader iframe navigation when changing this boundary.
