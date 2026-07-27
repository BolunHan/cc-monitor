# cc-monitor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python package that monitors Claude Code session state via hooks, serves it through a FastAPI REST API + SSE, and displays it in a browser dashboard.

**Architecture:** Hook scripts (stdlib-only) write state files and POST to a local FastAPI server. The server maintains in-memory state, broadcasts changes via SSE, and restores from disk on startup. A static HTML/JS frontend renders live session cards.

**Tech Stack:** Python 3.13, FastAPI, uvicorn, vanilla HTML/CSS/JS (no framework), SSE (EventSource)

## Global Constraints

- Python >=3.12
- Runtime deps: `fastapi`, `uvicorn`; hook scripts: stdlib only
- Dev deps: `pytest`, `httpx`
- Venv: `~/Projects/venv_313`
- Package layout: `src/cc_monitor/` (src layout)
- Data dir: `~/.cc-monitor/`
- Default port: 9876, host: 127.0.0.1
- States: `idle` | `working` | `pending_approval` | `all_done`

---

### Task 1: Project Scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `src/cc_monitor/__init__.py`
- Create: `tests/__init__.py`

**Interfaces:**
- Produces: `cc_monitor.__version__ = "0.1.0"`

- [ ] **Step 1: Create pyproject.toml**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "cc-monitor"
version = "0.1.0"
description = "Monitor Claude Code working status via hooks"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.30.0",
]
optional-dependencies.dev = [
    "pytest>=8.0",
    "httpx>=0.27.0",
]

[project.scripts]
cc-monitor = "cc_monitor.server:main"

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 2: Create `src/cc_monitor/__init__.py`**

```python
"""Monitor Claude Code working status via hooks."""

__version__ = "0.1.0"
```

- [ ] **Step 3: Create `tests/__init__.py`**

```python
```

- [ ] **Step 4: Install in dev mode and verify**

```bash
cd /home/bolun/Projects/cc-monitor
~/Projects/venv_313/bin/pip install -e ".[dev]"
```

Expected: package installs without error.

- [ ] **Step 5: Verify CLI entry point**

```bash
~/Projects/venv_313/bin/cc-monitor --help 2>&1 || true
```

Expected: errors because server.main doesn't exist yet — that's fine, only verifying the entry point is registered.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml src/cc_monitor/__init__.py tests/__init__.py
git commit -m "chore: scaffold project with pyproject.toml and src layout

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 2: Mapping Module (TDD)

**Files:**
- Create: `src/cc_monitor/mapping.py`
- Create: `tests/test_mapping.py`

