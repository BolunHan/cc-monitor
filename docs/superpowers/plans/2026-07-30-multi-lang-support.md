# Multi-Language Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add English + Simplified Chinese i18n to the web dashboard (manual switch) and Android app (auto system locale).

**Architecture:** Web uses a lightweight `I18n` class with JSON files loaded via `fetch()` and `data-i18n` DOM attributes. Android uses Flutter's built-in `flutter_localizations` with ARB files and code generation. Both follow their platform's standard i18n approach.

**Tech Stack:** Vanilla JS (web), Flutter `flutter_localizations` + `intl` + `flutter gen-l10n` (Android)

## Global Constraints

- Languages: English (en, default) and Simplified Chinese (zh-CN web / zh Flutter)
- Web: manual `<select>` switch in header, persisted to localStorage
- Android: auto-detected from device system locale, falls back to en
- No RTL support needed (both are LTR)
- No server-side changes — frontends handle language independently

---

## Part A: Web Frontend

### Task 1: Create English i18n JSON file

**Files:**
- Create: `static/i18n/en.json`

**Interfaces:**
- Produces: JSON file consumed by `I18n.load('en')` in Task 3

- [ ] **Step 1: Write `static/i18n/en.json`**

```json
{
  "header.title": "cc-monitor",
  "connection.connected": "connected",
  "connection.disconnected": "disconnected",
  "connection.connecting": "connecting",
  "hooks.badge": "⚠ global hooks not installed",
  "hooks.install": "Install Global Hooks",
  "hooks.installing": "installing…",
  "hooks.installed": "✓ {n} hooks installed",
  "hooks.unreachable": "✗ server unreachable",
  "hooks.checking": "checking…",
  "hooks.installed_status": "✓ installed",
  "hooks.not_installed_status": "not installed",
  "hooks.remove_failed": "✗ {detail}",
  "hooks.removing": "removing…",
  "hooks.removed": "✓ {n} hooks removed",
  "unauth.badge": "🔒 unauthorized access",
  "unauth.pair": "Pair",
  "settings.title": "Settings",
  "settings.server_url": "Server URL",
  "settings.port": "Port",
  "settings.save": "Save & Reconnect",
  "settings.saved": "✓ saved, reconnecting…",
  "settings.url_required": "✗ Server URL is required",
  "settings.hook_status": "Global hooks",
  "settings.check": "Check",
  "settings.uninstall": "Uninstall",
  "section.active": "Active",
  "section.complete": "Complete",
  "section.archived": "Archived",
  "empty.active": "No active sessions",
  "empty.complete": "No completed sessions",
  "empty.archived": "No archived sessions",
  "state.working": "working",
  "state.idle": "idle",
  "state.pending_approval": "pending approval",
  "state.pending_review": "pending review",
  "state.all_done": "all done",
  "state.archived": "archived",
  "card.archive": "Archive",
  "card.unarchive": "Unarchive",
  "card.mark_done": "Mark Done",
  "time.just_now": "just now",
  "time.seconds_ago": "{n}s ago",
  "time.minutes_ago": "{n}m ago",
  "time.hours_ago": "{n}h ago",
  "notify.pending_review.title": "{name} — Pending Review",
  "notify.pending_review.body": "Claude finished responding. Review the output.",
  "notify.idle.title": "{name} — Task Complete",
  "notify.idle.body": "Claude Code is idle, waiting for your input.",
  "notify.pending_approval.title": "{name} — Pending Approval",
  "notify.pending_approval.body": "Claude Code needs permission to proceed.",
  "modal.install_title": "Install cc-monitor Hooks",
  "modal.install_warning": "⚠ This script modifies ~/.claude/settings.json directly. Only run installers from the trusted cc-monitor repository:",
  "modal.install_desc": "Run this command on the machine where Claude Code runs:",
  "modal.copy": "Copy",
  "modal.copied": "✓ copied",
  "modal.close": "Close",
  "pair.title": "Pair Device",
  "pair.qr_col_title": "QR Code",
  "pair.qr_hint": "Scan with cc-monitor Android app",
  "pair.requests_title": "Pending Requests",
  "pair.devices_title": "Paired Devices",
  "pair.empty_requests": "No pending requests",
  "pair.empty_devices": "No paired devices",
  "pair.error": "Pairing not available — start server with --host 0.0.0.0",
  "pair.unreachable": "Server unreachable or auth not enabled",
  "pair.waiting": "Waiting for approval…",
  "pair.approved": "✓ Approved!",
  "pair.denied": "✗ Denied",
  "pair.paired": "✓ Paired! Token saved.",
  "pair.reloading": "Reloading page to apply token…",
  "pair.failed_submit": "✗ failed to submit pairing request",
  "pair.modal_title": "Pair Web Dashboard",
  "pair.modal_warning": "⚠ This dashboard needs authorization to access the cc-monitor server. Only approve if you initiated this pairing from a trusted source:",
  "pair.code_label": "Pairing code:",
  "pair.approve_hint": "Approve with this command on the server machine:",
  "footer.version": "cc-monitor v{version}",
  "docker_badge.docker": "🐳 Docker",
  "docker_badge.native": "🖥 Native"
}
```

- [ ] **Step 2: Commit**

```bash
git add static/i18n/en.json
git commit -m "feat(i18n): add English translation JSON for web dashboard"
```

