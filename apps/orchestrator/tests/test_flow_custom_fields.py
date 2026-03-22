"""
N-161: Flow Custom Fields — POST  /flows/{id}/custom-fields (define schema)
                             GET   /flows/{id}/custom-fields
                             PUT   /flows/{id}/custom-fields/{name} (set value)
                             GET   /flows/{id}/custom-fields/{name}
                             DELETE /flows/{id}/custom-fields/{name}

Tests:
  - POST defines field; returns 201
  - POST response shape (flow_id, name, type)
  - POST invalid field name → 422
  - POST unknown type → 422
  - POST redefine existing field updates type
  - GET returns empty fields on fresh flow
  - GET lists all fields with values after define + set
  - GET returns allowed_types and flow_id
  - GET single field by name
  - GET single field 404 for undefined name
  - PUT sets string value
  - PUT sets number value
  - PUT sets boolean value
  - PUT sets date value (ISO format)
  - PUT wrong type for field → 422
  - PUT 404 for undefined field
  - DELETE removes field; returns {deleted: true}
  - DELETE 404 for undefined field
  - GET after DELETE shows empty
  - POST/GET 404 for unknown flow
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
        json={"email": f"cf-{uid}@test.com", "password": "pass1234"},
    )
    assert r.status_code == 201
    return r.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_flow(client: TestClient, token: str) -> str:
    resp = client.post(
        "/api/v1/flows",
        json={"name": "Custom Field Test Flow", "nodes": [], "edges": []},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _define_field(
    client: TestClient,
    token: str,
    flow_id: str,
    name: str = "project_code",
    field_type: str = "string",
) -> dict:
    resp = client.post(
        f"/api/v1/flows/{flow_id}/custom-fields",
        json={"name": name, "type": field_type},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    return resp.json()


# ---------------------------------------------------------------------------
# Tests — POST /flows/{id}/custom-fields
# ---------------------------------------------------------------------------


class TestFlowCustomFieldDefine:
    def test_post_returns_201(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/custom-fields",
                json={"name": "region", "type": "string"},
                headers=_auth(token),
            )
        assert resp.status_code == 201
        data = resp.json()
        assert data["flow_id"] == flow_id

    def test_post_response_shape(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/custom-fields",
                json={"name": "priority_score", "type": "number"},
                headers=_auth(token),
            )
        data = resp.json()
        assert data["flow_id"] == flow_id
        assert data["name"] == "priority_score"
        assert data["type"] == "number"

    def test_post_invalid_name_422(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/custom-fields",
                json={"name": "has spaces", "type": "string"},
                headers=_auth(token),
            )
        assert resp.status_code == 422
        assert "error" in resp.json()

    def test_post_unknown_type_422(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/custom-fields",
                json={"name": "my_field", "type": "json"},
                headers=_auth(token),
            )
        assert resp.status_code == 422
        assert "error" in resp.json()

    def test_post_redefine_updates_type(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _define_field(client, token, flow_id, "my_field", "string")
            resp = client.post(
                f"/api/v1/flows/{flow_id}/custom-fields",
                json={"name": "my_field", "type": "number"},
                headers=_auth(token),
            )
        assert resp.json()["type"] == "number"

    def test_post_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.post(
                "/api/v1/flows/nonexistent/custom-fields",
                json={"name": "x", "type": "string"},
                headers=_auth(token),
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_post_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/custom-fields",
                json={"name": "x", "type": "string"},
            )
        assert resp.status_code == 401
        assert "error" in resp.json()


# ---------------------------------------------------------------------------
# Tests — GET /flows/{id}/custom-fields
# ---------------------------------------------------------------------------


class TestFlowCustomFieldList:
    def test_get_empty_on_fresh_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/custom-fields", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["fields"] == []

    def test_get_lists_fields_with_values(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _define_field(client, token, flow_id, "code", "string")
            client.put(
                f"/api/v1/flows/{flow_id}/custom-fields/code",
                json={"value": "PROJ-42"},
                headers=_auth(token),
            )
            resp = client.get(f"/api/v1/flows/{flow_id}/custom-fields", headers=_auth(token))
        fields = resp.json()["fields"]
        assert len(fields) == 1
        assert fields[0]["name"] == "code"
        assert fields[0]["value"] == "PROJ-42"

    def test_get_response_has_allowed_types(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/custom-fields", headers=_auth(token))
        assert len(resp.json()["allowed_types"]) == 4

    def test_get_flow_id_in_response(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/custom-fields", headers=_auth(token))
        assert resp.json()["flow_id"] == flow_id

    def test_get_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get("/api/v1/flows/nonexistent/custom-fields", headers=_auth(token))
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_get_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/custom-fields")
        assert resp.status_code == 401
        assert "error" in resp.json()


# ---------------------------------------------------------------------------
# Tests — PUT /flows/{id}/custom-fields/{name}  (set value)
# ---------------------------------------------------------------------------


class TestFlowCustomFieldSetValue:
    def test_set_string_value(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _define_field(client, token, flow_id, "label", "string")
            resp = client.put(
                f"/api/v1/flows/{flow_id}/custom-fields/label",
                json={"value": "production"},
                headers=_auth(token),
            )
        assert resp.status_code == 200
        assert resp.json()["value"] == "production"

    def test_set_number_value(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _define_field(client, token, flow_id, "score", "number")
            resp = client.put(
                f"/api/v1/flows/{flow_id}/custom-fields/score",
                json={"value": 9.5},
                headers=_auth(token),
            )
        assert resp.json()["value"] == 9.5

    def test_set_boolean_value(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _define_field(client, token, flow_id, "active", "boolean")
            resp = client.put(
                f"/api/v1/flows/{flow_id}/custom-fields/active",
                json={"value": True},
                headers=_auth(token),
            )
        assert resp.json()["value"] is True

    def test_set_date_value(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _define_field(client, token, flow_id, "due_date", "date")
            resp = client.put(
                f"/api/v1/flows/{flow_id}/custom-fields/due_date",
                json={"value": "2026-12-31"},
                headers=_auth(token),
            )
        assert resp.json()["value"] == "2026-12-31"

    def test_set_wrong_type_422(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _define_field(client, token, flow_id, "score", "number")
            resp = client.put(
                f"/api/v1/flows/{flow_id}/custom-fields/score",
                json={"value": "not-a-number"},
                headers=_auth(token),
            )
        assert resp.status_code == 422
        assert "error" in resp.json()

    def test_set_undefined_field_404(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/custom-fields/undefined_field",
                json={"value": "x"},
                headers=_auth(token),
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_set_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _define_field(client, token, flow_id, "x", "string")
            resp = client.put(
                f"/api/v1/flows/{flow_id}/custom-fields/x",
                json={"value": "y"},
            )
        assert resp.status_code == 401
        assert "error" in resp.json()


# ---------------------------------------------------------------------------
# Tests — GET /flows/{id}/custom-fields/{name}
# ---------------------------------------------------------------------------


class TestFlowCustomFieldGetOne:
    def test_get_single_field(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _define_field(client, token, flow_id, "region", "string")
            resp = client.get(
                f"/api/v1/flows/{flow_id}/custom-fields/region", headers=_auth(token)
            )
        assert resp.status_code == 200
        assert resp.json()["name"] == "region"
        assert resp.json()["type"] == "string"

    def test_get_single_404_undefined(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(
                f"/api/v1/flows/{flow_id}/custom-fields/nonexistent", headers=_auth(token)
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_get_single_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _define_field(client, token, flow_id, "x", "string")
            resp = client.get(f"/api/v1/flows/{flow_id}/custom-fields/x")
        assert resp.status_code == 401
        assert "error" in resp.json()


# ---------------------------------------------------------------------------
# Tests — DELETE /flows/{id}/custom-fields/{name}
# ---------------------------------------------------------------------------


class TestFlowCustomFieldDelete:
    def test_delete_removes_field(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _define_field(client, token, flow_id, "temp", "string")
            resp = client.delete(
                f"/api/v1/flows/{flow_id}/custom-fields/temp", headers=_auth(token)
            )
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True
        assert resp.json()["name"] == "temp"

    def test_get_after_delete_shows_empty(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _define_field(client, token, flow_id, "temp", "string")
            client.delete(
                f"/api/v1/flows/{flow_id}/custom-fields/temp", headers=_auth(token)
            )
            resp = client.get(f"/api/v1/flows/{flow_id}/custom-fields", headers=_auth(token))
        assert resp.json()["fields"] == []

    def test_delete_404_undefined_field(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.delete(
                f"/api/v1/flows/{flow_id}/custom-fields/nonexistent", headers=_auth(token)
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_delete_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.delete(
                "/api/v1/flows/nonexistent/custom-fields/x", headers=_auth(token)
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_delete_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _define_field(client, token, flow_id, "x", "string")
            resp = client.delete(f"/api/v1/flows/{flow_id}/custom-fields/x")
        assert resp.status_code == 401
        assert "error" in resp.json()
