"""
N-184: Flow Circuit Breaker — PUT/GET/DELETE /flows/{id}/circuit-breaker

Tests:
  - PUT sets circuit breaker; returns 200
  - PUT response shape (flow_id, enabled, failure_threshold, recovery_timeout_s, state, updated_at)
  - PUT enabled=True stored
  - PUT enabled=False stored
  - PUT failure_threshold stored
  - PUT recovery_timeout_s stored
  - PUT initial state is "closed"
  - PUT failure_threshold=1 (min) allowed
  - PUT failure_threshold=100 (max) allowed
  - PUT failure_threshold=0 → 422
  - PUT failure_threshold=101 → 422
  - PUT recovery_timeout_s=1 (min) allowed
  - PUT recovery_timeout_s=3600 (max) allowed
  - PUT recovery_timeout_s=0 → 422
  - PUT replaces existing config
  - PUT 404 for unknown flow
  - PUT requires auth
  - GET returns config after PUT
  - GET 404 when no config
  - GET 404 for unknown flow
  - GET requires auth
  - DELETE removes config; returns {deleted: true, flow_id}
  - DELETE 404 when no config
  - DELETE 404 unknown flow
  - DELETE requires auth
  - GET 404 after DELETE
"""

import uuid

from fastapi.testclient import TestClient

