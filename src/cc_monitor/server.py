"""FastAPI server for cc-monitor — REST API + SSE + static dashboard."""

import argparse
import asyncio
import json
import logging
from pathlib import Path

from cc_monitor import __version__
from cc_monitor.state import StateManager
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

logger = logging.getLogger(__name__)

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


def create_app(data_dir: Path | None = None) -> FastAPI:
    """Build the FastAPI app with a given data directory.

    Args:
        data_dir: Where session state files are stored. Defaults to
            ~/.cc-monitor.

    Returns:
        A configured FastAPI application.
    """
    app = FastAPI(title="cc-monitor", version=__version__)
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
                        payload = await asyncio.wait_for(queue.get(), timeout=3.0)
                        yield _format_sse_event("state_update", json.dumps(payload))
                    except asyncio.TimeoutError:
                        yield _format_sse_event("heartbeat", json.dumps({"ts": asyncio.get_event_loop().time()}))
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
    args = parser.parse_args()

    import uvicorn

    data_dir = Path(args.data_dir) if args.data_dir else None
    _app = create_app(data_dir=data_dir)

    uvicorn.run(_app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
