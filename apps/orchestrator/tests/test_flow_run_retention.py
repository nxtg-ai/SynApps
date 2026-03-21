"""
N-176: Flow Run History Retention — PUT/GET/DELETE /flows/{id}/run-retention

Tests:
  - PUT sets retention policy; returns 200
  - PUT response shape (flow_id, retain_days, max_runs, updated_at)
  - PUT with retain_days stores correctly
  - PUT with max_runs stores correctly
  - PUT without max_runs defaults None
  - PUT retain_days=1 (min) succeeds
  - PUT retain_days=365 (max) succeeds
  - PUT retain_days=0 → 422
  - PUT retain_days=366 → 422
  - PUT max_runs=0 → 422
  - PUT replaces existing policy
  - PUT 404 for unknown flow
  - PUT requires auth
  - GET returns policy after PUT
  - GET 404 when no policy set
  - GET 404 for unknown flow
  - GET requires auth
  - DELETE removes policy; returns {deleted: true, flow_id}
  - DELETE 404 when no policy
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
        json={"email": f"ret-{uid}@test.com", "password": "pass1234"},
    )
    assert r.status_code == 201
    return r.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_flow(client: TestClient, token: str) -> str:
    resp = client.post(
        "/api/v1/flows",
        json={"name": "Retention Test Flow", "nodes": [], "edges": []},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _set_retention(
    client: TestClient,
    token: str,
    flow_id: str,
    retain_days: int = 30,
    max_runs: int | None = None,
) -> dict:
    payload: dict = {"retain_days": retain_days}
    if max_runs is not None:
        payload["max_runs"] = max_runs
    resp = client.put(
        f"/api/v1/flows/{flow_id}/run-retention",
        json=payload,
        headers=_auth(token),
    )
    assert resp.status_code == 200
    return resp.json()


# ---------------------------------------------------------------------------
# Tests — PUT /flows/{id}/run-retention
# ---------------------------------------------------------------------------


class TestFlowRunRetentionPut:
    def test_put_returns_200(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/run-retention",
                json={"retain_days": 14},
                headers=_auth(token),
            )
        assert resp.status_code == 200

    def test_put_response_shape(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/run-retention",
                json={"retain_days": 7},
                headers=_auth(token),
            )
        data = resp.json()
        assert data["flow_id"] == flow_id
        assert data["retain_days"] == 7
        assert "max_runs" in data
        assert "updated_at" in data

    def test_put_stores_retain_days(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/run-retention",
                json={"retain_days": 90},
                headers=_auth(token),
            )
        assert resp.json()["retain_days"] == 90

    def test_put_stores_max_runs(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/run-retention",
                json={"retain_days": 30, "max_runs": 100},
                headers=_auth(token),
            )
        assert resp.json()["max_runs"] == 100

    def test_put_without_max_runs_defaults_none(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/run-retention",
                json={"retain_days": 30},
                headers=_auth(token),
            )
        assert resp.json()["max_runs"] is None

    def test_put_min_retain_days(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/run-retention",
                json={"retain_days": 1},
                headers=_auth(token),
            )
        assert resp.status_code == 200

    def test_put_max_retain_days(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/run-retention",
                json={"retain_days": 365},
                headers=_auth(token),
            )
        assert resp.status_code == 200

    def test_put_retain_days_zero_422(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/run-retention",
                json={"retain_days": 0},
                headers=_auth(token),
            )
        assert resp.status_code == 422

    def test_put_retain_days_too_large_422(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/run-retention",
                json={"retain_days": 366},
                headers=_auth(token),
            )
        assert resp.status_code == 422

    def test_put_max_runs_zero_422(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/run-retention",
                json={"retain_days": 30, "max_runs": 0},
                headers=_auth(token),
            )
        assert resp.status_code == 422

    def test_put_replaces_existing(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_retention(client, token, flow_id, 7)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/run-retention",
                json={"retain_days": 60},
                headers=_auth(token),
            )
        assert resp.json()["retain_days"] == 60

    def test_put_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.put(
                "/api/v1/flows/nonexistent/run-retention",
                json={"retain_days": 30},
                headers=_auth(token),
            )
        assert resp.status_code == 404

    def test_put_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/run-retention",
                json={"retain_days": 30},
            )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Tests — GET /flows/{id}/run-retention
# ---------------------------------------------------------------------------


class TestFlowRunRetentionGet:
    def test_get_returns_policy_after_put(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_retention(client, token, flow_id, 45)
            resp = client.get(f"/api/v1/flows/{flow_id}/run-retention", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["retain_days"] == 45

    def test_get_404_when_no_policy(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/run-retention", headers=_auth(token))
        assert resp.status_code == 404

    def test_get_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get("/api/v1/flows/nonexistent/run-retention", headers=_auth(token))
        assert resp.status_code == 404

    def test_get_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_retention(client, token, flow_id)
            resp = client.get(f"/api/v1/flows/{flow_id}/run-retention")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Tests — DELETE /flows/{id}/run-retention
# ---------------------------------------------------------------------------


class TestFlowRunRetentionDelete:
    def test_delete_removes_policy(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_retention(client, token, flow_id)
            resp = client.delete(
                f"/api/v1/flows/{flow_id}/run-retention", headers=_auth(token)
            )
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True
        assert resp.json()["flow_id"] == flow_id

    def test_get_404_after_delete(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_retention(client, token, flow_id)
            client.delete(f"/api/v1/flows/{flow_id}/run-retention", headers=_auth(token))
            resp = client.get(f"/api/v1/flows/{flow_id}/run-retention", headers=_auth(token))
        assert resp.status_code == 404

    def test_delete_404_when_no_policy(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.delete(
                f"/api/v1/flows/{flow_id}/run-retention", headers=_auth(token)
            )
        assert resp.status_code == 404

    def test_delete_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.delete(
                "/api/v1/flows/nonexistent/run-retention", headers=_auth(token)
            )
        assert resp.status_code == 404

    def test_delete_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_retention(client, token, flow_id)
            resp = client.delete(f"/api/v1/flows/{flow_id}/run-retention")
        assert resp.status_code == 401
