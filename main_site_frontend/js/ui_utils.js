(function initMpbUiUtils() {
    function normalizeApiBase(rawValue) {
        if (typeof rawValue !== "string") return "";
        const trimmed = rawValue.trim();
        if (!trimmed) return "";
        if (trimmed === "/") return "";
        return trimmed.replace(/\/+$/, "");
    }

    function resolveApiBase() {
        const fromGlobal =
            typeof window.__MPB_API_BASE__ === "string" ? window.__MPB_API_BASE__ : "";
        const fromMeta =
            document.querySelector('meta[name="mpb-api-base"]')?.getAttribute("content") || "";
        const normalized = normalizeApiBase(fromGlobal) || normalizeApiBase(fromMeta);
        return normalized || "/api";
    }

    window.MPB_API_BASE = resolveApiBase();
    window.getMpbApiBase = function getMpbApiBase() {
        return window.MPB_API_BASE || "/api";
    };

    const popupState = {
        mounted: false,
        containerId: "mpbPopupContainer",
        styleId: "mpbPopupStyle",
    };

    function mountPopupUi() {
        if (popupState.mounted) return;

        if (!document.getElementById(popupState.styleId)) {
            const style = document.createElement("style");
            style.id = popupState.styleId;
            style.textContent = `
                #${popupState.containerId} {
                    position: fixed;
                    right: 1rem;
                    top: 6rem;
                    z-index: 130;
                    display: flex;
                    flex-direction: column;
                    gap: 0.5rem;
                    pointer-events: none;
                    width: min(24rem, calc(100vw - 2rem));
                }

                .mpb-popup {
                    pointer-events: auto;
                    border-radius: 0.9rem;
                    border: 1px solid #e2e8f0;
                    background: #ffffff;
                    color: #0f172a;
                    box-shadow: 0 18px 38px -24px rgba(15, 23, 42, 0.35);
                    overflow: hidden;
                    transform: translateY(-8px);
                    opacity: 0;
                    transition: transform 0.2s ease, opacity 0.2s ease;
                }

                .mpb-popup.mpb-popup-visible {
                    transform: translateY(0);
                    opacity: 1;
                }

                .mpb-popup-head {
                    display: flex;
                    align-items: center;
                    justify-content: space-between;
                    gap: 0.75rem;
                    padding: 0.6rem 0.8rem;
                    font-size: 0.75rem;
                    font-weight: 800;
                    letter-spacing: 0.04em;
                    text-transform: uppercase;
                }

                .mpb-popup-body {
                    padding: 0.72rem 0.8rem 0.82rem;
                    font-size: 0.86rem;
                    line-height: 1.35;
                    font-weight: 600;
                }

                .mpb-popup-close {
                    border: none;
                    background: transparent;
                    color: inherit;
                    cursor: pointer;
                    font-size: 0.75rem;
                    font-weight: 800;
                    text-transform: uppercase;
                    letter-spacing: 0.04em;
                }

                .mpb-popup-info .mpb-popup-head {
                    background: #e0f2fe;
                    color: #0369a1;
                }

                .mpb-popup-success .mpb-popup-head {
                    background: #dcfce7;
                    color: #166534;
                }

                .mpb-popup-warning .mpb-popup-head {
                    background: #fef3c7;
                    color: #92400e;
                }

                .mpb-popup-error .mpb-popup-head {
                    background: #fee2e2;
                    color: #b91c1c;
                }
            `;
            document.head.appendChild(style);
        }

        if (!document.getElementById(popupState.containerId)) {
            const container = document.createElement("div");
            container.id = popupState.containerId;
            container.setAttribute("aria-live", "polite");
            container.setAttribute("aria-atomic", "false");
            document.body.appendChild(container);
        }

        popupState.mounted = true;
    }

    function createPopup(type, title, message, durationMs) {
        mountPopupUi();
        const container = document.getElementById(popupState.containerId);
        if (!container) return;

        const popup = document.createElement("article");
        popup.className = `mpb-popup mpb-popup-${type}`;
        popup.setAttribute("role", type === "error" ? "alert" : "status");

        popup.innerHTML = `
            <div class="mpb-popup-head">
                <span>${title}</span>
                <button type="button" class="mpb-popup-close" aria-label="Dismiss notification">Close</button>
            </div>
            <div class="mpb-popup-body"></div>
        `;

        const body = popup.querySelector(".mpb-popup-body");
        if (body) body.textContent = message;

        const closePopup = () => {
            popup.classList.remove("mpb-popup-visible");
            window.setTimeout(() => popup.remove(), 170);
        };

        const closeBtn = popup.querySelector(".mpb-popup-close");
        closeBtn?.addEventListener("click", closePopup);

        container.appendChild(popup);
        window.setTimeout(() => popup.classList.add("mpb-popup-visible"), 20);

        if (durationMs > 0) {
            window.setTimeout(closePopup, durationMs);
        }
    }

    window.mpbPopup = function mpbPopup(message, options = {}) {
        const text = String(message || "").trim();
        if (!text) return;

        const typeRaw = String(options.type || "info").toLowerCase();
        const type =
            typeRaw === "success" || typeRaw === "warning" || typeRaw === "error"
                ? typeRaw
                : "info";
        const defaultTitleMap = {
            info: "Notice",
            success: "Success",
            warning: "Warning",
            error: "Error",
        };
        const title = String(options.title || defaultTitleMap[type]);
        const duration = Number.isFinite(options.duration) ? Number(options.duration) : 4200;
        createPopup(type, title, text, Math.max(1000, duration));
    };
})();
