"""
N-173: Flow Version Lock — POST/GET/DELETE /flows/{id}/version-lock

Tests:
  - POST creates lock; returns 200
  - POST response shape (flow_id, locked_version, reason, locked_by, locked_at)
  - POST with reason succeeds
  - POST without reason uses empty string default
  - POST locked_version too long → 422
  - POST replaces existing lock (re-lock with new version)
  - POST 404 for unknown flow
  - POST requires auth
  - GET returns lock after POST
  - GET locked_by matches authenticated user
  - GET 404 when not locked
  - GET 404 for unknown flow
  - GET requires auth
  - DELETE unlocks; returns {deleted: true, flow_id}
  - DELETE 404 when not locked
  - DELETE 404 for unknown flow
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
        json={"email": f"vlock-{uid}@test.com", "password": "pass1234"},
    )
    assert r.status_code == 201
    return r.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_flow(client: TestClient, token: str) -> str:
    resp = client.post(
        "/api/v1/flows",
        json={"name": "Version Lock Test Flow", "nodes": [], "edges": []},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _lock_version(
    client: TestClient,
    token: str,
    flow_id: str,
    version: str = "1.2.3",
    reason: str = "",
) -> dict:
    resp = client.post(
        f"/api/v1/flows/{flow_id}/version-lock",
        json={"locked_version": version, "reason": reason},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    return resp.json()


# ---------------------------------------------------------------------------
# Tests — POST /flows/{id}/version-lock
# ---------------------------------------------------------------------------


class TestFlowVersionLockPost:
    def test_post_returns_200(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/version-lock",
                json={"locked_version": "2.0.0"},
                headers=_auth(token),
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["flow_id"] == flow_id

    def test_post_response_shape(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/version-lock",
                json={"locked_version": "1.0.0", "reason": "Stable release"},
                headers=_auth(token),
            )
        data = resp.json()
        assert data["flow_id"] == flow_id
        assert data["locked_version"] == "1.0.0"
        assert data["reason"] == "Stable release"
        assert "locked_by" in data
        assert "locked_at" in data

    def test_post_with_reason(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/version-lock",
                json={"locked_version": "3.1.0", "reason": "Production freeze"},
                headers=_auth(token),
            )
        assert resp.json()["reason"] == "Production freeze"

    def test_post_without_reason_defaults_empty(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/version-lock",
                json={"locked_version": "1.0.0"},
                headers=_auth(token),
            )
        assert resp.json()["reason"] == ""

    def test_post_version_too_long_422(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/version-lock",
                json={"locked_version": "v" + "1" * 50},  # 51 chars
                headers=_auth(token),
            )
        assert resp.status_code == 422
        assert "error" in resp.json()

    def test_post_replaces_existing_lock(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _lock_version(client, token, flow_id, "1.0.0")
            resp = client.post(
                f"/api/v1/flows/{flow_id}/version-lock",
                json={"locked_version": "2.5.1"},
                headers=_auth(token),
            )
        assert resp.json()["locked_version"] == "2.5.1"

    def test_post_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.post(
                "/api/v1/flows/nonexistent/version-lock",
                json={"locked_version": "1.0.0"},
                headers=_auth(token),
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_post_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/version-lock",
                json={"locked_version": "1.0.0"},
            )
        assert resp.status_code == 401
        assert "error" in resp.json()


# ---------------------------------------------------------------------------
# Tests — GET /flows/{id}/version-lock
# ---------------------------------------------------------------------------


class TestFlowVersionLockGet:
    def test_get_returns_lock_after_post(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _lock_version(client, token, flow_id, "4.0.0-rc1")
            resp = client.get(f"/api/v1/flows/{flow_id}/version-lock", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["locked_version"] == "4.0.0-rc1"

    def test_get_locked_by_matches_user(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _lock_version(client, token, flow_id)
            resp = client.get(f"/api/v1/flows/{flow_id}/version-lock", headers=_auth(token))
        assert "@" in resp.json()["locked_by"]

    def test_get_404_when_not_locked(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/version-lock", headers=_auth(token))
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_get_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get("/api/v1/flows/nonexistent/version-lock", headers=_auth(token))
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_get_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _lock_version(client, token, flow_id)
            resp = client.get(f"/api/v1/flows/{flow_id}/version-lock")
        assert resp.status_code == 401
        assert "error" in resp.json()


# ---------------------------------------------------------------------------
# Tests — DELETE /flows/{id}/version-lock
# ---------------------------------------------------------------------------


class TestFlowVersionLockDelete:
    def test_delete_unlocks(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _lock_version(client, token, flow_id)
            resp = client.delete(
                f"/api/v1/flows/{flow_id}/version-lock", headers=_auth(token)
            )
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True
        assert resp.json()["flow_id"] == flow_id

    def test_get_404_after_delete(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _lock_version(client, token, flow_id)
            client.delete(f"/api/v1/flows/{flow_id}/version-lock", headers=_auth(token))
            resp = client.get(f"/api/v1/flows/{flow_id}/version-lock", headers=_auth(token))
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_delete_404_when_not_locked(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.delete(
                f"/api/v1/flows/{flow_id}/version-lock", headers=_auth(token)
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_delete_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.delete(
                "/api/v1/flows/nonexistent/version-lock", headers=_auth(token)
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_delete_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _lock_version(client, token, flow_id)
            resp = client.delete(f"/api/v1/flows/{flow_id}/version-lock")
        assert resp.status_code == 401
        assert "error" in resp.json()
