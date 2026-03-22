"""Tests for N-24 Execution Analytics.

Covers:
  - AnalyticsService.get_workflow_analytics (unit, various scenarios)
  - AnalyticsService.get_node_analytics (unit, various scenarios)
  - GET /api/v1/analytics/workflows endpoint
  - GET /api/v1/analytics/nodes endpoint
"""

import asyncio
import time
import uuid

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

from apps.orchestrator.db import close_db_connections, init_db
from apps.orchestrator.main import app
from apps.orchestrator.repositories import WorkflowRunRepository
from apps.orchestrator.request_models import AnalyticsService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_data(
    *,
    flow_id: str,
    run_id: str | None = None,
    status: str = "success",
    start_time: float | None = None,
    end_time: float | None = None,
    results: dict | None = None,
    error: str | None = None,
) -> dict:
    """Build a minimal WorkflowRun seed dict."""
    now = time.time()
    return {
        "run_id": run_id or str(uuid.uuid4()),
        "flow_id": flow_id,
        "status": status,
        "start_time": start_time if start_time is not None else now,
        "end_time": end_time,
        "results": results or {},
        "error": error,
    }


# ---------------------------------------------------------------------------
# DB fixture (async)
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


# ---------------------------------------------------------------------------
# TestClient fixture (sync HTTP tests)
# ---------------------------------------------------------------------------


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


# ===========================================================================
# TestAnalyticsServiceWorkflows
# ===========================================================================


class TestAnalyticsServiceWorkflows:
    @pytest.mark.asyncio
    async def test_empty_db_returns_empty_list(self, db):
        result = await AnalyticsService.get_workflow_analytics()
        assert isinstance(result, list)
        assert result == []

    @pytest.mark.asyncio
    async def test_single_run_success_produces_one_entry(self, db):
        flow_id = f"flow-{uuid.uuid4().hex[:8]}"
        await WorkflowRunRepository.save(_run_data(flow_id=flow_id, status="success"))

        result = await AnalyticsService.get_workflow_analytics()
        assert isinstance(result, list)
        assert len(result) >= 1  # Gate 2
        entry = next(r for r in result if r["flow_id"] == flow_id)
        assert entry["run_count"] == 1
        assert entry["success_count"] == 1
        assert entry["error_count"] == 0

    @pytest.mark.asyncio
    async def test_single_run_error_increments_error_count(self, db):
        flow_id = f"flow-{uuid.uuid4().hex[:8]}"
        await WorkflowRunRepository.save(_run_data(flow_id=flow_id, status="error", error="boom"))

        result = await AnalyticsService.get_workflow_analytics()
        assert isinstance(result, list)
        assert len(result) >= 1  # Gate 2
        entry = next(r for r in result if r["flow_id"] == flow_id)
        assert entry["error_count"] == 1
        assert entry["success_count"] == 0

    @pytest.mark.asyncio
    async def test_multiple_flows_each_get_own_entry(self, db):
        fid_a = f"flow-a-{uuid.uuid4().hex[:6]}"
        fid_b = f"flow-b-{uuid.uuid4().hex[:6]}"
        await WorkflowRunRepository.save(_run_data(flow_id=fid_a, status="success"))
        await WorkflowRunRepository.save(_run_data(flow_id=fid_b, status="error"))

        result = await AnalyticsService.get_workflow_analytics()
        assert isinstance(result, list)
        assert len(result) >= 2  # Gate 2
        flow_ids = [r["flow_id"] for r in result]
        assert fid_a in flow_ids
        assert fid_b in flow_ids

    @pytest.mark.asyncio
    async def test_flow_id_filter_excludes_other_flows(self, db):
        fid_a = f"flow-a-{uuid.uuid4().hex[:6]}"
        fid_b = f"flow-b-{uuid.uuid4().hex[:6]}"
        await WorkflowRunRepository.save(_run_data(flow_id=fid_a, status="success"))
        await WorkflowRunRepository.save(_run_data(flow_id=fid_b, status="success"))

        result = await AnalyticsService.get_workflow_analytics(flow_id=fid_a)
        assert isinstance(result, list)
        assert len(result) >= 1  # Gate 2
        assert all(r["flow_id"] == fid_a for r in result)

    @pytest.mark.asyncio
    async def test_success_rate_zero_when_no_terminal_runs(self, db):
        flow_id = f"flow-{uuid.uuid4().hex[:8]}"
        # "running" and "idle" are not terminal
        await WorkflowRunRepository.save(_run_data(flow_id=flow_id, status="running"))
        await WorkflowRunRepository.save(_run_data(flow_id=flow_id, status="idle"))

        result = await AnalyticsService.get_workflow_analytics(flow_id=flow_id)
        assert isinstance(result, list)
        assert len(result) >= 1  # Gate 2
        entry = result[0]
        assert entry["success_rate"] == 0.0
        assert entry["error_rate"] == 0.0

    @pytest.mark.asyncio
    async def test_avg_duration_computed_correctly(self, db):
        flow_id = f"flow-{uuid.uuid4().hex[:8]}"
        base = time.time()
        await WorkflowRunRepository.save(
            _run_data(flow_id=flow_id, status="success", start_time=base, end_time=base + 10.0)
        )
        await WorkflowRunRepository.save(
            _run_data(flow_id=flow_id, status="success", start_time=base, end_time=base + 20.0)
        )

        result = await AnalyticsService.get_workflow_analytics(flow_id=flow_id)
        assert isinstance(result, list)
        assert len(result) >= 1  # Gate 2
        entry = result[0]
        assert entry["avg_duration_seconds"] == pytest.approx(15.0)

    @pytest.mark.asyncio
    async def test_sorted_by_last_run_at_descending(self, db):
        fid_old = f"flow-old-{uuid.uuid4().hex[:6]}"
        fid_new = f"flow-new-{uuid.uuid4().hex[:6]}"
        base = time.time()
        await WorkflowRunRepository.save(
            _run_data(flow_id=fid_old, status="success", start_time=base - 1000)
        )
        await WorkflowRunRepository.save(
            _run_data(flow_id=fid_new, status="success", start_time=base - 10)
        )

        result = await AnalyticsService.get_workflow_analytics()
        assert isinstance(result, list)
        assert len(result) >= 2  # Gate 2
        # The newest flow should come first
        ids = [r["flow_id"] for r in result]
        assert ids.index(fid_new) < ids.index(fid_old)


