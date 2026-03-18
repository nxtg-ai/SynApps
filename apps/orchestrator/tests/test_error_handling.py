"""Tests for D-77 Error Handling + DLQ.

Covers:
  - ErrorHandlerNodeApplet registration and capabilities
  - ErrorHandlerNodeApplet.on_message behaviour (suppress vs forward)
  - DeadLetterQueue unit: push, get, list, delete, increment_replay, size
  - DLQ REST endpoints: list, get, delete, replay
  - retry_on conditions: timeout-only, error-only, all, max_retries respected
"""

import asyncio
import copy
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

from apps.orchestrator.db import close_db_connections, init_db
from apps.orchestrator.main import (
    ERROR_HANDLER_NODE_TYPE,
    KNOWN_NODE_TYPES,
    AppletMessage,
    DeadLetterQueue,
    ErrorHandlerNodeApplet,
    Orchestrator,
    app,
    applet_registry,
    dead_letter_queue,
)
from apps.orchestrator.repositories import WorkflowRunRepository


# ---------------------------------------------------------------------------
# Autouse fixture: clear DLQ between tests
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_dlq():
    """Clear the shared dead_letter_queue before and after each test."""
    with dead_letter_queue._lock:
        dead_letter_queue._entries.clear()
    yield
    with dead_letter_queue._lock:
        dead_letter_queue._entries.clear()


# ---------------------------------------------------------------------------
# TestClient + auth helper
# ---------------------------------------------------------------------------


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def _register_and_login(client):
    import uuid
    email = f"dlquser-{uuid.uuid4().hex[:8]}@test.com"
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "DlqPass123!"},
    )
    return resp.json()["access_token"]


# ---------------------------------------------------------------------------
# DB fixture for async tests
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="function")
async def db():
    await init_db()
    yield
    pending = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    if pending:
        _, still_running = await asyncio.wait(pending, timeout=2.0)
        for t in still_running:
            t.cancel()
        if still_running:
            await asyncio.gather(*still_running, return_exceptions=True)
    await close_db_connections()


async def _poll_until_terminal(run_id: str, *, max_attempts: int = 80):
    """Poll until run reaches success/error status."""
    for _ in range(max_attempts):
        await asyncio.sleep(0.15)
        run = await WorkflowRunRepository.get_by_run_id(run_id)
        if run and run.get("status") in ("success", "error"):
            return run
    return await WorkflowRunRepository.get_by_run_id(run_id)


# ===========================================================================
# TestErrorHandlerNodeRegistration
# ===========================================================================


class TestErrorHandlerNodeRegistration:
    def test_error_handler_in_applet_registry(self):
        assert ERROR_HANDLER_NODE_TYPE in applet_registry

    def test_error_handler_in_known_node_types(self):
        assert ERROR_HANDLER_NODE_TYPE in KNOWN_NODE_TYPES

    @pytest.mark.asyncio
    async def test_load_applet_error_handler_canonical(self):
        applet = await Orchestrator.load_applet(ERROR_HANDLER_NODE_TYPE)
        assert isinstance(applet, ErrorHandlerNodeApplet)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("alias", ["catch", "error-handler"])
    async def test_load_applet_error_handler_alias(self, alias):
        applet = await Orchestrator.load_applet(alias)
        assert isinstance(applet, ErrorHandlerNodeApplet)

    def test_error_handler_applet_capabilities(self):
        applet = ErrorHandlerNodeApplet()
        caps = applet.CAPABILITIES
        assert isinstance(caps, list)
        assert len(caps) >= 1  # Gate 2: at least one capability declared
        assert "error-handling" in caps


# ===========================================================================
# TestErrorHandlerNodeAppletBehaviour
# ===========================================================================


