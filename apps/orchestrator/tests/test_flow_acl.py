"""
N-180: Flow Access Control List — POST/GET/DELETE /flows/{id}/acl/{user}

Tests:
  - POST grant returns 200
  - POST response shape (flow_id, user, permissions, granted_at)
  - POST with read permission
  - POST with multiple permissions
  - POST invalid permission → 422
  - POST replaces existing grant
  - POST 404 for unknown flow
  - POST requires auth
  - GET /acl lists all entries
  - GET /acl returns empty list when no grants
  - GET /acl/{user} returns entry after grant
  - GET /acl/{user} 404 when not granted
  - GET /acl/{user} 404 unknown flow
  - GET /acl requires auth
  - GET /acl/{user} requires auth
  - DELETE revokes; returns {deleted: true, flow_id, user}
  - DELETE 404 when not granted
  - DELETE 404 unknown flow
  - DELETE requires auth
  - GET /acl/{user} 404 after DELETE
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
        json={"email": f"acl-{uid}@test.com", "password": "pass1234"},
    )
    assert r.status_code == 201
    return r.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_flow(client: TestClient, token: str) -> str:
    resp = client.post(
        "/api/v1/flows",
        json={"name": "ACL Test Flow", "nodes": [], "edges": []},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _grant(
    client: TestClient, token: str, flow_id: str, user: str, permissions: list
) -> dict:
    resp = client.post(
        f"/api/v1/flows/{flow_id}/acl/{user}",
        json={"permissions": permissions},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    return resp.json()


# ---------------------------------------------------------------------------
# Tests — POST /flows/{id}/acl/{user}
# ---------------------------------------------------------------------------


class TestFlowAclPost:
    def test_grant_returns_200(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/acl/alice@test.com",
                json={"permissions": ["read"]},
                headers=_auth(token),
            )
        assert resp.status_code == 200

    def test_grant_response_shape(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/acl/bob@test.com",
                json={"permissions": ["read", "execute"]},
                headers=_auth(token),
            )
        data = resp.json()
        assert data["flow_id"] == flow_id
        assert data["user"] == "bob@test.com"
        assert "permissions" in data
        assert "granted_at" in data

    def test_grant_read_permission(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/acl/carol@test.com",
                json={"permissions": ["read"]},
                headers=_auth(token),
            )
        assert "read" in resp.json()["permissions"]

    def test_grant_multiple_permissions(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/acl/dan@test.com",
                json={"permissions": ["read", "write", "execute"]},
                headers=_auth(token),
            )
        perms = resp.json()["permissions"]
        assert "read" in perms
        assert "write" in perms
        assert "execute" in perms

    def test_grant_invalid_permission_422(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/acl/eve@test.com",
                json={"permissions": ["superuser"]},
                headers=_auth(token),
            )
        assert resp.status_code == 422

    def test_grant_replaces_existing(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _grant(client, token, flow_id, "frank@test.com", ["read"])
            resp = client.post(
                f"/api/v1/flows/{flow_id}/acl/frank@test.com",
                json={"permissions": ["admin"]},
                headers=_auth(token),
            )
        assert "admin" in resp.json()["permissions"]

    def test_grant_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.post(
                "/api/v1/flows/nonexistent/acl/user@test.com",
                json={"permissions": ["read"]},
                headers=_auth(token),
            )
        assert resp.status_code == 404

    def test_grant_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/acl/user@test.com",
                json={"permissions": ["read"]},
            )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Tests — GET /flows/{id}/acl
# ---------------------------------------------------------------------------


class TestFlowAclList:
    def test_list_returns_entries(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _grant(client, token, flow_id, "a@test.com", ["read"])
            _grant(client, token, flow_id, "b@test.com", ["write"])
            resp = client.get(f"/api/v1/flows/{flow_id}/acl", headers=_auth(token))
        assert resp.status_code == 200
        entries = resp.json()["entries"]
        assert len(entries) >= 2  # Gate 2: non-empty

    def test_list_empty_when_no_grants(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/acl", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["entries"] == []

    def test_list_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get("/api/v1/flows/nonexistent/acl", headers=_auth(token))
        assert resp.status_code == 404

    def test_list_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/acl")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Tests — GET /flows/{id}/acl/{user}
# ---------------------------------------------------------------------------


class TestFlowAclGetUser:
    def test_get_user_returns_entry(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _grant(client, token, flow_id, "grace@test.com", ["execute"])
            resp = client.get(
                f"/api/v1/flows/{flow_id}/acl/grace@test.com", headers=_auth(token)
            )
        assert resp.status_code == 200
        assert "execute" in resp.json()["permissions"]

    def test_get_user_404_when_not_granted(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(
                f"/api/v1/flows/{flow_id}/acl/nobody@test.com", headers=_auth(token)
            )
        assert resp.status_code == 404

    def test_get_user_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get(
                "/api/v1/flows/nonexistent/acl/user@test.com", headers=_auth(token)
            )
        assert resp.status_code == 404

    def test_get_user_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _grant(client, token, flow_id, "henry@test.com", ["read"])
            resp = client.get(f"/api/v1/flows/{flow_id}/acl/henry@test.com")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Tests — DELETE /flows/{id}/acl/{user}
# ---------------------------------------------------------------------------


class TestFlowAclDelete:
    def test_delete_revokes(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _grant(client, token, flow_id, "ivan@test.com", ["write"])
            resp = client.delete(
                f"/api/v1/flows/{flow_id}/acl/ivan@test.com", headers=_auth(token)
            )
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True
        assert resp.json()["flow_id"] == flow_id
        assert resp.json()["user"] == "ivan@test.com"

    def test_get_user_404_after_delete(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _grant(client, token, flow_id, "julia@test.com", ["read"])
            client.delete(f"/api/v1/flows/{flow_id}/acl/julia@test.com", headers=_auth(token))
            resp = client.get(
                f"/api/v1/flows/{flow_id}/acl/julia@test.com", headers=_auth(token)
            )
        assert resp.status_code == 404

    def test_delete_404_when_not_granted(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.delete(
                f"/api/v1/flows/{flow_id}/acl/nobody@test.com", headers=_auth(token)
            )
        assert resp.status_code == 404

    def test_delete_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.delete(
                "/api/v1/flows/nonexistent/acl/user@test.com", headers=_auth(token)
            )
        assert resp.status_code == 404

    def test_delete_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _grant(client, token, flow_id, "kyle@test.com", ["read"])
            resp = client.delete(f"/api/v1/flows/{flow_id}/acl/kyle@test.com")
        assert resp.status_code == 401
