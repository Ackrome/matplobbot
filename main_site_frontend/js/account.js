(() => {
    "use strict";
    const api = window.getMpbApiBase ? window.getMpbApiBase() : "/api";
    const byId = (id) => document.getElementById(id);
    const t = (key, fallback, params = {}) => window.mpbI18n?.t?.(key, fallback, params) || fallback;
    let receipt = null;
    let receiptExpires = 0;
    let exportAuthToken = null;
    let busy = false;
    let signedIn = false;
    let accountName = "";
    let accountId = null;
    let profileAuthToken = null;
    let statusKey = "";
    let statusFallback = "";

    function token() { return localStorage.getItem("jwt_token"); }
    byId("account-logout-all").addEventListener("click", () => window.performLogout(true));
    function status(key, fallback) {
        statusKey = key;
        statusFallback = fallback;
        byId("account-status").textContent = t(key, fallback);
        if(key.startsWith("account.export")) byId("account-export-status").textContent=t(key,fallback);
    }
    function updateControls() {
        const ready = receipt && Date.now() < receiptExpires && token() === exportAuthToken;
        byId("account-export").disabled = busy;
        byId("account-delete-fields").disabled = busy || !ready;
        byId("account-delete").disabled = busy || !ready ||
            byId("account-confirmation").value !== "DELETE" || !byId("account-acknowledge").checked;
    }
    async function request(path, options = {}) {
        const response = await fetch(`${api}${path}`, {
            ...options, cache: "no-store",
            headers: { Authorization: `Bearer ${token()}`, ...options.headers },
        });
        if (response.status === 401) {
            signedIn = false;
            receipt = null;
            byId("account-controls").hidden = true;
            byId("account-login").hidden = false;
            throw new Error("unauthorized");
        }
        if (!response.ok) throw new Error(response.status === 409 ? "expired" : "request");
        return response.json();
    }
    byId("account-export").addEventListener("click", async () => {
        busy = true;
        receipt = null;
        updateControls();
        status("account.exporting", "Preparing your export…");
        try {
            const authToken = token();
            const data = await request("/auth/account/export");
            if (token() !== authToken || authToken !== profileAuthToken ||
                String(data.account?.id) !== String(accountId)) throw new Error("unauthorized");
            const prefix = `mpb-studio-v1:${encodeURIComponent(String(accountId))}:`;
            data.local_studio_drafts = Object.fromEntries(Object.keys(localStorage)
                .filter((key) => key.startsWith(prefix)).map((key) => [key, localStorage.getItem(key)]));
            if(byId('account-export-format').value==='zip'){
                const files=[{name:'account.json',text:JSON.stringify(data,null,2)},{name:'README.txt',text:t('ux.exportReadme','Your data export. account.json contains settings and local drafts; projects/ contains the original Studio files. Keep this archive private.')}];
                for(const file of data.project_files||[]){const project=(data.projects||[]).find(p=>p.id===file.project_id);const name=`projects/${file.project_id}-${MpbArchive.safePath(project?.name||'project')}/${MpbArchive.safePath(file.file_path)}`;const binary=file.content_binary;files.push(binary?.encoding==='base64'?{name,bytes:Uint8Array.from(atob(binary.data),c=>c.charCodeAt(0))}:{name,text:file.content_text||''});}
                MpbArchive.download(MpbArchive.zip(files),'matplobbot-account.zip');
            }else MpbArchive.download(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}),'matplobbot-account.json');
            receipt = data.deletion_token;
            receiptExpires = Date.now() + 15 * 60 * 1000;
            exportAuthToken = authToken;
            status("account.exported", "Export downloaded. Save it before confirming deletion.");
        } catch (error) {
            status(error.message === "unauthorized" ? "account.signIn" : "account.exportFailed",
                error.message === "unauthorized" ? "Sign in to manage your account." : "Export failed. No data was deleted; try again.");
        } finally { busy = false; updateControls(); }
    });
    byId("account-confirmation").addEventListener("input", updateControls);
    byId("account-acknowledge").addEventListener("change", updateControls);
    byId("account-delete").addEventListener("click", async () => {
        updateControls();
        if (byId("account-delete").disabled) return;
        busy = true;
        updateControls();
        status("account.deleting", "Deleting your account…");
        try {
            await request("/auth/account", {
                method: "DELETE", headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ confirmation: "DELETE", export_token: receipt }),
            });
            receipt = null;
            signedIn = false;
            const prefix = `mpb-studio-v1:${encodeURIComponent(String(accountId))}:`;
            Object.keys(localStorage).filter((key) => key.startsWith(prefix))
                .forEach((key) => localStorage.removeItem(key));
            localStorage.removeItem("mpb-last-project:" + encodeURIComponent(String(accountId)));
            if (token() === exportAuthToken) localStorage.removeItem("jwt_token");
            byId("account-controls").hidden = true;
            byId("account-identity").textContent = "";
            window.dispatchEvent(new CustomEvent("mpb-auth-token-changed"));
            status("account.deleted", "Your account has been deleted. Previous website sessions are no longer valid.");
        } catch (error) {
            if (error.message === "expired") receipt = null;
            status(error.message === "expired" ? "account.exportRequirement" : "account.deleteFailed",
                error.message === "expired" ? "Download a fresh export first." : "Deletion could not be confirmed. Check your account before trying again.");
        } finally { busy = false; updateControls(); }
    });
    function translateRuntime() {
        if (signedIn) byId("account-identity").textContent = t("account.signedIn", "Signed in as {name}", { name: accountName });
        if (statusKey) status(statusKey, statusFallback);
        byId("account-language").value=window.mpbI18n.getLanguage();
    }
    window.addEventListener("mpb-language-change", translateRuntime);
    window.addEventListener("mpb-auth-token-changed", () => {
        if (signedIn && token() !== profileAuthToken) { receipt = null; location.reload(); }
    });
    window.addEventListener("storage", (event) => {
        if (event.key === "jwt_token") { receipt = null; location.reload(); }
    });
    byId('account-language').addEventListener('change',event=>window.mpbI18n.setLanguage(event.target.value));
    byId('account-theme').addEventListener('change',event=>{const isDark=event.target.value==='dark';localStorage.setItem('theme',event.target.value);document.documentElement.classList.toggle('dark',isDark);document.documentElement.dataset.theme=event.target.value;window.dispatchEvent(new CustomEvent('mpb-theme-change',{detail:{isDark}}));});
    setInterval(updateControls, 15000);
    (async () => {
        await window.mpbI18n?.ready;
        if (!token()) { byId("account-login").hidden = false; return; }
        try {
            const authToken = token();
            const user = await request("/auth/me");
            if (token() !== authToken) { location.reload(); return; }
            signedIn = true;
            profileAuthToken = authToken;
            accountId = user.id;
            accountName = user.username || "User";
            byId('account-telegram').dataset.i18n=user.telegram_id?'ux.telegramLinked':'ux.telegramUnlinked';byId('account-telegram').textContent=t(byId('account-telegram').dataset.i18n,'');
            byId('account-language').value=window.mpbI18n.getLanguage();
            byId('account-theme').value=document.documentElement.classList.contains('dark')?'dark':'light';
            translateRuntime();
            byId("account-controls").hidden = false;
            window.MpbAccountSubscriptions?.init(user);
        } catch (error) {
            status("account.loadFailed", "Account information is unavailable. Please sign in or try again later.");
        }
    })();
})();