class TestErrorHandlerNodeAppletBehaviour:
    @pytest.mark.asyncio
    async def test_on_message_passthrough_content(self):
        """With suppress_error=False the original content is forwarded."""
        applet = ErrorHandlerNodeApplet()
        msg = AppletMessage(
            content="upstream output",
            metadata={"node_data": {"suppress_error": False}},
        )
        result = await applet.on_message(msg)
        assert result.content == "upstream output"

    @pytest.mark.asyncio
    async def test_on_message_fallback_content_when_suppressed(self):
        """With suppress_error=True the fallback_content is emitted."""
        applet = ErrorHandlerNodeApplet()
        msg = AppletMessage(
            content="broken",
            metadata={"node_data": {"suppress_error": True, "fallback_content": "safe fallback"}},
        )
        result = await applet.on_message(msg)
        assert result.content == "safe fallback"

    @pytest.mark.asyncio
    async def test_on_message_metadata_applet_field(self):
        """Response metadata must carry applet='error_handler'."""
        applet = ErrorHandlerNodeApplet()
        msg = AppletMessage(content="x", metadata={"node_data": {}})
        result = await applet.on_message(msg)
        assert result.metadata.get("applet") == ERROR_HANDLER_NODE_TYPE

    @pytest.mark.asyncio
    async def test_on_message_metadata_status_handled(self):
        """suppress_error=True -> status='handled'."""
        applet = ErrorHandlerNodeApplet()
        msg = AppletMessage(
            content="err",
            metadata={"node_data": {"suppress_error": True, "fallback_content": "ok"}},
        )
        result = await applet.on_message(msg)
        assert result.metadata.get("status") == "handled"

    @pytest.mark.asyncio
    async def test_on_message_metadata_status_error_forwarded(self):
        """suppress_error=False -> status='error_forwarded'."""
        applet = ErrorHandlerNodeApplet()
        msg = AppletMessage(content="err", metadata={"node_data": {"suppress_error": False}})
        result = await applet.on_message(msg)
        assert result.metadata.get("status") == "error_forwarded"


# ===========================================================================
# TestDeadLetterQueueUnit
# ===========================================================================


class TestDeadLetterQueueUnit:
    def _make_dlq(self):
        return DeadLetterQueue()

    def test_push_returns_entry_with_id(self):
        dlq = self._make_dlq()
        entry = dlq.push("run-1", "flow-1", None, {}, "some error")
        assert "id" in entry
        assert isinstance(entry["id"], str)
        assert len(entry["id"]) > 0

    def test_push_stores_run_id(self):
        dlq = self._make_dlq()
        entry = dlq.push("run-abc", "flow-1", None, {}, "err")
        assert entry["run_id"] == "run-abc"

    def test_push_stores_error(self):
        dlq = self._make_dlq()
        entry = dlq.push("run-1", "flow-1", None, {}, "connection refused")
        assert entry["error"] == "connection refused"

    def test_push_replay_count_starts_at_zero(self):
        dlq = self._make_dlq()
        entry = dlq.push("run-1", "flow-1", None, {}, "err")
        assert entry["replay_count"] == 0

    def test_get_returns_entry(self):
        dlq = self._make_dlq()
        entry = dlq.push("run-1", "flow-1", None, {}, "err")
        fetched = dlq.get(entry["id"])
        assert fetched is not None
        assert fetched["id"] == entry["id"]

    def test_get_missing_returns_none(self):
        dlq = self._make_dlq()
        assert dlq.get("does-not-exist") is None

    def test_list_all(self):
        dlq = self._make_dlq()
        dlq.push("run-1", "flow-A", None, {}, "err1")
        dlq.push("run-2", "flow-B", None, {}, "err2")
        items = dlq.list()
        assert isinstance(items, list)
        assert len(items) >= 2  # Gate 2: both entries present

    def test_list_filter_by_flow_id(self):
        dlq = self._make_dlq()
        dlq.push("run-1", "flow-X", None, {}, "err1")
        dlq.push("run-2", "flow-X", None, {}, "err2")
        dlq.push("run-3", "flow-Y", None, {}, "err3")
        items = dlq.list(flow_id="flow-X")
        assert len(items) == 2  # Gate 2: filter returns exactly matching entries
        for item in items:
            assert item["flow_id"] == "flow-X"

    def test_list_flow_id_filter_no_match(self):
        dlq = self._make_dlq()
        dlq.push("run-1", "flow-A", None, {}, "err")
        items = dlq.list(flow_id="flow-Z")
        assert items == []

    def test_delete_removes_entry(self):
        dlq = self._make_dlq()
        entry = dlq.push("run-1", "flow-1", None, {}, "err")
        assert dlq.delete(entry["id"]) is True
        assert dlq.get(entry["id"]) is None

    def test_delete_missing_returns_false(self):
        dlq = self._make_dlq()
        assert dlq.delete("ghost-id") is False

    def test_increment_replay_increments_count(self):
        dlq = self._make_dlq()
        entry = dlq.push("run-1", "flow-1", None, {}, "err")
        dlq.increment_replay(entry["id"])
        dlq.increment_replay(entry["id"])
        updated = dlq.get(entry["id"])
        assert updated is not None
        assert updated["replay_count"] == 2


# ===========================================================================
# TestDLQEndpoints
# ===========================================================================


