"""
N-199: Flow Data Retention Policy — PUT/GET/DELETE /flows/{id}/data-retention

Tests:
  - PUT sets retention policy; returns 200
  - PUT response shape (flow_id, retention_days, delete_on_expiry, anonymize_on_expiry, enabled, updated_at)
  - PUT retention_days stored
  - PUT delete_on_expiry=True stored
  - PUT anonymize_on_expiry=True stored
  - PUT enabled=False stored
  - PUT retention_days=1 (min) stored
  - PUT retention_days=3650 (max) stored
  - PUT retention_days=0 → 422
  - PUT retention_days=3651 → 422
  - PUT replaces existing policy
  - PUT 404 for unknown flow
  - PUT requires auth
  - GET returns policy after PUT
  - GET 404 when no policy
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
        json={"email": f"dataret-{uid}@test.com", "password": "pass1234"},
    )
    assert r.status_code == 201
    return r.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_flow(client: TestClient, token: str) -> str:
    resp = client.post(
        "/api/v1/flows",
        json={"name": "Data Retention Test Flow", "nodes": [], "edges": []},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _set_retention(
    client: TestClient,
    token: str,
    flow_id: str,
    retention_days: int = 90,
    delete_on_expiry: bool = False,
    anonymize_on_expiry: bool = False,
    enabled: bool = True,
) -> dict:
    resp = client.put(
        f"/api/v1/flows/{flow_id}/data-retention",
        json={
            "retention_days": retention_days,
            "delete_on_expiry": delete_on_expiry,
            "anonymize_on_expiry": anonymize_on_expiry,
            "enabled": enabled,
        },
        headers=_auth(token),
    )
    assert resp.status_code == 200
    return resp.json()


# ---------------------------------------------------------------------------
# Tests — PUT /flows/{id}/data-retention
# ---------------------------------------------------------------------------


class TestFlowDataRetentionPut:
    def test_put_returns_200(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/data-retention",
                json={"retention_days": 30},
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
                f"/api/v1/flows/{flow_id}/data-retention",
                json={"retention_days": 60},
                headers=_auth(token),
            )
        data = resp.json()
        assert data["flow_id"] == flow_id
        assert "retention_days" in data
        assert "delete_on_expiry" in data
        assert "anonymize_on_expiry" in data
        assert "enabled" in data
        assert "updated_at" in data

    def test_put_retention_days_stored(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/data-retention",
                json={"retention_days": 180},
                headers=_auth(token),
            )
        assert resp.json()["retention_days"] == 180

    def test_put_delete_on_expiry_true(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/data-retention",
                json={"retention_days": 30, "delete_on_expiry": True},
                headers=_auth(token),
            )
        assert resp.json()["delete_on_expiry"] is True

    def test_put_anonymize_on_expiry_true(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/data-retention",
                json={"retention_days": 30, "anonymize_on_expiry": True},
                headers=_auth(token),
            )
        assert resp.json()["anonymize_on_expiry"] is True

    def test_put_enabled_false(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/data-retention",
                json={"retention_days": 30, "enabled": False},
                headers=_auth(token),
            )
        assert resp.json()["enabled"] is False

    def test_put_retention_days_min(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/data-retention",
                json={"retention_days": 1},
                headers=_auth(token),
            )
        assert resp.status_code == 200
        assert resp.json()["retention_days"] == 1

    def test_put_retention_days_max(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/data-retention",
                json={"retention_days": 3650},
                headers=_auth(token),
            )
        assert resp.status_code == 200
        assert resp.json()["retention_days"] == 3650

    def test_put_retention_days_zero_422(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/data-retention",
                json={"retention_days": 0},
                headers=_auth(token),
            )
        assert resp.status_code == 422
        assert "error" in resp.json()

    def test_put_retention_days_over_max_422(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/data-retention",
                json={"retention_days": 3651},
                headers=_auth(token),
            )
        assert resp.status_code == 422
        assert "error" in resp.json()

    def test_put_replaces_existing(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_retention(client, token, flow_id, retention_days=30)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/data-retention",
                json={"retention_days": 365, "delete_on_expiry": True},
                headers=_auth(token),
            )
        assert resp.json()["retention_days"] == 365
        assert resp.json()["delete_on_expiry"] is True

    def test_put_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.put(
                "/api/v1/flows/nonexistent/data-retention",
                json={"retention_days": 30},
                headers=_auth(token),
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_put_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/data-retention",
                json={"retention_days": 30},
            )
        assert resp.status_code == 401
        assert "error" in resp.json()


# ---------------------------------------------------------------------------
# Tests — GET /flows/{id}/data-retention
# ---------------------------------------------------------------------------


class TestFlowDataRetentionGet:
    def test_get_returns_policy_after_put(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_retention(client, token, flow_id, retention_days=45)
            resp = client.get(f"/api/v1/flows/{flow_id}/data-retention", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["retention_days"] == 45

    def test_get_404_when_no_policy(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/data-retention", headers=_auth(token))
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_get_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get("/api/v1/flows/nonexistent/data-retention", headers=_auth(token))
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_get_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_retention(client, token, flow_id)
            resp = client.get(f"/api/v1/flows/{flow_id}/data-retention")
        assert resp.status_code == 401
        assert "error" in resp.json()


# ---------------------------------------------------------------------------
# Tests — DELETE /flows/{id}/data-retention
# ---------------------------------------------------------------------------


class TestFlowDataRetentionDelete:
    def test_delete_removes_policy(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_retention(client, token, flow_id)
            resp = client.delete(
                f"/api/v1/flows/{flow_id}/data-retention", headers=_auth(token)
            )
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True
        assert resp.json()["flow_id"] == flow_id

    def test_get_404_after_delete(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_retention(client, token, flow_id)
            client.delete(f"/api/v1/flows/{flow_id}/data-retention", headers=_auth(token))
            resp = client.get(f"/api/v1/flows/{flow_id}/data-retention", headers=_auth(token))
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_delete_404_when_no_policy(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.delete(
                f"/api/v1/flows/{flow_id}/data-retention", headers=_auth(token)
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_delete_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.delete(
                "/api/v1/flows/nonexistent/data-retention", headers=_auth(token)
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_delete_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_retention(client, token, flow_id)
            resp = client.delete(f"/api/v1/flows/{flow_id}/data-retention")
        assert resp.status_code == 401
        assert "error" in resp.json()
