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
        const contextId = globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`;
        let current = null;
        let pending = Promise.resolve();
        function key(record) { return record.projectId ? `${record.projectId}:${record.fileId}` : `quick:${record.type}`; }
        function journalPrefix(record) { return `${prefix}${key(record)}:draft:`; }
        function journalKey(record) { return journalPrefix(record) + contextId; }
        function read(name) {
            try { return JSON.parse(storage.getItem(prefix + name) || 'null'); }
            catch (_) { return null; }
        }
        function readDrafts(record) {
            const legacyKey = prefix + key(record);
            const names = new Set([legacyKey, journalKey(record)]);
            const journals = journalPrefix(record);
            try {
                for (let i = 0; i < storage.length; i++) {
                    const name = storage.key(i);
                    if (name?.startsWith(journals)) names.add(name);
                }
            } catch (_) { /* The editor also works without browser storage. */ }

            const drafts = [];
            for (const name of names) {
                try {
                    const entry = storage.getItem(name);
                    const draft = JSON.parse(entry);
                    if (typeof draft?.content === 'string' && draft.content !== record.content) {
                        drafts.push({ ...draft, name, entry, legacy: name === legacyKey });
                    }
                } catch (_) { /* Ignore malformed entries without deleting them. */ }
            }
            return drafts.sort((left, right) => (right.updatedAt || 0) - (left.updatedAt || 0));
        }
        function write(record) {
            try {
                const entry = JSON.stringify({
                    content: record.content, baseContent: record.saved, updatedAt: Date.now(),
                    editId: globalThis.crypto?.randomUUID?.() || String(Math.random()),
                });
                const name = journalKey(record);
                storage.setItem(name, entry);
                record.draftEntry = { name, entry };
                return true;
            } catch (error) { onStorageError(error); return false; }
        }
        function removeEntry(draft) {
            try {
                if (draft && storage.getItem(draft.name) === draft.entry) storage.removeItem(draft.name);
            } catch (error) { onStorageError(error); }
        }
        function remove(record) {
            removeEntry(record.draftEntry);
            removeEntry(record.sourceDraft);
            delete record.draftEntry;
            delete record.sourceDraft;
        }
        function restoreDraft(index) {
            const draft = current.draftChoices?.[index];
            delete current.draftChoices;
            if (!draft) return { ...current };
            current.sourceDraft = draft;
            current.conflict = Boolean(current.projectId && draft.baseContent !== current.saved);
            if (current.conflict) {
                current.draftContent = draft.content;
                current.draftUpdatedAt = draft.updatedAt;
                current.serverContent = current.content;
                current.serverRevision = current.revision;
            } else {
                current.content = draft.content;
                current.recovered = true;
            }
            return { ...current };
        }
        function open(record, { restore = true } = {}) {
            current = { ...record, saved: record.content, content: record.content, recovered: false, conflict: false };
            if (restore) {
                const drafts = readDrafts(record);
                if (drafts.length) {
                    current.draftChoices = drafts;
                    const [only] = drafts;
                    if (drafts.length === 1 && (only.legacy || only.name === journalKey(record) || !record.projectId)) {
                        return restoreDraft(0);
                    }
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
            if (!current || current.conflict || current.draftChoices) return;
            current.content = content;
            if (write(current) && !current.projectId) {
                removeEntry(current.sourceDraft);
                delete current.sourceDraft;
            }
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
        return { open, edit, flush, restoreDraft, resolveConflict, snapshot: () => current && { ...current },
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
