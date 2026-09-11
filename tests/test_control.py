"""Tests for the bidirectional control channel (pending requests, directives, stop).

These cover the contract between three parties:

    hook  --(POST /api/event)-->  server  --(SSE state_update)-->  UI
    UI    --(POST .../respond)-->  server  --(GET .../decision)-->  hook

Expected values are derived from the documented protocol rather than from the
implementation: a decision is only "delivered" when some caller is genuinely
blocked waiting for it, and every degraded path (no UI watching, hook gave up,
server restarted) must leave the agent's local behaviour untouched.
"""

import asyncio
import json
import sys
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from cc_monitor.server import create_app
from cc_monitor.state import StateManager

# The hook helpers are stdlib-only scripts, deliberately not part of the
# installed package, so they are reached by path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))
import _common  # noqa: E402


def _perm_event(**overrides) -> dict:
    """A minimal but realistic PermissionRequest hook payload."""
    event = {
        "session_id": "s1",
        "cwd": "/home/user/project",
        "hook_event_name": "PermissionRequest",
        "tool_name": "Bash",
        "tool_input": {"command": "rm -rf build/"},
    }
    event.update(overrides)
    return event


@pytest.fixture
def manager(tmp_path):
    return StateManager(data_dir=tmp_path)


@pytest.fixture
def app(tmp_path):
    return create_app(data_dir=tmp_path)


def _client(app):
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


class TestPendingRequestRegistration:
    """Contract: a PermissionRequest event publishes an answerable decision.

    The UI must be able to render *what* is being asked without guessing, so
    the request carries a normalised kind, a human preview, and — for prompts
    that have their own options — those options.

    Derivation: kind/preview/options are read back off the same payload the
    server received, so every assertion is checkable against the input by hand.
    """

    @pytest.mark.asyncio
    async def test_00_permission_request_publishes_request(self, app):
        async with _client(app) as client:
            resp = await client.post("/api/event", json=_perm_event())
            data = resp.json()

        req = data["pending_request"]
        assert req is not None
        assert req["kind"] == "permission"
        assert req["tool_name"] == "Bash"
        # The preview is what a phone shows — it must be the command itself.
        assert req["preview"] == "rm -rf build/"
        assert req["options"] == []

    @pytest.mark.asyncio
    async def test_01_request_id_is_published_in_control_block(self, app):
        """The hook needs the id back to poll for the answer."""
        async with _client(app) as client:
            resp = await client.post("/api/event", json=_perm_event())
            data = resp.json()

        control = data["control"]
        assert control["request_id"] == data["pending_request"]["request_id"]
        assert control["request_id"]

    @pytest.mark.asyncio
    async def test_02_ask_user_question_is_classified_as_question(self, app):
        """AskUserQuestion is answered by option label, not allow/deny."""
        payload = _perm_event(
            tool_name="AskUserQuestion",
            tool_input={
                "questions": [
                    {
                        "question": "Which database?",
                        "header": "DB",
                        "multiSelect": False,
                        "options": [
                            {"label": "Postgres", "description": "Relational"},
                            {"label": "SQLite", "description": "Embedded"},
                        ],
                    }
                ]
            },
        )
        async with _client(app) as client:
            data = (await client.post("/api/event", json=payload)).json()

        req = data["pending_request"]
        assert req["kind"] == "question"
        assert [o["label"] for o in req["options"]] == ["Postgres", "SQLite"]
        assert req["options"][0]["question"] == "Which database?"
        assert req["preview"] == "Which database?"

    @pytest.mark.asyncio
    async def test_03_exit_plan_mode_is_classified_as_plan(self, app):
        payload = _perm_event(tool_name="ExitPlanMode", tool_input={"plan": "# Do the thing"})
        async with _client(app) as client:
            data = (await client.post("/api/event", json=payload)).json()

        req = data["pending_request"]
        assert req["kind"] == "plan"
        assert [o["label"] for o in req["options"]] == ["Approve", "Reject"]

    @pytest.mark.asyncio
    async def test_04_long_tool_input_is_truncated(self, app):
        """tool_input is persisted per session, so a huge value must not land on disk whole."""
        payload = _perm_event(tool_input={"command": "x" * 50000})
        async with _client(app) as client:
            data = (await client.post("/api/event", json=payload)).json()

        stored = data["pending_request"]["tool_input"]["command"]
        assert len(stored) < 5000
        assert stored.startswith("x" * 100)

    @pytest.mark.asyncio
    async def test_05_pre_tool_use_clears_outstanding_request(self, app):
        """The tool ran, so the decision is settled — a stale prompt must not linger."""
        async with _client(app) as client:
            await client.post("/api/event", json=_perm_event())
            data = (
                await client.post(
                    "/api/event",
                    json={
                        "session_id": "s1",
                        "cwd": "/home/user/project",
                        "hook_event_name": "PreToolUse",
                        "tool_name": "Bash",
                    },
                )
            ).json()

        assert data["pending_request"] is None

    @pytest.mark.asyncio
    async def test_06_notification_does_not_clear_outstanding_request(self, app):
        """Regression guard: Notification(permission_prompt) arrives *with* the
        request, not after it. Clearing on it would drop every live prompt
        before a UI ever saw one."""
        async with _client(app) as client:
            await client.post("/api/event", json=_perm_event())
            data = (
                await client.post(
                    "/api/event",
                    json={
                        "session_id": "s1",
                        "cwd": "/home/user/project",
                        "hook_event_name": "Notification",
                        "notification_type": "permission_prompt",
                    },
                )
            ).json()

        assert data["pending_request"] is not None
        assert data["pending_request"]["tool_name"] == "Bash"


