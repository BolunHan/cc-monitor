"""FastAPI server for cc-monitor — REST API + SSE + static dashboard."""

import argparse
import asyncio
import json
import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from cc_monitor.state import StateManager

logger = logging.getLogger(__name__)

_STATIC_DIR = Path(__file__).resolve().parent.parent.parent / "static"
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_SOURCE_HOOKS_PATH = _PROJECT_ROOT / ".claude" / "settings.json"
_GLOBAL_SETTINGS_PATH = Path.home() / ".claude" / "settings.json"


def create_app(data_dir: Path | None = None) -> FastAPI:
    """Build the FastAPI app with a given data directory.

    Args:
        data_dir: Where session state files are stored. Defaults to
            ~/.cc-monitor.

    Returns:
        A configured FastAPI application.
    """
    app = FastAPI(title="cc-monitor", version="0.1.0")
    manager = StateManager(data_dir=data_dir)

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
                        payload = await asyncio.wait_for(queue.get(), timeout=30.0)
                        yield f"event: state_update\ndata: {json.dumps(payload)}\n\n"
                    except asyncio.TimeoutError:
                        yield ": keepalive\n\n"
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

    # ---- Hook installation ----

    @app.post("/api/install-hooks")
    async def install_hooks():
        """Inject cc-monitor hooks into the global Claude Code settings.

        Reads the project's .claude/settings.json as the hook source,
        merges hooks into ~/.claude/settings.json, preserving all
        existing non-cc-monitor settings and hooks.
        """
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

        source_hooks = source.get("hooks", {})
        if not source_hooks:
            raise HTTPException(status_code=500, detail="No hooks found in source settings")

        # Read or init the global settings
        target: dict = {}
        if _GLOBAL_SETTINGS_PATH.exists():
            try:
                target = json.loads(_GLOBAL_SETTINGS_PATH.read_text())
            except json.JSONDecodeError as exc:
                raise HTTPException(
                    status_code=500,
                    detail=f"Invalid JSON in {_GLOBAL_SETTINGS_PATH}: {exc}",
                )

        # Deep-merge: replace cc-monitor hook events, preserve others
        target_hooks = target.get("hooks", {})
        merged_count = 0
        for event_name, matcher_groups in source_hooks.items():
            merged_count += 1
            target_hooks[event_name] = matcher_groups

        target["hooks"] = target_hooks

        # Write back
        _GLOBAL_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        _GLOBAL_SETTINGS_PATH.write_text(json.dumps(target, indent=2))

        logger.info(
            "Installed %d cc-monitor hook events into %s",
            merged_count,
            _GLOBAL_SETTINGS_PATH,
        )

        return JSONResponse({
            "status": "ok",
            "installed_events": merged_count,
            "target": str(_GLOBAL_SETTINGS_PATH),
        })

    # ---- Static files ----

    @app.get("/", response_class=HTMLResponse)
    async def index():
        """Serve the dashboard."""
        index_path = _STATIC_DIR / "index.html"
        if not index_path.exists():
            return HTMLResponse("<h1>cc-monitor</h1><p>static/index.html not found.</p>")
        return HTMLResponse(index_path.read_text())

    if _STATIC_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

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
