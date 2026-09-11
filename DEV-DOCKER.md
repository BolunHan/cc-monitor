# cc-monitor dev sandbox

A throwaway container with **Claude Code CLI + dsh + cc-monitor**, for testing
against a real agent without disturbing the live instance.

The live cc-monitor usually *is in use* — it holds the real session state on
port 9876 and the host's hooks point at it. Nothing in this sandbox touches
any of that.

```
./scripts/build-dev-docker.sh          # build (cached) + start on :9877
./scripts/build-dev-docker.sh --shell  # shell into the sandbox
./scripts/build-dev-docker.sh --logs   # follow the server log
./scripts/build-dev-docker.sh --down   # stop and remove
```

| Action | Flag |
| --- | --- |
| Build only, don't start | `--build-only` |
| Full rebuild, ignore layer cache | `--no-cache` |
| Re-seed the Claude config from the host | `--seed-only` |

## Isolation

The sandbox is namespaced away from production on every axis:

| | Production | Sandbox |
| --- | --- | --- |
| Compose project | `cc-monitor` | `cc-monitor-dev` |
| Container | `cc-monitor` | `cc-monitor-dev` |
| Port | 9876 (TLS) | 9877 (TLS) |
| State dir | `~/.cc-monitor/docker/data` | `~/.cc-monitor-dev/data` |
| Claude config | `~/.claude` | `~/.cc-monitor-dev/claude` |
| Hooks | `~/.cc-monitor/hooks` | `~/.cc-monitor-dev/data/hooks` |

Both use host networking (house convention), so `:9877` is reachable from the
LAN for phone testing with no port mapping.

> ⚠️ Do not point any `docker-compose.dev.yaml` mount at `~/.cc-monitor`.

## Caching

The whole point is that you never wait for Node, npm, Claude Code or dsh to
download again. Three mechanisms stack:

**1. Layer ordering.** `Dockerfile.dev` puts everything slow and rarely
changing above everything fast and frequently changing:

```
python:3.13-slim
  → apt (git, jq, tmux, ripgrep, tini, …)      ← rarely changes
  → Node tarball into /opt/node                ← pinned by NODE_VERSION
  → npm i -g claude-code + dsh                 ← the expensive layer
  ─────────────────────────────────────────────────────────────
  → pip install -e ".[dev]"                    ← changes with pyproject
  → COPY source                                ← changes constantly
```

Editing a `.py` file invalidates only the last layer. Measured: a full rebuild
after a source change takes **under a second** of build time.

**2. BuildKit cache mounts.** These survive even a cache-*busting* rebuild:

| Mount | Holds |
| --- | --- |
| `/var/cache/apt`, `/var/lib/apt` | apt package lists and debs |
| `/tmp/download` | the Node `.tar.xz` |
| `/root/.npm` | the npm tarball cache |
| `/root/.cache/pip` | wheels |

Even `--no-cache` will not re-download the Node tarball or re-fetch npm
packages that are already in those mounts.

**3. Live source mount.** The repo is bind-mounted at `/app` over an
*editable* install, so source edits take effect on container restart — no
rebuild at all:

```bash
./scripts/build-dev-docker.sh      # once
# ...edit code...
docker compose -f docker-compose.dev.yaml restart
```

**Forcing a refresh.** Bump the version args in `docker-compose.dev.yaml`
(`CLAUDE_CODE_VERSION`, `DSH_VERSION`, `NODE_VERSION`) or pass `--no-cache`.

**Persistent state.** `~/.cc-monitor-dev/{data,claude,claude.json,dsh}` are
bind-mounted, so a `compose up --force-recreate` keeps session history, your
login, installed hooks, and dsh plugins. In particular the hook scripts under
`/root/.cc-monitor/hooks` survive — you do **not** re-run `install-hooks.sh`
after every rebuild.

## Authentication

`build-dev-docker.sh` seeds `~/.cc-monitor-dev/claude/settings.json` from the
host's `~/.claude/settings.json` on first run, which is what carries the
`ANTHROPIC_*` env block. **You never log in inside the container.**

The seeder also **sanitizes** the settings on every run, because the host's
file carries the host's own cc-monitor hook wiring — absolute paths under
`/home/<user>` that do not exist in the container, and `--url` pointing at the
live 9876 server. Left in place those shadow the sandbox's hooks (the
installer dedupes on the exact command string, so both sets get installed and
the broken ones win). It strips hook commands that name a hooks directory
*other than the sandbox's own*, and drops `CC_MONITOR_UID` so the sandbox
registers as its own installation.

This is idempotent — re-running reports `removed 0 host hook handler(s)`.

## Installing the hooks

Inside the container, after the server is up:

```bash
docker compose -f docker-compose.dev.yaml exec dev \
  bash -c 'cd /app && SERVER_URL=https://localhost:9877 \
           CC_MONITOR_UID=dev-docker bash scripts/install-hooks.sh'
```

Wait for `https://127.0.0.1:9877/api/version` to answer first — the installer
downloads the hook scripts *from the server*, so it fails with `0/8 downloaded`
if it races startup.

## Driving an agent

