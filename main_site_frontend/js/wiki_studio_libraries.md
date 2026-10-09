# Studio lazy libraries

`studio_libraries.js` exposes `mpbStudioLibraries.ensure(group)` for `layout`,
`markdown`, and `mermaid`. It reads pinned SRI/crossorigin script and stylesheet elements
from the inert `studio-library-manifest` template in `studio.html`, then loads only the chosen
group. Example: `await mpbStudioLibraries.ensure('markdown')` before preview rendering.

The loader deduplicates successful/in-flight loads, preserves dependency ordering, times out
after 12 seconds, and removes failed entries so Retry can try again. It depends on the DOM and
network/CDN availability; appending tags executes third-party code subject to CSP and SRI.
Callers must catch failures, preserve editable contents, and display a recoverable state.

Keep the sanitizer before Marked/Mermaid and KaTeX before its extension. Update pinned URLs and
SRI together in the manifest, never remove integrity to make a failing CDN asset load. Monaco
loads separately in `studio-editor.html` so its AMD namespace does not capture these UMD libraries.
Manual asset versions remain required.
