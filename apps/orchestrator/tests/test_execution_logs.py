"""
DIRECTIVE-NXTG-20260318-108: Execution Logs + Debug Console — N-25

Tests for:
  1. ExecutionLogStore unit — append / get / delete / has / size / reset
  2. Log events emitted during a real pipeline run (node_start / node_success)
  3. GET /executions/{run_id}/logs — 200 with log list, 404 when none
  4. POST /flows/{id}/runs?debug=true — returns logs inline with terminal status
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from apps.orchestrator.main import (
    AppletMessage,
    ExecutionLogStore,
    app,
    execution_log_store,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SIMPLE_FLOW = {
    "id": "logs-test-flow-001",
    "name": "Logs Test Flow",
    "nodes": [
        {"id": "start", "type": "start", "position": {"x": 0, "y": 0}, "data": {"label": "Start"}},
        {"id": "end", "type": "end", "position": {"x": 0, "y": 100}, "data": {"label": "End"}},
    ],
    "edges": [
        {"id": "s-e", "source": "start", "target": "end"},
    ],
}

_LLM_FLOW = {
    "id": "logs-test-llm-flow-002",
    "name": "Logs LLM Flow",
    "nodes": [
        {"id": "start", "type": "start", "position": {"x": 0, "y": 0}, "data": {"label": "Start"}},
        {
            "id": "llm1",
            "type": "llm",
            "position": {"x": 0, "y": 100},
            "data": {
                "label": "LLM",
                "provider": "openai",
                "model": "gpt-4o-mini",
                "system_prompt": "Be brief.",
            },
        },
        {"id": "end", "type": "end", "position": {"x": 0, "y": 200}, "data": {"label": "End"}},
    ],
    "edges": [
        {"id": "s-l", "source": "start", "target": "llm1"},
        {"id": "l-e", "source": "llm1", "target": "end"},
    ],
}

_MOCK_LLM = AppletMessage(
    content="mocked summary",
    context={},
    metadata={"applet": "llm", "status": "success"},
)


def _poll_run(client: TestClient, run_id: str, *, timeout: float = 5.0):
    import time

    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(0.1)
        resp = client.get(f"/api/v1/runs/{run_id}")
        if resp.status_code == 200:
            run = resp.json()
            if run.get("status") in ("success", "error"):
                return run
    return None


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_log_store():
    execution_log_store.reset()
    yield
    execution_log_store.reset()


# ===========================================================================
# Unit: ExecutionLogStore
# ===========================================================================


class TestExecutionLogStoreUnit:
    """Unit tests for ExecutionLogStore in isolation."""

    def test_append_and_get(self):
        store = ExecutionLogStore()
        store.append("r1", {"event": "node_start"})
        store.append("r1", {"event": "node_success"})
        logs = store.get("r1")
        assert len(logs) >= 2  # Gate 2: non-empty after append
        assert logs[0]["event"] == "node_start"
        assert logs[1]["event"] == "node_success"

    def test_get_unknown_run_returns_empty_list(self):
        store = ExecutionLogStore()
        result = store.get("nonexistent")
        assert result == []

    def test_has_returns_true_after_append(self):
        store = ExecutionLogStore()
        assert store.has("r2") is False
        store.append("r2", {"event": "node_start"})
        assert store.has("r2") is True  # Gate 2: explicit has check

    def test_delete_removes_run(self):
        store = ExecutionLogStore()
        store.append("r3", {"event": "x"})
        deleted = store.delete("r3")
        assert deleted is True
        assert store.has("r3") is False

    def test_delete_nonexistent_returns_false(self):
        store = ExecutionLogStore()
        assert store.delete("ghost") is False

    def test_size_tracks_distinct_runs(self):
        store = ExecutionLogStore()
        store.append("a", {"event": "e"})
        store.append("b", {"event": "e"})
        store.append("a", {"event": "e2"})
        assert store.size() == 2  # Gate 2: two distinct run IDs

    def test_reset_clears_all(self):
        store = ExecutionLogStore()
        store.append("r1", {"event": "e"})
        store.append("r2", {"event": "e"})
        store.reset()
        assert store.size() == 0

    def test_get_returns_copy(self):
        """Modifying the returned list must not affect the store."""
        store = ExecutionLogStore()
        store.append("r1", {"event": "e"})
        logs = store.get("r1")
        logs.append({"event": "injected"})
        assert len(store.get("r1")) == 1  # Gate 2: original unchanged


# ===========================================================================
# Integration: log events emitted during a flow run
# ===========================================================================


class TestLogEventsEmittedDuringRun:
    """Verify that execution log entries are produced during real flow runs."""

    def test_start_and_end_nodes_emit_node_start_and_success(self):
        with TestClient(app) as client:
            flow = {**_SIMPLE_FLOW, "id": f"log-run-{uuid.uuid4().hex[:8]}"}
            resp = client.post("/api/v1/flows", json=flow)
            assert resp.status_code == 201

            with patch(
                "apps.orchestrator.main.broadcast_status",
                new_callable=AsyncMock,
            ):
                resp = client.post(
                    f"/api/v1/flows/{flow['id']}/runs",
                    json={"input": {}},
                )
            assert resp.status_code == 202
            run_id = resp.json()["run_id"]

            run = _poll_run(client, run_id)
            assert run is not None

            logs = execution_log_store.get(run_id)
            assert len(logs) >= 2  # Gate 2: at least start + end node events
            events = [e["event"] for e in logs]
            assert "node_start" in events
            assert "node_success" in events

    def test_llm_node_emits_success_event(self):
        with TestClient(app) as client:
            flow = {**_LLM_FLOW, "id": f"log-llm-{uuid.uuid4().hex[:8]}"}
            resp = client.post("/api/v1/flows", json=flow)
            assert resp.status_code == 201

            with patch(
                "apps.orchestrator.main.LLMNodeApplet.on_message",
                new_callable=AsyncMock,
                return_value=_MOCK_LLM,
            ), patch(
                "apps.orchestrator.main.broadcast_status",
                new_callable=AsyncMock,
            ):
                resp = client.post(
                    f"/api/v1/flows/{flow['id']}/runs",
                    json={"input": {}},
                )
            assert resp.status_code == 202
            run_id = resp.json()["run_id"]

            run = _poll_run(client, run_id)
            assert run is not None

            logs = execution_log_store.get(run_id)
            assert len(logs) >= 3  # Gate 2: start, llm, end nodes
            node_ids_logged = {e["node_id"] for e in logs}
            assert "llm1" in node_ids_logged  # Gate 2: LLM node logged

    def test_log_entry_schema(self):
        """Each log entry must contain required fields."""
        with TestClient(app) as client:
            flow = {**_SIMPLE_FLOW, "id": f"log-schema-{uuid.uuid4().hex[:8]}"}
            client.post("/api/v1/flows", json=flow)

            with patch("apps.orchestrator.main.broadcast_status", new_callable=AsyncMock):
                resp = client.post(
                    f"/api/v1/flows/{flow['id']}/runs",
                    json={"input": {}},
                )
            run_id = resp.json()["run_id"]
            _poll_run(client, run_id)

            logs = execution_log_store.get(run_id)
            assert len(logs) >= 1  # Gate 2: at least one entry
            for entry in logs:
                assert "timestamp" in entry
                assert "run_id" in entry
                assert "node_id" in entry
                assert "node_type" in entry
                assert "event" in entry
                assert "attempt" in entry


# ===========================================================================
# Endpoint: GET /executions/{run_id}/logs
# ===========================================================================


class TestGetExecutionLogsEndpoint:
    """Tests for GET /api/v1/executions/{run_id}/logs."""

    def test_404_when_no_logs_exist(self):
        with TestClient(app) as client:
            resp = client.get("/api/v1/executions/nonexistent-run/logs")
            assert resp.status_code == 404

    def test_200_with_logs_after_run(self):
        with TestClient(app) as client:
            flow = {**_SIMPLE_FLOW, "id": f"log-ep-{uuid.uuid4().hex[:8]}"}
            client.post("/api/v1/flows", json=flow)

            with patch("apps.orchestrator.main.broadcast_status", new_callable=AsyncMock):
                resp = client.post(
                    f"/api/v1/flows/{flow['id']}/runs",
                    json={"input": {}},
                )
            run_id = resp.json()["run_id"]
            _poll_run(client, run_id)

            resp = client.get(f"/api/v1/executions/{run_id}/logs")
            assert resp.status_code == 200
            body = resp.json()
            assert body["run_id"] == run_id
            assert "logs" in body
            assert body["count"] >= 1  # Gate 2: count matches non-empty logs
            assert len(body["logs"]) == body["count"]

    def test_response_has_correct_run_id(self):
        with TestClient(app) as client:
            flow = {**_SIMPLE_FLOW, "id": f"log-ep2-{uuid.uuid4().hex[:8]}"}
            client.post("/api/v1/flows", json=flow)

            with patch("apps.orchestrator.main.broadcast_status", new_callable=AsyncMock):
                resp = client.post(
                    f"/api/v1/flows/{flow['id']}/runs",
                    json={"input": {}},
                )
            run_id = resp.json()["run_id"]
            _poll_run(client, run_id)

            resp = client.get(f"/api/v1/executions/{run_id}/logs")
            assert resp.json()["run_id"] == run_id  # Gate 2: run_id echoed correctly

    def test_logs_ordered_by_timestamp(self):
        """Log entries must be in ascending timestamp order."""
        with TestClient(app) as client:
            flow = {**_LLM_FLOW, "id": f"log-order-{uuid.uuid4().hex[:8]}"}
            client.post("/api/v1/flows", json=flow)

            with patch(
                "apps.orchestrator.main.LLMNodeApplet.on_message",
                new_callable=AsyncMock,
                return_value=_MOCK_LLM,
            ), patch("apps.orchestrator.main.broadcast_status", new_callable=AsyncMock):
                resp = client.post(
                    f"/api/v1/flows/{flow['id']}/runs",
                    json={"input": {}},
                )
            run_id = resp.json()["run_id"]
            _poll_run(client, run_id)

            resp = client.get(f"/api/v1/executions/{run_id}/logs")
            logs = resp.json()["logs"]
            assert len(logs) >= 2  # Gate 2: need at least 2 to check order
            timestamps = [e["timestamp"] for e in logs]
            assert timestamps == sorted(timestamps), "Log entries must be in ascending timestamp order"


# ===========================================================================
# Debug mode: POST /flows/{id}/runs?debug=true
# ===========================================================================


class TestDebugMode:
    """Tests for ?debug=true on POST /flows/{id}/runs."""

    def test_debug_true_returns_logs_inline(self):
        with TestClient(app) as client:
            flow = {**_SIMPLE_FLOW, "id": f"debug-{uuid.uuid4().hex[:8]}"}
            client.post("/api/v1/flows", json=flow)

            with patch("apps.orchestrator.main.broadcast_status", new_callable=AsyncMock):
                resp = client.post(
                    f"/api/v1/flows/{flow['id']}/runs?debug=true",
                    json={"input": {}},
                )
            assert resp.status_code == 202
            body = resp.json()
            assert "run_id" in body  # Gate 2: run_id present
            assert "status" in body
            assert "logs" in body
            assert body["status"] in ("success", "error", "unknown")
            assert isinstance(body["logs"], list)

    def test_debug_true_logs_non_empty(self):
        with TestClient(app) as client:
            flow = {**_SIMPLE_FLOW, "id": f"debug2-{uuid.uuid4().hex[:8]}"}
            client.post("/api/v1/flows", json=flow)

            with patch("apps.orchestrator.main.broadcast_status", new_callable=AsyncMock):
                resp = client.post(
                    f"/api/v1/flows/{flow['id']}/runs?debug=true",
                    json={"input": {}},
                )
            body = resp.json()
            assert len(body["logs"]) >= 1  # Gate 2: at least one log entry inline

    def test_debug_false_returns_only_run_id(self):
        """Without debug, response must only contain run_id."""
        with TestClient(app) as client:
            flow = {**_SIMPLE_FLOW, "id": f"nodebug-{uuid.uuid4().hex[:8]}"}
            client.post("/api/v1/flows", json=flow)

            with patch("apps.orchestrator.main.broadcast_status", new_callable=AsyncMock):
                resp = client.post(
                    f"/api/v1/flows/{flow['id']}/runs?debug=false",
                    json={"input": {}},
                )
            assert resp.status_code == 202
            body = resp.json()
            assert "run_id" in body
            assert "logs" not in body  # debug=false → no inline logs

    def test_debug_omitted_default_no_logs(self):
        """Default (no debug param) must not return logs."""
        with TestClient(app) as client:
            flow = {**_SIMPLE_FLOW, "id": f"nodbg2-{uuid.uuid4().hex[:8]}"}
            client.post("/api/v1/flows", json=flow)

            with patch("apps.orchestrator.main.broadcast_status", new_callable=AsyncMock):
                resp = client.post(
                    f"/api/v1/flows/{flow['id']}/runs",
                    json={"input": {}},
                )
            assert resp.status_code == 202
            assert "logs" not in resp.json()
