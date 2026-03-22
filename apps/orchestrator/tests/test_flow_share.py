"""
N-139: Flow Sharing Links
  POST /api/v1/flows/{id}/share       — generate read-only token
  GET  /api/v1/flows/shared/{token}   — fetch flow (no auth required)
  GET  /api/v1/flows/{id}/shares      — list active tokens
  DELETE /api/v1/flows/{id}/share/{token} — revoke token

Tests:
  - POST returns 201 with token, flow_id, expires_at, ttl
  - GET /flows/shared/{token} returns flow + share metadata (no auth)
  - GET with expired/unknown token → 404
  - GET /flows/{id}/shares lists active tokens
  - DELETE revokes token; subsequent GET returns 404
  - DELETE unknown token → 404
  - Custom TTL respected
  - TTL below minimum (60s) → 422
  - TTL above maximum (7d) → 422
  - POST/GET shares/DELETE return 404 for unknown flow
  - POST share and DELETE share require auth; GET shared/{token} does not
"""

import time
import uuid

from fastapi.testclient import TestClient

from apps.orchestrator.main import app
from apps.orchestrator.stores import FlowShareStore, flow_share_store

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _register(client: TestClient) -> str:
    uid = uuid.uuid4().hex[:8]
    r = client.post(
        "/api/v1/auth/register",
        json={"email": f"share-{uid}@test.com", "password": "pass1234"},
    )
    assert r.status_code == 201
    return r.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_flow(client: TestClient, token: str) -> str:
    resp = client.post(
        "/api/v1/flows",
        json={"name": "Share Test Flow", "nodes": [], "edges": []},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


# ---------------------------------------------------------------------------
# Tests — POST /flows/{id}/share
# ---------------------------------------------------------------------------


class TestCreateShareLink:
    def test_create_returns_201(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(f"/api/v1/flows/{flow_id}/share", headers=_auth(token))
        assert resp.status_code == 201
        data = resp.json()
        assert data["flow_id"] == flow_id

    def test_create_response_shape(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(f"/api/v1/flows/{flow_id}/share", headers=_auth(token))
        data = resp.json()
        assert "token" in data
        assert data["flow_id"] == flow_id
        assert "expires_at" in data
        assert data["ttl"] == FlowShareStore.DEFAULT_TTL

    def test_create_custom_ttl(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/share",
                json={"ttl": 3600},
                headers=_auth(token),
            )
        assert resp.status_code == 201
        assert resp.json()["ttl"] == 3600

    def test_create_ttl_below_min_422(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/share",
                json={"ttl": 59},
                headers=_auth(token),
            )
        assert resp.status_code == 422
        assert "error" in resp.json()

    def test_create_ttl_above_max_422(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/share",
                json={"ttl": 604_801},
                headers=_auth(token),
            )
        assert resp.status_code == 422
        assert "error" in resp.json()

    def test_create_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.post("/api/v1/flows/nonexistent/share", headers=_auth(token))
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_create_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(f"/api/v1/flows/{flow_id}/share")
        assert resp.status_code == 401
        assert "error" in resp.json()


# ---------------------------------------------------------------------------
# Tests — GET /flows/shared/{token}
# ---------------------------------------------------------------------------


class TestGetSharedFlow:
    def test_get_shared_no_auth_required(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            share_resp = client.post(
                f"/api/v1/flows/{flow_id}/share", headers=_auth(token)
            )
            share_token = share_resp.json()["token"]
            resp = client.get(f"/api/v1/flows/shared/{share_token}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["flow"]["id"] == flow_id

    def test_get_shared_response_shape(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            share_resp = client.post(
                f"/api/v1/flows/{flow_id}/share", headers=_auth(token)
            )
            share_token = share_resp.json()["token"]
            resp = client.get(f"/api/v1/flows/shared/{share_token}")
        data = resp.json()
        assert "flow" in data
        assert data["flow"]["id"] == flow_id
        assert data["share"]["token"] == share_token

    def test_get_shared_unknown_token_404(self):
        with TestClient(app) as client:
            _register(client)
            resp = client.get("/api/v1/flows/shared/doesnotexist")
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_get_shared_expired_token_404(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            # Create token then manually expire it via store
            share_resp = client.post(
                f"/api/v1/flows/{flow_id}/share",
                json={"ttl": 60},
                headers=_auth(token),
            )
            share_token = share_resp.json()["token"]
            # Monkey-patch expires_at to the past
            with flow_share_store._lock:
                flow_share_store._tokens[share_token]["expires_at"] = time.time() - 1
            resp = client.get(f"/api/v1/flows/shared/{share_token}")
        assert resp.status_code == 404
        assert "error" in resp.json()


# ---------------------------------------------------------------------------
# Tests — GET /flows/{id}/shares
# ---------------------------------------------------------------------------


class TestListShareLinks:
    def test_list_returns_active_tokens(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            client.post(f"/api/v1/flows/{flow_id}/share", headers=_auth(token))
            client.post(f"/api/v1/flows/{flow_id}/share", headers=_auth(token))
            resp = client.get(f"/api/v1/flows/{flow_id}/shares", headers=_auth(token))
        data = resp.json()
        assert data["flow_id"] == flow_id
        assert len(data["tokens"]) == 2

    def test_list_empty_when_none_created(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/shares", headers=_auth(token))
        assert resp.json()["tokens"] == []

    def test_list_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get("/api/v1/flows/nonexistent/shares", headers=_auth(token))
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_list_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/shares")
        assert resp.status_code == 401
        assert "error" in resp.json()


# ---------------------------------------------------------------------------
# Tests — DELETE /flows/{id}/share/{token}
# ---------------------------------------------------------------------------


class TestRevokeShareLink:
    def test_revoke_returns_200(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            share_resp = client.post(
                f"/api/v1/flows/{flow_id}/share", headers=_auth(token)
            )
            share_token = share_resp.json()["token"]
            resp = client.delete(
                f"/api/v1/flows/{flow_id}/share/{share_token}", headers=_auth(token)
            )
        assert resp.status_code == 200
        assert resp.json()["revoked"] is True

    def test_revoke_makes_token_invalid(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            share_resp = client.post(
                f"/api/v1/flows/{flow_id}/share", headers=_auth(token)
            )
            share_token = share_resp.json()["token"]
            client.delete(
                f"/api/v1/flows/{flow_id}/share/{share_token}", headers=_auth(token)
            )
            resp = client.get(f"/api/v1/flows/shared/{share_token}")
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_revoke_unknown_token_404(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.delete(
                f"/api/v1/flows/{flow_id}/share/ghost", headers=_auth(token)
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_revoke_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.delete(
                "/api/v1/flows/nonexistent/share/tok", headers=_auth(token)
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_revoke_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            share_resp = client.post(
                f"/api/v1/flows/{flow_id}/share", headers=_auth(token)
            )
            share_token = share_resp.json()["token"]
            resp = client.delete(f"/api/v1/flows/{flow_id}/share/{share_token}")
        assert resp.status_code == 401
        assert "error" in resp.json()
