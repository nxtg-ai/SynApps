"""
N-40: Workflow Debugging — Step-Through Execution

Tests for DebugSession dataclass, DebugSessionStore, _run_flow_debug background
function, and the six debug REST endpoints.

Test classes
------------
* TestDebugSessionStore      — 6 tests covering CRUD + reset
* TestDebugSessionLogic      — 8 tests covering DebugSession invariants
* TestDebugEndpoints         — 12+ tests covering all REST endpoints
"""

import asyncio
import time
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from apps.orchestrator.main import (
    AppletMessage,
    DebugSession,
    DebugSessionStore,
    app,
    audit_log_store,
    debug_session_store,
    workflow_permission_store,
)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_MINIMAL_FLOW_ID = "flow-debug-test"


def _make_flow(flow_id: str = _MINIMAL_FLOW_ID) -> dict:
    """Return a minimal flow dict: start → code → end."""
    return {
        "id": flow_id,
        "name": "Debug Test Flow",
        "nodes": [
            {"id": "start-1", "type": "start", "data": {}},
            {"id": "code-1", "type": "code", "data": {"code": "output = input"}},
            {"id": "end-1", "type": "end", "data": {}},
        ],
        "edges": [
            {"id": "e1", "source": "start-1", "target": "code-1"},
            {"id": "e2", "source": "code-1", "target": "end-1"},
        ],
    }


@pytest.fixture(autouse=True)
def _clean():
    """Reset all mutable singletons before and after each test."""
    debug_session_store.reset()
    audit_log_store.reset()
    workflow_permission_store.reset()
    yield
    debug_session_store.reset()
    audit_log_store.reset()
    workflow_permission_store.reset()


def _register(client: TestClient, email: str | None = None) -> tuple[str, str]:
    """Register a user and return (access_token, email)."""
    email = email or f"dbg-{uuid.uuid4().hex[:8]}@test.com"
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "DebugPass1!"},
    )
    # Register returns 200 or 201 depending on server version
    assert resp.status_code in (200, 201), resp.text
    return resp.json()["access_token"], email


# ===========================================================================
# TestDebugSessionStore
# ===========================================================================


class TestDebugSessionStore:
    """Unit tests for DebugSessionStore CRUD operations."""

    def test_create_returns_session(self):
        """create() should return a DebugSession with correct fields."""
        store = DebugSessionStore()
        run_id = str(uuid.uuid4())
        session = store.create(run_id=run_id, flow_id="f1", breakpoints=["n1", "n2"])
        assert isinstance(session, DebugSession)
        assert session.run_id == run_id
        assert session.flow_id == "f1"
        assert session.breakpoints == {"n1", "n2"}
        assert session.status == "running"

    def test_get_returns_session_by_id(self):
        """get() should return the session created under the same session_id."""
        store = DebugSessionStore()
        run_id = str(uuid.uuid4())
        session = store.create(run_id=run_id, flow_id="f1", breakpoints=[])
        fetched = store.get(session.session_id)
        assert fetched is session  # same object

    def test_get_missing_returns_none(self):
        """get() with an unknown session_id should return None."""
        store = DebugSessionStore()
        assert store.get("does-not-exist") is None

    def test_get_by_run_id(self):
        """get_by_run_id() should locate the session via run_id."""
        store = DebugSessionStore()
        run_id = str(uuid.uuid4())
        session = store.create(run_id=run_id, flow_id="f1", breakpoints=[])
        result = store.get_by_run_id(run_id)
        assert result is session

    def test_list_active_returns_only_active(self):
        """list_active() excludes completed and aborted sessions."""
        store = DebugSessionStore()

        run_a = str(uuid.uuid4())
        run_b = str(uuid.uuid4())
        run_c = str(uuid.uuid4())

        s_running = store.create(run_id=run_a, flow_id="f", breakpoints=[])
        s_completed = store.create(run_id=run_b, flow_id="f", breakpoints=[])
        s_aborted = store.create(run_id=run_c, flow_id="f", breakpoints=[])

        s_completed.status = "completed"
        s_aborted.status = "aborted"

        active = store.list_active()
        # Gate 2: confirm at least one active session is returned
        assert isinstance(active, list)
        assert len(active) >= 1
        assert s_running in active
        assert s_completed not in active
        assert s_aborted not in active

    def test_reset_clears_all_sessions(self):
        """reset() should empty all stored sessions."""
        store = DebugSessionStore()
        for _ in range(3):
            store.create(run_id=str(uuid.uuid4()), flow_id="f", breakpoints=[])

        store.reset()
        assert store.list_active() == []