**Interfaces:**
- Produces:
  - `class MonitorState(enum.StrEnum)` — `IDLE = "idle"`, `WORKING = "working"`, `PENDING_APPROVAL = "pending_approval"`, `ALL_DONE = "all_done"`
  - `def map_event(hook_event_name: str, notification_type: str | None = None) -> MonitorState`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for cc_monitor.mapping."""

import pytest
from cc_monitor.mapping import MonitorState, map_event


class TestMonitorState:
    def test_enum_values(self):
        assert MonitorState.IDLE == "idle"
        assert MonitorState.WORKING == "working"
        assert MonitorState.PENDING_APPROVAL == "pending_approval"
        assert MonitorState.ALL_DONE == "all_done"

    def test_enum_members(self):
        assert len(MonitorState) == 4


class TestMapEvent:
    # --- WORKING ---
    @pytest.mark.parametrize("event", ["PreToolUse", "PostToolUse", "UserPromptSubmit"])
    def test_tool_events_map_to_working(self, event):
        assert map_event(event) == MonitorState.WORKING

    # --- IDLE ---
    def test_stop_maps_to_idle(self):
        assert map_event("Stop") == MonitorState.IDLE

    def test_notification_idle_prompt_maps_to_idle(self):
        assert map_event("Notification", notification_type="idle_prompt") == MonitorState.IDLE

    # --- PENDING_APPROVAL ---
    def test_permission_request_maps_to_pending_approval(self):
        assert map_event("PermissionRequest") == MonitorState.PENDING_APPROVAL

    def test_notification_permission_prompt_maps_to_pending_approval(self):
        assert map_event("Notification", notification_type="permission_prompt") == MonitorState.PENDING_APPROVAL

    # --- ALL_DONE ---
    def test_session_end_maps_to_all_done(self):
        assert map_event("SessionEnd") == MonitorState.ALL_DONE

    # --- Edge cases ---
    def test_unknown_event_defaults_to_working(self):
        assert map_event("SomeUnknownEvent") == MonitorState.WORKING

    def test_notification_without_type_defaults_to_working(self):
        assert map_event("Notification") == MonitorState.WORKING

    def test_str_enum_comparison(self):
        state = map_event("Stop")
        assert state == "idle"
        assert state == MonitorState.IDLE
```

- [ ] **Step 2: Run test to verify it fails**

```bash
~/Projects/venv_313/bin/pytest tests/test_mapping.py -v
```

Expected: ImportError — `mapping` module doesn't exist yet.

- [ ] **Step 3: Write mapping.py**

```python
"""Map raw Claude Code hook events to MonitorState."""

import enum


class MonitorState(enum.StrEnum):
    """Observable states of a Claude Code session."""

    IDLE = "idle"
    WORKING = "working"
    PENDING_APPROVAL = "pending_approval"
    ALL_DONE = "all_done"


def map_event(hook_event_name: str, notification_type: str | None = None) -> MonitorState:
    """Map a raw hook event to a MonitorState.

    Args:
        hook_event_name: The hook event name from stdin JSON (e.g. "PreToolUse").
        notification_type: For Notification events, the notification_type field
            (e.g. "idle_prompt", "permission_prompt"). None otherwise.

    Returns:
        The mapped MonitorState. Unknown events default to WORKING.
    """
    if hook_event_name in ("PreToolUse", "PostToolUse", "UserPromptSubmit"):
        return MonitorState.WORKING

    if hook_event_name == "Stop":
        return MonitorState.IDLE

    if hook_event_name == "Notification":
        if notification_type == "idle_prompt":
            return MonitorState.IDLE
        if notification_type == "permission_prompt":
            return MonitorState.PENDING_APPROVAL
        return MonitorState.WORKING

    if hook_event_name == "PermissionRequest":
        return MonitorState.PENDING_APPROVAL

    if hook_event_name == "SessionEnd":
        return MonitorState.ALL_DONE

    return MonitorState.WORKING
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
~/Projects/venv_313/bin/pytest tests/test_mapping.py -v
```

Expected: all 11 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/cc_monitor/mapping.py tests/test_mapping.py
git commit -m "feat: add MonitorState enum and map_event mapping

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 3: State Manager (TDD)

**Files:**
- Create: `src/cc_monitor/state.py`
- Create: `tests/test_state.py`

**Interfaces:**
- Produces:
  - `class SessionState` — dataclass: `session_id: str`, `cwd: str`, `state: MonitorState`, `raw_event: str`, `raw_detail: str | None`, `updated_at: datetime`
  - `class StateManager`:
    - `__init__(data_dir: Path = Path.home() / ".cc-monitor")`
    - `async restore() -> None` — load all JSON files from data_dir
    - `async handle_event(raw: dict) -> SessionState` — map + update + persist + broadcast
    - `subscribe() -> asyncio.Queue` — register SSE subscriber
    - `unsubscribe(q: asyncio.Queue) -> None` — remove subscriber
    - `get_all() -> list[SessionState]` — all sessions sorted by updated_at desc
    - `get(session_id: str) -> SessionState | None` — single session
- Consumes:
  - `from cc_monitor.mapping import MonitorState, map_event`

- [ ] **Step 1: Write failing tests**

```python
"""Tests for cc_monitor.state."""

import asyncio
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest
from cc_monitor.mapping import MonitorState
from cc_monitor.state import SessionState, StateManager


class TestSessionState:
    def test_create(self):
        now = datetime.now(timezone.utc)
        s = SessionState(
            session_id="abc-123",
            cwd="/tmp",
            state=MonitorState.WORKING,
            raw_event="PreToolUse",
            raw_detail="Bash",
            updated_at=now,
        )
        assert s.session_id == "abc-123"
        assert s.state == "working"

    def test_to_dict(self):
        now = datetime.now(timezone.utc)
        s = SessionState(
            session_id="abc-123",
            cwd="/tmp",
            state=MonitorState.IDLE,
            raw_event="Stop",
            raw_detail=None,
            updated_at=now,
        )
        d = s.to_dict()
        assert d["session_id"] == "abc-123"
        assert d["state"] == "idle"
        assert d["raw_detail"] is None
        assert "updated_at" in d


class TestStateManager:
    @pytest.fixture
    def tmp_dir(self):
        with tempfile.TemporaryDirectory() as d:
            yield Path(d)

    @pytest.fixture
    def manager(self, tmp_dir):
        return StateManager(data_dir=tmp_dir)

    def _make_event(self, **overrides):
        base = {
            "session_id": "s1",
            "cwd": "/home/user/project",
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
        }
        base.update(overrides)
        return base

    @pytest.mark.asyncio
    async def test_handle_event_creates_session(self, manager, tmp_dir):
        event = self._make_event()
        session = await manager.handle_event(event)

        assert session.session_id == "s1"
        assert session.state == MonitorState.WORKING
        assert session.raw_event == "PreToolUse"
        assert session.raw_detail == "Bash"

        # Verify file was written
        files = list(tmp_dir.glob("*.json"))
        assert len(files) == 1
        assert files[0].name == "s1.json"

        data = json.loads(files[0].read_text())
        assert data["state"] == "working"

    @pytest.mark.asyncio
    async def test_handle_event_updates_existing(self, manager, tmp_dir):
        await manager.handle_event(self._make_event())
        await manager.handle_event(self._make_event(hook_event_name="Stop", tool_name=None))

        session = manager.get("s1")
        assert session.state == MonitorState.IDLE
        assert session.raw_event == "Stop"

    @pytest.mark.asyncio
    async def test_get_all_and_get(self, manager):
        await manager.handle_event(self._make_event(session_id="s1"))
        await manager.handle_event(self._make_event(session_id="s2"))

        all_sessions = manager.get_all()
        assert len(all_sessions) == 2

        s1 = manager.get("s1")
        s2 = manager.get("s2")
        assert s1 is not None
        assert s2 is not None
        assert manager.get("nonexistent") is None

    @pytest.mark.asyncio
    async def test_pending_approval_guards_stop(self, manager):
        # PermissionRequest → PENDING_APPROVAL
        await manager.handle_event(self._make_event(hook_event_name="PermissionRequest", tool_name=None))
        assert manager.get("s1").state == MonitorState.PENDING_APPROVAL

        # Stop should NOT flip back to IDLE while approval is pending
        await manager.handle_event(self._make_event(hook_event_name="Stop", tool_name=None))
        assert manager.get("s1").state == MonitorState.PENDING_APPROVAL

        # UserPromptSubmit clears the guard → WORKING
        await manager.handle_event(self._make_event(hook_event_name="UserPromptSubmit", tool_name=None))
        assert manager.get("s1").state == MonitorState.WORKING

    @pytest.mark.asyncio
    async def test_restore_from_disk(self, tmp_dir):
        # Write a state file manually
        state_file = tmp_dir / "old-session.json"
        state_file.write_text(json.dumps({
            "session_id": "old-session",
            "cwd": "/old/project",
            "state": "all_done",
            "raw_event": "SessionEnd",
            "raw_detail": None,
            "updated_at": "2026-07-27T00:00:00.000000Z",
        }))

        # Create a fresh manager pointing at same dir
        manager = StateManager(data_dir=tmp_dir)
        await manager.restore()

        session = manager.get("old-session")
        assert session is not None
        assert session.state == MonitorState.ALL_DONE
        assert session.cwd == "/old/project"

    @pytest.mark.asyncio
    async def test_restore_skips_invalid_json(self, tmp_dir):
        (tmp_dir / "bad.json").write_text("not json")
        (tmp_dir / "good.json").write_text(json.dumps({
            "session_id": "good",
            "cwd": "/proj",
            "state": "idle",
            "raw_event": "Stop",
            "raw_detail": None,
            "updated_at": "2026-07-27T00:00:00.000000Z",
        }))

        manager = StateManager(data_dir=tmp_dir)
        await manager.restore()

        assert manager.get("good") is not None
        assert manager.get("bad.json") is None  # file stem used as id for valid files only

    @pytest.mark.asyncio
    async def test_sse_subscribe_and_broadcast(self, manager):
        queue = manager.subscribe()
        assert isinstance(queue, asyncio.Queue)

        await manager.handle_event(self._make_event())

        # Should receive the broadcast
        msg = await asyncio.wait_for(queue.get(), timeout=1.0)
        assert msg["session_id"] == "s1"
        assert msg["state"] == "working"

        # Unsubscribe
        manager.unsubscribe(queue)
        await manager.handle_event(self._make_event(hook_event_name="Stop", tool_name=None))

        # Queue should be empty (unsubscribed — but actually the queue
        # still exists, it's just not in the broadcast list anymore)
        assert queue.empty()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
~/Projects/venv_313/bin/pytest tests/test_state.py -v
```

Expected: ImportError — `state` module doesn't exist yet.

- [ ] **Step 3: Write state.py**

```python
"""Session state management — in-memory store, file persistence, SSE fan-out."""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from cc_monitor.mapping import MonitorState, map_event

logger = logging.getLogger(__name__)


@dataclass
class SessionState:
    """The current state of one Claude Code session."""

    session_id: str
    cwd: str
    state: MonitorState
    raw_event: str
    raw_detail: str | None
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "cwd": self.cwd,
            "state": str(self.state),
            "raw_event": self.raw_event,
            "raw_detail": self.raw_detail,
            "updated_at": self.updated_at.isoformat(),
        }


class StateManager:
    """Manages session states in memory and on disk, with SSE broadcast.

    On startup, restore() loads all state files from data_dir.
    Events update state, write the file, and broadcast to SSE subscribers.
    """

    def __init__(self, data_dir: Path | None = None):
        self._data_dir = data_dir or Path.home() / ".cc-monitor"
        self._sessions: dict[str, SessionState] = {}
        self._pending_approval: set[str] = set()
        self._queues: list[asyncio.Queue] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def restore(self) -> None:
        """Load all state JSON files from data_dir into memory."""
        self._data_dir.mkdir(parents=True, exist_ok=True)
        for file_path in self._data_dir.glob("*.json"):
            try:
                data = json.loads(file_path.read_text())
                session = SessionState(
                    session_id=data["session_id"],
                    cwd=data["cwd"],
                    state=MonitorState(data["state"]),
                    raw_event=data["raw_event"],
                    raw_detail=data.get("raw_detail"),
                    updated_at=datetime.fromisoformat(data["updated_at"]),
                )
                self._sessions[session.session_id] = session
                if session.state == MonitorState.PENDING_APPROVAL:
                    self._pending_approval.add(session.session_id)
            except (json.JSONDecodeError, KeyError, ValueError) as exc:
                logger.warning("Skipping invalid state file %s: %s", file_path.name, exc)

    async def handle_event(self, raw: dict) -> SessionState:
        """Process a raw hook event: map state, update store, persist, broadcast.

        Args:
            raw: The full hook event JSON from stdin, with at minimum:
                session_id, cwd, hook_event_name.

        Returns:
            The updated SessionState.
        """
        session_id = raw.get("session_id", "unknown")
        hook_event_name = raw.get("hook_event_name", "")
        notification_type = raw.get("notification_type")
        tool_name = raw.get("tool_name")

        new_state = map_event(hook_event_name, notification_type)

        # --- pending_approval guard ---
        if new_state == MonitorState.PENDING_APPROVAL:
            self._pending_approval.add(session_id)
        elif hook_event_name != "Stop" and session_id in self._pending_approval:
            # A non-Stop event after approval was pending — user resolved it
            self._pending_approval.discard(session_id)

        # If Stop fires while approval is pending, keep pending_approval
        if hook_event_name == "Stop" and session_id in self._pending_approval:
            existing = self._sessions.get(session_id)
            if existing:
                existing.raw_event = "Stop"
                existing.raw_detail = None
                existing.updated_at = datetime.now(timezone.utc)
                return existing
            # No existing session — create as idle anyway (edge case)
            new_state = MonitorState.IDLE

        # --- update ---
        session = SessionState(
            session_id=session_id,
            cwd=raw.get("cwd", ""),
            state=new_state,
            raw_event=hook_event_name,
            raw_detail=tool_name,
        )
        self._sessions[session_id] = session

        # --- persist ---
        self._write_file(session)

        # --- broadcast ---
        await self._broadcast(session)

        return session

    def get_all(self) -> list[SessionState]:
        """Return all sessions, most recently updated first."""
        return sorted(
            self._sessions.values(),
            key=lambda s: s.updated_at,
            reverse=True,
        )

    def get(self, session_id: str) -> SessionState | None:
        """Return a single session by ID, or None."""
        return self._sessions.get(session_id)

    def subscribe(self) -> asyncio.Queue:
        """Register a new SSE subscriber. Returns a queue to iterate on."""
        q: asyncio.Queue = asyncio.Queue()
        self._queues.append(q)
        return q

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        """Remove an SSE subscriber."""
        try:
            self._queues.remove(queue)
        except ValueError:
            pass

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _write_file(self, session: SessionState) -> None:
        """Persist session state to disk."""
        self._data_dir.mkdir(parents=True, exist_ok=True)
        file_path = self._data_dir / f"{session.session_id}.json"
        file_path.write_text(json.dumps(session.to_dict(), indent=2))

    async def _broadcast(self, session: SessionState) -> None:
        """Send a state_update event to all SSE subscribers."""
        payload = session.to_dict()
        dead: list[asyncio.Queue] = []
        for q in self._queues:
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                dead.append(q)
        for q in dead:
            self.unsubscribe(q)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
~/Projects/venv_313/bin/pytest tests/test_state.py -v
```

Expected: all 8 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/cc_monitor/state.py tests/test_state.py
git commit -m "feat: add StateManager with file persistence and SSE broadcast

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 4: Server + CLI (TDD)

**Files:**
- Create: `src/cc_monitor/server.py`

**Interfaces:**
- Produces:
  - FastAPI app at module level (`app`)
  - `POST /api/event` — receive raw hook event
  - `GET /api/status` — all sessions
  - `GET /api/status/{session_id}` — single session
  - `GET /api/stream` — SSE endpoint
  - `GET /` — serve index.html
  - `def main() -> None` — CLI entry point, runs uvicorn
- Consumes:
  - `from cc_monitor.state import StateManager`

- [ ] **Step 1: Write failing test**

```python
"""Tests for cc_monitor.server."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from cc_monitor.server import app, create_app


