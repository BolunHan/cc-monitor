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
