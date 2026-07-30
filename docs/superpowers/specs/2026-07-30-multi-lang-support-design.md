# Multi-Language Support — Design Spec

**Date:** 2026-07-30
**Status:** draft

## Overview

Add i18n support to both the web dashboard and Android app. Two languages: **English** (default) and **Simplified Chinese** (zh-CN).

- **Web**: Manual language switch button in header, user choice persisted to localStorage, JSON translation files
- **Android**: Auto-detected from device system locale, falls back to English, Flutter-standard ARB localization

---

## Web Frontend (`static/`)

### i18n JSON Structure

Flat key-value map. Keys follow `context.element` naming. Dynamic strings use `{placeholder}` interpolation.

Files:
- `static/i18n/en.json` — English (authoritative, all keys defined here)
- `static/i18n/zh-CN.json` — Simplified Chinese (mirrors all keys)

```json
{
  "header.title": "cc-monitor",
  "connection.connected": "connected",
  "connection.disconnected": "disconnected",
  "hooks.banner.badge": "⚠ global hooks not installed",
  "hooks.banner.install": "Install Global Hooks",
  "settings.title": "Settings",
  "settings.server_url": "Server URL",
  "settings.port": "Port",
  "settings.save": "Save & Reconnect",
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
  "install_modal.title": "Install cc-monitor Hooks",
  "install_modal.desc": "Run this command on the machine where Claude Code runs:",
  "install_modal.copy": "Copy",
  "install_modal.close": "Close",
  "pair.title": "Pair Device",
  "pair.qr_title": "QR Code",
  "pair.refresh_qr": "⟳",
  "pair.scan_hint": "Scan with cc-monitor Android app",
  "pair.requests_title": "Pending Requests",
  "pair.devices_title": "Paired Devices",
  "pair.empty_requests": "No pending requests",
  "pair.empty_devices": "No paired devices",
  "unauth.badge": "🔒 unauthorized access",
  "unauth.pair": "Pair",
  "footer.version": "cc-monitor v{version}",
  "sse.alive": "SSE alive | {count} events | tap for log",
  "sse.disconnected": "SSE disconnected | tap for log",
  "disconnected.banner": "Disconnected — token revoked or server unreachable.\nRemove this server from the sidebar."
}
```

### I18n Class (embedded in `js/app.js`)

```js
const I18n = (() => {
  let _lang = 'en';
  let _data = null;

  async function load(lang) {
    try {
      const resp = await fetch(`./i18n/${lang}.json`);
      if (!resp.ok) throw new Error('not found');
      _data = await resp.json();
      _lang = lang;
    } catch (_) {
      // Fallback to English
      if (lang !== 'en') return load('en');
    }
  }

  function t(key, vars) {
    let s = (_data && _data[key]) || key;
    if (vars) {
      for (const [k, v] of Object.entries(vars)) {
        s = s.replace(`{${k}}`, v);
      }
    }
    return s;
  }

  function renderAll() {
    document.querySelectorAll('[data-i18n]').forEach(el => {
      const key = el.dataset.i18n;
      if (key) el.textContent = t(key);
    });
  }

  async function setLang(lang) {
    localStorage.setItem('cc-monitor-lang', lang);
    await load(lang);
    renderAll();
    // Re-render dynamic content
    loadSessions();
    loadVersion();
    checkHooksStatus();
  }

  function current() { return _lang; }

  return { load, t, renderAll, setLang, current };
})();
```

### HTML Changes

Add `data-i18n` attributes to all text-bearing elements. Example:

```html
<!-- Before -->
<h1 class="header__title">cc-monitor</h1>
<button class="btn btn--warning" id="btn-install-hooks">Install Global Hooks</button>

<!-- After -->
<h1 class="header__title" data-i18n="header.title">cc-monitor</h1>
<button class="btn btn--warning" id="btn-install-hooks" data-i18n="hooks.banner.install">Install Global Hooks</button>
```

The hardcoded text stays as fallback content (visible before JS loads, or if JS fails). `I18n.renderAll()` overwrites with the translated version once the JSON is loaded.

### Language Switch UI

A `<select>` dropdown in `.header__actions` between the connection status and the settings button:

```html
<select id="lang-switch" class="lang-switch" aria-label="Language">
  <option value="en">EN</option>
  <option value="zh-CN">中文</option>
</select>
```

Styled to match the dark header (transparent bg, muted text, no border — blends with the header). On change: `I18n.setLang(value)`.

### JS Changes

All dynamic string construction replaced with `I18n.t()` calls:

| Current | New |
|---------|-----|
| `'just now'` | `I18n.t('time.just_now')` |
| `` `${minutes}m ago` `` | `I18n.t('time.minutes_ago', {n: minutes})` |
| `` `${basename} — Pending Review` `` | `I18n.t('notify.pending_review.title', {name: basename})` |
| `'connected'` / `'disconnected'` | `I18n.t('connection.connected')` / `I18n.t('connection.disconnected')` |
| Section tab labels, state badges, button labels | All via `I18n.t()` |