# ===========================================================================
# TestAnalyticsServiceNodes
# ===========================================================================


class TestAnalyticsServiceNodes:
    @pytest.mark.asyncio
    async def test_empty_results_returns_empty_list(self, db):
        flow_id = f"flow-{uuid.uuid4().hex[:8]}"
        await WorkflowRunRepository.save(_run_data(flow_id=flow_id, status="success", results={}))

        result = await AnalyticsService.get_node_analytics(flow_id=flow_id)
        assert isinstance(result, list)
        assert result == []

    @pytest.mark.asyncio
    async def test_node_appears_in_multiple_runs_aggregated(self, db):
        flow_id = f"flow-{uuid.uuid4().hex[:8]}"
        node_results = {"node-A": {"status": "success"}}
        await WorkflowRunRepository.save(
            _run_data(flow_id=flow_id, status="success", results=node_results)
        )
        await WorkflowRunRepository.save(
            _run_data(flow_id=flow_id, status="success", results=node_results)
        )

        result = await AnalyticsService.get_node_analytics(flow_id=flow_id)
        assert isinstance(result, list)
        assert len(result) >= 1  # Gate 2
        entry = next(r for r in result if r["node_id"] == "node-A")
        assert entry["execution_count"] == 2
        assert entry["success_count"] == 2

    @pytest.mark.asyncio
    async def test_success_rate_calculated_correctly(self, db):
        flow_id = f"flow-{uuid.uuid4().hex[:8]}"
        await WorkflowRunRepository.save(
            _run_data(
                flow_id=flow_id,
                status="success",
                results={"node-X": {"status": "success"}},
            )
        )
        await WorkflowRunRepository.save(
            _run_data(
                flow_id=flow_id,
                status="error",
                results={"node-X": {"status": "error"}},
            )
        )

        result = await AnalyticsService.get_node_analytics(flow_id=flow_id)
        assert isinstance(result, list)
        assert len(result) >= 1  # Gate 2
        entry = next(r for r in result if r["node_id"] == "node-X")
        assert entry["success_rate"] == pytest.approx(0.5)
        assert entry["execution_count"] == 2

    @pytest.mark.asyncio
    async def test_flow_id_filter_works_for_nodes(self, db):
        fid_a = f"flow-a-{uuid.uuid4().hex[:6]}"
        fid_b = f"flow-b-{uuid.uuid4().hex[:6]}"
        await WorkflowRunRepository.save(
            _run_data(flow_id=fid_a, status="success", results={"node-1": {"status": "success"}})
        )
        await WorkflowRunRepository.save(
            _run_data(flow_id=fid_b, status="success", results={"node-2": {"status": "success"}})
        )

        result = await AnalyticsService.get_node_analytics(flow_id=fid_a)
        assert isinstance(result, list)
        assert len(result) >= 1  # Gate 2
        assert all(r["flow_id"] == fid_a for r in result)
        node_ids = [r["node_id"] for r in result]
        assert "node-1" in node_ids
        assert "node-2" not in node_ids

    @pytest.mark.asyncio
    async def test_sorted_by_execution_count_descending(self, db):
        flow_id = f"flow-{uuid.uuid4().hex[:8]}"
        # node-A appears 3 times, node-B 1 time
        for _ in range(3):
            await WorkflowRunRepository.save(
                _run_data(
                    flow_id=flow_id,
                    status="success",
                    results={"node-A": {"status": "success"}},
                )
            )
        await WorkflowRunRepository.save(
            _run_data(
                flow_id=flow_id,
                status="success",
                results={"node-B": {"status": "success"}},
            )
        )

        result = await AnalyticsService.get_node_analytics(flow_id=flow_id)
        assert isinstance(result, list)
        assert len(result) >= 2  # Gate 2
        assert result[0]["node_id"] == "node-A"
        assert result[0]["execution_count"] == 3

    @pytest.mark.asyncio
    async def test_missing_duration_handled_gracefully(self, db):
        flow_id = f"flow-{uuid.uuid4().hex[:8]}"
        # No duration_seconds in node result
        await WorkflowRunRepository.save(
            _run_data(
                flow_id=flow_id,
                status="success",
                results={"node-Z": {"status": "success"}},
            )
        )

        result = await AnalyticsService.get_node_analytics(flow_id=flow_id)
        assert isinstance(result, list)
        assert len(result) >= 1  # Gate 2
        entry = next(r for r in result if r["node_id"] == "node-Z")
        assert entry["avg_duration_seconds"] is None

    @pytest.mark.asyncio
    async def test_multiple_node_types_in_same_run(self, db):
        flow_id = f"flow-{uuid.uuid4().hex[:8]}"
        results = {
            "llm-node": {"status": "success", "duration_seconds": 1.5},
            "transform-node": {"status": "success", "duration_seconds": 0.2},
            "http-node": {"status": "error"},
        }
        await WorkflowRunRepository.save(
            _run_data(flow_id=flow_id, status="error", results=results)
        )

        result = await AnalyticsService.get_node_analytics(flow_id=flow_id)
        assert isinstance(result, list)
        assert len(result) >= 3  # Gate 2
        node_ids = {r["node_id"] for r in result}
        assert "llm-node" in node_ids
        assert "transform-node" in node_ids
        assert "http-node" in node_ids

        llm = next(r for r in result if r["node_id"] == "llm-node")
        assert llm["avg_duration_seconds"] == pytest.approx(1.5)

        http = next(r for r in result if r["node_id"] == "http-node")
        assert http["error_count"] == 1
        assert http["success_count"] == 0


