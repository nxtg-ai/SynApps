"""
N-178: Flow Output Destination — PUT/GET/DELETE /flows/{id}/output-destination

Tests:
  - PUT sets destination; returns 200
  - PUT response shape (flow_id, dest_type, config, updated_at)
  - PUT dest_type "webhook" succeeds
  - PUT dest_type "s3" succeeds
  - PUT dest_type "database" succeeds
  - PUT dest_type "file" succeeds
  - PUT dest_type "none" succeeds
  - PUT invalid dest_type → 422
  - PUT replaces existing destination
  - PUT with config dict stored
  - PUT 404 for unknown flow
  - PUT requires auth
  - GET returns destination after PUT
  - GET 404 when no destination
  - GET 404 for unknown flow
  - GET requires auth
  - DELETE removes destination; returns {deleted: true, flow_id}
  - DELETE 404 when no destination
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
        json={"email": f"outdest-{uid}@test.com", "password": "pass1234"},
    )
    assert r.status_code == 201
    return r.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_flow(client: TestClient, token: str) -> str:
    resp = client.post(
        "/api/v1/flows",
        json={"name": "Output Destination Test Flow", "nodes": [], "edges": []},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _set_destination(
    client: TestClient,
    token: str,
    flow_id: str,
    dest_type: str = "none",
    config: dict | None = None,
) -> dict:
    resp = client.put(
        f"/api/v1/flows/{flow_id}/output-destination",
        json={"dest_type": dest_type, "config": config or {}},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    return resp.json()


# ---------------------------------------------------------------------------
# Tests — PUT /flows/{id}/output-destination
# ---------------------------------------------------------------------------


class TestFlowOutputDestinationPut:
    def test_put_returns_200(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/output-destination",
                json={"dest_type": "none"},
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
                f"/api/v1/flows/{flow_id}/output-destination",
                json={"dest_type": "webhook"},
                headers=_auth(token),
            )
        data = resp.json()
        assert data["flow_id"] == flow_id
        assert data["dest_type"] == "webhook"
        assert "config" in data
        assert "updated_at" in data

    def test_put_webhook(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/output-destination",
                json={"dest_type": "webhook"},
                headers=_auth(token),
            )
        assert resp.json()["dest_type"] == "webhook"

    def test_put_s3(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/output-destination",
                json={"dest_type": "s3"},
                headers=_auth(token),
            )
        assert resp.json()["dest_type"] == "s3"

    def test_put_database(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/output-destination",
                json={"dest_type": "database"},
                headers=_auth(token),
            )
        assert resp.json()["dest_type"] == "database"

    def test_put_file(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/output-destination",
                json={"dest_type": "file"},
                headers=_auth(token),
            )
        assert resp.json()["dest_type"] == "file"

    def test_put_none(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/output-destination",
                json={"dest_type": "none"},
                headers=_auth(token),
            )
        assert resp.json()["dest_type"] == "none"

    def test_put_invalid_dest_type_422(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/output-destination",
                json={"dest_type": "kafka"},
                headers=_auth(token),
            )
        assert resp.status_code == 422
        assert "error" in resp.json()

    def test_put_replaces_existing(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_destination(client, token, flow_id, "none")
            resp = client.put(
                f"/api/v1/flows/{flow_id}/output-destination",
                json={"dest_type": "s3"},
                headers=_auth(token),
            )
        assert resp.json()["dest_type"] == "s3"

    def test_put_with_config_dict(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/output-destination",
                json={"dest_type": "s3", "config": {"bucket": "my-bucket"}},
                headers=_auth(token),
            )
        assert resp.json()["config"]["bucket"] == "my-bucket"

    def test_put_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.put(
                "/api/v1/flows/nonexistent/output-destination",
                json={"dest_type": "none"},
                headers=_auth(token),
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_put_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/output-destination",
                json={"dest_type": "none"},
            )
        assert resp.status_code == 401
        assert "error" in resp.json()


# ---------------------------------------------------------------------------
# Tests — GET /flows/{id}/output-destination
# ---------------------------------------------------------------------------


class TestFlowOutputDestinationGet:
    def test_get_returns_destination_after_put(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_destination(client, token, flow_id, "database")
            resp = client.get(
                f"/api/v1/flows/{flow_id}/output-destination", headers=_auth(token)
            )
        assert resp.status_code == 200
        assert resp.json()["dest_type"] == "database"

    def test_get_404_when_no_destination(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(
                f"/api/v1/flows/{flow_id}/output-destination", headers=_auth(token)
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_get_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get(
                "/api/v1/flows/nonexistent/output-destination", headers=_auth(token)
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_get_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_destination(client, token, flow_id)
            resp = client.get(f"/api/v1/flows/{flow_id}/output-destination")
        assert resp.status_code == 401
        assert "error" in resp.json()


# ---------------------------------------------------------------------------
# Tests — DELETE /flows/{id}/output-destination
# ---------------------------------------------------------------------------


class TestFlowOutputDestinationDelete:
    def test_delete_removes_destination(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_destination(client, token, flow_id)
            resp = client.delete(
                f"/api/v1/flows/{flow_id}/output-destination", headers=_auth(token)
            )
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True
        assert resp.json()["flow_id"] == flow_id

    def test_get_404_after_delete(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_destination(client, token, flow_id)
            client.delete(f"/api/v1/flows/{flow_id}/output-destination", headers=_auth(token))
            resp = client.get(
                f"/api/v1/flows/{flow_id}/output-destination", headers=_auth(token)
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_delete_404_when_no_destination(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.delete(
                f"/api/v1/flows/{flow_id}/output-destination", headers=_auth(token)
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_delete_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.delete(
                "/api/v1/flows/nonexistent/output-destination", headers=_auth(token)
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_delete_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_destination(client, token, flow_id)
            resp = client.delete(f"/api/v1/flows/{flow_id}/output-destination")
        assert resp.status_code == 401
        assert "error" in resp.json()