# ===========================================================================
# TestDebugSessionLogic
# ===========================================================================


class TestDebugSessionLogic:
    """Unit tests for DebugSession dataclass invariants."""

    def _make_session(self, **overrides) -> DebugSession:
        defaults = dict(
            session_id=str(uuid.uuid4()),
            run_id=str(uuid.uuid4()),
            flow_id="f1",
            status="running",
            breakpoints=set(),
            current_node_id=None,
            current_node_input={},
            current_node_output={},
            execution_history=[],
            created_at=time.time(),
            paused_at=None,
            _resume_event=asyncio.Event(),
            _skip_flag=False,
        )
        defaults.update(overrides)
        return DebugSession(**defaults)

    def test_initial_state_defaults(self):
        """Freshly created DebugSession should have correct default values."""
        s = self._make_session()
        assert s.status == "running"
        assert s.current_node_id is None
        assert s.current_node_input == {}
        assert s.current_node_output == {}
        assert s.execution_history == []
        assert s.paused_at is None
        assert s._skip_flag is False

    def test_breakpoints_stored_as_set(self):
        """breakpoints field should be a Python set (not list)."""
        s = self._make_session(breakpoints={"a", "b", "c"})
        assert isinstance(s.breakpoints, set)
        assert "a" in s.breakpoints

    def test_skip_flag_defaults_false(self):
        """_skip_flag should default to False."""
        s = self._make_session()
        assert s._skip_flag is False

    def test_resume_event_is_asyncio_event(self):
        """_resume_event should be an asyncio.Event instance."""
        s = self._make_session()
        assert isinstance(s._resume_event, asyncio.Event)

    def test_paused_at_set_when_status_paused(self):
        """Setting status to paused and recording paused_at should work."""
        s = self._make_session()
        s.status = "paused"
        s.paused_at = time.time()
        assert s.status == "paused"
        assert s.paused_at is not None

    def test_execution_history_appends_correctly(self):
        """execution_history should grow with each appended entry."""
        s = self._make_session()
        entry = {
            "node_id": "n1",
            "input": {"x": 1},
            "output": {"y": 2},
            "skipped": False,
            "timestamp": time.time(),
        }
        s.execution_history.append(entry)
        # Gate 2: confirm history is non-empty
        assert isinstance(s.execution_history, list)
        assert len(s.execution_history) >= 1
        assert s.execution_history[0]["node_id"] == "n1"

    def test_session_with_no_breakpoints_runs_straight_through(self):
        """A session with an empty breakpoints set should never pause."""
        s = self._make_session(breakpoints=set())
        # Simulate iterating three nodes — none should trigger a pause
        for nid in ("n1", "n2", "n3"):
            should_pause = nid in s.breakpoints
            assert not should_pause

    def test_to_dict_serializes_session(self):
        """to_dict() should return a plain dict with all expected keys."""
        s = self._make_session(
            breakpoints={"bp1", "bp2"},
            current_node_id="bp1",
            current_node_input={"k": "v"},
            current_node_output={"out": 42},
        )
        d = s.to_dict()
        assert isinstance(d, dict)
        for key in (
            "session_id",
            "run_id",
            "flow_id",
            "status",
            "breakpoints",
            "current_node_id",
            "current_node_input",
            "current_node_output",
            "execution_history",
            "created_at",
            "paused_at",
        ):
            assert key in d, f"Missing key: {key}"
        assert d["current_node_input"] == {"k": "v"}
        assert d["current_node_output"] == {"out": 42}
        assert set(d["breakpoints"]) == {"bp1", "bp2"}


# ===========================================================================
# TestDebugEndpoints
# ===========================================================================