class TestRequestDetail:
    """Contract: a pending request carries enough content to actually review.

    This is the whole point of the feature. `preview` is a one-line summary —
    a file write showed only a path and a plan showed nothing at all — so
    `details` carries labelled blocks built server-side, which is also what
    lets the Android client render them identically without reimplementing
    Claude Code's tool semantics.

    Derivation: each block is read back against the tool_input the server
    received, so expected values are taken from the payload, not the code.
    """

    @staticmethod
    def _details(blocks: list[dict]) -> dict:
        return {b["label"]: b for b in blocks}

    @pytest.mark.asyncio
    async def test_00_bash_exposes_the_command(self, app):
        async with _client(app) as client:
            req = (await client.post("/api/event", json=_perm_event())).json()["pending_request"]

        d = self._details(req["details"])
        assert d["Command"]["value"] == "rm -rf build/"
        assert d["Command"]["kind"] == "code"

    @pytest.mark.asyncio
    async def test_01_write_exposes_the_content(self, app):
        """The case that motivated this: approving a write blind."""
        payload = _perm_event(
            tool_name="Write",
            tool_input={"file_path": "/tmp/a.py", "content": "print('hello')\n"},
        )
        async with _client(app) as client:
            req = (await client.post("/api/event", json=payload)).json()["pending_request"]

        d = self._details(req["details"])
        assert d["File"]["value"] == "/tmp/a.py"
        assert d["Content being written"]["value"] == "print('hello')\n"

    @pytest.mark.asyncio
    async def test_02_edit_is_rendered_as_a_diff(self, app):
        payload = _perm_event(
            tool_name="Edit",
            tool_input={"file_path": "/tmp/a.py", "old_string": "old line", "new_string": "new line"},
        )
        async with _client(app) as client:
            req = (await client.post("/api/event", json=payload)).json()["pending_request"]

        changes = self._details(req["details"])["Changes"]
        assert changes["kind"] == "diff"
        assert changes["value"] == "- old line\n+ new line"

    @pytest.mark.asyncio
    async def test_03_multi_edit_concatenates_each_edit(self, app):
        payload = _perm_event(
            tool_name="MultiEdit",
            tool_input={
                "file_path": "/tmp/a.py",
                "edits": [
                    {"old_string": "one", "new_string": "1"},
                    {"old_string": "two", "new_string": "2"},
                ],
            },
        )
        async with _client(app) as client:
            req = (await client.post("/api/event", json=payload)).json()["pending_request"]

        assert self._details(req["details"])["Changes"]["value"] == "- one\n+ 1\n\n- two\n+ 2"

    @pytest.mark.asyncio
    async def test_04_plan_is_transmitted(self, app):
        """Previously the plan was not sent at all — nothing to review."""
        payload = _perm_event(
            tool_name="ExitPlanMode",
            tool_input={"plan": "# Step 1\nDo the thing", "planFilePath": "/tmp/plan.md"},
        )
        async with _client(app) as client:
            req = (await client.post("/api/event", json=payload)).json()["pending_request"]

        d = self._details(req["details"])
        assert d["Plan"]["value"] == "# Step 1\nDo the thing"
        assert d["Plan"]["kind"] == "text"
        assert d["Plan file"]["value"] == "/tmp/plan.md"

    @pytest.mark.asyncio
    async def test_05_unknown_tool_falls_back_to_raw_input(self, app):
        """An unlabelled JSON dump is still reviewable; an empty panel is not."""
        payload = _perm_event(tool_name="SomeFutureTool", tool_input={"alpha": 1, "beta": "two"})
        async with _client(app) as client:
            req = (await client.post("/api/event", json=payload)).json()["pending_request"]

        details = req["details"]
        assert len(details) == 1
        assert details[0]["label"] == "Input"
        assert '"alpha": 1' in details[0]["value"]

    @pytest.mark.asyncio
    async def test_06_large_content_is_flagged_when_truncated(self, app):
        big = "x" * 50000
        payload = _perm_event(tool_name="Write", tool_input={"file_path": "/tmp/big", "content": big})
        async with _client(app) as client:
            req = (await client.post("/api/event", json=payload)).json()["pending_request"]

        content = self._details(req["details"])["Content being written"]
        assert content["truncated"] is True
        assert "more characters" in content["value"]
        # Still far more than the one-line preview would ever have carried.
        assert len(content["value"]) > 10000

    @pytest.mark.asyncio
    async def test_07_small_content_is_not_flagged(self, app):
        payload = _perm_event(tool_name="Write", tool_input={"file_path": "/tmp/s", "content": "hi"})
        async with _client(app) as client:
            req = (await client.post("/api/event", json=payload)).json()["pending_request"]

        assert self._details(req["details"])["Content being written"]["truncated"] is False

    @pytest.mark.asyncio
    async def test_08_absent_optional_fields_produce_no_empty_blocks(self, app):
        payload = _perm_event(tool_name="Bash", tool_input={"command": "ls"})
        async with _client(app) as client:
            req = (await client.post("/api/event", json=payload)).json()["pending_request"]

        labels = [b["label"] for b in req["details"]]
        assert labels == ["Command"]
        assert all(b["value"].strip() for b in req["details"])

    @pytest.mark.asyncio
    async def test_09_question_requests_carry_no_tool_detail(self, app):
        """AskUserQuestion's content is the questions, not the raw input."""
        payload = _perm_event(
            tool_name="AskUserQuestion",
            tool_input={"questions": [{"question": "Which?", "options": [{"label": "A"}]}]},
        )
        async with _client(app) as client:
            req = (await client.post("/api/event", json=payload)).json()["pending_request"]

        assert req["details"] == []
        assert req["questions"][0]["question"] == "Which?"


