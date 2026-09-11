#!/usr/bin/env bash
#
# Build (and optionally start) the cc-monitor dev sandbox.
#
# The proxy is a *build-time* concern and is supplied from your environment by
# this script — it is never written into Dockerfile.dev or the compose file,
# because this repository is public.
#
# Usage:
#   scripts/build-dev-docker.sh                 # build (cached) + start
#   scripts/build-dev-docker.sh --build-only    # build, don't start
#   scripts/build-dev-docker.sh --no-cache      # full rebuild, ignore layer cache
#   scripts/build-dev-docker.sh --shell         # exec a shell in the sandbox
#   scripts/build-dev-docker.sh --logs          # follow the server log
#   scripts/build-dev-docker.sh --down          # stop and remove the sandbox
#   scripts/build-dev-docker.sh --seed-only     # (re)seed the claude config dir
#
# Proxy overrides (defaults below point at the usual LAN proxy):
#   BUILD_PROXY=http://192.168.3.25:7780
#   BUILD_ALL_PROXY=socks5://192.168.3.25:7779
#
# The repo's own docker daemon needs root here, so every docker invocation goes
# through sudo. HOME is preserved explicitly — sudo resets it, and compose
# interpolates ${HOME} in the volume paths.
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${REPO_ROOT}/docker-compose.dev.yaml"

# Build-time proxy. Override via the environment; the socks proxy is only
# exported if the caller asked for it, since most builds do not need it.
BUILD_PROXY="${BUILD_PROXY:-http://192.168.3.25:7780}"
BUILD_ALL_PROXY="${BUILD_ALL_PROXY:-}"
NO_PROXY_DEFAULT="localhost,127.0.0.1,::1,192.168.3.0/24,10.8.0.0/24"

DEV_ROOT="${HOME}/.cc-monitor-dev"

docker_dev() {
  sudo env HOME="${HOME}" docker "$@"
}

compose_dev() {
  sudo env \
    HOME="${HOME}" \
    HTTP_PROXY="${BUILD_PROXY}" \
    HTTPS_PROXY="${BUILD_PROXY}" \
    NO_PROXY="${NO_PROXY_DEFAULT}" \
    docker compose -f "${COMPOSE_FILE}" "$@"
}