class TestDebugEndpoints:
    """Integration tests for the six debug REST endpoints."""

    # -----------------------------------------------------------------------
    # POST /workflows/{flow_id}/debug
    # -----------------------------------------------------------------------

    def test_start_debug_returns_session_id(self):
        """POST /debug should return session_id, run_id, status, and breakpoints."""
        with TestClient(app) as client:
            token, _ = _register(client)
            with patch(
                "apps.orchestrator.main.FlowRepository.get_by_id",
                new_callable=AsyncMock,
                return_value=_make_flow(),
            ):
                resp = client.post(
                    f"/api/v1/workflows/{_MINIMAL_FLOW_ID}/debug",
                    json={"input_data": {}, "breakpoints": ["code-1"]},
                    headers={"Authorization": f"Bearer {token}"},
                )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert "session_id" in data
        assert "run_id" in data
        assert data["status"] == "running"
        assert "code-1" in data["breakpoints"]

    def test_start_debug_unknown_flow_returns_404(self):
        """POST /debug for a non-existent flow should return 404."""
        with TestClient(app) as client:
            token, _ = _register(client)
            with patch(
                "apps.orchestrator.main.FlowRepository.get_by_id",
                new_callable=AsyncMock,
                return_value=None,
            ):
                resp = client.post(
                    "/api/v1/workflows/no-such-flow/debug",
                    json={"input_data": {}, "breakpoints": []},
                    headers={"Authorization": f"Bearer {token}"},
                )
        assert resp.status_code == 404

    # -----------------------------------------------------------------------
    # GET /debug/{session_id}
    # -----------------------------------------------------------------------

    def test_get_debug_session_returns_state(self):
        """GET /debug/{session_id} should return the full session state."""
        store = debug_session_store
        run_id = str(uuid.uuid4())
        session = store.create(run_id=run_id, flow_id="f1", breakpoints=["n1"])

        with TestClient(app) as client:
            token, _ = _register(client)
            resp = client.get(
                f"/api/v1/debug/{session.session_id}",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"] == session.session_id
        assert data["run_id"] == run_id
        assert "n1" in data["breakpoints"]

    def test_get_debug_session_unknown_returns_404(self):
        """GET /debug/{session_id} for an unknown id should return 404."""
        with TestClient(app) as client:
            token, _ = _register(client)
            resp = client.get(
                "/api/v1/debug/does-not-exist",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 404

    def test_get_debug_session_requires_auth(self):
        """GET /debug/{id} without credentials returns 401 once a user exists in the DB.

        We register a user first so ALLOW_ANONYMOUS_WHEN_NO_USERS is no longer
        satisfied, then make an unauthenticated request which must be rejected.
        """
        store = debug_session_store
        session = store.create(run_id=str(uuid.uuid4()), flow_id="f1", breakpoints=[])
        with TestClient(app) as client:
            # Register a user so the system knows anonymous access is not allowed
            _register(client)
            resp = client.get(f"/api/v1/debug/{session.session_id}")
        assert resp.status_code == 401

    # -----------------------------------------------------------------------
    # POST /debug/{session_id}/continue
    # -----------------------------------------------------------------------

    def test_continue_on_running_session_returns_200(self):
        """POST /continue on a running (non-paused) session should be a no-op with 200."""
        session = debug_session_store.create(
            run_id=str(uuid.uuid4()), flow_id="f1", breakpoints=[]
        )
        session.status = "running"

        with TestClient(app) as client:
            token, _ = _register(client)
            resp = client.post(
                f"/api/v1/debug/{session.session_id}/continue",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "running"

    def test_continue_on_unknown_session_returns_404(self):
        """POST /continue for unknown session_id should return 404."""
        with TestClient(app) as client:
            token, _ = _register(client)
            resp = client.post(
                "/api/v1/debug/no-such-session/continue",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 404

    def test_continue_unpauses_session(self):
        """POST /continue on a paused session should set status to running."""
        session = debug_session_store.create(
            run_id=str(uuid.uuid4()), flow_id="f1", breakpoints=["n1"]
        )
        session.status = "paused"
        session.current_node_id = "n1"
        session._resume_event.clear()

        with TestClient(app) as client:
            token, _ = _register(client)
            resp = client.post(
                f"/api/v1/debug/{session.session_id}/continue",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "running"
        assert session._resume_event.is_set()

    # -----------------------------------------------------------------------
    # POST /debug/{session_id}/skip
    # -----------------------------------------------------------------------

    def test_skip_on_unknown_session_returns_404(self):
        """POST /skip for unknown session_id should return 404."""
        with TestClient(app) as client:
            token, _ = _register(client)
            resp = client.post(
                "/api/v1/debug/no-such-session/skip",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 404

    def test_skip_sets_skip_flag(self):
        """POST /skip on a paused session should set _skip_flag and signal the event."""
        session = debug_session_store.create(
            run_id=str(uuid.uuid4()), flow_id="f1", breakpoints=["n1"]
        )
        session.status = "paused"
        session.current_node_id = "n1"
        session._resume_event.clear()

        with TestClient(app) as client:
            token, _ = _register(client)
            resp = client.post(
                f"/api/v1/debug/{session.session_id}/skip",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 200
        assert session._skip_flag is True
        assert session._resume_event.is_set()

    # -----------------------------------------------------------------------
    # POST /debug/{session_id}/breakpoints
    # -----------------------------------------------------------------------

    def test_update_breakpoints(self):
        """POST /breakpoints should replace the existing breakpoint set."""
        session = debug_session_store.create(
            run_id=str(uuid.uuid4()), flow_id="f1", breakpoints=["old-node"]
        )

        with TestClient(app) as client:
            token, _ = _register(client)
            resp = client.post(
                f"/api/v1/debug/{session.session_id}/breakpoints",
                json={"breakpoints": ["new-node-1", "new-node-2"]},
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "new-node-1" in data["breakpoints"]
        assert "new-node-2" in data["breakpoints"]
        assert "old-node" not in data["breakpoints"]
        assert session.breakpoints == {"new-node-1", "new-node-2"}

    # -----------------------------------------------------------------------
    # DELETE /debug/{session_id}
    # -----------------------------------------------------------------------

    def test_abort_sets_status_aborted(self):
        """DELETE /debug/{id} should mark the session as aborted."""
        session = debug_session_store.create(
            run_id=str(uuid.uuid4()), flow_id="f1", breakpoints=[]
        )

        with TestClient(app) as client:
            token, _ = _register(client)
            resp = client.delete(
                f"/api/v1/debug/{session.session_id}",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 204
        assert session.status == "aborted"
        assert session._resume_event.is_set()

    def test_abort_unknown_session_returns_404(self):
        """DELETE /debug/{id} for an unknown session should return 404."""
        with TestClient(app) as client:
            token, _ = _register(client)
            resp = client.delete(
                "/api/v1/debug/no-such-session",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 404

    # -----------------------------------------------------------------------
    # Full debug flow: start → pause at breakpoint → continue → complete
    # -----------------------------------------------------------------------

    def test_full_debug_flow_pause_and_continue(self):
        """End-to-end: start debug, verify paused at breakpoint, continue, verify completed."""
        flow = _make_flow()

        # Patch the code node applet so it returns immediately without real execution
        fake_response = AppletMessage(
            content={"result": "ok"},
            context={},
            metadata={},
        )

        async def fake_load_applet(applet_type: str):
            from apps.orchestrator.main import BaseApplet

            class _FakeApplet(BaseApplet):
                async def on_message(self, message: AppletMessage) -> AppletMessage:
                    return fake_response

            return _FakeApplet()

        with TestClient(app) as client:
            token, _ = _register(client)

            with (
                patch(
                    "apps.orchestrator.main.FlowRepository.get_by_id",
                    new_callable=AsyncMock,
                    return_value=flow,
                ),
                patch(
                    "apps.orchestrator.main.WorkflowRunRepository.save",
                    new_callable=AsyncMock,
                    return_value=None,
                ),
                patch(
                    "apps.orchestrator.main.Orchestrator.load_applet",
                    side_effect=fake_load_applet,
                ),
            ):
                # Step 1: Start the debug session with a breakpoint on code-1
                start_resp = client.post(
                    f"/api/v1/workflows/{_MINIMAL_FLOW_ID}/debug",
                    json={"input_data": {"x": 1}, "breakpoints": ["code-1"]},
                    headers={"Authorization": f"Bearer {token}"},
                )
                assert start_resp.status_code == 201, start_resp.text
                session_id = start_resp.json()["session_id"]

                # Step 2: Poll until paused (max 2 s)
                deadline = time.time() + 2.0
                state = None
                while time.time() < deadline:
                    state_resp = client.get(
                        f"/api/v1/debug/{session_id}",
                        headers={"Authorization": f"Bearer {token}"},
                    )
                    assert state_resp.status_code == 200
                    state = state_resp.json()
                    if state["status"] == "paused":
                        break
                    import time as _t

                    _t.sleep(0.05)

                assert state is not None
                assert state["status"] == "paused", f"Expected paused, got: {state['status']}"
                assert state["current_node_id"] == "code-1"

                # Step 3: Send continue
                cont_resp = client.post(
                    f"/api/v1/debug/{session_id}/continue",
                    headers={"Authorization": f"Bearer {token}"},
                )
                assert cont_resp.status_code == 200

                # Step 4: Poll until completed (max 2 s)
                deadline = time.time() + 2.0
                final_state = None
                while time.time() < deadline:
                    state_resp = client.get(
                        f"/api/v1/debug/{session_id}",
                        headers={"Authorization": f"Bearer {token}"},
                    )
                    assert state_resp.status_code == 200
                    final_state = state_resp.json()
                    if final_state["status"] == "completed":
                        break
                    import time as _t

                    _t.sleep(0.05)

                assert final_state is not None
                assert final_state["status"] == "completed", (
                    f"Expected completed, got: {final_state['status']}"
                )
                # Gate 2: execution history must contain at least one entry
                assert isinstance(final_state["execution_history"], list)
                assert len(final_state["execution_history"]) >= 1