@pytest.fixture
def tmp_data_dir(tmp_path):
    return tmp_path


@pytest.fixture
def test_app(tmp_data_dir):
    app = create_app(data_dir=tmp_data_dir)
    return app


@pytest.mark.asyncio
async def test_post_event_creates_session(test_app, tmp_data_dir):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/event", json={
            "session_id": "test-session",
            "cwd": "/home/user/test",
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
        })

    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"] == "test-session"
    assert data["state"] == "working"

    # Verify file was written
    state_file = tmp_data_dir / "test-session.json"
    assert state_file.exists()
    assert json.loads(state_file.read_text())["state"] == "working"


@pytest.mark.asyncio
async def test_get_all_status(test_app, tmp_data_dir):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/api/event", json={
            "session_id": "s1",
            "cwd": "/a",
            "hook_event_name": "Stop",
        })
        await client.post("/api/event", json={
            "session_id": "s2",
            "cwd": "/b",
            "hook_event_name": "PreToolUse",
            "tool_name": "Write",
        })
        resp = await client.get("/api/status")

    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 2
    assert len(data["sessions"]) == 2


@pytest.mark.asyncio
async def test_get_single_status(test_app, tmp_data_dir):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/api/event", json={
            "session_id": "s1",
            "cwd": "/a",
            "hook_event_name": "Stop",
        })
        resp = await client.get("/api/status/s1")

    assert resp.status_code == 200
    assert resp.json()["session_id"] == "s1"
    assert resp.json()["state"] == "idle"