from apps.orchestrator.main import app

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _register(client: TestClient) -> str:
    uid = uuid.uuid4().hex[:8]
    r = client.post(
        "/api/v1/auth/register",
        json={"email": f"cb-{uid}@test.com", "password": "pass1234"},
    )
    assert r.status_code == 201
    return r.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_flow(client: TestClient, token: str) -> str:
    resp = client.post(
        "/api/v1/flows",
        json={"name": "Circuit Breaker Test Flow", "nodes": [], "edges": []},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _set_cb(
    client: TestClient,
    token: str,
    flow_id: str,
    enabled: bool = True,
    failure_threshold: int = 5,
    recovery_timeout_s: int = 60,
) -> dict:
    resp = client.put(
        f"/api/v1/flows/{flow_id}/circuit-breaker",
        json={
            "enabled": enabled,
            "failure_threshold": failure_threshold,
            "recovery_timeout_s": recovery_timeout_s,
        },
        headers=_auth(token),
    )
    assert resp.status_code == 200
    return resp.json()


# ---------------------------------------------------------------------------
# Tests — PUT /flows/{id}/circuit-breaker
# ---------------------------------------------------------------------------


class TestFlowCircuitBreakerPut:
    def test_put_returns_200(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/circuit-breaker",
                json={"failure_threshold": 5, "recovery_timeout_s": 30},
                headers=_auth(token),
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["flow_id"] == flow_id

    def test_put_response_shape(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/circuit-breaker",
                json={"failure_threshold": 3, "recovery_timeout_s": 60},
                headers=_auth(token),
            )
        data = resp.json()
        assert data["flow_id"] == flow_id
        assert "enabled" in data
        assert "failure_threshold" in data
        assert "recovery_timeout_s" in data
        assert "state" in data
        assert "updated_at" in data

    def test_put_enabled_true(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/circuit-breaker",
                json={"enabled": True, "failure_threshold": 5, "recovery_timeout_s": 30},
                headers=_auth(token),
            )
        assert resp.json()["enabled"] is True

    def test_put_enabled_false(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/circuit-breaker",
                json={"enabled": False, "failure_threshold": 5, "recovery_timeout_s": 30},
                headers=_auth(token),
            )
        assert resp.json()["enabled"] is False

    def test_put_failure_threshold_stored(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/circuit-breaker",
                json={"failure_threshold": 10, "recovery_timeout_s": 30},
                headers=_auth(token),
            )
        assert resp.json()["failure_threshold"] == 10

    def test_put_recovery_timeout_stored(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/circuit-breaker",
                json={"failure_threshold": 5, "recovery_timeout_s": 120},
                headers=_auth(token),
            )
        assert resp.json()["recovery_timeout_s"] == 120

    def test_put_initial_state_closed(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/circuit-breaker",
                json={"failure_threshold": 5, "recovery_timeout_s": 30},
                headers=_auth(token),
            )
        assert resp.json()["state"] == "closed"

    def test_put_min_threshold_allowed(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/circuit-breaker",
                json={"failure_threshold": 1, "recovery_timeout_s": 30},
                headers=_auth(token),
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["flow_id"] == flow_id

    def test_put_max_threshold_allowed(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/circuit-breaker",
                json={"failure_threshold": 100, "recovery_timeout_s": 30},
                headers=_auth(token),
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["flow_id"] == flow_id

    def test_put_threshold_zero_422(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/circuit-breaker",
                json={"failure_threshold": 0, "recovery_timeout_s": 30},
                headers=_auth(token),
            )
        assert resp.status_code == 422
        assert "error" in resp.json()

    def test_put_threshold_too_large_422(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/circuit-breaker",
                json={"failure_threshold": 101, "recovery_timeout_s": 30},
                headers=_auth(token),
            )
        assert resp.status_code == 422
        assert "error" in resp.json()

    def test_put_min_recovery_allowed(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/circuit-breaker",
                json={"failure_threshold": 5, "recovery_timeout_s": 1},
                headers=_auth(token),
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["flow_id"] == flow_id

    def test_put_max_recovery_allowed(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/circuit-breaker",
                json={"failure_threshold": 5, "recovery_timeout_s": 3600},
                headers=_auth(token),
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["flow_id"] == flow_id

    def test_put_recovery_zero_422(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/circuit-breaker",
                json={"failure_threshold": 5, "recovery_timeout_s": 0},
                headers=_auth(token),
            )
        assert resp.status_code == 422
        assert "error" in resp.json()

    def test_put_replaces_existing(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_cb(client, token, flow_id, failure_threshold=3)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/circuit-breaker",
                json={"failure_threshold": 20, "recovery_timeout_s": 90},
                headers=_auth(token),
            )
        assert resp.json()["failure_threshold"] == 20

    def test_put_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.put(
                "/api/v1/flows/nonexistent/circuit-breaker",
                json={"failure_threshold": 5, "recovery_timeout_s": 30},
                headers=_auth(token),
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_put_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/circuit-breaker",
                json={"failure_threshold": 5, "recovery_timeout_s": 30},
            )
        assert resp.status_code == 401
        assert "error" in resp.json()


# ---------------------------------------------------------------------------
# Tests — GET /flows/{id}/circuit-breaker
# ---------------------------------------------------------------------------


class TestFlowCircuitBreakerGet:
    def test_get_returns_config_after_put(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_cb(client, token, flow_id, failure_threshold=7, recovery_timeout_s=45)
            resp = client.get(f"/api/v1/flows/{flow_id}/circuit-breaker", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["failure_threshold"] == 7

    def test_get_404_when_no_config(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/circuit-breaker", headers=_auth(token))
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_get_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get("/api/v1/flows/nonexistent/circuit-breaker", headers=_auth(token))
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_get_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_cb(client, token, flow_id)
            resp = client.get(f"/api/v1/flows/{flow_id}/circuit-breaker")
        assert resp.status_code == 401
        assert "error" in resp.json()


# ---------------------------------------------------------------------------
# Tests — DELETE /flows/{id}/circuit-breaker
# ---------------------------------------------------------------------------


class TestFlowCircuitBreakerDelete:
    def test_delete_removes_config(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_cb(client, token, flow_id)
            resp = client.delete(
                f"/api/v1/flows/{flow_id}/circuit-breaker", headers=_auth(token)
            )
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True
        assert resp.json()["flow_id"] == flow_id

    def test_get_404_after_delete(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_cb(client, token, flow_id)
            client.delete(f"/api/v1/flows/{flow_id}/circuit-breaker", headers=_auth(token))
            resp = client.get(f"/api/v1/flows/{flow_id}/circuit-breaker", headers=_auth(token))
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_delete_404_when_no_config(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.delete(
                f"/api/v1/flows/{flow_id}/circuit-breaker", headers=_auth(token)
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_delete_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.delete(
                "/api/v1/flows/nonexistent/circuit-breaker", headers=_auth(token)
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_delete_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_cb(client, token, flow_id)
            resp = client.delete(f"/api/v1/flows/{flow_id}/circuit-breaker")
        assert resp.status_code == 401
        assert "error" in resp.json()
