"""
N-165: Flow Timeout Config — PUT/GET/DELETE /flows/{id}/timeout

Tests:
  - PUT creates timeout config; returns 200
  - PUT response shape (flow_id, timeout_seconds, updated_at)
  - PUT lower bound (1 second) succeeds
  - PUT upper bound (3600 seconds) succeeds
  - PUT below lower bound → 422
  - PUT above upper bound → 422
  - PUT replaces existing timeout
  - PUT 404 for unknown flow
  - PUT requires auth
  - GET returns timeout after PUT
  - GET 404 when no timeout set
  - GET 404 for unknown flow
  - GET requires auth
  - DELETE removes timeout; returns {deleted: true, flow_id}
  - DELETE 404 when no timeout set
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
        json={"email": f"timeout-{uid}@test.com", "password": "pass1234"},
    )
    assert r.status_code == 201
    return r.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_flow(client: TestClient, token: str) -> str:
    resp = client.post(
        "/api/v1/flows",
        json={"name": "Timeout Test Flow", "nodes": [], "edges": []},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _set_timeout(client: TestClient, token: str, flow_id: str, seconds: int = 300) -> dict:
    resp = client.put(
        f"/api/v1/flows/{flow_id}/timeout",
        json={"timeout_seconds": seconds},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    return resp.json()


# ---------------------------------------------------------------------------
# Tests — PUT /flows/{id}/timeout
# ---------------------------------------------------------------------------


class TestFlowTimeoutPut:
    def test_put_returns_200(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/timeout",
                json={"timeout_seconds": 60},
                headers=_auth(token),
            )
        assert resp.status_code == 200

    def test_put_response_shape(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/timeout",
                json={"timeout_seconds": 120},
                headers=_auth(token),
            )
        data = resp.json()
        assert data["flow_id"] == flow_id
        assert data["timeout_seconds"] == 120
        assert "updated_at" in data

    def test_put_lower_bound(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/timeout",
                json={"timeout_seconds": 1},
                headers=_auth(token),
            )
        assert resp.status_code == 200
        assert resp.json()["timeout_seconds"] == 1

    def test_put_upper_bound(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/timeout",
                json={"timeout_seconds": 3600},
                headers=_auth(token),
            )
        assert resp.status_code == 200
        assert resp.json()["timeout_seconds"] == 3600

    def test_put_below_lower_bound_422(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/timeout",
                json={"timeout_seconds": 0},
                headers=_auth(token),
            )
        assert resp.status_code == 422

    def test_put_above_upper_bound_422(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/timeout",
                json={"timeout_seconds": 3601},
                headers=_auth(token),
            )
        assert resp.status_code == 422

    def test_put_replaces_existing(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_timeout(client, token, flow_id, 60)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/timeout",
                json={"timeout_seconds": 900},
                headers=_auth(token),
            )
        assert resp.json()["timeout_seconds"] == 900

    def test_put_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.put(
                "/api/v1/flows/nonexistent/timeout",
                json={"timeout_seconds": 60},
                headers=_auth(token),
            )
        assert resp.status_code == 404

    def test_put_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/timeout",
                json={"timeout_seconds": 60},
            )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Tests — GET /flows/{id}/timeout
# ---------------------------------------------------------------------------


class TestFlowTimeoutGet:
    def test_get_returns_timeout_after_put(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_timeout(client, token, flow_id, 180)
            resp = client.get(f"/api/v1/flows/{flow_id}/timeout", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["timeout_seconds"] == 180

    def test_get_404_when_no_timeout(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/timeout", headers=_auth(token))
        assert resp.status_code == 404

    def test_get_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get("/api/v1/flows/nonexistent/timeout", headers=_auth(token))
        assert resp.status_code == 404

    def test_get_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_timeout(client, token, flow_id)
            resp = client.get(f"/api/v1/flows/{flow_id}/timeout")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Tests — DELETE /flows/{id}/timeout
# ---------------------------------------------------------------------------


class TestFlowTimeoutDelete:
    def test_delete_removes_timeout(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_timeout(client, token, flow_id)
            resp = client.delete(f"/api/v1/flows/{flow_id}/timeout", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True
        assert resp.json()["flow_id"] == flow_id

    def test_get_404_after_delete(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_timeout(client, token, flow_id)
            client.delete(f"/api/v1/flows/{flow_id}/timeout", headers=_auth(token))
            resp = client.get(f"/api/v1/flows/{flow_id}/timeout", headers=_auth(token))
        assert resp.status_code == 404

    def test_delete_404_when_no_timeout(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.delete(f"/api/v1/flows/{flow_id}/timeout", headers=_auth(token))
        assert resp.status_code == 404

    def test_delete_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.delete("/api/v1/flows/nonexistent/timeout", headers=_auth(token))
        assert resp.status_code == 404

    def test_delete_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_timeout(client, token, flow_id)
            resp = client.delete(f"/api/v1/flows/{flow_id}/timeout")
        assert resp.status_code == 401