class TestQuestionGrouping:
    """Contract: a multi-question AskUserQuestion is answerable in full.

    Claude Code expects an `answers` entry for *every* question in a call. The
    flattened `options` list cannot express which question an option belongs to
    in a way that tells a client when it has answered them all, so the request
    also carries `questions`, grouped one entry per question.

    Derivation: counts and groupings are read straight back off the posted
    tool_input, so each assertion is checkable by hand against the payload.
    """

    @staticmethod
    def _ask(questions: list) -> dict:
        return _perm_event(
            tool_name="AskUserQuestion", tool_input={"questions": questions}
        )

    @pytest.mark.asyncio
    async def test_00_single_question_is_grouped(self, app):
        payload = self._ask([{
            "question": "Which database?",
            "header": "DB",
            "multiSelect": False,
            "options": [
                {"label": "Postgres", "description": "Relational"},
                {"label": "SQLite", "description": "Embedded"},
            ],
        }])
        async with _client(app) as client:
            req = (await client.post("/api/event", json=payload)).json()["pending_request"]

        assert len(req["questions"]) == 1
        q = req["questions"][0]
        assert q["question"] == "Which database?"
        assert q["header"] == "DB"
        assert q["multi_select"] is False
        assert [o["label"] for o in q["options"]] == ["Postgres", "SQLite"]
        assert q["options"][0]["description"] == "Relational"

    @pytest.mark.asyncio
    async def test_01_two_questions_stay_separate(self, app):
        """The case the flattened list cannot express."""
        payload = self._ask([
            {
                "question": "Which database?",
                "header": "DB",
                "options": [{"label": "Postgres"}, {"label": "SQLite"}],
            },
            {
                "question": "Which region?",
                "header": "Region",
                "options": [{"label": "eu-west"}, {"label": "us-east"}],
            },
        ])
        async with _client(app) as client:
            req = (await client.post("/api/event", json=payload)).json()["pending_request"]

        assert [q["question"] for q in req["questions"]] == [
            "Which database?", "Which region?",
        ]
        assert [[o["label"] for o in q["options"]] for q in req["questions"]] == [
            ["Postgres", "SQLite"], ["eu-west", "us-east"],
        ]
        # The flat list is still there for simple clients, tagged per option.
        assert len(req["options"]) == 4
        assert {o["question"] for o in req["options"]} == {"Which database?", "Which region?"}

    @pytest.mark.asyncio
    async def test_02_multi_select_survives_grouping(self, app):
        payload = self._ask([{
            "question": "Which features?",
            "header": "Feat",
            "multiSelect": True,
            "options": [{"label": "auth"}, {"label": "billing"}],
        }])
        async with _client(app) as client:
            req = (await client.post("/api/event", json=payload)).json()["pending_request"]

        assert req["questions"][0]["multi_select"] is True
        assert req["options"][0]["multi_select"] is True

    @pytest.mark.asyncio
    async def test_03_non_question_requests_have_no_questions(self, app):
        async with _client(app) as client:
            req = (await client.post("/api/event", json=_perm_event())).json()["pending_request"]

        assert req["questions"] == []
        assert req["options"] == []

    @pytest.mark.asyncio
    async def test_04_malformed_questions_do_not_crash(self, app):
        """Degraded path: a caller must still get a permission request back."""
        payload = _perm_event(
            tool_name="AskUserQuestion",
            tool_input={"questions": ["not-a-dict", {"question": "ok?", "options": None}]},
        )
        async with _client(app) as client:
            resp = await client.post("/api/event", json=payload)

        assert resp.status_code == 200
        req = resp.json()["pending_request"]
        assert req["kind"] == "question"
        assert [q["question"] for q in req["questions"]] == ["ok?"]
        assert req["questions"][0]["options"] == []

    @pytest.mark.asyncio
    async def test_05_answers_for_every_question_reach_the_hook(self, manager):
        """The whole point: one respond carrying both answers."""
        payload = self._ask([
            {"question": "Which database?", "options": [{"label": "SQLite"}]},
            {"question": "Which region?", "options": [{"label": "eu-west"}]},
        ])
        session = await manager.handle_event(payload)
        request_id = session.pending_request.request_id
        waiter = asyncio.create_task(manager.await_decision(request_id, timeout=5.0))
        await asyncio.sleep(0)

        answers = {"Which database?": "SQLite", "Which region?": "eu-west"}
        delivered, _ = await manager.resolve_pending_request(
            "s1", request_id, {"behavior": "allow", "answers": answers}
        )

        assert delivered is True
        decision = await waiter
        assert decision["answers"] == answers