# ===========================================================================
# TestAnalyticsWorkflowsEndpoint
# ===========================================================================


class TestAnalyticsWorkflowsEndpoint:
    @pytest.mark.asyncio
    async def test_endpoint_returns_200(self, db, client):
        resp = client.get("/api/v1/analytics/workflows")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_empty_result_structure(self, db, client):
        resp = client.get("/api/v1/analytics/workflows")
        assert resp.status_code == 200
        body = resp.json()
        assert "workflows" in body
        assert "total_flows" in body
        assert isinstance(body["workflows"], list)
        assert isinstance(body["total_flows"], int)

    @pytest.mark.asyncio
    async def test_with_real_runs_gate2(self, db, client):
        flow_id = f"flow-ep-{uuid.uuid4().hex[:8]}"
        await WorkflowRunRepository.save(_run_data(flow_id=flow_id, status="success"))

        resp = client.get("/api/v1/analytics/workflows")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["workflows"]) >= 1  # Gate 2
        assert body["total_flows"] >= 1

    @pytest.mark.asyncio
    async def test_flow_id_filter_on_endpoint(self, db, client):
        fid_a = f"flow-ep-a-{uuid.uuid4().hex[:6]}"
        fid_b = f"flow-ep-b-{uuid.uuid4().hex[:6]}"
        await WorkflowRunRepository.save(_run_data(flow_id=fid_a, status="success"))
        await WorkflowRunRepository.save(_run_data(flow_id=fid_b, status="success"))

        resp = client.get(f"/api/v1/analytics/workflows?flow_id={fid_a}")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["workflows"]) >= 1  # Gate 2
        assert all(w["flow_id"] == fid_a for w in body["workflows"])

    @pytest.mark.asyncio
    async def test_total_flows_field_is_correct(self, db, client):
        fid_x = f"flow-x-{uuid.uuid4().hex[:6]}"
        fid_y = f"flow-y-{uuid.uuid4().hex[:6]}"
        await WorkflowRunRepository.save(_run_data(flow_id=fid_x, status="success"))
        await WorkflowRunRepository.save(_run_data(flow_id=fid_y, status="success"))

        # Filter to just one flow — total_flows should be 1
        resp = client.get(f"/api/v1/analytics/workflows?flow_id={fid_x}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_flows"] == len(body["workflows"])