---

### Task 2: Create Simplified Chinese i18n JSON file

**Files:**
- Create: `static/i18n/zh-CN.json`

**Interfaces:**
- Produces: JSON file consumed by `I18n.load('zh-CN')` in Task 3

- [ ] **Step 1: Write `static/i18n/zh-CN.json`**

```json
{
  "header.title": "cc-monitor",
  "connection.connected": "已连接",
  "connection.disconnected": "已断开",
  "connection.connecting": "连接中",
  "hooks.badge": "⚠ 未安装全局钩子",
  "hooks.install": "安装全局钩子",
  "hooks.installing": "安装中…",
  "hooks.installed": "✓ 已安装 {n} 个钩子",
  "hooks.unreachable": "✗ 服务器不可达",
  "hooks.checking": "检查中…",
  "hooks.installed_status": "✓ 已安装",
  "hooks.not_installed_status": "未安装",
  "hooks.remove_failed": "✗ {detail}",
  "hooks.removing": "移除中…",
  "hooks.removed": "✓ 已移除 {n} 个钩子",
  "unauth.badge": "🔒 未授权访问",
  "unauth.pair": "配对",
  "settings.title": "设置",
  "settings.server_url": "服务器 URL",
  "settings.port": "端口",
  "settings.save": "保存并重连",
  "settings.saved": "✓ 已保存，重连中…",
  "settings.url_required": "✗ 服务器 URL 不能为空",
  "settings.hook_status": "全局钩子",
  "settings.check": "检查",
  "settings.uninstall": "卸载",
  "section.active": "活跃",
  "section.complete": "已完成",
  "section.archived": "已归档",
  "empty.active": "无活跃会话",
  "empty.complete": "无已完成会话",
  "empty.archived": "无已归档会话",
  "state.working": "工作中",
  "state.idle": "空闲",
  "state.pending_approval": "等待批准",
  "state.pending_review": "等待审阅",
  "state.all_done": "全部完成",
  "state.archived": "已归档",
  "card.archive": "归档",
  "card.unarchive": "取消归档",
  "card.mark_done": "标记完成",
  "time.just_now": "刚刚",
  "time.seconds_ago": "{n}秒前",
  "time.minutes_ago": "{n}分钟前",
  "time.hours_ago": "{n}小时前",
  "notify.pending_review.title": "{name} — 等待审阅",
  "notify.pending_review.body": "Claude 已完成响应，请审阅输出。",
  "notify.idle.title": "{name} — 任务完成",
  "notify.idle.body": "Claude Code 空闲中，等待你的输入。",
  "notify.pending_approval.title": "{name} — 等待批准",
  "notify.pending_approval.body": "Claude Code 需要权限才能继续。",
  "modal.install_title": "安装 cc-monitor 钩子",
  "modal.install_warning": "⚠ 此脚本将直接修改 ~/.claude/settings.json。请仅从受信任的 cc-monitor 仓库运行安装程序：",
  "modal.install_desc": "在运行 Claude Code 的机器上执行此命令：",
  "modal.copy": "复制",
  "modal.copied": "✓ 已复制",
  "modal.close": "关闭",
  "pair.title": "配对设备",
  "pair.qr_col_title": "二维码",
  "pair.qr_hint": "使用 cc-monitor Android 应用扫描",
  "pair.requests_title": "待处理请求",
  "pair.devices_title": "已配对设备",
  "pair.empty_requests": "无待处理请求",
  "pair.empty_devices": "无已配对设备",
  "pair.error": "配对不可用 — 使用 --host 0.0.0.0 启动服务器",
  "pair.unreachable": "服务器不可达或未启用认证",
  "pair.waiting": "等待批准…",
  "pair.approved": "✓ 已批准！",
  "pair.denied": "✗ 已拒绝",
  "pair.paired": "✓ 已配对！令牌已保存。",
  "pair.reloading": "刷新页面以应用令牌…",
  "pair.failed_submit": "✗ 提交配对请求失败",
  "pair.modal_title": "配对 Web 控制台",
  "pair.modal_warning": "⚠ 此控制台需要授权才能访问 cc-monitor 服务器。只有从受信任来源发起配对时才批准：",
  "pair.code_label": "配对码：",
  "pair.approve_hint": "在服务器机器上运行此命令批准：",
  "footer.version": "cc-monitor v{version}",
  "docker_badge.docker": "🐳 Docker",
  "docker_badge.native": "🖥 原生"
}
```

- [ ] **Step 2: Commit**

```bash
git add static/i18n/zh-CN.json
git commit -m "feat(i18n): add Simplified Chinese translation JSON for web dashboard"
```

---

### Task 3: Add I18n class and language switch to web frontend

**Files:**
- Modify: `static/js/app.js` — add I18n class at top, modify all dynamic string sites
- Modify: `static/index.html` — add `data-i18n` attributes and language switch
- Modify: `static/css/app.css` — style `.lang-switch`

**Interfaces:**
- Consumes: `static/i18n/{lang}.json` from Tasks 1 & 2
- Produces: `I18n.t(key, vars?)` callable from anywhere in app.js; `I18n.current` → current lang code

- [ ] **Step 1: Add I18n class to `app.js`**

Insert after the `"use strict"` / IIFE opening, before `STORAGE_KEY_URL`:

