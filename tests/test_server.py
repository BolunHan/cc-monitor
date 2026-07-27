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
