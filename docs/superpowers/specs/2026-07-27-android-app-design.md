# Android App Frontend — Design Spec

## Overview

Add an Android app frontend to cc-monitor with full feature parity to the web
dashboard, accessible over LAN with proper authentication and TLS encryption.

## Current State

cc-monitor is a FastAPI server (default `127.0.0.1:9876`) that monitors Claude
Code sessions via hooks. It provides REST + SSE APIs and serves a static web
dashboard. The web dashboard on localhost is considered always authorized.

## Architecture

```
┌──────────────────────────────────────────────────┐
│  Android App (Flutter)                           │
│  ┌──────────┐  ┌───────────┐  ┌──────────────┐  │
│  │ QR Scan  │  │ REST+SSE  │  │ Secure Store │  │
│  │ (pairing)│  │ Client    │  │ (token+cert) │  │
│  └──────────┘  └───────────┘  └──────────────┘  │
└──────────────────────┬───────────────────────────┘
                       │ HTTPS (self-signed, pinned)
┌──────────────────────▼───────────────────────────┐
│  Server (FastAPI)                                │
│  ┌──────────┐ ┌───────────┐ ┌────────────────┐  │
│  │ existing │ │ Token     │ │ TLS cert gen   │  │
│  │ REST+SSE│ │ Auth      │ │ + QR endpoint   │  │
│  │ API      │ │ Middleware│ │ /api/auth/*     │  │
│  └──────────┘ └───────────┘ └────────────────┘  │
└──────────────────────────────────────────────────┘
```

### Server changes (Python/FastAPI)

- **TLS:** Self-signed certificate auto-generated on first `--host 0.0.0.0` run,
  stored in `~/.cc-monitor/`. Server listens on HTTPS with this cert.
  `--host 127.0.0.1` runs plain HTTP (no TLS) as before.
- **Auth middleware:** Checks `Authorization: Bearer <token>` on all `/api/*`
  routes. Localhost (`127.0.0.1`, `::1`) bypasses auth entirely.
- **mDNS advertiser:** When `--host` is not loopback, advertises
  `_cc-monitor._tcp` via multicast DNS (Python `zeroconf`). TXT records include
  host, port, version, TLS fingerprint, and pairing status. Disable with
  `--no-mdns`.
- **Token storage:** `~/.cc-monitor/tokens.json` — maps token → device_name,
  created_at, expires_at.
- **Pairing request storage:** `~/.cc-monitor/pairing_requests.json`.

### Android app (Flutter)

- Flutter + Dart, Material 3, targeting Android 10+ (API 29).
- `flutter_secure_storage` for token + pinned cert fingerprint.
- `dio` HTTP client with custom `SecurityContext` for cert pinning.
- `mobile_scanner` for QR code scanning.
- `Provider` + `ChangeNotifier` for state management.

#### Project layout

```
android_app/
├── lib/
│   ├── main.dart                    # entry, MaterialApp, routing
│   ├── app_theme.dart               # Material 3 theme, colors
│   ├── services/
│   │   ├── api_client.dart          # dio instance, cert pinning, auth header
│   │   ├── pairing_service.dart     # QR scan, pairing handshake
│   │   ├── sse_client.dart          # SSE stream → state
│   │   ├── discovery_service.dart   # mDNS browser for LAN discovery
│   │   └── secure_store.dart        # flutter_secure_storage wrapper
│   ├── models/
│   │   └── session.dart             # Session data class (from JSON)
│   ├── providers/
│   │   ├── session_provider.dart    # ChangeNotifier — sessions + SSE
│   │   └── pairing_provider.dart    # ChangeNotifier — pairing requests
│   └── screens/
│       ├── dashboard_screen.dart    # 3-section list (active/complete/archived)
│       ├── session_detail_screen.dart
│       ├── server_picker_screen.dart # mDNS results + scan QR + manual entry
│       ├── pairing_screen.dart      # QR scanner view
│       └── settings_screen.dart     # server URL, token status, reconnect
├── pubspec.yaml
└── android/
```

#### Screens

| Screen | Content |
|--------|---------|
| Dashboard | Three horizontal sections — Active, Complete, Archived. Each is a scrollable list of `SessionCard`. Swipe to reveal archive/complete actions. Pull-to-refresh. Live badges via SSE. |
| Session Detail | Full session info: ID, state, last activity. Action buttons: Archive, Unarchive, Mark Complete. |
| Server Picker | mDNS-discovered cc-monitor servers on LAN. Each row shows hostname, IP:port, version, pairing status. Also has "Scan QR Code" and "Manual Entry" buttons. |
| Pairing | Full-screen QR scanner (`mobile_scanner`). Below: manual entry fields (server IP, port, token) as fallback. |
| Settings | Current server URL, token expiry countdown, "Re-pair" button, "Forget server" (clears secure store), app version. |

