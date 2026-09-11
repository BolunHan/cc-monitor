"""Session state management — in-memory store, file persistence, SSE fan-out."""

import asyncio
import json
import logging
import shutil
import time
import uuid
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

# Max length of a single tool_input field echoed to a UI for approval.
# Long values are truncated rather than dropped, so the reviewer still sees
# the shape of what they are approving.
_MAX_REQUEST_FIELD_LENGTH = 4000

# Max length of one detail block. Deliberately far larger than
# _MAX_REQUEST_FIELD_LENGTH: a detail block is the thing being reviewed, and
# approving a file write you cannot read is not a review. Truncation is always
# flagged so the client can say so rather than silently showing a prefix.
_MAX_DETAIL_LENGTH = 20000

# Cap on the structured approval payload carried by a timeline message. Must
# comfortably exceed _MAX_DETAIL_LENGTH, since it wraps the detail blocks.
_MAX_APPROVAL_PAYLOAD_LENGTH = 24000

# Tools whose PermissionRequest is really "the agent is asking a question"
# rather than "the agent wants to run something".  They carry their own
# answer options, so the UI renders them differently.
_QUESTION_TOOLS = {"AskUserQuestion"}
_PLAN_TOOLS = {"ExitPlanMode"}

# How long a PermissionRequest hook should hold the terminal dialog open
# waiting for a remote decision, when at least one UI is watching.
#
# Set to the ceiling in _MAX_HOLD_SECONDS deliberately. The whole point of
# gating on a connected UI is that someone is watching remotely and may need
# time to reach a phone or another machine; five minutes turned out to be too
# short to be useful, and there is no cost to the terminal user here because
# the hold does not apply at all when nobody is connected.
_DEFAULT_HOLD_SECONDS = 540.0

