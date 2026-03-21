"""
N-156: Flow Bookmarks — POST/GET /flows/{id}/bookmarks
                         DELETE /flows/{id}/bookmarks/{bm_id}

Tests:
  - POST creates bookmark; returns 201
  - POST response shape (id, flow_id, user, name, viewport, created_at)
  - POST without viewport defaults to empty dict
  - POST with viewport stores it correctly
  - POST empty name → 422
  - GET returns empty list on fresh flow
  - GET lists bookmarks for current user
  - GET bookmarks are user-scoped (other user sees empty list)
  - GET flow_id and user in response
  - DELETE removes bookmark; returns {deleted: true}
  - DELETE 404 for unknown bookmark
  - GET after DELETE shows empty
  - POST/GET/DELETE 404 for unknown flow
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
    email = f"bm-{uid}@test.com"
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
        json={"name": "Bookmark Test Flow", "nodes": [], "edges": []},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _add_bookmark(
    client: TestClient,
    token: str,
    flow_id: str,
    name: str = "My Bookmark",
    viewport: dict | None = None,
) -> dict:
    body: dict = {"name": name}
    if viewport is not None:
        body["viewport"] = viewport
    resp = client.post(
        f"/api/v1/flows/{flow_id}/bookmarks",
        json=body,
        headers=_auth(token),
    )
    assert resp.status_code == 201
    return resp.json()


# ---------------------------------------------------------------------------
# Tests — POST /flows/{id}/bookmarks
# ---------------------------------------------------------------------------


class TestFlowBookmarkPost:
    def test_post_returns_201(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/bookmarks",
                json={"name": "Start position"},
                headers=_auth(token),
            )
        assert resp.status_code == 201

    def test_post_response_shape(self):
        with TestClient(app) as client:
            token, email = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/bookmarks",
                json={"name": "Shape Test", "viewport": {"x": 10, "y": 20, "zoom": 1.5}},
                headers=_auth(token),
            )
        data = resp.json()
        assert "id" in data
        assert data["flow_id"] == flow_id
        assert data["name"] == "Shape Test"
        assert data["user"] == email
        assert data["viewport"] == {"x": 10, "y": 20, "zoom": 1.5}
        assert "created_at" in data

    def test_post_default_viewport_empty(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/bookmarks",
                json={"name": "No Viewport"},
                headers=_auth(token),
            )
        assert resp.json()["viewport"] == {}

    def test_post_with_viewport(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/bookmarks",
                json={"name": "Zoom In", "viewport": {"x": -100, "y": 50, "zoom": 2.0}},
                headers=_auth(token),
            )
        assert resp.json()["viewport"]["zoom"] == 2.0

    def test_post_empty_name_422(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/bookmarks",
                json={"name": ""},
                headers=_auth(token),
            )
        assert resp.status_code == 422

    def test_post_404_unknown_flow(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            resp = client.post(
                "/api/v1/flows/nonexistent/bookmarks",
                json={"name": "x"},
                headers=_auth(token),
            )
        assert resp.status_code == 404

    def test_post_requires_auth(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/bookmarks",
                json={"name": "no-auth"},
            )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Tests — GET /flows/{id}/bookmarks
# ---------------------------------------------------------------------------


class TestFlowBookmarkGet:
    def test_get_empty_on_fresh_flow(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/bookmarks", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["items"] == []

    def test_get_lists_bookmarks(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            flow_id = _create_flow(client, token)
            _add_bookmark(client, token, flow_id, "BM A")
            _add_bookmark(client, token, flow_id, "BM B")
            resp = client.get(f"/api/v1/flows/{flow_id}/bookmarks", headers=_auth(token))
        assert len(resp.json()["items"]) == 2

    def test_get_user_scoped(self):
        """User B's bookmarks are not visible to user A."""
        with TestClient(app) as client:
            token_a, _ = _register(client)
            token_b, _ = _register(client)
            flow_id = _create_flow(client, token_a)
            # User B adds a bookmark
            _add_bookmark(client, token_b, flow_id, "B's bookmark")
            # User A should see empty
            resp = client.get(f"/api/v1/flows/{flow_id}/bookmarks", headers=_auth(token_a))
        assert resp.json()["items"] == []

    def test_get_flow_id_in_response(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/bookmarks", headers=_auth(token))
        assert resp.json()["flow_id"] == flow_id

    def test_get_user_in_response(self):
        with TestClient(app) as client:
            token, email = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/bookmarks", headers=_auth(token))
        assert resp.json()["user"] == email

    def test_get_404_unknown_flow(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            resp = client.get("/api/v1/flows/nonexistent/bookmarks", headers=_auth(token))
        assert resp.status_code == 404

    def test_get_requires_auth(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/bookmarks")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Tests — DELETE /flows/{id}/bookmarks/{bm_id}
# ---------------------------------------------------------------------------


class TestFlowBookmarkDelete:
    def test_delete_removes_bookmark(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            flow_id = _create_flow(client, token)
            bm = _add_bookmark(client, token, flow_id)
            resp = client.delete(
                f"/api/v1/flows/{flow_id}/bookmarks/{bm['id']}", headers=_auth(token)
            )
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True

    def test_get_after_delete_shows_empty(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            flow_id = _create_flow(client, token)
            bm = _add_bookmark(client, token, flow_id)
            client.delete(
                f"/api/v1/flows/{flow_id}/bookmarks/{bm['id']}", headers=_auth(token)
            )
            resp = client.get(f"/api/v1/flows/{flow_id}/bookmarks", headers=_auth(token))
        assert resp.json()["items"] == []

    def test_delete_404_unknown_bookmark(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.delete(
                f"/api/v1/flows/{flow_id}/bookmarks/nonexistent", headers=_auth(token)
            )
        assert resp.status_code == 404

    def test_delete_404_unknown_flow(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            resp = client.delete(
                "/api/v1/flows/nonexistent/bookmarks/any-id", headers=_auth(token)
            )
        assert resp.status_code == 404

    def test_delete_requires_auth(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            flow_id = _create_flow(client, token)
            bm = _add_bookmark(client, token, flow_id)
            resp = client.delete(f"/api/v1/flows/{flow_id}/bookmarks/{bm['id']}")
        assert resp.status_code == 401

    def test_other_user_cannot_delete(self):
        """User B cannot delete user A's bookmark."""
        with TestClient(app) as client:
            token_a, _ = _register(client)
            token_b, _ = _register(client)
            flow_id = _create_flow(client, token_a)
            bm = _add_bookmark(client, token_a, flow_id)
            resp = client.delete(
                f"/api/v1/flows/{flow_id}/bookmarks/{bm['id']}", headers=_auth(token_b)
            )
        assert resp.status_code == 404
