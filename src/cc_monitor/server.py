"""FastAPI server for cc-monitor — REST API + SSE + static dashboard."""

import argparse
import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from cc_monitor import __version__
from cc_monitor.auth import PairingManager, TokenManager
from cc_monitor.auth_routes import create_auth_middleware, create_auth_router
from cc_monitor.mdns import MDNSAdvertiser
from cc_monitor.state import StateManager
from cc_monitor.tls import CertConfig, generate_self_signed_cert, get_cert_fingerprint
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

logger = logging.getLogger(__name__)


def _detect_lan_ip() -> str:
    """Auto-detect the LAN IP address (no internet required).

    Uses the UDP-connect trick: opens a datagram socket and
    "connects" to 10.254.254.254 (TEST-NET-2, RFC 5737 — guaranteed
    non-routable).  The kernel never sends a packet; it just binds
    the local address to whichever interface has the default route.
    This returns the LAN IP that other devices on the network can
    reach.

    If no default route exists (isolated network with static IP),
    falls back to iterating network interfaces via if_nameindex()
    and picks the first non-loopback IPv4 address.

    In the worst case returns "127.0.0.1" — the user can always
    pass an explicit --host flag.
    """
    import socket

    # Tier 1 — UDP connect (works with or without internet, but needs a route)
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.1)
        s.connect(("10.254.254.254", 1))
        ip: str = s.getsockname()[0]
        s.close()
        if ip != "127.0.0.1":
            return ip
    except OSError:
        pass

    # Tier 2 — interface walk (no route / no gateway needed)
    try:
        for if_name, _ in socket.if_nameindex():
            if if_name.startswith("lo"):
                continue
            try:
                addrlist = socket.getaddrinfo(
                    socket.gethostname(),
                    None,
                    family=socket.AF_INET,
                )
                for _fam, _typ, _proto, _cn, sa in addrlist:
                    ip = sa[0]
                    if not ip.startswith("127."):
                        return ip
            except Exception:
                continue
    except Exception:
        pass

    return "127.0.0.1"


def _resolve_root() -> Path:
    """Find the project root containing static/ and hooks/ directories.

    When installed via pip, __file__ points into site-packages and
    the static/hooks directories are elsewhere.  Check:
    1. CC_MONITOR_ROOT env var (Docker / custom deployments)
    2. Relative to __file__ (editable install / dev)
    3. /app (Docker container default)
    """
    import os
    if (env := os.environ.get("CC_MONITOR_ROOT")):
        return Path(env)
    candidate = Path(__file__).resolve().parent.parent.parent
    if (candidate / "static").is_dir():
        return candidate
    if (Path("/app/static")).is_dir():
        return Path("/app")
    return candidate  # fallback

_PROJECT_ROOT = _resolve_root()
_STATIC_DIR = _PROJECT_ROOT / "static"
_SOURCE_HOOKS_DIR = _PROJECT_ROOT / "hooks"
# Set during Docker build — server uses this to route install/uninstall to the one-liner
_IS_DOCKER = (_PROJECT_ROOT / ".docker-env").exists()


def _safe_home() -> Path:
    """Return the data directory root.

    In Docker: /data (a named volume managed by Docker).
    Natively: the user's home directory.
    """
    if _IS_DOCKER:
        return Path("/data")
    return Path.home()


_GLOBAL_HOOKS_DIR = _safe_home() / ".cc-monitor" / "hooks"
_GLOBAL_SETTINGS_PATH = _safe_home() / ".claude" / "settings.json"
_BACKUP_PATH = _safe_home() / ".claude" / "settings.json.cc-monitor.bak"

# Hook event definitions (kept in sync with install-hooks.sh)
_HOOK_EVENT_DEFS: dict[str, dict[str, str]] = {
    "PreToolUse":        {"matcher": "*", "script": "pre_tool_use.py"},
    "PostToolUse":       {"matcher": "*", "script": "post_tool_use.py"},
    "UserPromptSubmit":  {"matcher": "",  "script": "user_prompt_submit.py"},
    "Stop":              {"matcher": "",  "script": "stop.py"},
    "Notification":      {"matcher": "*", "script": "notification.py"},
    "PermissionRequest": {"matcher": "*", "script": "permission_request.py"},
    "SessionEnd":        {"matcher": "",  "script": "session_end.py"},
}