```js
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
```

- [ ] **Step 2: Replace string sites in `app.js` — `setConnected()`**

```js
// Before
function setConnected(state) {
    if (indicator) indicator.classList.toggle("connected", state);
    if (label) label.textContent = state ? "connected" : "disconnected";
}

// After
function setConnected(state) {
    if (indicator) indicator.classList.toggle("connected", state);
    if (label) label.textContent = state ? I18n.t("connection.connected") : I18n.t("connection.disconnected");
}
```

- [ ] **Step 3: Replace `relativeTime()`**

```js
// Before
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

// After
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
```

- [ ] **Step 4: Replace `createCard()` badge and button strings**

```js
// In createCard(), replace:
//   const badgeLabel = isArchived ? "archived" : session.state.replace("_", " ");
// With:
const badgeLabel = isArchived ? I18n.t("state.archived") : I18n.t("state." + session.state);

// Replace button labels:
//   actions += `<button ...>Archive</button>`;
// With:
if (section === "active" || section === "complete") {
    actions += `<button class="btn--card btn--card-archive" data-action="archive" data-sid="${escapeHtml(session.session_id)}">${I18n.t("card.archive")}</button>`;
} else {
    actions += `<button class="btn--card btn--card-unarchive" data-action="unarchive" data-sid="${escapeHtml(session.session_id)}">${I18n.t("card.unarchive")}</button>`;
}
if (section === "active") {
    actions += `<button class="btn--card btn--card-complete" data-action="complete" data-sid="${escapeHtml(session.session_id)}">${I18n.t("card.mark_done")}</button>`;
}
```

- [ ] **Step 5: Replace `notify()` strings**

```js
// Before
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

// After
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
```

- [ ] **Step 6: Replace hook management strings**

```js
// updateHookStatusUI():
if (settingsHookStatus) {
    settingsHookStatus.textContent = installed ? I18n.t("hooks.installed_status") : I18n.t("hooks.not_installed_status");
    settingsHookStatus.className = "settings-panel__hook-status " + (installed ? "installed" : "not-installed");
}

// btnInstall click handler — replace string literals:
installFeedback.textContent = I18n.t("hooks.installing");
// ... on success:
installFeedback.textContent = I18n.t("hooks.installed", {n: data.installed_events});
// ... on error:
installFeedback.textContent = I18n.t("hooks.remove_failed", {detail: data.detail});
// ... on unreachable:
installFeedback.textContent = I18n.t("hooks.unreachable");

// btnUninstall click handler:
settingsFeedback.textContent = I18n.t("hooks.removing");
// ... on success:
settingsFeedback.textContent = I18n.t("hooks.removed", {n: data.removed_entries});
```

- [ ] **Step 7: Replace settings strings**

```js
// In btnSaveSettings handler:
settingsFeedback.textContent = I18n.t("settings.url_required");
settingsFeedback.textContent = I18n.t("settings.saved");
```

- [ ] **Step 8: Replace install modal strings**

In `showInstallModal()`:

```js
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
```

And in the copy button handler:

```js
fb.textContent = I18n.t("modal.copied");
```

- [ ] **Step 9: Replace pairing panel and modal strings**

In all pairing UI code — `loadPairingQR()`, `pollPairingRequests()`, `loadPairedDevices()`, `btnPairDevice` handler, `reRequestToken()`:

```js
// loadPairingQR():
pairQr.innerHTML = '<p class="pairing-error">' + I18n.t("pair.error") + '</p>';
pairQr.innerHTML = '<p class="pairing-error">' + I18n.t("pair.unreachable") + '</p>';

// pollPairingRequests():
pairingRequestsList.innerHTML = '<p class="pairing-empty">' + I18n.t("pair.empty_requests") + '</p>';

// loadPairedDevices():
list.innerHTML = '<p class="pairing-empty">' + I18n.t("pair.empty_devices") + '</p>';

// btnPairDevice handler — modal:
pairFeedback.textContent = I18n.t("pair.failed_submit");
// modal innerHTML:
<h2 class="modal__title">${I18n.t("pair.modal_title")}</h2>
<div class="modal__warning">${I18n.t("pair.modal_warning")}<br>...</div>
<p class="modal__desc">${I18n.t("pair.code_label")} <strong>...</strong></p>
<p class="modal__desc">${I18n.t("pair.approve_hint")}</p>
<div class="modal__cmd"><code>...</code></div>
<button>${I18n.t("modal.copy")}</button>
<button>${I18n.t("modal.close")}</button>

// startPairStatusPoll():
log.innerHTML += '<div class="modal__log-entry">' + I18n.t("pair.waiting") + '</div>';
log.innerHTML += '<div class="modal__log-entry success">' + I18n.t("pair.approved") + '</div>';
log.innerHTML += '<div class="modal__log-entry error">' + I18n.t("pair.denied") + '</div>';
log.innerHTML += '<div class="modal__log-entry">' + I18n.t("pair.reloading") + '</div>';
log.innerHTML += '<div class="modal__log-entry success">' + I18n.t("pair.paired") + '</div>';
```

- [ ] **Step 10: Replace version/docker badge strings**

