"""
N-144: Flow Watch — POST/DELETE /flows/{id}/watch
                    GET /flows/{id}/watchers
                    GET /flows/watched

Tests:
  - POST /watch returns 201 with watching:True
  - POST /watch twice → 409
  - DELETE /watch returns 200 with watching:False
  - DELETE /watch when not watching → 404
  - GET /watchers returns list with watcher email
  - GET /watchers empty on fresh flow
  - GET /flows/watched returns watched flow IDs
  - GET /flows/watched empty when not watching anything
  - Watch/unwatch are per-user isolated
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
    email = f"watch-{uid}@test.com"
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
        json={"name": "Watch Test Flow", "nodes": [], "edges": []},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


# ---------------------------------------------------------------------------
# Tests — POST/DELETE /flows/{id}/watch
# ---------------------------------------------------------------------------


class TestFlowWatchCrud:
    def test_watch_returns_201(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(f"/api/v1/flows/{flow_id}/watch", headers=_auth(token))
        assert resp.status_code == 201

    def test_watch_response_shape(self):
        with TestClient(app) as client:
            token, email = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(f"/api/v1/flows/{flow_id}/watch", headers=_auth(token))
        data = resp.json()
        assert data["flow_id"] == flow_id
        assert data["watching"] is True
        assert data["watcher"] == email

    def test_watch_twice_409(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            flow_id = _create_flow(client, token)
            client.post(f"/api/v1/flows/{flow_id}/watch", headers=_auth(token))
            resp = client.post(f"/api/v1/flows/{flow_id}/watch", headers=_auth(token))
        assert resp.status_code == 409

    def test_unwatch_returns_200(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            flow_id = _create_flow(client, token)
            client.post(f"/api/v1/flows/{flow_id}/watch", headers=_auth(token))
            resp = client.delete(f"/api/v1/flows/{flow_id}/watch", headers=_auth(token))
        assert resp.status_code == 200

    def test_unwatch_response_watching_false(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            flow_id = _create_flow(client, token)
            client.post(f"/api/v1/flows/{flow_id}/watch", headers=_auth(token))
            resp = client.delete(f"/api/v1/flows/{flow_id}/watch", headers=_auth(token))
        assert resp.json()["watching"] is False

    def test_unwatch_not_watching_404(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.delete(f"/api/v1/flows/{flow_id}/watch", headers=_auth(token))
        assert resp.status_code == 404

    def test_watch_404_unknown_flow(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            resp = client.post("/api/v1/flows/nonexistent/watch", headers=_auth(token))
        assert resp.status_code == 404

    def test_unwatch_404_unknown_flow(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            resp = client.delete("/api/v1/flows/nonexistent/watch", headers=_auth(token))
        assert resp.status_code == 404

    def test_watch_requires_auth(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(f"/api/v1/flows/{flow_id}/watch")
        assert resp.status_code == 401

    def test_unwatch_requires_auth(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.delete(f"/api/v1/flows/{flow_id}/watch")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Tests — GET /flows/{id}/watchers
# ---------------------------------------------------------------------------


class TestFlowWatchers:
    def test_watchers_empty_on_fresh_flow(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/watchers", headers=_auth(token))
        data = resp.json()
        assert data["watchers"] == []
        assert data["total"] == 0

    def test_watchers_contains_watcher_email(self):
        with TestClient(app) as client:
            token, email = _register(client)
            flow_id = _create_flow(client, token)
            client.post(f"/api/v1/flows/{flow_id}/watch", headers=_auth(token))
            resp = client.get(f"/api/v1/flows/{flow_id}/watchers", headers=_auth(token))
        assert email in resp.json()["watchers"]

    def test_watchers_reflects_multiple_users(self):
        with TestClient(app) as client:
            token1, email1 = _register(client)
            token2, email2 = _register(client)
            flow_id = _create_flow(client, token1)
            client.post(f"/api/v1/flows/{flow_id}/watch", headers=_auth(token1))
            client.post(f"/api/v1/flows/{flow_id}/watch", headers=_auth(token2))
            resp = client.get(f"/api/v1/flows/{flow_id}/watchers", headers=_auth(token1))
        watchers = set(resp.json()["watchers"])
        assert email1 in watchers
        assert email2 in watchers
        assert resp.json()["total"] == 2

    def test_unwatch_removes_from_watchers(self):
        with TestClient(app) as client:
            token, email = _register(client)
            flow_id = _create_flow(client, token)
            client.post(f"/api/v1/flows/{flow_id}/watch", headers=_auth(token))
            client.delete(f"/api/v1/flows/{flow_id}/watch", headers=_auth(token))
            resp = client.get(f"/api/v1/flows/{flow_id}/watchers", headers=_auth(token))
        assert email not in resp.json()["watchers"]

    def test_watchers_404_unknown_flow(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            resp = client.get("/api/v1/flows/nonexistent/watchers", headers=_auth(token))
        assert resp.status_code == 404

    def test_watchers_requires_auth(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/watchers")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Tests — GET /flows/watched
# ---------------------------------------------------------------------------


class TestFlowsWatchedList:
    def test_watched_empty_by_default(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            resp = client.get("/api/v1/flows/watched", headers=_auth(token))
        data = resp.json()
        assert data["flow_ids"] == []
        assert data["total"] == 0

    def test_watched_contains_watched_flow(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            flow_id = _create_flow(client, token)
            client.post(f"/api/v1/flows/{flow_id}/watch", headers=_auth(token))
            resp = client.get("/api/v1/flows/watched", headers=_auth(token))
        assert flow_id in resp.json()["flow_ids"]

    def test_watched_per_user_isolation(self):
        with TestClient(app) as client:
            token1, _ = _register(client)
            token2, _ = _register(client)
            flow_id = _create_flow(client, token1)
            client.post(f"/api/v1/flows/{flow_id}/watch", headers=_auth(token1))
            resp = client.get("/api/v1/flows/watched", headers=_auth(token2))
        assert flow_id not in resp.json()["flow_ids"]

    def test_unwatch_removes_from_watched(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            flow_id = _create_flow(client, token)
            client.post(f"/api/v1/flows/{flow_id}/watch", headers=_auth(token))
            client.delete(f"/api/v1/flows/{flow_id}/watch", headers=_auth(token))
            resp = client.get("/api/v1/flows/watched", headers=_auth(token))
        assert flow_id not in resp.json()["flow_ids"]

    def test_watched_requires_auth(self):
        with TestClient(app) as client:
            _register(client)
            resp = client.get("/api/v1/flows/watched")
        assert resp.status_code == 401
