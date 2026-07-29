#!/usr/bin/env bash
# ============================================================================
# cc-monitor Hook Installer
#
# Downloads hook scripts from a cc-monitor server and injects them into
# ~/.claude/settings.json.  Generates a unique CC_MONITOR_UID so hooks
# identify themselves to the server, and posts telemetry on completion.
#
# Usage:
#   curl -skSL https://<server>:9876/static/install-hooks.sh | SERVER_URL=https://<server>:9876 bash
# ============================================================================
set -euo pipefail

SERVER_URL="${SERVER_URL:-https://127.0.0.1:9876}"
HOOKS_DIR="${HOME}/.cc-monitor/hooks"
SETTINGS_FILE="${HOME}/.claude/settings.json"
BACKUP_FILE="${HOME}/.claude/settings.json.cc-monitor.bak"

# Generate a unique installation ID
CC_MONITOR_UID=$(python3 -c "import uuid; print(uuid.uuid4().hex[:12])" 2>/dev/null || echo "cc$(date +%s)$(shuf -i 100-999 -n 1)")

HOOKS=(
    "pre_tool_use.py" "post_tool_use.py" "user_prompt_submit.py"
    "stop.py" "notification.py" "permission_request.py"
    "session_end.py" "_common.py"
)

echo "=== cc-monitor Hook Installer ==="
echo "  Server: ${SERVER_URL}"
echo "  UID:    ${CC_MONITOR_UID}"
echo ""

# ------------------------------------------------------------------
# 1. Python check
# ------------------------------------------------------------------
PYTHON=""
for c in python3 python; do
    command -v "$c" &>/dev/null && { PYTHON="$c"; break; }
done
if [ -z "$PYTHON" ]; then
    echo "ERROR: python3 not found."
    exit 1
fi
echo "[1/4] Python: $($PYTHON --version 2>&1)"

# ------------------------------------------------------------------
# 2. Download hook scripts
# ------------------------------------------------------------------
echo "[2/4] Downloading hook scripts..."
mkdir -p "$HOOKS_DIR"
DOWNLOADS=0; FAILS=0

for hook in "${HOOKS[@]}"; do
    ok=false
    for proto in https http; do
        if curl -fsk -o "${HOOKS_DIR}/${hook}" \
            "${proto}://$(echo "${SERVER_URL}" | sed 's|https\?://||')/hooks/${hook}" 2>/dev/null; then
            echo "  ✓ ${hook}"
            chmod +x "${HOOKS_DIR}/${hook}" 2>/dev/null || true
            DOWNLOADS=$((DOWNLOADS + 1)); ok=true; break
        fi
    done
    $ok || { echo "  ✗ ${hook}"; FAILS=$((FAILS + 1)); }
done
echo "  ${DOWNLOADS}/${#HOOKS[@]} downloaded"

# ------------------------------------------------------------------
# 3. Backup settings
# ------------------------------------------------------------------
echo "[3/4] Backing up settings..."
[ -f "$SETTINGS_FILE" ] && cp "$SETTINGS_FILE" "$BACKUP_FILE" && echo "  Backup: ${BACKUP_FILE}" || echo "  No existing settings"

# ------------------------------------------------------------------
# 4. Inject hooks + post telemetry (single Python block)
# ------------------------------------------------------------------
echo "[4/4] Injecting hooks and reporting to server..."
SETTINGS="$SETTINGS_FILE" HOOKS="$HOOKS_DIR" SERVER="$SERVER_URL" \
  CCUID="$CC_MONITOR_UID" DLS="$DOWNLOADS" FLS="$FAILS" "$PYTHON" << 'PYEOF'
import json, os, ssl, sys, urllib.request
from pathlib import Path

settings_file = Path(os.environ['SETTINGS'])
hooks_dir = Path(os.environ['HOOKS'])
server_url = os.environ.get('SERVER', '').rstrip('/')
cc_uid = os.environ.get('CCUID', '')
downloads = int(os.environ.get('DLS', 0))
fails = int(os.environ.get('FLS', 0))

HOOK_EVENTS = {
    'PreToolUse':        {'matcher': '*', 'script': 'pre_tool_use.py'},
    'PostToolUse':       {'matcher': '*', 'script': 'post_tool_use.py'},
    'UserPromptSubmit':  {'matcher': '',  'script': 'user_prompt_submit.py'},
    'Stop':              {'matcher': '',  'script': 'stop.py'},
    'Notification':      {'matcher': '*', 'script': 'notification.py'},
    'PermissionRequest': {'matcher': '*', 'script': 'permission_request.py'},
    'SessionEnd':        {'matcher': '',  'script': 'session_end.py'},
}

# Build hook config
hooks_config = {}
for event_name, cfg in HOOK_EVENTS.items():
    cmd = f"{hooks_dir / cfg['script']} --url {server_url} --uid {cc_uid}"
    entry = {'hooks': [{'type': 'command', 'command': cmd, 'description': f'cc-monitor: {event_name}'}]}
    if cfg['matcher']:
        entry['matcher'] = cfg['matcher']
    hooks_config[event_name] = [entry]

# Load target
target = json.loads(settings_file.read_text()) if settings_file.exists() else {}
target_hooks = target.get('hooks', {})

merged, skipped = 0, 0
for event_name, new_groups in hooks_config.items():
    existing = target_hooks.get(event_name, [])
    already = any(cc_uid in eh.get('command', '') for eg in existing for eh in eg.get('hooks', []))
    if already:
        skipped += 1
        continue
    target_hooks[event_name] = existing + new_groups
    merged += 1

# Set CC_MONITOR_UID in Claude's env so hooks inherit it automatically
target['hooks'] = target_hooks
env = target.get('env', {})
env['CC_MONITOR_UID'] = cc_uid
target['env'] = env
settings_file.parent.mkdir(parents=True, exist_ok=True)
settings_file.write_text(json.dumps(target, indent=2))
print(f'  Injected {merged}, skipped {skipped}')

# Post telemetry
ctx = ssl._create_unverified_context()
api = f"{server_url}/api/hooks-telemetry"
body = json.dumps({
    'cc_monitor_uid': cc_uid,
    'status': 'installed',
    'server_url': server_url,
    'events_merged': merged,
    'events_skipped': skipped,
    'downloads': downloads,
    'download_fails': fails,
}).encode()

for url in (api, api.replace('https://', 'http://', 1)):
    try:
        req = urllib.request.Request(url, data=body, headers={'Content-Type': 'application/json'}, method='POST')
        urllib.request.urlopen(req, timeout=5, context=ctx) if url.startswith('https') else urllib.request.urlopen(req, timeout=5)
        print('  ✓ Server notified')
        break
    except Exception as e:
        continue
else:
    print(f'  ⚠ Could not reach server (hooks are still installed)')
PYEOF

echo ""
echo "=== Done ==="
echo "cc-monitor hooks installed (UID: ${CC_MONITOR_UID}). Restart Claude Code to use them."
echo "Uninstall: curl -sSL ${SERVER_URL}/static/uninstall-hooks.sh | SERVER_URL=${SERVER_URL} CC_MONITOR_UID=${CC_MONITOR_UID} bash"
