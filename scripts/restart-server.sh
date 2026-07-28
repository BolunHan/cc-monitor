#!/usr/bin/env bash
#
# restart-server.sh — kill, reinstall, and restart cc-monitor server
#
# Usage:
#   ./scripts/restart-server.sh              # default port 9876, host 0.0.0.0
#   ./scripts/restart-server.sh 8443         # custom port
#   ./scripts/restart-server.sh 9876 127.0.0.1  # custom port + host

set -euo pipefail

PORT="${1:-9876}"
HOST="${2:-0.0.0.0}"
VENV="${HOME}/Projects/venv_313"
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "=== cc-monitor server restart ==="
echo "    port: $PORT  host: $HOST"
echo "    venv: $VENV"

# 1. Kill existing server
echo "--- killing existing server ---"
# Kill by port first (most reliable)
fuser -k ${PORT}/tcp 2>/dev/null || true
# Also try pattern matching
pkill -f "cc-monitor" 2>/dev/null || true
pkill -f "cc_monitor" 2>/dev/null || true
sleep 1
echo "    done"

# 2. Reinstall package
echo "--- reinstalling package ---"
cd "$PROJECT_ROOT"
# Clear stale bytecode
find src -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
find src -name "*.pyc" -delete 2>/dev/null || true
"$VENV/bin/pip" install -e ".[dev]" -q
echo "    done"

# 3. Start server
echo "--- starting server ---"
LOGFILE="${PROJECT_ROOT}/server.log"
nohup "$VENV/bin/cc-monitor" \
    --port "$PORT" \
    --host "$HOST" \
    > "$LOGFILE" 2>&1 &

sleep 2

# 4. Verify
if curl -sk "https://127.0.0.1:${PORT}/api/version" > /dev/null 2>&1; then
    VERSION=$(curl -sk "https://127.0.0.1:${PORT}/api/version")
    echo "=== server running: $VERSION ==="
    echo "    log: $LOGFILE"
else
    echo "=== server may be starting (check log) ==="
    tail -5 "$LOGFILE"
fi
