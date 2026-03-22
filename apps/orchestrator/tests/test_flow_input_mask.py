"""
N-197: Flow Input Mask — PUT/GET/DELETE /flows/{id}/input-mask

Tests:
  - PUT sets mask config; returns 200
  - PUT response shape (flow_id, rules, enabled, updated_at)
  - PUT rules stored
  - PUT mask type full stored
  - PUT mask type partial stored
  - PUT mask type hash stored
  - PUT mask type redact stored
  - PUT invalid mask type → 422
  - PUT enabled=False stored
  - PUT empty rules allowed
  - PUT replaces existing config
  - PUT too many rules → 422
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
        json={"email": f"inmask-{uid}@test.com", "password": "pass1234"},
    )
    assert r.status_code == 201
    return r.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_flow(client: TestClient, token: str) -> str:
    resp = client.post(
        "/api/v1/flows",
        json={"name": "Input Mask Test Flow", "nodes": [], "edges": []},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _set_mask(
    client: TestClient,
    token: str,
    flow_id: str,
    rules: dict | None = None,
    enabled: bool = True,
) -> dict:
    resp = client.put(
        f"/api/v1/flows/{flow_id}/input-mask",
        json={"rules": rules or {}, "enabled": enabled},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    return resp.json()


# ---------------------------------------------------------------------------
# Tests — PUT /flows/{id}/input-mask
# ---------------------------------------------------------------------------


class TestFlowInputMaskPut:
    def test_put_returns_200(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/input-mask",
                json={"rules": {"password": "full"}},
                headers=_auth(token),
            )
        assert resp.status_code == 200

    def test_put_response_shape(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/input-mask",
                json={"rules": {"email": "partial"}},
                headers=_auth(token),
            )
        data = resp.json()
        assert data["flow_id"] == flow_id
        assert "rules" in data
        assert "enabled" in data
        assert "updated_at" in data

    def test_put_rules_stored(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/input-mask",
                json={"rules": {"ssn": "redact", "dob": "hash"}},
                headers=_auth(token),
            )
        rules = resp.json()["rules"]
        assert rules["ssn"] == "redact"
        assert rules["dob"] == "hash"

    def test_put_mask_type_full(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/input-mask",
                json={"rules": {"secret": "full"}},
                headers=_auth(token),
            )
        assert resp.json()["rules"]["secret"] == "full"

    def test_put_mask_type_partial(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/input-mask",
                json={"rules": {"card": "partial"}},
                headers=_auth(token),
            )
        assert resp.json()["rules"]["card"] == "partial"

    def test_put_mask_type_hash(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/input-mask",
                json={"rules": {"pin": "hash"}},
                headers=_auth(token),
            )
        assert resp.json()["rules"]["pin"] == "hash"

    def test_put_mask_type_redact(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/input-mask",
                json={"rules": {"token": "redact"}},
                headers=_auth(token),
            )
        assert resp.json()["rules"]["token"] == "redact"

    def test_put_invalid_mask_type_422(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/input-mask",
                json={"rules": {"field": "encrypt"}},
                headers=_auth(token),
            )
        assert resp.status_code == 422

    def test_put_enabled_false(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/input-mask",
                json={"rules": {}, "enabled": False},
                headers=_auth(token),
            )
        assert resp.json()["enabled"] is False

    def test_put_empty_rules_allowed(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/input-mask",
                json={"rules": {}},
                headers=_auth(token),
            )
        assert resp.status_code == 200

    def test_put_replaces_existing(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_mask(client, token, flow_id, rules={"old_field": "full"})
            resp = client.put(
                f"/api/v1/flows/{flow_id}/input-mask",
                json={"rules": {"new_field": "partial"}},
                headers=_auth(token),
            )
        assert "new_field" in resp.json()["rules"]
        assert "old_field" not in resp.json()["rules"]

    def test_put_too_many_rules_422(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            rules = {f"field_{i}": "full" for i in range(51)}
            resp = client.put(
                f"/api/v1/flows/{flow_id}/input-mask",
                json={"rules": rules},
                headers=_auth(token),
            )
        assert resp.status_code == 422

    def test_put_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.put(
                "/api/v1/flows/nonexistent/input-mask",
                json={"rules": {}},
                headers=_auth(token),
            )
        assert resp.status_code == 404

    def test_put_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/input-mask",
                json={"rules": {}},
            )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Tests — GET /flows/{id}/input-mask
# ---------------------------------------------------------------------------


class TestFlowInputMaskGet:
    def test_get_returns_config_after_put(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_mask(client, token, flow_id, rules={"pw": "full"})
            resp = client.get(f"/api/v1/flows/{flow_id}/input-mask", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["rules"]["pw"] == "full"

    def test_get_404_when_no_config(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/input-mask", headers=_auth(token))
        assert resp.status_code == 404

    def test_get_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get("/api/v1/flows/nonexistent/input-mask", headers=_auth(token))
        assert resp.status_code == 404

    def test_get_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_mask(client, token, flow_id)
            resp = client.get(f"/api/v1/flows/{flow_id}/input-mask")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Tests — DELETE /flows/{id}/input-mask
# ---------------------------------------------------------------------------


class TestFlowInputMaskDelete:
    def test_delete_removes_config(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_mask(client, token, flow_id)
            resp = client.delete(f"/api/v1/flows/{flow_id}/input-mask", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True
        assert resp.json()["flow_id"] == flow_id

    def test_get_404_after_delete(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_mask(client, token, flow_id)
            client.delete(f"/api/v1/flows/{flow_id}/input-mask", headers=_auth(token))
            resp = client.get(f"/api/v1/flows/{flow_id}/input-mask", headers=_auth(token))
        assert resp.status_code == 404

    def test_delete_404_when_no_config(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.delete(f"/api/v1/flows/{flow_id}/input-mask", headers=_auth(token))
        assert resp.status_code == 404

    def test_delete_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.delete("/api/v1/flows/nonexistent/input-mask", headers=_auth(token))
        assert resp.status_code == 404

    def test_delete_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_mask(client, token, flow_id)
            resp = client.delete(f"/api/v1/flows/{flow_id}/input-mask")
        assert resp.status_code == 401
