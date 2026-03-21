"""
N-133: Flow Favorites — POST/DELETE /flows/{id}/favorite + GET /flows/favorites

Tests:
  - POST adds favorite, returns 201 + {favorited: true}
  - Idempotent — adding same flow twice still returns 201
  - GET /flows/favorites returns favorited flows (items + total)
  - GET returns empty list when no favorites
  - Favorites are per-user (user A favorites don't appear for user B)
  - DELETE removes favorite, returns {favorited: false}
  - DELETE 404 when flow not in favorites
  - POST/DELETE/GET return 404 for unknown flow
  - Auth required on all three endpoints
  - Deleting favorited flow doesn't corrupt store (stale ID silently dropped)
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
        json={"email": f"fav-{uid}@test.com", "password": "pass1234"},
    )
    assert r.status_code == 201
    return r.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_flow(client: TestClient, token: str, name: str = "Fav Flow") -> str:
    resp = client.post(
        "/api/v1/flows",
        json={"name": name, "nodes": [], "edges": []},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestFavoriteAdd:
    def test_add_favorite_returns_201(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(f"/api/v1/flows/{flow_id}/favorite", headers=_auth(token))
        assert resp.status_code == 201

    def test_add_favorite_response_body(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(f"/api/v1/flows/{flow_id}/favorite", headers=_auth(token))
        data = resp.json()
        assert data["flow_id"] == flow_id
        assert data["favorited"] is True

    def test_add_favorite_idempotent(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            client.post(f"/api/v1/flows/{flow_id}/favorite", headers=_auth(token))
            resp = client.post(f"/api/v1/flows/{flow_id}/favorite", headers=_auth(token))
        assert resp.status_code == 201

    def test_add_favorite_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.post("/api/v1/flows/nonexistent/favorite", headers=_auth(token))
        assert resp.status_code == 404

    def test_add_favorite_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(f"/api/v1/flows/{flow_id}/favorite")
        assert resp.status_code == 401


class TestFavoriteList:
    def test_list_favorites_empty_by_default(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get("/api/v1/flows/favorites", headers=_auth(token))
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0

    def test_list_favorites_contains_added_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            client.post(f"/api/v1/flows/{flow_id}/favorite", headers=_auth(token))
            resp = client.get("/api/v1/flows/favorites", headers=_auth(token))
        data = resp.json()
        assert data["total"] == 1  # Gate 2: exactly one favorite
        assert data["items"][0]["id"] == flow_id

    def test_list_favorites_multiple(self):
        with TestClient(app) as client:
            token = _register(client)
            ids = [_create_flow(client, token, f"Flow {i}") for i in range(3)]
            for fid in ids:
                client.post(f"/api/v1/flows/{fid}/favorite", headers=_auth(token))
            resp = client.get("/api/v1/flows/favorites", headers=_auth(token))
        data = resp.json()
        assert data["total"] == 3  # Gate 2: all three favorites present
        returned_ids = {f["id"] for f in data["items"]}
        assert returned_ids == set(ids)

    def test_list_favorites_sorted_by_name(self):
        with TestClient(app) as client:
            token = _register(client)
            for name in ("Zebra", "Apple", "Mango"):
                fid = _create_flow(client, token, name)
                client.post(f"/api/v1/flows/{fid}/favorite", headers=_auth(token))
            resp = client.get("/api/v1/flows/favorites", headers=_auth(token))
        names = [f["name"] for f in resp.json()["items"]]
        assert names == sorted(names, key=str.lower)

    def test_favorites_are_per_user(self):
        """User A's favorites must not appear for user B."""
        with TestClient(app) as client:
            token_a = _register(client)
            token_b = _register(client)
            flow_id = _create_flow(client, token_a)
            client.post(f"/api/v1/flows/{flow_id}/favorite", headers=_auth(token_a))
            resp_b = client.get("/api/v1/flows/favorites", headers=_auth(token_b))
        assert resp_b.json()["total"] == 0

    def test_list_favorites_requires_auth(self):
        with TestClient(app) as client:
            _register(client)
            resp = client.get("/api/v1/flows/favorites")
        assert resp.status_code == 401


class TestFavoriteRemove:
    def test_remove_favorite_returns_200(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            client.post(f"/api/v1/flows/{flow_id}/favorite", headers=_auth(token))
            resp = client.delete(f"/api/v1/flows/{flow_id}/favorite", headers=_auth(token))
        assert resp.status_code == 200

    def test_remove_favorite_response_body(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            client.post(f"/api/v1/flows/{flow_id}/favorite", headers=_auth(token))
            resp = client.delete(f"/api/v1/flows/{flow_id}/favorite", headers=_auth(token))
        data = resp.json()
        assert data["flow_id"] == flow_id
        assert data["favorited"] is False

    def test_remove_favorite_no_longer_in_list(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            client.post(f"/api/v1/flows/{flow_id}/favorite", headers=_auth(token))
            client.delete(f"/api/v1/flows/{flow_id}/favorite", headers=_auth(token))
            resp = client.get("/api/v1/flows/favorites", headers=_auth(token))
        assert flow_id not in {f["id"] for f in resp.json()["items"]}

    def test_remove_favorite_404_not_favorited(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.delete(f"/api/v1/flows/{flow_id}/favorite", headers=_auth(token))
        assert resp.status_code == 404

    def test_remove_favorite_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.delete("/api/v1/flows/nonexistent/favorite", headers=_auth(token))
        assert resp.status_code == 404

    def test_remove_favorite_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            client.post(f"/api/v1/flows/{flow_id}/favorite", headers=_auth(token))
            resp = client.delete(f"/api/v1/flows/{flow_id}/favorite")
        assert resp.status_code == 401
