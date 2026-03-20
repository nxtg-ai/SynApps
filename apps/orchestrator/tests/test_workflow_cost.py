"""
N-41: Workflow Cost Tracker
Tests for CostTrackerStore, _estimate_node_cost, and cost endpoints.
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from apps.orchestrator.main import (
    CostTrackerStore,
    ExecutionCostRecord,
    _estimate_node_cost,
    app,
    cost_tracker_store,
    execution_log_store,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _register(client: TestClient, email: str | None = None) -> str:
    email = email or f"cost-{uuid.uuid4().hex[:8]}@test.com"
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "CostPass1!"},
    )
    assert resp.status_code in (200, 201), resp.text
    return resp.json()["access_token"]


FLOW_ID = "cost-test-flow-001"


@pytest.fixture(autouse=True)
def _clean():
    cost_tracker_store.reset()
    execution_log_store.reset()
    yield
    cost_tracker_store.reset()
    execution_log_store.reset()


# ===========================================================================
# TestCostTrackerStore — unit
# ===========================================================================


class TestCostTrackerStore:
    def test_record_returns_cost_record(self):
        store = CostTrackerStore()
        node_costs = [
            {
                "node_id": "n1",
                "node_type": "llm",
                "token_input": 100,
                "token_output": 50,
                "model": "gpt-4o",
                "estimated_usd": 0.00125,
                "api_calls": 0,
            },
        ]
        rec = store.record("exec-1", FLOW_ID, node_costs)
        assert isinstance(rec, ExecutionCostRecord)
        assert rec.execution_id == "exec-1"
        assert rec.flow_id == FLOW_ID

    def test_get_returns_stored_record(self):
        store = CostTrackerStore()
        store.record("exec-2", FLOW_ID, [])
        rec = store.get("exec-2")
        assert rec is not None
        assert rec.execution_id == "exec-2"

    def test_get_returns_none_for_unknown(self):
        store = CostTrackerStore()
        rec = store.get("does-not-exist")
        assert rec is None

    def test_list_for_flow_returns_all_records(self):
        store = CostTrackerStore()
        store.record("exec-a", FLOW_ID, [])
        store.record("exec-b", FLOW_ID, [])
        store.record("exec-c", "other-flow", [])
        results = store.list_for_flow(FLOW_ID)
        assert isinstance(results, list)
        assert len(results) >= 2  # Gate 2
        assert all(r.flow_id == FLOW_ID for r in results)

    def test_totals_computed_correctly(self):
        store = CostTrackerStore()
        node_costs = [
            {
                "node_id": "n1",
                "node_type": "llm",
                "token_input": 200,
                "token_output": 100,
                "model": "gpt-4o",
                "estimated_usd": 0.002500,
                "api_calls": 0,
            },
            {
                "node_id": "n2",
                "node_type": "http",
                "token_input": 0,
                "token_output": 0,
                "model": "",
                "estimated_usd": 0.0,
                "api_calls": 1,
            },
        ]
        rec = store.record("exec-totals", FLOW_ID, node_costs)
        assert rec.total_tokens == 300  # 200 + 100
        assert abs(rec.total_usd - 0.002500) < 1e-9

    def test_reset_clears_all_records(self):
        store = CostTrackerStore()
        store.record("exec-r1", FLOW_ID, [])
        store.record("exec-r2", FLOW_ID, [])
        store.reset()
        assert store.get("exec-r1") is None
        assert store.get("exec-r2") is None
        assert store.list_for_flow(FLOW_ID) == []


# ===========================================================================
# TestEstimateNodeCost — unit
# ===========================================================================


class TestEstimateNodeCost:
    def test_llm_node_has_nonzero_tokens(self):
        node_data = {"prompt": "Hello world " * 10, "model": "gpt-4o"}
        output = {"text": "Some response text here"}
        result = _estimate_node_cost("llm", node_data, output)
        assert result["token_input"] > 0
        assert result["token_output"] > 0

    def test_http_node_has_api_calls_one(self):
        result = _estimate_node_cost("http", {}, {})
        assert result["api_calls"] == 1
        assert result["token_input"] == 0
        assert result["token_output"] == 0

    def test_unknown_node_is_all_zero(self):
        result = _estimate_node_cost("transform", {}, {})
        assert result["token_input"] == 0
        assert result["token_output"] == 0
        assert result["estimated_usd"] == 0.0
        assert result["api_calls"] == 0

    def test_estimated_usd_is_float(self):
        node_data = {"prompt": "test prompt", "model": "gpt-4o"}
        result = _estimate_node_cost("llm", node_data, {"text": "out"})
        assert isinstance(result["estimated_usd"], float)

    def test_model_name_captured(self):
        node_data = {"prompt": "hello", "model": "gpt-3.5-turbo"}
        result = _estimate_node_cost("llm", node_data, {})
        assert result["model"] == "gpt-3.5-turbo"


# ===========================================================================
# TestCostEndpoints — HTTP
# ===========================================================================


class TestCostEndpoints:
    def test_get_cost_200_when_record_exists(self):
        cost_tracker_store.record("exec-http-1", FLOW_ID, [])
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get(
                "/api/v1/executions/exec-http-1/cost",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["execution_id"] == "exec-http-1"
        assert data["flow_id"] == FLOW_ID

    def test_get_cost_404_unknown_execution(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get(
                "/api/v1/executions/totally-unknown-exec/cost",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 404

    def test_get_cost_requires_auth(self):
        with TestClient(app) as client:
            resp = client.get(
                "/api/v1/executions/exec-http-1/cost",
                headers={"Authorization": "Bearer invalid.token.here"},
            )
        assert resp.status_code == 401

    def test_get_cost_summary_200_structure(self):
        cost_tracker_store.record("exec-s1", FLOW_ID, [])
        cost_tracker_store.record("exec-s2", FLOW_ID, [])
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get(
                f"/api/v1/workflows/{FLOW_ID}/cost-summary",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "flow_id" in data
        assert "run_count" in data
        assert "total_usd" in data
        assert "avg_usd_per_run" in data
        assert "total_tokens" in data
        assert "avg_tokens_per_run" in data
        assert "records" in data

    def test_get_cost_summary_no_runs_returns_zeros(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get(
                "/api/v1/workflows/no-runs-flow/cost-summary",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["run_count"] == 0
        assert data["total_usd"] == 0.0
        assert data["records"] == []

    def test_get_cost_summary_requires_auth(self):
        with TestClient(app) as client:
            resp = client.get(
                f"/api/v1/workflows/{FLOW_ID}/cost-summary",
                headers={"Authorization": "Bearer invalid.token.here"},
            )
        assert resp.status_code == 401

    def test_run_count_matches_records(self):
        cost_tracker_store.record("exec-rc1", FLOW_ID, [])
        cost_tracker_store.record("exec-rc2", FLOW_ID, [])
        cost_tracker_store.record("exec-rc3", FLOW_ID, [])
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get(
                f"/api/v1/workflows/{FLOW_ID}/cost-summary",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["run_count"] == 3
        assert len(data["records"]) >= 1  # Gate 2

    def test_totals_match_sum_of_records(self):
        nc1 = [
            {
                "node_id": "n1",
                "node_type": "llm",
                "token_input": 100,
                "token_output": 50,
                "model": "gpt-4o",
                "estimated_usd": 0.001750,
                "api_calls": 0,
            }
        ]
        nc2 = [
            {
                "node_id": "n2",
                "node_type": "llm",
                "token_input": 200,
                "token_output": 80,
                "model": "gpt-4o",
                "estimated_usd": 0.002200,
                "api_calls": 0,
            }
        ]
        cost_tracker_store.record("exec-sum1", FLOW_ID, nc1)
        cost_tracker_store.record("exec-sum2", FLOW_ID, nc2)
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get(
                f"/api/v1/workflows/{FLOW_ID}/cost-summary",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 200
        data = resp.json()
        expected_total = 0.001750 + 0.002200
        assert abs(data["total_usd"] - expected_total) < 1e-9
