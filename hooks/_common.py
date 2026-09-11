"""Shared utilities for cc-monitor hook scripts (stdlib only, no deps).

This module is intentionally self-contained — it does NOT import from the
cc_monitor package, so hook scripts work regardless of venv state.

Identifiers:
  --url <url>      CLI arg — which cc-monitor server to POST events to
  CC_MONITOR_UID   env var — set by Claude Code via settings.json env field,
                   identifies the Claude instance across all servers
  CC_MONITOR_URL   env var — fallback server URL (legacy)

Fallback priority for server URL:
  1. --url CLI argument
  2. CC_MONITOR_URL environment variable
  3. https://localhost:9876 (legacy default)
"""

import json
import os
import ssl
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path.home() / ".cc-monitor"

# Accept self-signed certs (local dev server)
_SSL_CONTEXT = ssl._create_unverified_context()


def _parse_server_url() -> str:
    """Parse --url from CLI args, env, or default."""
    args = sys.argv[1:]
    for i, arg in enumerate(args):
        if arg == "--url" and i + 1 < len(args):
            return args[i + 1].rstrip("/")
    env_url = os.environ.get("CC_MONITOR_URL", "")
    if env_url:
        return env_url.rstrip("/")
    return "https://localhost:9876"


_SERVER_URL = _parse_server_url()
# Set by Claude Code via the 'env' field in ~/.claude/settings.json.
# This identifies the Claude instance, not the cc-monitor server.
_CC_MONITOR_UID = os.environ.get("CC_MONITOR_UID", "")

# Claude Code's per-session inbox socket. Exported into the hook environment,
# which makes the hook the only place that can see it — so every event carries
# it back to the server. Holding it lets a UI push a directive into an *idle*
# session instead of waiting for the session to stop on its own.
_MESSAGING_SOCKET = os.environ.get("CLAUDE_CODE_MESSAGING_SOCKET", "")
_MESSAGING_TOKEN = os.environ.get("CLAUDE_CODE_MESSAGING_TOKEN", "")


def _url_candidates(url: str) -> list[str]:
    """Yield the URL, plus an http:// variant when the URL is https://.

    The server may be running with or without TLS depending on how it was
    started, and a hook has no way to know which. Trying both costs one failed
    connect in the mismatch case and nothing in the common case.
    """
    if url.startswith("https://"):
        return [url, url.replace("https://", "http://", 1)]
    return [url]


def emit(payload: dict) -> None:
    """Write a Claude Code decision object to stdout.

    This is the only way a hook can influence the session, and no hook script
    printed to stdout before this existed, so there is nothing to collide with.
    """
    sys.stdout.write(json.dumps(payload))
    sys.stdout.flush()


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
    """Persist session state to ~/.cc-monitor/<session_id>/session.json.

    The server also owns this file and stores control-channel fields in it
    (queued directives, an outstanding pending request). Those are merged
    through rather than dropped — this hook has no opinion about them, and
    clobbering them would silently discard a directive the user had typed.
    """
    session_dir = DATA_DIR / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    file_path = session_dir / "session.json"

    carried: dict = {}
    try:
        existing = json.loads(file_path.read_text())
        if isinstance(existing, dict):
            for key in ("pending_request", "stop_requested", "stop_reason", "queued_directives"):
                if key in existing:
                    carried[key] = existing[key]
    except (OSError, json.JSONDecodeError, ValueError):
        pass

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
        "message_count": 0,
        **carried,
    }
    file_path.write_text(json.dumps(state, indent=2))