```js
// In loadVersion():
document.getElementById("footer-version").textContent = I18n.t("footer.version", {version: data.version});
// Docker badge:
badge.textContent = data.docker ? I18n.t("docker_badge.docker") : I18n.t("docker_badge.native");
```

- [ ] **Step 11: Add `data-i18n` attributes and language switch to `index.html`**

Add language switch in `.header__actions` (between connection indicator and pair button):

```html
<div class="header__actions">
    <div id="hooks-banner" class="hooks-banner hidden">
        <span class="hooks-banner__badge" data-i18n="hooks.badge">⚠ global hooks not installed</span>
        <button class="btn btn--warning" id="btn-install-hooks" data-i18n="hooks.install">Install Global Hooks</button>
        <span class="install-feedback" id="install-feedback"></span>
    </div>
    <div id="unauth-banner" class="hooks-banner hidden">
        <span class="hooks-banner__badge" data-i18n="unauth.badge">🔒 unauthorized access</span>
        <button class="btn btn--warning" id="btn-pair-device" data-i18n="unauth.pair">Pair</button>
        <span class="install-feedback" id="pair-feedback"></span>
    </div>
    <div class="header__status">
        <span class="connection-indicator" id="connection-indicator" title="SSE connection status"></span>
        <span class="connection-label" id="connection-label" data-i18n="connection.connecting">connecting</span>
    </div>
    <select id="lang-switch" class="lang-switch" aria-label="Language">
        <option value="en">EN</option>
        <option value="zh-CN">中文</option>
    </select>
    <button class="btn btn--icon" id="btn-pair" title="Pair Device">⧉</button>
    <button class="btn btn--icon" id="btn-settings" title="Settings">⚙</button>
</div>
```

Add `data-i18n` to other HTML elements:

```html
<!-- Pairing panel -->
<h3 class="pairing-panel__title" data-i18n="pair.title">Pair Device</h3>
<div class="pairing-panel__col-title">
    <span data-i18n="pair.qr_col_title">QR Code</span>
    <button class="btn btn--icon btn--small" id="btn-refresh-qr" title="Refresh QR code">⟳</button>
</div>
<p class="pairing-hint" data-i18n="pair.qr_hint">Scan with cc-monitor Android app</p>
<h4 class="pairing-requests__title" data-i18n="pair.requests_title">Pending Requests</h4>
<h4 class="pairing-requests__title" data-i18n="pair.devices_title">Paired Devices</h4>

<!-- Settings panel -->
<h3 class="settings-panel__title"><span data-i18n="settings.title">Settings</span> <span class="settings-panel__docker-badge" id="settings-docker-badge"></span></h3>
<label class="settings-panel__label">
    <span data-i18n="settings.server_url">Server URL</span>
    <input type="text" class="settings-panel__input" id="settings-url" placeholder="http://127.0.0.1">
</label>
<label class="settings-panel__label">
    <span data-i18n="settings.port">Port</span>
    <input type="number" class="settings-panel__input settings-panel__input--short" id="settings-port" placeholder="9876">
</label>
<button class="btn btn--primary" id="btn-save-settings" data-i18n="settings.save">Save &amp; Reconnect</button>
<span class="settings-panel__label-text" data-i18n="settings.hook_status">Global hooks</span>
<button class="btn btn--check btn--small" id="btn-check-hooks" data-i18n="settings.check">Check</button>
<button class="btn btn--danger btn--small" id="btn-uninstall-hooks" data-i18n="settings.uninstall">Uninstall</button>

<!-- Sections -->
<h2 class="section__title" data-i18n="section.active">Active</h2>
<p class="empty-state" id="empty-active" data-i18n="empty.active">No active sessions</p>
<h2 class="section__title" data-i18n="section.complete">Complete</h2>
<p class="empty-state" id="empty-complete" data-i18n="empty.complete">No completed sessions</p>
<h2 class="section__title" data-i18n="section.archived">Archived</h2>
<p class="empty-state" id="empty-archive" data-i18n="empty.archived">No archived sessions</p>
```

- [ ] **Step 12: Add CSS for `.lang-switch`**

Add to `static/css/app.css`:

```css
/* ---- Language Switch ---- */

.lang-switch {
  background: transparent;
  color: var(--color-text-muted);
  border: 1px solid var(--color-border);
  border-radius: 4px;
  padding: 2px 6px;
  font-size: 13px;
  cursor: pointer;
  margin: 0 4px;
}

.lang-switch:focus-visible {
  outline: 1px solid var(--color-accent);
}
```

- [ ] **Step 13: Wire up language switch and init in `app.js`**

Add lang switch event listener in the initialisation section:

```js
// ---- Language switch ----

const langSwitch = document.getElementById("lang-switch");

langSwitch.addEventListener("change", () => {
    I18n.setLang(langSwitch.value);
});
```

Replace startup in initialisation section:

```js
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
```

- [ ] **Step 14: Store extra card metadata for re-render**

In `updateCard()`, store extra fields on the `cards` map so `loadSessionsView()` can re-render cards:

```js
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
```

- [ ] **Step 15: Commit**

```bash
git add static/js/app.js static/index.html static/css/app.css
git commit -m "feat(i18n): add I18n class, language switch, and wire up all web dashboard strings"
```

---

## Part B: Android App

### Task 4: Configure Flutter l10n and create ARB files