# How long a Stop hook should linger at the end of a turn, waiting for a
# directive to arrive from a UI, before letting the turn end normally.
#
# Deliberately much shorter than the approval hold: this pause is felt by
# whoever is sitting at the terminal, and its only purpose is to catch a
# follow-up typed while the agent is finishing. It also means the agent is
# frozen mid-transition, so it must not be long.
_DEFAULT_DIRECTIVE_HOLD_SECONDS = 45.0


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
class PendingRequest:
    """A decision an agent is blocked on, waiting for a human.

    Created when a PermissionRequest hook reports in, and resolved either by a
    UI (via ``POST /api/session/{id}/respond``) or by the hook giving up and
    letting the local terminal dialog take over.

    ``kind`` tells the UI how to render the affordance:

    * ``permission`` — allow / deny
    * ``question``   — the agent asked a multiple-choice question; answer with
      one of ``options``
    * ``plan``       — the agent presented a plan; approve / reject
    """

    request_id: str
    kind: str
    tool_name: str | None = None
    tool_input: dict | None = None
    preview: str | None = None
    # Flattened choices — every option of every question, each tagged with the
    # question it belongs to. Enough for a client that only ever answers one
    # question, or renders a simple list.
    options: list[dict] = field(default_factory=list)
    # Grouped choices, one entry per question. A client must use this (rather
    # than `options`) to answer a multi-question call, because Claude Code
    # requires an answer for every question in the call.
    questions: list[dict] = field(default_factory=list)
    # What is actually being asked for, in labelled blocks any client can
    # render without knowing tool semantics:
    #   {"label", "value", "kind": "code"|"text"|"diff", "truncated"}
    details: list[dict] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    expires_at: float | None = None
    # Whether a hook is currently blocked waiting for this answer. If no hook
    # is holding, the answer is best-effort: it can still be delivered, but
    # nothing is gated on it.
    holding: bool = False

    def to_dict(self) -> dict:
        return {
            "request_id": self.request_id,
            "kind": self.kind,
            "tool_name": self.tool_name,
            "tool_input": self.tool_input,
            "preview": self.preview,
            "options": self.options,
            "questions": self.questions,
            "details": self.details,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "holding": self.holding,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PendingRequest":
        return cls(
            request_id=data["request_id"],
            kind=data.get("kind", "permission"),
            tool_name=data.get("tool_name"),
            tool_input=data.get("tool_input"),
            preview=data.get("preview"),
            options=data.get("options") or [],
            questions=data.get("questions") or [],
            details=data.get("details") or [],
            created_at=data.get("created_at", time.time()),
            expires_at=data.get("expires_at"),
            holding=bool(data.get("holding", False)),
        )


@dataclass
class Directive:
    """A message a user pushed into a session from a UI."""

    directive_id: str
    text: str
    created_at: float = field(default_factory=time.time)
    delivered_at: float | None = None
    via: str | None = None  # "hook" | "socket" — how it actually got in

    def to_dict(self) -> dict:
        return {
            "directive_id": self.directive_id,
            "text": self.text,
            "created_at": self.created_at,
            "delivered_at": self.delivered_at,
            "via": self.via,
        }


def _build_request_preview(tool_name: str | None, tool_input: dict | None) -> str:
    """One-line human summary of a pending tool call.

    Best-effort by design: tool_input shapes vary per tool and change between
    Claude Code releases, so anything unrecognised falls back to a compact
    JSON dump rather than rendering nothing.
    """
    if not isinstance(tool_input, dict):
        return tool_name or ""

    if tool_name == "Bash":
        return str(tool_input.get("command", ""))[:_MAX_REQUEST_FIELD_LENGTH]
    if tool_name in ("Write", "Edit", "NotebookEdit", "Read"):
        path = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
        return str(path)
    if tool_name in ("WebFetch", "WebSearch"):
        return str(tool_input.get("url") or tool_input.get("query") or "")
    if tool_name in _PLAN_TOOLS:
        return "Plan ready for review"
    if tool_name in _QUESTION_TOOLS:
        questions = tool_input.get("questions") or []
        if isinstance(questions, list) and questions:
            first = questions[0]
            if isinstance(first, dict):
                return str(first.get("question", ""))
        return "Question"
    try:
        return json.dumps(tool_input, ensure_ascii=False)[:_MAX_REQUEST_FIELD_LENGTH]
    except (TypeError, ValueError):
        return str(tool_input)[:_MAX_REQUEST_FIELD_LENGTH]


def _extract_options(tool_name: str | None, tool_input: dict | None) -> list[dict]:
    """Pull answer options out of a tool call, if it has any.

    Returns a list of ``{"label", "description", "header"}`` dicts — an
    intentionally flat shape so both the web UI and the Android client can
    render it without knowing which agent produced it.
    """
    if not isinstance(tool_input, dict):
        return []

    options: list[dict] = []

    if tool_name in _QUESTION_TOOLS:
        questions = tool_input.get("questions") or []
        if isinstance(questions, list):
            for q in questions:
                if not isinstance(q, dict):
                    continue
                header = q.get("header") or q.get("question") or ""
                for opt in q.get("options") or []:
                    if not isinstance(opt, dict):
                        continue
                    options.append(
                        {
                            "label": opt.get("label", ""),
                            "description": opt.get("description", ""),
                            "question": q.get("question", ""),
                            "header": header,
                            "multi_select": bool(q.get("multiSelect", False)),
                        }
                    )
        return options

    if tool_name in _PLAN_TOOLS:
        # ExitPlanMode is a yes/no gate; present it as such.
        return [
            {"label": "Approve", "description": "", "action": "allow", "header": "plan"},
            {"label": "Reject", "description": "", "action": "deny", "header": "plan"},
        ]

    return options


def _clip(value: str, limit: int = _MAX_DETAIL_LENGTH) -> tuple[str, bool]:
    """Truncate a detail value, reporting whether it was truncated."""
    if len(value) <= limit:
        return value, False
    return value[:limit] + f"\n… [{len(value) - limit} more characters]", True


def _block(label: str, value: object, kind: str = "code") -> dict | None:
    """One labelled detail block, or None when there is nothing to show."""
    if value is None:
        return None
    text = value if isinstance(value, str) else str(value)
    if not text.strip():
        return None
    clipped, truncated = _clip(text)
    return {"label": label, "value": clipped, "kind": kind, "truncated": truncated}


def _diff_text(old: object, new: object) -> str:
    """Render a string replacement as unified-diff-ish lines.

    Emitted as plain text with +/- prefixes rather than an HTML diff so every
    client — web, Android, anything later — can style it the same way from one
    flat string.
    """
    old_lines = str(old or "").splitlines() or [""]
    new_lines = str(new or "").splitlines() or [""]
    return "\n".join(
        [f"- {line}" for line in old_lines] + [f"+ {line}" for line in new_lines]
    )


def _build_details(tool_name: str | None, tool_input: dict | None) -> list[dict]:
    """Presentation-ready view of *what is actually being asked for*.

    Built server-side, and tool-aware, for two reasons: the review content must
    reach every client identically (the Android app should not have to
    reimplement Claude Code's tool semantics), and `preview` alone is not
    enough to review — it is a one-line summary, so a file write showed only a
    path and a plan showed nothing at all.

    Unknown tools fall back to the raw input rather than showing nothing: an
    unlabelled JSON dump is still reviewable, an empty panel is not.
    """
    if not isinstance(tool_input, dict):
        return []

    if tool_name in _QUESTION_TOOLS:
        # The questions are the content and are transmitted separately; a raw
        # input dump alongside them would be noise.
        return []

    def blocks(*candidates):
        return [b for b in candidates if b is not None]

    out: list[dict] = []

    if tool_name == "Bash":
        out = blocks(_block("Command", tool_input.get("command")),
                     _block("Description", tool_input.get("description"), "text"))
        if tool_input.get("run_in_background"):
            out.append({"label": "Runs in background", "value": "yes", "kind": "text", "truncated": False})

    elif tool_name == "Write":
        out = blocks(_block("File", tool_input.get("file_path")),
                     _block("Content being written", tool_input.get("content")))

    elif tool_name == "Edit":
        out = blocks(_block("File", tool_input.get("file_path")),
                     _block("Changes", _diff_text(tool_input.get("old_string"), tool_input.get("new_string")), "diff"))
        if tool_input.get("replace_all"):
            out.append({"label": "Replace all occurrences", "value": "yes", "kind": "text", "truncated": False})

    elif tool_name == "MultiEdit":
        edits = tool_input.get("edits") or []
        chunks = [
            _diff_text(e.get("old_string"), e.get("new_string"))
            for e in edits if isinstance(e, dict)
        ]
        out = blocks(_block("File", tool_input.get("file_path")),
                     _block("Changes", "\n\n".join(chunks), "diff"))

    elif tool_name == "NotebookEdit":
        out = blocks(_block("Notebook", tool_input.get("notebook_path")),
                     _block("Cell", tool_input.get("cell_id")),
                     _block("New source", tool_input.get("new_source")))

    elif tool_name == "Read":
        out = blocks(_block("File", tool_input.get("file_path")))
        span = []
        if tool_input.get("offset") is not None:
            span.append(f"from line {tool_input['offset']}")
        if tool_input.get("limit") is not None:
            span.append(f"limit {tool_input['limit']}")
        if span:
            out.append({"label": "Range", "value": ", ".join(span), "kind": "text", "truncated": False})

    elif tool_name in ("WebFetch", "WebSearch"):
        out = blocks(_block("URL", tool_input.get("url")),
                     _block("Query", tool_input.get("query"), "text"),
                     _block("Prompt", tool_input.get("prompt"), "text"))

    elif tool_name in _PLAN_TOOLS:
        # The whole point of this request is the plan; previously it was not
        # transmitted at all, so the review had nothing to review.
        out = blocks(_block("Plan", tool_input.get("plan"), "text"),
                     _block("Plan file", tool_input.get("planFilePath")))

    elif tool_name in ("Task", "Agent"):
        out = blocks(_block("Subagent", tool_input.get("subagent_type")),
                     _block("Prompt", tool_input.get("prompt"), "text"))

    elif tool_name == "TodoWrite":
        todos = tool_input.get("todos") or []
        lines = [
            f"[{t.get('status', '?')}] {t.get('content', '')}"
            for t in todos if isinstance(t, dict)
        ]
        out = blocks(_block("Todos", "\n".join(lines), "text"))

    if not out:
        # Unknown tool, or a known one whose fields were absent — fall back to
        # the raw input so the reviewer is never shown an empty panel.
        try:
            rendered = json.dumps(tool_input, indent=2, ensure_ascii=False)
        except (TypeError, ValueError):
            rendered = str(tool_input)
        out = blocks(_block("Input", rendered))

    return out


def _extract_questions(tool_input: dict | None) -> list[dict]:
    """Grouped view of an ``AskUserQuestion`` call: one entry per question.

    ``options`` is the flattened form (one entry per choice, each carrying its
    own question text), which is all a simple client needs. This grouped form
    is what a client needs to answer a *multi-question* call correctly: Claude
    Code expects an ``answers`` entry for every question in the call, so a UI
    working from the flattened list alone cannot tell when it has answered them
    all, and would submit a partial map.
    """
    if not isinstance(tool_input, dict):
        return []

    questions = tool_input.get("questions")
    if not isinstance(questions, list):
        return []

    out: list[dict] = []
    for q in questions:
        if not isinstance(q, dict):
            continue
        text = str(q.get("question", ""))
        opts = [
            {"label": str(o.get("label", "")), "description": str(o.get("description", ""))}
            for o in (q.get("options") or [])
            if isinstance(o, dict)
        ]
        out.append({
            "question": text,
            "header": str(q.get("header", "")),
            "multi_select": bool(q.get("multiSelect", False)),
            "options": opts,
        })
    return out


def _classify_request(tool_name: str | None) -> str:
    """Map a tool name to a PendingRequest kind."""
    if tool_name in _QUESTION_TOOLS:
        return "question"
    if tool_name in _PLAN_TOOLS:
        return "plan"
    return "permission"


def _safe_tool_input(tool_input: object) -> dict | None:
    """Coerce tool_input into a JSON-serialisable dict, truncating long values.

    The raw input can be arbitrarily large (a whole file for Write), and it is
    stored per-session on disk, so each field is capped.
    """
    if not isinstance(tool_input, dict):
        return None
    out: dict = {}
    for key, value in tool_input.items():
        if isinstance(value, str) and len(value) > _MAX_REQUEST_FIELD_LENGTH:
            out[key] = value[:_MAX_REQUEST_FIELD_LENGTH] + "…"
        else:
            out[key] = value
    return out


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
    agent: str = "claude"  # claude | dsh — which coding agent reported this session
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    message_count: int = 0  # cached count, updated on message write
    # A decision the agent is currently blocked on, if any.
    pending_request: PendingRequest | None = None
    # Set when a user asks for the current task to stop; the PreToolUse hook
    # reads it back and denies tool calls until the user prompts again.
    stop_requested: bool = False
    stop_reason: str | None = None
    # Directives queued from a UI but not yet delivered to the agent.
    queued_directives: list[Directive] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "cwd": self.cwd,
            "state": str(self.state),
            "raw_event": self.raw_event,
            "raw_detail": self.raw_detail,
            "summary": self.summary,
            "cc_monitor_uid": self.cc_monitor_uid,
            "agent": self.agent,
            "archived": self.archived,
            "updated_at": self.updated_at.isoformat(),
            "message_count": self.message_count,
            "pending_request": self.pending_request.to_dict() if self.pending_request else None,
            "stop_requested": self.stop_requested,
            "stop_reason": self.stop_reason,
            "queued_directives": [d.to_dict() for d in self.queued_directives],
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

        # --- control channel (view-only → bidirectional) ---
        # request_id → the future a blocked PermissionRequest hook is awaiting.
        # Resolved by a UI, or abandoned when the hook times out.
        self._decision_waiters: dict[str, asyncio.Future] = {}
        # session_id → messaging-socket descriptor reported by a hook. Lets the
        # server push a directive into an *idle* session, not just a stopping
        # one. See _deliver_via_socket().
        self._session_sockets: dict[str, dict] = {}
        # session_id → the future a Stop hook is parked on, waiting for a
        # directive to hand to the agent. Resolved by queue_directive().
        self._directive_waiters: dict[str, asyncio.Future] = {}

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
                "agent": data.get("agent", "claude"),
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
                    agent=data.get("agent", "claude"),
                    updated_at=datetime.fromisoformat(data["updated_at"]),
                    message_count=data.get("message_count", 0),
                    # Directives are user input and survive a restart.
                    queued_directives=[
                        Directive(
                            directive_id=d.get("directive_id", uuid.uuid4().hex[:12]),
                            text=d.get("text", ""),
                            created_at=d.get("created_at", time.time()),
                            delivered_at=d.get("delivered_at"),
                            via=d.get("via"),
                        )
                        for d in (data.get("queued_directives") or [])
                    ],
                    # A pending request is NOT restored: whatever hook was
                    # blocked on it died with the old server process, so the
                    # agent has already fallen back to its local dialog.
                    pending_request=None,
                    stop_requested=False,
                    stop_reason=None,
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

        # Hooks are the only place Claude Code's messaging-socket coordinates
        # are visible, so every event is an opportunity to refresh them.
        socket_path = raw.get("messaging_socket")
        if socket_path:
            self.set_session_socket(session_id, socket_path, raw.get("messaging_token", ""))

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

        # Notification(permission_prompt) fires alongside the PermissionRequest
        # that already recorded the real thing, and carries no details of its
        # own. Keeping both left the timeline with a contentless duplicate row
        # — literally "Approval needed / Waiting for approval… / Notification".
        if (
            hook_event_name == "Notification"
            and notification_type == "permission_prompt"
            and (self._sessions.get(session_id) is not None)
            and self._sessions[session_id].pending_request is not None
        ):
            msg_or_list = None

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

        # Preserve the reporting agent. DSH's plugin sends `agent: dsh`;
        # Claude Code hooks omit it and keep the historical default `claude`.
        raw_agent = raw.get("agent")
        if raw_agent in ("claude", "dsh"):
            agent = raw_agent
        else:
            agent = existing.agent if existing else "claude"

        session = SessionState(
            session_id=session_id,
            cwd=raw.get("cwd", ""),
            state=new_state,
            raw_event=hook_event_name,
            raw_detail=tool_name or notification_type,
            summary=summary,
            cc_monitor_uid=raw.get("cc_monitor_uid", existing.cc_monitor_uid if existing else ""),
            agent=agent,
            message_count=msg_count,
            # Control-channel state survives the per-event rebuild.
            stop_requested=existing.stop_requested if existing else False,
            stop_reason=existing.stop_reason if existing else None,
            queued_directives=list(existing.queued_directives) if existing else [],
        )
        self._sessions[session_id] = session

        # --- control channel ---
        if hook_event_name == "PermissionRequest":
            hold = self.hold_seconds_for(session_id)
            self.create_pending_request(session, raw, hold)
        elif hook_event_name in ("PreToolUse", "PostToolUse", "UserPromptSubmit"):
            # The tool proceeded (or a new turn began), so any outstanding
            # decision has been settled locally. Notification and Stop are
            # deliberately excluded: they arrive *around* a PermissionRequest
            # rather than after it, and clearing on them would drop live
            # requests before a UI ever saw them.
            session.pending_request = None
        elif existing is not None:
            session.pending_request = existing.pending_request

        if hook_event_name == "UserPromptSubmit":
            # A fresh prompt from the user supersedes an earlier stop.
            session.stop_requested = False
            session.stop_reason = None

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

    # ------------------------------------------------------------------
    # Control channel — pending requests
    # ------------------------------------------------------------------

    @property
    def subscriber_count(self) -> int:
        """Number of live SSE subscribers (web UI, Android app, ...)."""
        return len(self._queues)

    def hold_seconds_for(self, session_id: str) -> float:
        """How long a PermissionRequest hook should hold the terminal dialog.

        This is what keeps remote approval from ruining the local experience:
        if nobody is watching a UI, the hook must not stall the terminal, so we
        tell it to return immediately and let the local dialog appear as
        normal. When at least one UI *is* connected we hold, because someone
        may be about to answer from their phone.
        """
        if self.subscriber_count == 0:
            return 0.0
        return _DEFAULT_HOLD_SECONDS

    def create_pending_request(self, session: SessionState, raw: dict, hold_seconds: float) -> PendingRequest:
        """Register a decision the agent is blocked on, and attach it to the session."""
        tool_name = raw.get("tool_name")
        # Two views of the same input, with different budgets. `tool_input` is
        # the compact archival copy (cheap to persist and broadcast); `details`
        # is the review content and must not inherit that clip, or a file write
        # would be truncated long before _MAX_DETAIL_LENGTH ever applied.
        raw_input = raw.get("tool_input")
        tool_input = _safe_tool_input(raw_input)
        request = PendingRequest(
            request_id=uuid.uuid4().hex[:12],
            kind=_classify_request(tool_name),
            tool_name=tool_name,
            tool_input=tool_input,
            preview=_build_request_preview(tool_name, tool_input),
            options=_extract_options(tool_name, tool_input),
            questions=_extract_questions(tool_input),
            details=_build_details(
                tool_name, raw_input if isinstance(raw_input, dict) else None
            ),
            expires_at=time.time() + hold_seconds if hold_seconds > 0 else None,
            holding=hold_seconds > 0,
        )
        session.pending_request = request
        return request

    def get_pending_request(self, session_id: str) -> PendingRequest | None:
        """Return the session's outstanding decision, if any."""
        session = self._sessions.get(session_id)
        return session.pending_request if session else None

    async def resolve_pending_request(
        self, session_id: str, request_id: str, decision: dict
    ) -> tuple[bool, str]:
        """Answer a pending request on behalf of a UI.

        Returns ``(delivered, reason)``. ``delivered`` is False when no hook is
        blocked any more — the answer is recorded and the request cleared, but
        the agent will have fallen back to its local dialog, so the caller
        should be told rather than left thinking it worked.
        """
        session = self._sessions.get(session_id)
        if session is None:
            return False, "unknown session"

        pending = session.pending_request
        if pending is None or pending.request_id != request_id:
            return False, "no such pending request"

        waiter = self._decision_waiters.get(request_id)
        holding = waiter is not None and not waiter.done()

        if holding and waiter is not None:
            waiter.set_result(decision)
            self._decision_waiters.pop(request_id, None)

        session.pending_request = None
        session.updated_at = datetime.now(timezone.utc)
        self._write_session_file(session)
        await self._broadcast(session)
        return (True, "delivered") if holding else (False, "no hook waiting")

    async def await_decision(self, request_id: str, timeout: float) -> dict | None:
        """Block until a UI answers ``request_id``, or ``timeout`` elapses.

        Returns the decision dict, or None on timeout — in which case the
        caller must fall back to whatever the local behaviour is.
        """
        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        self._decision_waiters[request_id] = future
        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            return None
        finally:
            self._decision_waiters.pop(request_id, None)

    async def expire_pending_requests(self) -> None:
        """Mark requests whose hold window closed with no answer.

        The request is *kept* and flipped to ``holding = False`` rather than
        deleted. Deleting it left the card still reading "pending approval"
        with nothing to click and no explanation — the session state outlives
        the request, so the UI has to be able to say "this one is at the
        terminal now". It is cleared by the next real event, as any request is.
        """
        now = time.time()
        for session in list(self._sessions.values()):
            pending = session.pending_request
            if pending is None or pending.expires_at is None:
                continue
            if now < pending.expires_at:
                continue
            if pending.request_id in self._decision_waiters:
                continue  # still being held by a live hook
            pending.holding = False
            pending.expires_at = None  # don't re-evaluate it every tick
            self._write_session_file(session)
            await self._broadcast(session)

    # ------------------------------------------------------------------
    # Control channel — directives and stop
    # ------------------------------------------------------------------

    def hold_for_directive(self, session_id: str) -> float:
        """How long a Stop hook should linger waiting for a directive.

        Same bargain as the approval hold: only worth pausing the agent for if
        a UI is connected to type into. With nobody watching, the hook returns
        at once and the turn ends exactly as it would without cc-monitor.
        """
        if self.subscriber_count == 0:
            return 0.0
        return _DEFAULT_DIRECTIVE_HOLD_SECONDS

    async def await_directive(self, session_id: str, timeout: float) -> Directive | None:
        """Park until a directive is queued for ``session_id``, or time out.

        Returns the directive, or None if none arrived — in which case the
        caller must let the turn end normally.
        """
        directive = self.claim_directive(session_id)
        if directive is not None:
            return directive

        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        self._directive_waiters[session_id] = future
        try:
            await asyncio.wait_for(future, timeout=timeout)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            return None
        finally:
            self._directive_waiters.pop(session_id, None)
        return self.claim_directive(session_id)

    async def queue_directive(self, session_id: str, text: str) -> Directive:
        """Queue a directive for delivery to the agent."""
        session = self._sessions.get(session_id)
        directive = Directive(directive_id=uuid.uuid4().hex[:12], text=text)
        if session is not None:
            session.queued_directives.append(directive)
            session.updated_at = datetime.now(timezone.utc)
            self._write_session_file(session)
            await self._broadcast(session)

        # Wake a Stop hook that is holding the turn open for exactly this.
        waiter = self._directive_waiters.get(session_id)
        if waiter is not None and not waiter.done():
            waiter.set_result(True)
        return directive

    def claim_directive(self, session_id: str) -> Directive | None:
        """Pop the oldest undelivered directive, marking it delivered.

        Called by a Stop hook, so the directive rides back to the agent as hook
        feedback rather than sitting in the queue until the user is prompted
        again.
        """
        session = self._sessions.get(session_id)
        if session is None:
            return None
        for directive in session.queued_directives:
            if directive.delivered_at is None:
                directive.delivered_at = time.time()
                directive.via = "hook"
                self._write_session_file(session)
                return directive
        return None

    def get_directive(self, session_id: str, directive_id: str) -> Directive | None:
        """Look up a specific directive by id."""
        session = self._sessions.get(session_id)
        if session is None:
            return None
        for directive in session.queued_directives:
            if directive.directive_id == directive_id:
                return directive
        return None

    async def request_stop(self, session_id: str, reason: str | None = None) -> bool:
        """Ask a session to stop working.

        Enforcement is cooperative and happens in the PreToolUse hook, which
        reads the flag back and denies tool calls. That is the only mechanism
        available: Claude Code exposes no external interrupt.
        """
        session = self._sessions.get(session_id)
        if session is None:
            return False
        session.stop_requested = True
        session.stop_reason = reason or "Stopped from cc-monitor"
        session.updated_at = datetime.now(timezone.utc)
        self._write_session_file(session)
        await self._broadcast(session)
        return True

    async def clear_stop(self, session_id: str) -> None:
        """Clear a stop request — a fresh user prompt overrides it."""
        session = self._sessions.get(session_id)
        if session is None or not session.stop_requested:
            return
        session.stop_requested = False
        session.stop_reason = None
        self._write_session_file(session)
        await self._broadcast(session)

    def is_stop_requested(self, session_id: str) -> bool:
        """Whether a stop has been requested and not yet cleared."""
        session = self._sessions.get(session_id)
        return bool(session and session.stop_requested)

    # ------------------------------------------------------------------
    # Control channel — messaging sockets
    # ------------------------------------------------------------------

    def set_session_socket(self, session_id: str, path: str, token: str) -> None:
        """Remember a session's Claude Code messaging socket.

        Reported by the hooks, which are the only place these values are
        visible (Claude Code exports them into the hook environment). Holding
        them lets the server push a directive into an idle session instead of
        waiting for it to stop.
        """
        if not path:
            return
        self._session_sockets[session_id] = {"path": path, "token": token, "seen": time.time()}

    def get_session_socket(self, session_id: str) -> dict | None:
        """Return this session's messaging-socket descriptor, if known."""
        return self._session_sockets.get(session_id)

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
            raw_input = raw.get("tool_input")
            if not isinstance(raw_input, dict):
                raw_input = None

            # The timeline used to record only "Waiting for approval…" and the
            # tool name, so the historical record of *what was asked* was the
            # one thing missing from it — a question's body, a plan's text and
            # a file's contents never reached it at all. Carry the same
            # structured payload the live card uses, so the timeline can render
            # it with the same renderer.
            payload = {
                "kind": _classify_request(tool_name),
                "preview": _build_request_preview(tool_name, raw_input),
                "details": _build_details(tool_name, raw_input),
                "questions": _extract_questions(raw_input),
            }
            rendered = json.dumps(payload, ensure_ascii=False)
            if len(rendered) > _MAX_APPROVAL_PAYLOAD_LENGTH:
                rendered = rendered[:_MAX_APPROVAL_PAYLOAD_LENGTH] + "…"

            return Message(
                timestamp=ts,
                type="pending_approval",
                tool_name=tool_name or None,
                content=payload["preview"] or "Waiting for approval…",
                tool_input=rendered,
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
            await self.expire_pending_requests()
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