def _format_sse_event(event: str, data: str | None = None) -> str:
    """Format a single SSE event block.

    Args:
        event: The event type name (e.g. "state_update", "heartbeat").
        data: Optional JSON string for the data field.

    Returns:
        An SSE-formatted string ending with \\n\\n.
    """
    if data is not None:
        return f"event: {event}\ndata: {data}\n\n"
    return f"event: {event}\n\n"


def create_app(
    data_dir: Path | None = None,
    enable_auth: bool = False,
    token_ttl: int = 604800,
    cert_config: CertConfig | None = None,
    pairing_manager: PairingManager | None = None,
    token_manager: TokenManager | None = None,
    lan_host: str = "",
    port: int = 9876,
    use_tls: bool = False,
) -> FastAPI:
    """Build the FastAPI app with a given data directory.

    Args:
        data_dir: Where session state files are stored. Defaults to
            ~/.cc-monitor.
        enable_auth: Enables authentication middleware and auth routes
            when True. Defaults to False for backward compatibility.
        token_ttl: Token lifetime in seconds (0 = never expire).
            Default: 604800 (7 days).
        cert_config: TLS certificate configuration for QR pairing.
            Auto-created with placeholder fingerprint if None.
        pairing_manager: Shared PairingManager instance. Created from
            token_ttl if None.
        token_manager: Shared TokenManager instance. Created from
            data_dir if None.
        port: Server port (used to construct hook --url arg).
        use_tls: Whether TLS is enabled (used to construct hook --url).

    Returns:
        A configured FastAPI application.
    """
    app = FastAPI(title="cc-monitor", version=__version__)
    _data_dir = data_dir or _safe_home() / ".cc-monitor"
    manager = StateManager(data_dir=_data_dir)

    # Allow cross-origin requests from any origin (dashboard may be
    # hosted on GitHub Pages or another static host).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.on_event("startup")
    async def _restore():
        await manager.restore()
        manager.start_review_timeout()

    # Wire auth if enabled
    if enable_auth:
        if token_manager is None:
            token_manager = TokenManager(data_dir=_data_dir)
        if pairing_manager is None:
            pairing_manager = PairingManager(
                data_dir=_data_dir,
                token_manager=token_manager,
                ttl_seconds=token_ttl,
            )
        if cert_config is None:
            cert_config = CertConfig(
                certfile=_data_dir / "cert.pem",
                keyfile=_data_dir / "key.pem",
                fingerprint="",
            )

        app.middleware("http")(create_auth_middleware(token_manager))

        auth_router = create_auth_router(
            token_manager, pairing_manager, cert_config, token_ttl,
            lan_host=lan_host,
            broadcast_callback=manager.broadcast_event,
        )
        app.include_router(auth_router)

        # Store references on app for lifecycle access
        app.state.token_manager = token_manager
        app.state.pairing_manager = pairing_manager

        # Background task to broadcast new pairing requests via SSE
        @app.on_event("startup")
        async def _start_pairing_poll():
            _seen: set[str] = set()

            async def _poll_loop():
                while True:
                    try:
                        for req in pairing_manager.get_pending():
                            if req.id not in _seen:
                                _seen.add(req.id)
                                await manager.broadcast_pairing_request({
                                    "id": req.id,
                                    "device_name": req.device_name,
                                    "requested_at": req.requested_at.isoformat(),
                                    "status": req.status,
                                })
                    except Exception:
                        logger.exception("Error polling pairing requests")

                    # Cap _seen to prevent unbounded memory growth
                    if len(_seen) > 1000:
                        _seen.clear()
                        for req in pairing_manager.get_pending():
                            _seen.add(req.id)

                    await asyncio.sleep(1.0)

            asyncio.ensure_future(_poll_loop())

    # ---- API routes ----

    @app.post("/api/event")
    async def handle_event(request: Request):
        """Receive a raw hook event, update state, broadcast SSE."""
        raw = await request.json()
        session = await manager.handle_event(raw)
        return JSONResponse(session.to_dict())

    @app.get("/api/status")
    async def get_all_status():
        """Return all known session states."""
        sessions = [s.to_dict() for s in manager.get_all()]
        return JSONResponse({"sessions": sessions, "count": len(sessions)})

    @app.get("/api/status/{session_id}")
    async def get_session_status(session_id: str):
        """Return a single session's state, or 404."""
        session = manager.get(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found")
        return JSONResponse(session.to_dict())

    @app.get("/api/stream")
    async def sse_stream(request: Request):
        """SSE endpoint — pushes state_update events in real time."""
        queue = manager.subscribe()

        async def event_generator():
            try:
                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        item = await asyncio.wait_for(queue.get(), timeout=3.0)
                        if isinstance(item, dict) and "type" in item:
                            # Typed envelope: {"type": "event_name", "data": {...}}
                            if item["type"] == "pairing_request":
                                yield _format_sse_event(
                                    "pairing_request", item["data"],
                                )
                            elif item["type"] == "state_update":
                                yield _format_sse_event(
                                    "state_update", json.dumps(item["data"]),
                                )
                            else:
                                # device_update, pairing_resolved, etc.
                                yield _format_sse_event(
                                    str(item["type"]), json.dumps(item["data"]),
                                )
                        else:
                            # Old-style plain dict (_broadcast backward compat)
                            yield _format_sse_event(
                                "state_update", json.dumps(item),
                            )
                    except asyncio.TimeoutError:
                        yield _format_sse_event(
                            "heartbeat",
                            json.dumps({"ts": asyncio.get_event_loop().time()}),
                        )
            finally:
                manager.unsubscribe(queue)

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @app.get("/api/version")
    async def version():
        """Return the cc-monitor server version and runtime info."""
        return JSONResponse({
            "version": __version__,
            "docker": _IS_DOCKER,
        })

    # ---- Session actions ----

    @app.post("/api/session/{session_id}/archive")
    async def archive_session(session_id: str):
        """Archive a session (hide from active/complete views)."""
        session = await manager.archive(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found")
        return JSONResponse(session.to_dict())

    @app.post("/api/session/{session_id}/unarchive")
    async def unarchive_session(session_id: str):
        """Unarchive a session."""
        session = await manager.unarchive(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found")
        return JSONResponse(session.to_dict())

    @app.post("/api/session/{session_id}/complete")
    async def mark_complete(session_id: str):
        """Manually mark a session as all_done."""
        session = await manager.mark_complete(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found")
        return JSONResponse(session.to_dict())

    # ---- Hook installation ----

    # Compute the URL hooks should use to reach this server.
    # Server-side install is only reachable from localhost, so hooks
    # on the same machine use 127.0.0.1:<port>.
    _hooks_scheme = "https" if use_tls else "http"
    _hooks_server_url = f"{_hooks_scheme}://127.0.0.1:{port}"

    def _build_hook_command(script_name: str) -> str:
        """Construct the hook command string with --url argument."""
        script_path = str(_GLOBAL_HOOKS_DIR / script_name)
        return f"{script_path} --url {_hooks_server_url}"

    def _build_hook_groups() -> dict:
        """Build hook event groups with proper commands and matchers."""
        hooks_config = {}
        for event_name, cfg in _HOOK_EVENT_DEFS.items():
            entry: dict = {
                "hooks": [{
                    "type": "command",
                    "command": _build_hook_command(cfg["script"]),
                    "description": f"cc-monitor: {event_name}",
                }]
            }
            if cfg["matcher"]:
                entry["matcher"] = cfg["matcher"]
            hooks_config[event_name] = [entry]
        return hooks_config

    def _load_global_settings() -> dict:
        """Read the global settings file, or return empty dict."""
        if not _GLOBAL_SETTINGS_PATH.exists():
            return {}
        try:
            return json.loads(_GLOBAL_SETTINGS_PATH.read_text())
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Invalid JSON in {_GLOBAL_SETTINGS_PATH}: {exc}",
            )

    def _save_global_settings(settings: dict) -> None:
        """Write global settings to disk."""
        _GLOBAL_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        _GLOBAL_SETTINGS_PATH.write_text(json.dumps(settings, indent=2))

    # Populate known event names from hook event defs
    _hook_event_names: set[str] = set(_HOOK_EVENT_DEFS.keys())
    _marker_file = manager._data_dir / ".hooks-installed"

    @app.get("/api/hooks-status")
    async def hooks_status():
        """Check whether cc-monitor hooks are installed.

        Checks (in order):
        1. Marker file (~/.cc-monitor/.hooks-installed) — most reliable
        2. Global settings (~/.claude/settings.json) — localhost fallback
        """
        marker = _marker_file.exists()

        installed_events: list[str] = []
        missing_events: list[str] = []
        try:
            global_settings = _load_global_settings()
            global_hooks = global_settings.get("hooks", {})
            for event_name in _hook_event_names:
                if event_name in global_hooks:
                    installed_events.append(event_name)
                else:
                    missing_events.append(event_name)
        except Exception:
            pass

        installed = marker or (
            len(missing_events) == 0 and len(installed_events) > 0
        )

        return JSONResponse({
            "installed": installed,
            "marker": marker,
            "installed_events": installed_events,
            "missing_events": missing_events,
            "target": str(_GLOBAL_SETTINGS_PATH),
        })

    # In-memory hook telemetry (populated by install/uninstall/check scripts)
    _hook_state: dict = {"installed": False, "uids": [], "last_report": "", "updated_at": ""}

    @app.post("/api/hooks-telemetry")
    async def hooks_telemetry(request: Request):
        """Receive hook installation telemetry from install/check scripts.

        Called by install-hooks.sh, uninstall-hooks.sh, and check-hooks.sh
        after they complete.  The server stores this and broadcasts an SSE
        event so the dashboard updates in real time.
        """
        body = await request.json()
        status = body.get("status", "")
        uids = body.get("cc_monitor_uids", [])
        uid = body.get("cc_monitor_uid", "")
        if uid and uid not in uids:
            uids.append(uid)

        now_iso = datetime.now(timezone.utc).isoformat()

        if status == "installed":
            _hook_state.update({
                "installed": True, "uids": uids, "last_report": "installed",
                "events_found": body.get("events_merged", 0) or len(uids) * 7,
                "events_missing": 0, "updated_at": now_iso,
            })
        elif status == "uninstalled":
            _hook_state.update({
                "installed": False, "uids": [], "last_report": "uninstalled",
                "events_found": 0, "events_missing": 7, "updated_at": now_iso,
            })
        elif status == "check":
            found = body.get("events_found", 0)
            missing = body.get("events_missing", 0)
            _hook_state.update({
                "installed": found > 0, "uids": uids, "last_report": "check",
                "events_found": found, "events_missing": missing, "updated_at": now_iso,
            })

        # Also maintain the marker file for backward compat
        if _hook_state["installed"]:
            _marker_file.touch()
        elif _marker_file.exists():
            _marker_file.unlink()

        # Broadcast to all SSE clients
        await manager.broadcast_event("hooks_status_update", {
            "installed": _hook_state["installed"],
            "uids": _hook_state["uids"],
            "events_found": _hook_state.get("events_found", 0),
            "events_missing": _hook_state.get("events_missing", 0),
            "last_report": _hook_state["last_report"],
            "updated_at": _hook_state["updated_at"],
        })

        return JSONResponse({"status": "ok", "hook_state": _hook_state})

    @app.post("/api/install-hooks")
    async def install_hooks():
        """Inject cc-monitor hooks into the global Claude Code settings.

        When running natively, copies hook scripts and merges configuration
        into ~/.claude/settings.json.  Creates the .hooks-installed marker.

        When running in Docker, the server cannot write to the host's
        ~/.claude/settings.json — returns the one-liner shell command
        that the browser can display to the user.
        """
        if _IS_DOCKER:
            # Docker can still copy hook scripts to the shared volume
            if _SOURCE_HOOKS_DIR.is_dir():
                import shutil
                _GLOBAL_HOOKS_DIR.mkdir(parents=True, exist_ok=True)
                for src_file in _SOURCE_HOOKS_DIR.iterdir():
                    if src_file.suffix == ".py":
                        shutil.copy2(src_file, _GLOBAL_HOOKS_DIR / src_file.name)
            # Create marker so hooks-status reports installed
            _marker_file.touch()
            # Return the one-liner — the web UI shows this in a modal
            return JSONResponse({
                "status": "docker",
                "mode": "docker",
                "oneliner": (
                    f"curl -skSL {_hooks_server_url}/static/install-hooks.sh"
                    f" | SERVER_URL={_hooks_server_url} bash"
                ),
                "message": "Running in Docker — run this command on the host machine.",
            })

        # --- Native install below ---

        # 1. Copy hook scripts to ~/.cc-monitor/hooks/
        if _SOURCE_HOOKS_DIR.is_dir():
            import shutil
            _GLOBAL_HOOKS_DIR.mkdir(parents=True, exist_ok=True)
            copied = 0
            for src_file in _SOURCE_HOOKS_DIR.iterdir():
                if src_file.suffix == ".py":
                    shutil.copy2(src_file, _GLOBAL_HOOKS_DIR / src_file.name)
                    copied += 1
            logger.info("Copied %d hook scripts to %s", copied, _GLOBAL_HOOKS_DIR)

        # 2. Build hook groups with --url commands
        source_hooks = _build_hook_groups()
        target = _load_global_settings()

        # Create backup before modifying
        if _GLOBAL_SETTINGS_PATH.exists() and _GLOBAL_SETTINGS_PATH.is_file():
            _BACKUP_PATH.write_text(json.dumps(target, indent=2))
            logger.info("Backed up global settings to %s", _BACKUP_PATH)

        # 3. Merge: append our hook groups, preserving existing entries
        target_hooks = target.get("hooks", {})
        merged_count = 0
        skipped_count = 0

        for event_name, new_groups in source_hooks.items():
            our_cmds = set()
            for g in new_groups:
                for h in g.get("hooks", []):
                    our_cmds.add(h.get("command", ""))

            existing_groups = target_hooks.get(event_name, [])

            already_there = False
            for eg in existing_groups:
                for eh in eg.get("hooks", []):
                    if eh.get("command", "") in our_cmds:
                        already_there = True
                        break

            if already_there:
                skipped_count += 1
                continue

            target_hooks[event_name] = existing_groups + new_groups
            merged_count += 1

        target["hooks"] = target_hooks
        _save_global_settings(target)

        # 4. Create marker file
        _marker_file.touch()

        logger.info(
            "Installed %d cc-monitor hook events into %s (skipped %d already present)",
            merged_count, _GLOBAL_SETTINGS_PATH, skipped_count,
        )

        return JSONResponse({
            "status": "ok",
            "mode": "native",
            "installed_events": merged_count,
            "skipped_events": skipped_count,
            "target": str(_GLOBAL_SETTINGS_PATH),
            "backup": str(_BACKUP_PATH) if _BACKUP_PATH.exists() else None,
        })

    @app.post("/api/uninstall-hooks")
    async def uninstall_hooks():
        """Remove cc-monitor hooks from the global Claude Code settings.

        When running in Docker, returns the one-liner uninstall command.
        When native, surgically removes only this server's hooks.
        """
        if _IS_DOCKER:
            # Clean up marker + scripts from shared volume
            if _marker_file.exists():
                _marker_file.unlink()
            if _GLOBAL_HOOKS_DIR.is_dir():
                import shutil
                shutil.rmtree(_GLOBAL_HOOKS_DIR, ignore_errors=True)
            return JSONResponse({
                "status": "docker",
                "mode": "docker",
                "oneliner": (
                    f"curl -skSL {_hooks_server_url}/static/uninstall-hooks.sh"
                    f" | SERVER_URL={_hooks_server_url} bash"
                ),
                "message": "Running in Docker — run this command on the host machine.",
            })

        # --- Native uninstall below ---
        target = _load_global_settings()
        target_hooks = target.get("hooks", {})

        removed_count = 0
        server_url = _hooks_server_url
        hooks_dir_str = str(_GLOBAL_HOOKS_DIR)

        for event_name in _hook_event_names:
            groups = target_hooks.get(event_name, [])
            new_groups = []
            for group in groups:
                kept_hooks = []
                for h in group.get("hooks", []):
                    cmd = h.get("command", "")
                    if (hooks_dir_str in cmd) and (server_url in cmd):
                        removed_count += 1
                    else:
                        kept_hooks.append(h)
                if kept_hooks:
                    group["hooks"] = kept_hooks
                    new_groups.append(group)

            if new_groups:
                target_hooks[event_name] = new_groups
            elif event_name in target_hooks:
                del target_hooks[event_name]

        target["hooks"] = target_hooks
        _save_global_settings(target)

        if _marker_file.exists():
            _marker_file.unlink()

        if _GLOBAL_HOOKS_DIR.is_dir():
            import shutil
            shutil.rmtree(_GLOBAL_HOOKS_DIR, ignore_errors=True)

        logger.info(
            "Uninstalled %d cc-monitor hook entries from %s",
            removed_count, _GLOBAL_SETTINGS_PATH,
        )

        return JSONResponse({
            "status": "ok",
            "mode": "native",
            "removed_entries": removed_count,
            "target": str(_GLOBAL_SETTINGS_PATH),
            "backup_available": _BACKUP_PATH.exists(),
        })

    # ---- Static files ----
    # Serve at /static (absolute paths) and at /css, /js (relative paths for gh-pages compat)

    @app.get("/favicon.svg")
    async def favicon():
        """Serve the favicon at root level (HTML uses relative ./favicon.svg)."""
        path = _STATIC_DIR / "favicon.svg"
        if path.exists():
            return FileResponse(path, media_type="image/svg+xml")
        raise HTTPException(status_code=404)

    @app.get("/", response_class=HTMLResponse)
    async def index():
        index_path = _STATIC_DIR / "index.html"
        if not index_path.exists():
            return HTMLResponse("<h1>cc-monitor</h1><p>static/index.html not found.</p>")
        return HTMLResponse(index_path.read_text())

    if _STATIC_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")
    if (_STATIC_DIR / "css").is_dir():
        app.mount("/css", StaticFiles(directory=str(_STATIC_DIR / "css")), name="css")
    if (_STATIC_DIR / "js").is_dir():
        app.mount("/js", StaticFiles(directory=str(_STATIC_DIR / "js")), name="js")
    _hooks_dir = _PROJECT_ROOT / "hooks"
    if _hooks_dir.is_dir():
        app.mount("/hooks", StaticFiles(directory=str(_hooks_dir)), name="hooks")

    return app


# Module-level app instance for uvicorn
app = create_app()


def main() -> None:
    """CLI entry point: start the cc-monitor server."""
    parser = argparse.ArgumentParser(description="cc-monitor — Claude Code status monitor")
    parser.add_argument("--port", type=int, default=9876, help="Port to listen on (default: 9876)")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host to bind to (default: 127.0.0.1)")
    parser.add_argument("--data-dir", type=str, default=None,
                        help="State file directory (default: ~/.cc-monitor)")
    parser.add_argument("--token-ttl", type=int, default=604800,
                        help="Token lifetime in seconds (0 = never expire, default: 604800)")
    parser.add_argument("--no-mdns", action="store_true",
                        help="Disable mDNS LAN advertisement")
    parser.add_argument("--revoke-all", action="store_true",
                        help="Revoke all tokens and exit")
    parser.add_argument("--tls-cert", type=str, default=None,
                        help="Path to custom TLS certificate")
    parser.add_argument("--tls-key", type=str, default=None,
                        help="Path to custom TLS private key")
    parser.add_argument("--approve", type=str, default=None, metavar="CODE",
                        help="Approve a pairing request by 6-digit code")
    args = parser.parse_args()

    import uvicorn

    data_dir = Path(args.data_dir) if args.data_dir else None
    _data_dir = data_dir or _safe_home() / ".cc-monitor"

    # Handle --revoke-all
    if args.revoke_all:
        import ssl as _ssl
        import urllib.request as _ur
        import urllib.parse as _up
        ctx = _ssl._create_unverified_context()
        base = f"https://127.0.0.1:{args.port}"
        try:
            req = _ur.Request(f"{base}/api/auth/devices")
            resp = _ur.urlopen(req, timeout=5, context=ctx)
            devices = json.loads(resp.read().decode())["devices"]
            for d in devices:
                cid = d.get("client_id", "")
                if cid:
                    req2 = _ur.Request(
                        f"{base}/api/auth/devices/{_up.quote(cid, safe='')}",
                        method="DELETE",
                    )
                    _ur.urlopen(req2, timeout=5, context=ctx)
            print(f"Revoked {len(devices)} device(s).")
        except Exception as e:
            print(f"Failed: {e}")
        return

    # Handle --approve <code>
    if args.approve:
        import ssl
        import urllib.request
        code = args.approve.strip()
        ctx = ssl._create_unverified_context()
        base = f"https://127.0.0.1:{args.port}"
        try:
            # List pending requests
            req = urllib.request.Request(f"{base}/api/auth/pair/requests")
            resp = urllib.request.urlopen(req, timeout=5, context=ctx)
            pending = json.loads(resp.read().decode())["requests"]
            match = next((r for r in pending if r.get("pairing_code") == code), None)
            if match is None:
                print(f"No pending pairing request with code '{code}'")
                codes = [r.get("pairing_code", "") for r in pending]
                print(f"Pending codes: {codes}")
                return
            # Approve via API
            req2 = urllib.request.Request(
                f"{base}/api/auth/pair/request/{match['id']}/approve",
                method="POST",
            )
            resp2 = urllib.request.urlopen(req2, timeout=5, context=ctx)
            result = json.loads(resp2.read().decode())
            print(f"Approved pairing request '{match['id']}'")
            print(f"Device: {match['device_name']}")
            print(f"Token: {result['token']}")
        except Exception as e:
            print(f"Failed to approve: {e}")
            print("Is the cc-monitor server running?")
        return

    # Enable auth when binding to non-localhost
    enable_auth = args.host not in ("127.0.0.1", "localhost", "::1")
    if enable_auth:
        logger.info("LAN mode: auth, TLS, and mDNS enabled (host=%s)", args.host)
    else:
        logger.info("Local mode: auth and mDNS disabled (localhost only)")

    # TLS configuration
    ssl_kwargs: dict[str, str] = {}
    cert_config = None
    if enable_auth:
        if args.tls_cert and args.tls_key:
            cert_path = Path(args.tls_cert)
            key_path = Path(args.tls_key)
        else:
            cert_path, key_path = generate_self_signed_cert(_data_dir)
        fingerprint = get_cert_fingerprint(cert_path)
        cert_config = CertConfig(
            certfile=cert_path, keyfile=key_path, fingerprint=fingerprint,
        )
        ssl_kwargs = {
            "ssl_certfile": str(cert_path),
            "ssl_keyfile": str(key_path),
        }
        logger.info("TLS enabled, cert fingerprint: %s", fingerprint)

    # Auto-detect LAN IP for QR pairing when binding to 0.0.0.0
    lan_host = args.host
    if lan_host in ("0.0.0.0", "::"):
        lan_host = _detect_lan_ip()
        logger.info("Detected LAN IP: %s", lan_host)

    _app = create_app(
        data_dir=data_dir,
        enable_auth=enable_auth,
        token_ttl=args.token_ttl,
        cert_config=cert_config,
        lan_host=lan_host,
        port=args.port,
        use_tls=bool(ssl_kwargs),
    )

    # Start mDNS advertiser
    if enable_auth and not args.no_mdns and cert_config:
        mdns = MDNSAdvertiser(
            host=lan_host,
            port=args.port,
            version=__version__,
            cert_sha256=cert_config.fingerprint,
        )

        @_app.on_event("startup")
        async def _start_mdns():
            print(f"[mDNS] Starting advertisement for _cc-monitor._tcp on {lan_host}:{args.port}")
            try:
                await mdns.start()
                print(f"[mDNS] Now advertising _cc-monitor._tcp on LAN (version={__version__})")
                logger.info(
                    "mDNS: advertising _cc-monitor._tcp on %s:%d (version=%s, cert=%s)",
                    args.host, args.port, __version__, cert_config.fingerprint[:18] + "...",
                )
            except Exception as exc:
                import traceback
                print(f"[mDNS] FAILED to start: {type(exc).__name__}: {exc}")
                traceback.print_exc()
                logger.warning("mDNS: failed to start advertisement: %s", exc, exc_info=True)

        @_app.on_event("shutdown")
        async def _stop_mdns():
            await mdns.stop()
    elif enable_auth and args.no_mdns:
        logger.info("mDNS: disabled via --no-mdns flag")
    elif enable_auth and not cert_config:
        logger.warning("mDNS: skipped — no TLS cert configured")

    uvicorn_kwargs: dict[str, str | int] = {
        "host": args.host,
        "port": args.port,
        "log_level": "info",
    }
    if ssl_kwargs:
        uvicorn_kwargs.update(ssl_kwargs)

    # Startup summary
    scheme = "https" if ssl_kwargs else "http"
    print(f"\n  cc-monitor v{__version__}")
    print(f"  Listening on {scheme}://{args.host}:{args.port}")
    if enable_auth:
        print(f"  Auth: enabled (token TTL: {args.token_ttl}s" + (" = never" if args.token_ttl == 0 else "") + ")")
        print(f"  TLS fingerprint: {cert_config.fingerprint}")
        print(f"  mDNS: {'advertising _cc-monitor._tcp on LAN' if not args.no_mdns else 'disabled'}")
        print(f"  Pair devices: open http://127.0.0.1:{args.port} and click 'Pair New Device'")
    print()

    uvicorn.run(_app, **uvicorn_kwargs)


if __name__ == "__main__":
    main()
