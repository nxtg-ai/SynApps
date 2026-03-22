"""
N-200: Flow Allowed Origins — PUT/GET/DELETE /flows/{id}/allowed-origins

Tests:
  - PUT sets origins config; returns 200
  - PUT response shape (flow_id, origins, enabled, updated_at)
  - PUT origins list stored
  - PUT empty origins list allowed
  - PUT enabled=False stored
  - PUT replaces existing config
  - PUT too many origins → 422
  - PUT 404 for unknown flow
  - PUT requires auth
  - GET returns config after PUT
  - GET 404 when no config
  - GET 404 for unknown flow
  - GET requires auth
  - DELETE removes config; returns {deleted: true, flow_id}
  - DELETE 404 when no config
  - DELETE 404 unknown flow
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
        json={"email": f"origins-{uid}@test.com", "password": "pass1234"},
    )
    assert r.status_code == 201
    return r.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_flow(client: TestClient, token: str) -> str:
    resp = client.post(
        "/api/v1/flows",
        json={"name": "Allowed Origins Test Flow", "nodes": [], "edges": []},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _set_origins(
    client: TestClient,
    token: str,
    flow_id: str,
    origins: list | None = None,
    enabled: bool = True,
) -> dict:
    resp = client.put(
        f"/api/v1/flows/{flow_id}/allowed-origins",
        json={"origins": origins or [], "enabled": enabled},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    return resp.json()


# ---------------------------------------------------------------------------
# Tests — PUT /flows/{id}/allowed-origins
# ---------------------------------------------------------------------------


class TestFlowAllowedOriginsPut:
    def test_put_returns_200(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/allowed-origins",
                json={"origins": ["https://example.com"]},
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
                f"/api/v1/flows/{flow_id}/allowed-origins",
                json={"origins": ["https://app.example.com"]},
                headers=_auth(token),
            )
        data = resp.json()
        assert data["flow_id"] == flow_id
        assert "origins" in data
        assert "enabled" in data
        assert "updated_at" in data

    def test_put_origins_stored(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/allowed-origins",
                json={"origins": ["https://a.com", "https://b.com"]},
                headers=_auth(token),
            )
        origins = resp.json()["origins"]
        assert "https://a.com" in origins
        assert "https://b.com" in origins

    def test_put_empty_origins_allowed(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/allowed-origins",
                json={"origins": []},
                headers=_auth(token),
            )
        assert resp.status_code == 200
        assert resp.json()["origins"] == []

    def test_put_enabled_false(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/allowed-origins",
                json={"origins": [], "enabled": False},
                headers=_auth(token),
            )
        assert resp.json()["enabled"] is False

    def test_put_replaces_existing(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_origins(client, token, flow_id, origins=["https://old.com"])
            resp = client.put(
                f"/api/v1/flows/{flow_id}/allowed-origins",
                json={"origins": ["https://new.com"]},
                headers=_auth(token),
            )
        origins = resp.json()["origins"]
        assert "https://new.com" in origins
        assert "https://old.com" not in origins

    def test_put_too_many_origins_422(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            origins = [f"https://origin{i}.com" for i in range(51)]
            resp = client.put(
                f"/api/v1/flows/{flow_id}/allowed-origins",
                json={"origins": origins},
                headers=_auth(token),
            )
        assert resp.status_code == 422
        assert "error" in resp.json()

    def test_put_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.put(
                "/api/v1/flows/nonexistent/allowed-origins",
                json={"origins": []},
                headers=_auth(token),
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_put_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/allowed-origins",
                json={"origins": []},
            )
        assert resp.status_code == 401
        assert "error" in resp.json()


# ---------------------------------------------------------------------------
# Tests — GET /flows/{id}/allowed-origins
# ---------------------------------------------------------------------------


class TestFlowAllowedOriginsGet:
    def test_get_returns_config_after_put(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_origins(client, token, flow_id, origins=["https://get-test.com"])
            resp = client.get(f"/api/v1/flows/{flow_id}/allowed-origins", headers=_auth(token))
        assert resp.status_code == 200
        assert "https://get-test.com" in resp.json()["origins"]

    def test_get_404_when_no_config(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/allowed-origins", headers=_auth(token))
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_get_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get(
                "/api/v1/flows/nonexistent/allowed-origins", headers=_auth(token)
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_get_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_origins(client, token, flow_id)
            resp = client.get(f"/api/v1/flows/{flow_id}/allowed-origins")
        assert resp.status_code == 401
        assert "error" in resp.json()


# ---------------------------------------------------------------------------
# Tests — DELETE /flows/{id}/allowed-origins
# ---------------------------------------------------------------------------


class TestFlowAllowedOriginsDelete:
    def test_delete_removes_config(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_origins(client, token, flow_id)
            resp = client.delete(
                f"/api/v1/flows/{flow_id}/allowed-origins", headers=_auth(token)
            )
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True
        assert resp.json()["flow_id"] == flow_id

    def test_get_404_after_delete(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_origins(client, token, flow_id)
            client.delete(f"/api/v1/flows/{flow_id}/allowed-origins", headers=_auth(token))
            resp = client.get(f"/api/v1/flows/{flow_id}/allowed-origins", headers=_auth(token))
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_delete_404_when_no_config(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.delete(
                f"/api/v1/flows/{flow_id}/allowed-origins", headers=_auth(token)
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_delete_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.delete(
                "/api/v1/flows/nonexistent/allowed-origins", headers=_auth(token)
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_delete_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_origins(client, token, flow_id)
            resp = client.delete(f"/api/v1/flows/{flow_id}/allowed-origins")
        assert resp.status_code == 401
        assert "error" in resp.json()
