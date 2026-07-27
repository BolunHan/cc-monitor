"""Map raw Claude Code hook events to MonitorState."""

import enum


class MonitorState(enum.StrEnum):
    """Observable states of a Claude Code session."""

    IDLE = "idle"
    WORKING = "working"
    PENDING_APPROVAL = "pending_approval"
    PENDING_REVIEW = "pending_review"
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
        return MonitorState.PENDING_REVIEW

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