class TestApprovalTimelineMessage:
    """Contract: the timeline records *what was asked*, not just that something was.

    The stored `pending_approval` message used to carry a literal
    "Waiting for approval…" and nothing else, so the history showed
    "Approval needed / Waiting for approval…" with the question text, the plan
    and the file contents all absent. It now carries the same structured
    payload the live card renders.

    Derivation: the payload is parsed back out of the stored message and
    checked against the event that produced it.
    """

    @staticmethod
    def _approval_messages(manager, session_id="s1") -> list[dict]:
        messages, _ = manager.get_messages(session_id, offset=0, limit=50)
        return [m for m in messages if m.type == "pending_approval"]

    @pytest.mark.asyncio
    async def test_00_permission_message_carries_the_command(self, manager):
        await manager.handle_event(_perm_event())
        msgs = self._approval_messages(manager)

        assert len(msgs) == 1
        assert msgs[0].content == "rm -rf build/"
        payload = json.loads(msgs[0].tool_input)
        assert payload["details"][0]["value"] == "rm -rf build/"

    @pytest.mark.asyncio
    async def test_01_question_message_carries_the_question_and_options(self, manager):
        """The case reported: the question body was missing from the history."""
        await manager.handle_event(_perm_event(
            tool_name="AskUserQuestion",
            tool_input={"questions": [{
                "question": "Which database?",
                "header": "DB",
                "options": [
                    {"label": "Postgres", "description": "Relational"},
                    {"label": "SQLite", "description": "Embedded"},
                ],
            }]},
        ))
        payload = json.loads(self._approval_messages(manager)[0].tool_input)

        assert payload["kind"] == "question"
        assert payload["questions"][0]["question"] == "Which database?"
        assert [o["label"] for o in payload["questions"][0]["options"]] == ["Postgres", "SQLite"]
        assert payload["questions"][0]["options"][0]["description"] == "Relational"

    @pytest.mark.asyncio
    async def test_02_plan_message_carries_the_plan_text(self, manager):
        await manager.handle_event(_perm_event(
            tool_name="ExitPlanMode", tool_input={"plan": "# Step 1\nDo it"},
        ))
        payload = json.loads(self._approval_messages(manager)[0].tool_input)

        assert payload["details"][0]["label"] == "Plan"
        assert payload["details"][0]["value"] == "# Step 1\nDo it"

    @pytest.mark.asyncio
    async def test_03_notification_duplicate_is_suppressed(self, manager):
        """Notification(permission_prompt) carries no details of its own."""
        await manager.handle_event(_perm_event())
        await manager.handle_event({
            "session_id": "s1", "cwd": "/home/user/project",
            "hook_event_name": "Notification", "notification_type": "permission_prompt",
        })

        assert len(self._approval_messages(manager)) == 1

    @pytest.mark.asyncio
    async def test_04_notification_still_records_when_nothing_else_did(self, manager):
        """Don't lose the signal on a setup where PermissionRequest doesn't fire."""
        await manager.handle_event({
            "session_id": "s1", "cwd": "/home/user/project",
            "hook_event_name": "Notification", "notification_type": "permission_prompt",
        })

        assert len(self._approval_messages(manager)) == 1

    @pytest.mark.asyncio
    async def test_05_oversized_payload_is_capped(self, manager):
        await manager.handle_event(_perm_event(
            tool_name="Write",
            tool_input={"file_path": "/tmp/big", "content": "z" * 80000},
        ))
        stored = self._approval_messages(manager)[0].tool_input

        assert len(stored) <= 24001


class TestHoldNegotiation:
    """Contract: the terminal dialog is only deferred when someone is watching.

    A remote-approval feature that stalls the local terminal when no remote UI
    exists is strictly worse than no feature. The server therefore tells the
    hook how long to hold, and the answer is zero unless a UI is subscribed.
    """

    @pytest.mark.asyncio
    async def test_00_hold_is_zero_without_subscribers(self, app):
        async with _client(app) as client:
            data = (await client.post("/api/event", json=_perm_event())).json()

        assert data["control"]["hold_seconds"] == 0
        assert data["pending_request"]["holding"] is False

    @pytest.mark.asyncio
    async def test_01_hold_is_positive_with_a_subscriber(self, manager):
        """An attached SSE client is what unlocks remote approval."""
        queue = manager.subscribe()
        try:
            session = await manager.handle_event(_perm_event())
            assert manager.hold_seconds_for(session.session_id) > 0
        finally:
            manager.unsubscribe(queue)

    @pytest.mark.asyncio
    async def test_02_hold_returns_to_zero_when_subscriber_leaves(self, manager):
        queue = manager.subscribe()
        manager.unsubscribe(queue)
        assert manager.hold_seconds_for("s1") == 0


