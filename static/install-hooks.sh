#!/usr/bin/env bash
# ============================================================================
# cc-monitor Hook Installer
#
# Downloads hook scripts from a cc-monitor server and injects them into the
# local ~/.claude/settings.json.  Works regardless of where the server runs
# (localhost, LAN, Docker container — as long as the server URL is reachable).
#
# Usage:
#   curl -sSL https://bolunhan.github.io/cc-monitor/install-hooks.sh | bash
#   # or with a custom server URL:
#   SERVER_URL=https://192.168.1.50:9876 bash install-hooks.sh
#
# The script:
#   1. Downloads hook scripts from the cc-monitor server
#   2. Places them in ~/.cc-monitor/hooks/
#   3. Merges hook configuration into ~/.claude/settings.json
#   4. Preserves existing non-cc-monitor settings and hooks
# ============================================================================
set -euo pipefail

SERVER_URL="${SERVER_URL:-https://127.0.0.1:9876}"
HOOKS_DIR="${HOME}/.cc-monitor/hooks"
SETTINGS_FILE="${HOME}/.claude/settings.json"
BACKUP_FILE="${HOME}/.claude/settings.json.cc-monitor.bak"

# List of hook scripts to download (mirrors hooks/ directory)
HOOKS=(
    "pre_tool_use.py"
    "post_tool_use.py"
    "user_prompt_submit.py"
    "stop.py"
    "notification.py"
    "permission_request.py"
    "session_end.py"
    "_common.py"
)

echo "=== cc-monitor Hook Installer ==="
echo "  Server: ${SERVER_URL}"
echo "  Hooks dir: ${HOOKS_DIR}"
echo "  Settings: ${SETTINGS_FILE}"
echo ""

# ------------------------------------------------------------------
# 1. Check Python availability (hooks are Python scripts)
# ------------------------------------------------------------------
PYTHON=""
for candidate in python3 python; do
    if command -v "$candidate" &>/dev/null; then
        PYTHON="$candidate"
        break
    fi
done
if [ -z "$PYTHON" ]; then
    echo "ERROR: python3 not found in PATH. Hook scripts require Python."
    exit 1
fi
echo "[1/4] Python: $($PYTHON --version 2>&1)"

# ------------------------------------------------------------------
# 2. Download hook scripts from server
# ------------------------------------------------------------------
echo "[2/4] Downloading hook scripts..."
mkdir -p "$HOOKS_DIR"

for hook in "${HOOKS[@]}"; do
    downloaded=false
    # Try HTTPS first, then HTTP (server may have TLS or not)
    for proto in https http; do
        if curl -fsk -o "${HOOKS_DIR}/${hook}" \
            "${proto}://$(echo "${SERVER_URL}" | sed 's|https\?://||')/hooks/${hook}" 2>/dev/null; then
            echo "  ✓ ${hook} (${proto})"
            chmod +x "${HOOKS_DIR}/${hook}" 2>/dev/null || true
            downloaded=true
            break
        fi
    done
    if ! $downloaded; then
        echo "  ✗ ${hook} — download failed. Is the server reachable at ${SERVER_URL}?"
        echo "    Continuing with remaining hooks..."
    fi
done
echo "  Hooks saved to ${HOOKS_DIR}"

# ------------------------------------------------------------------
# 3. Backup existing settings
# ------------------------------------------------------------------
echo "[3/4] Backing up settings..."
if [ -f "$SETTINGS_FILE" ]; then
    cp "$SETTINGS_FILE" "$BACKUP_FILE"
    echo "  Backup: ${BACKUP_FILE}"
else
    echo "  No existing settings to backup"
fi

# ------------------------------------------------------------------
# 4. Inject hook configuration
# ------------------------------------------------------------------
echo "[4/4] Injecting hook configuration..."
SETTINGS="$SETTINGS_FILE" HOOKS="$HOOKS_DIR" "$PYTHON" << 'PYEOF'
import json, os, sys
from pathlib import Path

settings_file = Path(os.environ['SETTINGS'])
hooks_dir = Path(os.environ['HOOKS'])

hook_events = {
    'PreToolUse':        {'matcher': '*', 'script': 'pre_tool_use.py'},
    'PostToolUse':       {'matcher': '*', 'script': 'post_tool_use.py'},
    'UserPromptSubmit':  {'matcher': '',   'script': 'user_prompt_submit.py'},
    'Stop':              {'matcher': '',   'script': 'stop.py'},
    'Notification':      {'matcher': '*',  'script': 'notification.py'},
    'PermissionRequest': {'matcher': '*',  'script': 'permission_request.py'},
    'SessionEnd':        {'matcher': '',   'script': 'session_end.py'},
}

hooks_config = {}
for event_name, cfg in hook_events.items():
    script_path = str(hooks_dir / cfg['script'])
    entry = {
        'hooks': [{
            'type': 'command',
            'command': script_path,
            'description': f'cc-monitor: {event_name}',
        }]
    }
    if cfg['matcher']:
        entry['matcher'] = cfg['matcher']
    hooks_config[event_name] = [entry]

target = {}
if settings_file.exists():
    target = json.loads(settings_file.read_text())

target_hooks = target.get('hooks', {})
merged = 0
for event_name, matcher_groups in hooks_config.items():
    target_hooks[event_name] = matcher_groups
    merged += 1

target['hooks'] = target_hooks

settings_file.parent.mkdir(parents=True, exist_ok=True)
settings_file.write_text(json.dumps(target, indent=2))
print(f'  Injected {merged} hook events into {settings_file}')
PYEOF

# Write marker file for Docker-based status detection
touch "${HOME}/.cc-monitor/.hooks-installed"

echo ""
echo "=== Done ==="
echo "cc-monitor hooks installed. Restart Claude Code to use them."
echo "To uninstall: curl -sSL ${SERVER_URL}/static/uninstall-hooks.sh | bash"
