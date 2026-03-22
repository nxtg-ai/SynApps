"""
N-162: Flow Collaborators — PUT/GET/DELETE /flows/{id}/collaborators/{user}
                             GET            /flows/{id}/collaborators

Tests:
  - PUT adds collaborator; returns 200
  - PUT response shape (flow_id, user, role)
  - PUT invalid role → 422
  - PUT updates role for existing collaborator
  - GET returns empty list on fresh flow
  - GET lists collaborators after add
  - GET returns flow_id, total, allowed_roles
  - GET single collaborator by user
  - GET single 404 for unknown user
  - DELETE removes collaborator; returns {deleted: true, user}
  - DELETE 404 for user not added
  - GET after DELETE shows empty list
  - Two collaborators with different roles
  - PUT/GET/DELETE 404 for unknown flow
  - Auth required on all endpoints
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
        json={"email": f"collab-{uid}@test.com", "password": "pass1234"},
    )
    assert r.status_code == 201
    return r.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_flow(client: TestClient, token: str) -> str:
    resp = client.post(
        "/api/v1/flows",
        json={"name": "Collaborator Test Flow", "nodes": [], "edges": []},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _add_collaborator(
    client: TestClient,
    token: str,
    flow_id: str,
    user: str = "alice@example.com",
    role: str = "editor",
) -> dict:
    resp = client.put(
        f"/api/v1/flows/{flow_id}/collaborators/{user}",
        json={"role": role},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    return resp.json()


# ---------------------------------------------------------------------------
# Tests — PUT /flows/{id}/collaborators/{user}
# ---------------------------------------------------------------------------


class TestFlowCollaboratorPut:
    def test_put_returns_200(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/collaborators/bob@example.com",
                json={"role": "viewer"},
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
                f"/api/v1/flows/{flow_id}/collaborators/alice@example.com",
                json={"role": "editor"},
                headers=_auth(token),
            )
        data = resp.json()
        assert data["flow_id"] == flow_id
        assert data["user"] == "alice@example.com"
        assert data["role"] == "editor"

    def test_put_invalid_role_422(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/collaborators/bob@example.com",
                json={"role": "superadmin"},
                headers=_auth(token),
            )
        assert resp.status_code == 422
        assert "error" in resp.json()

    def test_put_updates_existing_role(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _add_collaborator(client, token, flow_id, "alice@example.com", "viewer")
            resp = client.put(
                f"/api/v1/flows/{flow_id}/collaborators/alice@example.com",
                json={"role": "editor"},
                headers=_auth(token),
            )
        assert resp.json()["role"] == "editor"

    def test_put_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.put(
                "/api/v1/flows/nonexistent/collaborators/bob@example.com",
                json={"role": "viewer"},
                headers=_auth(token),
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_put_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/collaborators/bob@example.com",
                json={"role": "viewer"},
            )
        assert resp.status_code == 401
        assert "error" in resp.json()


# ---------------------------------------------------------------------------
# Tests — GET /flows/{id}/collaborators
# ---------------------------------------------------------------------------


class TestFlowCollaboratorList:
    def test_get_empty_on_fresh_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/collaborators", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["collaborators"] == []

    def test_get_lists_collaborators(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _add_collaborator(client, token, flow_id, "alice@example.com", "editor")
            _add_collaborator(client, token, flow_id, "bob@example.com", "viewer")
            resp = client.get(f"/api/v1/flows/{flow_id}/collaborators", headers=_auth(token))
        data = resp.json()
        assert data["total"] == 2
        users = {c["user"] for c in data["collaborators"]}
        assert users == {"alice@example.com", "bob@example.com"}

    def test_get_response_has_allowed_roles(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/collaborators", headers=_auth(token))
        assert len(resp.json()["allowed_roles"]) == 4

    def test_get_flow_id_in_response(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/collaborators", headers=_auth(token))
        assert resp.json()["flow_id"] == flow_id

    def test_get_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get("/api/v1/flows/nonexistent/collaborators", headers=_auth(token))
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_get_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/collaborators")
        assert resp.status_code == 401
        assert "error" in resp.json()


# ---------------------------------------------------------------------------
# Tests — GET /flows/{id}/collaborators/{user}
# ---------------------------------------------------------------------------


class TestFlowCollaboratorGetOne:
    def test_get_single_collaborator(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _add_collaborator(client, token, flow_id, "alice@example.com", "owner")
            resp = client.get(
                f"/api/v1/flows/{flow_id}/collaborators/alice@example.com",
                headers=_auth(token),
            )
        assert resp.status_code == 200
        assert resp.json()["role"] == "owner"

    def test_get_single_404_not_added(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(
                f"/api/v1/flows/{flow_id}/collaborators/nobody@example.com",
                headers=_auth(token),
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_get_single_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _add_collaborator(client, token, flow_id, "alice@example.com", "viewer")
            resp = client.get(
                f"/api/v1/flows/{flow_id}/collaborators/alice@example.com"
            )
        assert resp.status_code == 401
        assert "error" in resp.json()


# ---------------------------------------------------------------------------
# Tests — DELETE /flows/{id}/collaborators/{user}
# ---------------------------------------------------------------------------


class TestFlowCollaboratorDelete:
    def test_delete_removes_collaborator(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _add_collaborator(client, token, flow_id, "alice@example.com")
            resp = client.delete(
                f"/api/v1/flows/{flow_id}/collaborators/alice@example.com",
                headers=_auth(token),
            )
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True
        assert resp.json()["user"] == "alice@example.com"

    def test_get_after_delete_shows_empty(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _add_collaborator(client, token, flow_id, "alice@example.com")
            client.delete(
                f"/api/v1/flows/{flow_id}/collaborators/alice@example.com",
                headers=_auth(token),
            )
            resp = client.get(f"/api/v1/flows/{flow_id}/collaborators", headers=_auth(token))
        assert resp.json()["collaborators"] == []

    def test_delete_404_not_added(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.delete(
                f"/api/v1/flows/{flow_id}/collaborators/nobody@example.com",
                headers=_auth(token),
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_delete_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.delete(
                "/api/v1/flows/nonexistent/collaborators/alice@example.com",
                headers=_auth(token),
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_delete_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _add_collaborator(client, token, flow_id, "alice@example.com")
            resp = client.delete(
                f"/api/v1/flows/{flow_id}/collaborators/alice@example.com"
            )
        assert resp.status_code == 401
        assert "error" in resp.json()

    def test_two_collaborators_different_roles(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _add_collaborator(client, token, flow_id, "alice@example.com", "owner")
            _add_collaborator(client, token, flow_id, "bob@example.com", "commenter")
            resp = client.get(f"/api/v1/flows/{flow_id}/collaborators", headers=_auth(token))
        roles = {c["user"]: c["role"] for c in resp.json()["collaborators"]}
        assert roles["alice@example.com"] == "owner"
        assert roles["bob@example.com"] == "commenter"
