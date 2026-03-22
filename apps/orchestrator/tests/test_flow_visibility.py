"""
N-172: Flow Visibility — PUT/GET/DELETE /flows/{id}/visibility

Tests:
  - PUT sets visibility; returns 200
  - PUT response shape (flow_id, visibility, updated_at, allowed_levels)
  - PUT "private" succeeds
  - PUT "internal" succeeds
  - PUT "public" succeeds
  - PUT invalid level → 422
  - PUT replaces existing visibility
  - PUT 404 for unknown flow
  - PUT requires auth
  - GET returns visibility after PUT
  - GET response includes allowed_levels
  - GET 404 when no visibility set
  - GET 404 for unknown flow
  - GET requires auth
  - DELETE removes visibility; returns {deleted: true, flow_id}
  - DELETE 404 when no visibility set
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
        json={"email": f"vis-{uid}@test.com", "password": "pass1234"},
    )
    assert r.status_code == 201
    return r.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_flow(client: TestClient, token: str) -> str:
    resp = client.post(
        "/api/v1/flows",
        json={"name": "Visibility Test Flow", "nodes": [], "edges": []},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _set_visibility(client: TestClient, token: str, flow_id: str, level: str = "private") -> dict:
    resp = client.put(
        f"/api/v1/flows/{flow_id}/visibility",
        json={"visibility": level},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    return resp.json()


# ---------------------------------------------------------------------------
# Tests — PUT /flows/{id}/visibility
# ---------------------------------------------------------------------------


class TestFlowVisibilityPut:
    def test_put_returns_200(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/visibility",
                json={"visibility": "private"},
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
                f"/api/v1/flows/{flow_id}/visibility",
                json={"visibility": "internal"},
                headers=_auth(token),
            )
        data = resp.json()
        assert data["flow_id"] == flow_id
        assert data["visibility"] == "internal"
        assert "updated_at" in data
        assert "allowed_levels" in data

    def test_put_private(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/visibility",
                json={"visibility": "private"},
                headers=_auth(token),
            )
        assert resp.json()["visibility"] == "private"

    def test_put_internal(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/visibility",
                json={"visibility": "internal"},
                headers=_auth(token),
            )
        assert resp.json()["visibility"] == "internal"

    def test_put_public(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/visibility",
                json={"visibility": "public"},
                headers=_auth(token),
            )
        assert resp.json()["visibility"] == "public"

    def test_put_invalid_level_422(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/visibility",
                json={"visibility": "secret"},
                headers=_auth(token),
            )
        assert resp.status_code == 422
        assert "error" in resp.json()

    def test_put_replaces_existing(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_visibility(client, token, flow_id, "private")
            resp = client.put(
                f"/api/v1/flows/{flow_id}/visibility",
                json={"visibility": "public"},
                headers=_auth(token),
            )
        assert resp.json()["visibility"] == "public"

    def test_put_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.put(
                "/api/v1/flows/nonexistent/visibility",
                json={"visibility": "private"},
                headers=_auth(token),
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_put_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/visibility",
                json={"visibility": "private"},
            )
        assert resp.status_code == 401
        assert "error" in resp.json()


# ---------------------------------------------------------------------------
# Tests — GET /flows/{id}/visibility
# ---------------------------------------------------------------------------


class TestFlowVisibilityGet:
    def test_get_returns_visibility_after_put(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_visibility(client, token, flow_id, "public")
            resp = client.get(f"/api/v1/flows/{flow_id}/visibility", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["visibility"] == "public"

    def test_get_includes_allowed_levels(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_visibility(client, token, flow_id)
            resp = client.get(f"/api/v1/flows/{flow_id}/visibility", headers=_auth(token))
        assert len(resp.json()["allowed_levels"]) == 3

    def test_get_404_when_no_visibility(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/visibility", headers=_auth(token))
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_get_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get("/api/v1/flows/nonexistent/visibility", headers=_auth(token))
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_get_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_visibility(client, token, flow_id)
            resp = client.get(f"/api/v1/flows/{flow_id}/visibility")
        assert resp.status_code == 401
        assert "error" in resp.json()


# ---------------------------------------------------------------------------
# Tests — DELETE /flows/{id}/visibility
# ---------------------------------------------------------------------------


class TestFlowVisibilityDelete:
    def test_delete_removes_visibility(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_visibility(client, token, flow_id)
            resp = client.delete(f"/api/v1/flows/{flow_id}/visibility", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True
        assert resp.json()["flow_id"] == flow_id

    def test_get_404_after_delete(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_visibility(client, token, flow_id)
            client.delete(f"/api/v1/flows/{flow_id}/visibility", headers=_auth(token))
            resp = client.get(f"/api/v1/flows/{flow_id}/visibility", headers=_auth(token))
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_delete_404_when_no_visibility(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.delete(f"/api/v1/flows/{flow_id}/visibility", headers=_auth(token))
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_delete_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_visibility(client, token, flow_id)
            resp = client.delete(f"/api/v1/flows/{flow_id}/visibility")
        assert resp.status_code == 401
        assert "error" in resp.json()
