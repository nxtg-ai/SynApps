"""
N-194: Flow Webhook Signing — PUT/GET/DELETE /flows/{id}/webhook-signing

Tests:
  - PUT sets signing config; returns 200
  - PUT response shape (flow_id, secret, algorithm, enabled, updated_at)
  - PUT secret stored
  - PUT algorithm sha256 stored
  - PUT algorithm sha512 stored
  - PUT invalid algorithm → 422
  - PUT secret too short → 422
  - PUT enabled=False stored
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
        json={"email": f"whsign-{uid}@test.com", "password": "pass1234"},
    )
    assert r.status_code == 201
    return r.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_flow(client: TestClient, token: str) -> str:
    resp = client.post(
        "/api/v1/flows",
        json={"name": "Webhook Signing Test Flow", "nodes": [], "edges": []},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _set_signing(
    client: TestClient,
    token: str,
    flow_id: str,
    secret: str = "supersecretkey123",
    algorithm: str = "sha256",
    enabled: bool = True,
) -> dict:
    resp = client.put(
        f"/api/v1/flows/{flow_id}/webhook-signing",
        json={"secret": secret, "algorithm": algorithm, "enabled": enabled},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    return resp.json()


# ---------------------------------------------------------------------------
# Tests — PUT /flows/{id}/webhook-signing
# ---------------------------------------------------------------------------


class TestFlowWebhookSigningPut:
    def test_put_returns_200(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/webhook-signing",
                json={"secret": "mysecretkey1234"},
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
                f"/api/v1/flows/{flow_id}/webhook-signing",
                json={"secret": "shapetest_key1234"},
                headers=_auth(token),
            )
        data = resp.json()
        assert data["flow_id"] == flow_id
        assert "secret" in data
        assert "algorithm" in data
        assert "enabled" in data
        assert "updated_at" in data

    def test_put_secret_stored(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/webhook-signing",
                json={"secret": "stored_secret_abc"},
                headers=_auth(token),
            )
        assert resp.json()["secret"] == "stored_secret_abc"

    def test_put_algorithm_sha256(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/webhook-signing",
                json={"secret": "algo256secret123", "algorithm": "sha256"},
                headers=_auth(token),
            )
        assert resp.json()["algorithm"] == "sha256"

    def test_put_algorithm_sha512(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/webhook-signing",
                json={"secret": "algo512secret123", "algorithm": "sha512"},
                headers=_auth(token),
            )
        assert resp.json()["algorithm"] == "sha512"

    def test_put_invalid_algorithm_422(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/webhook-signing",
                json={"secret": "invalidsecret123", "algorithm": "md5"},
                headers=_auth(token),
            )
        assert resp.status_code == 422
        assert "error" in resp.json()

    def test_put_secret_too_short_422(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/webhook-signing",
                json={"secret": "abc"},
                headers=_auth(token),
            )
        assert resp.status_code == 422
        assert "error" in resp.json()

    def test_put_enabled_false(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/webhook-signing",
                json={"secret": "disabled_key_abc123", "enabled": False},
                headers=_auth(token),
            )
        assert resp.json()["enabled"] is False

    def test_put_replaces_existing(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_signing(client, token, flow_id, secret="old_secret_key123")
            resp = client.put(
                f"/api/v1/flows/{flow_id}/webhook-signing",
                json={"secret": "new_secret_key456", "algorithm": "sha512"},
                headers=_auth(token),
            )
        assert resp.json()["secret"] == "new_secret_key456"
        assert resp.json()["algorithm"] == "sha512"

    def test_put_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.put(
                "/api/v1/flows/nonexistent/webhook-signing",
                json={"secret": "anysecretkey123"},
                headers=_auth(token),
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_put_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/webhook-signing",
                json={"secret": "anysecretkey123"},
            )
        assert resp.status_code == 401
        assert "error" in resp.json()


# ---------------------------------------------------------------------------
# Tests — GET /flows/{id}/webhook-signing
# ---------------------------------------------------------------------------


class TestFlowWebhookSigningGet:
    def test_get_returns_config_after_put(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_signing(client, token, flow_id, algorithm="sha512")
            resp = client.get(f"/api/v1/flows/{flow_id}/webhook-signing", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["algorithm"] == "sha512"

    def test_get_404_when_no_config(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/webhook-signing", headers=_auth(token))
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_get_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get(
                "/api/v1/flows/nonexistent/webhook-signing", headers=_auth(token)
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_get_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_signing(client, token, flow_id)
            resp = client.get(f"/api/v1/flows/{flow_id}/webhook-signing")
        assert resp.status_code == 401
        assert "error" in resp.json()


# ---------------------------------------------------------------------------
# Tests — DELETE /flows/{id}/webhook-signing
# ---------------------------------------------------------------------------


class TestFlowWebhookSigningDelete:
    def test_delete_removes_config(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_signing(client, token, flow_id)
            resp = client.delete(
                f"/api/v1/flows/{flow_id}/webhook-signing", headers=_auth(token)
            )
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True
        assert resp.json()["flow_id"] == flow_id

    def test_get_404_after_delete(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_signing(client, token, flow_id)
            client.delete(f"/api/v1/flows/{flow_id}/webhook-signing", headers=_auth(token))
            resp = client.get(f"/api/v1/flows/{flow_id}/webhook-signing", headers=_auth(token))
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_delete_404_when_no_config(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.delete(
                f"/api/v1/flows/{flow_id}/webhook-signing", headers=_auth(token)
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_delete_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.delete(
                "/api/v1/flows/nonexistent/webhook-signing", headers=_auth(token)
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_delete_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_signing(client, token, flow_id)
            resp = client.delete(f"/api/v1/flows/{flow_id}/webhook-signing")
        assert resp.status_code == 401
        assert "error" in resp.json()
