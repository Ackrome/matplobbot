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

    class FileConflict extends Error {
        constructor(content, revision) {
            super('Studio file revision conflict');
            this.content = content;
            this.revision = revision;
        }
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
                const entry = JSON.stringify({
                    content: record.content, baseContent: record.saved, updatedAt: Date.now(),
                    editId: globalThis.crypto?.randomUUID?.() || String(Math.random()),
                });
                storage.setItem(prefix + key(record), entry);
                record.draftEntry = entry;
                return true;
            } catch (error) { onStorageError(error); return false; }
        }
        function remove(record) {
            try {
                const name = prefix + key(record);
                if (record.draftEntry && storage.getItem(name) === record.draftEntry) storage.removeItem(name);
                delete record.draftEntry;
            } catch (error) { onStorageError(error); }
        }
        function open(record, { restore = true } = {}) {
            const draft = read(key(record));
            current = { ...record, saved: record.content, content: record.content, recovered: false, conflict: false };
            if (restore && draft && typeof draft.content === 'string' && draft.content !== record.content) {
                current.conflict = Boolean(record.projectId && draft.baseContent !== record.content);
                current.draftContent = draft.content;
                current.draftUpdatedAt = draft.updatedAt;
                current.draftEntry = JSON.stringify(draft);
                if (current.conflict) {
                    current.serverContent = record.content;
                    current.serverRevision = record.revision;
                } else {
                    current.content = draft.content;
                    current.recovered = true;
                }
            }
            return { ...current };
        }
        function resolveConflict(useDraft) {
            if (!current?.conflict) return;
            current.saved = current.serverContent;
            current.revision = current.serverRevision;
            current.content = useDraft ? current.draftContent : current.serverContent;
            current.recovered = useDraft;
            current.conflict = false;
            delete current.draftContent;
            delete current.draftUpdatedAt;
            delete current.serverContent;
            delete current.serverRevision;
            if (current.content !== current.saved) write(current);
            else remove(current);
            return { ...current };
        }
        function edit(content) {
            if (!current || current.conflict) return;
            current.content = content;
            write(current);
        }
        function flush() {
            const record = current;
            const operation = pending.catch(() => {}).then(async () => {
                if (!record || !record.projectId) return;
                if (record.conflict) throw new FileConflict(record.serverContent, record.serverRevision);
                while (record.content !== record.saved) {
                    const content = record.content;
                    try {
                        const saved = await save({ ...record, content });
                        record.revision = saved?.revision ?? record.revision;
                    } catch (error) {
                        if (error instanceof FileConflict) {
                            record.conflict = true;
                            record.draftContent = record.content;
                            record.draftUpdatedAt = Date.now();
                            record.serverContent = error.content;
                            record.serverRevision = error.revision;
                            write(record);
                        }
                        throw error;
                    }
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
            dirty: () => Boolean(current?.projectId && (current.conflict || current.content !== current.saved)),
            readValue: name => read(name),
            storeValue(name, value) {
                try { storage.setItem(prefix + name, JSON.stringify(value)); }
                catch (error) { onStorageError(error); }
            },
            removeValue(name) { try { storage.removeItem(prefix + name); } catch (_) { /* best effort */ } },
        };
    }
    return { create, accountScope, FileConflict };
});