@pytest.mark.asyncio
async def test_get_single_status_404(test_app):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/status/nonexistent")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_index_html_served(test_app):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/")

    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


@pytest.mark.asyncio
async def test_static_files_served(test_app):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/static/css/app.css")

    assert resp.status_code == 200
    assert "text/css" in resp.headers["content-type"]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
~/Projects/venv_313/bin/pytest tests/test_server.py -v
```

Expected: ImportError — server module doesn't exist or create_app is missing.

- [ ] **Step 3: Write server.py**

```python
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

    # ---- Static files ----

    @app.get("/", response_class=HTMLResponse)
    async def index():
        """Serve the dashboard."""
        index_path = _STATIC_DIR / "index.html"
        if not index_path.exists():
            return HTMLResponse("<h1>cc-monitor</h1><p>static/index.html not found.</p>")
        return HTMLResponse(index_path.read_text())

    if (_STATIC_DIR / "css").exists():
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
~/Projects/venv_313/bin/pytest tests/test_server.py -v
```

Expected: all 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/cc_monitor/server.py tests/test_server.py
git commit -m "feat: add FastAPI server with REST API, SSE, and CLI entry point

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 5: Hook Scripts

**Files:**
- Create: `hooks/_common.py`
- Create: `hooks/pre_tool_use.py`
- Create: `hooks/post_tool_use.py`
- Create: `hooks/user_prompt_submit.py`
- Create: `hooks/stop.py`
- Create: `hooks/notification.py`
- Create: `hooks/permission_request.py`
- Create: `hooks/session_end.py`

**Interfaces:**
- Produces: Self-contained Python scripts that read stdin JSON, write state file, POST to server.
- Each script is a thin wrapper: it imports `_common.run_hook(hook_event_name)`.

- [ ] **Step 1: Write `hooks/_common.py` — shared utilities**

```python
"""Shared utilities for cc-monitor hook scripts (stdlib only, no deps).

This module is intentionally self-contained — it does NOT import from the
cc_monitor package, so hook scripts work regardless of venv state.
"""

