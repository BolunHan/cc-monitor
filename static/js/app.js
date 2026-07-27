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
            new Notification(title, { body, tag: session.session_id });
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
        cards.forEach((_, sid) => {
            const s = prevStates.get(sid);
            if (s) counts[getSection({archived: s.archived, state: s.state})]++;
        });
        for (const sec of ["active", "complete", "archive"]) {
            getCount(sec).textContent = counts[sec];
        }
    }

    // ---- Session Cards ----

    function createCard(session) {
        const card = document.createElement("div");
        card.className = "session-card";
        card.id = `card-${session.session_id}`;

        const basename = dirBasename(session.cwd);
        const title = basename || session.session_id.substring(0, 8) + "…";
        const subtitle = basename ? escapeHtml(session.session_id) : "";
        const summary = session.summary
            ? `<div class="session-card__summary" title="${escapeHtml(session.summary)}">${escapeHtml(truncate(session.summary, 100))}</div>`
            : "";

        const section = getSection(session);
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
            ${summary}
            <div class="session-card__detail">
                <strong>cwd:</strong> ${escapeHtml(session.cwd || "—")}<br>
                <strong>event:</strong> ${escapeHtml(session.raw_event || "—")}
                ${session.raw_detail ? ` (${escapeHtml(session.raw_detail)})` : ""}
            </div>
            <div class="session-card__time">${relativeTime(session.updated_at)}</div>
            ${actions ? `<div class="session-card__actions">${actions}</div>` : ""}
        `;
        return card;
    }

    function placeCard(session, cardEl) {
        const section = getSection(session);
        const grid = getGrid(section);
        const empty = getEmpty(section);
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
        empty.style.display = "none";
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
            getGrid(sec).querySelectorAll(".session-card").forEach(c => c.remove());
            getEmpty(sec).style.removeProperty("display");
            getCount(sec).textContent = "0";
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
        clearAllCards();
        setConnected(false);
        lastHeartbeat = 0;
        label.textContent = "connecting";

        const es = new EventSource(apiUrl("/api/stream"));
        currentEventSource = es;

        es.addEventListener("open", () => {
            lastHeartbeat = Date.now();
            setConnected(true);
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
        try {
            const resp = await fetch(apiUrl("/api/hooks-status"));
            const data = await resp.json();
            updateHookStatusUI(data.installed);
        } catch (err) {
            updateHookStatusUI(false);
        }
    }

    btnInstall.addEventListener("click", async () => {
        btnInstall.disabled = true;
        installFeedback.textContent = "installing…";
        installFeedback.className = "install-feedback";
        try {
            const resp = await fetch(apiUrl("/api/install-hooks"), { method: "POST" });
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

    // ---- Initialise ----

    requestNotificationPermission();
    populateSettingsInputs();
    loadVersion();
    checkHooksStatus();
    connectSSE();
})();
