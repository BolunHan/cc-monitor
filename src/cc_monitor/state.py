"""Session state management — in-memory store, file persistence, SSE fan-out."""

import asyncio
import json
import logging
import shutil
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from cc_monitor.mapping import MonitorState, map_event

logger = logging.getLogger(__name__)

# PENDING_REVIEW sessions auto-transition to IDLE after this duration
_REVIEW_TIMEOUT = timedelta(hours=24)
# How often to check for stale PENDING_REVIEW sessions
_REVIEW_CHECK_INTERVAL = 60  # seconds

# Max length for stored tool input/output to keep msg files small
_MAX_TOOL_FIELD_LENGTH = 2000


@dataclass
class Message:
    """A single message in a session conversation timeline."""

    timestamp: float  # unix timestamp (time.time())
    type: Literal["user_prompt", "assistant_response", "tool_use", "thinking", "pending_approval"]
    content: str | None = None
    tool_name: str | None = None
    tool_input: str | None = None
    tool_output: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    skeleton: bool = False
    source: str | None = None  # hook event name that produced this message

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "type": self.type,
            "content": self.content,
            "tool_name": self.tool_name,
            "tool_input": self.tool_input,
            "tool_output": self.tool_output,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "skeleton": self.skeleton or None,  # omit if False for compactness
            "source": self.source,
        }

    @property
    def correlation_key(self) -> str | None:
        """Key for matching skeletons with their completed versions."""
        if self.type == "tool_use":
            return self.tool_name
        if self.type == "thinking":
            return "thinking"
        if self.type == "pending_approval":
            return "pending_approval"
        return None

    @classmethod
    def from_dict(cls, data: dict) -> "Message":
        # Backward compat: "preliminary" was renamed to "skeleton"
        skeleton = data.get("skeleton", data.get("preliminary", False)) or False
        return cls(
            timestamp=data["timestamp"],
            type=data["type"],
            content=data.get("content"),
            tool_name=data.get("tool_name"),
            tool_input=data.get("tool_input"),
            tool_output=data.get("tool_output"),
            input_tokens=data.get("input_tokens"),
            output_tokens=data.get("output_tokens"),
            skeleton=skeleton,
            source=data.get("source"),
        )


@dataclass
class SessionState:
    """The current state of one Claude Code session."""

    session_id: str
    cwd: str
    state: MonitorState
    raw_event: str
    raw_detail: str | None
    summary: str | None = None
    archived: bool = False
    cc_monitor_uid: str = ""
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    message_count: int = 0  # cached count, updated on message write

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "cwd": self.cwd,
            "state": str(self.state),
            "raw_event": self.raw_event,
            "raw_detail": self.raw_detail,
            "summary": self.summary,
            "cc_monitor_uid": self.cc_monitor_uid,
            "archived": self.archived,
            "updated_at": self.updated_at.isoformat(),
            "message_count": self.message_count,
        }