The server runs as the container's main process; run agents via `exec`:

```bash
docker exec -it cc-monitor-dev tmux new -A -s spike   # persistent TTY
# inside:  claude
```

`tmux` is installed for exactly this — Claude Code's TUI needs a TTY, and
`docker exec -it` sessions die with your terminal.

> **Do not rely on `ENV PATH` alone.** The CLIs live in `/opt/node/bin` and are
> also symlinked into `/usr/local/bin`, because an interactive/login shell
> (`tmux`, `su -`, ssh) re-sources `/etc/profile` and clobbers `ENV PATH` —
> otherwise `claude` is "command not found" in precisely the shell you want.

## Testing the control channel end-to-end

The web UI's behaviour is exercised over the same API it uses. With the server
up and an SSE subscriber attached (the subscriber is what enables the holds —
with no UI connected, hooks deliberately do not park):

```bash
# 1. Attach a "UI" — this is what tells hooks a human is watching
curl -skN https://127.0.0.1:9877/api/stream &

# 2. In the agent's tmux pane, ask for something that needs approval,
#    e.g. "Create a file at /tmp/x.txt containing: hello"

# 3. The request shows up on the session, and the hook parks:
curl -sk https://127.0.0.1:9877/api/status | jq '.sessions[] | select(.pending_request)'

# 4. Answer it
curl -sk -X POST https://127.0.0.1:9877/api/session/<sid>/respond \
  -H 'Content-Type: application/json' \
  -d '{"request_id":"<rid>","behavior":"allow"}'
#    → the terminal prompt is bypassed; the pane shows
#      "Allowed by PermissionRequest hook"

# 5. Directives and stop
curl -sk -X POST https://127.0.0.1:9877/api/session/<sid>/directive \
  -H 'Content-Type: application/json' -d '{"text":"reply with DONE"}'
curl -sk -X POST https://127.0.0.1:9877/api/session/<sid>/stop -d '{}'
```

## Known limitations

**The session messaging socket does not work.** Claude Code documents
`CLAUDE_CODE_MESSAGING_SOCKET` as a way to post into a live session, and hooks
do report it — but measured against a real interactive session on 2.1.268,
**every** write is accepted at the transport level and then silently
discarded. That includes writes from a genuine child hook holding the correct
path and token. Nothing distinguishes "delivered" from "dropped", and setting
`crossSessionInbound: "accept"` made no difference.

Consequently cc-monitor records the socket (diagnostically) but never delivers
through it — a directive always rides the `Stop` hook. **This means a directive
to a long-running turn waits until that turn ends.** The API reports `queued`,
not `delivered`, for exactly this reason.

**Host hooks that aren't cc-monitor's are left alone.** The seeder only strips
cc-monitor hook commands. If your global config has other `InstructionsLoaded`
hooks referencing host paths, they will fail noisily inside the sandbox. Remove
them from `~/.cc-monitor-dev/claude/settings.json` if the noise bothers you.

**Stop is cooperative.** Claude Code exposes no external interrupt, so the stop
button denies tool calls and ends the turn — it cannot abort a tool already
executing.

## Troubleshooting

| Symptom | Cause / fix |
| --- | --- |
| `claude: command not found` in tmux | Should not happen — symlinks cover it. If it does, check `/usr/local/bin/claude` exists. |
| `0/8 downloaded` in the installer | The server was not up yet. Wait for `/api/version`, retry. |
| Hooks never fire | Check `~/.cc-monitor-dev/claude/settings.json` — each event's hook list must be non-empty. Re-run the installer, then rebuild (sanitize is idempotent). |
| First-run wizard reappears | `~/.cc-monitor-dev/claude.json` was empty/corrupt. Delete it and rebuild; the seeder recreates it. |
| Rebuild re-downloads everything | Something above the expensive layer changed. Check `docker build` layer order, and confirm cache mounts are in use (`DOCKER_BUILDKIT=1`). |

## Files

| Path | Role |
| --- | --- |
| `Dockerfile.dev` | The image. No proxy settings — deliberate, this repo is public. |
| `docker-compose.dev.yaml` | Ports, mounts, isolation. |
| `scripts/build-dev-docker.sh` | Build wrapper: injects the build-time proxy, seeds and sanitizes the Claude config. |
| `scripts/dev-docker-entrypoint.sh` | Container entrypoint (`server` / `shell` / anything). |

### On the proxy

The build-time proxy is supplied **from your shell environment** by
`scripts/build-dev-docker.sh` and is never written into any committed file —
this repository is public.

BuildKit's predefined proxy args (`HTTP_PROXY`, `HTTPS_PROXY`, `NO_PROXY`,
`ALL_PROXY`) are forwarded automatically by `docker build` from the client
environment and are not persisted into the image or its layers. Override the
default with:

```bash
BUILD_PROXY=http://host:port ./scripts/build-dev-docker.sh
```

At **run** time the container goes direct by default. If the sandbox needs an
egress proxy, set `DEV_HTTP_PROXY` (deliberately *not* `HTTP_PROXY`, so the
build-time proxy cannot leak into the runtime environment).