import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path.home() / ".cc-monitor"
SERVER_URL = "http://localhost:9876/api/event"


def map_event(hook_event_name: str, notification_type: str | None = None) -> str:
    """Map a raw hook event to a state string.

    Duplicated here so hook scripts don't depend on cc_monitor.mapping.
    Keep in sync with src/cc_monitor/mapping.py.
    """
    if hook_event_name in ("PreToolUse", "PostToolUse", "UserPromptSubmit"):
        return "working"
    if hook_event_name == "Stop":
        return "idle"
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
    """POST the raw hook event to the server. Returns True on success."""
    try:
        body = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(
            SERVER_URL,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=2)
        return True
    except Exception:
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

    session_id = data.get("session_id", "unknown")
    write_state_file(session_id, data)
    notify_server(data)
```

- [ ] **Step 2: Write hook scripts**

`hooks/pre_tool_use.py`:
```python
#!/usr/bin/env python3
"""Hook for PreToolUse — marks session as working."""
from _common import run_hook
run_hook("PreToolUse")
```

`hooks/post_tool_use.py`:
```python
#!/usr/bin/env python3
"""Hook for PostToolUse — marks session as working."""
from _common import run_hook
run_hook("PostToolUse")
```

`hooks/user_prompt_submit.py`:
```python
#!/usr/bin/env python3
"""Hook for UserPromptSubmit — marks session as working."""
from _common import run_hook
run_hook("UserPromptSubmit")
```

`hooks/stop.py`:
```python
#!/usr/bin/env python3
"""Hook for Stop — marks session as idle."""
from _common import run_hook
run_hook("Stop")
```

`hooks/notification.py`:
```python
#!/usr/bin/env python3
"""Hook for Notification — marks session based on notification_type."""
from _common import run_hook
run_hook("Notification")
```

`hooks/permission_request.py`:
```python
#!/usr/bin/env python3
"""Hook for PermissionRequest — marks session as pending_approval."""
from _common import run_hook
run_hook("PermissionRequest")
```

`hooks/session_end.py`:
```python
#!/usr/bin/env python3
"""Hook for SessionEnd — marks session as all_done."""
from _common import run_hook
run_hook("SessionEnd")
```

- [ ] **Step 3: Verify hook scripts work standalone**

```bash
cd /home/bolun/Projects/cc-monitor
echo '{"session_id":"test-123","cwd":"/tmp","hook_event_name":"PreToolUse","tool_name":"Bash"}' | python3 hooks/pre_tool_use.py
cat ~/.cc-monitor/test-123.json
```

Expected: JSON file at `~/.cc-monitor/test-123.json` with `"state": "working"`.

- [ ] **Step 4: Commit**

```bash
git add hooks/
git commit -m "feat: add self-contained hook scripts for all 7 hook events

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 6: Static Frontend

