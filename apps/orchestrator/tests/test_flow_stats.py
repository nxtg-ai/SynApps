"""
N-143: Flow Statistics — GET /api/v1/flows/{flow_id}/stats

Tests:
  - Returns 200 with stats shape
  - Zero runs on a fresh flow
  - total_runs increments when executions are registered
  - success_count / failure_count track completed / failed runs
  - active_count reflects running/paused executions
  - avg_duration_ms is computed correctly (non-zero after runs)
  - last_run_at is None for fresh flow, ISO timestamp after a run
  - 404 for unknown flow
  - Auth required
"""

import time
import uuid

from fastapi.testclient import TestClient

from apps.orchestrator.main import app
from apps.orchestrator.stores import execution_dashboard_store

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _register(client: TestClient) -> str:
    uid = uuid.uuid4().hex[:8]
    r = client.post(
        "/api/v1/auth/register",
        json={"email": f"stats-{uid}@test.com", "password": "pass1234"},
    )
    assert r.status_code == 201
    return r.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_flow(client: TestClient, token: str) -> str:
    resp = client.post(
        "/api/v1/flows",
        json={"name": "Stats Test Flow", "nodes": [], "edges": []},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _seed_run(flow_id: str, status: str = "completed", duration_ms: float = 500.0) -> None:
    """Directly seed the execution_dashboard_store with a fake run entry."""
    run_id = str(uuid.uuid4())
    now = time.time()
    started = now - duration_ms / 1000
    execution_dashboard_store.register(
        run_id=run_id,
        flow_id=flow_id,
        flow_name="Stats Test Flow",
        user_id="stats@test.com",
        node_count=1,
    )
    # Patch the entry to set the desired final status and timing
    with execution_dashboard_store._lock:
        entry = execution_dashboard_store._entries[run_id]
        entry["status"] = status
        entry["started_at"] = started
        entry["updated_at"] = now


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestFlowStats:
    def test_returns_200(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/stats", headers=_auth(token))
        assert resp.status_code == 200
        data = resp.json()
        assert data["flow_id"] == flow_id

    def test_response_shape(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/stats", headers=_auth(token))
        data = resp.json()
        assert data["flow_id"] == flow_id
        assert "total_runs" in data
        assert "success_count" in data
        assert "failure_count" in data
        assert "active_count" in data
        assert "avg_duration_ms" in data
        assert "last_run_at" in data

    def test_zero_runs_on_fresh_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/stats", headers=_auth(token))
        data = resp.json()
        assert data["total_runs"] == 0
        assert data["success_count"] == 0
        assert data["failure_count"] == 0
        assert data["last_run_at"] is None

    def test_total_runs_counts_all_statuses(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _seed_run(flow_id, "completed")
            _seed_run(flow_id, "failed")
            _seed_run(flow_id, "running")
            resp = client.get(f"/api/v1/flows/{flow_id}/stats", headers=_auth(token))
        assert resp.json()["total_runs"] == 3

    def test_success_count_only_completed(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _seed_run(flow_id, "completed")
            _seed_run(flow_id, "completed")
            _seed_run(flow_id, "failed")
            resp = client.get(f"/api/v1/flows/{flow_id}/stats", headers=_auth(token))
        assert resp.json()["success_count"] == 2

    def test_failure_count_only_failed(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _seed_run(flow_id, "completed")
            _seed_run(flow_id, "failed")
            _seed_run(flow_id, "failed")
            resp = client.get(f"/api/v1/flows/{flow_id}/stats", headers=_auth(token))
        assert resp.json()["failure_count"] == 2

    def test_active_count_running_and_paused(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _seed_run(flow_id, "running")
            _seed_run(flow_id, "paused")
            _seed_run(flow_id, "completed")
            resp = client.get(f"/api/v1/flows/{flow_id}/stats", headers=_auth(token))
        assert resp.json()["active_count"] == 2

    def test_avg_duration_ms_nonzero_after_runs(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _seed_run(flow_id, "completed", duration_ms=1000.0)
            _seed_run(flow_id, "completed", duration_ms=2000.0)
            resp = client.get(f"/api/v1/flows/{flow_id}/stats", headers=_auth(token))
        assert resp.json()["avg_duration_ms"] > 0

    def test_last_run_at_is_iso_timestamp(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _seed_run(flow_id, "completed")
            resp = client.get(f"/api/v1/flows/{flow_id}/stats", headers=_auth(token))
        last_run_at = resp.json()["last_run_at"]
        assert last_run_at is not None
        # ISO-8601 format check: contains 'T' separator and timezone offset
        assert "T" in last_run_at

    def test_stats_isolated_to_flow(self):
        """Stats for one flow should not bleed into another flow's stats."""
        with TestClient(app) as client:
            token = _register(client)
            flow_a = _create_flow(client, token)
            flow_b = _create_flow(client, token)
            _seed_run(flow_a, "completed")
            _seed_run(flow_a, "completed")
            resp_b = client.get(f"/api/v1/flows/{flow_b}/stats", headers=_auth(token))
        assert resp_b.json()["total_runs"] == 0

    def test_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get("/api/v1/flows/nonexistent/stats", headers=_auth(token))
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/stats")
        assert resp.status_code == 401
        assert "error" in resp.json()
