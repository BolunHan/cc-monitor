/**
 * cc-monitor dashboard — SSE client, hooks management, settings panel.
 * Fully static: can be hosted on any HTTP server (gh-pages, nginx, etc.)
 * and connect to a cc-monitor server running elsewhere.
 */
(() => {
    const STORAGE_KEY_URL = "cc-monitor-server-url";
    const DEFAULT_HOST = "http://127.0.0.1";
    const DEFAULT_PORT = "9876";

    // ---- Server URL ----

    function getServerUrl() {
        const stored = localStorage.getItem(STORAGE_KEY_URL);
        if (stored) return stored.replace(/\/+$/, "");
        // If served from localhost, use current origin (server knows its port)
        const hostname = window.location.hostname;
        if (hostname === "localhost" || hostname === "127.0.0.1" || hostname === "[::1]") {
            return window.location.origin;
        }
        // Default for remote dashboards (gh-pages, etc.)
        return DEFAULT_HOST + ":" + DEFAULT_PORT;
    }

    function setServerUrl(url) {
        localStorage.setItem(STORAGE_KEY_URL, url.replace(/\/+$/, ""));
    }

    function apiUrl(path) {
        return getServerUrl() + path;
    }

    // ---- Globals ----

    const indicator = document.getElementById("connection-indicator");
    const label = document.getElementById("connection-label");
    const cards = new Map(); // session_id -> {section, element}
    const prevStates = new Map(); // session_id -> {state, archived}
    let notificationsPermitted = false;
    let currentEventSource = null;

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
        if (prev && session.state === prev.state) return;
        if (session.state !== "idle" && session.state !== "pending_approval" && session.state !== "pending_review") return;

        const basename = dirBasename(session.cwd) || session.session_id.substring(0, 8);
        let title, body;
        if (session.state === "pending_review") {
            title = `${basename} — Pending Review`;
            body = "Claude finished responding. Review the output.";
        } else if (session.state === "idle") {
            title = `${basename} — Task Complete`;
            body = "Claude Code is idle, waiting for your input.";
        } else {
            title = `${basename} — Pending Approval`;
            body = "Claude Code needs permission to proceed.";
        }
        try {
            new Notification(title, { body, tag: session.session_id });
        } catch (_) { /* ignore */ }
    }

    // ---- Connection state ----

    function setConnected(state) {
        if (indicator) indicator.classList.toggle("connected", state);
        if (label) label.textContent = state ? "connected" : "disconnected";
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

    function truncate(str, maxLen) {
        return str.length <= maxLen ? str : str.substring(0, maxLen - 1) + "…";
    }

    function dirBasename(cwd) {
        if (!cwd) return null;
        const trimmed = cwd.endsWith("/") ? cwd.slice(0, -1) : cwd;
        const idx = Math.max(trimmed.lastIndexOf("/"), trimmed.lastIndexOf("\\"));
        return idx >= 0 ? trimmed.slice(idx + 1) : trimmed;
    }

    // ---- Section routing ----

    function getSection(session) {
        if (session.archived) return "archive";
        if (session.state === "all_done") return "complete";
        return "active";
    }

    function cardStateClass(session) {
        if (session.archived) return "card--archived";
        return "card--" + session.state;
    }

    const STATE_EMOJI = {
        working: "🔵",            // 🔵
        idle: "⚪",                      // ⚪
        pending_approval: "🟡",   // 🟡
        pending_review: "🟢",     // 🟢
        all_done: "✅",                  // ✅
    };

    function getGrid(section) {
        return document.getElementById("grid-" + section);
    }

    function getEmpty(section) {
        return document.getElementById("empty-" + section);
    }

    function getCount(section) {
        return document.getElementById("count-" + section);
    }

    function updateCounts() {
        let counts = {active: 0, complete: 0, archive: 0};
        let breakdown = {}; // {section: {state: count}}
        for (const sec of ["active", "complete", "archive"]) {
            breakdown[sec] = {};
        }
        cards.forEach((_, sid) => {
            const s = prevStates.get(sid);
            if (!s) return;
            const section = getSection({archived: s.archived, state: s.state});
            counts[section]++;
            breakdown[section][s.state] = (breakdown[section][s.state] || 0) + 1;
        });
        for (const sec of ["active", "complete", "archive"]) {
            const el = getCount(sec);
            if (el) el.textContent = counts[sec];
        }
        // Active section emoji breakdown
        const bd = document.getElementById("breakdown-active");
        if (bd) {
            const parts = [];
            const ab = breakdown["active"] || {};
            for (const [state, emoji] of Object.entries(STATE_EMOJI)) {
                const n = ab[state] || 0;
                if (n > 0) parts.push(`${emoji}${n}`);
            }
            bd.textContent = parts.length > 0 ? "| " + parts.join(" ") : "";
        }
    }

    // ---- Session Cards ----

    function createCard(session) {
        const card = document.createElement("div");
        card.className = "session-card " + cardStateClass(session);
        card.id = `card-${session.session_id}`;

        const basename = dirBasename(session.cwd);
        const title = basename || session.session_id.substring(0, 8) + "…";
        const subtitle = basename ? escapeHtml(session.session_id) : "";
        const summary = session.summary
            ? `<div class="session-card__summary" title="${escapeHtml(session.summary)}">${escapeHtml(truncate(session.summary, 100))}</div>`
            : "";

        const section = getSection(session);
        const isArchived = section === "archive";
        const badgeState = isArchived ? "archived" : session.state;
        const badgeLabel = isArchived ? "archived" : session.state.replace("_", " ");

        let actions = "";
        if (section === "active" || section === "complete") {
            actions += `<button class="btn--card btn--card-archive" data-action="archive" data-sid="${escapeHtml(session.session_id)}">Archive</button>`;
        } else {
            actions += `<button class="btn--card btn--card-unarchive" data-action="unarchive" data-sid="${escapeHtml(session.session_id)}">Unarchive</button>`;
        }
        if (section === "active") {
            actions += `<button class="btn--card btn--card-complete" data-action="complete" data-sid="${escapeHtml(session.session_id)}">Mark Done</button>`;
        }

        card.innerHTML = `
            <div class="session-card__body">
                <div class="session-card__header">
                    <div>
                        <div class="session-card__title" title="${escapeHtml(session.cwd || session.session_id)}">
                            ${escapeHtml(title)}
                        </div>
                        ${subtitle ? `<div class="session-card__subtitle" title="${escapeHtml(session.session_id)}">${subtitle.substring(0, 20)}</div>` : ""}
                    </div>
                    <span class="session-card__badge badge-${badgeState}">
                        ${badgeLabel}
                    </span>
                </div>
                ${summary}
                <div class="session-card__detail">
                    <strong>cwd:</strong> ${escapeHtml(session.cwd || "—")}<br>
                    <strong>event:</strong> ${escapeHtml(session.raw_event || "—")}
                    ${session.raw_detail ? ` (${escapeHtml(session.raw_detail)})` : ""}
                </div>
                <div class="session-card__time">${relativeTime(session.updated_at)}</div>
            </div>
            ${actions ? `<div class="session-card__actions">${actions}</div>` : ""}
        `;
        return card;
    }

    function placeCard(session, cardEl) {
        const section = getSection(session);
        const grid = getGrid(section);
        const empty = getEmpty(section);
        if (!grid) return;
        const existing = cards.get(session.session_id);

        if (existing) {
            if (existing.section === section) {
                existing.element.replaceWith(cardEl);
            } else {
                existing.element.remove();
                grid.appendChild(cardEl);
            }
        } else {
            grid.appendChild(cardEl);
        }
        if (empty) empty.style.display = "none";
        cards.set(session.session_id, {section, element: cardEl});
    }

    function updateCard(session) {
        const card = createCard(session);
        placeCard(session, card);
        updateCounts();
        bindCardActions(card);
    }

    function clearAllCards() {
        cards.clear();
        for (const sec of ["active", "complete", "archive"]) {
            const grid = getGrid(sec);
            if (grid) grid.querySelectorAll(".session-card").forEach(c => c.remove());
            const empty = getEmpty(sec);
            if (empty) empty.style.removeProperty("display");
            const count = getCount(sec);
            if (count) count.textContent = "0";
        }
    }

    // ---- Card actions ----

    async function handleCardAction(action, sessionId) {
        try {
            const resp = await fetch(apiUrl(`/api/session/${sessionId}/${action}`), {method: "POST"});
            if (resp.ok) {
                const session = await resp.json();
                updateCard(session);
                prevStates.set(session.session_id, {state: session.state, archived: session.archived});
            }
        } catch (err) {
            console.error("cc-monitor: action failed", action, err);
        }
    }

    function bindCardActions(card) {
        card.querySelectorAll("[data-action]").forEach(btn => {
            btn.addEventListener("click", (e) => {
                e.stopPropagation();
                handleCardAction(btn.dataset.action, btn.dataset.sid);
            });
        });
    }

    // ---- SSE Connection ----

    let lastHeartbeat = 0;
    const HEARTBEAT_GRACE = 10;

    function connectSSE() {
        if (currentEventSource) currentEventSource.close();
        lastHeartbeat = 0;

        const es = new EventSource(apiUrl("/api/stream"));
        currentEventSource = es;

        es.addEventListener("open", () => {
            lastHeartbeat = Date.now();
            setConnected(true);
            // Refresh in case events were missed while disconnected
            loadSessions();
        });

        es.addEventListener("state_update", (e) => {
            try {
                const session = JSON.parse(e.data);
                updateCard(session);
                notify(session);
                prevStates.set(session.session_id, {state: session.state, archived: session.archived});
                lastHeartbeat = Date.now();
            } catch (err) {
                console.error("cc-monitor: failed to parse SSE data", err);
            }
        });

        es.addEventListener("heartbeat", () => {
            lastHeartbeat = Date.now();
        });

        // Pairing/device push events — refresh relevant sections in real time
        es.addEventListener("pairing_request", () => {
            pollPairingRequests();
        });

        es.addEventListener("pairing_resolved", () => {
            pollPairingRequests();
        });

        es.addEventListener("device_update", () => {
            loadPairedDevices();
            // Also refresh QR pairing payload (new device may need new QR)
            if (typeof loadPairingQR === "function") loadPairingQR();
        });

        es.addEventListener("error", () => {});
    }

    setInterval(() => {
        if (lastHeartbeat === 0) return;
        const since = (Date.now() - lastHeartbeat) / 1000;
        setConnected(since < HEARTBEAT_GRACE);
    }, 1000);

    // ---- Data fetching ----

    async function loadSessions() {
        try {
            const resp = await fetch(apiUrl("/api/status"));
            const data = await resp.json();
            if (data.sessions && data.sessions.length > 0) {
                data.sessions.forEach(s => {
                    updateCard(s);
                    prevStates.set(s.session_id, {state: s.state, archived: s.archived});
                });
            }
            updateCounts();
        } catch (err) {
            console.error("cc-monitor: failed to load sessions", err);
        }
    }

    async function loadVersion() {
        try {
            const resp = await fetch(apiUrl("/api/version"));
            const data = await resp.json();
            document.getElementById("footer-version").textContent =
                `cc-monitor v${data.version}`;
        } catch (_) {}
    }

    // ---- Hooks Management ----

    const hooksBanner = document.getElementById("hooks-banner");
    const btnInstall = document.getElementById("btn-install-hooks");
    const installFeedback = document.getElementById("install-feedback");
    const settingsHookStatus = document.getElementById("settings-hook-status");

    function isLocalhost() {
        const hostname = window.location.hostname;
        return hostname === "localhost" || hostname === "127.0.0.1" || hostname === "[::1]";
    }

    function updateHookStatusUI(installed) {
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
        console.log("[hooks] checking status at", apiUrl("/api/hooks-status"));
        try {
            const resp = await fetch(apiUrl("/api/hooks-status"));
            const data = await resp.json();
            console.log("[hooks] status response:", data);
            updateHookStatusUI(data.installed);
        } catch (err) {
            console.warn("[hooks] status check failed:", err);
            updateHookStatusUI(false);
        }
    }

    btnInstall.addEventListener("click", async () => {
        btnInstall.disabled = true;
        installFeedback.textContent = "installing…";
        installFeedback.className = "install-feedback";

        // ---- Step 1: Determine if server is local or remote ----
        const local = isLocalhost();
        console.log("[hooks] step 1 — server location:",
            local ? "LOCAL (same machine)" : "REMOTE (different machine / container)");
        console.log("[hooks]   window.location:", window.location.hostname, "server URL:", getServerUrl());

        if (!local) {
            // ---- Remote / Docker: cannot inject from browser ----
            console.log("[hooks] step 2 — REMOTE detected, checking local Python…");
            console.log("[hooks]   Browser cannot write to host filesystem from remote origin.");
            console.log("[hooks]   Provide a one-liner for the user to run on the host machine.");

            const serverUrl = getServerUrl();
            const oneLiner = `curl -sSL ${serverUrl}/static/install-hooks.sh | SERVER_URL=${serverUrl} bash`;
            console.log("[hooks] step 3 — one-liner command:");
            console.log("  %c" + oneLiner, "font-weight:bold;color:#22c55e;font-size:14px;");

            installFeedback.innerHTML = `Remote server — run this on the host:<br><code style="font-size:11px;word-break:break-all;">${escapeHtml(oneLiner)}</code>`;
            installFeedback.className = "install-feedback";
            btnInstall.disabled = false;
            return;
        }

        // ---- Local: server can write to local ~/.claude/ ----
        console.log("[hooks] step 2 — LOCAL: server can write to ~/.claude/settings.json directly");
        console.log("[hooks] step 3 — calling POST /api/install-hooks …");

        try {
            const resp = await fetch(apiUrl("/api/install-hooks"), { method: "POST" });
            const data = await resp.json();
            console.log("[hooks] step 4 — response:", resp.status, data);

            if (resp.ok) {
                console.log("[hooks] ✓ installed %d events into %s", data.installed_events, data.target);
                installFeedback.textContent = `✓ ${data.installed_events} hooks installed`;
                installFeedback.className = "install-feedback success";
                updateHookStatusUI(true);
            } else {
                console.error("[hooks] ✗ install failed:", data.detail);
                installFeedback.textContent = `✗ ${data.detail}`;
                installFeedback.className = "install-feedback error";
            }
        } catch (err) {
            console.error("[hooks] ✗ server unreachable:", err);
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
    const settingsUrl = document.getElementById("settings-url");
    const settingsPort = document.getElementById("settings-port");
    const btnSaveSettings = document.getElementById("btn-save-settings");
    const btnUninstall = document.getElementById("btn-uninstall-hooks");
    const settingsFeedback = document.getElementById("settings-feedback");

    function populateSettingsInputs() {
        const url = getServerUrl();
        try {
            const u = new URL(url);
            settingsUrl.value = u.protocol + "//" + u.hostname;
            settingsPort.value = u.port || DEFAULT_PORT;
        } catch (_) {
            settingsUrl.value = url;
            settingsPort.value = "";
        }
    }

    btnSettings.addEventListener("click", () => {
        settingsPanel.classList.toggle("hidden");
        if (!settingsPanel.classList.contains("hidden")) {
            populateSettingsInputs();
            checkHooksStatus();
        }
    });

    btnSaveSettings.addEventListener("click", () => {
        const host = settingsUrl.value.trim().replace(/\/+$/, "");
        const port = settingsPort.value.trim();
        if (!host) {
            settingsFeedback.textContent = "✗ Server URL is required";
            settingsFeedback.className = "settings-panel__feedback error";
            return;
        }
        let fullUrl = host;
        if (port) fullUrl = host + ":" + port;
        setServerUrl(fullUrl);
        settingsFeedback.textContent = "✓ saved, reconnecting…";
        settingsFeedback.className = "settings-panel__feedback success";
        setTimeout(() => {
            settingsFeedback.textContent = "";
            settingsFeedback.className = "settings-panel__feedback";
        }, 2000);
        connectSSE();
        loadVersion();
        checkHooksStatus();
    });

    btnUninstall.addEventListener("click", async () => {
        if (!isLocalhost()) {
            settingsFeedback.textContent = "✗ Cannot uninstall from remote — run: rm -rf ~/.cc-monitor/hooks";
            settingsFeedback.className = "settings-panel__feedback error";
            setTimeout(() => { settingsFeedback.textContent = ""; settingsFeedback.className = "settings-panel__feedback"; }, 6000);
            return;
        }
        if (!confirm("Remove cc-monitor hooks from ~/.claude/settings.json?")) return;
        btnUninstall.disabled = true;
        settingsFeedback.textContent = "removing…";
        settingsFeedback.className = "settings-panel__feedback";
        try {
            const resp = await fetch(apiUrl("/api/uninstall-hooks"), { method: "POST" });
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

    // ---- Section collapse/expand ----

    document.querySelectorAll(".section__header").forEach(header => {
        header.addEventListener("click", () => {
            const section = header.closest(".section");
            const body = section.querySelector(".section__body");
            const toggle = section.querySelector(".section__toggle");
            const isCollapsed = body.classList.contains("hidden");
            if (isCollapsed) {
                body.classList.remove("hidden");
                toggle.textContent = "▼";
                section.classList.remove("section--collapsed");
            } else {
                body.classList.add("hidden");
                toggle.textContent = "▶";
                section.classList.add("section--collapsed");
            }
        });
    });

    // ---- Device Pairing ----

    const btnPair = document.getElementById("btn-pair");
    const pairingPanel = document.getElementById("pairing-panel");
    const btnRefreshQr = document.getElementById("btn-refresh-qr");
    const pairQr = document.getElementById("pair-qr");
    const pairingRequestsList = document.getElementById("pairing-requests-list");
    let qrCodeInstance = null;
    let pairingPollInterval = null;

    btnPair.addEventListener("click", () => {
        const wasHidden = pairingPanel.classList.contains("hidden");
        settingsPanel.classList.add("hidden");
        pairingPanel.classList.toggle("hidden");
        if (wasHidden) {
            loadPairingQR();
            startPairingPoll();
            loadPairedDevices();
        } else {
            stopPairingPoll();
        }
    });

    btnRefreshQr.addEventListener("click", () => {
        loadPairingQR();
    });

    async function loadPairingQR() {
        try {
            const resp = await fetch(apiUrl("/api/auth/pair/qr"));
            if (!resp.ok) {
                pairQr.innerHTML = '<p class="pairing-error">Pairing not available — start server with --host 0.0.0.0</p>';
                return;
            }
            const data = await resp.json();
            // Use URL format so browsers can offer to open with our app
            const url = `ccmonitor://pair?t=${encodeURIComponent(data.token)}&h=${encodeURIComponent(data.host)}&p=${encodeURIComponent(data.port)}&c=${encodeURIComponent(data.cert_sha256)}`;
            pairQr.innerHTML = "";
            qrCodeInstance = new QRCode(pairQr, {
                text: url,
                width: 200,
                height: 200,
                colorDark: "#e1e4ed",
                colorLight: "#1a1d27",
            });
        } catch (err) {
            pairQr.innerHTML = '<p class="pairing-error">Server unreachable or auth not enabled</p>';
        }
    }

    function startPairingPoll() {
        stopPairingPoll();
        pairingPollInterval = setInterval(pollPairingRequests, 3000);
        pollPairingRequests();
    }

    function stopPairingPoll() {
        if (pairingPollInterval) {
            clearInterval(pairingPollInterval);
            pairingPollInterval = null;
        }
    }

    async function pollPairingRequests() {
        try {
            const resp = await fetch(apiUrl("/api/auth/pair/requests"));
            if (!resp.ok) return;
            const data = await resp.json();
            const requests = data.requests || [];
            if (requests.length === 0) {
                pairingRequestsList.innerHTML = '<p class="pairing-empty">No pending requests</p>';
                return;
            }
            pairingRequestsList.innerHTML = requests.map(r => `
                <div class="pairing-request">
                    <span class="pairing-request__name">${escHtml(r.device_name)}${r.pairing_code ? `<br><code style="font-size:0.9em">${escHtml(r.pairing_code)}</code>` : ''}</span>
                    <div class="pairing-request__actions">
                        <button class="btn btn--success btn--tiny" onclick="window._ccApprovePair('${r.id}')">✓</button>
                        <button class="btn btn--danger btn--tiny" onclick="window._ccDenyPair('${r.id}')">✗</button>
                    </div>
                </div>
            `).join("");
        } catch (_) {}
    }

    window._ccApprovePair = async function(requestId) {
        try {
            await fetch(apiUrl(`/api/auth/pair/request/${requestId}/approve`), { method: "POST" });
            pollPairingRequests();
            loadPairedDevices();
            loadPairingQR();
        } catch (_) {}
    };

    window._ccDenyPair = async function(requestId) {
        try {
            await fetch(apiUrl(`/api/auth/pair/request/${requestId}/deny`), { method: "POST" });
            pollPairingRequests();
        } catch (_) {}
    };

    async function loadPairedDevices() {
        const list = document.getElementById("paired-devices-list");
        try {
            const resp = await fetch(apiUrl("/api/auth/devices"));
            if (!resp.ok) { list.innerHTML = '<p class="pairing-empty">—</p>'; return; }
            const data = await resp.json();
            const devices = data.devices || [];
            if (devices.length === 0) {
                list.innerHTML = '<p class="pairing-empty">No paired devices</p>';
                return;
            }
            list.innerHTML = devices.map(d => `
                <div class="pairing-request">
                    <span class="pairing-request__name">${escHtml(d.device_name)}<br><code style="font-size:0.85em">${escHtml(d.client_id ? d.client_id.substring(0, 8) : '-')}</code> <small>${d.expired ? 'expired' : 'active'}</small></span>
                    <div class="pairing-request__actions">
                        <button class="btn btn--danger btn--tiny" onclick="window._ccRevokeDevice('${d.client_id}')" title="Revoke">✕</button>
                    </div>
                </div>
            `).join("");
        } catch (_) {}
    }

    window._ccRevokeDevice = async function(clientId) {
        try {
            await fetch(apiUrl(`/api/auth/devices/${encodeURIComponent(clientId)}`), { method: "DELETE" });
            loadPairedDevices();
        } catch (_) {}
    };

    function escHtml(str) {
        const div = document.createElement("div");
        div.textContent = str;
        return div.innerHTML;
    }

    // ---- Initialise ----

    requestNotificationPermission();
    populateSettingsInputs();
    loadVersion();
    checkHooksStatus();

    // Fetch sessions immediately via REST — don't wait for SSE to connect.
    // SSE connects in parallel for live updates; when its 'open' fires,
    // loadSessions() refreshes any events missed during the handshake.
    loadSessions().then(() => {
        if (lastHeartbeat === 0) setConnected(true);
    });
    connectSSE();
})();
