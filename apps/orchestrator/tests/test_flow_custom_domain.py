"""
N-193: Flow Custom Domain — PUT/GET/DELETE /flows/{id}/custom-domain

Tests:
  - PUT sets domain; returns 200
  - PUT response shape (flow_id, domain, enabled, updated_at)
  - PUT domain stored
  - PUT enabled=True stored
  - PUT enabled=False stored
  - PUT replaces existing domain
  - PUT domain too short → 422
  - PUT domain too long → 422
  - PUT duplicate domain on different flow → 422
  - PUT 404 for unknown flow
  - PUT requires auth
  - GET returns domain after PUT
  - GET 404 when no domain
  - GET 404 for unknown flow
  - GET requires auth
  - DELETE removes domain; returns {deleted: true, flow_id}
  - DELETE 404 when no domain
  - DELETE 404 unknown flow
  - DELETE requires auth
  - GET 404 after DELETE
  - PUT same domain on same flow (re-registration) allowed
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
        json={"email": f"cdom-{uid}@test.com", "password": "pass1234"},
    )
    assert r.status_code == 201
    return r.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_flow(client: TestClient, token: str) -> str:
    resp = client.post(
        "/api/v1/flows",
        json={"name": "Custom Domain Test Flow", "nodes": [], "edges": []},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _set_domain(
    client: TestClient,
    token: str,
    flow_id: str,
    domain: str = "api.example.com",
    enabled: bool = True,
) -> dict:
    resp = client.put(
        f"/api/v1/flows/{flow_id}/custom-domain",
        json={"domain": domain, "enabled": enabled},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    return resp.json()


# ---------------------------------------------------------------------------
# Tests — PUT /flows/{id}/custom-domain
# ---------------------------------------------------------------------------


class TestFlowCustomDomainPut:
    def test_put_returns_200(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/custom-domain",
                json={"domain": "api.myapp.com"},
                headers=_auth(token),
            )
        assert resp.status_code == 200

    def test_put_response_shape(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/custom-domain",
                json={"domain": "shape.example.com"},
                headers=_auth(token),
            )
        data = resp.json()
        assert data["flow_id"] == flow_id
        assert "domain" in data
        assert "enabled" in data
        assert "updated_at" in data

    def test_put_domain_stored(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/custom-domain",
                json={"domain": "stored.example.com"},
                headers=_auth(token),
            )
        assert resp.json()["domain"] == "stored.example.com"

    def test_put_enabled_true(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/custom-domain",
                json={"domain": "enabled.example.com", "enabled": True},
                headers=_auth(token),
            )
        assert resp.json()["enabled"] is True

    def test_put_enabled_false(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/custom-domain",
                json={"domain": "disabled.example.com", "enabled": False},
                headers=_auth(token),
            )
        assert resp.json()["enabled"] is False

    def test_put_replaces_existing(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_domain(client, token, flow_id, domain="old.example.com")
            resp = client.put(
                f"/api/v1/flows/{flow_id}/custom-domain",
                json={"domain": "new.example.com"},
                headers=_auth(token),
            )
        assert resp.json()["domain"] == "new.example.com"

    def test_put_domain_too_short_422(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/custom-domain",
                json={"domain": "ab"},
                headers=_auth(token),
            )
        assert resp.status_code == 422

    def test_put_domain_too_long_422(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/custom-domain",
                json={"domain": "a" * 254},
                headers=_auth(token),
            )
        assert resp.status_code == 422

    def test_put_duplicate_domain_different_flow_422(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id_1 = _create_flow(client, token)
            flow_id_2 = _create_flow(client, token)
            _set_domain(client, token, flow_id_1, domain="shared.example.com")
            resp = client.put(
                f"/api/v1/flows/{flow_id_2}/custom-domain",
                json={"domain": "shared.example.com"},
                headers=_auth(token),
            )
        assert resp.status_code == 422

    def test_put_same_domain_same_flow_allowed(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_domain(client, token, flow_id, domain="reuse.example.com")
            resp = client.put(
                f"/api/v1/flows/{flow_id}/custom-domain",
                json={"domain": "reuse.example.com", "enabled": False},
                headers=_auth(token),
            )
        assert resp.status_code == 200

    def test_put_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.put(
                "/api/v1/flows/nonexistent/custom-domain",
                json={"domain": "api.example.com"},
                headers=_auth(token),
            )
        assert resp.status_code == 404

    def test_put_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/custom-domain",
                json={"domain": "api.example.com"},
            )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Tests — GET /flows/{id}/custom-domain
# ---------------------------------------------------------------------------


class TestFlowCustomDomainGet:
    def test_get_returns_domain_after_put(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_domain(client, token, flow_id, domain="get.example.com")
            resp = client.get(f"/api/v1/flows/{flow_id}/custom-domain", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["domain"] == "get.example.com"

    def test_get_404_when_no_domain(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/custom-domain", headers=_auth(token))
        assert resp.status_code == 404

    def test_get_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get("/api/v1/flows/nonexistent/custom-domain", headers=_auth(token))
        assert resp.status_code == 404

    def test_get_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_domain(client, token, flow_id)
            resp = client.get(f"/api/v1/flows/{flow_id}/custom-domain")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Tests — DELETE /flows/{id}/custom-domain
# ---------------------------------------------------------------------------


class TestFlowCustomDomainDelete:
    def test_delete_removes_domain(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_domain(client, token, flow_id)
            resp = client.delete(f"/api/v1/flows/{flow_id}/custom-domain", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True
        assert resp.json()["flow_id"] == flow_id

    def test_get_404_after_delete(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_domain(client, token, flow_id)
            client.delete(f"/api/v1/flows/{flow_id}/custom-domain", headers=_auth(token))
            resp = client.get(f"/api/v1/flows/{flow_id}/custom-domain", headers=_auth(token))
        assert resp.status_code == 404

    def test_delete_404_when_no_domain(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.delete(f"/api/v1/flows/{flow_id}/custom-domain", headers=_auth(token))
        assert resp.status_code == 404

    def test_delete_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.delete(
                "/api/v1/flows/nonexistent/custom-domain", headers=_auth(token)
            )
        assert resp.status_code == 404

    def test_delete_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_domain(client, token, flow_id)
            resp = client.delete(f"/api/v1/flows/{flow_id}/custom-domain")
        assert resp.status_code == 401