**Files:**
- Create: `android_app/l10n.yaml`
- Modify: `android_app/pubspec.yaml`
- Create: `android_app/lib/l10n/app_en.arb`
- Create: `android_app/lib/l10n/app_zh.arb`

**Interfaces:**
- Produces: `AppLocalizations` class (generated by `flutter gen-l10n`), consumed by all screen tasks

- [ ] **Step 1: Modify `pubspec.yaml`**

Replace the existing `flutter:` section and add `intl` dependency:

```yaml
dependencies:
  flutter:
    sdk: flutter
  flutter_localizations:
    sdk: flutter
  intl: ^0.19.0
  dio: ^5.4.0
  flutter_secure_storage: ^10.0.0
  mobile_scanner: ^6.0.0
  provider: ^6.1.0
  multicast_dns: ^0.3.2

dev_dependencies:
  flutter_test:
    sdk: flutter
  flutter_lints: ^3.0.0

flutter:
  uses-material-design: true
  generate: true
```

- [ ] **Step 2: Create `android_app/l10n.yaml`**

```yaml
arb-dir: lib/l10n
template-arb-file: app_en.arb
output-localization-file: app_localizations.dart
synthetic-package: false
nullable-getter: false
```

- [ ] **Step 3: Create `android_app/lib/l10n/app_en.arb`**

```json
{
  "@@locale": "en",
  "appTitle": "cc-monitor",
  "noSessions": "No sessions",
  "activeTab": "Active ({count})",
  "@activeTab": { "placeholders": { "count": {} } },
  "completeTab": "Complete ({count})",
  "@completeTab": { "placeholders": { "count": {} } },
  "archivedTab": "Archived ({count})",
  "@archivedTab": { "placeholders": { "count": {} } },
  "disconnectedBanner": "Disconnected — token revoked or server unreachable.\nRemove this server from the sidebar.",
  "stateWorking": "working",
  "stateIdle": "idle",
  "statePendingApproval": "pending approval",
  "statePendingReview": "pending review",
  "stateAllDone": "all done",
  "stateArchived": "archived",
  "timeJustNow": "just now",
  "timeMinutesAgo": "{n}m ago",
  "@timeMinutesAgo": { "placeholders": { "n": {} } },
  "timeHoursAgo": "{n}h ago",
  "@timeHoursAgo": { "placeholders": { "n": {} } },
  "timeDaysAgo": "{n}d ago",
  "@timeDaysAgo": { "placeholders": { "n": {} } },
  "sseAlive": "SSE alive | {count} events | tap for log",
  "@sseAlive": { "placeholders": { "count": {} } },
  "sseDisconnected": "SSE disconnected | tap for log",
  "eventLogTitle": "SSE Event Log ({filtered}/{total})",
  "@eventLogTitle": { "placeholders": { "filtered": {}, "total": {} } },
  "eventLogEmpty": "No events — waiting for SSE…",
  "eventLogLevel": "Level:",
  "eventLogConnected": "CONNECTED",
  "eventLogDisconnected": "DISCONNECTED",
  "settingsTitle": "Settings",
  "settingsServer": "Server",
  "settingsTokenStatus": "Token Status",
  "settingsTokenValid": "Valid",
  "settingsTokenExpires": "Expires: {date}",
  "@settingsTokenExpires": { "placeholders": { "date": {} } },
  "settingsRotate": "Rotate",
  "settingsPairNew": "Pair New Server",
  "settingsForget": "Forget Server",
  "settingsForgetDesc": "Clear all pairing data",
  "settingsNotifications": "Notifications",
  "settingsSound": "Sound",
  "settingsSoundDesc": "Play sound on alerts",
  "settingsVibration": "Vibration",
  "settingsVibrationDesc": "Vibrate on alerts",
  "settingsAbout": "cc-monitor App",
  "connectTitle": "Connect to Server",
  "connectScanQr": "Scan QR Code",
  "connectManual": "Manual Entry",
  "connectNoServers": "No cc-monitor servers found on LAN",
  "connectScanAgain": "Scan Again",
  "connectManualTitle": "Manual Entry",
  "connectServerIp": "Server IP",
  "connectPort": "Port",
  "connectToken": "Token",
  "connectCancel": "Cancel",
  "connectConnect": "Connect",
  "connectingTitle": "Connecting",
  "pairingCodeLabel": "Pairing Code",
  "verifyCodeHint": "Verify this code on the web dashboard",
  "scanQrTitle": "Scan QR Code",
  "scanFound": "Found! Opening...",
  "scanHint": "Point camera at the QR code shown on the web dashboard",
  "sessionTitle": "Session",
  "sessionNotFound": "Session not found",
  "sessionId": "Session ID",
  "sessionUid": "UID",
  "sessionState": "State",
  "sessionCwd": "CWD",
  "sessionLastEvent": "Last Event",
  "sessionDetail": "Detail",
  "sessionUpdated": "Updated",
  "archive": "Archive",
  "unarchive": "Unarchive",
  "markComplete": "Mark Complete",
  "servers": "Servers",
  "noServersPaired": "No servers paired",
  "addServer": "Add Server"
}
```

- [ ] **Step 4: Create `android_app/lib/l10n/app_zh.arb`**

