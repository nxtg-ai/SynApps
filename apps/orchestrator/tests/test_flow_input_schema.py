"""
N-168: Flow Input Schema — PUT/GET/DELETE /flows/{id}/input-schema

Tests:
  - PUT defines schema; returns 200
  - PUT response shape (flow_id, schema, updated_at)
  - PUT empty schema object succeeds
  - PUT complex nested schema succeeds
  - PUT replaces existing schema
  - PUT 404 for unknown flow
  - PUT requires auth
  - GET returns schema after PUT
  - GET 404 when no schema defined
  - GET 404 for unknown flow
  - GET requires auth
  - DELETE removes schema; returns {deleted: true, flow_id}
  - DELETE 404 when no schema defined
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
        json={"email": f"schema-{uid}@test.com", "password": "pass1234"},
    )
    assert r.status_code == 201
    return r.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_flow(client: TestClient, token: str) -> str:
    resp = client.post(
        "/api/v1/flows",
        json={"name": "Input Schema Test Flow", "nodes": [], "edges": []},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


_SIMPLE_SCHEMA = {
    "type": "object",
    "properties": {
        "message": {"type": "string"},
        "count": {"type": "integer"},
    },
    "required": ["message"],
}


def _set_schema(
    client: TestClient,
    token: str,
    flow_id: str,
    schema: dict | None = None,
) -> dict:
    resp = client.put(
        f"/api/v1/flows/{flow_id}/input-schema",
        json={"schema": schema if schema is not None else _SIMPLE_SCHEMA},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    return resp.json()


# ---------------------------------------------------------------------------
# Tests — PUT /flows/{id}/input-schema
# ---------------------------------------------------------------------------


class TestFlowInputSchemaPut:
    def test_put_returns_200(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/input-schema",
                json={"schema": _SIMPLE_SCHEMA},
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
                f"/api/v1/flows/{flow_id}/input-schema",
                json={"schema": _SIMPLE_SCHEMA},
                headers=_auth(token),
            )
        data = resp.json()
        assert data["flow_id"] == flow_id
        assert data["schema"]["type"] == "object"
        assert "updated_at" in data

    def test_put_empty_schema_succeeds(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/input-schema",
                json={"schema": {}},
                headers=_auth(token),
            )
        assert resp.status_code == 200
        assert resp.json()["schema"] == {}

    def test_put_complex_nested_schema(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            nested = {
                "type": "object",
                "properties": {
                    "user": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "age": {"type": "integer", "minimum": 0},
                        },
                    },
                    "tags": {"type": "array", "items": {"type": "string"}},
                },
            }
            resp = client.put(
                f"/api/v1/flows/{flow_id}/input-schema",
                json={"schema": nested},
                headers=_auth(token),
            )
        assert resp.status_code == 200
        assert resp.json()["schema"]["properties"]["user"]["type"] == "object"

    def test_put_replaces_existing_schema(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_schema(client, token, flow_id)
            new_schema = {"type": "object", "properties": {"value": {"type": "number"}}}
            resp = client.put(
                f"/api/v1/flows/{flow_id}/input-schema",
                json={"schema": new_schema},
                headers=_auth(token),
            )
        assert resp.json()["schema"] == new_schema

    def test_put_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.put(
                "/api/v1/flows/nonexistent/input-schema",
                json={"schema": {}},
                headers=_auth(token),
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_put_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/input-schema",
                json={"schema": {}},
            )
        assert resp.status_code == 401
        assert "error" in resp.json()


# ---------------------------------------------------------------------------
# Tests — GET /flows/{id}/input-schema
# ---------------------------------------------------------------------------


class TestFlowInputSchemaGet:
    def test_get_returns_schema_after_put(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_schema(client, token, flow_id, _SIMPLE_SCHEMA)
            resp = client.get(f"/api/v1/flows/{flow_id}/input-schema", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["schema"]["required"] == ["message"]

    def test_get_404_when_no_schema(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/input-schema", headers=_auth(token))
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_get_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get("/api/v1/flows/nonexistent/input-schema", headers=_auth(token))
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_get_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_schema(client, token, flow_id)
            resp = client.get(f"/api/v1/flows/{flow_id}/input-schema")
        assert resp.status_code == 401
        assert "error" in resp.json()


# ---------------------------------------------------------------------------
# Tests — DELETE /flows/{id}/input-schema
# ---------------------------------------------------------------------------


class TestFlowInputSchemaDelete:
    def test_delete_removes_schema(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_schema(client, token, flow_id)
            resp = client.delete(f"/api/v1/flows/{flow_id}/input-schema", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True
        assert resp.json()["flow_id"] == flow_id

    def test_get_404_after_delete(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_schema(client, token, flow_id)
            client.delete(f"/api/v1/flows/{flow_id}/input-schema", headers=_auth(token))
            resp = client.get(f"/api/v1/flows/{flow_id}/input-schema", headers=_auth(token))
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_delete_404_when_no_schema(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.delete(f"/api/v1/flows/{flow_id}/input-schema", headers=_auth(token))
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_delete_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.delete(
                "/api/v1/flows/nonexistent/input-schema", headers=_auth(token)
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_delete_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_schema(client, token, flow_id)
            resp = client.delete(f"/api/v1/flows/{flow_id}/input-schema")
        assert resp.status_code == 401
        assert "error" in resp.json()
