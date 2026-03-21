"""
N-169: Flow Output Schema — PUT/GET/DELETE /flows/{id}/output-schema

Tests:
  - PUT defines schema; returns 200
  - PUT response shape (flow_id, schema, updated_at)
  - PUT empty schema object succeeds
  - PUT complex schema with nested properties
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
        json={"email": f"outschema-{uid}@test.com", "password": "pass1234"},
    )
    assert r.status_code == 201
    return r.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_flow(client: TestClient, token: str) -> str:
    resp = client.post(
        "/api/v1/flows",
        json={"name": "Output Schema Test Flow", "nodes": [], "edges": []},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


_SIMPLE_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "result": {"type": "string"},
        "status": {"type": "string", "enum": ["ok", "error"]},
    },
    "required": ["result", "status"],
}


def _set_output_schema(
    client: TestClient,
    token: str,
    flow_id: str,
    schema: dict | None = None,
) -> dict:
    resp = client.put(
        f"/api/v1/flows/{flow_id}/output-schema",
        json={"schema": schema if schema is not None else _SIMPLE_OUTPUT_SCHEMA},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    return resp.json()


# ---------------------------------------------------------------------------
# Tests — PUT /flows/{id}/output-schema
# ---------------------------------------------------------------------------


class TestFlowOutputSchemaPut:
    def test_put_returns_200(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/output-schema",
                json={"schema": _SIMPLE_OUTPUT_SCHEMA},
                headers=_auth(token),
            )
        assert resp.status_code == 200

    def test_put_response_shape(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/output-schema",
                json={"schema": _SIMPLE_OUTPUT_SCHEMA},
                headers=_auth(token),
            )
        data = resp.json()
        assert data["flow_id"] == flow_id
        assert data["schema"]["type"] == "object"
        assert "result" in data["schema"]["properties"]
        assert "updated_at" in data

    def test_put_empty_schema_succeeds(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/output-schema",
                json={"schema": {}},
                headers=_auth(token),
            )
        assert resp.status_code == 200
        assert resp.json()["schema"] == {}

    def test_put_complex_schema(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            nested = {
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "score": {"type": "number"},
                            },
                        },
                    },
                    "meta": {"type": "object"},
                },
            }
            resp = client.put(
                f"/api/v1/flows/{flow_id}/output-schema",
                json={"schema": nested},
                headers=_auth(token),
            )
        assert resp.status_code == 200
        assert resp.json()["schema"]["properties"]["items"]["type"] == "array"

    def test_put_replaces_existing_schema(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_output_schema(client, token, flow_id)
            new_schema = {"type": "object", "properties": {"value": {"type": "boolean"}}}
            resp = client.put(
                f"/api/v1/flows/{flow_id}/output-schema",
                json={"schema": new_schema},
                headers=_auth(token),
            )
        assert resp.json()["schema"] == new_schema

    def test_put_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.put(
                "/api/v1/flows/nonexistent/output-schema",
                json={"schema": {}},
                headers=_auth(token),
            )
        assert resp.status_code == 404

    def test_put_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/output-schema",
                json={"schema": {}},
            )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Tests — GET /flows/{id}/output-schema
# ---------------------------------------------------------------------------


class TestFlowOutputSchemaGet:
    def test_get_returns_schema_after_put(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_output_schema(client, token, flow_id, _SIMPLE_OUTPUT_SCHEMA)
            resp = client.get(f"/api/v1/flows/{flow_id}/output-schema", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["schema"]["required"] == ["result", "status"]

    def test_get_404_when_no_schema(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/output-schema", headers=_auth(token))
        assert resp.status_code == 404

    def test_get_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get("/api/v1/flows/nonexistent/output-schema", headers=_auth(token))
        assert resp.status_code == 404

    def test_get_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_output_schema(client, token, flow_id)
            resp = client.get(f"/api/v1/flows/{flow_id}/output-schema")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Tests — DELETE /flows/{id}/output-schema
# ---------------------------------------------------------------------------


class TestFlowOutputSchemaDelete:
    def test_delete_removes_schema(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_output_schema(client, token, flow_id)
            resp = client.delete(
                f"/api/v1/flows/{flow_id}/output-schema", headers=_auth(token)
            )
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True
        assert resp.json()["flow_id"] == flow_id

    def test_get_404_after_delete(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_output_schema(client, token, flow_id)
            client.delete(f"/api/v1/flows/{flow_id}/output-schema", headers=_auth(token))
            resp = client.get(f"/api/v1/flows/{flow_id}/output-schema", headers=_auth(token))
        assert resp.status_code == 404

    def test_delete_404_when_no_schema(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.delete(
                f"/api/v1/flows/{flow_id}/output-schema", headers=_auth(token)
            )
        assert resp.status_code == 404

    def test_delete_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.delete(
                "/api/v1/flows/nonexistent/output-schema", headers=_auth(token)
            )
        assert resp.status_code == 404

    def test_delete_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_output_schema(client, token, flow_id)
            resp = client.delete(f"/api/v1/flows/{flow_id}/output-schema")
        assert resp.status_code == 401
