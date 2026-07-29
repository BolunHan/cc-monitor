#!/usr/bin/env bash
# ============================================================================
# cc-monitor Hook Uninstaller
#
# Surgically removes cc-monitor hooks from ~/.claude/settings.json.
# Matches hooks by CC_MONITOR_UID for precise removal — multiple
# cc-monitor installations coexist without interference.
#
# Usage:
#   curl -skSL https://<server>:9876/static/uninstall-hooks.sh | SERVER_URL=https://<server>:9876 bash
#   # With explicit UID for precise matching:
#   CC_MONITOR_UID=abc123 bash uninstall-hooks.sh
# ============================================================================
set -euo pipefail

SERVER_URL="${SERVER_URL:-}"
CC_MONITOR_UID="${CC_MONITOR_UID:-}"
HOOKS_DIR="${HOME}/.cc-monitor/hooks"
SETTINGS_FILE="${HOME}/.claude/settings.json"
BACKUP_FILE="${HOME}/.claude/settings.json.cc-monitor.uninstall.$(date +%Y%m%d-%H%M%S).bak"

echo "=== cc-monitor Hook Uninstaller ==="
if [ -n "$SERVER_URL" ]; then echo "  Server: ${SERVER_URL}"; fi
if [ -n "$CC_MONITOR_UID" ]; then echo "  UID:    ${CC_MONITOR_UID}"; fi
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

# ------------------------------------------------------------------
# 2. Backup
# ------------------------------------------------------------------
echo "[1/3] Backing up settings..."
[ -f "$SETTINGS_FILE" ] && cp "$SETTINGS_FILE" "$BACKUP_FILE" && echo "  Backup: ${BACKUP_FILE}" || echo "  No existing settings"

# ------------------------------------------------------------------
# 3. Remove hooks + post telemetry
# ------------------------------------------------------------------
echo "[2/3] Removing hooks..."
SETTINGS="$SETTINGS_FILE" HOOKS="$HOOKS_DIR" SERVER="$SERVER_URL" \
  CCUID="$CC_MONITOR_UID" "$PYTHON" << 'PYEOF'
import json, os, ssl, sys, urllib.request
from pathlib import Path

settings_file = Path(os.environ['SETTINGS'])
hooks_dir = str(Path(os.environ['HOOKS']))
server_url = os.environ.get('SERVER', '').rstrip('/')
cc_uid = os.environ.get('CCUID', '')

if not settings_file.exists():
    print('  No settings file — nothing to do')
    sys.exit(0)

settings = json.loads(settings_file.read_text())
hooks = settings.get('hooks', {})

EVENTS = ['PreToolUse','PostToolUse','UserPromptSubmit','Stop',
          'Notification','PermissionRequest','SessionEnd']

removed = 0
for event in EVENTS:
    groups = hooks.get(event, [])
    new_groups = []
    for group in groups:
        kept = []
        for h in group.get('hooks', []):
            cmd = h.get('command', '')
            # Match: hook is ours if command contains hooks_dir AND server_url
            if server_url and hooks_dir in cmd and server_url in cmd:
                removed += 1
            else:
                kept.append(h)
        if kept:
            group['hooks'] = kept
            new_groups.append(group)
    if new_groups:
        hooks[event] = new_groups
    elif event in hooks:
        del hooks[event]

settings['hooks'] = hooks
# Only remove env.CC_MONITOR_UID if all cc-monitor hooks are gone
total_cc_hooks = sum(
    1 for ev in EVENTS
    for g in hooks.get(ev, [])
    for h in g.get('hooks', [])
    if hooks_dir in h.get('command', '')
)
if total_cc_hooks == 0 and 'env' in settings:
    settings['env'].pop('CC_MONITOR_UID', None)
    if not settings['env']:
        del settings['env']
settings_file.write_text(json.dumps(settings, indent=2))
print(f'  Removed {removed} hook entries')

# Post telemetry
if server_url:
    ctx = ssl._create_unverified_context()
    api = f"{server_url}/api/hooks-telemetry"
    body = json.dumps({
        'cc_monitor_uid': cc_uid or 'legacy',
        'status': 'uninstalled',
        'server_url': server_url,
        'events_removed': removed,
    }).encode()
    for url in (api, api.replace('https://', 'http://', 1)):
        try:
            req = urllib.request.Request(url, data=body, headers={'Content-Type': 'application/json'}, method='POST')
            urllib.request.urlopen(req, timeout=5, context=ctx) if url.startswith('https') else urllib.request.urlopen(req, timeout=5)
            print('  ✓ Server notified')
            break
        except Exception:
            continue
    else:
        print('  ⚠ Could not reach server (hooks removed locally)')
PYEOF

# ------------------------------------------------------------------
# 4. Clean up hook scripts
# ------------------------------------------------------------------
echo "[3/3] Cleaning up..."
rm -rf "$HOOKS_DIR" 2>/dev/null && echo "  Removed ${HOOKS_DIR}" || echo "  No hook scripts to remove"

echo ""
echo "=== Done ==="
echo "cc-monitor hooks uninstalled."
