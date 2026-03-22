"""
N-33: Workflow Execution SLA Tracking
Tests for SLAStore, SLA policy endpoints, violation detection, and dashboard.
"""

import time
import uuid

import pytest
from fastapi.testclient import TestClient

from apps.orchestrator.main import app
from apps.orchestrator.stores import (
    SLAStore,
    sla_store,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _register(client: TestClient, email: str | None = None) -> str:
    """Register a user and return the access token."""
    email = email or f"sla-{uuid.uuid4().hex[:8]}@test.com"
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "SlaPass1!"},
    )
    assert resp.status_code in (200, 201), resp.text
    return resp.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _get_user_id(client: TestClient, token: str) -> str:
    resp = client.get("/api/v1/auth/me", headers=_auth(token))
    return resp.json()["id"]


def _create_flow(client: TestClient, token: str, name: str = "SLA Test") -> str:
    """Create a minimal flow with start/end nodes and return its ID."""
    flow_payload = {
        "name": name,
        "nodes": [
            {
                "id": "start",
                "type": "start",
                "position": {"x": 0, "y": 0},
                "data": {"label": "Start"},
            },
            {
                "id": "end",
                "type": "end",
                "position": {"x": 0, "y": 100},
                "data": {"label": "End"},
            },
        ],
        "edges": [
            {"id": "e1", "source": "start", "target": "end"},
        ],
    }
    resp = client.post("/api/v1/flows", json=flow_payload, headers=_auth(token))
    assert resp.status_code == 201
    return resp.json()["id"]


def _run_flow_and_wait(client: TestClient, token: str, flow_id: str) -> str:
    """Run a flow via API and poll until terminal status. Return run_id."""
    resp = client.post(
        f"/api/v1/flows/{flow_id}/runs",
        json={"input": {}},
        headers=_auth(token),
    )
    assert resp.status_code in (200, 201, 202), resp.text
    run_id = resp.json()["run_id"]
    terminal = {"success", "error", "failed"}
    deadline = time.time() + 5.0
    while time.time() < deadline:
        status_resp = client.get(f"/api/v1/history/{run_id}")
        if status_resp.status_code == 200 and status_resp.json().get("status") in terminal:
            break
        time.sleep(0.05)
    return run_id


FLOW_ID = "sla-test-flow-001"
OWNER_ID = "owner-001"


@pytest.fixture(autouse=True)
def _clean():
    sla_store.reset()
    yield
    sla_store.reset()


# ===========================================================================
# TestSLAStore — unit tests (8)
# ===========================================================================


class TestSLAStore:
    def test_set_policy_creates_with_correct_fields(self):
        store = SLAStore()
        policy = store.set_policy(FLOW_ID, OWNER_ID, 10.0, 0.8)
        assert policy["flow_id"] == FLOW_ID
        assert policy["owner_id"] == OWNER_ID
        assert policy["max_duration_seconds"] == 10.0
        assert policy["alert_threshold_pct"] == 0.8
        assert "policy_id" in policy
        assert "created_at" in policy

    def test_get_policy_returns_none_for_unknown(self):
        store = SLAStore()
        result = store.get_policy("nonexistent-flow")
        assert result is None

    def test_delete_policy_returns_false_for_unknown(self):
        store = SLAStore()
        result = store.delete_policy("nonexistent-flow")
        assert result is False

    def test_list_policies_filters_by_owner_id(self):
        store = SLAStore()
        store.set_policy("flow-a", "owner-1", 5.0)
        store.set_policy("flow-b", "owner-1", 10.0)
        store.set_policy("flow-c", "owner-2", 15.0)
        policies = store.list_policies("owner-1")
        assert isinstance(policies, list)
        assert len(policies) >= 2  # Gate 2
        assert all(p["owner_id"] == "owner-1" for p in policies)

    def test_record_violation_calculates_pct_over(self):
        store = SLAStore()
        violation = store.record_violation(
            policy_id="pol-1",
            flow_id=FLOW_ID,
            run_id="run-1",
            actual_duration=15.0,
            max_duration=10.0,
        )
        assert violation["pct_over"] == 50.0
        assert violation["actual_duration_seconds"] == 15.0
        assert violation["max_duration_seconds"] == 10.0
        assert "violation_id" in violation

    def test_list_violations_returns_newest_first(self):
        store = SLAStore()
        v1 = store.record_violation("pol-1", FLOW_ID, "run-1", 12.0, 10.0)
        v2 = store.record_violation("pol-1", FLOW_ID, "run-2", 14.0, 10.0)
        violations = store.list_violations()
        assert isinstance(violations, list)
        assert len(violations) >= 2  # Gate 2
        # v2 created after v1, so v2 should be first
        assert violations[0]["violation_id"] == v2["violation_id"]
        assert violations[1]["violation_id"] == v1["violation_id"]

    def test_list_violations_filters_by_flow_id(self):
        store = SLAStore()
        store.record_violation("pol-1", "flow-a", "run-1", 12.0, 10.0)
        store.record_violation("pol-1", "flow-b", "run-2", 14.0, 10.0)
        violations = store.list_violations(flow_id="flow-a")
        assert isinstance(violations, list)
        assert len(violations) >= 1  # Gate 2
        assert all(v["flow_id"] == "flow-a" for v in violations)

    def test_compliance_stats_returns_correct_rate(self):
        store = SLAStore()
        store.set_policy("flow-x", "owner-1", 10.0)
        # Simulate 10 runs, 2 violations
        for _ in range(10):
            store.increment_run_count("owner-1")
        store.record_violation("pol-1", "flow-x", "run-1", 12.0, 10.0)
        store.record_violation("pol-1", "flow-x", "run-2", 15.0, 10.0)
        stats = store.compliance_stats("owner-1")
        assert stats["total_runs"] == 10
        assert stats["violations"] == 2
        assert stats["compliance_rate_pct"] == 80.0
        assert isinstance(stats["by_flow"], list)
        assert len(stats["by_flow"]) >= 1  # Gate 2


