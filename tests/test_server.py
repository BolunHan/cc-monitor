"""Tests for cc_monitor.server."""

import json
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from cc_monitor.server import create_app


@pytest.fixture
def tmp_data_dir(tmp_path):
    return tmp_path


@pytest.fixture
def test_app(tmp_data_dir):
    _app = create_app(data_dir=tmp_data_dir)
    return _app


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
    state_file = tmp_data_dir / "test-session" / "session.json"
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
    assert resp.json()["state"] == "pending_review"


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


class TestAuthEnabledServer:
    """Integration tests for create_app with enable_auth=True."""

    @pytest.fixture
    def auth_app(self, tmp_path):
        from cc_monitor.tls import CertConfig, generate_self_signed_cert, get_cert_fingerprint

        cert_path, key_path = generate_self_signed_cert(tmp_path)
        fingerprint = get_cert_fingerprint(cert_path)
        cert_config = CertConfig(
            certfile=cert_path, keyfile=key_path, fingerprint=fingerprint,
        )
        return create_app(
            data_dir=tmp_path,
            enable_auth=True,
            cert_config=cert_config,
            token_ttl=3600,
        )

    @pytest.mark.asyncio
    async def test_localhost_access_unauthenticated(self, auth_app):
        transport = ASGITransport(app=auth_app, client=("127.0.0.1", 12345))
        async with AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
            resp = await client.get("/api/status")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_remote_access_blocked_without_token(self, auth_app):
        transport = ASGITransport(app=auth_app, client=("10.0.0.1", 12345))
        async with AsyncClient(transport=transport, base_url="http://10.0.0.1") as client:
            resp = await client.get("/api/status")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_remote_access_allowed_with_token(self, auth_app):
        tm = auth_app.state.token_manager
        info = tm.create_token("Test Device")
        transport = ASGITransport(app=auth_app, client=("10.0.0.1", 12345))
        async with AsyncClient(transport=transport, base_url="http://10.0.0.1") as client:
            resp = await client.get(
                "/api/status",
                headers={"Authorization": f"Bearer {info.token}"},
            )
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_get_session_messages(test_app, tmp_data_dir):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Post events that generate messages
        await client.post("/api/event", json={
            "session_id": "s1", "cwd": "/a",
            "hook_event_name": "UserPromptSubmit",
            "prompt": "Hello world",
        })
        await client.post("/api/event", json={
            "session_id": "s1", "cwd": "/a",
            "hook_event_name": "Stop",
            "last_assistant_message": "Hello back",
        })

        resp = await client.get("/api/session/s1/messages?offset=0&limit=5")

    assert resp.status_code == 200
    data = resp.json()
    assert "messages" in data
    assert "total" in data
    assert data["total"] >= 2
    types = [m["type"] for m in data["messages"]]
    assert "user_prompt" in types or "assistant_response" in types


@pytest.mark.asyncio
async def test_get_session_messages_404(test_app):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/session/nonexistent/messages")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_session_stats(test_app, tmp_data_dir):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/api/event", json={
            "session_id": "s1", "cwd": "/a",
            "hook_event_name": "UserPromptSubmit",
            "prompt": "Test",
        })
        await client.post("/api/event", json={
            "session_id": "s1", "cwd": "/a",
            "hook_event_name": "PostToolUse",
            "tool_name": "Read",
            "tool_input": {"file_path": "x.py"},
            "tool_output": "content",
        })
        await client.post("/api/event", json={
            "session_id": "s1", "cwd": "/a",
            "hook_event_name": "Stop",
            "last_assistant_message": "Done",
            "usage": {"input_tokens": 100, "output_tokens": 50},
        })

        resp = await client.get("/api/session/s1/stats")

    assert resp.status_code == 200
    stats = resp.json()
    assert stats["total_prompts"] >= 1
    assert stats["total_tool_calls"] >= 1
    assert stats["total_assistant_messages"] >= 1
    assert stats["total_input_tokens"] >= 100
    assert stats["total_output_tokens"] >= 50
    assert "Read" in stats["tool_breakdown"]


@pytest.mark.asyncio
async def test_get_session_stats_404(test_app):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/session/nonexistent/stats")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_session(test_app, tmp_data_dir):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/api/event", json={
            "session_id": "to-delete", "cwd": "/x",
            "hook_event_name": "PreToolUse", "tool_name": "Bash",
        })

        resp = await client.delete("/api/session/to-delete")

    assert resp.status_code == 200
    assert resp.json()["status"] == "deleted"

    # Verify it's gone
    transport2 = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport2, base_url="http://test") as client:
        resp = await client.get("/api/status/to-delete")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_session_404(test_app):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.delete("/api/session/nonexistent")
    assert resp.status_code == 404


class TestSafeHome:
    """_safe_home() Docker mount fallback — persistence robustness."""

    def test_native_uses_home(self):
        from cc_monitor.server import _safe_home
        assert _safe_home() == Path.home()

    def test_docker_with_mounted_data(self, monkeypatch):
        import os
        from cc_monitor.server import _safe_home
        monkeypatch.setattr("cc_monitor.server._IS_DOCKER", True)
        monkeypatch.setattr(os.path, "ismount", lambda p: p == "/data")
        assert _safe_home() == Path("/data")

    def test_docker_with_bind_mount_at_data_cc_monitor(self, monkeypatch):
        """Bind mount ~/.cc-monitor/docker/data -> /data/.cc-monitor."""
        import os
        from cc_monitor.server import _safe_home
        monkeypatch.setattr("cc_monitor.server._IS_DOCKER", True)
        monkeypatch.setattr(os.path, "ismount", lambda p: p == "/data/.cc-monitor")
        assert _safe_home() == Path("/data")

    def test_docker_without_volume_falls_back_to_home(self, monkeypatch):
        import os
        from cc_monitor.server import _safe_home
        monkeypatch.setattr("cc_monitor.server._IS_DOCKER", True)
        monkeypatch.setattr(os.path, "ismount", lambda p: False)
        assert _safe_home() == Path.home()
