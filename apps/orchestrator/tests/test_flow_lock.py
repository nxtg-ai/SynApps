"""
N-145: Flow Edit Lock — POST/DELETE/GET /api/v1/flows/{flow_id}/lock

Tests:
  - GET /lock returns locked:False on fresh flow
  - POST /lock returns 201 with locked:True
  - POST /lock response shape (locked_by, reason, locked_at)
  - POST /lock twice → 409
  - DELETE /lock returns 200 with locked:False
  - DELETE /lock when not locked → 404
  - GET /lock after POST shows locked:True with correct user
  - GET /lock after DELETE shows locked:False
  - Reason is stored and returned
  - PUT /flows/{id} (update) is blocked (423) when flow is locked
  - PUT /flows/{id} succeeds after unlock
  - 404 for unknown flow on all endpoints
  - Auth required on all endpoints
"""

import uuid

from fastapi.testclient import TestClient

from apps.orchestrator.main import app

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _register(client: TestClient) -> tuple[str, str]:
    uid = uuid.uuid4().hex[:8]
    email = f"lock-{uid}@test.com"
    r = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "pass1234"},
    )
    assert r.status_code == 201
    return r.json()["access_token"], email


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_flow(client: TestClient, token: str) -> str:
    resp = client.post(
        "/api/v1/flows",
        json={"name": "Lock Test Flow", "nodes": [], "edges": []},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


# ---------------------------------------------------------------------------
# Tests — GET /flows/{id}/lock
# ---------------------------------------------------------------------------


class TestFlowLockGet:
    def test_get_unlocked_by_default(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/lock", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["locked"] is False
        assert resp.json()["lock"] is None

    def test_get_flow_id_in_response(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/lock", headers=_auth(token))
        assert resp.json()["flow_id"] == flow_id

    def test_get_404_unknown_flow(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            resp = client.get("/api/v1/flows/nonexistent/lock", headers=_auth(token))
        assert resp.status_code == 404

    def test_get_requires_auth(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/lock")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Tests — POST /flows/{id}/lock
# ---------------------------------------------------------------------------


class TestFlowLockPost:
    def test_lock_returns_201(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(f"/api/v1/flows/{flow_id}/lock", headers=_auth(token))
        assert resp.status_code == 201

    def test_lock_response_shape(self):
        with TestClient(app) as client:
            token, email = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(f"/api/v1/flows/{flow_id}/lock", headers=_auth(token))
        data = resp.json()
        assert data["locked"] is True
        assert data["lock"]["locked_by"] == email
        assert "locked_at" in data["lock"]

    def test_lock_reason_stored(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/lock",
                json={"reason": "Production freeze"},
                headers=_auth(token),
            )
        assert resp.json()["lock"]["reason"] == "Production freeze"

    def test_lock_twice_409(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            flow_id = _create_flow(client, token)
            client.post(f"/api/v1/flows/{flow_id}/lock", headers=_auth(token))
            resp = client.post(f"/api/v1/flows/{flow_id}/lock", headers=_auth(token))
        assert resp.status_code == 409

    def test_lock_404_unknown_flow(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            resp = client.post("/api/v1/flows/nonexistent/lock", headers=_auth(token))
        assert resp.status_code == 404

    def test_lock_requires_auth(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(f"/api/v1/flows/{flow_id}/lock")
        assert resp.status_code == 401

    def test_get_after_lock_shows_locked(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            flow_id = _create_flow(client, token)
            client.post(f"/api/v1/flows/{flow_id}/lock", headers=_auth(token))
            resp = client.get(f"/api/v1/flows/{flow_id}/lock", headers=_auth(token))
        assert resp.json()["locked"] is True


# ---------------------------------------------------------------------------
# Tests — DELETE /flows/{id}/lock
# ---------------------------------------------------------------------------


class TestFlowLockDelete:
    def test_unlock_returns_200(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            flow_id = _create_flow(client, token)
            client.post(f"/api/v1/flows/{flow_id}/lock", headers=_auth(token))
            resp = client.delete(f"/api/v1/flows/{flow_id}/lock", headers=_auth(token))
        assert resp.status_code == 200

    def test_unlock_response_locked_false(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            flow_id = _create_flow(client, token)
            client.post(f"/api/v1/flows/{flow_id}/lock", headers=_auth(token))
            resp = client.delete(f"/api/v1/flows/{flow_id}/lock", headers=_auth(token))
        assert resp.json()["locked"] is False
        assert resp.json()["lock"] is None

    def test_unlock_not_locked_404(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.delete(f"/api/v1/flows/{flow_id}/lock", headers=_auth(token))
        assert resp.status_code == 404

    def test_get_after_unlock_shows_unlocked(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            flow_id = _create_flow(client, token)
            client.post(f"/api/v1/flows/{flow_id}/lock", headers=_auth(token))
            client.delete(f"/api/v1/flows/{flow_id}/lock", headers=_auth(token))
            resp = client.get(f"/api/v1/flows/{flow_id}/lock", headers=_auth(token))
        assert resp.json()["locked"] is False

    def test_unlock_404_unknown_flow(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            resp = client.delete("/api/v1/flows/nonexistent/lock", headers=_auth(token))
        assert resp.status_code == 404

    def test_unlock_requires_auth(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            flow_id = _create_flow(client, token)
            client.post(f"/api/v1/flows/{flow_id}/lock", headers=_auth(token))
            resp = client.delete(f"/api/v1/flows/{flow_id}/lock")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Tests — Lock enforcement on PUT /flows/{id}
# ---------------------------------------------------------------------------


class TestFlowLockEnforcement:
    def test_put_blocked_when_locked(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            flow_id = _create_flow(client, token)
            client.post(f"/api/v1/flows/{flow_id}/lock", headers=_auth(token))
            resp = client.put(
                f"/api/v1/flows/{flow_id}",
                json={"name": "Edited", "nodes": [], "edges": []},
                headers=_auth(token),
            )
        assert resp.status_code == 423

    def test_put_succeeds_after_unlock(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            flow_id = _create_flow(client, token)
            client.post(f"/api/v1/flows/{flow_id}/lock", headers=_auth(token))
            client.delete(f"/api/v1/flows/{flow_id}/lock", headers=_auth(token))
            resp = client.put(
                f"/api/v1/flows/{flow_id}",
                json={"name": "Now Editable", "nodes": [], "edges": []},
                headers=_auth(token),
            )
        assert resp.status_code == 200
