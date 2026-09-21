(() => {
  const apiBase = window.getMpbApiBase ? window.getMpbApiBase() : (window.__MPB_API_BASE__ || "/api");
  const status = document.getElementById("status");
  const profile = document.getElementById("profile");
  const actions = document.getElementById("actions");
  const actionsBody = document.getElementById("actionsBody");
  const userId = new URLSearchParams(window.location.search).get("user_id");
  const escapeHtml = (value) => String(value ?? "").replace(/[&<>'"]/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[char]));

  const fail = (message) => {
    status.className = "rounded-xl border border-red-200 bg-red-50 p-5 text-sm text-red-700";
    status.textContent = message;
  };

  if (!userId || !/^\d+$/.test(userId)) {
    fail("A valid user id is required.");
    return;
  }

  const token = localStorage.getItem("jwt_token");
  if (!token) {
    fail("Administrator authentication is required. Please sign in first.");
    return;
  }

  fetch(`${apiBase}/stats/users/${encodeURIComponent(userId)}/profile?page=1&page_size=50`, {
    headers: { Authorization: `Bearer ${token}`, Accept: "application/json" },
  }).then(async (response) => {
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(response.status === 403 ? "Admin access required." : (data.detail || "Unable to load user details."));
    return data;
  }).then((data) => {
    const user = data.user_details || {};
    status.className = "hidden";
    profile.className = "mt-4 rounded-xl border border-slate-200 bg-white p-5";
    profile.innerHTML = `<div class="flex flex-wrap items-baseline justify-between gap-2"><h2 class="text-xl font-semibold">${escapeHtml(user.full_name || user.username || userId)}</h2><span class="text-sm text-slate-500">Telegram ID: ${escapeHtml(user.user_id || userId)}</span></div><p class="mt-2 text-sm text-slate-600">@${escapeHtml(user.username || "—")} · ${escapeHtml(user.total_actions || 0)} total actions</p>`;
    actions.className = "mt-4 overflow-hidden rounded-xl border border-slate-200 bg-white";
    actionsBody.innerHTML = (data.actions || []).map((action) => `<tr class="border-t border-slate-100"><td class="px-5 py-3 whitespace-nowrap">${escapeHtml(action.timestamp)}</td><td class="px-5 py-3">${escapeHtml(action.action_type)}</td><td class="px-5 py-3 text-slate-600">${escapeHtml(action.action_details || "—")}</td></tr>`).join("") || `<tr><td class="px-5 py-4 text-slate-500" colspan="3">No actions found.</td></tr>`;
  }).catch((error) => fail(error.message || "Unable to load user details."));
})();
