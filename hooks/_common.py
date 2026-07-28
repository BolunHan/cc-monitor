"""Shared utilities for cc-monitor hook scripts (stdlib only, no deps).

This module is intentionally self-contained — it does NOT import from the
cc_monitor package, so hook scripts work regardless of venv state.
"""

import json
import ssl
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path.home() / ".cc-monitor"
_SERVER_HOST = "localhost"
_SERVER_PORT = 9876
_HTTP_URL = f"http://{_SERVER_HOST}:{_SERVER_PORT}/api/event"
_HTTPS_URL = f"https://{_SERVER_HOST}:{_SERVER_PORT}/api/event"
# Accept self-signed certs (local dev server)
_SSL_CONTEXT = ssl._create_unverified_context()


def map_event(hook_event_name: str, notification_type: str | None = None) -> str:
    """Map a raw hook event to a state string.

    Duplicated here so hook scripts don't depend on cc_monitor.mapping.
    Keep in sync with src/cc_monitor/mapping.py.
    """
    if hook_event_name in ("PreToolUse", "PostToolUse", "UserPromptSubmit"):
        return "working"
    if hook_event_name == "Stop":
        return "pending_review"
    if hook_event_name == "Notification":
        if notification_type == "idle_prompt":
            return "idle"
        if notification_type == "permission_prompt":
            return "pending_approval"
        return "working"
    if hook_event_name == "PermissionRequest":
        return "pending_approval"
    if hook_event_name == "SessionEnd":
        return "all_done"
    return "working"


def write_state_file(session_id: str, data: dict) -> None:
    """Persist session state to ~/.cc-monitor/<session_id>.json."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    state = {
        "session_id": session_id,
        "cwd": data.get("cwd", ""),
        "state": map_event(
            data.get("hook_event_name", ""),
            data.get("notification_type"),
        ),
        "raw_event": data.get("hook_event_name", ""),
        "raw_detail": data.get("tool_name") or data.get("notification_type"),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    file_path = DATA_DIR / f"{session_id}.json"
    file_path.write_text(json.dumps(state, indent=2))


def notify_server(data: dict) -> bool:
    """POST the raw hook event to the server. Returns True on success.

    Tries HTTPS first (server may have TLS enabled), then HTTP as fallback.
    Self-signed certificates are accepted (local dev server).
    """
    body = json.dumps(data).encode("utf-8")
    for url in (_HTTPS_URL, _HTTP_URL):
        try:
            req = urllib.request.Request(
                url,
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            if url.startswith("https"):
                urllib.request.urlopen(req, timeout=2, context=_SSL_CONTEXT)
            else:
                urllib.request.urlopen(req, timeout=2)
            return True
        except Exception:
            continue
    return False


def run_hook(expected_event: str) -> None:
    """Read stdin JSON, write state file, notify server."""
    raw = sys.stdin.read()
    if not raw.strip():
        return
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return

    if data.get("hook_event_name") != expected_event:
        return

    session_id = data.get("session_id", "unknown")
    write_state_file(session_id, data)
    notify_server(data)
