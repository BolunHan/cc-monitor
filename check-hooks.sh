#!/usr/bin/env bash
# ============================================================================
# cc-monitor Hook Checker
#
# Checks whether cc-monitor hooks are installed for a given server URL
# and reports the result back to the server so the dashboard updates.
#
# Usage:
#   curl -skSL https://<server>:9876/static/check-hooks.sh | SERVER_URL=https://<server>:9876 bash
# ============================================================================
set -euo pipefail

SERVER_URL="${SERVER_URL:-https://127.0.0.1:9876}"
SETTINGS_FILE="${HOME}/.claude/settings.json"

echo "=== cc-monitor Hook Checker ==="
echo "  Server: ${SERVER_URL}"
echo ""

PYTHON=""
for c in python3 python; do
    command -v "$c" &>/dev/null && { PYTHON="$c"; break; }
done
if [ -z "$PYTHON" ]; then
    echo "ERROR: python3 not found."
    exit 1
fi

echo "[1/2] Checking hooks..."
SETTINGS="$SETTINGS_FILE" SERVER="$SERVER_URL" "$PYTHON" << 'PYEOF'
import json, os, ssl, sys, urllib.request
from pathlib import Path

settings_file = Path(os.environ['SETTINGS'])
server_url = os.environ.get('SERVER', '').rstrip('/')

EVENTS = ['PreToolUse','PostToolUse','UserPromptSubmit','Stop',
          'Notification','PermissionRequest','SessionEnd']

result = {'found': 0, 'missing': 0, 'uids': [], 'total': len(EVENTS)}

if not settings_file.exists():
    result['missing'] = len(EVENTS)
else:
    settings = json.loads(settings_file.read_text())
    hooks = settings.get('hooks', {})
    for event in EVENTS:
        found_event = False
        for group in hooks.get(event, []):
            for h in group.get('hooks', []):
                cmd = h.get('command', '')
                # Extract UID from command: ... --uid <uid>
                if server_url in cmd:
                    found_event = True
                    parts = cmd.split()
                    for i, p in enumerate(parts):
                        if p == '--uid' and i + 1 < len(parts):
                            uid = parts[i + 1]
                            if uid not in result['uids']:
                                result['uids'].append(uid)
        if found_event:
            result['found'] += 1
        else:
            result['missing'] += 1

print(f"  Found: {result['found']}/{result['total']}")
if result['uids']:
    print(f"  UIDs:  {', '.join(result['uids'])}")

# Post to server
ctx = ssl._create_unverified_context()
api = f"{server_url}/api/hooks-telemetry"
body = json.dumps({
    'status': 'check',
    'server_url': server_url,
    'cc_monitor_uids': result['uids'],
    'events_found': result['found'],
    'events_missing': result['missing'],
    'events_total': result['total'],
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
    print('  ⚠ Could not reach server')
PYEOF

echo ""
echo "=== Done ==="
