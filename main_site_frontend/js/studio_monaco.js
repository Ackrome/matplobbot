/* Keep Monaco's AMD namespace inside the editor frame, away from preview UMD libraries. */
window.mpbStudioMonacoReady = new Promise((resolve, reject) => {
    if (typeof require !== 'function') { reject(new Error('Monaco loader unavailable')); return; }
    require.config({ paths: { vs: 'https://cdnjs.cloudflare.com/ajax/libs/monaco-editor/0.38.0/min/vs' } });
    require(['vs/editor/editor.main'], resolve, reject);
});
// The parent handles the rejection and keeps its textarea. Avoid an unhandled event before load.
window.mpbStudioMonacoReady.catch(() => {});
