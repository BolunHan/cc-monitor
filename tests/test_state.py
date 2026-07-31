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

        # Verify file was written to session dir
        session_file = tmp_dir / "s1" / "session.json"
        assert session_file.exists()

        data = json.loads(session_file.read_text())
        assert data["state"] == "working"

    @pytest.mark.asyncio
    async def test_handle_event_updates_existing(self, manager, tmp_dir):
        await manager.handle_event(self._make_event())
        await manager.handle_event(self._make_event(hook_event_name="Stop", tool_name=None))

        session = manager.get("s1")
        assert session.state == MonitorState.PENDING_REVIEW
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
        # Write a session dir manually
        session_dir = tmp_dir / "old-session"
        session_dir.mkdir()
        (session_dir / "session.json").write_text(json.dumps({
            "session_id": "old-session",
            "cwd": "/old/project",
            "state": "all_done",
            "raw_event": "SessionEnd",
            "raw_detail": None,
            "updated_at": "2026-07-27T00:00:00.000000Z",
            "message_count": 0,
        }))

        # Create a fresh manager pointing at same dir
        manager = StateManager(data_dir=tmp_dir)
        await manager.restore()

        session = manager.get("old-session")
        assert session is not None
        assert session.state == MonitorState.ALL_DONE
        assert session.cwd == "/old/project"

    @pytest.mark.asyncio
    async def test_stop_maps_to_pending_review(self, manager):
        event = self._make_event(hook_event_name="Stop", tool_name=None)
        session = await manager.handle_event(event)
        assert session.state == MonitorState.PENDING_REVIEW

    @pytest.mark.asyncio
    async def test_restore_skips_invalid_json(self, tmp_dir):
        # Write a session dir with invalid JSON
        bad_dir = tmp_dir / "bad-dir"
        bad_dir.mkdir()
        (bad_dir / "session.json").write_text("not json")
        # Write a valid session dir
        good_dir = tmp_dir / "good-dir"
        good_dir.mkdir()
        (good_dir / "session.json").write_text(json.dumps({
            "session_id": "good",
            "cwd": "/proj",
            "state": "idle",
            "raw_event": "Stop",
            "raw_detail": None,
            "updated_at": "2026-07-27T00:00:00.000000Z",
            "message_count": 0,
        }))

        manager = StateManager(data_dir=tmp_dir)
        await manager.restore()

        assert manager.get("good") is not None
        assert manager.get("bad-dir") is None

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