def notify_server(data: dict) -> dict | None:
    """POST the raw hook event to the server.

    Returns the server's parsed response, or None if it was unreachable. The
    response carries the ``control`` block — hold instructions for a pending
    approval, a stop request, or a queued directive — which is why this
    returns a value rather than a bool.

    Uses the configured server URL from --url / CC_MONITOR_URL / default.
    Self-signed certificates are accepted (local dev server).
    Includes cc_monitor_uid so the server knows which installation fired.
    """
    # Tag the event with our installation UID
    if _CC_MONITOR_UID:
        data["cc_monitor_uid"] = _CC_MONITOR_UID

    body = json.dumps(data).encode("utf-8")

    for url in _url_candidates(_SERVER_URL + "/api/event"):
        try:
            req = urllib.request.Request(
                url,
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            if url.startswith("https"):
                resp = urllib.request.urlopen(req, timeout=2, context=_SSL_CONTEXT)
            else:
                resp = urllib.request.urlopen(req, timeout=2)
            return json.loads(resp.read().decode("utf-8"))
        except Exception:
            continue
    return None


def fetch_decision(request_id: str, timeout: float) -> dict | None:
    """Long-poll the server for a UI's answer to a pending request.

    Returns the decision dict, or None if nobody answered within ``timeout``
    (or the server went away). None means "behave as if cc-monitor were not
    installed" — the caller must let the normal local flow proceed.
    """
    url = f"{_SERVER_URL}/api/request/{request_id}/decision?timeout={timeout}"
    # Client-side ceiling must exceed the server-side hold, or we would time
    # out first and abandon answers that arrived in the last moments.
    client_timeout = timeout + 10

    for candidate in _url_candidates(url):
        try:
            req = urllib.request.Request(candidate)
            if candidate.startswith("https"):
                resp = urllib.request.urlopen(req, timeout=client_timeout, context=_SSL_CONTEXT)
            else:
                resp = urllib.request.urlopen(req, timeout=client_timeout)
            return json.loads(resp.read().decode("utf-8")).get("decision")
        except Exception:
            continue
    return None


def fetch_directive(session_id: str, timeout: float) -> dict | None:
    """Long-poll the server for a directive typed into a UI.

    Returns the directive dict, or None if nothing arrived within ``timeout``.
    """
    url = f"{_SERVER_URL}/api/session/{session_id}/directive/next?timeout={timeout}"
    client_timeout = timeout + 10

    for candidate in _url_candidates(url):
        try:
            req = urllib.request.Request(candidate)
            if candidate.startswith("https"):
                resp = urllib.request.urlopen(req, timeout=client_timeout, context=_SSL_CONTEXT)
            else:
                resp = urllib.request.urlopen(req, timeout=client_timeout)
            return json.loads(resp.read().decode("utf-8")).get("directive")
        except Exception:
            continue
    return None


def permission_decision_payload(data: dict, decision: dict) -> dict:
    """Translate a cc-monitor decision into a PermissionRequest hook result.

    Kept here (rather than server-side) so the server stays agent-agnostic and
    knows nothing about Claude Code's hook JSON schema.
    """
    behavior = decision.get("behavior", "deny")
    out: dict = {"behavior": behavior}

    if behavior == "deny":
        out["message"] = decision.get("message") or "Denied from cc-monitor."
        return {"hookSpecificOutput": {"hookEventName": "PermissionRequest", "decision": out}}

    answers = decision.get("answers")
    tool_input = data.get("tool_input")
    if answers and isinstance(tool_input, dict):
        # AskUserQuestion is answered by echoing its input back with an
        # `answers` map added — returning "allow" alone does NOT answer it.
        updated = dict(tool_input)
        updated["answers"] = answers
        out["updatedInput"] = updated
    elif decision.get("updated_input"):
        out["updatedInput"] = decision["updated_input"]

    return {"hookSpecificOutput": {"hookEventName": "PermissionRequest", "decision": out}}


def _apply_permission_control(data: dict, control: dict) -> None:
    """Hold the terminal dialog and answer it remotely, if a UI is watching."""
    request_id = control.get("request_id")
    try:
        hold = float(control.get("hold_seconds") or 0)
    except (TypeError, ValueError):
        hold = 0.0

    # hold == 0 means no UI is connected (or the feature is off). Return
    # immediately so the local dialog appears with no added latency.
    if not request_id or hold <= 0:
        return

    decision = fetch_decision(request_id, hold)
    if decision:
        emit(permission_decision_payload(data, decision))


def _apply_control(data: dict, control: dict) -> None:
    """Handle the non-approval control instructions: stop and directives."""
    event = data.get("hook_event_name")

    if event == "PreToolUse" and control.get("stop"):
        # Denying the tool is the stop. `continue: false` is what actually
        # ends the turn rather than letting the agent route around the deny —
        # it is the closest hook-level equivalent of pressing Esc.
        emit({
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": (
                    "The user requested a stop from cc-monitor. Do not call "
                    "further tools. End your turn and summarise where things stand."
                ),
            },
            "continue": False,
            "stopReason": control.get("stop_reason") or "Stopped from cc-monitor",
        })
        return

    if event == "Stop":
        directive = control.get("directive")

        # Nothing queued yet, but a UI is connected — park at the turn boundary
        # for a moment so a follow-up typed right now can still land.
        if not directive:
            try:
                hold = float(control.get("directive_hold_seconds") or 0)
            except (TypeError, ValueError):
                hold = 0.0
            if hold > 0:
                directive = fetch_directive(data.get("session_id", ""), hold)

        if not directive or not directive.get("text"):
            return
        # No `stop_hook_active` guard here on purpose. That guard exists to
        # stop a hook blocking unconditionally forever, but this hook only
        # blocks when a *new* directive is waiting — and the server marks a
        # directive delivered as it hands it over, so the same one can never be
        # handed out twice. The guard would instead break the second of two
        # directives typed in quick succession, because Claude Code sets
        # `stop_hook_active` on the continuation. Claude Code's own
        # 8-consecutive-block ceiling remains as the backstop.
        emit({
            "hookSpecificOutput": {
                "hookEventName": "Stop",
                "additionalContext": (
                    "[cc-monitor] The user sent this directive from the cc-monitor "
                    "UI. Act on it now:\n\n" + str(directive.get("text", ""))
                ),
            },
        })


def run_hook(expected_event: str, decide: bool = False) -> None:
    """Read stdin JSON, write state file, notify server, apply control.

    Args:
        expected_event: Event name this script is registered for; anything
            else on stdin is ignored.
        decide: When True (PermissionRequest only), hold the terminal dialog
            open for a remote answer if a UI is connected.
    """
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

    # Report the inbox socket so the server can push directives into this
    # session even while it sits idle.
    if _MESSAGING_SOCKET:
        data.setdefault("messaging_socket", _MESSAGING_SOCKET)
        data.setdefault("messaging_token", _MESSAGING_TOKEN)

    write_state_file(session_id, data)
    response = notify_server(data)
    control = (response or {}).get("control") or {}

    if decide:
        _apply_permission_control(data, control)
    else:
        _apply_control(data, control)