```json
{
  "@@locale": "zh",
  "appTitle": "cc-monitor",
  "noSessions": "无会话",
  "activeTab": "活跃 ({count})",
  "@activeTab": { "placeholders": { "count": {} } },
  "completeTab": "已完成 ({count})",
  "@completeTab": { "placeholders": { "count": {} } },
  "archivedTab": "已归档 ({count})",
  "@archivedTab": { "placeholders": { "count": {} } },
  "disconnectedBanner": "已断开 — 令牌被撤销或服务器不可达。\n从侧边栏移除此服务器。",
  "stateWorking": "工作中",
  "stateIdle": "空闲",
  "statePendingApproval": "等待批准",
  "statePendingReview": "等待审阅",
  "stateAllDone": "全部完成",
  "stateArchived": "已归档",
  "timeJustNow": "刚刚",
  "timeMinutesAgo": "{n}分钟前",
  "@timeMinutesAgo": { "placeholders": { "n": {} } },
  "timeHoursAgo": "{n}小时前",
  "@timeHoursAgo": { "placeholders": { "n": {} } },
  "timeDaysAgo": "{n}天前",
  "@timeDaysAgo": { "placeholders": { "n": {} } },
  "sseAlive": "SSE 已连接 | {count} 个事件 | 点击查看日志",
  "@sseAlive": { "placeholders": { "count": {} } },
  "sseDisconnected": "SSE 已断开 | 点击查看日志",
  "eventLogTitle": "SSE 事件日志 ({filtered}/{total})",
  "@eventLogTitle": { "placeholders": { "filtered": {}, "total": {} } },
  "eventLogEmpty": "无事件 — 等待 SSE…",
  "eventLogLevel": "级别：",
  "eventLogConnected": "已连接",
  "eventLogDisconnected": "已断开",
  "settingsTitle": "设置",
  "settingsServer": "服务器",
  "settingsTokenStatus": "令牌状态",
  "settingsTokenValid": "有效",
  "settingsTokenExpires": "过期时间：{date}",
  "@settingsTokenExpires": { "placeholders": { "date": {} } },
  "settingsRotate": "刷新",
  "settingsPairNew": "配对新服务器",
  "settingsForget": "忘记服务器",
  "settingsForgetDesc": "清除所有配对数据",
  "settingsNotifications": "通知",
  "settingsSound": "声音",
  "settingsSoundDesc": "提醒时播放声音",
  "settingsVibration": "振动",
  "settingsVibrationDesc": "提醒时振动",
  "settingsAbout": "cc-monitor 应用",
  "connectTitle": "连接服务器",
  "connectScanQr": "扫描二维码",
  "connectManual": "手动输入",
  "connectNoServers": "局域网内未发现 cc-monitor 服务器",
  "connectScanAgain": "重新扫描",
  "connectManualTitle": "手动输入",
  "connectServerIp": "服务器 IP",
  "connectPort": "端口",
  "connectToken": "令牌",
  "connectCancel": "取消",
  "connectConnect": "连接",
  "connectingTitle": "连接中",
  "pairingCodeLabel": "配对码",
  "verifyCodeHint": "在 Web 控制台验证此代码",
  "scanQrTitle": "扫描二维码",
  "scanFound": "已找到！正在打开…",
  "scanHint": "将摄像头对准 Web 控制台显示的二维码",
  "sessionTitle": "会话",
  "sessionNotFound": "未找到会话",
  "sessionId": "会话 ID",
  "sessionUid": "UID",
  "sessionState": "状态",
  "sessionCwd": "工作目录",
  "sessionLastEvent": "最近事件",
  "sessionDetail": "详情",
  "sessionUpdated": "更新时间",
  "archive": "归档",
  "unarchive": "取消归档",
  "markComplete": "标记完成",
  "servers": "服务器",
  "noServersPaired": "无已配对服务器",
  "addServer": "添加服务器"
}
```

- [ ] **Step 5: Run code generation and commit**

```bash
cd android_app && flutter pub get && cd ..
```

Then commit:

```bash
git add android_app/pubspec.yaml android_app/l10n.yaml android_app/lib/l10n/
git commit -m "feat(i18n): add Flutter l10n config and ARB translation files"
```

---

### Task 5: Update Flutter main.dart for locale support

**Files:**
- Modify: `android_app/lib/main.dart`

**Interfaces:**
- Consumes: `AppLocalizations` from Task 4
- Produces: Locale-aware `MaterialApp`

- [ ] **Step 1: Add imports and locale config to `main.dart`**

Add import at top:

```dart
import 'package:flutter_gen/gen_l10n/app_localizations.dart';
```

In `CCMonitorApp.build()`, modify `MaterialApp`:

```dart
return MaterialApp(
  title: 'cc-monitor',
  debugShowCheckedModeBanner: false,
  themeMode: ThemeMode.system,
  theme: AppTheme.light,
  darkTheme: AppTheme.dark,
  supportedLocales: const [Locale('en'), Locale('zh')],
  localizationsDelegates: const [
    AppLocalizations.delegate,
    GlobalMaterialLocalizations.delegate,
    GlobalWidgetsLocalizations.delegate,
    GlobalCupertinoLocalizations.delegate,
  ],
  home: _StartupGate(
    apiClient: apiClient,
  ),
  onGenerateRoute: (settings) { ... },
);
```

- [ ] **Step 2: Run `flutter gen-l10n` to verify generation**

