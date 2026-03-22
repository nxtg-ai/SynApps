"""
N-151: Flow Rate Limiting — GET/PUT/DELETE /api/v1/flows/{flow_id}/rate-limit
                             POST /flows/{id}/runs returns 429 when limit exceeded

Tests:
  - GET returns null config on fresh flow
  - GET includes flow_id and current_count
  - PUT sets rate limit; GET returns it
  - PUT invalid max_runs (0) → 422
  - PUT invalid window_seconds (0) → 422
  - DELETE removes rate limit
  - DELETE when no limit → 404
  - GET/PUT/DELETE 404 for unknown flow
  - Auth required on all endpoints
  - POST /runs succeeds within limit
  - POST /runs returns 429 when limit exceeded
  - POST /runs succeeds again after limit deleted
"""

import uuid

from fastapi.testclient import TestClient

from apps.orchestrator.main import app
from apps.orchestrator.stores import flow_rate_limit_store

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _register(client: TestClient) -> str:
    uid = uuid.uuid4().hex[:8]
    r = client.post(
        "/api/v1/auth/register",
        json={"email": f"rl-{uid}@test.com", "password": "pass1234"},
    )
    assert r.status_code == 201
    return r.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_flow(client: TestClient, token: str) -> str:
    resp = client.post(
        "/api/v1/flows",
        json={"name": "Rate Limit Test Flow", "nodes": [], "edges": []},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _run_flow(client: TestClient, token: str, flow_id: str) -> int:
    resp = client.post(
        f"/api/v1/flows/{flow_id}/runs",
        json={"input": {}},
        headers=_auth(token),
    )
    return resp.status_code


# ---------------------------------------------------------------------------
# Tests — GET /flows/{id}/rate-limit
# ---------------------------------------------------------------------------


class TestFlowRateLimitGet:
    def test_null_by_default(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/rate-limit", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["max_runs"] is None
        assert resp.json()["window_seconds"] is None

    def test_flow_id_in_response(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/rate-limit", headers=_auth(token))
        assert resp.json()["flow_id"] == flow_id

    def test_current_count_zero_by_default(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/rate-limit", headers=_auth(token))
        assert resp.json()["current_count"] == 0

    def test_get_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get("/api/v1/flows/nonexistent/rate-limit", headers=_auth(token))
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_get_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/rate-limit")
        assert resp.status_code == 401
        assert "error" in resp.json()


# ---------------------------------------------------------------------------
# Tests — PUT /flows/{id}/rate-limit
# ---------------------------------------------------------------------------


class TestFlowRateLimitPut:
    def test_put_returns_200(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/rate-limit",
                json={"max_runs": 5, "window_seconds": 60},
                headers=_auth(token),
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["flow_id"] == flow_id

    def test_put_stores_config(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            client.put(
                f"/api/v1/flows/{flow_id}/rate-limit",
                json={"max_runs": 10, "window_seconds": 3600},
                headers=_auth(token),
            )
            resp = client.get(f"/api/v1/flows/{flow_id}/rate-limit", headers=_auth(token))
        assert resp.json()["max_runs"] == 10
        assert resp.json()["window_seconds"] == 3600

    def test_put_max_runs_in_response(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/rate-limit",
                json={"max_runs": 3, "window_seconds": 30},
                headers=_auth(token),
            )
        assert resp.json()["max_runs"] == 3
        assert resp.json()["window_seconds"] == 30

    def test_put_invalid_max_runs_zero_422(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/rate-limit",
                json={"max_runs": 0, "window_seconds": 60},
                headers=_auth(token),
            )
        assert resp.status_code == 422
        assert "error" in resp.json()

    def test_put_invalid_window_zero_422(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/rate-limit",
                json={"max_runs": 5, "window_seconds": 0},
                headers=_auth(token),
            )
        assert resp.status_code == 422
        assert "error" in resp.json()

    def test_put_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.put(
                "/api/v1/flows/nonexistent/rate-limit",
                json={"max_runs": 5, "window_seconds": 60},
                headers=_auth(token),
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_put_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/rate-limit",
                json={"max_runs": 5, "window_seconds": 60},
            )
        assert resp.status_code == 401
        assert "error" in resp.json()


# ---------------------------------------------------------------------------
# Tests — DELETE /flows/{id}/rate-limit
# ---------------------------------------------------------------------------


class TestFlowRateLimitDelete:
    def test_delete_removes_limit(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            client.put(
                f"/api/v1/flows/{flow_id}/rate-limit",
                json={"max_runs": 5, "window_seconds": 60},
                headers=_auth(token),
            )
            resp = client.delete(f"/api/v1/flows/{flow_id}/rate-limit", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["max_runs"] is None

    def test_get_after_delete_shows_null(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            client.put(
                f"/api/v1/flows/{flow_id}/rate-limit",
                json={"max_runs": 5, "window_seconds": 60},
                headers=_auth(token),
            )
            client.delete(f"/api/v1/flows/{flow_id}/rate-limit", headers=_auth(token))
            resp = client.get(f"/api/v1/flows/{flow_id}/rate-limit", headers=_auth(token))
        assert resp.json()["max_runs"] is None

    def test_delete_no_limit_404(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.delete(f"/api/v1/flows/{flow_id}/rate-limit", headers=_auth(token))
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_delete_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.delete("/api/v1/flows/nonexistent/rate-limit", headers=_auth(token))
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_delete_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            client.put(
                f"/api/v1/flows/{flow_id}/rate-limit",
                json={"max_runs": 5, "window_seconds": 60},
                headers=_auth(token),
            )
            resp = client.delete(f"/api/v1/flows/{flow_id}/rate-limit")
        assert resp.status_code == 401
        assert "error" in resp.json()


# ---------------------------------------------------------------------------
# Tests — Enforcement (POST /flows/{id}/runs returns 429)
# ---------------------------------------------------------------------------


class TestFlowRateLimitEnforcement:
    def test_run_succeeds_within_limit(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            # max_runs=2, large window
            flow_rate_limit_store.set(flow_id, 2, 3600)
            status = _run_flow(client, token, flow_id)
        assert status == 202

    def test_run_429_when_limit_exceeded(self):
        """After consuming max_runs, the next attempt returns 429."""
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            # Allow 1 run per large window
            flow_rate_limit_store.set(flow_id, 1, 3600)
            _run_flow(client, token, flow_id)  # consumes the 1 allowed run
            status = _run_flow(client, token, flow_id)
        assert status == 429

    def test_run_succeeds_after_limit_deleted(self):
        """Once the rate limit is removed, runs proceed freely."""
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            flow_rate_limit_store.set(flow_id, 1, 3600)
            _run_flow(client, token, flow_id)  # exhaust limit
            # Remove limit
            client.delete(f"/api/v1/flows/{flow_id}/rate-limit", headers=_auth(token))
            status = _run_flow(client, token, flow_id)
        assert status == 202
