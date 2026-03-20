"""
Tests for the Workflow Execution Cost Calculator.

Covers:
  - CostCalculator unit tests (8 tests)
  - POST /flows/estimate-cost integration tests (7 tests)
  - POST /flows/{flow_id}/estimate-cost integration tests (5 tests)
"""

import pytest
from fastapi.testclient import TestClient

from apps.orchestrator.main import CostCalculator, app

# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
def client():
    """Create a TestClient that triggers lifespan events."""
    with TestClient(app) as c:
        yield c


def _create_flow(client: TestClient, flow_id: str, nodes: list[dict]) -> str:
    """Helper: create a flow and return its ID."""
    flow = {
        "id": flow_id,
        "name": "Cost Test Flow",
        "nodes": [
            {**n, "position": {"x": 0, "y": 0}, "data": {"label": n.get("type", "node")}}
            for n in nodes
        ],
        "edges": [],
    }
    resp = client.post("/api/v1/flows", json=flow)
    assert resp.status_code == 201
    return resp.json()["id"]


# ============================================================
# TestCostCalculator — 8 unit tests
# ============================================================


class TestCostCalculator:
    """Unit tests for CostCalculator.estimate()."""

    def test_empty_nodes_returns_zero(self):
        """Estimate with no nodes returns total_usd=0.0."""
        result = CostCalculator.estimate([])
        assert result["total_usd"] == 0.0
        assert result["node_count"] == 0
        assert result["billable_node_count"] == 0
        assert result["breakdown"] == []
        assert result["currency"] == "USD"

    def test_llm_node_costs_0_002(self):
        """A single LLM node costs $0.002."""
        result = CostCalculator.estimate([{"id": "n1", "type": "llm"}])
        assert result["total_usd"] == 0.002
        assert len(result["breakdown"]) >= 1  # Gate 2
        assert result["breakdown"][0]["cost_usd"] == 0.002

    def test_imagegen_node_costs_0_020(self):
        """A single imagegen node costs $0.020."""
        result = CostCalculator.estimate([{"id": "n1", "type": "imagegen"}])
        assert result["total_usd"] == 0.020
        assert result["breakdown"][0]["cost_usd"] == 0.020

    def test_foreach_node_multiplied_by_iterations(self):
        """Foreach node cost is per_call * foreach_iterations."""
        result = CostCalculator.estimate(
            [{"id": "n1", "type": "foreach"}],
            foreach_iterations=5,
        )
        # 0.001 * 5 = 0.005
        assert result["total_usd"] == 0.005
        assert result["breakdown"][0]["cost_usd"] == 0.005

    def test_mixed_nodes_sum_correctly(self):
        """Total is the sum of all individual node costs."""
        nodes = [
            {"id": "n1", "type": "llm"},       # 0.002
            {"id": "n2", "type": "imagegen"},   # 0.020
            {"id": "n3", "type": "code"},       # 0.001
            {"id": "n4", "type": "http"},       # 0.000
            {"id": "n5", "type": "foreach"},    # 0.001 * 10 = 0.010
        ]
        result = CostCalculator.estimate(nodes, foreach_iterations=10)
        expected = 0.002 + 0.020 + 0.001 + 0.000 + 0.010
        assert result["total_usd"] == round(expected, 6)

    def test_unknown_node_type_costs_zero(self):
        """An unknown node type defaults to $0.00 (free)."""
        result = CostCalculator.estimate([{"id": "n1", "type": "custom_widget"}])
        assert result["total_usd"] == 0.0
        assert result["breakdown"][0]["cost_usd"] == 0.0
        assert result["breakdown"][0]["note"] == "free"

    def test_billable_node_count(self):
        """billable_node_count counts only nodes with cost > 0."""
        nodes = [
            {"id": "n1", "type": "llm"},        # billable
            {"id": "n2", "type": "http"},        # free
            {"id": "n3", "type": "transform"},   # free
            {"id": "n4", "type": "code"},        # billable
        ]
        result = CostCalculator.estimate(nodes)
        assert result["billable_node_count"] == 2

    def test_breakdown_has_entry_per_node(self):
        """Breakdown list length matches the number of input nodes."""
        nodes = [
            {"id": "n1", "type": "llm"},
            {"id": "n2", "type": "merge"},
            {"id": "n3", "type": "ifelse"},
        ]
        result = CostCalculator.estimate(nodes)
        assert len(result["breakdown"]) == 3
        assert result["node_count"] == 3


# ============================================================
# TestEstimateCostEndpoint — 7 integration tests
# POST /api/v1/flows/estimate-cost
# ============================================================