```bash
cd android_app && flutter gen-l10n
```

Expected: `AppLocalizations` class generated at `.dart_tool/flutter_gen/gen_l10n/app_localizations.dart` with typed getters for all ARB keys.

- [ ] **Step 3: Commit**

```bash
git add android_app/lib/main.dart
git commit -m "feat(i18n): add locale support to Flutter MaterialApp"
```

---

### Task 6: Localize Flutter screens

**Files:**
- Modify: `android_app/lib/screens/dashboard_screen.dart`
- Modify: `android_app/lib/screens/settings_screen.dart`
- Modify: `android_app/lib/screens/server_picker_screen.dart`
- Modify: `android_app/lib/screens/pairing_screen.dart`
- Modify: `android_app/lib/screens/session_detail_screen.dart`
- Modify: `android_app/lib/screens/connecting_screen.dart`

**Interfaces:**
- Consumes: `AppLocalizations` from Task 4, `main.dart` locale support from Task 5

- [ ] **Step 1: Localize `dashboard_screen.dart`**

Add import:

```dart
import 'package:flutter_gen/gen_l10n/app_localizations.dart';
```

Replace strings in `_DashboardScreenState.build()`:

```dart
// Before: appBar title
title: const Text('cc-monitor'),

// After:
final l10n = AppLocalizations.of(context)!;
// In appBar:
title: Text(l10n.appTitle),
```

Replace tab labels (inside `DefaultTabController`):

```dart
Tab(text: l10n.activeTab(provider.active.length)),
Tab(text: l10n.completeTab(provider.complete.length)),
Tab(text: l10n.archivedTab(provider.archived.length)),
```

Replace disconnected banner:

```dart
Text(l10n.disconnectedBanner, style: const TextStyle(...)),
```

Replace `_SessionList`:

```dart
// "No sessions" → l10n.noSessions
Text(l10n.noSessions)
```

Replace `_SessionCard` state label — use `l10n` passed via builder or look up. Since `_SessionCard` is a `StatelessWidget`, access via context:

```dart
// Before:
subtitle: Text(session.state.replaceAll('_', ' ')),

// After:
final l10n = AppLocalizations.of(context)!;  // in build()
// then:
subtitle: Text(_stateLabel(session.state, l10n)),
```

Add helper:

```dart
String _stateLabel(String state, AppLocalizations l10n) {
  return switch (state) {
    'working' => l10n.stateWorking,
    'idle' => l10n.stateIdle,
    'pending_approval' => l10n.statePendingApproval,
    'pending_review' => l10n.statePendingReview,
    'all_done' => l10n.stateAllDone,
    _ => l10n.stateArchived,
  };
}
```

Replace `_formatTime()`:

```dart
String _formatTime(DateTime dt, AppLocalizations l10n) {
  final now = DateTime.now();
  final diff = now.difference(dt);
  if (diff.inMinutes < 1) return l10n.timeJustNow;
  if (diff.inMinutes < 60) return l10n.timeMinutesAgo(diff.inMinutes);
  if (diff.inHours < 24) return l10n.timeHoursAgo(diff.inHours);
  return l10n.timeDaysAgo(diff.inDays);
}
```

Replace `_ServerDrawer` strings:

```dart
// "Servers" → l10n.servers
// "No servers paired" → l10n.noServersPaired
// "Add Server" → l10n.addServer
```

Pass `l10n` into `_ServerDrawer` via constructor or access from context inside `build()`.

Replace `_StateBar`:

```dart
// Before:
provider.connected
    ? 'SSE alive | ${log.length} events | tap for log'
    : 'SSE disconnected | tap for log',

// After:
provider.connected
    ? l10n.sseAlive(log.length)
    : l10n.sseDisconnected,
```

Replace `_StateLogSheet`:

```dart
// Title:
Text(l10n.eventLogTitle(log.length, allLog.length), ...)
// Connected/disconnected:
Text(provider.connected ? l10n.eventLogConnected : l10n.eventLogDisconnected, ...)
// Level:
Text(l10n.eventLogLevel, ...)
// Empty:
Text(l10n.eventLogEmpty)
```

- [ ] **Step 2: Localize `settings_screen.dart`**

Add import:

```dart
import 'package:flutter_gen/gen_l10n/app_localizations.dart';
```

Replace strings in `build()`:

```dart
final l10n = AppLocalizations.of(context)!;

// AppBar
AppBar(title: Text(l10n.settingsTitle))

// Server
ListTile(title: Text(l10n.settingsServer), ...)

// Token Status
ListTile(
  title: Text(l10n.settingsTokenStatus),
  subtitle: Text(pp.tokenExpiringSoon
      ? l10n.settingsTokenExpires(pp.tokenExpiresAt)
      : l10n.settingsTokenValid),
  trailing: pp.tokenExpiringSoon
      ? ElevatedButton(onPressed: ..., child: Text(l10n.settingsRotate))
      : null,
)

// Pair New Server
ListTile(title: Text(l10n.settingsPairNew), ...)

// Forget Server
ListTile(
  title: Text(l10n.settingsForget),
  subtitle: Text(l10n.settingsForgetDesc),
  ...
)

// Notifications
ListTile(title: Text(l10n.settingsNotifications), ...)
SwitchListTile(title: Text(l10n.settingsSound), subtitle: Text(l10n.settingsSoundDesc), ...)
SwitchListTile(title: Text(l10n.settingsVibration), subtitle: Text(l10n.settingsVibrationDesc), ...)

// About
ListTile(
  title: Text(l10n.settingsAbout),
  subtitle: const Text('v0.4.1'),
  ...
)
```

