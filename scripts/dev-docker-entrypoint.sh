#!/usr/bin/env bash
#
# Entrypoint for the cc-monitor dev sandbox (see Dockerfile.dev).
#
#   server   (default)  start cc-monitor on $CC_MONITOR_PORT
#   shell               drop into bash
#   <anything else>     exec it verbatim
#
set -euo pipefail

PORT="${CC_MONITOR_PORT:-9877}"
DATA_DIR="${CC_MONITOR_DATA_DIR:-/data/.cc-monitor}"
CONFIG_DIR="${CLAUDE_CONFIG_DIR:-${HOME}/.claude}"

mkdir -p "${DATA_DIR}" "${CONFIG_DIR}"

case "${1:-server}" in
  server)
    shift || true
    echo "[dev-docker] cc-monitor on port ${PORT}, data dir ${DATA_DIR}"
    echo "[dev-docker] claude config  ${CONFIG_DIR}"
    echo "[dev-docker] run an agent:  docker compose -f docker-compose.dev.yaml exec dev bash"
    exec cc-monitor \
      --host 0.0.0.0 \
      --port "${PORT}" \
      --data-dir "${DATA_DIR}" \
      --no-mdns \
      "$@"
    ;;
  shell)
    exec bash
    ;;
  *)
    exec "$@"
    ;;
esac
