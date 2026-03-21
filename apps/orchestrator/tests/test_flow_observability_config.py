"""
N-185: Flow Observability Configuration — PUT/GET/DELETE /flows/{id}/observability-config

Tests:
  - PUT sets config; returns 200
  - PUT response shape (flow_id, traces_enabled, metrics_enabled, logs_enabled, sample_rate, updated_at)
  - PUT traces_enabled=True stored
  - PUT metrics_enabled=False stored
  - PUT logs_enabled=True stored
  - PUT sample_rate=0.5 stored
  - PUT sample_rate=0.0 allowed
  - PUT sample_rate=1.0 allowed
  - PUT sample_rate > 1.0 → 422
  - PUT sample_rate < 0.0 → 422
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
        json={"email": f"obs-{uid}@test.com", "password": "pass1234"},
    )
    assert r.status_code == 201
    return r.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_flow(client: TestClient, token: str) -> str:
    resp = client.post(
        "/api/v1/flows",
        json={"name": "Observability Test Flow", "nodes": [], "edges": []},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _set_obs(
    client: TestClient,
    token: str,
    flow_id: str,
    traces: bool = True,
    metrics: bool = True,
    logs: bool = True,
    sample_rate: float = 1.0,
) -> dict:
    resp = client.put(
        f"/api/v1/flows/{flow_id}/observability-config",
        json={
            "traces_enabled": traces,
            "metrics_enabled": metrics,
            "logs_enabled": logs,
            "sample_rate": sample_rate,
        },
        headers=_auth(token),
    )
    assert resp.status_code == 200
    return resp.json()


# ---------------------------------------------------------------------------
# Tests — PUT /flows/{id}/observability-config
# ---------------------------------------------------------------------------


class TestFlowObservabilityConfigPut:
    def test_put_returns_200(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/observability-config",
                json={"traces_enabled": True},
                headers=_auth(token),
            )
        assert resp.status_code == 200

    def test_put_response_shape(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/observability-config",
                json={"traces_enabled": True, "metrics_enabled": True, "sample_rate": 0.5},
                headers=_auth(token),
            )
        data = resp.json()
        assert data["flow_id"] == flow_id
        assert "traces_enabled" in data
        assert "metrics_enabled" in data
        assert "logs_enabled" in data
        assert "sample_rate" in data
        assert "updated_at" in data

    def test_put_traces_true(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/observability-config",
                json={"traces_enabled": True},
                headers=_auth(token),
            )
        assert resp.json()["traces_enabled"] is True

    def test_put_metrics_false(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/observability-config",
                json={"metrics_enabled": False},
                headers=_auth(token),
            )
        assert resp.json()["metrics_enabled"] is False

    def test_put_logs_true(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/observability-config",
                json={"logs_enabled": True},
                headers=_auth(token),
            )
        assert resp.json()["logs_enabled"] is True

    def test_put_sample_rate_stored(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/observability-config",
                json={"sample_rate": 0.25},
                headers=_auth(token),
            )
        assert resp.json()["sample_rate"] == 0.25

    def test_put_sample_rate_zero_allowed(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/observability-config",
                json={"sample_rate": 0.0},
                headers=_auth(token),
            )
        assert resp.status_code == 200

    def test_put_sample_rate_one_allowed(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/observability-config",
                json={"sample_rate": 1.0},
                headers=_auth(token),
            )
        assert resp.status_code == 200

    def test_put_sample_rate_too_high_422(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/observability-config",
                json={"sample_rate": 1.1},
                headers=_auth(token),
            )
        assert resp.status_code == 422

    def test_put_sample_rate_negative_422(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/observability-config",
                json={"sample_rate": -0.1},
                headers=_auth(token),
            )
        assert resp.status_code == 422

    def test_put_replaces_existing(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_obs(client, token, flow_id, sample_rate=1.0)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/observability-config",
                json={"sample_rate": 0.1},
                headers=_auth(token),
            )
        assert resp.json()["sample_rate"] == 0.1

    def test_put_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.put(
                "/api/v1/flows/nonexistent/observability-config",
                json={},
                headers=_auth(token),
            )
        assert resp.status_code == 404

    def test_put_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/observability-config",
                json={},
            )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Tests — GET /flows/{id}/observability-config
# ---------------------------------------------------------------------------


class TestFlowObservabilityConfigGet:
    def test_get_returns_config_after_put(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_obs(client, token, flow_id, traces=False)
            resp = client.get(
                f"/api/v1/flows/{flow_id}/observability-config", headers=_auth(token)
            )
        assert resp.status_code == 200
        assert resp.json()["traces_enabled"] is False

    def test_get_404_when_no_config(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(
                f"/api/v1/flows/{flow_id}/observability-config", headers=_auth(token)
            )
        assert resp.status_code == 404

    def test_get_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get(
                "/api/v1/flows/nonexistent/observability-config", headers=_auth(token)
            )
        assert resp.status_code == 404

    def test_get_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_obs(client, token, flow_id)
            resp = client.get(f"/api/v1/flows/{flow_id}/observability-config")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Tests — DELETE /flows/{id}/observability-config
# ---------------------------------------------------------------------------


class TestFlowObservabilityConfigDelete:
    def test_delete_removes_config(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_obs(client, token, flow_id)
            resp = client.delete(
                f"/api/v1/flows/{flow_id}/observability-config", headers=_auth(token)
            )
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True
        assert resp.json()["flow_id"] == flow_id

    def test_get_404_after_delete(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_obs(client, token, flow_id)
            client.delete(
                f"/api/v1/flows/{flow_id}/observability-config", headers=_auth(token)
            )
            resp = client.get(
                f"/api/v1/flows/{flow_id}/observability-config", headers=_auth(token)
            )
        assert resp.status_code == 404

    def test_delete_404_when_no_config(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.delete(
                f"/api/v1/flows/{flow_id}/observability-config", headers=_auth(token)
            )
        assert resp.status_code == 404

    def test_delete_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.delete(
                "/api/v1/flows/nonexistent/observability-config", headers=_auth(token)
            )
        assert resp.status_code == 404

    def test_delete_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_obs(client, token, flow_id)
            resp = client.delete(f"/api/v1/flows/{flow_id}/observability-config")
        assert resp.status_code == 401
