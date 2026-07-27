# cc-monitor Design Spec

## Overview

cc-monitor tracks Claude Code session state in real-time via hooks, exposes it through a local REST API + SSE, and provides a minimal browser dashboard.

**States:** `idle` | `working` | `pending_approval` | `all_done`

## Architecture

```
Claude Code hook fires
       │
       ▼
hook script (hooks/<event>.py)       ← self-contained, stdlib only
       │
       ├──→ writes ~/.cc-monitor/<session_id>.json
       │
       └──→ POST localhost:9876/api/event (best-effort, tolerates down)
                 │
                 ▼
       cc_monitor server (FastAPI + uvicorn)
                 │
        ┌────────┼────────┐
        ▼        ▼        ▼
    in-memory  file     SSE broadcast
     state     read      to all clients
                 │
                 ▼
       static/index.html + app.js + app.css
```

On server startup, all `~/.cc-monitor/*.json` files are read to restore prior state into memory.

## Package Layout

```
cc-monitor/
├── src/
│   └── cc_monitor/
│       ├── __init__.py         # version
│       ├── server.py           # FastAPI app, routes, SSE, main()
│       ├── state.py            # StateManager: memory + file + SSE fan-out
│       └── mapping.py          # raw event → MonitorState enum
├── hooks/                      # one self-contained script per hook event
│   ├── pre_tool_use.py
│   ├── post_tool_use.py
│   ├── user_prompt_submit.py
│   ├── stop.py
│   ├── notification.py
│   ├── permission_request.py
│   └── session_end.py
├── static/
│   ├── index.html
│   ├── css/
│   │   └── app.css
│   └── js/
│       └── app.js
├── tests/
│   ├── __init__.py
│   ├── test_mapping.py
│   └── test_state.py
├── pyproject.toml
├── .claude/
│   └── settings.json           # project hooks config (committable, for dogfooding)
└── README.md
```

## State File Schema

`~/.cc-monitor/<session_id>.json`:

```json
{
  "session_id": "9db738b8-...",
  "cwd": "/home/user/Projects/foo",
  "state": "working",
  "raw_event": "PreToolUse",
  "raw_detail": "Bash",
  "updated_at": "2026-07-27T12:00:00.000000Z"
}
```

Rotated on every event — a session file always holds the latest state for that session.

## State Mapping (`mapping.py`)

```python
class MonitorState(enum.StrEnum):
    IDLE = "idle"
    WORKING = "working"
    PENDING_APPROVAL = "pending_approval"
    ALL_DONE = "all_done"

def map_event(hook_event_name: str, notification_type: str | None = None) -> MonitorState:
    # UserPromptSubmit | PreToolUse | PostToolUse → WORKING
    # Stop → IDLE
    # Notification:
    #   idle_prompt → IDLE
    #   permission_prompt → PENDING_APPROVAL
    # PermissionRequest → PENDING_APPROVAL
    # SessionEnd → ALL_DONE
```

`state.py` holds a `_pending_approval: set[session_id]` to prevent `Stop` from flipping `PENDING_APPROVAL` back to `IDLE` mid-turn. When `map_event` returns `PENDING_APPROVAL`, the session is added to the set. When any subsequent non-`Stop` event fires (e.g. `PreToolUse`, `UserPromptSubmit`), it's cleared — the user resolved the approval. `Stop` is ignored while the session is in the set.

## Server API (`server.py`)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/event` | Hook submits raw event JSON; server maps, stores, broadcasts SSE |
| `GET` | `/api/status` | All sessions: `{sessions: [...], count: N}` |
| `GET` | `/api/status/{session_id}` | Single session or 404 |
| `GET` | `/api/stream` | SSE: `event: state_update`, `data: {session_id, state, ...}` |
| `GET` | `/` | Serve `index.html` |

Static files (`css/`, `js/`) mounted at `/static`.

## Hook Scripts

Each script in `hooks/` is self-contained — stdlib only, no imports from `cc_monitor` — so it works regardless of Python venv state. Each script:

1. Reads event JSON from stdin
2. Maps `hook_event_name` + `notification_type` → state string
3. Writes `~/.cc-monitor/<session_id>.json` (rotates latest)
4. HTTP POST to `http://localhost:9876/api/event` (ConnectionError → silent pass)

The mapping logic is intentionally duplicated in each hook vs. in `mapping.py` — hook scripts are standalone, server owns the canonical mapping.

## Settings.json (hooks config)

Distributed via `.claude/settings.json` in this repo (for dogfooding). Users reference the installed hook scripts by absolute path:

```json
{
  "hooks": {
    "PreToolUse": [{
      "matcher": "*",
      "hooks": [{
        "type": "command",
        "command": "/path/to/cc-monitor/hooks/pre_tool_use.py"
      }]
    }]
    // ... one block per event
  }
}
```

## Frontend (`static/`)

**index.html** — semantic structure: header with title + connection indicator, grid of `.session-card` elements populated by JS.

**app.css** — CSS custom properties for colors; card layout; `.state-badge` with variants:
- `idle`: slate
- `working`: blue with pulse animation
- `pending_approval`: amber with pulse animation
- `all_done`: green

**app.js** — opens `EventSource(/api/stream)`, maintains `Map<session_id, Card>`, creates/updates/removes cards on events. Shows session ID (truncated), cwd, state badge, last event, relative timestamp.

## CLI

```
cc-monitor server --port 9876 --host 127.0.0.1
```

Entry point registered via `pyproject.toml` `[project.scripts]`.

## Testing

- `test_mapping.py`: unit tests for every event → state mapping, edge cases
- `test_state.py`: unit tests for StateManager create/update/restore/SSE broadcast

## Dependencies

**Runtime:** `fastapi`, `uvicorn` (server); stdlib only for hook scripts.

**Dev:** `pytest`, `httpx` (for TestClient).
