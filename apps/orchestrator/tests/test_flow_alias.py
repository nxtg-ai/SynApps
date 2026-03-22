"""
N-150: Flow Aliases — GET/PUT/DELETE /api/v1/flows/{flow_id}/alias
                      GET /api/v1/flows/by-alias/{alias}

Tests:
  - GET returns null alias on fresh flow
  - GET returns flow_id in response
  - PUT sets alias; GET returns it
  - PUT updates to a new alias (old alias freed)
  - PUT same alias on same flow is idempotent
  - PUT invalid slug → 422
  - PUT alias already taken by another flow → 409
  - PUT 404 for unknown flow
  - DELETE removes alias
  - GET after DELETE shows null
  - DELETE when no alias → 404
  - DELETE 404 for unknown flow
  - GET /by-alias/{alias} returns full flow
  - GET /by-alias/{alias} 404 for unknown alias
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
        json={"email": f"alias-{uid}@test.com", "password": "pass1234"},
    )
    assert r.status_code == 201
    return r.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_flow(client: TestClient, token: str) -> str:
    resp = client.post(
        "/api/v1/flows",
        json={"name": "Alias Test Flow", "nodes": [], "edges": []},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


# ---------------------------------------------------------------------------
# Tests — GET /flows/{id}/alias
# ---------------------------------------------------------------------------


class TestFlowAliasGet:
    def test_null_by_default(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/alias", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["alias"] is None

    def test_flow_id_in_response(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/alias", headers=_auth(token))
        assert resp.json()["flow_id"] == flow_id

    def test_get_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get("/api/v1/flows/nonexistent/alias", headers=_auth(token))
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_get_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/alias")
        assert resp.status_code == 401
        assert "error" in resp.json()


# ---------------------------------------------------------------------------
# Tests — PUT /flows/{id}/alias
# ---------------------------------------------------------------------------


class TestFlowAliasPut:
    def test_put_returns_200(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/alias",
                json={"alias": "my-flow-alias"},
                headers=_auth(token),
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["flow_id"] == flow_id

    def test_put_stores_alias(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            client.put(
                f"/api/v1/flows/{flow_id}/alias",
                json={"alias": "stored-alias"},
                headers=_auth(token),
            )
            resp = client.get(f"/api/v1/flows/{flow_id}/alias", headers=_auth(token))
        assert resp.json()["alias"] == "stored-alias"

    def test_put_alias_in_response(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/alias",
                json={"alias": "response-alias"},
                headers=_auth(token),
            )
        assert resp.json()["alias"] == "response-alias"

    def test_put_updates_alias(self):
        """Updating to a new alias frees the old one."""
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            client.put(
                f"/api/v1/flows/{flow_id}/alias",
                json={"alias": "alias-v1"},
                headers=_auth(token),
            )
            client.put(
                f"/api/v1/flows/{flow_id}/alias",
                json={"alias": "alias-v2"},
                headers=_auth(token),
            )
            resp = client.get(f"/api/v1/flows/{flow_id}/alias", headers=_auth(token))
        assert resp.json()["alias"] == "alias-v2"

    def test_put_same_alias_idempotent(self):
        """Re-setting the same alias on the same flow is allowed."""
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            client.put(
                f"/api/v1/flows/{flow_id}/alias",
                json={"alias": "idempotent-alias"},
                headers=_auth(token),
            )
            resp = client.put(
                f"/api/v1/flows/{flow_id}/alias",
                json={"alias": "idempotent-alias"},
                headers=_auth(token),
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["flow_id"] == flow_id

    def test_put_invalid_slug_422(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/alias",
                json={"alias": "UPPERCASE"},
                headers=_auth(token),
            )
        assert resp.status_code == 422
        assert "error" in resp.json()

    def test_put_slug_with_spaces_422(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/alias",
                json={"alias": "has space"},
                headers=_auth(token),
            )
        assert resp.status_code == 422
        assert "error" in resp.json()

    def test_put_slug_starting_with_hyphen_422(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/alias",
                json={"alias": "-bad-start"},
                headers=_auth(token),
            )
        assert resp.status_code == 422
        assert "error" in resp.json()

    def test_put_conflict_409(self):
        """Same alias on two different flows → 409."""
        with TestClient(app) as client:
            token = _register(client)
            f1 = _create_flow(client, token)
            f2 = _create_flow(client, token)
            client.put(
                f"/api/v1/flows/{f1}/alias",
                json={"alias": "conflict-alias"},
                headers=_auth(token),
            )
            resp = client.put(
                f"/api/v1/flows/{f2}/alias",
                json={"alias": "conflict-alias"},
                headers=_auth(token),
            )
        assert resp.status_code == 409
        assert "error" in resp.json()

    def test_put_old_alias_freed_after_update(self):
        """After updating alias, the old slug can be claimed by another flow."""
        with TestClient(app) as client:
            token = _register(client)
            f1 = _create_flow(client, token)
            f2 = _create_flow(client, token)
            client.put(
                f"/api/v1/flows/{f1}/alias",
                json={"alias": "reuse-me"},
                headers=_auth(token),
            )
            # Update f1 to a new alias — "reuse-me" is now free
            client.put(
                f"/api/v1/flows/{f1}/alias",
                json={"alias": "new-alias-f1"},
                headers=_auth(token),
            )
            resp = client.put(
                f"/api/v1/flows/{f2}/alias",
                json={"alias": "reuse-me"},
                headers=_auth(token),
            )
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, (dict, list))

    def test_put_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.put(
                "/api/v1/flows/nonexistent/alias",
                json={"alias": "some-alias"},
                headers=_auth(token),
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_put_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/alias",
                json={"alias": "no-auth"},
            )
        assert resp.status_code == 401
        assert "error" in resp.json()


# ---------------------------------------------------------------------------
# Tests — DELETE /flows/{id}/alias
# ---------------------------------------------------------------------------


class TestFlowAliasDelete:
    def test_delete_removes_alias(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            client.put(
                f"/api/v1/flows/{flow_id}/alias",
                json={"alias": "delete-me"},
                headers=_auth(token),
            )
            resp = client.delete(f"/api/v1/flows/{flow_id}/alias", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["alias"] is None

    def test_get_after_delete_shows_null(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            client.put(
                f"/api/v1/flows/{flow_id}/alias",
                json={"alias": "temp-alias"},
                headers=_auth(token),
            )
            client.delete(f"/api/v1/flows/{flow_id}/alias", headers=_auth(token))
            resp = client.get(f"/api/v1/flows/{flow_id}/alias", headers=_auth(token))
        assert resp.json()["alias"] is None

    def test_delete_no_alias_404(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.delete(f"/api/v1/flows/{flow_id}/alias", headers=_auth(token))
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_delete_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.delete("/api/v1/flows/nonexistent/alias", headers=_auth(token))
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_delete_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            client.put(
                f"/api/v1/flows/{flow_id}/alias",
                json={"alias": "auth-delete"},
                headers=_auth(token),
            )
            resp = client.delete(f"/api/v1/flows/{flow_id}/alias")
        assert resp.status_code == 401
        assert "error" in resp.json()


# ---------------------------------------------------------------------------
# Tests — GET /flows/by-alias/{alias}
# ---------------------------------------------------------------------------


class TestFlowByAlias:
    def test_by_alias_returns_200(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            client.put(
                f"/api/v1/flows/{flow_id}/alias",
                json={"alias": "lookup-alias"},
                headers=_auth(token),
            )
            resp = client.get("/api/v1/flows/by-alias/lookup-alias", headers=_auth(token))
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == flow_id

    def test_by_alias_returns_correct_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            client.put(
                f"/api/v1/flows/{flow_id}/alias",
                json={"alias": "correct-flow"},
                headers=_auth(token),
            )
            resp = client.get("/api/v1/flows/by-alias/correct-flow", headers=_auth(token))
        assert resp.json()["id"] == flow_id

    def test_by_alias_404_unknown_alias(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get("/api/v1/flows/by-alias/no-such-alias", headers=_auth(token))
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_by_alias_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            client.put(
                f"/api/v1/flows/{flow_id}/alias",
                json={"alias": "needs-auth"},
                headers=_auth(token),
            )
            resp = client.get("/api/v1/flows/by-alias/needs-auth")
        assert resp.status_code == 401
        assert "error" in resp.json()

    def test_by_alias_404_after_delete(self):
        """Once the alias is deleted, by-alias lookup returns 404."""
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            client.put(
                f"/api/v1/flows/{flow_id}/alias",
                json={"alias": "gone-alias"},
                headers=_auth(token),
            )
            client.delete(f"/api/v1/flows/{flow_id}/alias", headers=_auth(token))
            resp = client.get("/api/v1/flows/by-alias/gone-alias", headers=_auth(token))
        assert resp.status_code == 404
        assert "error" in resp.json()
