#!/usr/bin/env bash
# ============================================================================
# cc-monitor Hook Uninstaller
#
# Removes cc-monitor hooks from ~/.claude/settings.json by parsing the JSON
# and deleting only hooks whose command contains BOTH the hooks directory
# AND the target server URL.  This means multiple cc-monitor servers can
# coexist — uninstalling one leaves the others intact.
#
# Usage:
#   curl -sSL https://192.168.3.28:9876/static/uninstall-hooks.sh | bash
#   # or with explicit server URL for precise matching:
#   curl -sSL ... | SERVER_URL=https://192.168.1.50:9876 bash
# ============================================================================
set -euo pipefail

SERVER_URL="${SERVER_URL:-}"
HOOKS_DIR="${HOME}/.cc-monitor/hooks"
SETTINGS_FILE="${HOME}/.claude/settings.json"
MARKER_FILE="${HOME}/.cc-monitor/.hooks-installed"
BACKUP_FILE="${HOME}/.claude/settings.json.cc-monitor.bak"

CC_HOOK_EVENTS=(
    "PreToolUse" "PostToolUse" "UserPromptSubmit" "Stop"
    "Notification" "PermissionRequest" "SessionEnd"
)

echo "=== cc-monitor Hook Uninstaller ==="
if [ -n "$SERVER_URL" ]; then
    echo "  Server: ${SERVER_URL}"
fi
echo "  Hooks dir: ${HOOKS_DIR}"

# 1. Remove hook scripts
echo "[1/3] Removing hook scripts..."
if [ -d "$HOOKS_DIR" ]; then
    rm -rf "$HOOKS_DIR"
    echo "  Removed $HOOKS_DIR"
else
    echo "  No hook scripts found"
fi

# 2. Remove cc-monitor hooks from settings.json
echo "[2/3] Removing hooks from $SETTINGS_FILE..."
CC_EVENTS="${CC_HOOK_EVENTS[*]}" CC_FILE="$SETTINGS_FILE" \
  HOOKS_DIR="$HOOKS_DIR" SERVER_URL="$SERVER_URL" python3 << 'PYEOF'
import json, os, sys
from pathlib import Path

events = os.environ['CC_EVENTS'].split()
f = Path(os.environ['CC_FILE'])
hooks_dir = os.environ.get('HOOKS_DIR', '')
server_url = os.environ.get('SERVER_URL', '').rstrip('/')

if not f.exists():
    print('  No settings file — nothing to do')
    sys.exit(0)

settings = json.loads(f.read_text())
hooks = settings.get('hooks', {})
removed = 0

for event in events:
    groups = hooks.get(event, [])
    new_groups = []
    for group in groups:
        kept_hooks = []
        for h in group.get('hooks', []):
            cmd = h.get('command', '')
            # A hook belongs to a specific cc-monitor server if its command
            # contains BOTH the hooks directory AND the server URL.
            # Without SERVER_URL, fall back to matching hooks_dir alone
            # (backward compat — removing legacy hooks installed without --url).
            if server_url:
                is_ours = (hooks_dir in cmd) and (server_url in cmd)
            else:
                # Legacy mode: match hooks_dir only (pre-URL installs)
                is_ours = (hooks_dir in cmd)
            if is_ours:
                removed += 1
            else:
                kept_hooks.append(h)
        if kept_hooks:
            group['hooks'] = kept_hooks
            new_groups.append(group)

    if new_groups:
        hooks[event] = new_groups
    elif event in hooks:
        del hooks[event]

if removed > 0:
    settings['hooks'] = hooks
    f.write_text(json.dumps(settings, indent=2))
    print(f'  Removed {removed} cc-monitor hook entries')
else:
    print('  No cc-monitor hooks found')
PYEOF

# 3. Clean up marker file
echo "[3/3] Cleaning up..."
rm -f "$MARKER_FILE"
echo "  Removed marker file"

echo ""
echo "=== Done ==="
echo "cc-monitor hooks uninstalled."
if [ -f "$BACKUP_FILE" ]; then
    echo "Backup saved at $BACKUP_FILE (restore with: cp $BACKUP_FILE $SETTINGS_FILE)"
fi