## Authentication & TLS

### Pairing flow (QR code path)

```
Android App                    Server                      Desktop
     │                            │                           │
     │  GET /api/auth/pair/qr     │                           │
     │ ─────────────────────────→ │                           │
     │                            │ generates token (32B)     │
     │                            │ reads cert fingerprint    │
     │  {token, host, port,       │                           │
     │   cert_sha256, expires_at} │                           │
     │ ←───────────────────────── │                           │
     │                            │                           │
     │  Shows QR on terminal      │                           │
     │ ← user scans QR ────────── │                           │
     │                            │                           │
     │  Stores in secure storage  │                           │
     │  Pins cert for all future  │                           │
     │  HTTPS connections         │                           │
     │                            │                           │
     │  POST /api/auth/pair/qr/confirm                        │
     │  {token, device_name: "Pixel 8"}                       │
     │ ─────────────────────────→ │                           │
     │                            │ token must be confirmed    │
     │                            │ within 5 min of generation │
     │                            │ marks token "active"      │
     │  {"status": "paired"}      │                           │
     │ ←───────────────────────── │                           │
```

**QR token confirmation window:** The token returned by `GET /api/auth/pair/qr`
is in a "pending" state. It must be confirmed via `POST /api/auth/pair/qr/confirm`
within 5 minutes, or it is automatically discarded. This prevents an attacker on
the LAN from racing to confirm a QR token intended for another device. The
confirmation call also registers the device name.

### Pairing flow (approval path)

```
Android App                              Server
     │                                      │
     │  POST /api/auth/pair/request          │
     │  {device_name: "Pixel 8"}             │
     │ ───────────────────────────────────→ │
     │                                      │ stores pending request
     │  {request_id, status: "pending"}     │
     │ ←─────────────────────────────────── │
     │                                      │
     │  GET /api/auth/pair/request/{id}/status  (poll)
     │ ───────────────────────────────────→ │
     │                                      │ waits for approval from:
     │                                      │  - CLI prompt (stdin y/N)
     │                                      │  - Web dashboard (localhost)
     │                                      │  - Authorized Android app (SSE)
     │  {status: "approved", token: "..."}  │
     │ ←─────────────────────────────────── │
```

### Multi-channel approval

When a pairing request is submitted, it can be approved through any of:

1. **CLI prompt** — server prints "Pair from Pixel 8? [y/N]" on stdin, waits
   up to 120 seconds for input (times out to "denied"), then continues
2. **Web dashboard** (localhost) — polls `GET /api/auth/pair/requests`, shows
   Approve/Deny buttons. Localhost is always authorized.
3. **Authorized Android app** — the SSE stream includes `pairing_request`
   events. The app shows an approval card and can approve/deny via API.

### Localhost bypass

Requests from `127.0.0.1` and `::1` skip auth entirely. The existing web
dashboard on `localhost:9876` works unchanged.

## Token Lifecycle

| Parameter | Default | Configurable |
|-----------|---------|--------------|
| TTL | 7 days (604800s) | `--token-ttl <seconds>` |
| No expiry | — | `--token-ttl 0` |
| Revocation | — | `cc-monitor --revoke-all` or `DELETE /api/auth/token` |

### Rotation

The app proactively rotates its token before expiry:

```
Android App                                  Server
     │                                          │
     │  POST /api/auth/token/rotate               │
     │  Authorization: Bearer <old_token>          │
     │  {device_name: "Pixel 8"}                  │
     │ ─────────────────────────────────────────→ │
     │                                          │ validates old_token
     │                                          │ generates new_token
     │                                          │ copies device_name, TTL
     │                                          │ revokes old_token
     │  {"token": "new_x7k9m...",                │
     │   "expires_at": "2026-08-10T12:00:00Z"}   │
     │ ←─────────────────────────────────────────│
```

**Rotation window:** App auto-rotates when `expires_at - now < 24h`. If rotation
fails (server unreachable), retries hourly. Token expired before successful
rotation → fall back to re-pairing.

With `--token-ttl 0`, rotation endpoint returns 409 Conflict.

**Expiry in headers:** Every authenticated response includes
`X-Token-Expires: <ISO8601>`. On 401, `X-Token-Expired: true` tells the app the
token expired (vs. invalid/revoked).

### QR code payload

```json
{
  "host": "192.168.1.42",
  "port": 9876,
  "cert_sha256": "a1b2c3...",
  "token": "x7k9m2...",
  "expires_at": "2026-08-03T12:00:00Z"
}
```

## LAN Server Discovery (mDNS)

Server advertises `_cc-monitor._tcp` via mDNS when `--host` is not loopback.
Disable with `--no-mdns`.

TXT records:

