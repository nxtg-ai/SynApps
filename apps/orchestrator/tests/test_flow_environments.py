"""
N-163: Flow Environments — PUT/GET/DELETE /flows/{id}/environments/{env}
                            GET            /flows/{id}/environments
                            POST           /flows/{id}/environments/{env}/activate

Tests:
  - PUT creates environment; returns 200
  - PUT response shape (flow_id, name, config, active, created_at, updated_at)
  - PUT invalid env name → 422
  - PUT replaces existing environment config
  - GET returns empty list on fresh flow
  - GET lists environments after PUT
  - GET returns flow_id, total, allowed_names
  - GET single environment by name
  - GET single 404 for unconfigured
  - POST /activate sets active=True; others set to False
  - POST /activate 404 for unconfigured env
  - DELETE removes environment; returns {deleted, env_name}
  - DELETE 404 for unconfigured
  - DELETE invalid env name → 422
  - GET after DELETE shows one less environment
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
        json={"email": f"env-{uid}@test.com", "password": "pass1234"},
    )
    assert r.status_code == 201
    return r.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_flow(client: TestClient, token: str) -> str:
    resp = client.post(
        "/api/v1/flows",
        json={"name": "Environment Test Flow", "nodes": [], "edges": []},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _set_env(
    client: TestClient,
    token: str,
    flow_id: str,
    env: str = "development",
    config: dict | None = None,
) -> dict:
    resp = client.put(
        f"/api/v1/flows/{flow_id}/environments/{env}",
        json={"config": config or {}},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    return resp.json()


# ---------------------------------------------------------------------------
# Tests — PUT /flows/{id}/environments/{env}
# ---------------------------------------------------------------------------


class TestFlowEnvironmentPut:
    def test_put_returns_200(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/environments/development",
                json={"config": {}},
                headers=_auth(token),
            )
        assert resp.status_code == 200

    def test_put_response_shape(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/environments/staging",
                json={"config": {"API_URL": "https://staging.api.example.com"}},
                headers=_auth(token),
            )
        data = resp.json()
        assert data["flow_id"] == flow_id
        assert data["name"] == "staging"
        assert data["config"]["API_URL"] == "https://staging.api.example.com"
        assert data["active"] is False
        assert "created_at" in data
        assert "updated_at" in data

    def test_put_invalid_env_name_422(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/environments/testing",
                json={"config": {}},
                headers=_auth(token),
            )
        assert resp.status_code == 422

    def test_put_replaces_config(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_env(client, token, flow_id, "production", {"KEY": "old"})
            resp = client.put(
                f"/api/v1/flows/{flow_id}/environments/production",
                json={"config": {"KEY": "new", "EXTRA": "val"}},
                headers=_auth(token),
            )
        assert resp.json()["config"] == {"KEY": "new", "EXTRA": "val"}

    def test_put_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.put(
                "/api/v1/flows/nonexistent/environments/development",
                json={"config": {}},
                headers=_auth(token),
            )
        assert resp.status_code == 404

    def test_put_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/environments/development",
                json={"config": {}},
            )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Tests — GET /flows/{id}/environments
# ---------------------------------------------------------------------------


class TestFlowEnvironmentList:
    def test_get_empty_on_fresh_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/environments", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["environments"] == []

    def test_get_lists_environments(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_env(client, token, flow_id, "development")
            _set_env(client, token, flow_id, "staging")
            resp = client.get(f"/api/v1/flows/{flow_id}/environments", headers=_auth(token))
        data = resp.json()
        assert data["total"] == 2
        names = {e["name"] for e in data["environments"]}
        assert names == {"development", "staging"}

    def test_get_has_allowed_names(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/environments", headers=_auth(token))
        assert len(resp.json()["allowed_names"]) == 3

    def test_get_flow_id_in_response(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/environments", headers=_auth(token))
        assert resp.json()["flow_id"] == flow_id

    def test_get_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get("/api/v1/flows/nonexistent/environments", headers=_auth(token))
        assert resp.status_code == 404

    def test_get_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/environments")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Tests — GET /flows/{id}/environments/{env}
# ---------------------------------------------------------------------------


class TestFlowEnvironmentGetOne:
    def test_get_single_environment(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_env(client, token, flow_id, "production", {"DB_HOST": "prod.db"})
            resp = client.get(
                f"/api/v1/flows/{flow_id}/environments/production", headers=_auth(token)
            )
        assert resp.status_code == 200
        assert resp.json()["config"]["DB_HOST"] == "prod.db"

    def test_get_single_404_unconfigured(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(
                f"/api/v1/flows/{flow_id}/environments/staging", headers=_auth(token)
            )
        assert resp.status_code == 404

    def test_get_single_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_env(client, token, flow_id, "development")
            resp = client.get(f"/api/v1/flows/{flow_id}/environments/development")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Tests — POST /flows/{id}/environments/{env}/activate
# ---------------------------------------------------------------------------


class TestFlowEnvironmentActivate:
    def test_activate_sets_active_true(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_env(client, token, flow_id, "staging")
            resp = client.post(
                f"/api/v1/flows/{flow_id}/environments/staging/activate",
                headers=_auth(token),
            )
        assert resp.status_code == 200
        assert resp.json()["active"] is True

    def test_activate_deactivates_others(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_env(client, token, flow_id, "development")
            _set_env(client, token, flow_id, "production")
            client.post(
                f"/api/v1/flows/{flow_id}/environments/development/activate",
                headers=_auth(token),
            )
            client.post(
                f"/api/v1/flows/{flow_id}/environments/production/activate",
                headers=_auth(token),
            )
            resp = client.get(f"/api/v1/flows/{flow_id}/environments", headers=_auth(token))
        active = [e for e in resp.json()["environments"] if e["active"]]
        assert len(active) == 1
        assert active[0]["name"] == "production"

    def test_activate_404_unconfigured(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/environments/staging/activate",
                headers=_auth(token),
            )
        assert resp.status_code == 404

    def test_activate_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_env(client, token, flow_id, "staging")
            resp = client.post(f"/api/v1/flows/{flow_id}/environments/staging/activate")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Tests — DELETE /flows/{id}/environments/{env}
# ---------------------------------------------------------------------------


class TestFlowEnvironmentDelete:
    def test_delete_removes_environment(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_env(client, token, flow_id, "development")
            resp = client.delete(
                f"/api/v1/flows/{flow_id}/environments/development", headers=_auth(token)
            )
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True
        assert resp.json()["env_name"] == "development"

    def test_get_after_delete_shows_less(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_env(client, token, flow_id, "development")
            _set_env(client, token, flow_id, "staging")
            client.delete(
                f"/api/v1/flows/{flow_id}/environments/development", headers=_auth(token)
            )
            resp = client.get(f"/api/v1/flows/{flow_id}/environments", headers=_auth(token))
        assert resp.json()["total"] == 1

    def test_delete_404_unconfigured(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.delete(
                f"/api/v1/flows/{flow_id}/environments/staging", headers=_auth(token)
            )
        assert resp.status_code == 404

    def test_delete_invalid_env_name_422(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.delete(
                f"/api/v1/flows/{flow_id}/environments/testing", headers=_auth(token)
            )
        assert resp.status_code == 422

    def test_delete_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.delete(
                "/api/v1/flows/nonexistent/environments/staging", headers=_auth(token)
            )
        assert resp.status_code == 404

    def test_delete_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_env(client, token, flow_id, "development")
            resp = client.delete(f"/api/v1/flows/{flow_id}/environments/development")
        assert resp.status_code == 401
