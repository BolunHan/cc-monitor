"""FastAPI server for cc-monitor — REST API + SSE + static dashboard."""

import argparse
import asyncio
import json
import logging
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


_STATIC_DIR = Path(__file__).resolve().parent.parent.parent / "static"
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_SOURCE_HOOKS_PATH = _PROJECT_ROOT / ".claude" / "settings.json"
_GLOBAL_SETTINGS_PATH = Path.home() / ".claude" / "settings.json"
_BACKUP_PATH = Path.home() / ".claude" / "settings.json.cc-monitor.bak"


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

    Returns:
        A configured FastAPI application.
    """
    app = FastAPI(title="cc-monitor", version=__version__)
    _data_dir = data_dir or Path.home() / ".cc-monitor"
    manager = StateManager(data_dir=data_dir)

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
        """Return the cc-monitor server version."""
        return JSONResponse({"version": __version__})

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

    _hook_event_names: set[str] = set()

    def _load_source_hooks() -> dict:
        """Load hook definitions from the project's .claude/settings.json."""
        if not _SOURCE_HOOKS_PATH.exists():
            raise HTTPException(
                status_code=500,
                detail=f"Source hooks file not found: {_SOURCE_HOOKS_PATH}",
            )
        try:
            source = json.loads(_SOURCE_HOOKS_PATH.read_text())
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Invalid JSON in source hooks: {exc}",
            )
        hooks = source.get("hooks", {})
        if not hooks:
            raise HTTPException(status_code=500, detail="No hooks found in source settings")
        return hooks

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

    # Populate known event names from source at startup
    try:
        _hook_event_names = set(_load_source_hooks().keys())
    except Exception:
        pass

    @app.get("/api/hooks-status")
    async def hooks_status():
        """Check whether cc-monitor hooks are installed globally."""
        try:
            global_settings = _load_global_settings()
        except HTTPException:
            return JSONResponse({"installed": False, "error": "cannot read global settings"})

        global_hooks = global_settings.get("hooks", {})
        installed_events = []
        missing_events = []
        for event_name in _hook_event_names:
            if event_name in global_hooks:
                installed_events.append(event_name)
            else:
                missing_events.append(event_name)

        return JSONResponse({
            "installed": len(missing_events) == 0 and len(installed_events) > 0,
            "installed_events": installed_events,
            "missing_events": missing_events,
            "target": str(_GLOBAL_SETTINGS_PATH),
        })

    @app.post("/api/install-hooks")
    async def install_hooks():
        """Inject cc-monitor hooks into the global Claude Code settings.

        Creates a backup of the existing global settings before modifying.
        Merges hooks into ~/.claude/settings.json, preserving all
        existing non-cc-monitor settings and hooks.
        """
        source_hooks = _load_source_hooks()
        target = _load_global_settings()

        # Create backup before modifying
        if _GLOBAL_SETTINGS_PATH.exists():
            _BACKUP_PATH.write_text(json.dumps(target, indent=2))
            logger.info("Backed up global settings to %s", _BACKUP_PATH)

        # Deep-merge: replace cc-monitor hook events, preserve others
        target_hooks = target.get("hooks", {})
        merged_count = 0
        for event_name, matcher_groups in source_hooks.items():
            merged_count += 1
            target_hooks[event_name] = matcher_groups

        target["hooks"] = target_hooks
        _save_global_settings(target)

        logger.info(
            "Installed %d cc-monitor hook events into %s",
            merged_count,
            _GLOBAL_SETTINGS_PATH,
        )

        return JSONResponse({
            "status": "ok",
            "installed_events": merged_count,
            "target": str(_GLOBAL_SETTINGS_PATH),
            "backup": str(_BACKUP_PATH) if _BACKUP_PATH.exists() else None,
        })

    @app.post("/api/uninstall-hooks")
    async def uninstall_hooks():
        """Remove cc-monitor hooks from the global Claude Code settings.

        Only removes hook events that match the project's source hooks.
        All other settings and hooks are preserved.
        """
        target = _load_global_settings()
        target_hooks = target.get("hooks", {})

        removed_count = 0
        for event_name in _hook_event_names:
            if event_name in target_hooks:
                del target_hooks[event_name]
                removed_count += 1

        target["hooks"] = target_hooks
        _save_global_settings(target)

        logger.info(
            "Uninstalled %d cc-monitor hook events from %s",
            removed_count,
            _GLOBAL_SETTINGS_PATH,
        )

        return JSONResponse({
            "status": "ok",
            "removed_events": removed_count,
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
    args = parser.parse_args()

    import uvicorn

    data_dir = Path(args.data_dir) if args.data_dir else None
    _data_dir = data_dir or Path.home() / ".cc-monitor"

    # Handle --revoke-all
    if args.revoke_all:
        tm = TokenManager(data_dir=_data_dir)
        count = tm.revoke_all()
        print(f"Revoked {count} token(s).")
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