- [ ] **Step 3: Localize `server_picker_screen.dart`**

Add import:

```dart
import 'package:flutter_gen/gen_l10n/app_localizations.dart';
```

Replace:

```dart
final l10n = AppLocalizations.of(context)!;

// AppBar
AppBar(title: Text(l10n.connectTitle))

// Buttons
ElevatedButton.icon(label: Text(l10n.connectScanQr), ...)
OutlinedButton.icon(label: Text(l10n.connectManual), ...)

// Empty state
Text(l10n.connectNoServers, ...)
ElevatedButton.icon(label: Text(l10n.connectScanAgain), ...)

// Manual entry dialog
AlertDialog(title: Text(l10n.connectManualTitle))
TextField(decoration: InputDecoration(labelText: l10n.connectServerIp))
TextField(decoration: InputDecoration(labelText: l10n.connectPort))
TextField(decoration: InputDecoration(labelText: l10n.connectToken))
TextButton(onPressed: ..., child: Text(l10n.connectCancel))
ElevatedButton(onPressed: ..., child: Text(l10n.connectConnect))
```

- [ ] **Step 4: Localize `pairing_screen.dart`**

Add import:

```dart
import 'package:flutter_gen/gen_l10n/app_localizations.dart';
```

Replace:

```dart
final l10n = AppLocalizations.of(context)!;

// AppBar
AppBar(title: Text(l10n.scanQrTitle))

// Status text in the overlay
_navigating
    ? l10n.scanFound
    : _lastScan.isNotEmpty
        ? _lastScan
        : l10n.scanHint,
```

- [ ] **Step 5: Localize `session_detail_screen.dart`**

Add import:

```dart
import 'package:flutter_gen/gen_l10n/app_localizations.dart';
```

Replace:

```dart
final l10n = AppLocalizations.of(context)!;

// AppBar (session not found)
AppBar(title: Text(l10n.sessionTitle))
Text(l10n.sessionNotFound)

// Labels
_InfoRow(l10n.sessionId, session.sessionId),
_InfoRow(l10n.sessionUid, session.ccMonitorUid),
_InfoRow(l10n.sessionState, session.state),
_InfoRow(l10n.sessionCwd, session.cwd),
_InfoRow(l10n.sessionLastEvent, session.rawEvent),
_InfoRow(l10n.sessionDetail, session.rawDetail!),
_InfoRow(l10n.sessionUpdated, session.updatedAt.toString()),

// Buttons
ElevatedButton.icon(label: Text(l10n.archive), ...)
ElevatedButton.icon(label: Text(l10n.unarchive), ...)
ElevatedButton.icon(label: Text(l10n.markComplete), ...)
```

- [ ] **Step 6: Localize `connecting_screen.dart`**

Add import:

```dart
import 'package:flutter_gen/gen_l10n/app_localizations.dart';
```

Replace:

```dart
final l10n = AppLocalizations.of(context)!;

// AppBar
AppBar(title: Text(l10n.connectingTitle))

// Pairing code section
Text(l10n.pairingCodeLabel, style: const TextStyle(...))
Text(l10n.verifyCodeHint, style: const TextStyle(...))
```

- [ ] **Step 7: Run Flutter analyze to check for errors**

```bash
cd android_app && flutter analyze
```

Fix any type errors — `l10n` needs to be accessed inside `build()` methods where `context` is available. For nested `StatelessWidget`s like `_SessionCard`, either pass `l10n` as a constructor parameter or access via `BuildContext`.

- [ ] **Step 8: Commit**

```bash
git add android_app/lib/screens/
git commit -m "feat(i18n): localize all Flutter screens with AppLocalizations"
```

---

### Task 7: Verify and test

**Files:**
- None (verification only)

- [ ] **Step 1: Verify web frontend i18n**

```bash
# Start cc-monitor server
cd /home/bolun/Projects/cc-monitor && source ~/Projects/venv_313/bin/activate && cc-monitor --port 9876 &
sleep 2
# Fetch i18n files
curl -s http://127.0.0.1:9876/static/i18n/en.json | python3 -m json.tool > /dev/null && echo "EN OK" || echo "EN FAIL"
curl -s http://127.0.0.1:9876/static/i18n/zh-CN.json | python3 -m json.tool > /dev/null && echo "ZH OK" || echo "ZH FAIL"
# Serve the static files through the existing mount
echo "Open http://127.0.0.1:9876 in browser to test language switch"
```

- [ ] **Step 2: Verify Flutter app builds**

```bash
cd android_app && flutter build apk --debug
```

Check that the build succeeds with no l10n-related errors.

- [ ] **Step 3: Run existing tests**

```bash
cd /home/bolun/Projects/cc-monitor && source ~/Projects/venv_313/bin/activate && python -m pytest tests/ -v
```

Expected: all existing 101 tests pass (no backend changes).

- [ ] **Step 4: Commit if any fixes**

```bash
git add -A && git commit -m "chore(i18n): verification fixes"
```
