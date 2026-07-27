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
