"""Integration tests for cc-monitor -- full hook->server->SSE pipeline."""

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
    """Simulate: start -> working -> pending approval -> done."""
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
        # ---- UserPromptSubmit -> WORKING ----
        resp = await client.post("/api/event", json=events[0])
        assert resp.json()["state"] == "working"

        # ---- PreToolUse -> WORKING ----
        resp = await client.post("/api/event", json=events[1])
        assert resp.json()["state"] == "working"

        # ---- PostToolUse -> WORKING ----
        resp = await client.post("/api/event", json=events[2])
        assert resp.json()["state"] == "working"

        # ---- PermissionRequest -> PENDING_APPROVAL ----
        resp = await client.post("/api/event", json=events[3])
        assert resp.json()["state"] == "pending_approval"

        # ---- Stop should NOT flip pending_approval ----
        resp = await client.post("/api/event", json=events[4])
        assert resp.json()["state"] == "pending_approval"

        # ---- UserPromptSubmit clears guard -> WORKING ----
        resp = await client.post("/api/event", json=events[5])
        assert resp.json()["state"] == "working"

        # ---- PreToolUse -> WORKING ----
        resp = await client.post("/api/event", json=events[6])
        assert resp.json()["state"] == "working"

        # ---- SessionEnd -> ALL_DONE ----
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
async def test_sse_broadcast_to_subscribers(test_app, tmp_data_dir):
    """Verify the pub/sub mechanism that powers SSE works end-to-end.

    Tests the StateManager's subscribe/handle_event/broadcast pipeline
    directly (the SSE HTTP endpoint wraps this same machinery).
    """
    from cc_monitor.state import StateManager

    manager = StateManager(data_dir=tmp_data_dir)

    # Subscribe -- simulates an SSE client connecting
    q = manager.subscribe()

    # Post an event -- simulates a hook event from Claude Code
    await manager.handle_event({
        "session_id": "sse-test",
        "cwd": "/p",
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
    })

    # The subscriber queue should have received the state_update payload
    payload = await asyncio.wait_for(q.get(), timeout=1.0)
    assert payload["session_id"] == "sse-test"
    assert payload["state"] == "working"

    # Multiple subscribers all receive the event
    q2 = manager.subscribe()
    await manager.handle_event({
        "session_id": "multi-sub",
        "cwd": "/p",
        "hook_event_name": "Stop",
    })

    payload1 = await asyncio.wait_for(q.get(), timeout=1.0)
    payload2 = await asyncio.wait_for(q2.get(), timeout=1.0)
    assert payload1["session_id"] == "multi-sub"
    assert payload1["state"] == "idle"
    assert payload2["session_id"] == "multi-sub"
    assert payload2["state"] == "idle"

    # Clean up
    manager.unsubscribe(q)
    manager.unsubscribe(q2)
