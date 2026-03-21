"""
N-183: Flow Caching Configuration — PUT/GET/DELETE /flows/{id}/caching-config

Tests:
  - PUT sets caching config; returns 200
  - PUT response shape (flow_id, enabled, ttl_seconds, key_fields, updated_at)
  - PUT enabled=True stored
  - PUT enabled=False stored
  - PUT ttl_seconds stored
  - PUT key_fields stored
  - PUT ttl_seconds=0 allowed (no cache)
  - PUT ttl_seconds=86400 (max) allowed
  - PUT ttl_seconds=86401 → 422
  - PUT too many key_fields → 422
  - PUT replaces existing config
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
        json={"email": f"cache-{uid}@test.com", "password": "pass1234"},
    )
    assert r.status_code == 201
    return r.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_flow(client: TestClient, token: str) -> str:
    resp = client.post(
        "/api/v1/flows",
        json={"name": "Caching Config Test Flow", "nodes": [], "edges": []},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _set_caching(
    client: TestClient,
    token: str,
    flow_id: str,
    enabled: bool = True,
    ttl_seconds: int = 300,
    key_fields: list | None = None,
) -> dict:
    resp = client.put(
        f"/api/v1/flows/{flow_id}/caching-config",
        json={"enabled": enabled, "ttl_seconds": ttl_seconds, "key_fields": key_fields or []},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    return resp.json()


# ---------------------------------------------------------------------------
# Tests — PUT /flows/{id}/caching-config
# ---------------------------------------------------------------------------


class TestFlowCachingConfigPut:
    def test_put_returns_200(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/caching-config",
                json={"enabled": True, "ttl_seconds": 60},
                headers=_auth(token),
            )
        assert resp.status_code == 200

    def test_put_response_shape(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/caching-config",
                json={"enabled": False, "ttl_seconds": 0},
                headers=_auth(token),
            )
        data = resp.json()
        assert data["flow_id"] == flow_id
        assert "enabled" in data
        assert "ttl_seconds" in data
        assert "key_fields" in data
        assert "updated_at" in data

    def test_put_enabled_true(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/caching-config",
                json={"enabled": True},
                headers=_auth(token),
            )
        assert resp.json()["enabled"] is True

    def test_put_enabled_false(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/caching-config",
                json={"enabled": False},
                headers=_auth(token),
            )
        assert resp.json()["enabled"] is False

    def test_put_ttl_seconds_stored(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/caching-config",
                json={"ttl_seconds": 3600},
                headers=_auth(token),
            )
        assert resp.json()["ttl_seconds"] == 3600

    def test_put_key_fields_stored(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/caching-config",
                json={"key_fields": ["user_id", "region"]},
                headers=_auth(token),
            )
        assert resp.json()["key_fields"] == ["user_id", "region"]

    def test_put_ttl_zero_allowed(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/caching-config",
                json={"ttl_seconds": 0},
                headers=_auth(token),
            )
        assert resp.status_code == 200

    def test_put_ttl_max_allowed(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/caching-config",
                json={"ttl_seconds": 86400},
                headers=_auth(token),
            )
        assert resp.status_code == 200

    def test_put_ttl_too_large_422(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/caching-config",
                json={"ttl_seconds": 86401},
                headers=_auth(token),
            )
        assert resp.status_code == 422

    def test_put_too_many_key_fields_422(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/caching-config",
                json={"key_fields": [f"field{i}" for i in range(11)]},
                headers=_auth(token),
            )
        assert resp.status_code == 422

    def test_put_replaces_existing(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_caching(client, token, flow_id, ttl_seconds=60)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/caching-config",
                json={"ttl_seconds": 1800},
                headers=_auth(token),
            )
        assert resp.json()["ttl_seconds"] == 1800

    def test_put_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.put(
                "/api/v1/flows/nonexistent/caching-config",
                json={"enabled": True},
                headers=_auth(token),
            )
        assert resp.status_code == 404

    def test_put_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/caching-config",
                json={"enabled": True},
            )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Tests — GET /flows/{id}/caching-config
# ---------------------------------------------------------------------------


class TestFlowCachingConfigGet:
    def test_get_returns_config_after_put(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_caching(client, token, flow_id, enabled=True, ttl_seconds=900)
            resp = client.get(f"/api/v1/flows/{flow_id}/caching-config", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["ttl_seconds"] == 900

    def test_get_404_when_no_config(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/caching-config", headers=_auth(token))
        assert resp.status_code == 404

    def test_get_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get(
                "/api/v1/flows/nonexistent/caching-config", headers=_auth(token)
            )
        assert resp.status_code == 404

    def test_get_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_caching(client, token, flow_id)
            resp = client.get(f"/api/v1/flows/{flow_id}/caching-config")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Tests — DELETE /flows/{id}/caching-config
# ---------------------------------------------------------------------------


class TestFlowCachingConfigDelete:
    def test_delete_removes_config(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_caching(client, token, flow_id)
            resp = client.delete(
                f"/api/v1/flows/{flow_id}/caching-config", headers=_auth(token)
            )
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True
        assert resp.json()["flow_id"] == flow_id

    def test_get_404_after_delete(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_caching(client, token, flow_id)
            client.delete(f"/api/v1/flows/{flow_id}/caching-config", headers=_auth(token))
            resp = client.get(f"/api/v1/flows/{flow_id}/caching-config", headers=_auth(token))
        assert resp.status_code == 404

    def test_delete_404_when_no_config(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.delete(
                f"/api/v1/flows/{flow_id}/caching-config", headers=_auth(token)
            )
        assert resp.status_code == 404

    def test_delete_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.delete(
                "/api/v1/flows/nonexistent/caching-config", headers=_auth(token)
            )
        assert resp.status_code == 404

    def test_delete_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_caching(client, token, flow_id)
            resp = client.delete(f"/api/v1/flows/{flow_id}/caching-config")
        assert resp.status_code == 401
