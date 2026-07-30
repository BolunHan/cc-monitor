/**
 * cc-monitor dashboard — SSE client, hooks management, settings panel.
 * Fully static: can be hosted on any HTTP server (gh-pages, nginx, etc.)
 * and connect to a cc-monitor server running elsewhere.
 */
(() => {
// ---- I18n ----

const I18n = (() => {
    let _lang = 'en';
    let _data = null;

    async function load(lang) {
        try {
            const resp = await fetch('./i18n/' + lang + '.json');
            if (!resp.ok) throw new Error('not found');
            _data = await resp.json();
            _lang = lang;
        } catch (_) {
            if (lang !== 'en') return load('en');
            _data = null;
        }
    }

    function t(key, vars) {
        let s = (_data && _data[key]) || key;
        if (vars) {
            for (const [k, v] of Object.entries(vars)) {
                s = s.replace('{' + k + '}', v);
            }
        }
        return s;
    }

    function renderAll() {
        document.querySelectorAll('[data-i18n]').forEach(el => {
            const k = el.dataset.i18n;
            if (k) el.textContent = t(k);
        });
        // Re-render dynamic content tied to data
        loadVersion();
        loadSessionsView();
    }

    async function setLang(lang) {
        localStorage.setItem('cc-monitor-lang', lang);
        await load(lang);
        renderAll();
        loadSessions();
        loadVersion();
        checkHooksStatus();
    }

    function current() { return _lang; }

    return { load, t, renderAll, setLang, current };
})();

function loadSessionsView() {
    // Re-render all cards with current language
    cards.forEach((meta, sid) => {
        const prev = prevStates.get(sid);
        if (prev) {
            const session = { session_id: sid, state: prev.state, archived: prev.archived, cwd: meta.cwd, raw_event: meta.rawEvent, raw_detail: meta.rawDetail, summary: meta.summary, cc_monitor_uid: meta.uid, updated_at: meta.updatedAt };
            updateCard(session);
        }
    });
    updateCounts();
}

    const STORAGE_KEY_URL = "cc-monitor-server-url";
    const STORAGE_KEY_TOKEN = "cc-monitor-auth-token";
    const STORAGE_KEY_CLIENT_ID = "cc-monitor-client-id";

    function getClientId() {
        let cid = localStorage.getItem(STORAGE_KEY_CLIENT_ID);
        if (!cid) {
            cid = "web-" + crypto.randomUUID();
            localStorage.setItem(STORAGE_KEY_CLIENT_ID, cid);
        }
        return cid;
    }

    // ---- Server URL ----

    function getServerUrl() {
        const stored = localStorage.getItem(STORAGE_KEY_URL);
        if (stored) return stored.replace(/\/+$/, "");
        return window.location.origin;
    }

    function setServerUrl(url) {
        localStorage.setItem(STORAGE_KEY_URL, url.replace(/\/+$/, ""));
    }

    function apiUrl(path) {
        return getServerUrl() + path;
    }

    // ---- Auth token ----

    function getAuthToken() {
        return localStorage.getItem(STORAGE_KEY_TOKEN) || "";
    }

    function setAuthToken(token) {
        localStorage.setItem(STORAGE_KEY_TOKEN, token);
    }

    function clearAuthToken() {
        localStorage.removeItem(STORAGE_KEY_TOKEN);
    }

    async function apiFetch(path, opts = {}) {
        const url = apiUrl(path);
        const headers = { ...(opts.headers || {}) };
        const token = getAuthToken();
        if (token) headers["Authorization"] = "Bearer " + token;
        const resp = await fetch(url, { ...opts, headers });
        if (resp.status === 401) {
            updateUnauthorizedUI(true);
        }
        return resp;
    }

    let isUnauthorized = false;

    function updateUnauthorizedUI(unauth) {
        isUnauthorized = unauth;
        const banner = document.getElementById("unauth-banner");
        if (banner) {
            banner.classList.toggle("hidden", !unauth);
        }
        // Don't mark as connected if unauthorized
        if (unauth) {
            setConnected(false);
        }
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
            title = I18n.t("notify.pending_review.title", {name: basename});
            body = I18n.t("notify.pending_review.body");
        } else if (session.state === "idle") {
            title = I18n.t("notify.idle.title", {name: basename});
            body = I18n.t("notify.idle.body");
        } else {
            title = I18n.t("notify.pending_approval.title", {name: basename});
            body = I18n.t("notify.pending_approval.body");
        }
        try {
            new Notification(title, { body, tag: session.session_id });
        } catch (_) { /* ignore */ }
    }

    // ---- Connection state ----

    function setConnected(state) {
        if (indicator) indicator.classList.toggle("connected", state);
        if (label) label.textContent = state ? I18n.t("connection.connected") : I18n.t("connection.disconnected");
    }

    // ---- Utilities ----

    function relativeTime(isoString) {
        const then = new Date(isoString);
        const now = new Date();
        const seconds = Math.floor((now - then) / 1000);
        if (seconds < 5) return I18n.t("time.just_now");
        if (seconds < 60) return I18n.t("time.seconds_ago", {n: seconds});
        const minutes = Math.floor(seconds / 60);
        if (minutes < 60) return I18n.t("time.minutes_ago", {n: minutes});
        const hours = Math.floor(minutes / 60);
        return I18n.t("time.hours_ago", {n: hours});
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
        const badgeLabel = isArchived ? I18n.t("state.archived") : I18n.t("state." + session.state);

        let actions = "";
        if (section === "active" || section === "complete") {
            actions += `<button class="btn--card btn--card-archive" data-action="archive" data-sid="${escapeHtml(session.session_id)}">${I18n.t("card.archive")}</button>`;
        } else {
            actions += `<button class="btn--card btn--card-unarchive" data-action="unarchive" data-sid="${escapeHtml(session.session_id)}">${I18n.t("card.unarchive")}</button>`;
        }
        if (section === "active") {
            actions += `<button class="btn--card btn--card-complete" data-action="complete" data-sid="${escapeHtml(session.session_id)}">${I18n.t("card.mark_done")}</button>`;
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
                    ${session.cc_monitor_uid ? `<br><strong>uid:</strong> <code>${escapeHtml(session.cc_monitor_uid)}</code>` : ""}
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
        // Store metadata for language re-render
        cards.get(session.session_id).cwd = session.cwd;
        cards.get(session.session_id).rawEvent = session.raw_event;
        cards.get(session.session_id).rawDetail = session.raw_detail;
        cards.get(session.session_id).summary = session.summary;
        cards.get(session.session_id).uid = session.cc_monitor_uid;
        cards.get(session.session_id).updatedAt = session.updated_at;
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
            const resp = await apiFetch(`/api/session/${sessionId}/${action}`, {method: "POST"});
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

        let sseUrl = apiUrl("/api/stream");
        const token = getAuthToken();
        if (token) sseUrl += "?token=" + encodeURIComponent(token);

        const es = new EventSource(sseUrl);
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
            if (typeof loadPairingQR === "function") loadPairingQR();
        });

        es.addEventListener("hooks_status_update", (e) => {
            try {
                const data = JSON.parse(e.data);
                updateHookStatusUI(data.installed);
            } catch (_) {}
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
            const resp = await apiFetch("/api/status");
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
            const resp = await apiFetch("/api/version");
            const data = await resp.json();
            document.getElementById("footer-version").textContent =
                I18n.t("footer.version", {version: data.version});
            // Docker badge in settings
            const badge = document.getElementById("settings-docker-badge");
            if (badge) {
                if (data.docker) {
                    badge.textContent = I18n.t("docker_badge.docker");
                    badge.className = "settings-panel__docker-badge docker";
                } else {
                    badge.textContent = I18n.t("docker_badge.native");
                    badge.className = "settings-panel__docker-badge native";
                }
            }
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
            settingsHookStatus.textContent = installed ? I18n.t("hooks.installed_status") : I18n.t("hooks.not_installed_status");
            settingsHookStatus.className = "settings-panel__hook-status " + (installed ? "installed" : "not-installed");
        }
    }

    async function checkHooksStatus() {
        console.log("[hooks] checking status at", apiUrl("/api/hooks-status"));
        try {
            const resp = await apiFetch("/api/hooks-status");
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
        installFeedback.textContent = I18n.t("hooks.installing");
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
            const oneLiner = `curl -skSL ${serverUrl}/static/install-hooks.sh | SERVER_URL=${serverUrl} bash`;
            console.log("[hooks] step 3 — one-liner command:");
            console.log("  %c" + oneLiner, "font-weight:bold;color:#22c55e;font-size:14px;");

            showInstallModal(oneLiner);
            btnInstall.disabled = false;
            return;
        }

        // ---- Local: server may be native or Docker ----
        console.log("[hooks] step 2 — LOCAL: calling POST /api/install-hooks …");

        try {
            const resp = await apiFetch("/api/install-hooks", { method: "POST" });
            const data = await resp.json();
            console.log("[hooks] step 3 — response:", resp.status, data);

            if (resp.ok) {
                if (data.mode === "docker") {
                    // Docker server — can't write to host, show one-liner
                    console.log("[hooks] Docker detected, showing one-liner");
                    showInstallModal(data.oneliner);
                    installFeedback.textContent = "";
                    installFeedback.className = "install-feedback";
                } else {
                    console.log("[hooks] ✓ installed %d events into %s", data.installed_events, data.target);
                    installFeedback.textContent = I18n.t("hooks.installed", {n: data.installed_events});
                    installFeedback.className = "install-feedback success";
                    updateHookStatusUI(true);
                }
            } else {
                console.error("[hooks] ✗ install failed:", data.detail);
                installFeedback.textContent = I18n.t("hooks.remove_failed", {detail: data.detail});
                installFeedback.className = "install-feedback error";
            }
        } catch (err) {
            console.error("[hooks] ✗ server unreachable:", err);
            installFeedback.textContent = I18n.t("hooks.unreachable");
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
    const btnCheck = document.getElementById("btn-check-hooks");
    const settingsFeedback = document.getElementById("settings-feedback");

    function populateSettingsInputs() {
        const url = getServerUrl();
        try {
            const u = new URL(url);
            settingsUrl.value = u.protocol + "//" + u.hostname;
            settingsPort.value = u.port || window.location.port || DEFAULT_PORT;
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
            settingsFeedback.textContent = I18n.t("settings.url_required");
            settingsFeedback.className = "settings-panel__feedback error";
            return;
        }
        let fullUrl = host;
        if (port) fullUrl = host + ":" + port;
        setServerUrl(fullUrl);
        settingsFeedback.textContent = I18n.t("settings.saved");
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
            const serverUrl = getServerUrl();
            const oneLiner = `curl -skSL ${serverUrl}/static/uninstall-hooks.sh | SERVER_URL=${serverUrl} bash`;
            showInstallModal(oneLiner);
            return;
        }
        btnUninstall.disabled = true;
        settingsFeedback.textContent = I18n.t("hooks.removing");
        settingsFeedback.className = "settings-panel__feedback";
        try {
            const resp = await apiFetch("/api/uninstall-hooks", { method: "POST" });
            const data = await resp.json();
            if (resp.ok) {
                if (data.mode === "docker") {
                    // Docker server — show one-liner
                    showInstallModal(data.oneliner);
                    settingsFeedback.textContent = "";
                    settingsFeedback.className = "settings-panel__feedback";
                } else {
                    settingsFeedback.textContent = I18n.t("hooks.removed", {n: data.removed_entries});
                    settingsFeedback.className = "settings-panel__feedback success";
                    updateHookStatusUI(false);
                }
            } else {
                settingsFeedback.textContent = I18n.t("hooks.remove_failed", {detail: data.detail});
                settingsFeedback.className = "settings-panel__feedback error";
            }
        } catch (err) {
            settingsFeedback.textContent = I18n.t("hooks.unreachable");
            settingsFeedback.className = "settings-panel__feedback error";
        }
        btnUninstall.disabled = false;
        setTimeout(() => {
            settingsFeedback.textContent = "";
            settingsFeedback.className = "settings-panel__feedback";
        }, 4000);
    });

    btnCheck.addEventListener("click", () => {
        const serverUrl = getServerUrl();
        const oneLiner = `curl -skSL ${serverUrl}/static/check-hooks.sh | SERVER_URL=${serverUrl} bash`;
        showInstallModal(oneLiner);
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
            const resp = await apiFetch("/api/auth/pair/qr");
            if (!resp.ok) {
                pairQr.innerHTML = '<p class="pairing-error">' + I18n.t("pair.error") + '</p>';
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
            pairQr.innerHTML = '<p class="pairing-error">' + I18n.t("pair.unreachable") + '</p>';
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
            const resp = await apiFetch("/api/auth/pair/requests");
            if (!resp.ok) return;
            const data = await resp.json();
            const requests = data.requests || [];
            if (requests.length === 0) {
                pairingRequestsList.innerHTML = '<p class="pairing-empty">' + I18n.t("pair.empty_requests") + '</p>';
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
            await apiFetch(`/api/auth/pair/request/${requestId}/approve`, { method: "POST" });
            pollPairingRequests();
            loadPairedDevices();
            loadPairingQR();
        } catch (_) {}
    };

    window._ccDenyPair = async function(requestId) {
        try {
            await apiFetch(`/api/auth/pair/request/${requestId}/deny`, { method: "POST" });
            pollPairingRequests();
        } catch (_) {}
    };

    async function loadPairedDevices() {
        const list = document.getElementById("paired-devices-list");
        try {
            const resp = await apiFetch("/api/auth/devices");
            if (!resp.ok) { list.innerHTML = '<p class="pairing-empty">—</p>'; return; }
            const data = await resp.json();
            const devices = data.devices || [];
            if (devices.length === 0) {
                list.innerHTML = '<p class="pairing-empty">' + I18n.t("pair.empty_devices") + '</p>';
                return;
            }
            const myId = getClientId();
            list.innerHTML = devices.map(d => {
                const isSelf = d.client_id === myId;
                const meta = d.meta || {};
                const info = [
                    isSelf ? '<span style="color:#ef4444;font-weight:600">SELF</span>' : '',
                    meta.browser || '',
                    meta.platform || '',
                ].filter(Boolean).join(' · ');
                return `
                <div class="pairing-request${isSelf ? ' pairing-request--self' : ''}">
                    <span class="pairing-request__name">
                        ${escHtml(d.device_name)}
                        ${info ? `<br><small style="color:var(--color-text-muted)">${info}</small>` : ''}
                        <br><code style="font-size:0.85em">${escHtml(d.client_id ? d.client_id.substring(0, 8) : '-')}</code>
                        <small>${d.expired ? 'expired' : 'active'}</small>
                    </span>
                    <div class="pairing-request__actions">
                        <button class="btn btn--danger btn--tiny" onclick="window._ccRevokeDevice('${d.client_id}')" title="Revoke">✕</button>
                    </div>
                </div>
                `;
            }).join("");
        } catch (_) {}
    }

    window._ccRevokeDevice = async function(clientId) {
        try {
            await apiFetch(`/api/auth/devices/${encodeURIComponent(clientId)}`, { method: "DELETE" });
            loadPairedDevices();
        } catch (_) {}
    };

    function escHtml(str) {
        const div = document.createElement("div");
        div.textContent = str;
        return div.innerHTML;
    }

    // ---- Install modal (remote / Docker) ----

    function showInstallModal(oneLiner) {
        // Remove any existing modal
        const old = document.getElementById("install-modal");
        if (old) old.remove();

        const modal = document.createElement("div");
        modal.id = "install-modal";
        modal.className = "modal-overlay";
        modal.innerHTML = `
            <div class="modal">
                <h2 class="modal__title">${I18n.t("modal.install_title")}</h2>
                <div class="modal__warning">
                    ${I18n.t("modal.install_warning")}<br>
                    <a href="https://github.com/BolunHan/cc-monitor" target="_blank" rel="noopener">
                        github.com/BolunHan/cc-monitor
                    </a>
                </div>
                <p class="modal__desc">${I18n.t("modal.install_desc")}</p>
                <div class="modal__cmd">
                    <code id="install-oneliner">${escapeHtml(oneLiner)}</code>
                </div>
                <div class="modal__actions">
                    <button class="btn btn--primary" id="btn-copy-oneliner">${I18n.t("modal.copy")}</button>
                    <button class="btn" id="btn-close-modal">${I18n.t("modal.close")}</button>
                </div>
                <span class="modal__feedback" id="modal-feedback"></span>
            </div>
        `;
        document.body.appendChild(modal);

        // Copy button
        document.getElementById("btn-copy-oneliner").addEventListener("click", () => {
            navigator.clipboard.writeText(oneLiner).then(() => {
                const fb = document.getElementById("modal-feedback");
                fb.textContent = I18n.t("modal.copied");
                fb.className = "modal__feedback success";
                setTimeout(() => { fb.textContent = ""; fb.className = "modal__feedback"; }, 2000);
            }).catch(() => {
                // Fallback: select the text
                const el = document.getElementById("install-oneliner");
                const range = document.createRange();
                range.selectNodeContents(el);
                const sel = window.getSelection();
                sel.removeAllRanges();
                sel.addRange(range);
            });
        });

        // Close button + click-outside
        document.getElementById("btn-close-modal").addEventListener("click", () => modal.remove());
        modal.addEventListener("click", (e) => { if (e.target === modal) modal.remove(); });
    }

    // ---- Pairing modal (unauthorized web UI) ----

    const btnPairDevice = document.getElementById("btn-pair-device");
    const pairFeedback = document.getElementById("pair-feedback");
    let pairingCode = "";
    let pairingRequestId = "";
    let _pairPollTimer = null;

    function generatePairingCode() {
        return String(Math.floor(100000 + Math.random() * 900000));
    }

    btnPairDevice.addEventListener("click", async () => {
        pairingCode = generatePairingCode();
        const serverUrl = getServerUrl();
        const approveCmd = `cc-monitor --approve ${pairingCode}`;

        // Submit pairing request
        let requestId = "";
        try {
            const resp = await apiFetch("/api/auth/pair/request", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    device_name: "Web Dashboard",
                    pairing_code: pairingCode,
                    client_id: getClientId(),
                    device_meta: {
                        browser: navigator.userAgent.includes("Firefox") ? "Firefox" :
                                 navigator.userAgent.includes("Chrome") ? "Chrome" :
                                 navigator.userAgent.includes("Safari") ? "Safari" : "Unknown",
                        platform: navigator.platform || "Unknown",
                    },
                }),
            });
            const data = await resp.json();
            requestId = data.request_id;
            pairingRequestId = requestId;
        } catch (err) {
            pairFeedback.textContent = I18n.t("pair.failed_submit");
            pairFeedback.className = "install-feedback error";
            return;
        }

        // Build modal
        const old = document.getElementById("pairing-modal");
        if (old) old.remove();

        const modal = document.createElement("div");
        modal.id = "pairing-modal";
        modal.className = "modal-overlay";
        modal.innerHTML = `
            <div class="modal">
                <h2 class="modal__title">${I18n.t("pair.modal_title")}</h2>
                <div class="modal__warning">
                    ${I18n.t("pair.modal_warning")}<br>
                    <a href="https://github.com/BolunHan/cc-monitor" target="_blank" rel="noopener">
                        github.com/BolunHan/cc-monitor
                    </a>
                </div>
                <p class="modal__desc">${I18n.t("pair.code_label")} <strong style="font-size:22px;letter-spacing:4px;">${pairingCode}</strong></p>
                <p class="modal__desc">${I18n.t("pair.approve_hint")}</p>
                <div class="modal__cmd">
                    <code id="pair-oneliner">${escapeHtml(approveCmd)}</code>
                </div>
                <div class="modal__actions">
                    <button class="btn btn--primary" id="btn-copy-pair">${I18n.t("modal.copy")}</button>
                    <button class="btn" id="btn-close-pair">${I18n.t("modal.close")}</button>
                </div>
                <div class="modal__log" id="pair-log">
                    <div class="modal__log-entry">${I18n.t("pair.waiting")}</div>
                </div>
            </div>
        `;
        document.body.appendChild(modal);

        // Copy button
        document.getElementById("btn-copy-pair").addEventListener("click", () => {
            navigator.clipboard.writeText(approveCmd).then(() => {
                const fb = document.getElementById("pair-log");
                fb.innerHTML += '<div class="modal__log-entry success">✓ copied to clipboard</div>';
            });
        });

        // Close + cleanup
        document.getElementById("btn-close-pair").addEventListener("click", () => {
            modal.remove();
            stopPairStatusPoll();
        });
        modal.addEventListener("click", (e) => {
            if (e.target === modal) { modal.remove(); stopPairStatusPoll(); }
        });

        // Start polling
        startPairStatusPoll(requestId, modal);
    });

    function startPairStatusPoll(requestId, modal) {
        const log = modal.querySelector("#pair-log");
        let attempts = 0;
        _pairPollTimer = setInterval(async () => {
            try {
                const resp = await apiFetch(`/api/auth/pair/request/${requestId}/status`);
                const data = await resp.json();
                attempts++;
                log.innerHTML += `<div class="modal__log-entry">[${attempts}] status: ${data.status}</div>`;
                if (data.status === "approved") {
                    log.innerHTML += '<div class="modal__log-entry success">' + I18n.t("pair.approved") + '</div>';
                    stopPairStatusPoll();
                    // The token was returned to the approver; re-submit to get a new one
                    // For now, close the modal — user needs to refresh
                    setTimeout(() => {
                        log.innerHTML += '<div class="modal__log-entry">' + I18n.t("pair.reloading") + '</div>';
                        // Actually, we need the token. Let's re-request.
                        reRequestToken(requestId, modal);
                    }, 1000);
                } else if (data.status === "denied") {
                    log.innerHTML += '<div class="modal__log-entry error">' + I18n.t("pair.denied") + '</div>';
                    stopPairStatusPoll();
                }
            } catch (err) {
                log.innerHTML += `<div class="modal__log-entry error">Poll error: ${err}</div>`;
            }
        }, 2000);
    }

    function stopPairStatusPoll() {
        if (_pairPollTimer) {
            clearInterval(_pairPollTimer);
            _pairPollTimer = null;
        }
    }

    async function reRequestToken(requestId, modal) {
        const log = modal.querySelector("#pair-log");
        try {
            const resp = await apiFetch("/api/auth/pair/request", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    device_name: "Web Dashboard",
                    pairing_code: pairingCode,
                    client_id: getClientId(),
                    device_meta: {
                        browser: navigator.userAgent.includes("Firefox") ? "Firefox" :
                                 navigator.userAgent.includes("Chrome") ? "Chrome" :
                                 navigator.userAgent.includes("Safari") ? "Safari" : "Unknown",
                        platform: navigator.platform || "Unknown",
                    },
                }),
            });
            const data = await resp.json();
            if (data.token) {
                log.innerHTML += '<div class="modal__log-entry success">' + I18n.t("pair.paired") + '</div>';
                setAuthToken(data.token);
                updateUnauthorizedUI(false);
                setTimeout(() => {
                    modal.remove();
                    connectSSE();
                    loadSessions();
                    loadVersion();
                    checkHooksStatus();
                }, 500);
            }
        } catch (err) {
            log.innerHTML += `<div class="modal__log-entry error">Re-request failed: ${err}</div>`;
        }
    }

    // ---- Language switch ----

    const langSwitch = document.getElementById("lang-switch");

    langSwitch.addEventListener("change", () => {
        I18n.setLang(langSwitch.value);
    });

    // ---- Initialise ----

    requestNotificationPermission();
    populateSettingsInputs();

    // Load i18n first, then bootstrap
    (async () => {
        const savedLang = localStorage.getItem("cc-monitor-lang") || "en";
        langSwitch.value = savedLang;
        await I18n.load(savedLang);
        I18n.renderAll();
        loadVersion();
        checkHooksStatus();
        await loadSessions();
        if (lastHeartbeat === 0) setConnected(true);
        connectSSE();
    })();
})();