class TestDecisionRoundTrip:
    """Contract: an answer reaches a blocked hook exactly once, and a late
    answer is reported as late rather than silently accepted.

    Derivation: `delivered` must be True iff a waiter was registered. The
    distinguishing cases are (a) waiter present, (b) waiter absent, (c) waiter
    timed out — each produces a different observable outcome.
    """

    @pytest.mark.asyncio
    async def test_00_decision_reaches_a_waiting_caller(self, manager):
        session = await manager.handle_event(_perm_event())
        request_id = session.pending_request.request_id

        waiter = asyncio.create_task(manager.await_decision(request_id, timeout=5.0))
        await asyncio.sleep(0)  # let the waiter register

        delivered, reason = await manager.resolve_pending_request(
            "s1", request_id, {"behavior": "allow"}
        )

        assert (delivered, reason) == (True, "delivered")
        assert await waiter == {"behavior": "allow"}

    @pytest.mark.asyncio
    async def test_01_late_answer_is_reported_as_not_delivered(self, manager):
        """No hook is blocked any more — the user must not be told it worked."""
        session = await manager.handle_event(_perm_event())
        request_id = session.pending_request.request_id

        delivered, reason = await manager.resolve_pending_request(
            "s1", request_id, {"behavior": "allow"}
        )

        assert delivered is False
        assert reason == "no hook waiting"

    @pytest.mark.asyncio
    async def test_02_waiting_times_out_with_no_answer(self, manager):
        session = await manager.handle_event(_perm_event())
        request_id = session.pending_request.request_id

        engine = asyncio.get_running_loop()
        started = engine.time()
        decision = await manager.await_decision(request_id, timeout=0.05)

        assert decision is None
        assert engine.time() - started >= 0.05

    @pytest.mark.asyncio
    async def test_03_answering_clears_the_pending_request(self, manager):
        session = await manager.handle_event(_perm_event())
        request_id = session.pending_request.request_id
        waiter = asyncio.create_task(manager.await_decision(request_id, timeout=5.0))
        await asyncio.sleep(0)

        await manager.resolve_pending_request("s1", request_id, {"behavior": "deny"})
        await waiter

        assert manager.get("s1").pending_request is None

    @pytest.mark.asyncio
    async def test_04_unknown_request_id_is_rejected(self, manager):
        await manager.handle_event(_perm_event())
        delivered, reason = await manager.resolve_pending_request(
            "s1", "not-a-real-id", {"behavior": "allow"}
        )
        assert (delivered, reason) == (False, "no such pending request")

    @pytest.mark.asyncio
    async def test_05_unknown_session_is_rejected(self, manager):
        delivered, reason = await manager.resolve_pending_request(
            "ghost", "whatever", {"behavior": "allow"}
        )
        assert (delivered, reason) == (False, "unknown session")

    @pytest.mark.asyncio
    async def test_06_expiry_stops_the_request_being_remotely_answerable(self, manager):
        """Once the hold window closes, the hook is gone and no remote answer
        can reach the agent — so the request must stop presenting itself as
        answerable.

        It is deliberately *kept* rather than deleted: the session state stays
        `pending_approval` until the next event, and a card that says "pending
        approval" with nothing on it explains nothing to the user.
        """
        session = await manager.handle_event(_perm_event())
        session.pending_request.expires_at = 0.0  # already past
        request_id = session.pending_request.request_id

        await manager.expire_pending_requests()

        pending = manager.get("s1").pending_request
        assert pending is not None
        assert pending.request_id == request_id
        assert pending.holding is False
        assert pending.expires_at is None  # not re-evaluated every tick

    @pytest.mark.asyncio
    async def test_06b_answering_an_expired_request_is_reported_as_missed(self, manager):
        session = await manager.handle_event(_perm_event())
        session.pending_request.expires_at = 0.0
        request_id = session.pending_request.request_id
        await manager.expire_pending_requests()

        delivered, reason = await manager.resolve_pending_request(
            "s1", request_id, {"behavior": "allow"}
        )

        assert delivered is False
        assert reason == "no hook waiting"

    @pytest.mark.asyncio
    async def test_07_expiry_spares_a_request_being_held(self, manager):
        session = await manager.handle_event(_perm_event())
        request_id = session.pending_request.request_id
        session.pending_request.expires_at = 0.0
        waiter = asyncio.create_task(manager.await_decision(request_id, timeout=5.0))
        await asyncio.sleep(0)

        await manager.expire_pending_requests()

        assert manager.get("s1").pending_request is not None
        await manager.resolve_pending_request("s1", request_id, {"behavior": "allow"})
        await waiter


class TestRespondRoute:
    @pytest.mark.asyncio
    async def test_00_respond_requires_request_id(self, app):
        async with _client(app) as client:
            resp = await client.post("/api/session/s1/respond", json={"behavior": "allow"})
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_01_respond_rejects_unknown_behavior(self, app):
        async with _client(app) as client:
            resp = await client.post(
                "/api/session/s1/respond",
                json={"request_id": "x", "behavior": "maybe"},
            )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_02_decision_endpoint_returns_null_on_immediate_timeout(self, app):
        """timeout=0 must return at once, not hang — hooks call this on a budget."""
        async with _client(app) as client:
            resp = await client.get("/api/request/nonexistent/decision?timeout=0")

        assert resp.status_code == 200
        assert resp.json()["decision"] is None

    @pytest.mark.asyncio
    async def test_03_allow_without_answers_is_rejected_for_a_question(self, app):
        """Regression guard.

        `allow` alone does not answer an AskUserQuestion: the agent stays
        blocked, but the server has already cleared the request — so the client
        loses the prompt and the session stalls with nothing left to click.
        Observed for real when a client blindly approved every pending request.
        """
        payload = _perm_event(
            tool_name="AskUserQuestion",
            tool_input={"questions": [{"question": "Which?", "options": [{"label": "A"}]}]},
        )
        async with _client(app) as client:
            req = (await client.post("/api/event", json=payload)).json()["pending_request"]
            resp = await client.post(
                f"/api/session/s1/respond",
                json={"request_id": req["request_id"], "behavior": "allow"},
            )
            # The request must survive the rejection, or the prompt is lost.
            still = (await client.get("/api/status/s1")).json()["pending_request"]

        assert resp.status_code == 400
        assert "answers" in resp.json()["detail"]
        assert still is not None and still["request_id"] == req["request_id"]

    @pytest.mark.asyncio
    async def test_04_allow_with_answers_is_accepted_for_a_question(self, app):
        payload = _perm_event(
            tool_name="AskUserQuestion",
            tool_input={"questions": [{"question": "Which?", "options": [{"label": "A"}]}]},
        )
        async with _client(app) as client:
            req = (await client.post("/api/event", json=payload)).json()["pending_request"]
            resp = await client.post(
                "/api/session/s1/respond",
                json={
                    "request_id": req["request_id"],
                    "behavior": "allow",
                    "answers": {"Which?": "A"},
                },
            )

        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_05_deny_needs_no_answers_for_a_question(self, app):
        """Declining a question is a complete answer on its own."""
        payload = _perm_event(
            tool_name="AskUserQuestion",
            tool_input={"questions": [{"question": "Which?", "options": [{"label": "A"}]}]},
        )
        async with _client(app) as client:
            req = (await client.post("/api/event", json=payload)).json()["pending_request"]
            resp = await client.post(
                "/api/session/s1/respond",
                json={"request_id": req["request_id"], "behavior": "deny"},
            )

        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_06_allow_without_answers_is_fine_for_a_permission(self, app):
        """Only questions need answers — a plain permission must not regress."""
        async with _client(app) as client:
            req = (await client.post("/api/event", json=_perm_event())).json()["pending_request"]
            resp = await client.post(
                "/api/session/s1/respond",
                json={"request_id": req["request_id"], "behavior": "allow"},
            )

        assert resp.status_code == 200


