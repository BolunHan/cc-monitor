/**
 * cc-monitor dashboard — SSE client, hooks management, settings panel.
 */
(() => {
    const grid = document.getElementById("session-grid");
    const emptyState = document.getElementById("empty-state");
    const indicator = document.getElementById("connection-indicator");
    const label = document.getElementById("connection-label");
    const cards = new Map(); // session_id -> HTMLElement
    const prevStates = new Map(); // session_id -> state string
    let notificationsPermitted = false;

    // ---- Browser Notifications ----

    function requestNotificationPermission() {
        if (!("Notification" in window)) return;
        if (Notification.permission === "granted") {
            notificationsPermitted = true;
        } else if (Notification.permission !== "denied") {
            Notification.requestPermission().then(p => {
                notificationsPermitted = (p === "granted");
            });
        }
    }

    function notify(session) {
        if (!notificationsPermitted) return;

        const prev = prevStates.get(session.session_id);
        // Only notify on transition to these states
        if (session.state === prev) return;
        if (session.state !== "idle" && session.state !== "pending_approval") return;

        const basename = dirBasename(session.cwd) || session.session_id.substring(0, 8);

        let title, body;
        if (session.state === "idle") {
            title = `${basename} — Task Complete`;
            body = "Claude Code is idle, waiting for your input.";
        } else {
            title = `${basename} — Pending Approval`;
            body = "Claude Code needs permission to proceed.";
        }

        try {
            new Notification(title, { body, icon: "/static/favicon.ico", tag: session.session_id });
        } catch (_) { /* ignore */ }
    }

    // ---- Connection state ----

    function setConnected(state) {
        indicator.classList.toggle("connected", state);
        label.textContent = state ? "connected" : "disconnected";
    }

    // ---- Utilities ----

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

    function escapeHtml(str) {
        const el = document.createElement("span");
        el.textContent = str;
        return el.innerHTML;
    }

    function dirBasename(cwd) {
        if (!cwd) return null;
        const trimmed = cwd.endsWith("/") ? cwd.slice(0, -1) : cwd;
        const idx = Math.max(trimmed.lastIndexOf("/"), trimmed.lastIndexOf("\\"));
        return idx >= 0 ? trimmed.slice(idx + 1) : trimmed;
    }

    // ---- Session Cards ----

    function createCard(session) {
        const card = document.createElement("div");
        card.className = "session-card";
        card.id = `card-${session.session_id}`;

        const basename = dirBasename(session.cwd);
        const title = basename || session.session_id.substring(0, 8) + "…";
        const subtitle = basename ? escapeHtml(session.session_id) : "";

        card.innerHTML = `
            <div class="session-card__header">
                <div>
                    <div class="session-card__title" title="${escapeHtml(session.cwd || session.session_id)}">
                        ${escapeHtml(title)}
                    </div>
                    ${subtitle ? `<div class="session-card__subtitle" title="${escapeHtml(session.session_id)}">${subtitle.substring(0, 20)}</div>` : ""}
                </div>
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

    // ---- SSE Connection ----

    function connectSSE() {
        const es = new EventSource("/api/stream");

        es.addEventListener("state_update", (e) => {
            try {
                const session = JSON.parse(e.data);
                updateCard(session);
                notify(session);
                prevStates.set(session.session_id, session.state);
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

    // ---- Hooks Management ----

    const hooksBanner = document.getElementById("hooks-banner");
    const btnInstall = document.getElementById("btn-install-hooks");
    const installFeedback = document.getElementById("install-feedback");
    const settingsHookStatus = document.getElementById("settings-hook-status");

    let hooksInstalled = false;

    function updateHookStatusUI(installed) {
        hooksInstalled = installed;
        if (installed) {
            hooksBanner.classList.add("hidden");
        } else {
            hooksBanner.classList.remove("hidden");
        }
        if (settingsHookStatus) {
            settingsHookStatus.textContent = installed ? "✓ installed" : "not installed";
            settingsHookStatus.className = "settings-panel__hook-status " + (installed ? "installed" : "not-installed");
        }
    }

    async function checkHooksStatus() {
        try {
            const resp = await fetch("/api/hooks-status");
            const data = await resp.json();
            updateHookStatusUI(data.installed);
        } catch (err) {
            // Server might not be ready yet; retry after SSE connects
            updateHookStatusUI(false);
        }
    }

    btnInstall.addEventListener("click", async () => {
        btnInstall.disabled = true;
        installFeedback.textContent = "installing…";
        installFeedback.className = "install-feedback";
        try {
            const resp = await fetch("/api/install-hooks", { method: "POST" });
            const data = await resp.json();
            if (resp.ok) {
                installFeedback.textContent = `✓ ${data.installed_events} hooks installed`;
                installFeedback.className = "install-feedback success";
                updateHookStatusUI(true);
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

    // ---- Settings Panel ----

    const btnSettings = document.getElementById("btn-settings");
    const settingsPanel = document.getElementById("settings-panel");
    const settingsPort = document.getElementById("settings-port");
    const btnUninstall = document.getElementById("btn-uninstall-hooks");
    const settingsFeedback = document.getElementById("settings-feedback");

    // Show current port from window.location
    if (settingsPort) {
        settingsPort.value = window.location.port || "9876";
    }

    btnSettings.addEventListener("click", () => {
        settingsPanel.classList.toggle("hidden");
        // Refresh hook status when opening settings
        if (!settingsPanel.classList.contains("hidden")) {
            checkHooksStatus();
        }
    });

    btnUninstall.addEventListener("click", async () => {
        if (!confirm("Remove cc-monitor hooks from ~/.claude/settings.json?")) return;

        btnUninstall.disabled = true;
        settingsFeedback.textContent = "removing…";
        settingsFeedback.className = "settings-panel__feedback";
        try {
            const resp = await fetch("/api/uninstall-hooks", { method: "POST" });
            const data = await resp.json();
            if (resp.ok) {
                settingsFeedback.textContent = `✓ ${data.removed_events} hooks removed`;
                settingsFeedback.className = "settings-panel__feedback success";
                updateHookStatusUI(false);
            } else {
                settingsFeedback.textContent = `✗ ${data.detail}`;
                settingsFeedback.className = "settings-panel__feedback error";
            }
        } catch (err) {
            settingsFeedback.textContent = "✗ server unreachable";
            settingsFeedback.className = "settings-panel__feedback error";
        }
        btnUninstall.disabled = false;
        setTimeout(() => {
            settingsFeedback.textContent = "";
            settingsFeedback.className = "settings-panel__feedback";
        }, 4000);
    });

    // ---- Initialise ----

    requestNotificationPermission();

    fetch("/api/status")
        .then(r => r.json())
        .then(data => {
            if (data.sessions && data.sessions.length > 0) {
                data.sessions.forEach(s => {
                    updateCard(s);
                    prevStates.set(s.session_id, s.state);
                });
            }
            if (cards.size === 0) {
                emptyState.style.removeProperty("display");
            }
        })
        .catch(err => { console.error("cc-monitor: failed to load sessions", err); });

    checkHooksStatus();
    connectSSE();
})();
