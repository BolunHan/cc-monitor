#!/usr/bin/env bash
# ============================================================================
# cc-monitor Hook Uninstaller
#
# Removes cc-monitor hooks from ~/.claude/settings.json by parsing the JSON
# and deleting only the 7 cc-monitor hook events (not touching other hooks).
# Also removes the marker file and hook scripts.
#
# Usage:
#   curl -sSL https://192.168.3.28:9876/static/uninstall-hooks.sh | bash
# ============================================================================
set -euo pipefail

HOOKS_DIR="${HOME}/.cc-monitor/hooks"
SETTINGS_FILE="${HOME}/.claude/settings.json"
MARKER_FILE="${HOME}/.cc-monitor/.hooks-installed"
BACKUP_FILE="${HOME}/.claude/settings.json.cc-monitor.bak"

CC_HOOK_EVENTS=(
    "PreToolUse" "PostToolUse" "UserPromptSubmit" "Stop"
    "Notification" "PermissionRequest" "SessionEnd"
)

echo "=== cc-monitor Hook Uninstaller ==="

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
CC_EVENTS="${CC_HOOK_EVENTS[*]}" CC_FILE="$SETTINGS_FILE" python3 << 'PYEOF'
import json, os, sys
from pathlib import Path

events = os.environ['CC_EVENTS'].split()
f = Path(os.environ['CC_FILE'])
if not f.exists():
    print('  No settings file — nothing to do')
    sys.exit(0)

settings = json.loads(f.read_text())
hooks = settings.get('hooks', {})
removed = 0
for event in events:
    if event in hooks:
        del hooks[event]
        removed += 1

if removed > 0:
    settings['hooks'] = hooks
    f.write_text(json.dumps(settings, indent=2))
    print(f'  Removed {removed} cc-monitor hook events')
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
