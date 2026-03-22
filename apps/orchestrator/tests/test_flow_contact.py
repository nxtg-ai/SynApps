"""
N-170: Flow Contact Info — PUT/GET/DELETE /flows/{id}/contact

Tests:
  - PUT creates contact; returns 200
  - PUT response shape (flow_id, name, email, slack_handle, team, updated_at)
  - PUT all fields populated
  - PUT with all empty strings succeeds
  - PUT replaces existing contact
  - PUT 404 for unknown flow
  - PUT requires auth
  - GET returns contact after PUT
  - GET 404 when no contact set
  - GET 404 for unknown flow
  - GET requires auth
  - DELETE removes contact; returns {deleted: true, flow_id}
  - DELETE 404 when no contact set
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
        json={"email": f"contact-{uid}@test.com", "password": "pass1234"},
    )
    assert r.status_code == 201
    return r.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_flow(client: TestClient, token: str) -> str:
    resp = client.post(
        "/api/v1/flows",
        json={"name": "Contact Test Flow", "nodes": [], "edges": []},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _set_contact(
    client: TestClient,
    token: str,
    flow_id: str,
    name: str = "Alice",
    email: str = "alice@example.com",
    slack_handle: str = "@alice",
    team: str = "Platform",
) -> dict:
    resp = client.put(
        f"/api/v1/flows/{flow_id}/contact",
        json={"name": name, "email": email, "slack_handle": slack_handle, "team": team},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    return resp.json()


# ---------------------------------------------------------------------------
# Tests — PUT /flows/{id}/contact
# ---------------------------------------------------------------------------


class TestFlowContactPut:
    def test_put_returns_200(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/contact",
                json={"name": "Bob", "email": "bob@example.com", "slack_handle": "@bob", "team": "Infra"},
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
                f"/api/v1/flows/{flow_id}/contact",
                json={"name": "Carol", "email": "carol@example.com", "slack_handle": "@carol", "team": "AI"},
                headers=_auth(token),
            )
        data = resp.json()
        assert data["flow_id"] == flow_id
        assert data["name"] == "Carol"
        assert data["email"] == "carol@example.com"
        assert data["slack_handle"] == "@carol"
        assert data["team"] == "AI"
        assert "updated_at" in data

    def test_put_all_fields_populated(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/contact",
                json={
                    "name": "Dave",
                    "email": "dave@company.org",
                    "slack_handle": "#team-ai",
                    "team": "Machine Learning",
                },
                headers=_auth(token),
            )
        data = resp.json()
        assert data["team"] == "Machine Learning"

    def test_put_empty_strings_succeeds(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/contact",
                json={"name": "", "email": "", "slack_handle": "", "team": ""},
                headers=_auth(token),
            )
        assert resp.status_code == 200
        assert resp.json()["name"] == ""

    def test_put_replaces_existing(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_contact(client, token, flow_id, name="Old Name")
            resp = client.put(
                f"/api/v1/flows/{flow_id}/contact",
                json={"name": "New Name", "email": "", "slack_handle": "", "team": ""},
                headers=_auth(token),
            )
        assert resp.json()["name"] == "New Name"

    def test_put_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.put(
                "/api/v1/flows/nonexistent/contact",
                json={"name": "X", "email": "", "slack_handle": "", "team": ""},
                headers=_auth(token),
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_put_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/contact",
                json={"name": "", "email": "", "slack_handle": "", "team": ""},
            )
        assert resp.status_code == 401
        assert "error" in resp.json()


# ---------------------------------------------------------------------------
# Tests — GET /flows/{id}/contact
# ---------------------------------------------------------------------------


class TestFlowContactGet:
    def test_get_returns_contact_after_put(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_contact(client, token, flow_id, team="Backend")
            resp = client.get(f"/api/v1/flows/{flow_id}/contact", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["team"] == "Backend"

    def test_get_404_when_no_contact(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/contact", headers=_auth(token))
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_get_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get("/api/v1/flows/nonexistent/contact", headers=_auth(token))
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_get_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_contact(client, token, flow_id)
            resp = client.get(f"/api/v1/flows/{flow_id}/contact")
        assert resp.status_code == 401
        assert "error" in resp.json()


# ---------------------------------------------------------------------------
# Tests — DELETE /flows/{id}/contact
# ---------------------------------------------------------------------------


class TestFlowContactDelete:
    def test_delete_removes_contact(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_contact(client, token, flow_id)
            resp = client.delete(f"/api/v1/flows/{flow_id}/contact", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True
        assert resp.json()["flow_id"] == flow_id

    def test_get_404_after_delete(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_contact(client, token, flow_id)
            client.delete(f"/api/v1/flows/{flow_id}/contact", headers=_auth(token))
            resp = client.get(f"/api/v1/flows/{flow_id}/contact", headers=_auth(token))
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_delete_404_when_no_contact(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.delete(f"/api/v1/flows/{flow_id}/contact", headers=_auth(token))
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_delete_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.delete("/api/v1/flows/nonexistent/contact", headers=_auth(token))
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_delete_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_contact(client, token, flow_id)
            resp = client.delete(f"/api/v1/flows/{flow_id}/contact")
        assert resp.status_code == 401
        assert "error" in resp.json()