**Files:**
- Create: `static/index.html`
- Create: `static/css/app.css`
- Create: `static/js/app.js`

**Interfaces:**
- Produces: Browser dashboard that connects via SSE to `/api/stream` and renders session state cards.

- [ ] **Step 1: Write `static/index.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>cc-monitor</title>
    <link rel="stylesheet" href="/static/css/app.css">
</head>
<body>
    <header class="header">
        <h1 class="header__title">cc-monitor</h1>
        <div class="header__status">
            <span class="connection-indicator" id="connection-indicator" title="SSE connection status"></span>
            <span class="connection-label" id="connection-label">connecting</span>
        </div>
    </header>

    <main class="main">
        <div class="session-grid" id="session-grid">
            <p class="empty-state" id="empty-state">No active sessions. Start a Claude Code session to see it here.</p>
        </div>
    </main>

    <script src="/static/js/app.js"></script>
</body>
</html>
```

- [ ] **Step 2: Write `static/css/app.css`**

```css
:root {
    --color-bg: #0f1117;
    --color-surface: #1a1d27;
    --color-border: #2a2d3a;
    --color-text: #e1e4ed;
    --color-text-muted: #8b8fa3;
    --color-idle: #6b7280;
    --color-working: #3b82f6;
    --color-pending: #f59e0b;
    --color-done: #22c55e;
    --color-connected: #22c55e;
    --color-disconnected: #ef4444;
    --radius: 8px;
    --shadow: 0 1px 3px rgba(0, 0, 0, 0.3);
}

*, *::before, *::after {
    box-sizing: border-box;
    margin: 0;
    padding: 0;
}

body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: var(--color-bg);
    color: var(--color-text);
    min-height: 100vh;
}

.header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 16px 24px;
    border-bottom: 1px solid var(--color-border);
    background: var(--color-surface);
}

.header__title {
    font-size: 20px;
    font-weight: 600;
}

.header__status {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 13px;
    color: var(--color-text-muted);
}

.connection-indicator {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--color-disconnected);
    transition: background 0.3s;
}

.connection-indicator.connected {
    background: var(--color-connected);
}

.main {
    padding: 24px;
}

.session-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
    gap: 16px;
}

.empty-state {
    grid-column: 1 / -1;
    text-align: center;
    color: var(--color-text-muted);
    padding: 48px 0;
    font-size: 15px;
}

.session-card {
    background: var(--color-surface);
    border: 1px solid var(--color-border);
    border-radius: var(--radius);
    padding: 16px;
    box-shadow: var(--shadow);
    transition: border-color 0.2s;
}

.session-card:hover {
    border-color: var(--color-text-muted);
}

.session-card__header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: 12px;
}

.session-card__id {
    font-family: "SF Mono", "Fira Code", monospace;
    font-size: 13px;
    color: var(--color-text-muted);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    max-width: 200px;
}

.session-card__badge {
    font-size: 12px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    padding: 2px 8px;
    border-radius: 4px;
    flex-shrink: 0;
}

.badge-idle {
    background: color-mix(in srgb, var(--color-idle) 20%, transparent);
    color: var(--color-idle);
}

.badge-working {
    background: color-mix(in srgb, var(--color-working) 20%, transparent);
    color: var(--color-working);
    animation: pulse 2s ease-in-out infinite;
}

.badge-pending_approval {
    background: color-mix(in srgb, var(--color-pending) 20%, transparent);
    color: var(--color-pending);
    animation: pulse 1s ease-in-out infinite;
}

.badge-all_done {
    background: color-mix(in srgb, var(--color-done) 20%, transparent);
    color: var(--color-done);
}

@keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.6; }
}

.session-card__detail {
    font-size: 13px;
    color: var(--color-text-muted);
    line-height: 1.5;
}

.session-card__detail strong {
    color: var(--color-text);
    font-weight: 500;
}

.session-card__time {
    margin-top: 8px;
    font-size: 12px;
    color: var(--color-text-muted);
}
```

- [ ] **Step 3: Write `static/js/app.js`**

