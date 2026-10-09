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
    function status(key, fallback) {
        statusKey = key;
        statusFallback = fallback;
        byId("account-status").textContent = t(key, fallback);
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
            const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
            const link = document.createElement("a");
            link.href = url;
            link.download = "matplobbot-account.json";
            document.body.append(link);
            link.click();
            link.remove();
            setTimeout(() => URL.revokeObjectURL(url), 1000);
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
        if (statusKey) byId("account-status").textContent = t(statusKey, statusFallback);
    }
    window.addEventListener("mpb-language-change", translateRuntime);
    window.addEventListener("mpb-auth-token-changed", () => {
        if (signedIn && token() !== profileAuthToken) { receipt = null; location.reload(); }
    });
    window.addEventListener("storage", (event) => {
        if (event.key === "jwt_token") { receipt = null; location.reload(); }
    });
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
            translateRuntime();
            byId("account-controls").hidden = false;
        } catch (error) {
            status("account.loadFailed", "Account information is unavailable. Please sign in or try again later.");
        }
    })();
})();