class TestDirectives:
    """Contract: a directive is delivered at most once, and says how it went.

    Two transports exist — the session's messaging socket (immediate, reaches
    idle sessions) and the directive queue (drained by the Stop hook). The
    queue is the fallback, and claiming is destructive so a directive can never
    be replayed into the agent twice.
    """

    @pytest.mark.asyncio
    async def test_00_directive_is_queued_when_no_socket_known(self, app):
        async with _client(app) as client:
            await client.post("/api/event", json=_perm_event())
            data = (
                await client.post("/api/session/s1/directive", json={"text": "run the tests"})
            ).json()

        assert data["status"] == "queued"
        assert data["via"] == "hook"

    @pytest.mark.asyncio
    async def test_01_stop_hook_claims_a_queued_directive(self, manager):
        await manager.handle_event(_perm_event())
        await manager.queue_directive("s1", "run the tests")

        directive = manager.claim_directive("s1")

        assert directive is not None
        assert directive.text == "run the tests"
        assert directive.delivered_at is not None
        assert directive.via == "hook"

    @pytest.mark.asyncio
    async def test_02_directive_is_claimed_only_once(self, manager):
        """Double delivery would make the agent repeat work it already did."""
        await manager.handle_event(_perm_event())
        await manager.queue_directive("s1", "run the tests")

        assert manager.claim_directive("s1") is not None
        assert manager.claim_directive("s1") is None

    @pytest.mark.asyncio
    async def test_03_control_block_carries_directive_to_a_stopping_hook(self, app):
        async with _client(app) as client:
            await client.post("/api/event", json=_perm_event())
            await client.post("/api/session/s1/directive", json={"text": "run the tests"})
            data = (
                await client.post(
                    "/api/event",
                    json={
                        "session_id": "s1",
                        "cwd": "/home/user/project",
                        "hook_event_name": "Stop",
                        "last_assistant_message": "done",
                    },
                )
            ).json()

        assert data["control"]["directive"]["text"] == "run the tests"

    @pytest.mark.asyncio
    async def test_04_second_stop_does_not_receive_the_same_directive(self, app):
        async with _client(app) as client:
            await client.post("/api/event", json=_perm_event())
            await client.post("/api/session/s1/directive", json={"text": "run the tests"})
            stop = {
                "session_id": "s1",
                "cwd": "/home/user/project",
                "hook_event_name": "Stop",
                "last_assistant_message": "done",
            }
            await client.post("/api/event", json=stop)
            second = (await client.post("/api/event", json=stop)).json()

        assert "directive" not in second["control"]

    @pytest.mark.asyncio
    async def test_05_directive_requires_text(self, app):
        async with _client(app) as client:
            await client.post("/api/event", json=_perm_event())
            resp = await client.post("/api/session/s1/directive", json={"text": "   "})
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_06_directive_rejects_unknown_session(self, app):
        async with _client(app) as client:
            resp = await client.post("/api/session/ghost/directive", json={"text": "hi"})
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_07_undelivered_directives_survive_a_restart(self, tmp_path):
        """Directives are user input — losing them on restart is unacceptable."""
        first = StateManager(data_dir=tmp_path)
        await first.handle_event(_perm_event())
        await first.queue_directive("s1", "run the tests")

        restored = StateManager(data_dir=tmp_path)
        await restored.restore()

        session = restored.get("s1")
        assert [d.text for d in session.queued_directives] == ["run the tests"]
        assert session.queued_directives[0].delivered_at is None

    @pytest.mark.asyncio
    async def test_08_never_claims_delivery_through_the_messaging_socket(self, app):
        """Regression guard.

        The session messaging socket accepts every write and then discards it,
        so an earlier version reported "delivered via socket" for a directive
        the socket had actually dropped — and marked it delivered, racing the
        Stop hook that did deliver it. A reported socket must not change the
        outcome.
        """
        async with _client(app) as client:
            await client.post(
                "/api/event",
                json=_perm_event(
                    messaging_socket="/tmp/cc-socks/1.sock", messaging_token="tok"
                ),
            )
            data = (
                await client.post("/api/session/s1/directive", json={"text": "go"})
            ).json()

        assert data["status"] == "queued"
        assert data["via"] == "hook"
        assert data["socket_reported"] is True
        # Still claimable by the Stop hook: delivery is the hook's job.
        assert app.state.manager.claim_directive("s1") is not None

    @pytest.mark.asyncio
    async def test_09_pending_requests_do_not_survive_a_restart(self, tmp_path):
        """Whatever hook was blocked on it died with the old process."""
        first = StateManager(data_dir=tmp_path)
        await first.handle_event(_perm_event())

        restored = StateManager(data_dir=tmp_path)
        await restored.restore()

        assert restored.get("s1").pending_request is None


