(() => {
  const apiBase = window.getMpbApiBase ? window.getMpbApiBase() : (window.__MPB_API_BASE__ || "/api");
  const status = document.getElementById("status");
  const profile = document.getElementById("profile");
  const actions = document.getElementById("actions");
  const actionsBody = document.getElementById("actionsBody");
  const messageComposer = document.getElementById("messageComposer");
  const messageSyncStatus = document.getElementById("messageSyncStatus");
  const messageList = document.getElementById("messageList");
  const messageEmpty = document.getElementById("messageEmpty");
  const messageHistoryMeta = document.getElementById("messageHistoryMeta");
  const loadOlderMessagesButton = document.getElementById("loadOlderMessages");
  const messageForm = document.getElementById("messageForm");
  const messageInput = document.getElementById("messageInput");
  const messageCounter = document.getElementById("messageCounter");
  const messageStatus = document.getElementById("messageStatus");
  const sendMessageButton = document.getElementById("sendMessageButton");
  const maxMessageLength = Number(messageInput?.maxLength) || 4096;
  const userId = new URLSearchParams(window.location.search).get("user_id");
  const messages = new Map();
  const loadedPages = new Set();
  let nextOlderPage = 2;
  let hasOlderMessages = false;
  let messagePollTimer = null;

  const escapeHtml = (value) => String(value ?? "").replace(/[&<>'"]/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[char]));

  const fail = (message) => {
    status.className = "rounded-xl border border-red-200 bg-red-50 p-5 text-sm text-red-700";
    status.textContent = message;
  };

  const setMessageStatus = (message, kind = "info") => {
    if (!messageStatus) return;
    messageStatus.className = `text-sm ${kind === "error" ? "text-red-700" : kind === "success" ? "text-emerald-700" : "text-slate-600"}`;
    messageStatus.textContent = message;
  };

  const setMessageSyncStatus = (message, kind = "info") => {
    if (!messageSyncStatus) return;
    messageSyncStatus.className = `rounded-full bg-white px-3 py-1 text-xs font-medium ${kind === "error" ? "text-red-700" : "text-blue-700"}`;
    messageSyncStatus.textContent = message;
  };

  const findNextOlderPage = () => {
    let page = 2;
    while (loadedPages.has(page)) page += 1;
    return page;
  };

  const updateMessageCounter = () => {
    if (messageCounter && messageInput) {
      messageCounter.textContent = `${messageInput.value.length} / ${maxMessageLength}`;
    }
  };

  const formatMessageTime = (timestamp) => {
    const date = new Date(timestamp);
    if (Number.isNaN(date.getTime())) return timestamp || "";
    return new Intl.DateTimeFormat(undefined, {
      dateStyle: "short",
      timeStyle: "short",
    }).format(date);
  };

  const renderMessages = () => {
    if (!messageList || !messageEmpty) return;
    const sortedMessages = [...messages.values()].sort((left, right) => {
      const leftTime = Date.parse(left.timestamp) || 0;
      const rightTime = Date.parse(right.timestamp) || 0;
      return leftTime - rightTime || Number(left.id) - Number(right.id);
    });

    messageList.querySelectorAll("[data-message-id]").forEach((node) => node.remove());
    messageEmpty.classList.toggle("hidden", sortedMessages.length > 0);

    sortedMessages.forEach((message) => {
      const outgoing = message.direction === "outgoing";
      const wrapper = document.createElement("div");
      wrapper.dataset.messageId = String(message.id);
      wrapper.className = `flex ${outgoing ? "justify-end" : "justify-start"}`;
      const safeText = escapeHtml(message.text).replace(/\r?\n/g, "<br>");
      wrapper.innerHTML = `<article class="max-w-[85%] rounded-2xl px-4 py-3 shadow-sm ${outgoing ? "rounded-br-md bg-blue-600 text-white" : "rounded-bl-md border border-slate-200 bg-white text-slate-900"}"><p class="whitespace-pre-wrap break-words text-sm leading-6">${safeText}</p><div class="mt-2 flex items-center gap-2 text-[11px] ${outgoing ? "text-blue-100" : "text-slate-500"}"><span>${outgoing ? "Bot" : "User"}</span><span aria-hidden="true">·</span><time datetime="${escapeHtml(message.timestamp)}">${escapeHtml(formatMessageTime(message.timestamp))}</time></div></article>`;
      messageList.appendChild(wrapper);
    });

    if (messageHistoryMeta) {
      messageHistoryMeta.textContent = sortedMessages.length
        ? `${sortedMessages.length} messages loaded`
        : "";
    }
    if (loadOlderMessagesButton) {
      loadOlderMessagesButton.classList.toggle("hidden", !hasOlderMessages);
    }
  };

  const fetchJson = async (url, options = {}) => {
    const response = await fetch(url, {
      ...options,
      headers: {
        Accept: "application/json",
        Authorization: `Bearer ${token}`,
        ...(options.headers || {}),
      },
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(response.status === 403 ? "Admin access required." : (data.detail || `Request failed (${response.status})`));
    }
    return data;
  };

  const loadMessages = async ({ page = 1, silent = false } = {}) => {
    try {
      if (!silent) setMessageSyncStatus("Loading messages…");
      const data = await fetchJson(`${apiBase}/stats/users/${encodeURIComponent(userId)}/messages?page=${page}&page_size=50`);
      (data.messages || []).forEach((message) => messages.set(String(message.id), message));
      loadedPages.add(page);
      const pagination = data.pagination || {};
      if (page === 1) {
        nextOlderPage = findNextOlderPage();
        hasOlderMessages = Number(pagination.current_page || 1) < Number(pagination.total_pages || 0);
      } else {
        nextOlderPage = findNextOlderPage();
        hasOlderMessages = page < Number(pagination.total_pages || page);
      }
      renderMessages();
      setMessageSyncStatus("Updating automatically");
    } catch (error) {
      setMessageSyncStatus(error.message || "Unable to load messages.", "error");
    }
  };

  const startMessagePolling = () => {
    if (messagePollTimer) window.clearInterval(messagePollTimer);
    messagePollTimer = window.setInterval(() => {
      if (!document.hidden) void loadMessages({ page: 1, silent: true });
    }, 10000);
  };

  const sendMessage = async () => {
    if (!messageInput || !sendMessageButton) return;
    const text = messageInput.value.trim();
    if (!text) {
      setMessageStatus("Write a message before sending.", "error");
      messageInput.focus();
      return;
    }

    sendMessageButton.disabled = true;
    setMessageStatus("Sending…", "info");
    try {
      const data = await fetchJson(`${apiBase}/stats/users/${encodeURIComponent(userId)}/send_message`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
      messageInput.value = "";
      updateMessageCounter();
      const correlation = data.correlation_id ? ` Correlation ID: ${data.correlation_id}` : "";
      setMessageStatus(`Message sent from the bot.${correlation}`, "success");
      await loadMessages({ page: 1, silent: true });
    } catch (error) {
      setMessageStatus(error.message || "Unable to send the message.", "error");
    } finally {
      sendMessageButton.disabled = false;
    }
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

  messageInput?.addEventListener("input", updateMessageCounter);
  messageForm?.addEventListener("submit", (event) => {
    event.preventDefault();
    void sendMessage();
  });
  loadOlderMessagesButton?.addEventListener("click", () => {
    if (!loadedPages.has(nextOlderPage) && hasOlderMessages) {
      void loadMessages({ page: nextOlderPage });
    }
  });
  updateMessageCounter();

  fetchJson(`${apiBase}/stats/users/${encodeURIComponent(userId)}/profile?page=1&page_size=50`)
    .then(async (data) => {
      const user = data.user_details || {};
      status.className = "hidden";
      profile.className = "mt-4 rounded-xl border border-slate-200 bg-white p-5";
      profile.innerHTML = `<div class="flex flex-wrap items-baseline justify-between gap-2"><h2 class="text-xl font-semibold">${escapeHtml(user.full_name || user.username || userId)}</h2><span class="text-sm text-slate-500">Telegram ID: ${escapeHtml(user.user_id || userId)}</span></div><p class="mt-2 text-sm text-slate-600">@${escapeHtml(user.username || "—")} · ${escapeHtml(user.total_actions || 0)} total actions</p>`;
      messageComposer?.classList.remove("hidden");
      actions.className = "mt-4 overflow-hidden rounded-xl border border-slate-200 bg-white";
      actionsBody.innerHTML = (data.actions || []).map((action) => `<tr class="border-t border-slate-100"><td class="px-5 py-3 whitespace-nowrap">${escapeHtml(action.timestamp)}</td><td class="px-5 py-3">${escapeHtml(action.action_type)}</td><td class="px-5 py-3 text-slate-600">${escapeHtml(action.action_details || "—")}</td></tr>`).join("") || `<tr><td class="px-5 py-4 text-slate-500" colspan="3">No actions found.</td></tr>`;
      await loadMessages();
      startMessagePolling();
    })
    .catch((error) => fail(error.message || "Unable to load user details."));
})();
