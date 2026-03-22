"""
N-196: Flow Collaborator Roles — PUT/GET/DELETE /flows/{id}/collaborator-roles/{user_id}

Tests:
  - PUT assigns role; returns 200
  - PUT response shape (flow_id, user_id, role, updated_at)
  - PUT role viewer stored
  - PUT role editor stored
  - PUT role admin stored
  - PUT invalid role → 422
  - PUT replaces existing role
  - PUT 404 for unknown flow
  - PUT requires auth
  - GET list returns collaborators (Gate 2)
  - GET list empty when none
  - GET list 404 unknown flow
  - GET list requires auth
  - GET single returns role
  - GET single 404 unknown user
  - GET single 404 unknown flow
  - GET single requires auth
  - DELETE removes role; returns {deleted: true, user_id, flow_id}
  - DELETE 404 when not found
  - DELETE 404 unknown flow
  - DELETE requires auth
  - GET single 404 after DELETE
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
        json={"email": f"colrole-{uid}@test.com", "password": "pass1234"},
    )
    assert r.status_code == 201
    return r.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_flow(client: TestClient, token: str) -> str:
    resp = client.post(
        "/api/v1/flows",
        json={"name": "Collaborator Role Test Flow", "nodes": [], "edges": []},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _set_role(
    client: TestClient,
    token: str,
    flow_id: str,
    user_id: str = "user-abc",
    role: str = "viewer",
) -> dict:
    resp = client.put(
        f"/api/v1/flows/{flow_id}/collaborator-roles/{user_id}",
        json={"role": role},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    return resp.json()


# ---------------------------------------------------------------------------
# Tests — PUT /flows/{id}/collaborator-roles/{user_id}
# ---------------------------------------------------------------------------


class TestFlowCollaboratorRolePut:
    def test_put_returns_200(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/collaborator-roles/user-001",
                json={"role": "viewer"},
                headers=_auth(token),
            )
        assert resp.status_code == 200

    def test_put_response_shape(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/collaborator-roles/user-002",
                json={"role": "editor"},
                headers=_auth(token),
            )
        data = resp.json()
        assert data["flow_id"] == flow_id
        assert data["user_id"] == "user-002"
        assert "role" in data
        assert "updated_at" in data

    def test_put_role_viewer(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/collaborator-roles/user-v",
                json={"role": "viewer"},
                headers=_auth(token),
            )
        assert resp.json()["role"] == "viewer"

    def test_put_role_editor(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/collaborator-roles/user-e",
                json={"role": "editor"},
                headers=_auth(token),
            )
        assert resp.json()["role"] == "editor"

    def test_put_role_admin(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/collaborator-roles/user-a",
                json={"role": "admin"},
                headers=_auth(token),
            )
        assert resp.json()["role"] == "admin"

    def test_put_invalid_role_422(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/collaborator-roles/user-x",
                json={"role": "superadmin"},
                headers=_auth(token),
            )
        assert resp.status_code == 422

    def test_put_replaces_existing_role(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_role(client, token, flow_id, user_id="user-r", role="viewer")
            resp = client.put(
                f"/api/v1/flows/{flow_id}/collaborator-roles/user-r",
                json={"role": "admin"},
                headers=_auth(token),
            )
        assert resp.json()["role"] == "admin"

    def test_put_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.put(
                "/api/v1/flows/nonexistent/collaborator-roles/user-001",
                json={"role": "viewer"},
                headers=_auth(token),
            )
        assert resp.status_code == 404

    def test_put_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/collaborator-roles/user-001",
                json={"role": "viewer"},
            )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Tests — GET /flows/{id}/collaborator-roles
# ---------------------------------------------------------------------------


class TestFlowCollaboratorRoleList:
    def test_list_returns_collaborators(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_role(client, token, flow_id, user_id="user-1", role="viewer")
            _set_role(client, token, flow_id, user_id="user-2", role="editor")
            resp = client.get(
                f"/api/v1/flows/{flow_id}/collaborator-roles", headers=_auth(token)
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["collaborators"]) >= 1  # Gate 2

    def test_list_empty_when_none(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(
                f"/api/v1/flows/{flow_id}/collaborator-roles", headers=_auth(token)
            )
        assert resp.status_code == 200
        assert resp.json()["collaborators"] == []

    def test_list_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get(
                "/api/v1/flows/nonexistent/collaborator-roles", headers=_auth(token)
            )
        assert resp.status_code == 404

    def test_list_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/collaborator-roles")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Tests — GET /flows/{id}/collaborator-roles/{user_id}
# ---------------------------------------------------------------------------


class TestFlowCollaboratorRoleGet:
    def test_get_returns_role(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_role(client, token, flow_id, user_id="user-get", role="editor")
            resp = client.get(
                f"/api/v1/flows/{flow_id}/collaborator-roles/user-get",
                headers=_auth(token),
            )
        assert resp.status_code == 200
        assert resp.json()["role"] == "editor"

    def test_get_404_unknown_user(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(
                f"/api/v1/flows/{flow_id}/collaborator-roles/no-such-user",
                headers=_auth(token),
            )
        assert resp.status_code == 404

    def test_get_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get(
                "/api/v1/flows/nonexistent/collaborator-roles/any-user",
                headers=_auth(token),
            )
        assert resp.status_code == 404

    def test_get_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_role(client, token, flow_id, user_id="user-auth")
            resp = client.get(f"/api/v1/flows/{flow_id}/collaborator-roles/user-auth")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Tests — DELETE /flows/{id}/collaborator-roles/{user_id}
# ---------------------------------------------------------------------------


class TestFlowCollaboratorRoleDelete:
    def test_delete_removes_role(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_role(client, token, flow_id, user_id="user-del")
            resp = client.delete(
                f"/api/v1/flows/{flow_id}/collaborator-roles/user-del",
                headers=_auth(token),
            )
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True
        assert resp.json()["user_id"] == "user-del"
        assert resp.json()["flow_id"] == flow_id

    def test_delete_then_get_404(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_role(client, token, flow_id, user_id="user-gone")
            client.delete(
                f"/api/v1/flows/{flow_id}/collaborator-roles/user-gone",
                headers=_auth(token),
            )
            resp = client.get(
                f"/api/v1/flows/{flow_id}/collaborator-roles/user-gone",
                headers=_auth(token),
            )
        assert resp.status_code == 404

    def test_delete_404_not_found(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.delete(
                f"/api/v1/flows/{flow_id}/collaborator-roles/no-such-user",
                headers=_auth(token),
            )
        assert resp.status_code == 404

    def test_delete_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.delete(
                "/api/v1/flows/nonexistent/collaborator-roles/any-user",
                headers=_auth(token),
            )
        assert resp.status_code == 404

    def test_delete_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_role(client, token, flow_id, user_id="user-noauth")
            resp = client.delete(
                f"/api/v1/flows/{flow_id}/collaborator-roles/user-noauth"
            )
        assert resp.status_code == 401
