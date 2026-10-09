/* Durable, account-scoped editor state; also usable by the Node regression suite. */
(function (root, factory) {
    const api = factory();
    if (typeof module === 'object' && module.exports) module.exports = api;
    else root.MpbStudioSession = api;
})(typeof window === 'object' ? window : globalThis, function () {
    function accountScope(token) {
        try {
            const payload = JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')));
            if (payload.sub) return encodeURIComponent(String(payload.sub));
        } catch (_) { /* An invalid session must not see another account's drafts. */ }
        return 'anonymous';
    }

    function create({ storage, scope, save, onStorageError = () => {} }) {
        const prefix = `mpb-studio-v1:${scope}:`;
        let current = null;
        let pending = Promise.resolve();
        function key(record) { return record.projectId ? `${record.projectId}:${record.fileId}` : `quick:${record.type}`; }
        function read(name) {
            try { return JSON.parse(storage.getItem(prefix + name) || 'null'); }
            catch (_) { return null; }
        }
        function write(record) {
            try {
                storage.setItem(prefix + key(record), JSON.stringify({
                    content: record.content, baseContent: record.saved, updatedAt: Date.now(),
                }));
                return true;
            } catch (error) { onStorageError(error); return false; }
        }
        function remove(record) {
            try { storage.removeItem(prefix + key(record)); } catch (error) { onStorageError(error); }
        }
        function open(record, { restore = true } = {}) {
            const draft = read(key(record));
            current = { ...record, saved: record.content, content: record.content, recovered: false, conflict: false };
            if (restore && draft && typeof draft.content === 'string' && draft.content !== record.content) {
                current.conflict = Boolean(record.projectId && draft.baseContent !== record.content);
                current.draftContent = draft.content;
                current.draftUpdatedAt = draft.updatedAt;
                if (!current.conflict) { current.content = draft.content; current.recovered = true; }
            }
            return { ...current };
        }
        function resolveConflict(useDraft) {
            if (!current?.conflict) return;
            if (useDraft) { current.content = current.draftContent; current.recovered = true; write(current); }
            else remove(current);
            current.conflict = false;
            return { ...current };
        }
        function edit(content) {
            if (!current) return;
            current.content = content;
            write(current);
        }
        function flush() {
            const record = current;
            const operation = pending.catch(() => {}).then(async () => {
                if (!record || !record.projectId || record.conflict) return;
                while (record.content !== record.saved) {
                    const content = record.content;
                    await save({ ...record, content });
                    record.saved = content;
                    // Do not discard a newer edit made while the request was in flight.
                    if (record.content === content) remove(record);
                    else write(record);
                }
            });
            pending = operation;
            return operation;
        }
        return { open, edit, flush, resolveConflict, snapshot: () => current && { ...current },
            dirty: () => Boolean(current?.projectId && current.content !== current.saved),
            readValue: name => read(name),
            storeValue(name, value) {
                try { storage.setItem(prefix + name, JSON.stringify(value)); }
                catch (error) { onStorageError(error); }
            },
            removeValue(name) { try { storage.removeItem(prefix + name); } catch (_) { /* best effort */ } },
        };
    }
    return { create, accountScope };
});
