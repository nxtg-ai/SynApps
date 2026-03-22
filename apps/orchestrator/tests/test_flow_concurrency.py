"""
N-167: Flow Concurrency Limit — PUT/GET/DELETE /flows/{id}/concurrency

Tests:
  - PUT creates concurrency limit; returns 200
  - PUT response shape (flow_id, max_concurrent, updated_at)
  - PUT lower bound (1) succeeds
  - PUT upper bound (100) succeeds
  - PUT below lower bound → 422
  - PUT above upper bound → 422
  - PUT replaces existing limit
  - PUT 404 for unknown flow
  - PUT requires auth
  - GET returns limit after PUT
  - GET 404 when no limit set
  - GET 404 for unknown flow
  - GET requires auth
  - DELETE removes limit; returns {deleted: true, flow_id}
  - DELETE 404 when no limit set
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
        json={"email": f"concur-{uid}@test.com", "password": "pass1234"},
    )
    assert r.status_code == 201
    return r.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_flow(client: TestClient, token: str) -> str:
    resp = client.post(
        "/api/v1/flows",
        json={"name": "Concurrency Test Flow", "nodes": [], "edges": []},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _set_concurrency(client: TestClient, token: str, flow_id: str, limit: int = 5) -> dict:
    resp = client.put(
        f"/api/v1/flows/{flow_id}/concurrency",
        json={"max_concurrent": limit},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    return resp.json()


# ---------------------------------------------------------------------------
# Tests — PUT /flows/{id}/concurrency
# ---------------------------------------------------------------------------


class TestFlowConcurrencyPut:
    def test_put_returns_200(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/concurrency",
                json={"max_concurrent": 3},
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
                f"/api/v1/flows/{flow_id}/concurrency",
                json={"max_concurrent": 10},
                headers=_auth(token),
            )
        data = resp.json()
        assert data["flow_id"] == flow_id
        assert data["max_concurrent"] == 10
        assert "updated_at" in data

    def test_put_lower_bound(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/concurrency",
                json={"max_concurrent": 1},
                headers=_auth(token),
            )
        assert resp.status_code == 200
        assert resp.json()["max_concurrent"] == 1

    def test_put_upper_bound(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/concurrency",
                json={"max_concurrent": 100},
                headers=_auth(token),
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["flow_id"] == flow_id

    def test_put_below_lower_bound_422(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/concurrency",
                json={"max_concurrent": 0},
                headers=_auth(token),
            )
        assert resp.status_code == 422
        assert "error" in resp.json()

    def test_put_above_upper_bound_422(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/concurrency",
                json={"max_concurrent": 101},
                headers=_auth(token),
            )
        assert resp.status_code == 422
        assert "error" in resp.json()

    def test_put_replaces_existing(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_concurrency(client, token, flow_id, 5)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/concurrency",
                json={"max_concurrent": 20},
                headers=_auth(token),
            )
        assert resp.json()["max_concurrent"] == 20

    def test_put_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.put(
                "/api/v1/flows/nonexistent/concurrency",
                json={"max_concurrent": 5},
                headers=_auth(token),
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_put_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/concurrency",
                json={"max_concurrent": 5},
            )
        assert resp.status_code == 401
        assert "error" in resp.json()


# ---------------------------------------------------------------------------
# Tests — GET /flows/{id}/concurrency
# ---------------------------------------------------------------------------


class TestFlowConcurrencyGet:
    def test_get_returns_limit_after_put(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_concurrency(client, token, flow_id, 8)
            resp = client.get(f"/api/v1/flows/{flow_id}/concurrency", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["max_concurrent"] == 8

    def test_get_404_when_no_limit(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/concurrency", headers=_auth(token))
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_get_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get("/api/v1/flows/nonexistent/concurrency", headers=_auth(token))
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_get_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_concurrency(client, token, flow_id)
            resp = client.get(f"/api/v1/flows/{flow_id}/concurrency")
        assert resp.status_code == 401
        assert "error" in resp.json()


# ---------------------------------------------------------------------------
# Tests — DELETE /flows/{id}/concurrency
# ---------------------------------------------------------------------------


class TestFlowConcurrencyDelete:
    def test_delete_removes_limit(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_concurrency(client, token, flow_id)
            resp = client.delete(f"/api/v1/flows/{flow_id}/concurrency", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True
        assert resp.json()["flow_id"] == flow_id

    def test_get_404_after_delete(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_concurrency(client, token, flow_id)
            client.delete(f"/api/v1/flows/{flow_id}/concurrency", headers=_auth(token))
            resp = client.get(f"/api/v1/flows/{flow_id}/concurrency", headers=_auth(token))
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_delete_404_when_no_limit(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.delete(f"/api/v1/flows/{flow_id}/concurrency", headers=_auth(token))
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_delete_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.delete("/api/v1/flows/nonexistent/concurrency", headers=_auth(token))
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_delete_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_concurrency(client, token, flow_id)
            resp = client.delete(f"/api/v1/flows/{flow_id}/concurrency")
        assert resp.status_code == 401
        assert "error" in resp.json()