class TestDLQEndpoints:
    def test_list_dlq_empty_initially(self, client):
        token = _register_and_login(client)
        resp = client.get("/api/v1/dlq", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0

    def test_list_dlq_after_push(self, client):
        token = _register_and_login(client)
        dead_letter_queue.push("run-1", "flow-A", None, {}, "err")
        resp = client.get("/api/v1/dlq", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data["items"], list)
        assert len(data["items"]) >= 1  # Gate 2: pushed entry is present

    def test_list_dlq_filter_by_flow_id(self, client):
        token = _register_and_login(client)
        dead_letter_queue.push("run-1", "flow-F1", None, {}, "err")
        dead_letter_queue.push("run-2", "flow-F2", None, {}, "err")
        resp = client.get("/api/v1/dlq?flow_id=flow-F1", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert all(item["flow_id"] == "flow-F1" for item in data["items"])

    def test_get_dlq_entry_success(self, client):
        token = _register_and_login(client)
        entry = dead_letter_queue.push("run-1", "flow-1", None, {}, "err")
        resp = client.get(
            f"/api/v1/dlq/{entry['id']}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["id"] == entry["id"]

    def test_get_dlq_entry_not_found(self, client):
        token = _register_and_login(client)
        resp = client.get("/api/v1/dlq/does-not-exist", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 404

    def test_delete_dlq_entry_success(self, client):
        token = _register_and_login(client)
        entry = dead_letter_queue.push("run-1", "flow-1", None, {}, "err")
        resp = client.delete(
            f"/api/v1/dlq/{entry['id']}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 204
        assert dead_letter_queue.get(entry["id"]) is None

    def test_delete_dlq_entry_not_found(self, client):
        token = _register_and_login(client)
        resp = client.delete("/api/v1/dlq/ghost-id", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 404

    def test_replay_dlq_entry_not_found(self, client):
        token = _register_and_login(client)
        resp = client.post(
            "/api/v1/dlq/ghost-id/replay",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 404

    def test_replay_dlq_entry_no_flow_id_returns_422(self, client):
        token = _register_and_login(client)
        entry = dead_letter_queue.push("run-1", None, None, {}, "err")
        resp = client.post(
            f"/api/v1/dlq/{entry['id']}/replay",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 422

    def test_replay_dlq_entry_flow_not_found(self, client):
        token = _register_and_login(client)
        entry = dead_letter_queue.push("run-1", "nonexistent-flow-xyz", None, {}, "err")
        resp = client.post(
            f"/api/v1/dlq/{entry['id']}/replay",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 404

    def test_list_dlq_returns_items_and_total_keys(self, client):
        token = _register_and_login(client)
        resp = client.get("/api/v1/dlq", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data

    def test_dlq_size_reflects_entries(self, client):
        token = _register_and_login(client)
        dead_letter_queue.push("run-1", "flow-1", None, {}, "err1")
        dead_letter_queue.push("run-2", "flow-2", None, {}, "err2")
        resp = client.get("/api/v1/dlq", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 2  # Gate 2: total reflects pushed entries


# ===========================================================================
# TestRetryConditions
# ===========================================================================

_RETRY_FLOW_BASE = {
    "name": "Retry Test Flow",
    "nodes": [
        {"id": "start", "type": "start", "position": {"x": 0, "y": 0}, "data": {"label": "Start"}},
        {
            "id": "llm",
            "type": "llm",
            "position": {"x": 0, "y": 100},
            "data": {
                "label": "LLM",
                "retry_config": {
                    "max_retries": 2,
                    "delay": 0.0,
                    "backoff": 1.0,
                    "retry_on": "all",
                },
            },
        },
        {"id": "end", "type": "end", "position": {"x": 0, "y": 200}, "data": {"label": "End"}},
    ],
    "edges": [
        {"id": "e1", "source": "start", "target": "llm"},
        {"id": "e2", "source": "llm", "target": "end"},
    ],
}


def _flow_with_retry_on(retry_on, max_retries=2, flow_suffix=""):
    flow = copy.deepcopy(_RETRY_FLOW_BASE)
    flow["id"] = f"retry-test-{max_retries}{flow_suffix}"
    flow["nodes"][1]["data"]["retry_config"]["retry_on"] = retry_on
    flow["nodes"][1]["data"]["retry_config"]["max_retries"] = max_retries
    return flow


class TestRetryConditions:
    """Test retry_on behaviour by executing flows and polling for completion.

    execute_flow() launches a background task; we use _poll_until_terminal to
    wait for it and then inspect a shared call_counter.
    """

    @pytest.mark.asyncio
    async def test_retry_on_all_retries_on_error(self, db):
        """retry_on='all' - error causes retries up to max_retries."""
        call_counts = {"n": 0}

        async def failing(self_applet, message):
            call_counts["n"] += 1
            raise ValueError("simulated error")

        flow = _flow_with_retry_on("all", max_retries=2, flow_suffix="-a")
        with patch("apps.orchestrator.main.LLMNodeApplet.on_message", new=failing):
            with patch("apps.orchestrator.main.broadcast_status", new_callable=AsyncMock):
                run_id = await Orchestrator.execute_flow(flow, {"input": "test"})
                await _poll_until_terminal(run_id)

        # 3 calls = 1 initial + 2 retries
        assert call_counts["n"] == 3

    @pytest.mark.asyncio
    async def test_retry_on_timeout_only_does_not_retry_error(self, db):
        """retry_on=['timeout'] - ValueError should NOT be retried."""
        call_counts = {"n": 0}

        async def failing(self_applet, message):
            call_counts["n"] += 1
            raise ValueError("not a timeout")

        flow = _flow_with_retry_on(["timeout"], max_retries=2, flow_suffix="-b")
        with patch("apps.orchestrator.main.LLMNodeApplet.on_message", new=failing):
            with patch("apps.orchestrator.main.broadcast_status", new_callable=AsyncMock):
                run_id = await Orchestrator.execute_flow(flow, {"input": "test"})
                await _poll_until_terminal(run_id)

        # Only 1 attempt - error does not trigger retry when retry_on=['timeout']
        assert call_counts["n"] == 1

    @pytest.mark.asyncio
    async def test_retry_on_error_only_does_not_retry_timeout(self, db):
        """retry_on=['error'] - TimeoutError should NOT be retried."""
        call_counts = {"n": 0}

        async def timing_out(self_applet, message):
            call_counts["n"] += 1
            raise TimeoutError("simulated timeout")

        flow = _flow_with_retry_on(["error"], max_retries=2, flow_suffix="-c")
        with patch("apps.orchestrator.main.LLMNodeApplet.on_message", new=timing_out):
            with patch("apps.orchestrator.main.broadcast_status", new_callable=AsyncMock):
                run_id = await Orchestrator.execute_flow(flow, {"input": "test"})
                await _poll_until_terminal(run_id)

        # Only 1 attempt - timeout does not trigger retry when retry_on=['error']
        assert call_counts["n"] == 1

    @pytest.mark.asyncio
    async def test_retry_on_all_retries_timeout(self, db):
        """retry_on='all' - TimeoutError causes retries."""
        call_counts = {"n": 0}

        async def timing_out(self_applet, message):
            call_counts["n"] += 1
            raise TimeoutError("simulated timeout")

        flow = _flow_with_retry_on("all", max_retries=2, flow_suffix="-d")
        with patch("apps.orchestrator.main.LLMNodeApplet.on_message", new=timing_out):
            with patch("apps.orchestrator.main.broadcast_status", new_callable=AsyncMock):
                run_id = await Orchestrator.execute_flow(flow, {"input": "test"})
                await _poll_until_terminal(run_id)

        # 3 calls = 1 initial + 2 retries
        assert call_counts["n"] == 3

    @pytest.mark.asyncio
    async def test_retry_on_error_retries_on_exception(self, db):
        """retry_on=['error'] - generic exception IS retried."""
        call_counts = {"n": 0}

        async def failing(self_applet, message):
            call_counts["n"] += 1
            raise RuntimeError("runtime failure")

        flow = _flow_with_retry_on(["error"], max_retries=2, flow_suffix="-e")
        with patch("apps.orchestrator.main.LLMNodeApplet.on_message", new=failing):
            with patch("apps.orchestrator.main.broadcast_status", new_callable=AsyncMock):
                run_id = await Orchestrator.execute_flow(flow, {"input": "test"})
                await _poll_until_terminal(run_id)

        assert call_counts["n"] == 3

    @pytest.mark.asyncio
    async def test_retry_config_max_retries_respected(self, db):
        """max_retries=1 -> total 2 attempts only."""
        call_counts = {"n": 0}

        async def failing(self_applet, message):
            call_counts["n"] += 1
            raise ValueError("err")

        flow = _flow_with_retry_on("all", max_retries=1, flow_suffix="-f")
        with patch("apps.orchestrator.main.LLMNodeApplet.on_message", new=failing):
            with patch("apps.orchestrator.main.broadcast_status", new_callable=AsyncMock):
                run_id = await Orchestrator.execute_flow(flow, {"input": "test"})
                await _poll_until_terminal(run_id)

        # 2 calls = 1 initial + 1 retry
        assert call_counts["n"] == 2