# ===========================================================================
# TestSLAPolicyEndpoints — integration tests (6)
# ===========================================================================


class TestSLAPolicyEndpoints:
    def test_put_returns_200_with_policy(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.put(
                f"/api/v1/sla/policies/{FLOW_ID}",
                json={"max_duration_seconds": 30.0},
                headers=_auth(token),
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["flow_id"] == FLOW_ID
            assert data["max_duration_seconds"] == 30.0
            assert data["alert_threshold_pct"] == 0.8

    def test_get_returns_200_after_setting(self):
        with TestClient(app) as client:
            token = _register(client)
            client.put(
                f"/api/v1/sla/policies/{FLOW_ID}",
                json={"max_duration_seconds": 20.0},
                headers=_auth(token),
            )
            resp = client.get(
                f"/api/v1/sla/policies/{FLOW_ID}",
                headers=_auth(token),
            )
            assert resp.status_code == 200
            assert resp.json()["max_duration_seconds"] == 20.0

    def test_get_returns_404_when_not_set(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get(
                "/api/v1/sla/policies/nonexistent-flow",
                headers=_auth(token),
            )
            assert resp.status_code == 404
            assert "error" in resp.json()

    def test_delete_returns_204(self):
        with TestClient(app) as client:
            token = _register(client)
            client.put(
                f"/api/v1/sla/policies/{FLOW_ID}",
                json={"max_duration_seconds": 10.0},
                headers=_auth(token),
            )
            resp = client.delete(
                f"/api/v1/sla/policies/{FLOW_ID}",
                headers=_auth(token),
            )
            assert resp.status_code == 204

    def test_list_returns_callers_policies(self):
        with TestClient(app) as client:
            token = _register(client)
            client.put(
                "/api/v1/sla/policies/flow-1",
                json={"max_duration_seconds": 10.0},
                headers=_auth(token),
            )
            client.put(
                "/api/v1/sla/policies/flow-2",
                json={"max_duration_seconds": 20.0},
                headers=_auth(token),
            )
            resp = client.get(
                "/api/v1/sla/policies",
                headers=_auth(token),
            )
            assert resp.status_code == 200
            data = resp.json()
            assert isinstance(data, list)
            assert len(data) >= 2  # Gate 2

    def test_put_requires_auth(self):
        with TestClient(app) as client:
            # Register a user first so anonymous bootstrap is disabled
            _register(client)
            resp = client.put(
                f"/api/v1/sla/policies/{FLOW_ID}",
                json={"max_duration_seconds": 10.0},
            )
            assert resp.status_code in (401, 403)
            assert "error" in resp.json()


# ===========================================================================
# TestSLAViolationDetection — integration tests (5)
# ===========================================================================


class TestSLAViolationDetection:
    def test_no_violation_when_under_sla(self):
        """Execution within SLA does not record a violation."""
        with TestClient(app) as client:
            token = _register(client)
            user_id = _get_user_id(client, token)
            flow_id = _create_flow(client, token, "Fast Flow")
            # Set a generous SLA (100 seconds)
            sla_store.set_policy(flow_id, user_id, 100.0)
            _run_flow_and_wait(client, token, flow_id)
            violations = sla_store.list_violations(flow_id=flow_id)
            assert violations == []

    def test_violation_recorded_when_exceeds_sla(self):
        """Execution exceeding SLA threshold records a violation."""
        with TestClient(app) as client:
            token = _register(client)
            user_id = _get_user_id(client, token)
            flow_id = _create_flow(client, token, "SLA Breach Flow")
            # Set an impossibly tight SLA (0.001 seconds)
            sla_store.set_policy(flow_id, user_id, 0.001)
            _run_flow_and_wait(client, token, flow_id)
            violations = sla_store.list_violations(flow_id=flow_id)
            assert isinstance(violations, list)
            assert len(violations) >= 1  # Gate 2
            assert violations[0]["flow_id"] == flow_id

    def test_violations_endpoint_returns_items(self):
        """Violations API endpoint returns recorded violations."""
        with TestClient(app) as client:
            token = _register(client)
            user_id = _get_user_id(client, token)
            # Directly record a violation in the store
            sla_store.set_policy("flow-v", user_id, 5.0)
            sla_store.record_violation("pol-1", "flow-v", "run-1", 10.0, 5.0)
            resp = client.get(
                "/api/v1/sla/violations",
                headers=_auth(token),
            )
            assert resp.status_code == 200
            data = resp.json()
            assert isinstance(data, list)
            assert len(data) >= 1  # Gate 2

    def test_dashboard_compliance_below_100_after_violation(self):
        """Dashboard shows < 100% compliance after a violation."""
        with TestClient(app) as client:
            token = _register(client)
            user_id = _get_user_id(client, token)
            sla_store.set_policy("flow-d", user_id, 5.0)
            sla_store.increment_run_count(user_id)
            sla_store.increment_run_count(user_id)
            sla_store.record_violation("pol-1", "flow-d", "run-1", 10.0, 5.0)
            resp = client.get(
                "/api/v1/sla/dashboard",
                headers=_auth(token),
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["compliance_rate_pct"] < 100.0

    def test_dashboard_compliance_100_when_no_violations(self):
        """Dashboard shows 100% compliance when no violations exist."""
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get(
                "/api/v1/sla/dashboard",
                headers=_auth(token),
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["compliance_rate_pct"] == 100.0


# ===========================================================================
# TestSLADashboard — integration tests (4)
# ===========================================================================


class TestSLADashboard:
    def test_dashboard_returns_200_with_required_keys(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get(
                "/api/v1/sla/dashboard",
                headers=_auth(token),
            )
            assert resp.status_code == 200
            data = resp.json()
            assert "total_runs" in data
            assert "violations" in data
            assert "compliance_rate_pct" in data
            assert "by_flow" in data

    def test_dashboard_requires_auth(self):
        with TestClient(app) as client:
            # Register a user first so anonymous bootstrap is disabled
            _register(client)
            resp = client.get("/api/v1/sla/dashboard")
            assert resp.status_code in (401, 403)
            assert "error" in resp.json()

    def test_by_flow_breakdown_present(self):
        with TestClient(app) as client:
            token = _register(client)
            user_id = _get_user_id(client, token)
            sla_store.set_policy("flow-bf", user_id, 5.0)
            sla_store.increment_run_count(user_id)
            sla_store.record_violation("pol-bf", "flow-bf", "run-1", 8.0, 5.0)
            resp = client.get(
                "/api/v1/sla/dashboard",
                headers=_auth(token),
            )
            data = resp.json()
            assert isinstance(data["by_flow"], list)
            assert len(data["by_flow"]) >= 1  # Gate 2
            assert data["by_flow"][0]["flow_id"] == "flow-bf"

    def test_total_runs_increases(self):
        with TestClient(app) as client:
            token = _register(client)
            user_id = _get_user_id(client, token)
            sla_store.set_policy("flow-tr", user_id, 100.0)
            # Initial state
            resp1 = client.get(
                "/api/v1/sla/dashboard",
                headers=_auth(token),
            )
            initial_runs = resp1.json()["total_runs"]
            # Simulate runs
            sla_store.increment_run_count(user_id)
            sla_store.increment_run_count(user_id)
            resp2 = client.get(
                "/api/v1/sla/dashboard",
                headers=_auth(token),
            )
            assert resp2.json()["total_runs"] == initial_runs + 2
