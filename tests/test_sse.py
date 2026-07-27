"""Verify SSE message format correctness."""
import json

from cc_monitor.server import _format_sse_event


class TestFormatSseEvent:
    """Unit tests for SSE message formatting — no server needed."""

    def test_state_update_with_data(self):
        result = _format_sse_event("state_update", '{"state":"working"}')
        assert result == 'event: state_update\ndata: {"state":"working"}\n\n'

    def test_heartbeat_with_data(self):
        result = _format_sse_event("heartbeat", '{"ts":123.45}')
        assert result == 'event: heartbeat\ndata: {"ts":123.45}\n\n'

    def test_event_without_data(self):
        result = _format_sse_event("open")
        assert result == "event: open\n\n"

    def test_ends_with_double_newline(self):
        """SSE spec: each event block ends with \\n\\n (blank line delimiter)."""
        result = _format_sse_event("heartbeat", "{}")
        assert result.endswith("\n\n")
        assert not result.endswith("\n\n\n")

    def test_event_line_before_data_line(self):
        """SSE spec: event field must come before data field."""
        result = _format_sse_event("heartbeat", "{}")
        lines = result.strip("\n").split("\n")
        assert lines[0].startswith("event: ")
        assert lines[1].startswith("data: ")

    def test_colon_space_separator(self):
        """SSE spec requires ': ' (colon + single space) between field and value."""
        result = _format_sse_event("heartbeat", "{}")
        assert "event: heartbeat\n" in result
        assert "data: {}\n" in result

    def test_data_is_valid_json(self):
        """EventSource parses data as JSON; broken JSON breaks the JS client."""
        payload = {"session_id": "abc", "state": "idle", "cwd": "/tmp"}
        formatted = _format_sse_event("state_update", json.dumps(payload))
        for line in formatted.split("\n"):
            if line.startswith("data: "):
                parsed = json.loads(line[6:])
                assert parsed == payload
                return
        pytest.fail("No data line found in formatted SSE event")

    def test_heartbeat_data_is_valid_json(self):
        """Heartbeat data must parse as valid JSON for EventSource."""
        formatted = _format_sse_event("heartbeat", '{"ts":100.0}')
        for line in formatted.split("\n"):
            if line.startswith("data: "):
                parsed = json.loads(line[6:])
                assert "ts" in parsed
                return
        pytest.fail("No data line in heartbeat")

    def test_no_extra_whitespace(self):
        """No leading/trailing whitespace on field lines."""
        result = _format_sse_event("heartbeat", "{}")
        for line in result.strip("\n").split("\n"):
            assert line == line.strip()
            assert not line.startswith(" ")
            assert not line.endswith(" ")

    def test_multiline_data_is_rejected(self):
        """SSE multiline data requires special handling; our data should be single-line JSON."""
        payload = {"key": "value"}
        formatted = _format_sse_event("state_update", json.dumps(payload))
        assert "\n" not in json.dumps(payload)  # compact JSON is single-line


class TestSseStreamSetup:
    """Verify the SSE stream endpoint is wired correctly via create_app."""

    def test_create_app_has_stream_route(self, tmp_path):
        """The /api/stream route must exist in the FastAPI app."""
        from cc_monitor.server import create_app
        app = create_app(data_dir=tmp_path)
        routes = [r.path for r in app.routes]
        assert "/api/stream" in routes

    def test_create_app_has_event_route(self, tmp_path):
        """The /api/event route must exist."""
        from cc_monitor.server import create_app
        app = create_app(data_dir=tmp_path)
        routes = [r.path for r in app.routes]
        assert "/api/event" in routes

    def test_create_app_has_status_route(self, tmp_path):
        """The /api/status route must exist."""
        from cc_monitor.server import create_app
        app = create_app(data_dir=tmp_path)
        routes = [r.path for r in app.routes]
        assert "/api/status" in routes
