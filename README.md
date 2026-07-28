# cc-monitor

**[→ Open Dashboard](https://bolunhan.github.io/cc-monitor/)**
[![Deploy to GitHub Pages](https://github.com/bolunhan/cc-monitor/actions/workflows/deploy-gh-pages.yml/badge.svg)](https://github.com/bolunhan/cc-monitor/actions/workflows/deploy-gh-pages.yml)

Monitor Claude Code working status via hooks — see which sessions are idle, working, pending approval, or done, in a local browser dashboard.

## Install

```bash
cd cc-monitor
pip install -e ".[dev]"
```

## Usage

**1. Start the server:**

```bash
cc-monitor --port 9876
```

**2. Open the dashboard:**

[http://localhost:9876](http://localhost:9876)

**3. Configure hooks in your `~/.claude/settings.json`:**

Copy the hook entries from `.claude/settings.json` in this repo, adjusting paths to point at the installed hook scripts.

## States

| State | Meaning |
|-------|---------|
| `working` | Claude is actively processing — executing tools, generating output |
| `pending_review` | Claude finished responding — output ready for review |
| `idle` | No activity for 24hr — session is dormant |
| `pending_approval` | Claude needs permission to proceed (PermissionRequest or permission prompt) |
| `all_done` | Session has ended |

## API

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/event` | Submit a raw hook event |
| `GET` | `/api/status` | All sessions' current states |
| `GET` | `/api/status/<id>` | Single session state |
| `GET` | `/api/stream` | SSE stream of state updates |
| `POST` | `/api/session/<id>/archive` | Archive a session |
| `POST` | `/api/session/<id>/unarchive` | Unarchive a session |
| `POST` | `/api/session/<id>/complete` | Mark session as all_done |

## Architecture

Hook scripts (stdlib-only Python) write `~/.cc-monitor/<session_id>.json` files and POST to the server. The FastAPI server holds in-memory state, broadcasts changes via SSE, and restores state from disk on startup.

## Docker

Pre-built image or build from source:

```bash
# Build
docker build --build-arg HTTP_PROXY=$HTTP_PROXY -t cc-monitor .

# Run (host network + persistent volume required)
docker run -d --name cc-monitor --network=host \
    -v ~/.cc-monitor:/root/.cc-monitor \
    --restart unless-stopped cc-monitor
```

Or use docker-compose:

```bash
docker compose up -d
```

**Important:** The `~/.cc-monitor` volume mount is **required**. It stores:
- Session state files (persisted across restarts)
- `.hooks-installed` marker file (for hooks status detection)

## Hook Installation

Install hook scripts so Claude Code reports its state to cc-monitor:

```bash
curl -skSL https://<server>:9876/static/install-hooks.sh | SERVER_URL=https://<server>:9876 bash
```

This downloads hook scripts to `~/.cc-monitor/hooks/` and injects them into `~/.claude/settings.json`.
The installer creates a `.hooks-installed` marker file so the server (even in Docker) knows hooks are active.

To uninstall:

```bash
curl -skSL https://<server>:9876/static/uninstall-hooks.sh | bash
```

## Remote Dashboard

The dashboard is fully static — host it anywhere and point it at your cc-monitor server.

**GitHub Pages** — auto-deployed on every push to `main` via `.github/workflows/deploy-gh-pages.yml`:

1. Push to `main` → deploys `static/` to the `gh-pages` branch
2. In your repo: **Settings → Pages → Source** → "Deploy from a branch", select `gh-pages`, `/ (root)`, Save
3. Open `https://<user>.github.io/cc-monitor/`
4. Click ⚙ → set **Server URL** to `http://127.0.0.1` + **Port** `9876` → Save & Reconnect
