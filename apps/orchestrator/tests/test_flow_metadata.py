"""
N-146: Flow Metadata — GET/PUT/PATCH /api/v1/flows/{flow_id}/metadata
                        DELETE /api/v1/flows/{flow_id}/metadata/{key}

Tests:
  - GET returns empty dict on fresh flow
  - PUT replaces metadata; GET returns it
  - PATCH merges new keys into existing
  - PATCH does not overwrite keys not in the update
  - DELETE /metadata/{key} removes one key
  - DELETE /metadata/{key} on missing key → 404
  - PUT with too many keys (>50) → 422
  - PUT with key too long (>100 chars) → 422
  - Values can be strings, numbers, booleans, lists, dicts
  - 404 for unknown flow on all endpoints
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
        json={"email": f"meta-{uid}@test.com", "password": "pass1234"},
    )
    assert r.status_code == 201
    return r.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_flow(client: TestClient, token: str) -> str:
    resp = client.post(
        "/api/v1/flows",
        json={"name": "Metadata Test Flow", "nodes": [], "edges": []},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestFlowMetadataGet:
    def test_empty_on_fresh_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/metadata", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["metadata"] == {}

    def test_flow_id_in_response(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/metadata", headers=_auth(token))
        assert resp.json()["flow_id"] == flow_id

    def test_get_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get("/api/v1/flows/nonexistent/metadata", headers=_auth(token))
        assert resp.status_code == 404

    def test_get_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/metadata")
        assert resp.status_code == 401


class TestFlowMetadataPut:
    def test_put_returns_200(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/metadata",
                json={"metadata": {"env": "prod"}},
                headers=_auth(token),
            )
        assert resp.status_code == 200

    def test_put_stores_metadata(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            client.put(
                f"/api/v1/flows/{flow_id}/metadata",
                json={"metadata": {"env": "prod", "version": 2}},
                headers=_auth(token),
            )
            resp = client.get(f"/api/v1/flows/{flow_id}/metadata", headers=_auth(token))
        meta = resp.json()["metadata"]
        assert meta["env"] == "prod"
        assert meta["version"] == 2

    def test_put_replaces_existing(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            client.put(
                f"/api/v1/flows/{flow_id}/metadata",
                json={"metadata": {"old_key": "old_value"}},
                headers=_auth(token),
            )
            client.put(
                f"/api/v1/flows/{flow_id}/metadata",
                json={"metadata": {"new_key": "new_value"}},
                headers=_auth(token),
            )
            resp = client.get(f"/api/v1/flows/{flow_id}/metadata", headers=_auth(token))
        meta = resp.json()["metadata"]
        assert "old_key" not in meta
        assert meta["new_key"] == "new_value"

    def test_put_accepts_various_value_types(self):
        meta = {
            "str_val": "hello",
            "int_val": 42,
            "bool_val": True,
            "list_val": [1, 2, 3],
            "dict_val": {"nested": "yes"},
        }
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/metadata",
                json={"metadata": meta},
                headers=_auth(token),
            )
        assert resp.json()["metadata"] == meta

    def test_put_too_many_keys_422(self):
        oversized = {f"key_{i}": i for i in range(51)}
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/metadata",
                json={"metadata": oversized},
                headers=_auth(token),
            )
        assert resp.status_code == 422

    def test_put_key_too_long_422(self):
        long_key = "k" * 101
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/metadata",
                json={"metadata": {long_key: "v"}},
                headers=_auth(token),
            )
        assert resp.status_code == 422

    def test_put_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.put(
                "/api/v1/flows/nonexistent/metadata",
                json={"metadata": {"k": "v"}},
                headers=_auth(token),
            )
        assert resp.status_code == 404

    def test_put_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/metadata",
                json={"metadata": {"k": "v"}},
            )
        assert resp.status_code == 401


class TestFlowMetadataPatch:
    def test_patch_merges_keys(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            client.put(
                f"/api/v1/flows/{flow_id}/metadata",
                json={"metadata": {"a": 1}},
                headers=_auth(token),
            )
            resp = client.patch(
                f"/api/v1/flows/{flow_id}/metadata",
                json={"metadata": {"b": 2}},
                headers=_auth(token),
            )
        meta = resp.json()["metadata"]
        assert meta["a"] == 1
        assert meta["b"] == 2

    def test_patch_overwrites_existing_key(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            client.put(
                f"/api/v1/flows/{flow_id}/metadata",
                json={"metadata": {"x": "old"}},
                headers=_auth(token),
            )
            resp = client.patch(
                f"/api/v1/flows/{flow_id}/metadata",
                json={"metadata": {"x": "new"}},
                headers=_auth(token),
            )
        assert resp.json()["metadata"]["x"] == "new"

    def test_patch_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.patch(
                "/api/v1/flows/nonexistent/metadata",
                json={"metadata": {"k": "v"}},
                headers=_auth(token),
            )
        assert resp.status_code == 404

    def test_patch_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.patch(
                f"/api/v1/flows/{flow_id}/metadata",
                json={"metadata": {"k": "v"}},
            )
        assert resp.status_code == 401


class TestFlowMetadataDeleteKey:
    def test_delete_key_removes_it(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            client.put(
                f"/api/v1/flows/{flow_id}/metadata",
                json={"metadata": {"keep": 1, "remove": 2}},
                headers=_auth(token),
            )
            client.delete(f"/api/v1/flows/{flow_id}/metadata/remove", headers=_auth(token))
            resp = client.get(f"/api/v1/flows/{flow_id}/metadata", headers=_auth(token))
        meta = resp.json()["metadata"]
        assert "remove" not in meta
        assert meta["keep"] == 1

    def test_delete_key_returns_remaining(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            client.put(
                f"/api/v1/flows/{flow_id}/metadata",
                json={"metadata": {"a": 1, "b": 2}},
                headers=_auth(token),
            )
            resp = client.delete(f"/api/v1/flows/{flow_id}/metadata/a", headers=_auth(token))
        assert resp.json()["deleted_key"] == "a"
        assert "b" in resp.json()["metadata"]

    def test_delete_missing_key_404(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.delete(
                f"/api/v1/flows/{flow_id}/metadata/nonexistent", headers=_auth(token)
            )
        assert resp.status_code == 404

    def test_delete_key_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.delete("/api/v1/flows/nonexistent/metadata/somekey", headers=_auth(token))
        assert resp.status_code == 404

    def test_delete_key_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            client.put(
                f"/api/v1/flows/{flow_id}/metadata",
                json={"metadata": {"k": "v"}},
                headers=_auth(token),
            )
            resp = client.delete(f"/api/v1/flows/{flow_id}/metadata/k")
        assert resp.status_code == 401