class TestMessages:
    """Tests for Message creation, storage, and retrieval."""

    @pytest.fixture
    def tmp_dir(self):
        with tempfile.TemporaryDirectory() as d:
            yield Path(d)

    @pytest.fixture
    def manager(self, tmp_dir):
        return StateManager(data_dir=tmp_dir)

    def _event(self, **overrides):
        base = {"session_id": "s1", "cwd": "/project", "hook_event_name": "PreToolUse", "tool_name": "Bash"}
        base.update(overrides)
        return base

    @pytest.mark.asyncio
    async def test_user_prompt_creates_message(self, manager, tmp_dir):
        await manager.handle_event(self._event(
            hook_event_name="UserPromptSubmit", tool_name=None,
            prompt="Hello, refactor this code",
        ))
        msgs, total = manager.get_messages("s1")
        assert total == 2  # prompt + thinking skeleton
        user_msgs = [m for m in msgs if m.type == "user_prompt"]
        assert len(user_msgs) == 1
        assert user_msgs[0].content == "Hello, refactor this code"

    @pytest.mark.asyncio
    async def test_stop_creates_assistant_message(self, manager, tmp_dir):
        await manager.handle_event(self._event(
            hook_event_name="Stop", tool_name=None,
            last_assistant_message="Here is the refactored code.",
            usage={"input_tokens": 500, "output_tokens": 200},
        ))
        msgs, total = manager.get_messages("s1")
        resp_msgs = [m for m in msgs if m.type == "assistant_response"]
        assert len(resp_msgs) >= 1
        assert resp_msgs[0].content == "Here is the refactored code."
        assert resp_msgs[0].input_tokens == 500
        assert resp_msgs[0].output_tokens == 200

    @pytest.mark.asyncio
    async def test_tool_use_creates_message(self, manager, tmp_dir):
        await manager.handle_event(self._event(
            hook_event_name="PostToolUse",
            tool_name="Read",
            tool_input={"file_path": "/path/to/file.py"},
            tool_output="line 1: import os\nline 2: ...",
        ))
        msgs, total = manager.get_messages("s1")
        tool_msgs = [m for m in msgs if m.type == "tool_use"]
        assert len(tool_msgs) >= 1
        assert tool_msgs[0].tool_name == "Read"
        assert "file.py" in (tool_msgs[0].tool_input or "")

    @pytest.mark.asyncio
    async def test_get_messages_pagination(self, manager, tmp_dir):
        # Send several events to build up messages
        for i in range(7):
            await manager.handle_event(self._event(
                session_id="s1",
                hook_event_name="UserPromptSubmit", tool_name=None,
                prompt=f"Prompt {i}",
            ))
        msgs, total = manager.get_messages("s1", offset=0, limit=3)
        assert len(msgs) == 3
        assert total >= 7

        msgs2, _ = manager.get_messages("s1", offset=3, limit=3)
        assert len(msgs2) >= 1

    @pytest.mark.asyncio
    async def test_get_messages_nonexistent_session(self, manager):
        msgs, total = manager.get_messages("nonexistent")
        assert msgs == []
        assert total == 0

    @pytest.mark.asyncio
    async def test_get_stats(self, manager, tmp_dir):
        await manager.handle_event(self._event(
            hook_event_name="UserPromptSubmit", tool_name=None,
            prompt="First prompt",
        ))
        await manager.handle_event(self._event(
            hook_event_name="PostToolUse",
            tool_name="Read",
            tool_input={"file_path": "a.py"},
            tool_output="content",
        ))
        await manager.handle_event(self._event(
            hook_event_name="Stop", tool_name=None,
            last_assistant_message="Done.",
            usage={"input_tokens": 100, "output_tokens": 50},
        ))

        stats = manager.get_stats("s1")
        assert stats is not None
        assert stats["total_prompts"] >= 1
        assert stats["total_tool_calls"] >= 1
        assert stats["total_assistant_messages"] >= 1
        assert stats["total_input_tokens"] >= 100
        assert stats["total_output_tokens"] >= 50
        assert "Read" in stats["tool_breakdown"]

    @pytest.mark.asyncio
    async def test_get_stats_nonexistent_session(self, manager):
        assert manager.get_stats("nonexistent") is None

    @pytest.mark.asyncio
    async def test_delete_session(self, manager, tmp_dir):
        await manager.handle_event(self._event())
        session_dir = tmp_dir / "s1"
        assert session_dir.is_dir()
        assert manager.get("s1") is not None

        deleted = manager.delete_session("s1")
        assert deleted is True
        assert not session_dir.exists()
        assert manager.get("s1") is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_session(self, manager):
        assert manager.delete_session("nonexistent") is False

    @pytest.mark.asyncio
    async def test_message_count_tracked(self, manager):
        session = await manager.handle_event(self._event(
            hook_event_name="UserPromptSubmit", tool_name=None,
            prompt="Hello",
        ))
        assert session.message_count >= 1


class TestLegacyMigration:
    """Tests for migrating v0.4.x flat JSON files to directory layout."""

    @pytest.fixture
    def tmp_dir(self):
        with tempfile.TemporaryDirectory() as d:
            yield Path(d)

    def test_migration(self, tmp_dir):
        # Write a legacy flat file
        (tmp_dir / "legacy-session.json").write_text(json.dumps({
            "session_id": "legacy-session",
            "cwd": "/legacy/project",
            "state": "idle",
            "raw_event": "Stop",
            "raw_detail": None,
            "summary": "Old session",
            "archived": False,
            "updated_at": "2026-07-01T00:00:00.000000Z",
        }))

        manager = StateManager(data_dir=tmp_dir)
        import asyncio
        asyncio.get_event_loop().run_until_complete(manager.restore())

        # Old flat file should be gone
        assert not (tmp_dir / "legacy-session.json").exists()
        # New directory layout should exist
        assert (tmp_dir / "legacy-session" / "session.json").exists()

        session = manager.get("legacy-session")
        assert session is not None
        assert session.state == MonitorState.IDLE
        assert session.cwd == "/legacy/project"
        assert session.summary == "Old session"

