(() => {
    "use strict";
    const $ = id => document.getElementById(id);
    const esc = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
    const lang = () => window.mpbI18n?.getLanguage() === "en" ? "en" : "ru";
    const t = (key, params = {}) => window.mpbI18n?.t(`curricula.${key}`, key, params) || key;
    const text = key => `<span data-curricula="${key}">${t(key)}</span>`;
    const button = (key, action, cls = "") => `<button type="button" data-action="${action}" class="${cls}">${text(key)}</button>`;
    const field = (key, value = "", type = "text", extra = "") => `<label>${text(key)}<input name="${key}" type="${type}" value="${esc(value)}" required ${extra}></label>`;
    let plans = [], selected = null, busy = false, dirty = false, statusKey = "loading";
    const dirtySections = new Set();
    const requests = new Set(), rowPreviews = new WeakMap();
    let pollTimer = null, pollController = null, pollGeneration = 0, incomingPlan = null, pageActive = true;
    let previewTrigger = null, previousOverflow = "";
    const isProcessing = plan => ["queued", "processing"].includes(plan?.processing_state);

    function translate() {
        document.querySelectorAll("[data-curricula]").forEach(el => { el.textContent = t(el.dataset.curricula); });
        document.querySelectorAll("[data-curricula-aria]").forEach(el => { el.setAttribute("aria-label", t(el.dataset.curriculaAria)); });
        document.querySelectorAll("[data-curricula-date]").forEach(el => { el.textContent = date(el.dataset.curriculaDate); });
        document.querySelectorAll("[data-curricula-cadence]").forEach(el => { el.textContent = t("cadenceDays", {days:Number(selected?.refresh_interval_days) || 7}); });
        document.title = `${t("heading")} | Matplobbot`;
        renderStatus();
        renderProcessing();
        if ($("crop-preview")?.open) updatePreviewLabels();
    }
    function renderStatus() {
        $("curricula-status").textContent = t(statusKey);
        if (statusKey === "forbidden") {
            const link = document.createElement("a"); link.href = "/login"; link.textContent = t("login");
            $("curricula-status").append(" ", link);
        }
    }
    function status(key) { statusKey = key; renderStatus(); }
    function markDirty(section) {
        dirty = true; dirtySections.add(section);
        if (section === "assessment-form" && $("review-check")) $("review-check").checked = false;
    }
    async function request(path, options = {}) {
        const authToken = localStorage.getItem("jwt_token");
        if (!authToken) throw new Error("forbidden");
        const controller = new AbortController();
        const abort = () => controller.abort();
        options.signal?.addEventListener("abort", abort, {once:true});
        if (options.signal?.aborted) controller.abort();
        requests.add(controller);
        const timeout = setTimeout(() => controller.abort(), 90000);
        try {
            const response = await fetch(`${window.getMpbApiBase?.() || "/api"}/curricula${path}`, {
                ...options, signal: controller.signal, cache:"no-store",
                headers: { Authorization:`Bearer ${authToken || ""}`, ...options.headers }
            });
            if (authToken !== localStorage.getItem("jwt_token")) throw new Error("forbidden");
            if (!response.ok) throw new Error([401,403].includes(response.status) ? "forbidden" : response.status === 409 ? "conflict" : [400,413,422].includes(response.status) ? "invalid" : "error");
            if (response.status === 204) return null;
            const result = options.blob ? await response.blob() : await response.json();
            if (authToken !== localStorage.getItem("jwt_token")) throw new Error("forbidden");
            return result;
        } catch (error) {
            if (authToken !== localStorage.getItem("jwt_token")) throw new Error("forbidden");
            throw error;
        } finally { clearTimeout(timeout); requests.delete(controller); options.signal?.removeEventListener("abort", abort); }
    }
    function json(method, body) { return { method, headers:{"Content-Type":"application/json"}, body:JSON.stringify(body) }; }
    async function run(action, successKey = "saved", workingKey = "working") {
        if (busy) return;
        stopPolling();
        busy = true; status(workingKey); setDisabled(true);
        try { await action(); status(typeof successKey === "function" ? successKey() : successKey); }
        catch (error) {
            status(["forbidden","invalid","conflict","error","noDocument"].includes(error.message) ? error.message : "error");
            if (error.message === "forbidden") {
                hideForAuth();
            }
        } finally { busy = false; setDisabled(false); schedulePoll(); }
    }
    function setDisabled(value) {
        $("curricula-controls").querySelectorAll("fieldset,button").forEach(el => { el.disabled = value; });
        $("plan-select") && ($("plan-select").disabled = value);
        const publish = $("assessment-form")?.querySelector('[type="submit"]');
        if (publish) publish.disabled = value || isProcessing(selected) || Boolean(incomingPlan);
    }
    function stopPolling() {
        clearTimeout(pollTimer); pollTimer = null; pollGeneration++;
        pollController?.abort(); pollController = null;
    }
    function hideForAuth() {
        stopPolling(); requests.forEach(controller => controller.abort());
        closePreview(); $("curricula-controls").hidden = true; status("forbidden");
    }
    function schedulePoll(delay = 1800) {
        if (!pageActive || busy || !isProcessing(selected) || document.hidden || $("curricula-controls").hidden) return;
        clearTimeout(pollTimer);
        const id = selected.id, generation = pollGeneration;
        pollTimer = setTimeout(async () => {
            if (generation !== pollGeneration || selected?.id !== id) return;
            pollController = new AbortController();
            try {
                const plan = await request(`/${id}`, {signal:pollController.signal});
                if (generation !== pollGeneration || selected?.id !== id || !pageActive) return;
                plans = plans.map(item => item.id === id ? plan : item);
                const editing = dirty || $("crop-preview")?.open || document.activeElement?.closest("#assessment-form, #groups-form");
                if (!isProcessing(plan) && !editing) renderPlan(plan);
                else {
                    if (!isProcessing(plan)) incomingPlan = plan;
                    // Background progress must not replace the administrator's working forms.
                    selected = {...selected, processing_state:plan.processing_state, processing_error:plan.processing_error,
                        parse_method:plan.parse_method, warnings:plan.warnings};
                    renderProcessing(); setDisabled(busy);
                }
                schedulePoll();
            } catch (error) {
                if (generation !== pollGeneration || !pageActive) return;
                if (error.message === "forbidden") { hideForAuth(); return; }
                renderProcessing("pollFailed"); schedulePoll(10000);
            }
        }, delay);
    }
    function renderProcessing(note) {
        const el = $("document-processing");
        if (!el || !selected) return;
        const state = selected.processing_state || "ready";
        const ocr = ["ocr", "mixed"].includes(selected.parse_method);
        const noEngine = (selected.warnings || []).some(warning => /ocr_unavailable|tesseract.*(?:not found|not available|unavailable|missing|not installed)/i.test(warning));
        const ocrTimedOut = (selected.warnings || []).some(warning => /^ocr_timeout:/i.test(warning));
        const retryable = !isProcessing(selected) && (state === "error" || noEngine || ocrTimedOut);
        const draftKey = ocr && selected.pending_hash ? selected.candidates?.length ? "ocrDraft" : "ocrNoRows" : "";
        const key = note || (state === "error" ? selected.processing_error === "parse_timeout" ? "parseTimeout" : "parseError" : incomingPlan ? "resultsReady" : state === "queued" ? "parseQueued" : state === "processing" ? "parseProcessing" : noEngine ? "ocrUnavailable" : ocrTimedOut ? "parseTimeout" : draftKey);
        el.hidden = !key;
        el.classList.toggle("curricula-processing-error", retryable);
        const renderKey = `${key}|${lang()}|${Boolean(incomingPlan)}|${state}`;
        if (el.dataset.renderKey === renderKey) return;
        el.dataset.renderKey = renderKey;
        el.innerHTML = key ? `<p>${text(key)}</p>${incomingPlan ? button("showResults", "show-results") : retryable ? button("retryProcessing", "retry-processing") : ""}` : "";
    }
    function shell() {
        $("curricula-controls").innerHTML = `<section class="curricula-card"><label>${text("select")}<select id="plan-select"></select></label></section>
            <details class="curricula-card"><summary>${text("create")}</summary><p><a class="curricula-catalog" href="https://www.fa.ru/sveden/education/edupr/" target="_blank" rel="noopener noreferrer">${text("catalog")}</a></p><form id="plan-create"><fieldset class="curricula-grid">
            ${field("title", "", "text", 'maxlength="300"')}${field("source_url", "", "url", 'placeholder="https://www.fa.ru/upload/…pdf"')}
            ${field("program")}${field("profile")}${field("campus")}${field("admission_year", new Date().getFullYear(), "number", 'min="2000" max="2100"')}${field("study_form")}
            <div class="curricula-actions curricula-wide"><button class="primary" type="submit">${text("save")}</button></div></fieldset></form></details><div id="plan-detail"></div>
            <dialog id="crop-preview" class="curricula-preview" aria-labelledby="crop-title" aria-describedby="crop-hint"><header><h2 id="crop-title"></h2>${button("closePreview","close-preview")}</header><p id="crop-hint" class="curricula-muted" data-curricula="cropHint">${t("cropHint")}</p><p id="crop-meta" class="curricula-muted"></p><div class="curricula-preview-image" tabindex="0" role="region" data-curricula-aria="sourceCrop" aria-label="${t("sourceCrop")}"></div></dialog>`;
        $("crop-preview").querySelector("button").addEventListener("click", closePreview);
        $("crop-preview").addEventListener("keydown", event => {
            if (event.key !== "Tab") return;
            const first = $("crop-preview").querySelector("button"), last = $("crop-preview").querySelector(".curricula-preview-image");
            if (event.shiftKey && document.activeElement === first || !event.shiftKey && document.activeElement === last) {
                event.preventDefault(); (event.shiftKey ? last : first).focus();
            }
        });
        $("crop-preview").addEventListener("click", event => { if (event.target === $("crop-preview")) closePreview(); });
        $("crop-preview").addEventListener("close", () => {
            $("crop-preview").querySelector(".curricula-preview-image").replaceChildren();
            document.body.style.overflow = previousOverflow;
            if (previewTrigger?.isConnected) previewTrigger.focus();
            previewTrigger = null;
        });
        $("plan-create").addEventListener("submit", event => {
            event.preventDefault();
            if (dirty && !window.confirm(t("unsaved"))) return;
            const data = Object.fromEntries(new FormData(event.target)); data.admission_year = Number(data.admission_year);
            run(async () => {
                const plan = await request("", json("POST", data));
                await load(plan.id); event.target.reset(); event.target.closest("details").open = false;
            });
        });
        $("plan-select").addEventListener("change", () => {
            const id = $("plan-select").value;
            if (dirty && !window.confirm(t("unsaved"))) { $("plan-select").value = selected?.id || ""; return; }
            if (!id) { renderPlan(null); return; }
            run(async () => {
                try { renderPlan(await request(`/${encodeURIComponent(id)}`)); }
                finally { $("plan-select").value = selected?.id || ""; }
            }, "loaded", "loading");
        });
        $("plan-detail").addEventListener("input", event => {
            const formId = event.target.closest("form")?.id;
            if (["assessment-form", "groups-form"].includes(formId)) markDirty(formId);
        });
        $("plan-detail").addEventListener("click", event => handleAction(event.target.closest("[data-action]")?.dataset.action, event));
    }
    async function load(id = selected?.id) {
        const data = await request(""); plans = Array.isArray(data) ? data : data.items || data.curricula || [];
        $("plan-select").innerHTML = `<option value="" data-curricula="choose">${t("choose")}</option>` + plans.map(plan => `<option value="${plan.id}">${esc(plan.title)} · ${esc(plan.admission_year)}</option>`).join("");
        const plan = plans.find(plan => String(plan.id) === String(id));
        renderPlan(plan ? await request(`/${plan.id}`) : null);
    }
    function date(value) { return value ? new Date(value).toLocaleString(lang() === "ru" ? "ru-RU" : "en-GB", {timeZone:"Europe/Moscow"}) : t("never"); }
    function renderPlan(plan) {
        stopPolling(); closePreview(); incomingPlan = null;
        selected = plan; dirty = false; dirtySections.clear(); $("plan-select").value = plan?.id || "";
        if (!plan) { $("plan-detail").replaceChildren(); return; }
        const source = /^https:\/\/(www\.)?fa\.ru\/upload\//i.test(plan.source_url) ? plan.source_url : "";
        $("plan-detail").innerHTML = `<section class="curricula-card"><h2>${text("document")}</h2><h3>${esc(plan.title)}</h3>
            <p class="curricula-muted">${[plan.program,plan.profile,plan.campus,plan.admission_year,plan.study_form].map(esc).join(" · ")}</p>
            <div class="curricula-meta"><span data-curricula="${esc(plan.status)}">${t(plan.status)}</span><span>${text("checked")}: <time data-curricula-date="${esc(plan.checked_at || "")}">${date(plan.checked_at)}</time></span><span>${text("next")}: <time data-curricula-date="${esc(plan.next_check_at || "")}">${date(plan.next_check_at)}</time></span></div>
            ${plan.last_error ? `<p class="curricula-note">${text("sourceError")}</p>` : ""}
            ${plan.pending_hash && plan.published_hash && plan.pending_hash !== plan.published_hash ? `<p class="curricula-note">${text("pending")}</p>` : ""}
            <div id="document-processing" class="curricula-processing" role="status" aria-live="polite" hidden></div>
            <p class="curricula-muted" data-curricula-cadence>${t("cadenceDays", {days:Number(plan.refresh_interval_days) || 7})}</p><div class="curricula-actions">${button("refresh","refresh","primary")}${button("open","open")}${source ? `<a class="curricula-link" href="${esc(source)}" target="_blank" rel="noopener noreferrer">${text("original")}</a>` : ""}</div>
            ${plan.warnings?.length ? `<details class="curricula-note"><summary>${text("diagnostics")}</summary>${plan.warnings.map(warning=>`<p>${esc(warning)}</p>`).join("")}</details>` : ""}
            <form id="document-upload"><fieldset><div class="curricula-actions"><label>${text("file")}<input type="file" id="document-file" accept="application/pdf,.pdf" required></label><button type="submit">${text("upload")}</button></div></fieldset></form></section>
            <section class="curricula-card"><h2>${text("review")}</h2><p class="curricula-muted">${text("reviewHint")}</p>
            <form id="assessment-form"><fieldset><div class="curricula-scroll"><table><thead><tr>${["code","discipline","semester","kind","page","evidence","remove"].map(key=>`<th>${text(key)}</th>`).join("")}</tr></thead><tbody id="assessment-rows"></tbody></table></div>
            <p id="assessment-empty" class="curricula-muted">${text("noRows")}</p><div class="curricula-actions">${button("addRow","add-row")}</div>
            <label class="curricula-review-check"><input id="review-check" type="checkbox" required>${text("reviewed")}</label><div class="curricula-actions"><button class="primary" type="submit">${text("publish")}</button></div></fieldset></form></section>
            <section class="curricula-card"><h2>${text("groups")}</h2><p class="curricula-muted">${text("groupHint")}</p><form id="groups-form"><fieldset><div id="group-rows"></div><p id="groups-empty" class="curricula-muted">${text("emptyGroups")}</p><div class="curricula-actions">${button("addGroup","add-group")}<button class="primary" type="submit">${text("saveGroups")}</button></div></fieldset></form></section>
            <section class="curricula-card curricula-danger"><h2>${text("deletePlan")}</h2><p class="curricula-muted">${text("deleteHint")}</p>${button("deletePlan","delete-plan","danger")}</section>`;
        // A changed, unreadable PDF must never inherit assessments from the old PDF.
        (plan.pending_hash ? plan.candidates || [] : plan.published_assessments || []).forEach(addAssessment);
        (plan.groups || []).forEach(addGroup);
        updateEmpty();
        $("review-check").addEventListener("input", event => event.stopPropagation());
        $("document-upload").addEventListener("submit", event => {
            event.preventDefault(); const file = $("document-file").files[0];
            if (!file || file.size > 20 * 1024 * 1024) { status("invalid"); return; }
            if (dirty && !window.confirm(t("unsaved"))) return;
            run(async () => { await request(`/${selected.id}/document`, {method:"PUT",headers:{"Content-Type":"application/pdf"},body:file}); await load(); if (selected.last_error) throw new Error("error"); }, () => isProcessing(selected) ? "backgroundAccepted" : "saved", "uploading");
        });
        $("assessment-form").addEventListener("submit", event => {
            event.preventDefault();
            const expectedHash = selected.pending_hash || selected.published_hash;
            if (!expectedHash) { status("noDocument"); return; }
            if (dirtySections.has("groups-form") && !window.confirm(t("unsaved"))) return;
            if (isProcessing(selected) || incomingPlan) return;
            const assessments = [...$("assessment-rows").children].map(row => Object.fromEntries(["discipline_code","discipline_name","semester","kind","page","evidence"].map(name => {
                const value = row.querySelector(`[name="${name}"]`).value;
                return [name, ["semester","page"].includes(name) ? Number(value) : value.trim()];
            })));
            run(async () => { await request(`/${selected.id}/publish`, json("POST",{expected_hash:expectedHash,assessments})); await load(); });
        });
        $("groups-form").addEventListener("submit", event => {
            event.preventDefault();
            if (dirtySections.has("assessment-form") && !window.confirm(t("unsaved"))) return;
            const groups = [...$("group-rows").children].map(row => ({group_id:row.querySelector('[name="groupId"]').value.trim(),group_name:row.querySelector('[name="groupName"]').value.trim(),terms:[...row.querySelectorAll(".curricula-term")].map(term => ({semester:Number(term.querySelector('[name="semester"]').value), start_date:term.querySelector('[name="start"]').value, end_date:term.querySelector('[name="end"]').value}))}));
            run(async () => { await request(`/${selected.id}/groups`,json("PUT",{groups})); await load(); });
        });
        setDisabled(busy);
        renderProcessing(); schedulePoll();
    }
    function addAssessment(row = {}) {
        const tr = document.createElement("tr");
        tr.innerHTML = [
            `<input name="discipline_code" data-curricula-aria="code" aria-label="${t("code")}" value="${esc(row.discipline_code)}" required maxlength="100">`,
            `<input name="discipline_name" data-curricula-aria="discipline" aria-label="${t("discipline")}" value="${esc(row.discipline_name)}" required maxlength="500">`,
            `<input name="semester" data-curricula-aria="semester" aria-label="${t("semester")}" type="number" min="1" max="16" value="${row.semester || 1}" required>`,
            `<select name="kind" data-curricula-aria="kind" aria-label="${t("kind")}">${["exam","pass","graded_pass","coursework","course_project"].map(kind=>`<option value="${kind}" ${kind === row.kind ? "selected" : ""} data-curricula="${kind}">${t(kind)}</option>`).join("")}</select>`,
            `<input name="page" data-curricula-aria="page" aria-label="${t("page")}" type="number" min="1" max="500" value="${row.page || 1}" required>`,
            `<textarea name="evidence" data-curricula-aria="evidence" aria-label="${t("evidence")}" required maxlength="2000">${esc(row.evidence)}</textarea>${row.ocr ? `<div class="curricula-ocr-label">${text("ocrCheck")}</div>` : ""}${validCrop(row.ocr?.crop_png_base64) ? button("sourceCrop","source-crop", "curricula-crop-button") : ""}`,button("remove","remove-row")
        ].map(html=>`<td>${html}</td>`).join("");
        if (row.ocr) rowPreviews.set(tr, {ocr:row.ocr, name:row.discipline_name || "", page:row.page || 1});
        $("assessment-rows").append(tr);
    }
    function validCrop(value) {
        // Only bounded PNG data supplied by the authenticated API is an image source.
        if (typeof value !== "string" || value.length > 480000 || !/^iVBORw0KGgo[A-Za-z0-9+/]*={0,2}$/.test(value)) return false;
        try {
            const bytes = atob(value.slice(0, 44));
            const read = offset => [0,1,2,3].reduce((n,index) => n * 256 + bytes.charCodeAt(offset + index), 0);
            return bytes.slice(12,16) === "IHDR" && read(16) > 0 && read(20) > 0 && read(16) <= 4096 && read(20) <= 4096;
        } catch (_) { return false; }
    }
    function updatePreviewLabels() {
        const row = previewTrigger?.closest("tr"), preview = row && rowPreviews.get(row);
        if (!preview) return;
        $("crop-title").textContent = t("sourceCrop");
        $("crop-meta").textContent = t("cropPage", {page:preview.page, name:preview.name});
        $("crop-preview").querySelector("img")?.setAttribute("alt", t("cropAlt", {page:preview.page, name:preview.name}));
    }
    function showPreview(trigger) {
        const preview = rowPreviews.get(trigger.closest("tr"));
        if (!preview || !validCrop(preview.ocr.crop_png_base64)) return;
        previewTrigger = trigger;
        const img = document.createElement("img"); img.decoding = "async";
        img.src = `data:image/png;base64,${preview.ocr.crop_png_base64}`;
        $("crop-preview").querySelector(".curricula-preview-image").replaceChildren(img);
        updatePreviewLabels(); previousOverflow = document.body.style.overflow; document.body.style.overflow = "hidden";
        $("crop-preview").showModal(); $("crop-preview").querySelector("button").focus();
    }
    function closePreview() { if ($("crop-preview")?.open) $("crop-preview").close(); }
    function addGroup(group = {}) {
        const el = document.createElement("div"); el.className = "curricula-group";
        el.innerHTML = `<div class="curricula-grid">${field("groupId",group.group_id)}${field("groupName",group.group_name)}</div><div class="curricula-terms"></div><div class="curricula-actions">${button("addTerm","add-term")}${button("remove","remove-group")}</div>`;
        $("group-rows").append(el); (group.terms?.length ? group.terms : [{}]).forEach(term => addTerm(el,term));
    }
    function addTerm(group, term = {}) {
        const el = document.createElement("div"); el.className = "curricula-term";
        el.innerHTML = `${field("semester",term.semester || 1,"number",'min="1" max="16"')}${field("start",term.start_date,"date")}${field("end",term.end_date,"date")}${button("remove","remove-term")}`;
        group.querySelector(".curricula-terms").append(el);
    }
    function updateEmpty() {
        $("assessment-empty").hidden = Boolean($("assessment-rows").children.length);
        $("groups-empty").hidden = Boolean($("group-rows").children.length);
    }
    function handleAction(action, event) {
        if (!action || busy) return;
        if (action === "source-crop") { showPreview(event.target.closest("button")); return; }
        if (action === "show-results") {
            if (!incomingPlan || dirty && !window.confirm(t("unsaved"))) return;
            renderPlan(incomingPlan); status("resultsLoaded"); return;
        }
        if (action === "retry-processing") {
            if (dirty && !window.confirm(t("unsaved"))) return;
            run(async () => { await request(`/${selected.id}/reprocess`, {method:"POST"}); await load(); }, () => isProcessing(selected) ? "backgroundAccepted" : "saved"); return;
        }
        if (action === "delete-plan") {
            if (!window.confirm(t("deleteConfirm", {title:selected.title}))) return;
            run(async () => { await request(`/${selected.id}`, {method:"DELETE"}); await load(null); }, "deleted"); return;
        }
        if (action === "refresh") {
            if (dirty && !window.confirm(t("unsaved"))) return;
            run(async () => { await request(`/${selected.id}/refresh`,{method:"POST"}); await load(); if (selected.last_error) throw new Error("error"); }, () => isProcessing(selected) ? "backgroundAccepted" : "saved", "sourceFetching"); return;
        }
        if (action === "open") {
            run(async () => {
                const blob = await request(`/${selected.id}/document`,{blob:true});
                const url = URL.createObjectURL(blob); const a = document.createElement("a");
                a.href = url; a.download = `curriculum-${selected.id}.pdf`; a.click(); setTimeout(()=>URL.revokeObjectURL(url),60000);
            }); return;
        }
        if (action === "add-row") addAssessment();
        if (action === "remove-row") event.target.closest("tr").remove();
        if (action === "add-group") addGroup();
        if (action === "remove-group") event.target.closest(".curricula-group").remove();
        if (action === "add-term") addTerm(event.target.closest(".curricula-group"));
        if (action === "remove-term") event.target.closest(".curricula-term").remove();
        markDirty(["add-row","remove-row"].includes(action) ? "assessment-form" : "groups-form"); updateEmpty();
    }
    window.addEventListener("beforeunload", event => { if (dirty) { event.preventDefault(); event.returnValue = ""; } });
    window.addEventListener("pagehide", () => { pageActive = false; stopPolling(); requests.forEach(controller => controller.abort()); closePreview(); });
    window.addEventListener("pageshow", () => { pageActive = true; schedulePoll(); });
    document.addEventListener("visibilitychange", () => { if (document.hidden) stopPolling(); else schedulePoll(); });
    window.addEventListener("storage", event => { if (event.key === "jwt_token") hideForAuth(); });
    window.addEventListener("mpb-auth-token-changed", hideForAuth);
    window.addEventListener("mpb-auth-ready", event => { if (!event.detail?.user) hideForAuth(); });
    window.mpbI18n?.registerTranslator(translate);
    window.mpbI18n.ready.then(() => {
        shell(); translate();
        run(async () => { await load(); $("curricula-controls").hidden = false; });
    });
})();