State badge text dynamically computed from `session.state` → `I18n.t('state.' + session.state)`.

### Startup Flow

1. HTML loads with English fallback text visible
2. `app.js` inits: read `localStorage['cc-monitor-lang']` → default `'en'`
3. `I18n.load(lang)` fetches JSON
4. `I18n.renderAll()` replaces all `[data-i18n]` text
5. SSE/REST flow continues as before
6. On `<select>` change → `I18n.setLang()` → reload JSON → re-render → refresh sessions/version

### CSS

New rules for `.lang-switch`:

```css
.lang-switch {
  background: transparent;
  color: var(--color-text-muted);
  border: 1px solid var(--color-border);
  border-radius: 4px;
  padding: 2px 6px;
  font-size: 13px;
  cursor: pointer;
}
.lang-switch:focus-visible {
  outline: 1px solid var(--color-accent);
}
```

---

## Android App (`android_app/`)

### Dependencies

`pubspec.yaml` additions:

```yaml
dependencies:
  flutter_localizations:
    sdk: flutter
  intl: ^0.19.0

flutter:
  generate: true
```

### l10n Configuration

`android_app/l10n.yaml`:

```yaml
arb-dir: lib/l10n
template-arb-file: app_en.arb
output-localization-file: app_localizations.dart
synthetic-package: false
nullable-getter: false
```

### ARB Files

**`lib/l10n/app_en.arb`** (template):

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
  "settingsVersion": "v0.4.1",
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
  "connecting": "Connecting",
  "connectingTitle": "Connecting",
  "pairingCode": "Pairing Code",
  "verifyCode": "Verify this code on the web dashboard",
  "scanQrTitle": "Scan QR Code",
  "scanFound": "Found! Opening...",
  "scanHint": "Point camera at the QR code shown on the web dashboard",
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
  "addServer": "Add Server",
  "connected": "CONNECTED",
  "disconnected": "DISCONNECTED"
}
```

**`lib/l10n/app_zh.arb`** (Simplified Chinese — key translations TBD during implementation, all keys mirrored):

```json
{
  "@@locale": "zh",
  "appTitle": "cc-monitor",
  "noSessions": "无会话",
  ...
}
```

### main.dart Changes

```dart
import 'package:flutter_gen/gen_l10n/app_localizations.dart';

// In CCMonitorApp.build():
MaterialApp(
  title: 'cc-monitor',
  supportedLocales: const [Locale('en'), Locale('zh')],
  localizationsDelegates: const [
    AppLocalizations.delegate,
    GlobalMaterialLocalizations.delegate,
    GlobalWidgetsLocalizations.delegate,
    GlobalCupertinoLocalizations.delegate,
  ],
  ...
)
```

`GlobalMaterialLocalizations` provides translated Material widget labels (date pickers, text fields, etc.) automatically.

### Screen Changes

Every screen imports `AppLocalizations` and uses it for user-visible strings. Pattern:

```dart
import 'package:flutter_gen/gen_l10n/app_localizations.dart';

// In build():
final l10n = AppLocalizations.of(context)!;
// Use: l10n.noSessions, l10n.activeCount(provider.active.length), etc.
```

`AppLocalizations` generated getters are typed — `String` for simple keys, functions for keys with placeholders.

### Locale Resolution

Flutter resolves locale automatically:
1. Reads device `locale.languageCode`
2. Matches against `supportedLocales`
3. Falls back to `en` (template ARB) if device locale is unsupported

No manual `PlatformDispatcher` code needed — `MaterialApp` handles it.

---

## Translation Coverage Summary

| Area | Web strings | Flutter strings |
|------|------------|-----------------|
| Header/title | 3 | 1 |
| Connection status | 2 | — |
| Hooks banner | 2 | — |
| Sections/tabs | 6 | 3 |
| Empty states | 3 | 1 |
| State labels | 6 | 5 |
| Card actions | 3 | 3 |
| Timestamps | 4 | 4 |
| Notifications | 6 | — |
| Settings | 8 | 16 |
| Install modal | 4 | — |
| Pairing panel | 10 | 7 |
| SSE bar / event log | 2 | 5 |
| Session detail | — | 8 |
| Server picker/connect | — | 10 |
| Drawer | — | 3 |
| Disconnected banner | 1 | 1 |
| **Total** | **~60** | **~67** |

---

## Non-Goals

- No RTL support (English + Chinese are both LTR)
- No server-side content negotiation — frontends handle language independently
- No language auto-detection on web (manual switch only, per user request)
- No auto-translation pipeline — translations written manually
