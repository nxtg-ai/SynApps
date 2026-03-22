"""
N-198: Flow Output Transform — PUT/GET/DELETE /flows/{id}/output-transform

Tests:
  - PUT sets transform config; returns 200
  - PUT response shape (flow_id, expression, output_format, enabled, updated_at)
  - PUT expression stored
  - PUT format json stored
  - PUT format xml stored
  - PUT format csv stored
  - PUT format text stored
  - PUT invalid format → 422
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
        json={"email": f"outtrans-{uid}@test.com", "password": "pass1234"},
    )
    assert r.status_code == 201
    return r.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_flow(client: TestClient, token: str) -> str:
    resp = client.post(
        "/api/v1/flows",
        json={"name": "Output Transform Test Flow", "nodes": [], "edges": []},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _set_transform(
    client: TestClient,
    token: str,
    flow_id: str,
    expression: str = ".result",
    output_format: str = "json",
    enabled: bool = True,
) -> dict:
    resp = client.put(
        f"/api/v1/flows/{flow_id}/output-transform",
        json={"expression": expression, "output_format": output_format, "enabled": enabled},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    return resp.json()


# ---------------------------------------------------------------------------
# Tests — PUT /flows/{id}/output-transform
# ---------------------------------------------------------------------------


class TestFlowOutputTransformPut:
    def test_put_returns_200(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/output-transform",
                json={"expression": ".data", "output_format": "json"},
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
                f"/api/v1/flows/{flow_id}/output-transform",
                json={"expression": ".out", "output_format": "xml"},
                headers=_auth(token),
            )
        data = resp.json()
        assert data["flow_id"] == flow_id
        assert "expression" in data
        assert "output_format" in data
        assert "enabled" in data
        assert "updated_at" in data

    def test_put_expression_stored(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/output-transform",
                json={"expression": ".items[] | .name", "output_format": "json"},
                headers=_auth(token),
            )
        assert resp.json()["expression"] == ".items[] | .name"

    def test_put_format_json(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/output-transform",
                json={"expression": ".x", "output_format": "json"},
                headers=_auth(token),
            )
        assert resp.json()["output_format"] == "json"

    def test_put_format_xml(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/output-transform",
                json={"expression": ".x", "output_format": "xml"},
                headers=_auth(token),
            )
        assert resp.json()["output_format"] == "xml"

    def test_put_format_csv(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/output-transform",
                json={"expression": ".x", "output_format": "csv"},
                headers=_auth(token),
            )
        assert resp.json()["output_format"] == "csv"

    def test_put_format_text(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/output-transform",
                json={"expression": ".x", "output_format": "text"},
                headers=_auth(token),
            )
        assert resp.json()["output_format"] == "text"

    def test_put_invalid_format_422(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/output-transform",
                json={"expression": ".x", "output_format": "yaml"},
                headers=_auth(token),
            )
        assert resp.status_code == 422
        assert "error" in resp.json()

    def test_put_enabled_false(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/output-transform",
                json={"expression": ".x", "output_format": "json", "enabled": False},
                headers=_auth(token),
            )
        assert resp.json()["enabled"] is False

    def test_put_replaces_existing(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_transform(client, token, flow_id, expression=".old", output_format="csv")
            resp = client.put(
                f"/api/v1/flows/{flow_id}/output-transform",
                json={"expression": ".new", "output_format": "json"},
                headers=_auth(token),
            )
        assert resp.json()["expression"] == ".new"
        assert resp.json()["output_format"] == "json"

    def test_put_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.put(
                "/api/v1/flows/nonexistent/output-transform",
                json={"expression": ".x", "output_format": "json"},
                headers=_auth(token),
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_put_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/output-transform",
                json={"expression": ".x", "output_format": "json"},
            )
        assert resp.status_code == 401
        assert "error" in resp.json()


# ---------------------------------------------------------------------------
# Tests — GET /flows/{id}/output-transform
# ---------------------------------------------------------------------------


class TestFlowOutputTransformGet:
    def test_get_returns_config_after_put(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_transform(client, token, flow_id, expression=".result", output_format="xml")
            resp = client.get(f"/api/v1/flows/{flow_id}/output-transform", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["expression"] == ".result"
        assert resp.json()["output_format"] == "xml"

    def test_get_404_when_no_config(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/output-transform", headers=_auth(token))
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_get_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get("/api/v1/flows/nonexistent/output-transform", headers=_auth(token))
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_get_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_transform(client, token, flow_id)
            resp = client.get(f"/api/v1/flows/{flow_id}/output-transform")
        assert resp.status_code == 401
        assert "error" in resp.json()


# ---------------------------------------------------------------------------
# Tests — DELETE /flows/{id}/output-transform
# ---------------------------------------------------------------------------


class TestFlowOutputTransformDelete:
    def test_delete_removes_config(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_transform(client, token, flow_id)
            resp = client.delete(
                f"/api/v1/flows/{flow_id}/output-transform", headers=_auth(token)
            )
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True
        assert resp.json()["flow_id"] == flow_id

    def test_get_404_after_delete(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_transform(client, token, flow_id)
            client.delete(f"/api/v1/flows/{flow_id}/output-transform", headers=_auth(token))
            resp = client.get(f"/api/v1/flows/{flow_id}/output-transform", headers=_auth(token))
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_delete_404_when_no_config(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.delete(
                f"/api/v1/flows/{flow_id}/output-transform", headers=_auth(token)
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_delete_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.delete(
                "/api/v1/flows/nonexistent/output-transform", headers=_auth(token)
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_delete_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_transform(client, token, flow_id)
            resp = client.delete(f"/api/v1/flows/{flow_id}/output-transform")
        assert resp.status_code == 401
        assert "error" in resp.json()