```javascript
/**
 * cc-monitor dashboard — SSE client that renders session state cards.
 */
(() => {
    const grid = document.getElementById("session-grid");
    const emptyState = document.getElementById("empty-state");
    const indicator = document.getElementById("connection-indicator");
    const label = document.getElementById("connection-label");
    const cards = new Map(); // session_id -> HTMLElement

    function setConnected(state) {
        indicator.classList.toggle("connected", state);
        label.textContent = state ? "connected" : "disconnected";
    }

    function relativeTime(isoString) {
        const then = new Date(isoString);
        const now = new Date();
        const seconds = Math.floor((now - then) / 1000);
        if (seconds < 5) return "just now";
        if (seconds < 60) return `${seconds}s ago`;
        const minutes = Math.floor(seconds / 60);
        if (minutes < 60) return `${minutes}m ago`;
        const hours = Math.floor(minutes / 60);
        return `${hours}h ago`;
    }

    function createCard(session) {
        const card = document.createElement("div");
        card.className = "session-card";
        card.id = `card-${session.session_id}`;
        card.innerHTML = `
            <div class="session-card__header">
                <span class="session-card__id" title="${session.session_id}">
                    ${session.session_id.substring(0, 8)}...
                </span>
                <span class="session-card__badge badge-${session.state}">
                    ${session.state.replace("_", " ")}
                </span>
            </div>
            <div class="session-card__detail">
                <strong>cwd:</strong> ${escapeHtml(session.cwd || "—")}<br>
                <strong>event:</strong> ${escapeHtml(session.raw_event || "—")}
                ${session.raw_detail ? ` (${escapeHtml(session.raw_detail)})` : ""}
            </div>
            <div class="session-card__time">${relativeTime(session.updated_at)}</div>
        `;
        return card;
    }

    function escapeHtml(str) {
        const el = document.createElement("span");
        el.textContent = str;
        return el.innerHTML;
    }

    function updateCard(session) {
        const card = createCard(session);
        const existing = cards.get(session.session_id);
        if (existing) {
            existing.replaceWith(card);
        } else {
            grid.appendChild(card);
            emptyState.style.display = "none";
        }
        cards.set(session.session_id, card);
    }

    function connect() {
        const es = new EventSource("/api/stream");

        es.addEventListener("state_update", (e) => {
            try {
                const session = JSON.parse(e.data);
                updateCard(session);
            } catch (err) {
                console.error("cc-monitor: failed to parse SSE data", err);
            }
        });

        es.addEventListener("open", () => setConnected(true));
        es.addEventListener("error", () => {
            setConnected(false);
            // EventSource auto-reconnects
        });
    }

    // Initial load — fetch existing sessions
    fetch("/api/status")
        .then(r => r.json())
        .then(data => {
            if (data.sessions && data.sessions.length > 0) {
                data.sessions.forEach(updateCard);
            }
        })
        .catch(() => {});

    connect();
})();
```

- [ ] **Step 4: Commit**

```bash
git add static/
git commit -m "feat: add minimal dashboard frontend with SSE live updates

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 7: Settings.json + README

**Files:**
- Create: `.claude/settings.json`
- Modify: `README.md`

**Interfaces:**
- Produces: Project hooks config for dogfooding + usage documentation.

- [ ] **Step 1: Write `.claude/settings.json`**

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "python3 /home/bolun/Projects/cc-monitor/hooks/pre_tool_use.py",
            "description": "cc-monitor: mark session as working"
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "python3 /home/bolun/Projects/cc-monitor/hooks/post_tool_use.py",
            "description": "cc-monitor: mark session as working"
          }
        ]
      }
    ],
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 /home/bolun/Projects/cc-monitor/hooks/user_prompt_submit.py",
            "description": "cc-monitor: mark session as working"
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 /home/bolun/Projects/cc-monitor/hooks/stop.py",
            "description": "cc-monitor: mark session as idle"
          }
        ]
      }
    ],
    "Notification": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "python3 /home/bolun/Projects/cc-monitor/hooks/notification.py",
            "description": "cc-monitor: handle notification events"
          }
        ]
      }
    ],
    "PermissionRequest": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "python3 /home/bolun/Projects/cc-monitor/hooks/permission_request.py",
            "description": "cc-monitor: mark session as pending approval"
          }
        ]
      }
    ],
    "SessionEnd": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 /home/bolun/Projects/cc-monitor/hooks/session_end.py",
            "description": "cc-monitor: mark session as all done"
          }
        ]
      }
    ]
  }
}
```

- [ ] **Step 2: Write README.md**

```markdown
# cc-monitor

Monitor Claude Code working status via hooks — see which sessions are idle, working, pending approval, or done, in a local browser dashboard.

## Install

```bash
cd cc-monitor
pip install -e ".[dev]"
```

## Usage

**1. Start the server:**

```bash
cc-monitor server --port 9876
```

**2. Open the dashboard:**

[http://localhost:9876](http://localhost:9876)

**3. Configure hooks in your `~/.claude/settings.json`:**

Copy the hook entries from `.claude/settings.json` in this repo, adjusting paths to point at the installed hook scripts.

## States

| State | Meaning |
|-------|---------|
| `working` | Claude is actively processing — executing tools, generating output |
| `idle` | Claude is waiting for your input |
| `pending_approval` | Claude needs permission to proceed (PermissionRequest or permission prompt) |
| `all_done` | Session has ended |

## API

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/event` | Submit a raw hook event |
| `GET` | `/api/status` | All sessions' current states |
| `GET` | `/api/status/<id>` | Single session state |
| `GET` | `/api/stream` | SSE stream of state updates |

## Architecture

