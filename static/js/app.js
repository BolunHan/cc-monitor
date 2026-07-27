/**
 * cc-monitor dashboard — SSE client that renders session state cards.
 */
(() => {
    const grid = document.getElementById("session-grid");
    const emptyState = document.getElementById("empty-state");
    const indicator = document.getElementById("connection-indicator");
    const label = document.getElementById("connection-label");
    const cards = new Map(); // session_id -> HTMLElement

    function setConnected(state) {
        indicator.classList.toggle("connected", state);
        label.textContent = state ? "connected" : "disconnected";
    }

    function relativeTime(isoString) {
        const then = new Date(isoString);
        const now = new Date();
        const seconds = Math.floor((now - then) / 1000);
        if (seconds < 5) return "just now";
        if (seconds < 60) return `${seconds}s ago`;
        const minutes = Math.floor(seconds / 60);
        if (minutes < 60) return `${minutes}m ago`;
        const hours = Math.floor(minutes / 60);
        return `${hours}h ago`;
    }

    function createCard(session) {
        const card = document.createElement("div");
        card.className = "session-card";
        card.id = `card-${session.session_id}`;
        card.innerHTML = `
            <div class="session-card__header">
                <span class="session-card__id" title="${escapeHtml(session.session_id)}">
                    ${escapeHtml(session.session_id).substring(0, 8)}...
                </span>
                <span class="session-card__badge badge-${session.state}">
                    ${session.state.replace("_", " ")}
                </span>
            </div>
            <div class="session-card__detail">
                <strong>cwd:</strong> ${escapeHtml(session.cwd || "—")}<br>
                <strong>event:</strong> ${escapeHtml(session.raw_event || "—")}
                ${session.raw_detail ? ` (${escapeHtml(session.raw_detail)})` : ""}
            </div>
            <div class="session-card__time">${relativeTime(session.updated_at)}</div>
        `;
        return card;
    }

    function escapeHtml(str) {
        const el = document.createElement("span");
        el.textContent = str;
        return el.innerHTML;
    }

    function updateCard(session) {
        const card = createCard(session);
        const existing = cards.get(session.session_id);
        if (existing) {
            existing.replaceWith(card);
        } else {
            grid.appendChild(card);
            emptyState.style.display = "none";
        }
        cards.set(session.session_id, card);
    }

    function connect() {
        const es = new EventSource("/api/stream");

        es.addEventListener("state_update", (e) => {
            try {
                const session = JSON.parse(e.data);
                updateCard(session);
            } catch (err) {
                console.error("cc-monitor: failed to parse SSE data", err);
            }
        });

        es.addEventListener("open", () => setConnected(true));
        es.addEventListener("error", () => {
            setConnected(false);
            // EventSource auto-reconnects
        });
    }

    // ---- Install hooks button ----
    const btnInstall = document.getElementById("btn-install-hooks");
    const installFeedback = document.getElementById("install-feedback");

    btnInstall.addEventListener("click", async () => {
        btnInstall.disabled = true;
        installFeedback.textContent = "installing…";
        installFeedback.className = "install-feedback";
        try {
            const resp = await fetch("/api/install-hooks", { method: "POST" });
            const data = await resp.json();
            if (resp.ok) {
                installFeedback.textContent = `✓ installed ${data.installed_events} hooks`;
                installFeedback.className = "install-feedback success";
            } else {
                installFeedback.textContent = `✗ ${data.detail}`;
                installFeedback.className = "install-feedback error";
            }
        } catch (err) {
            installFeedback.textContent = "✗ server unreachable";
            installFeedback.className = "install-feedback error";
        }
        btnInstall.disabled = false;
        setTimeout(() => {
            if (installFeedback.textContent.startsWith("✓")) {
                installFeedback.textContent = "";
                installFeedback.className = "install-feedback";
            }
        }, 4000);
    });

    // Initial load — fetch existing sessions
    fetch("/api/status")
        .then(r => r.json())
        .then(data => {
            if (data.sessions && data.sessions.length > 0) {
                data.sessions.forEach(updateCard);
            }
            if (cards.size === 0) {
                emptyState.style.removeProperty("display");
            }
        })
        .catch(err => { console.error("cc-monitor: failed to load sessions", err); });

    connect();
})();