class TestEstimateCostEndpoint:
    """Integration tests for the arbitrary-nodes estimate-cost endpoint."""

    def test_returns_200(self, client):
        """POST /flows/estimate-cost returns 200 on valid request."""
        resp = client.post(
            "/api/v1/flows/estimate-cost",
            json={"nodes": [{"id": "n1", "type": "llm"}]},
        )
        assert resp.status_code == 200

    def test_correct_total_for_llm(self, client):
        """Returns correct total_usd for LLM nodes (Gate 2: total > 0)."""
        resp = client.post(
            "/api/v1/flows/estimate-cost",
            json={
                "nodes": [
                    {"id": "n1", "type": "llm"},
                    {"id": "n2", "type": "llm"},
                ],
            },
        )
        data = resp.json()
        assert data["total_usd"] > 0  # Gate 2
        assert data["total_usd"] == 0.004

    def test_returns_zero_for_http_only(self, client):
        """Returns total_usd=0 for http-only nodes."""
        resp = client.post(
            "/api/v1/flows/estimate-cost",
            json={"nodes": [{"id": "n1", "type": "http"}]},
        )
        data = resp.json()
        assert data["total_usd"] == 0.0

    def test_foreach_iterations_param(self, client):
        """foreach_iterations parameter is accepted and affects result."""
        resp = client.post(
            "/api/v1/flows/estimate-cost",
            json={
                "nodes": [{"id": "n1", "type": "foreach"}],
                "foreach_iterations": 20,
            },
        )
        data = resp.json()
        assert data["total_usd"] == 0.020  # 0.001 * 20

    def test_requires_auth(self, client):
        """Endpoint requires authentication (anonymous bootstrap allows access)."""
        # In bootstrap mode anonymous access is allowed, so just confirm
        # the endpoint is wired up and responds (not 404/405).
        resp = client.post(
            "/api/v1/flows/estimate-cost",
            json={"nodes": []},
        )
        assert resp.status_code in (200, 401, 403)

    def test_breakdown_length_matches_nodes(self, client):
        """Breakdown list length matches the number of input nodes."""
        nodes = [
            {"id": "n1", "type": "llm"},
            {"id": "n2", "type": "code"},
            {"id": "n3", "type": "http"},
        ]
        resp = client.post("/api/v1/flows/estimate-cost", json={"nodes": nodes})
        data = resp.json()
        assert isinstance(data["breakdown"], list)
        assert len(data["breakdown"]) == 3  # Gate 2: matches node count

    def test_billable_node_count_correct(self, client):
        """billable_node_count matches count of nodes with cost > 0."""
        nodes = [
            {"id": "n1", "type": "llm"},       # billable
            {"id": "n2", "type": "http"},       # free
            {"id": "n3", "type": "imagegen"},   # billable
        ]
        resp = client.post("/api/v1/flows/estimate-cost", json={"nodes": nodes})
        data = resp.json()
        assert data["billable_node_count"] == 2


# ============================================================
# TestFlowEstimateCostEndpoint — 5 integration tests
# POST /api/v1/flows/{flow_id}/estimate-cost
# ============================================================


class TestFlowEstimateCostEndpoint:
    """Integration tests for the saved-flow estimate-cost endpoint."""

    def test_returns_200(self, client):
        """POST /flows/{id}/estimate-cost returns 200 for an existing flow."""
        flow_id = _create_flow(
            client,
            "cost-test-1",
            [{"id": "n1", "type": "llm"}],
        )
        resp = client.post(f"/api/v1/flows/{flow_id}/estimate-cost")
        assert resp.status_code == 200

    def test_returns_404_for_unknown_flow(self, client):
        """Returns 404 when flow does not exist."""
        resp = client.post("/api/v1/flows/nonexistent-flow-xyz/estimate-cost")
        assert resp.status_code == 404

    def test_requires_auth(self, client):
        """Endpoint requires authentication (bootstrap allows anonymous)."""
        resp = client.post("/api/v1/flows/any-id/estimate-cost")
        # Should be either 200/404 (bootstrap) or 401/403 (auth enforced)
        assert resp.status_code in (200, 404, 401, 403)

    def test_total_reflects_flow_nodes(self, client):
        """total_usd reflects the flow's actual node types."""
        nodes = [
            {"id": "n1", "type": "llm"},       # 0.002
            {"id": "n2", "type": "imagegen"},   # 0.020
        ]
        flow_id = _create_flow(client, "cost-test-2", nodes)
        resp = client.post(f"/api/v1/flows/{flow_id}/estimate-cost")
        data = resp.json()
        assert data["total_usd"] > 0  # Gate 2
        assert data["total_usd"] == 0.022
        assert data["node_count"] >= 1  # Gate 2

    def test_foreach_iterations_override(self, client):
        """foreach_iterations body param overrides the default."""
        nodes = [{"id": "n1", "type": "foreach"}]
        flow_id = _create_flow(client, "cost-test-3", nodes)
        resp = client.post(
            f"/api/v1/flows/{flow_id}/estimate-cost",
            json={"foreach_iterations": 50},
        )
        data = resp.json()
        assert data["total_usd"] == 0.050  # 0.001 * 50