class StateManager:
    """Manages session states in memory and on disk, with SSE broadcast.

    Directory layout (v0.5+):
        data_dir/
          <session_id>/
            session.json          # session metadata
            msg_<unix_ts>.json    # individual messages

    On startup, restore() loads all session dirs and migrates
    any legacy flat .json files from v0.4.x.
    """

    def __init__(self, data_dir: Path | None = None):
        if data_dir is None:
            try:
                home = Path.home()
                if str(home) == "/":
                    home = Path("/root")
            except (KeyError, RuntimeError):
                home = Path("/root")
            data_dir = home / ".cc-monitor"
        self._data_dir = data_dir
        self._sessions: dict[str, SessionState] = {}
        self._pending_approval: set[str] = set()
        self._queues: list[asyncio.Queue] = []
        self._review_timeout_task: asyncio.Task | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start_review_timeout(self) -> None:
        """Start a background task that expires stale PENDING_REVIEW sessions."""
        if self._review_timeout_task is not None:
            return
        self._review_timeout_task = asyncio.ensure_future(self._expire_reviews_loop())

    async def stop_review_timeout(self) -> None:
        """Stop the review timeout background task."""
        if self._review_timeout_task is not None:
            self._review_timeout_task.cancel()
            try:
                await self._review_timeout_task
            except asyncio.CancelledError:
                pass
            self._review_timeout_task = None

    def _session_dir(self, session_id: str) -> Path:
        return self._data_dir / session_id

    def _session_file(self, session_id: str) -> Path:
        return self._session_dir(session_id) / "session.json"

    async def restore(self) -> None:
        """Load all session directories into memory. Migrate legacy flat files."""
        self._data_dir.mkdir(parents=True, exist_ok=True)

        # Phase 1: migrate legacy flat .json files → session dirs
        for file_path in sorted(self._data_dir.glob("*.json")):
            sid = file_path.stem  # filename without .json
            try:
                data = json.loads(file_path.read_text())
            except (json.JSONDecodeError, OSError):
                data = None
            # Only session state files carry a session_id — never touch
            # other JSON files (tokens.json, pairing_requests.json), or
            # a stray directory named like them would cause deletion on
            # the next restart.
            if not isinstance(data, dict) or "session_id" not in data:
                continue
            session_dir = self._session_dir(sid)
            if session_dir.is_dir():
                # Already migrated — remove stale flat file
                logger.info("Removing stale flat file %s (dir already exists)", file_path.name)
                file_path.unlink()
                continue
            session_dir.mkdir(parents=True, exist_ok=True)
            # Extract session fields, drop anything message-related
            sess_data = {
                "session_id": data["session_id"],
                "cwd": data.get("cwd", ""),
                "state": data.get("state", "idle"),
                "raw_event": data.get("raw_event", ""),
                "raw_detail": data.get("raw_detail"),
                "summary": data.get("summary"),
                "archived": data.get("archived", False),
                "cc_monitor_uid": data.get("cc_monitor_uid", ""),
                "updated_at": data.get("updated_at", datetime.now(timezone.utc).isoformat()),
                "message_count": 0,
            }
            self._session_file(sid).write_text(json.dumps(sess_data, indent=2))
            file_path.unlink()
            logger.info("Migrated legacy session %s to directory layout", sid)

        # Phase 2: load all session directories
        for session_dir in sorted(self._data_dir.iterdir()):
            if not session_dir.is_dir():
                continue
            session_file = session_dir / "session.json"
            if not session_file.exists():
                continue
            try:
                data = json.loads(session_file.read_text())
                session = SessionState(
                    session_id=data["session_id"],
                    cwd=data["cwd"],
                    state=MonitorState(data["state"]),
                    raw_event=data["raw_event"],
                    raw_detail=data.get("raw_detail"),
                    summary=data.get("summary"),
                    archived=data.get("archived", False),
                    cc_monitor_uid=data.get("cc_monitor_uid", ""),
                    updated_at=datetime.fromisoformat(data["updated_at"]),
                    message_count=data.get("message_count", 0),
                )
                self._sessions[session.session_id] = session
                if session.state == MonitorState.PENDING_APPROVAL:
                    self._pending_approval.add(session.session_id)
            except (json.JSONDecodeError, KeyError, ValueError) as exc:
                logger.warning("Skipping invalid session dir %s: %s", session_dir.name, exc)

    async def handle_event(self, raw: dict) -> SessionState:
        """Process a raw hook event: map state, create message, persist, broadcast.

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
            self._pending_approval.discard(session_id)

        # If Stop fires while approval is pending, keep pending_approval
        if hook_event_name == "Stop" and session_id in self._pending_approval:
            existing = self._sessions.get(session_id)
            if existing:
                existing.raw_event = "Stop"
                existing.raw_detail = None
                existing.updated_at = datetime.now(timezone.utc)
                self._write_session_file(existing)
                await self._broadcast(existing)
                return existing
            new_state = MonitorState.IDLE

        # --- build message(s) ---
        msg_or_list = self._event_to_message(raw)
        if msg_or_list is not None:
            msgs = msg_or_list if isinstance(msg_or_list, list) else [msg_or_list]
            for m in msgs:
                ck = m.correlation_key
                if ck and not m.skeleton:
                    if m.type == "thinking":
                        # Consolidate: update skeleton file in-place, no new file
                        self._update_skeleton(session_id, ck, m)
                    else:
                        # Replace: remove skeleton, save real message
                        self._remove_skeletons(session_id, ck)
                        self._save_message(session_id, m)
                else:
                    self._save_message(session_id, m)
                # Broadcast each message to SSE subscribers
                payload = m.to_dict()
                payload["session_id"] = session_id
                asyncio.ensure_future(self._broadcast_message(payload))

        # --- update session ---
        summary = None
        existing = self._sessions.get(session_id)
        if hook_event_name == "UserPromptSubmit":
            prompt = raw.get("prompt", "")
            summary = prompt.strip() if prompt else None
        elif hook_event_name == "Stop":
            msg_text = raw.get("last_assistant_message", "")
            summary = msg_text.strip() if msg_text else None
        elif existing:
            summary = existing.summary

        # Re-count messages after save
        msg_count = self._count_messages(session_id)

        session = SessionState(
            session_id=session_id,
            cwd=raw.get("cwd", ""),
            state=new_state,
            raw_event=hook_event_name,
            raw_detail=tool_name or notification_type,
            summary=summary,
            cc_monitor_uid=raw.get("cc_monitor_uid", existing.cc_monitor_uid if existing else ""),
            message_count=msg_count,
        )
        self._sessions[session_id] = session

        # --- persist ---
        self._write_session_file(session)

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

    def get_messages(
        self, session_id: str, offset: int = 0, limit: int = 5
    ) -> tuple[list[Message], int]:
        """Return paginated messages for a session, newest first.

        Args:
            session_id: Session ID.
            offset: Number of messages to skip (from newest).
            limit: Max messages to return.

        Returns:
            (messages, total_count) tuple.
        """
        session_dir = self._session_dir(session_id)
        if not session_dir.is_dir():
            return [], 0

        msg_files = sorted(session_dir.glob("msg_*.json"), reverse=True)
        total = len(msg_files)
        batch = msg_files[offset : offset + limit]
        messages: list[Message] = []
        for fp in batch:
            try:
                messages.append(Message.from_dict(json.loads(fp.read_text())))
            except (json.JSONDecodeError, KeyError, ValueError) as exc:
                logger.warning("Skipping invalid message file %s: %s", fp.name, exc)
        return messages, total

    def get_stats(self, session_id: str) -> dict | None:
        """Compute aggregate stats for a session from its messages.

        Returns None if the session doesn't exist.
        """
        if session_id not in self._sessions:
            return None

        session_dir = self._session_dir(session_id)
        if not session_dir.is_dir():
            return self._empty_stats()

        msg_files = sorted(session_dir.glob("msg_*.json"))
        if not msg_files:
            return self._empty_stats()

        total_prompts = 0
        total_assistant = 0
        total_tool_calls = 0
        total_input_tokens = 0
        total_output_tokens = 0
        tool_counts: dict[str, int] = {}
        first_ts: float | None = None
        last_ts: float | None = None

        for fp in msg_files:
            try:
                m = json.loads(fp.read_text())
            except (json.JSONDecodeError, ValueError):
                continue
            mtype = m.get("type", "")
            if mtype == "user_prompt":
                total_prompts += 1
            elif mtype == "assistant_response":
                total_assistant += 1
            elif mtype == "thinking":
                pass  # counted as part of the response
            elif mtype == "pending_approval":
                pass  # not a content message
            elif mtype == "tool_use":
                total_tool_calls += 1
                tn = m.get("tool_name", "unknown")
                tool_counts[tn] = tool_counts.get(tn, 0) + 1
            ti = m.get("input_tokens")
            to = m.get("output_tokens")
            if isinstance(ti, (int, float)) and ti is not None:
                total_input_tokens += int(ti)
            if isinstance(to, (int, float)) and to is not None:
                total_output_tokens += int(to)
            ts = m.get("timestamp")
            if isinstance(ts, (int, float)):
                if first_ts is None or ts < first_ts:
                    first_ts = ts
                if last_ts is None or ts > last_ts:
                    last_ts = ts

        return {
            "total_prompts": total_prompts,
            "total_assistant_messages": total_assistant,
            "total_tool_calls": total_tool_calls,
            "total_input_tokens": total_input_tokens,
            "total_output_tokens": total_output_tokens,
            "tool_breakdown": tool_counts,
            "session_start": datetime.fromtimestamp(first_ts, tz=timezone.utc).isoformat() if first_ts else None,
            "session_end": datetime.fromtimestamp(last_ts, tz=timezone.utc).isoformat() if last_ts else None,
            "duration_seconds": round(last_ts - first_ts) if (first_ts and last_ts) else 0,
        }

    def get_session_size(self, session_id: str) -> int:
        """Return total size in bytes of all files in a session directory."""
        session_dir = self._session_dir(session_id)
        if not session_dir.is_dir():
            return 0
        total = 0
        for f in session_dir.rglob("*"):
            if f.is_file():
                try:
                    total += f.stat().st_size
                except OSError:
                    pass
        return total

    def delete_session(self, session_id: str) -> bool:
        """Permanently delete a session directory and remove from memory.

        Returns True if the session existed and was deleted.
        """
        session = self._sessions.pop(session_id, None)
        self._pending_approval.discard(session_id)
        session_dir = self._session_dir(session_id)
        if session_dir.is_dir():
            shutil.rmtree(session_dir)
            logger.info("Deleted session %s", session_id)
            return True
        return session is not None

    async def archive(self, session_id: str) -> SessionState | None:
        """Archive a session (hide from active/complete views)."""
        session = self._sessions.get(session_id)
        if session is None:
            return None
        session.archived = True
        session.updated_at = datetime.now(timezone.utc)
        self._write_session_file(session)
        await self._broadcast(session)
        return session

    async def unarchive(self, session_id: str) -> SessionState | None:
        """Unarchive a session."""
        session = self._sessions.get(session_id)
        if session is None:
            return None
        session.archived = False
        session.updated_at = datetime.now(timezone.utc)
        self._write_session_file(session)
        await self._broadcast(session)
        return session

    async def mark_complete(self, session_id: str) -> SessionState | None:
        """Manually mark a session as all_done."""
        session = self._sessions.get(session_id)
        if session is None:
            return None
        session.state = MonitorState.ALL_DONE
        session.raw_event = "ManualComplete"
        session.raw_detail = None
        session.updated_at = datetime.now(timezone.utc)
        self._write_session_file(session)
        await self._broadcast(session)
        return session

    async def broadcast_event(self, event_type: str, data: dict) -> None:
        """Broadcast an arbitrary event to all SSE subscribers."""
        payload = {"type": event_type, "data": data}
        dead: list[asyncio.Queue] = []
        for q in self._queues:
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                dead.append(q)
        for q in dead:
            self.unsubscribe(q)

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

    async def broadcast_pairing_request(self, request: dict) -> None:
        """Broadcast a pairing_request event to all SSE subscribers."""
        payload = json.dumps(request)
        dead: list[asyncio.Queue] = []
        for q in self._queues:
            try:
                q.put_nowait({"type": "pairing_request", "data": payload})
            except asyncio.QueueFull:
                dead.append(q)
        for q in dead:
            self.unsubscribe(q)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _write_session_file(self, session: SessionState) -> None:
        """Persist session state to <session_dir>/session.json."""
        session_dir = self._session_dir(session.session_id)
        session_dir.mkdir(parents=True, exist_ok=True)
        file_path = session_dir / "session.json"
        file_path.write_text(json.dumps(session.to_dict(), indent=2))

    # Maximum age (seconds) for two identical-type messages to be
    # considered duplicates.  Guards against double-firing when hooks
    # are installed at both project and global level.
    _MSG_DEDUP_WINDOW = 3.0

    def _save_message(self, session_id: str, msg: Message) -> None:
        """Write a single message to msg_<ts>.json in the session dir.

        Deduplicates: if the most recent message of the same type has
        identical content/tool_name and was saved within the dedup
        window, the new one is silently dropped.
        """
        session_dir = self._session_dir(session_id)
        session_dir.mkdir(parents=True, exist_ok=True)

        # Check for duplicate
        existing_files = sorted(session_dir.glob("msg_*.json"), reverse=True)
        for fp in existing_files:
            try:
                prev = json.loads(fp.read_text())
            except (json.JSONDecodeError, ValueError):
                continue
            if prev.get("type") != msg.type:
                continue
            same_content = (prev.get("content") == msg.content)
            same_tool = (prev.get("tool_name") == msg.tool_name)
            if same_content and same_tool:
                age = msg.timestamp - prev.get("timestamp", 0)
                if 0 < age < self._MSG_DEDUP_WINDOW:
                    return  # duplicate, skip
            break  # only check the most recent message of this type

        ts_str = f"{msg.timestamp:.6f}"
        file_path = session_dir / f"msg_{ts_str}.json"
        file_path.write_text(json.dumps(msg.to_dict(), indent=2))

    def _remove_skeletons(self, session_id: str, correlation_key: str) -> None:
        """Delete skeleton message files matching the given correlation key."""
        session_dir = self._session_dir(session_id)
        if not session_dir.is_dir():
            return
        for fp in sorted(session_dir.glob("msg_*.json")):
            try:
                data = json.loads(fp.read_text())
            except (json.JSONDecodeError, ValueError):
                continue
            if data.get("skeleton") or data.get("preliminary"):
                # Match tool_name for tools, type otherwise
                if data.get("type") == "tool_use":
                    ck = data.get("tool_name")
                elif data.get("type") == "pending_approval":
                    ck = "pending_approval"
                else:
                    ck = data.get("type")
                if ck == correlation_key:
                    fp.unlink()
                    logger.debug("Removed skeleton %s for %s", fp.name, correlation_key)

    def _update_skeleton(
        self, session_id: str, correlation_key: str, update: Message
    ) -> None:
        """Update an existing skeleton file in-place — used for thinking
        consolidation.  No-op if no matching skeleton is found."""
        session_dir = self._session_dir(session_id)
        if not session_dir.is_dir():
            return
        for fp in sorted(session_dir.glob("msg_*.json"), reverse=True):
            try:
                data = json.loads(fp.read_text())
            except (json.JSONDecodeError, ValueError):
                continue
            if not (data.get("skeleton") or data.get("preliminary")):
                continue
            if data.get("type") != correlation_key:
                continue
            # Found the skeleton — update it in-place
            merged = update.to_dict()
            # Preserve original timestamp and type
            merged["timestamp"] = data["timestamp"]
            merged["type"] = data["type"]
            # Merge content: keep skeleton content if update has none
            if not merged.get("content"):
                merged["content"] = data.get("content")
            fp.write_text(json.dumps(merged, indent=2))
            logger.debug("Consolidated skeleton %s for %s", fp.name, correlation_key)
            return

    def _count_messages(self, session_id: str) -> int:
        """Count message files in a session directory."""
        session_dir = self._session_dir(session_id)
        if not session_dir.is_dir():
            return 0
        return len(list(session_dir.glob("msg_*.json")))

    @staticmethod
    def _empty_stats() -> dict:
        return {
            "total_prompts": 0,
            "total_assistant_messages": 0,
            "total_tool_calls": 0,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "tool_breakdown": {},
            "session_start": None,
            "session_end": None,
            "duration_seconds": 0,
        }

    @staticmethod
    def _extract_tokens(raw: dict) -> tuple[int | None, int | None]:
        """Try to extract token counts from various possible locations.

        Claude Code hook events may or may not include usage data, and the
        field path varies across versions.  Fall back to a rough estimate
        from content length so the stats display is never blank.
        """
        # Path 1: nested "usage" object
        usage = raw.get("usage") or {}
        if isinstance(usage, dict):
            i = usage.get("input_tokens")
            o = usage.get("output_tokens")
            if i is not None or o is not None:
                return i, o

        # Path 2: top-level flat keys
        i = raw.get("input_tokens")
        o = raw.get("output_tokens")
        if i is not None or o is not None:
            return i, o

        # Path 3: Anthropic-style nested under "message"
        msg = raw.get("message") or {}
        if isinstance(msg, dict):
            u = msg.get("usage") or {}
            if isinstance(u, dict):
                i = u.get("input_tokens")
                o = u.get("output_tokens")
                if i is not None or o is not None:
                    return i, o

        # Path 4: estimate from content text (rough: 3.5 chars/token)
        content = raw.get("prompt") or raw.get("last_assistant_message") or ""
        if isinstance(content, str) and content.strip():
            estimated = max(1, int(len(content) / 3.5))
            return estimated, estimated

        return None, None

    @staticmethod
    def _estimate_text_tokens(text: str | None) -> int:
        """Rough token estimate from text length (~3.5 chars/token for English)."""
        if not text or not isinstance(text, str):
            return 0
        return max(1, int(len(text) / 3.5))

    @staticmethod
    def _event_to_message(raw: dict) -> Message | list[Message] | None:
        """Create Message(s) from a hook event dict. Returns None if not applicable."""
        hook_event_name = raw.get("hook_event_name", "")
        ts = time.time()

        if hook_event_name == "UserPromptSubmit":
            prompt = raw.get("prompt", "")
            in_tok, out_tok = StateManager._extract_tokens(raw)
            return [
                Message(
                    timestamp=ts,
                    type="user_prompt",
                    content=prompt.strip() if prompt else None,
                    input_tokens=in_tok,
                    source="UserPromptSubmit",
                ),
                Message(
                    timestamp=ts + 0.0001,
                    type="thinking",
                    content="Thinking…",
                    skeleton=True,
                    source="UserPromptSubmit",
                ),
            ]

        if hook_event_name == "PreToolUse":
            tool_name = raw.get("tool_name", "")
            return Message(
                timestamp=ts,
                type="tool_use",
                tool_name=tool_name or None,
                content="Executing…",
                skeleton=True,
                source="PreToolUse",
            )

        if hook_event_name == "Stop":
            msg_text = raw.get("last_assistant_message", "")
            in_tok, out_tok = StateManager._extract_tokens(raw)
            # Thinking message consolidates the skeleton (no new file — caller
            # updates the skeleton file in-place).  assistant_response is new.
            return [
                Message(
                    timestamp=ts - 0.001,
                    type="thinking",
                    input_tokens=in_tok,
                    skeleton=False,
                    source="Stop",
                ),
                Message(
                    timestamp=ts,
                    type="assistant_response",
                    content=msg_text.strip() if msg_text else None,
                    input_tokens=in_tok,
                    output_tokens=out_tok,
                    source="Stop",
                ),
            ]

        if hook_event_name == "PostToolUse":
            tool_name = raw.get("tool_name", "")
            tool_input_raw = raw.get("tool_input", {})
            tool_output_raw = raw.get("tool_output", "")

            # Serialize tool_input for storage if it's a dict/object
            if isinstance(tool_input_raw, dict):
                tool_input = json.dumps(tool_input_raw)
            elif isinstance(tool_input_raw, str):
                tool_input = tool_input_raw
            else:
                tool_input = str(tool_input_raw) if tool_input_raw else None

            # Truncate large fields
            if tool_input and len(tool_input) > _MAX_TOOL_FIELD_LENGTH:
                tool_input = tool_input[:_MAX_TOOL_FIELD_LENGTH] + "…"

            if isinstance(tool_output_raw, str) and len(tool_output_raw) > _MAX_TOOL_FIELD_LENGTH:
                tool_output = tool_output_raw[:_MAX_TOOL_FIELD_LENGTH] + "…"
            elif isinstance(tool_output_raw, str):
                tool_output = tool_output_raw
            elif tool_output_raw is not None:
                tool_output = str(tool_output_raw)
            else:
                tool_output = None

            # Estimate tokens from tool I/O (these count as context/input)
            ti_tokens = StateManager._estimate_text_tokens(tool_input)
            to_tokens = StateManager._estimate_text_tokens(tool_output)

            return Message(
                timestamp=ts,
                type="tool_use",
                tool_name=tool_name or None,
                tool_input=tool_input,
                tool_output=tool_output,
                input_tokens=(ti_tokens + to_tokens) or None,
                source="PostToolUse",
            )

        if hook_event_name == "PermissionRequest":
            tool_name = raw.get("tool_name", "")
            return Message(
                timestamp=ts,
                type="pending_approval",
                tool_name=tool_name or None,
                content="Waiting for approval…",
                skeleton=True,
                source="PermissionRequest",
            )

        if hook_event_name == "Notification":
            notification_type = raw.get("notification_type", "")
            if notification_type == "permission_prompt":
                return Message(
                    timestamp=ts,
                    type="pending_approval",
                    content="Waiting for approval…",
                    skeleton=True,
                    source="Notification",
                )

        return None

    async def _broadcast_message(self, payload: dict) -> None:
        """Send a message_update event to all SSE subscribers."""
        dead: list[asyncio.Queue] = []
        for q in self._queues:
            try:
                q.put_nowait({"type": "message_update", "data": payload})
            except asyncio.QueueFull:
                dead.append(q)
        for q in dead:
            self.unsubscribe(q)

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

    async def _expire_reviews_loop(self) -> None:
        """Periodically flip stale PENDING_REVIEW sessions to IDLE."""
        while True:
            await asyncio.sleep(_REVIEW_CHECK_INTERVAL)
            now = datetime.now(timezone.utc)
            expired = []
            for sid, session in self._sessions.items():
                if session.state == MonitorState.PENDING_REVIEW:
                    if now - session.updated_at >= _REVIEW_TIMEOUT:
                        expired.append(sid)
            for sid in expired:
                session = self._sessions[sid]
                session.state = MonitorState.IDLE
                session.raw_event = "ReviewTimeout"
                session.updated_at = now
                self._write_session_file(session)
                await self._broadcast(session)
                logger.info("Expired PENDING_REVIEW session %s → IDLE", sid)