| Key | Value |
|-----|-------|
| `host` | Server IP (e.g. `192.168.1.42`) |
| `port` | HTTPS port (e.g. `9876`) |
| `version` | cc-monitor version (e.g. `0.4.1`) |
| `cert_sha256` | `sha256:abc123...` (informational — not a trust anchor) |
| `pairing` | `open` if no pairing required, `required` otherwise |

App browses for `_cc-monitor._tcp` services and presents a picker on first
launch. Tapping a server starts the pairing flow. **mDNS is unauthenticated** —
the `cert_sha256` in TXT records is shown for informational display only. The
actual trust anchor comes from the QR code (`cert_sha256` field) or manual
entry. On first HTTPS connection, the app verifies the server's presented cert
against the pinned fingerprint — this catches any mDNS spoofing.

## API Reference

### New auth endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/api/auth/pair/requests` | localhost or Bearer | List pending pairing requests |
| `POST` | `/api/auth/pair/request` | none | Submit a pairing request |
| `GET` | `/api/auth/pair/request/{id}/status` | none | Poll request status |
| `POST` | `/api/auth/pair/request/{id}/approve` | localhost or Bearer | Approve a pairing request |
| `POST` | `/api/auth/pair/request/{id}/deny` | localhost or Bearer | Deny a pairing request |
| `GET` | `/api/auth/pair/qr` | none | Get QR code pairing payload |
| `POST` | `/api/auth/pair/qr/confirm` | none | Confirm QR-scanned token |
| `POST` | `/api/auth/token/rotate` | Bearer | Rotate to a new token |
| `DELETE` | `/api/auth/token` | Bearer | Revoke own token |

### Existing endpoints (unchanged)

All existing `/api/*` endpoints remain unchanged — the auth middleware is
transparent when a valid Bearer token is present or when accessed from
localhost.

### SSE extensions

The SSE stream (`/api/stream`) gains a new event type for authorized clients:

```
event: pairing_request
data: {"id": "req_abc", "device_name": "Pixel 8", "requested_at": "..."}
```

## Server CLI

```
cc-monitor --port 9876                         # localhost, plain HTTP (current)
cc-monitor --host 0.0.0.0 --port 9876          # LAN, HTTPS + mDNS, token TTL 7d
cc-monitor --host 0.0.0.0 --token-ttl 86400    # 24h TTL
cc-monitor --host 0.0.0.0 --token-ttl 0        # tokens never expire
cc-monitor --host 0.0.0.0 --no-mdns            # disable mDNS advertising
cc-monitor --revoke-all                         # revoke all tokens, exit
cc-monitor --tls-cert /path/to/cert.pem         # use custom TLS cert
cc-monitor --tls-key /path/to/key.pem           # use custom TLS key
```

## State Management (App)

Simple `ChangeNotifier` + `Provider`:

```dart
class SessionProvider extends ChangeNotifier {
  List<Session> active = [], complete = [], archived = [];

  void onSseUpdate(Map<String, dynamic> payload) {
    // update matching session in-place → notifyListeners()
  }
}

class PairingProvider extends ChangeNotifier {
  List<PairingRequest> pendingRequests = [];

  void onSsePairingRequest(PairingRequest req) {
    pendingRequests.add(req);
    notifyListeners();
  }
}
```

SSE client reconnects automatically with exponential backoff (1s → 30s cap).

## Component Parity

The Android app matches the existing web dashboard:

- Section grouping (active / complete / archived)
- State badges (working, idle, pending_review, pending_approval, all_done)
- Session actions (archive, unarchive, complete)
- Real-time updates via SSE
- Archive/unarchive toggling
- Dashboard header with stats

## Dependencies

### Python (server)

- `zeroconf` — mDNS advertisement
- `cryptography` — TLS cert generation
- `secrets` (stdlib) — token generation

### Flutter (app)

- `dio` — HTTP client with cert pinning support
- `flutter_secure_storage` — token + fingerprint storage
- `mobile_scanner` — QR code scanning
- `provider` — state management
- `multicast_dns` — mDNS service discovery

## Security Considerations

- Self-signed cert is pinned via SHA-256 fingerprint from QR code — MITM
  prevented after initial pairing
- Tokens are 32-byte cryptographically random (`secrets.token_urlsafe`)
- Token storage on Android uses `EncryptedSharedPreferences` via
  `flutter_secure_storage`
- No plain HTTP connections allowed from the app — `dio` is configured to reject
  non-HTTPS
- Localhost bypass is IP-enforced — only loopback addresses skip auth
- Expired tokens are pruned from disk automatically
- `--revoke-all` provides an emergency kill-switch

## Out of Scope

- iOS support (Flutter makes this possible later, but not in this phase)
- Internet/remote access (VPN/Tailscale can be configured independently)
- Push notifications (SSE works fine while the app is in foreground)
- Multi-user auth (single set of tokens, single server operator)
- Encrypted token storage on server (tokens are on the server's disk; physical
  access to the server host is game over)
