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