class TestStop:
    """Contract: stop is cooperative and reversible.

    Claude Code exposes no external interrupt, so stop is enforced by the
    PreToolUse hook denying tool calls. A subsequent user prompt always wins —
    a stop that could not be undone would strand the session.
    """

    @pytest.mark.asyncio
    async def test_00_stop_sets_flag_and_reaches_pre_tool_use(self, app):
        async with _client(app) as client:
            await client.post("/api/event", json=_perm_event())
            resp = await client.post("/api/session/s1/stop", json={})
            assert resp.status_code == 200
            data = (
                await client.post(
                    "/api/event",
                    json={
                        "session_id": "s1",
                        "cwd": "/home/user/project",
                        "hook_event_name": "PreToolUse",
                        "tool_name": "Bash",
                    },
                )
            ).json()

        assert data["control"]["stop"] is True
        assert data["control"]["stop_reason"]

    @pytest.mark.asyncio
    async def test_01_no_stop_instruction_when_not_requested(self, app):
        async with _client(app) as client:
            data = (
                await client.post(
                    "/api/event",
                    json={
                        "session_id": "s1",
                        "cwd": "/home/user/project",
                        "hook_event_name": "PreToolUse",
                        "tool_name": "Bash",
                    },
                )
            ).json()

        assert "stop" not in data["control"]

    @pytest.mark.asyncio
    async def test_02_stop_rejects_unknown_session(self, app):
        async with _client(app) as client:
            resp = await client.post("/api/session/ghost/stop", json={})
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_03_user_prompt_clears_stop(self, manager):
        await manager.handle_event(_perm_event())
        await manager.request_stop("s1", "user asked")
        assert manager.is_stop_requested("s1") is True

        await manager.handle_event(
            {
                "session_id": "s1",
                "cwd": "/home/user/project",
                "hook_event_name": "UserPromptSubmit",
                "prompt": "carry on",
            }
        )

        assert manager.is_stop_requested("s1") is False

    @pytest.mark.asyncio
    async def test_04_resume_route_clears_stop(self, app):
        async with _client(app) as client:
            await client.post("/api/event", json=_perm_event())
            await client.post("/api/session/s1/stop", json={})
            resp = await client.post("/api/session/s1/resume")
            assert resp.status_code == 200
            data = (await client.get("/api/status/s1")).json()

        assert data["stop_requested"] is False

    @pytest.mark.asyncio
    async def test_05_sending_a_directive_resumes_a_stopped_session(self, app):
        """Otherwise the directive would be denied by the very stop it should lift."""
        async with _client(app) as client:
            await client.post("/api/event", json=_perm_event())
            await client.post("/api/session/s1/stop", json={})
            await client.post("/api/session/s1/directive", json={"text": "keep going"})
            data = (await client.get("/api/status/s1")).json()

        assert data["stop_requested"] is False


class TestMessagingSocketReporting:
    """Contract: hooks report the session's inbox socket so the server can push
    into an idle session. Without it a directive can only ever be delivered
    when the agent happens to stop on its own."""

    @pytest.mark.asyncio
    async def test_00_socket_coordinates_are_remembered(self, manager):
        await manager.handle_event(
            _perm_event(messaging_socket="/run/user/1000/cc-socks/42.sock", messaging_token="tok")
        )

        sock = manager.get_session_socket("s1")
        assert sock["path"] == "/run/user/1000/cc-socks/42.sock"
        assert sock["token"] == "tok"

    @pytest.mark.asyncio
    async def test_01_no_socket_reported_is_not_an_error(self, manager):
        await manager.handle_event(_perm_event())
        assert manager.get_session_socket("s1") is None


