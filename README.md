# cc-monitor

Monitor Claude Code working status via hooks — see which sessions are idle, working, pending approval, or done, in a local browser dashboard.

## Install

```bash
cd cc-monitor
pip install -e ".[dev]"
```

## Usage

**1. Start the server:**

```bash
cc-monitor server --port 9876
```

**2. Open the dashboard:**

[http://localhost:9876](http://localhost:9876)

**3. Configure hooks in your `~/.claude/settings.json`:**

Copy the hook entries from `.claude/settings.json` in this repo, adjusting paths to point at the installed hook scripts.

## States

| State | Meaning |
|-------|---------|
| `working` | Claude is actively processing — executing tools, generating output |
| `idle` | Claude is waiting for your input |
| `pending_approval` | Claude needs permission to proceed (PermissionRequest or permission prompt) |
| `all_done` | Session has ended |

## API

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/event` | Submit a raw hook event |
| `GET` | `/api/status` | All sessions' current states |
| `GET` | `/api/status/<id>` | Single session state |
| `GET` | `/api/stream` | SSE stream of state updates |

## Architecture

Hook scripts (stdlib-only Python) write `~/.cc-monitor/<session_id>.json` files and POST to the server. The FastAPI server holds in-memory state, broadcasts changes via SSE, and restores state from disk on startup.
