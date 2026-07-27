"""End-to-end verification: start server, post events, check responses and UI.

This test uses httpx against a live uvicorn server — NOT ASGI transport —
to verify real HTTP behavior including SSE, JSON responses, and static files.
"""
import json
import time
import signal
import subprocess
import sys

import pytest
import httpx

SERVER_PORT = 19877
BASE_URL = f"http://127.0.0.1:{SERVER_PORT}"


@pytest.fixture(scope="module")
def server():
    """Start the cc-monitor server as a subprocess, yield, then kill it."""
    venv = "/home/bolun/Projects/venv_313/bin"
    proc = subprocess.Popen(
        [f"{venv}/python", "-c",
         f"from cc_monitor.server import create_app, main; "
         f"import uvicorn; "
         f"app = create_app(); "
         f"uvicorn.run(app, host='127.0.0.1', port={SERVER_PORT}, log_level='error')"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # Wait for server to be ready
    for _ in range(30):
        try:
            httpx.get(f"{BASE_URL}/api/version", timeout=0.5)
            break
        except Exception:
            time.sleep(0.1)
    else:
        proc.kill()
        pytest.fail("Server did not start within 3s")

    yield BASE_URL

    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


class TestVersion:
    """Verify version endpoint and __version__ consistency."""

    def test_version_endpoint_returns_030(self, server):
        resp = httpx.get(f"{server}/api/version")
        assert resp.status_code == 200
        data = resp.json()
        assert data["version"] == "0.4.0"

    def test_version_matches_package(self, server):
        from cc_monitor import __version__
        resp = httpx.get(f"{server}/api/version")
        assert resp.json()["version"] == __version__
        assert __version__ == "0.4.0"


class TestEventWithSummary:
    """Verify summary field flows through event pipeline."""

    def test_user_prompt_submit_captures_prompt_as_summary(self, server):
        resp = httpx.post(f"{server}/api/event", json={
            "session_id": "summary-test-1",
            "cwd": "/home/user/my-project",
            "hook_event_name": "UserPromptSubmit",
            "prompt": "Fix the login bug in auth.py",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["summary"] == "Fix the login bug in auth.py"
        assert data["state"] == "working"

    def test_stop_captures_last_assistant_message(self, server):
        # First submit a prompt
        httpx.post(f"{server}/api/event", json={
            "session_id": "summary-test-2",
            "cwd": "/home/user/proj",
            "hook_event_name": "UserPromptSubmit",
            "prompt": "Write tests for utils.py",
        })
        # Then stop with an assistant message
        resp = httpx.post(f"{server}/api/event", json={
            "session_id": "summary-test-2",
            "cwd": "/home/user/proj",
            "hook_event_name": "Stop",
            "last_assistant_message": "I've added 5 unit tests covering all edge cases.",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["summary"] == "I've added 5 unit tests covering all edge cases."
        assert data["state"] == "idle"

    def test_summary_persists_between_events(self, server):
        """When a non-summary event fires, the previous summary is kept."""
        # Setup: submit a prompt
        httpx.post(f"{server}/api/event", json={
            "session_id": "summary-test-3",
            "cwd": "/p",
            "hook_event_name": "UserPromptSubmit",
            "prompt": "Refactor the database layer",
        })
        # Intermediate event without summary data
        resp = httpx.post(f"{server}/api/event", json={
            "session_id": "summary-test-3",
            "cwd": "/p",
            "hook_event_name": "PreToolUse",
            "tool_name": "Read",
        })
        assert resp.status_code == 200
        assert resp.json()["summary"] == "Refactor the database layer"

    def test_summary_appears_in_status(self, server):
        """GET /api/status must include summary in session data."""
        httpx.post(f"{server}/api/event", json={
            "session_id": "summary-test-4",
            "cwd": "/app",
            "hook_event_name": "UserPromptSubmit",
            "prompt": "Deploy to production",
        })
        resp = httpx.get(f"{server}/api/status")
        assert resp.status_code == 200
        sessions = resp.json()["sessions"]
        session = next(s for s in sessions if s["session_id"] == "summary-test-4")
        assert session["summary"] == "Deploy to production"

    def test_summary_appears_in_single_status(self, server):
        """GET /api/status/{id} must include summary."""
        httpx.post(f"{server}/api/event", json={
            "session_id": "summary-test-5",
            "cwd": "/x",
            "hook_event_name": "UserPromptSubmit",
            "prompt": "Update dependencies",
        })
        resp = httpx.get(f"{server}/api/status/summary-test-5")
        assert resp.status_code == 200
        assert resp.json()["summary"] == "Update dependencies"


class TestSessionActions:
    """Archive, unarchive, and mark-complete endpoints."""

    def _create_session(self, server, sid="act-test", **kw):
        return httpx.post(f"{server}/api/event", json={
            "session_id": sid,
            "cwd": "/p",
            "hook_event_name": "UserPromptSubmit",
            "prompt": "Test session",
            **kw,
        })

    def test_archive_session(self, server):
        self._create_session(server)
        resp = httpx.post(f"{server}/api/session/act-test/archive")
        assert resp.status_code == 200
        assert resp.json()["archived"] is True

    def test_unarchive_session(self, server):
        self._create_session(server)
        httpx.post(f"{server}/api/session/act-test/archive")
        resp = httpx.post(f"{server}/api/session/act-test/unarchive")
        assert resp.status_code == 200
        assert resp.json()["archived"] is False

    def test_mark_complete(self, server):
        self._create_session(server, sid="complete-me")
        resp = httpx.post(f"{server}/api/session/complete-me/complete")
        assert resp.status_code == 200
        assert resp.json()["state"] == "all_done"
        assert resp.json()["raw_event"] == "ManualComplete"

    def test_archive_nonexistent_returns_404(self, server):
        resp = httpx.post(f"{server}/api/session/nope/archive")
        assert resp.status_code == 404

    def test_complete_nonexistent_returns_404(self, server):
        resp = httpx.post(f"{server}/api/session/nope/complete")
        assert resp.status_code == 404

    def test_archived_field_persists_in_status(self, server):
        self._create_session(server, sid="persist-me")
        httpx.post(f"{server}/api/session/persist-me/archive")
        resp = httpx.get(f"{server}/api/status")
        session = next(s for s in resp.json()["sessions"] if s["session_id"] == "persist-me")
        assert session["archived"] is True

    def test_default_archived_is_false(self, server):
        self._create_session(server, sid="fresh")
        resp = httpx.get(f"{server}/api/status/session/fresh")
        # The session is in /api/status via the list, get by specific ID
        resp2 = httpx.get(f"{server}/api/status")
        session = next(s for s in resp2.json()["sessions"] if s["session_id"] == "fresh")
        assert session["archived"] is False

    def test_section_routing_active(self, server):
        """Active sessions have archived=false and state != all_done."""
        self._create_session(server, sid="active-1")
        resp = httpx.get(f"{server}/api/status")
        s = next(s for s in resp.json()["sessions"] if s["session_id"] == "active-1")
        assert s["archived"] is False
        assert s["state"] == "working"

    def test_section_routing_complete(self, server):
        """Complete sessions have archived=false and state == all_done."""
        self._create_session(server, sid="done-1")
        httpx.post(f"{server}/api/session/done-1/complete")
        resp = httpx.get(f"{server}/api/status")
        s = next(s for s in resp.json()["sessions"] if s["session_id"] == "done-1")
        assert s["state"] == "all_done"
        assert s["archived"] is False

    def test_section_routing_archived(self, server):
        """Archived sessions have archived=true regardless of state."""
        self._create_session(server, sid="arch-1")
        httpx.post(f"{server}/api/session/arch-1/archive")
        resp = httpx.get(f"{server}/api/status")
        s = next(s for s in resp.json()["sessions"] if s["session_id"] == "arch-1")
        assert s["archived"] is True

    def test_archived_session_stays_archived_after_complete(self, server):
        """Archive + complete — session should remain archived."""
        self._create_session(server, sid="arch-complete")
        httpx.post(f"{server}/api/session/arch-complete/archive")
        httpx.post(f"{server}/api/session/arch-complete/complete")
        resp = httpx.get(f"{server}/api/status")
        s = next(s for s in resp.json()["sessions"] if s["session_id"] == "arch-complete")
        assert s["archived"] is True
        assert s["state"] == "all_done"

    def test_status_returns_archived_field(self, server):
        """All sessions in /api/status must include the 'archived' field."""
        self._create_session(server, sid="field-test")
        resp = httpx.get(f"{server}/api/status")
        for s in resp.json()["sessions"]:
            assert "archived" in s, f"Session {s.get('session_id')} missing 'archived' field"


class TestCors:
    """CORS headers must be present for cross-origin dashboard hosting.

    Note: CORS headers are only added when the request includes an Origin
    header that differs from the server.  Same-origin requests (no Origin
    header) correctly omit CORS headers per the spec.
    """

    _ORIGIN = {"Origin": "https://bolunhan.github.io"}

    def test_cors_header_on_api(self, server):
        resp = httpx.get(f"{server}/api/version", headers=self._ORIGIN)
        assert resp.headers["access-control-allow-origin"] == "*"

    def test_cors_header_on_status(self, server):
        resp = httpx.get(f"{server}/api/status", headers=self._ORIGIN)
        assert resp.headers["access-control-allow-origin"] == "*"

    def test_cors_header_on_event_post(self, server):
        resp = httpx.options(f"{server}/api/event", headers=self._ORIGIN)
        assert resp.headers["access-control-allow-origin"] == "*"

    def test_cors_preflight(self, server):
        """OPTIONS preflight must return CORS headers."""
        resp = httpx.options(f"{server}/api/version", headers={
            "Origin": "https://bolunhan.github.io",
            "Access-Control-Request-Method": "GET",
        })
        assert resp.status_code == 200
        assert resp.headers["access-control-allow-origin"] == "*"


class TestStaticFiles:
    """Verify static assets and HTML are served."""

    def test_index_html_served(self, server):
        resp = httpx.get(f"{server}/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "cc-monitor" in resp.text
        assert 'id="grid-active"' in resp.text

    def test_css_served(self, server):
        resp = httpx.get(f"{server}/static/css/app.css")
        assert resp.status_code == 200
        assert "text/css" in resp.headers["content-type"]
        assert "session-card__summary" in resp.text  # the CSS we added

    def test_js_served(self, server):
        resp = httpx.get(f"{server}/static/js/app.js")
        assert resp.status_code == 200
        assert "text/javascript" in resp.headers["content-type"] or \
               "application/javascript" in resp.headers["content-type"]
        assert "session.summary" in resp.text  # the JS summary logic we added

    def test_index_contains_footer_version(self, server):
        """The HTML must include the version footer element."""
        resp = httpx.get(f"{server}/")
        assert 'id="footer-version"' in resp.text
        assert "cc-monitor v" in resp.text

    def test_js_fetches_version(self, server):
        """The JS must fetch /api/version on init."""
        resp = httpx.get(f"{server}/static/js/app.js")
        assert 'apiUrl("/api/version")' in resp.text

    def test_css_served_at_css_path(self, server):
        """CSS must be accessible at /css/app.css (relative path compat)."""
        resp = httpx.get(f"{server}/css/app.css")
        assert resp.status_code == 200
        assert "text/css" in resp.headers["content-type"]

    def test_js_served_at_js_path(self, server):
        """JS must be accessible at /js/app.js (relative path compat)."""
        resp = httpx.get(f"{server}/js/app.js")
        assert resp.status_code == 200
        assert "text/javascript" in resp.headers["content-type"] or \
               "application/javascript" in resp.headers["content-type"]

    def test_index_uses_relative_paths(self, server):
        """index.html must use relative paths for gh-pages compatibility."""
        resp = httpx.get(f"{server}/")
        assert './css/app.css' in resp.text
        assert './js/app.js' in resp.text

    def test_js_has_configurable_server_url(self, server):
        """JS must support localStorage-based server URL configuration."""
        resp = httpx.get(f"{server}/js/app.js")
        assert 'cc-monitor-server-url' in resp.text
        assert 'localStorage.getItem' in resp.text
        assert 'getServerUrl' in resp.text
        assert 'apiUrl(' in resp.text
        assert 'Save & Reconnect' in resp.text or 'btn-save-settings' in resp.text

    def test_js_loads_sessions_immediately_on_init(self, server):
        """loadSessions() must be called on page load, not only after SSE open."""
        resp = httpx.get(f"{server}/js/app.js")
        assert "loadSessions().then(() => {" in resp.text
        assert "connectSSE()" in resp.text
        # loadSessions must appear BEFORE connectSSE in init
        initSection = resp.text.split("// ---- Initialise ----")[1].split("})();")[0]
        loadPos = initSection.index("loadSessions()")
        ssePos = initSection.index("connectSSE()")
        assert loadPos < ssePos, "loadSessions must be called before connectSSE"

    def test_index_has_server_url_settings(self, server):
        """Settings panel must have URL and Port inputs + save button."""
        resp = httpx.get(f"{server}/")
        assert 'id="settings-url"' in resp.text
        assert 'id="settings-port"' in resp.text
        assert 'id="btn-save-settings"' in resp.text

    def test_index_has_three_sections(self, server):
        """Dashboard must have Active, Complete, and Archived sections."""
        resp = httpx.get(f"{server}/")
        assert 'id="section-active"' in resp.text
        assert 'id="section-complete"' in resp.text
        assert 'id="section-archive"' in resp.text
        assert "Active" in resp.text
        assert "Complete" in resp.text
        assert "Archived" in resp.text

    def test_complete_and_archive_collapsed_by_default(self, server):
        """Complete and Archive sections must be collapsed on load."""
        resp = httpx.get(f"{server}/")
        assert 'section--collapsed' in resp.text or 'hidden' in resp.text

    def test_js_has_archive_complete_actions(self, server):
        """JS must support archive, unarchive, and mark-complete actions."""
        resp = httpx.get(f"{server}/js/app.js")
        assert 'apiUrl(`/api/session/${sessionId}/${action}`)' in resp.text
        assert '"archive"' in resp.text
        assert '"complete"' in resp.text
        assert '"unarchive"' in resp.text

    def test_js_default_url_127_0_0_1(self, server):
        """JS must default to http://127.0.0.1:9876 for remote dashboards."""
        resp = httpx.get(f"{server}/js/app.js")
        assert 'DEFAULT_HOST = "http://127.0.0.1"' in resp.text
        assert 'DEFAULT_PORT = "9876"' in resp.text

    def test_js_prevstates_stores_state_and_archived(self, server):
        """prevStates.set must store {state, archived} object, not bare string."""
        resp = httpx.get(f"{server}/js/app.js")
        assert "prevStates.set(session.session_id, {state: session.state, archived: session.archived})" in resp.text
        assert "prevStates.set(s.session_id, {state: s.state, archived: s.archived})" in resp.text

    def test_js_notify_uses_prev_state_property(self, server):
        """notify() must compare session.state with prev.state (not prev directly)."""
        resp = httpx.get(f"{server}/js/app.js")
        assert "prev && session.state === prev.state" in resp.text

    def test_js_getsection_routes_archived_first(self, server):
        """getSection must check archived before state."""
        resp = httpx.get(f"{server}/js/app.js")
        assert "if (session.archived) return \"archive\"" in resp.text

    def test_js_updatecounts_iterates_cards(self, server):
        """updateCounts must iterate cards Map and check prevStates."""
        resp = httpx.get(f"{server}/js/app.js")
        assert "cards.forEach" in resp.text
        assert "prevStates.get(sid)" in resp.text
        assert "getSection({archived: s.archived, state: s.state})" in resp.text

    def test_js_archived_badge_overrides_state(self, server):
        """Archived cards must show 'archived' badge, not the raw state."""
        resp = httpx.get(f"{server}/js/app.js")
        assert 'badgeState = isArchived ? "archived" : session.state' in resp.text
        assert 'badgeLabel = isArchived ? "archived" : session.state.replace("_", " ")' in resp.text
        assert 'badge-${badgeState}' in resp.text

    def test_css_has_archived_badge_style(self, server):
        """CSS must define .badge-archived style."""
        resp = httpx.get(f"{server}/css/app.css")
        assert ".badge-archived" in resp.text

    def test_js_connect_sse_does_not_clear_cards(self, server):
        """connectSSE must NOT clear cards — only clearAllCards on manual reconnect."""
        resp = httpx.get(f"{server}/js/app.js")
        connectBody = resp.text.split("function connectSSE() {")[1].split("setInterval")[0]
        assert "clearAllCards" not in connectBody, \
            "connectSSE must not clear cards on connect"

    def test_js_null_guards_on_dom_access(self, server):
        """DOM accessors must null-guard to prevent crashes on missing elements."""
        resp = httpx.get(f"{server}/js/app.js")
        assert "if (indicator)" in resp.text or "indicator.classList" in resp.text
        assert "if (!grid) return" in resp.text
        assert "if (grid) grid.querySelectorAll" in resp.text
        assert "if (empty) empty.style" in resp.text
        assert "const el = getCount(sec);" in resp.text
        assert "if (el) el.textContent" in resp.text


class TestSseStream:
    """Verify SSE endpoint behavior with raw TCP to avoid httpx buffering."""

    def test_sse_headers(self, server):
        """SSE stream must return correct headers — verified via raw HTTP."""
        import socket
        host, port = server.replace("http://", "").split(":")
        port = int(port)

        sock = socket.create_connection((host, port), timeout=3)
        try:
            sock.sendall(f"GET /api/stream HTTP/1.1\r\nHost: {host}:{port}\r\n\r\n".encode())
            # Read just the headers (until \r\n\r\n)
            buf = b""
            while b"\r\n\r\n" not in buf:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                buf += chunk

            headers_text = buf.split(b"\r\n\r\n")[0].decode()
            assert "HTTP/1.1 200" in headers_text, f"Bad status:\n{headers_text}"
            assert "text/event-stream" in headers_text, f"No SSE content-type:\n{headers_text}"
            assert "cache-control: no-cache" in headers_text.lower(), f"Missing no-cache:\n{headers_text}"
        finally:
            sock.close()

    def test_sse_receives_state_update(self, server):
        """Raw TCP: connect SSE, post event, read state_update from stream."""
        import socket
        host, port = server.replace("http://", "").split(":")
        port = int(port)

        sock = socket.create_connection((host, port), timeout=5)
        try:
            sock.sendall(f"GET /api/stream HTTP/1.1\r\nHost: {host}:{port}\r\n\r\n".encode())
            # Read past headers
            buf = b""
            while b"\r\n\r\n" not in buf:
                buf += sock.recv(4096)
            body_start = buf.split(b"\r\n\r\n", 1)[1] if b"\r\n\r\n" in buf else b""

            # Post an event via httpx
            httpx.post(f"{server}/api/event", json={
                "session_id": "sse-raw-verify",
                "cwd": "/verify",
                "hook_event_name": "Stop",
            })

            # Read body
            body = body_start
            deadline = time.time() + 4
            while time.time() < deadline:
                sock.settimeout(2)
                try:
                    chunk = sock.recv(4096)
                    if chunk:
                        body += chunk
                except socket.timeout:
                    pass
                if b"event: state_update" in body:
                    break

            text = body.decode("utf-8", errors="replace")
            assert "event: state_update" in text, f"No state_update in stream:\n{text[:500]}"
            assert "sse-raw-verify" in text, f"Missing session_id:\n{text[:500]}"
        finally:
            sock.close()

    def test_sse_receives_heartbeat(self, server):
        """Raw TCP: connect SSE, wait for heartbeat event."""
        import socket
        host, port = server.replace("http://", "").split(":")
        port = int(port)

        sock = socket.create_connection((host, port), timeout=8)
        try:
            sock.sendall(f"GET /api/stream HTTP/1.1\r\nHost: {host}:{port}\r\n\r\n".encode())
            # Read past headers
            buf = b""
            while b"\r\n\r\n" not in buf:
                buf += sock.recv(4096)
            body_start = buf.split(b"\r\n\r\n", 1)[1] if b"\r\n\r\n" in buf else b""

            body = body_start
            deadline = time.time() + 6
            while time.time() < deadline:
                sock.settimeout(2)
                try:
                    chunk = sock.recv(4096)
                    if chunk:
                        body += chunk
                except socket.timeout:
                    pass
                if b"event: heartbeat" in body:
                    break

            text = body.decode("utf-8", errors="replace")
            assert "event: heartbeat" in text, (
                f"No heartbeat in SSE after 6s. Raw body:\n{text[:500]}")
            assert "data:" in text, f"Missing data field in heartbeat:\n{text[:500]}"
        finally:
            sock.close()


class TestJsonRoundTrip:
    """State written to disk must round-trip through restore with summary intact."""

    def test_summary_round_trips_through_disk(self, tmp_path):
        from cc_monitor.state import StateManager

        mgr = StateManager(data_dir=tmp_path)

        # Write an event with summary
        import asyncio
        asyncio.run(mgr.handle_event({
            "session_id": "rt",
            "cwd": "/rt",
            "hook_event_name": "UserPromptSubmit",
            "prompt": "Round-trip test prompt",
        }))

        # Simulate server restart: new StateManager reading same dir
        mgr2 = StateManager(data_dir=tmp_path)
        asyncio.run(mgr2.restore())

        session = mgr2.get("rt")
        assert session is not None
        assert session.summary == "Round-trip test prompt"
        assert session.to_dict()["summary"] == "Round-trip test prompt"