# ===========================================================================
# TestAnalyticsNodesEndpoint
# ===========================================================================


class TestAnalyticsNodesEndpoint:
    @pytest.mark.asyncio
    async def test_endpoint_returns_200(self, db, client):
        resp = client.get("/api/v1/analytics/nodes")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_empty_result_structure(self, db, client):
        resp = client.get("/api/v1/analytics/nodes")
        assert resp.status_code == 200
        body = resp.json()
        assert "nodes" in body
        assert "total_nodes" in body
        assert isinstance(body["nodes"], list)
        assert isinstance(body["total_nodes"], int)

    @pytest.mark.asyncio
    async def test_with_runs_that_have_results_gate2(self, db, client):
        flow_id = f"flow-node-ep-{uuid.uuid4().hex[:6]}"
        await WorkflowRunRepository.save(
            _run_data(
                flow_id=flow_id,
                status="success",
                results={"my-node": {"status": "success"}},
            )
        )

        resp = client.get("/api/v1/analytics/nodes")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["nodes"]) >= 1  # Gate 2
        assert body["total_nodes"] >= 1

    @pytest.mark.asyncio
    async def test_flow_id_filter_on_nodes_endpoint(self, db, client):
        fid_a = f"flow-na-{uuid.uuid4().hex[:6]}"
        fid_b = f"flow-nb-{uuid.uuid4().hex[:6]}"
        await WorkflowRunRepository.save(
            _run_data(
                flow_id=fid_a, status="success", results={"node-alpha": {"status": "success"}}
            )
        )
        await WorkflowRunRepository.save(
            _run_data(flow_id=fid_b, status="success", results={"node-beta": {"status": "success"}})
        )

        resp = client.get(f"/api/v1/analytics/nodes?flow_id={fid_a}")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["nodes"]) >= 1  # Gate 2
        assert all(n["flow_id"] == fid_a for n in body["nodes"])
        node_ids = [n["node_id"] for n in body["nodes"]]
        assert "node-alpha" in node_ids
        assert "node-beta" not in node_ids

    @pytest.mark.asyncio
    async def test_total_nodes_field_matches_list_length(self, db, client):
        flow_id = f"flow-nc-{uuid.uuid4().hex[:6]}"
        await WorkflowRunRepository.save(
            _run_data(
                flow_id=flow_id,
                status="success",
                results={
                    "node-1": {"status": "success"},
                    "node-2": {"status": "error"},
                    "node-3": {"status": "success"},
                },
            )
        )

        resp = client.get(f"/api/v1/analytics/nodes?flow_id={flow_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_nodes"] == len(body["nodes"])
        assert body["total_nodes"] >= 3  # Gate 2: all 3 nodes tracked