class TestDirectiveHold:
    """Contract: at a turn boundary a connected UI gets a short window to send
    a follow-up, and that window costs nothing when nobody is watching.

    This is the *only* working delivery path for a directive. The session's
    messaging socket is documented but discards every message in practice
    (verified against a real interactive session, including messages sent by a
    genuine child hook), so the design cannot lean on it.

    Derivation: the hold is zero exactly when there are no subscribers, and the
    parked hook receives a directive exactly once.
    """

    @pytest.mark.asyncio
    async def test_00_hold_is_zero_without_subscribers(self, manager):
        await manager.handle_event(_perm_event())
        assert manager.hold_for_directive("s1") == 0.0

    @pytest.mark.asyncio
    async def test_01_hold_is_positive_with_a_subscriber(self, manager):
        queue = manager.subscribe()
        try:
            await manager.handle_event(_perm_event())
            assert manager.hold_for_directive("s1") > 0
        finally:
            manager.unsubscribe(queue)

    @pytest.mark.asyncio
    async def test_02_stop_control_offers_a_hold_only_when_ui_connected(self, app):
        stop = {
            "session_id": "s1",
            "cwd": "/home/user/project",
            "hook_event_name": "Stop",
            "last_assistant_message": "done",
        }
        async with _client(app) as client:
            without_ui = (await client.post("/api/event", json=stop)).json()

            app.state.manager.subscribe()
            with_ui = (await client.post("/api/event", json=stop)).json()

        assert "directive_hold_seconds" not in without_ui["control"]
        assert with_ui["control"]["directive_hold_seconds"] > 0

    @pytest.mark.asyncio
    async def test_03_already_queued_directive_is_returned_without_waiting(self, manager):
        await manager.handle_event(_perm_event())
        await manager.queue_directive("s1", "go left")

        engine = asyncio.get_running_loop()
        started = engine.time()
        directive = await manager.await_directive("s1", timeout=30.0)

        assert directive.text == "go left"
        assert engine.time() - started < 1.0

    @pytest.mark.asyncio
    async def test_04_parked_hook_is_woken_by_a_new_directive(self, manager):
        await manager.handle_event(_perm_event())
        waiter = asyncio.create_task(manager.await_directive("s1", timeout=5.0))
        await asyncio.sleep(0)

        await manager.queue_directive("s1", "go right")

        directive = await waiter
        assert directive.text == "go right"

    @pytest.mark.asyncio
    async def test_05_parked_hook_times_out_with_nothing_typed(self, manager):
        await manager.handle_event(_perm_event())
        assert await manager.await_directive("s1", timeout=0.05) is None

    @pytest.mark.asyncio
    async def test_06_woken_directive_is_marked_delivered(self, manager):
        """Otherwise the next turn boundary would replay it."""
        await manager.handle_event(_perm_event())
        waiter = asyncio.create_task(manager.await_directive("s1", timeout=5.0))
        await asyncio.sleep(0)
        await manager.queue_directive("s1", "go right")
        await waiter

        assert manager.claim_directive("s1") is None
        assert manager.get("s1").queued_directives[0].via == "hook"

    @pytest.mark.asyncio
    async def test_07_directive_next_route_returns_null_on_timeout(self, app):
        async with _client(app) as client:
            await client.post("/api/event", json=_perm_event())
            resp = await client.get("/api/session/s1/directive/next?timeout=0")

        assert resp.status_code == 200
        assert resp.json()["directive"] is None


class TestHookDecisionTranslation:
    """Contract: the server sends an agent-neutral decision; the hook turns it
    into Claude Code's PermissionRequest schema.

    Derivation: the shapes below are Claude Code's documented hook output, not
    this project's invention — `allow` alone is explicitly insufficient for
    AskUserQuestion, which needs its input echoed back with `answers` added.
    """

    def test_00_allow_produces_allow_decision(self):
        payload = _common.permission_decision_payload(
            {"tool_name": "Bash", "tool_input": {"command": "ls"}},
            {"behavior": "allow"},
        )
        assert payload == {
            "hookSpecificOutput": {
                "hookEventName": "PermissionRequest",
                "decision": {"behavior": "allow"},
            }
        }

    def test_01_deny_carries_a_message_for_the_model(self):
        payload = _common.permission_decision_payload(
            {"tool_name": "Bash", "tool_input": {"command": "rm -rf /"}},
            {"behavior": "deny", "message": "not that one"},
        )
        decision = payload["hookSpecificOutput"]["decision"]
        assert decision["behavior"] == "deny"
        assert decision["message"] == "not that one"

    def test_02_deny_defaults_a_message_when_none_supplied(self):
        payload = _common.permission_decision_payload(
            {"tool_name": "Bash", "tool_input": {}}, {"behavior": "deny"}
        )
        assert payload["hookSpecificOutput"]["decision"]["message"]

    def test_03_question_answer_echoes_input_and_adds_answers(self):
        tool_input = {
            "questions": [
                {
                    "question": "Which database?",
                    "options": [{"label": "Postgres"}, {"label": "SQLite"}],
                }
            ]
        }
        payload = _common.permission_decision_payload(
            {"tool_name": "AskUserQuestion", "tool_input": tool_input},
            {"behavior": "allow", "answers": {"Which database?": "Postgres"}},
        )

        decision = payload["hookSpecificOutput"]["decision"]
        assert decision["behavior"] == "allow"
        assert decision["updatedInput"]["answers"] == {"Which database?": "Postgres"}
        # The original questions must survive, or Claude Code cannot match the answer.
        assert decision["updatedInput"]["questions"] == tool_input["questions"]

    def test_04_plain_allow_does_not_invent_updated_input(self):
        payload = _common.permission_decision_payload(
            {"tool_name": "Bash", "tool_input": {"command": "ls"}}, {"behavior": "allow"}
        )
        assert "updatedInput" not in payload["hookSpecificOutput"]["decision"]

    def test_05_answer_for_a_non_dict_input_still_allows(self):
        """Degraded path: a malformed tool_input must not break the approval."""
        payload = _common.permission_decision_payload(
            {"tool_name": "AskUserQuestion", "tool_input": None},
            {"behavior": "allow", "answers": {"q": "a"}},
        )
        assert payload["hookSpecificOutput"]["decision"]["behavior"] == "allow"

    def test_06_url_candidates_falls_back_to_plain_http(self):
        assert _common._url_candidates("https://localhost:9877/api/event") == [
            "https://localhost:9877/api/event",
            "http://localhost:9877/api/event",
        ]

    def test_07_url_candidates_leaves_http_alone(self):
        assert _common._url_candidates("http://localhost:9877/api/event") == [
            "http://localhost:9877/api/event"
        ]