Hook scripts (stdlib-only Python) write `~/.cc-monitor/<session_id>.json` files and POST to the server. The FastAPI server holds in-memory state, broadcasts changes via SSE, and restores state from disk on startup.
```

- [ ] **Step 3: Commit**

```bash
git add .claude/settings.json README.md
git commit -m "docs: add hooks config and README

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 8: Integration Test + Final Verification

**Files:**
- Create: `tests/test_integration.py`

- [ ] **Step 1: Write integration test**

```python
"""Integration tests for cc-monitor — full hook→server→SSE pipeline."""

import asyncio
import json

import pytest
from httpx import ASGITransport, AsyncClient

from cc_monitor.server import create_app


@pytest.fixture
def tmp_data_dir(tmp_path):
    return tmp_path


@pytest.fixture
def test_app(tmp_data_dir):
    return create_app(data_dir=tmp_data_dir)


@pytest.mark.asyncio
async def test_full_lifecycle(test_app, tmp_data_dir):
    """Simulate: start → working → pending approval → done."""
    transport = ASGITransport(app=test_app)
    events = [
        {"session_id": "lifecycle", "cwd": "/project", "hook_event_name": "UserPromptSubmit"},
        {"session_id": "lifecycle", "cwd": "/project", "hook_event_name": "PreToolUse", "tool_name": "Read"},
        {"session_id": "lifecycle", "cwd": "/project", "hook_event_name": "PostToolUse", "tool_name": "Read"},
        {"session_id": "lifecycle", "cwd": "/project", "hook_event_name": "PermissionRequest"},
        {"session_id": "lifecycle", "cwd": "/project", "hook_event_name": "Stop"},
        {"session_id": "lifecycle", "cwd": "/project", "hook_event_name": "UserPromptSubmit"},
        {"session_id": "lifecycle", "cwd": "/project", "hook_event_name": "PreToolUse", "tool_name": "Write"},
        {"session_id": "lifecycle", "cwd": "/project", "hook_event_name": "SessionEnd"},
    ]

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # ---- UserPromptSubmit → WORKING ----
        resp = await client.post("/api/event", json=events[0])
        assert resp.json()["state"] == "working"

        # ---- PreToolUse → WORKING ----
        resp = await client.post("/api/event", json=events[1])
        assert resp.json()["state"] == "working"

        # ---- PostToolUse → WORKING ----
        resp = await client.post("/api/event", json=events[2])
        assert resp.json()["state"] == "working"

        # ---- PermissionRequest → PENDING_APPROVAL ----
        resp = await client.post("/api/event", json=events[3])
        assert resp.json()["state"] == "pending_approval"

        # ---- Stop should NOT flip pending_approval ----
        resp = await client.post("/api/event", json=events[4])
        assert resp.json()["state"] == "pending_approval"

        # ---- UserPromptSubmit clears guard → WORKING ----
        resp = await client.post("/api/event", json=events[5])
        assert resp.json()["state"] == "working"

        # ---- PreToolUse → WORKING ----
        resp = await client.post("/api/event", json=events[6])
        assert resp.json()["state"] == "working"

        # ---- SessionEnd → ALL_DONE ----
        resp = await client.post("/api/event", json=events[7])
        assert resp.json()["state"] == "all_done"

        # ---- Verify final status ----
        resp = await client.get("/api/status")
        data = resp.json()
        assert data["count"] == 1
        assert data["sessions"][0]["state"] == "all_done"

    # ---- Verify file persistence ----
    state_file = tmp_data_dir / "lifecycle.json"
    assert state_file.exists()
    assert json.loads(state_file.read_text())["state"] == "all_done"


@pytest.mark.asyncio
async def test_sse_stream_receives_events(test_app, tmp_data_dir):
    """Verify SSE subscribers receive state_update events."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Start SSE stream
        async with client.stream("GET", "/api/stream") as stream:
            # Give the stream a moment to establish
            await asyncio.sleep(0.05)

            # Post an event
            await client.post("/api/event", json={
                "session_id": "sse-test",
                "cwd": "/p",
                "hook_event_name": "PreToolUse",
                "tool_name": "Bash",
            })

            # Read SSE response
            lines = []
            try:
                async for line in stream.aiter_lines():
                    lines.append(line)
                    if "state_update" in line:
                        break
            except Exception:
                pass

            sse_text = "\n".join(lines)
            assert "event: state_update" in sse_text
            assert "sse-test" in sse_text
            assert "working" in sse_text
```

- [ ] **Step 2: Run integration tests**

```bash
~/Projects/venv_313/bin/pytest tests/test_integration.py -v
```

Expected: 2 tests PASS.

- [ ] **Step 3: Run all tests**

```bash
~/Projects/venv_313/bin/pytest tests/ -v
```

Expected: all tests PASS (11 mapping + 8 state + 6 server + 2 integration = 27 tests).

- [ ] **Step 4: Commit**

```bash
git add tests/test_integration.py
git commit -m "test: add integration tests for full lifecycle and SSE

Co-Authored-By: Claude <noreply@anthropic.com>"
```