# ---------------------------------------------------------------------------
# Seed the sandbox's Claude Code config from the host, once.
#
# The point is that you never log in again inside the container. We copy only
# the configuration that carries authentication and behaviour — settings.json
# (which holds the ANTHROPIC_* env block) and credentials — and deliberately
# leave behind host session history, project transcripts and sockets.
# ---------------------------------------------------------------------------
seed_claude_config() {
  local src="${HOME}/.claude"
  local dst="${DEV_ROOT}/claude"

  mkdir -p "${dst}"

  if [[ ! -f "${dst}/settings.json" ]]; then
    if [[ ! -f "${src}/settings.json" ]]; then
      echo "[dev-docker] WARNING: ${src}/settings.json not found — the sandbox"
      echo "[dev-docker]          will start unauthenticated; run 'claude' inside"
      echo "[dev-docker]          it to log in."
      return 0
    fi

    echo "[dev-docker] seeding claude config: ${src}/settings.json -> ${dst}/"
    cp "${src}/settings.json" "${dst}/settings.json"

    # Credentials, if the host keeps them on disk. The DeepSeek setups usually
    # authenticate purely via the ANTHROPIC_AUTH_TOKEN in settings.json, but
    # copying these costs nothing and saves a login when they exist.
    for f in .credentials.json credentials.json; do
      [[ -f "${src}/${f}" ]] && cp "${src}/${f}" "${dst}/${f}"
    done
  fi

  # Sanitise on every run, not just at seed time, so an already-contaminated
  # config heals itself.
  #
  # The host's settings.json carries the host's own cc-monitor hook wiring —
  # absolute paths under ${HOME} that do not exist inside the container, and a
  # --url pointing at the live 9876 server. Carried over verbatim they would
  # shadow the sandbox's own hooks: install-hooks.sh dedupes on the exact
  # command string, so the two sets differ and *both* get installed, with the
  # broken host ones winning. Strip them; the sandbox installs its own.
  #
  # Files under ${DEV_ROOT} are written by the container's root and are
  # therefore root-owned on the host, so this has to run elevated — running it
  # as the invoking user fails with EACCES, and under `set -e` that aborts the
  # whole build.
  local sanitizer
  sanitizer="$(mktemp)"
  cat > "${sanitizer}" <<'PY'
import json
import sys

path, sandbox_hooks_dir = sys.argv[1], sys.argv[2]
with open(path, encoding="utf-8") as f:
    data = json.load(f)


def is_host_hook(handler: dict) -> bool:
    """True for a hook command installed against the *host's* cc-monitor.

    The sandbox's own hooks also live under a .cc-monitor/hooks/ path, so
    matching on that alone would delete them on every rebuild — which is
    exactly the bug this predicate exists to avoid. The distinguishing
    feature is the directory the command actually names.
    """
    command = str(handler.get("command", ""))
    if ".cc-monitor/hooks/" not in command:
        return False
    return sandbox_hooks_dir not in command


removed = 0
for event, groups in list((data.get("hooks") or {}).items()):
    if not isinstance(groups, list):
        continue
    for group in groups:
        handlers = group.get("hooks") if isinstance(group, dict) else None
        if not isinstance(handlers, list):
            continue
        kept = [h for h in handlers if not (isinstance(h, dict) and is_host_hook(h))]
        removed += len(handlers) - len(kept)
        group["hooks"] = kept
    data["hooks"][event] = [g for g in groups if g.get("hooks")]

# The UID identifies an installation, not a server — the sandbox gets its own.
if isinstance(data.get("env"), dict):
    data["env"].pop("CC_MONITOR_UID", None)

with open(path, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
    f.write("\n")

print(f"[dev-docker] sanitised settings: removed {removed} host hook handler(s)")
PY

  # Inside the container the hooks live here; see the /root/.cc-monitor mount.
  local sandbox_hooks_dir="/root/.cc-monitor/hooks"
  if [[ -w "${dst}/settings.json" ]]; then
    python3 "${sanitizer}" "${dst}/settings.json" "${sandbox_hooks_dir}"
  else
    sudo env HOME="${HOME}" python3 "${sanitizer}" "${dst}/settings.json" "${sandbox_hooks_dir}"
  fi
  rm -f "${sanitizer}"

  echo "[dev-docker] seeded. install hooks inside the sandbox against https://localhost:9877"
}

# ---------------------------------------------------------------------------
# Action dispatch
# ---------------------------------------------------------------------------
ACTION="up"
BUILD_FLAGS=()
for arg in "$@"; do
  case "${arg}" in
    --build-only) ACTION="build" ;;
    --no-cache)   BUILD_FLAGS+=(--no-cache) ;;
    --shell)      ACTION="shell" ;;
    --logs)       ACTION="logs" ;;
    --down)       ACTION="down" ;;
    --seed-only)  ACTION="seed" ;;
    -h|--help)    sed -n '2,30p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "unknown option: ${arg}" >&2; exit 2 ;;
  esac
done

if [[ "${ACTION}" != "down" && "${ACTION}" != "logs" && "${ACTION}" != "shell" ]]; then
  mkdir -p "${DEV_ROOT}/data" "${DEV_ROOT}/claude" "${DEV_ROOT}/dsh"
  seed_claude_config
fi

if [[ "${ACTION}" == "seed" ]]; then
  echo "[dev-docker] seed-only: done"
  exit 0
fi

case "${ACTION}" in
  build)
    compose_dev build "${BUILD_FLAGS[@]}"
    ;;
  up)
    compose_dev build "${BUILD_FLAGS[@]}"
    compose_dev up -d --force-recreate
    echo
    echo "[dev-docker] sandbox up — https://localhost:9877 (or http, see --help)"
    compose_dev ps
    ;;
  down)
    compose_dev down
    ;;
  logs)
    compose_dev logs -f --tail=200
    ;;
  shell)
    exec docker_dev exec -it cc-monitor-dev bash
    ;;
esac
