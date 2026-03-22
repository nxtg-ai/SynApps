"""
N-175: Flow Trigger Configuration — PUT/GET/DELETE /flows/{id}/trigger-config

Tests:
  - PUT sets trigger config; returns 200
  - PUT response shape (flow_id, trigger_type, config, updated_at)
  - PUT trigger_type "manual" succeeds
  - PUT trigger_type "webhook" succeeds
  - PUT trigger_type "schedule" succeeds
  - PUT trigger_type "event" succeeds
  - PUT trigger_type "api" succeeds
  - PUT invalid trigger_type → 422
  - PUT replaces existing config
  - PUT with extra config dict stored
  - PUT 404 for unknown flow
  - PUT requires auth
  - GET returns config after PUT
  - GET 404 when no config set
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
        json={"email": f"trig-{uid}@test.com", "password": "pass1234"},
    )
    assert r.status_code == 201
    return r.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_flow(client: TestClient, token: str) -> str:
    resp = client.post(
        "/api/v1/flows",
        json={"name": "Trigger Config Test Flow", "nodes": [], "edges": []},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _set_trigger(
    client: TestClient,
    token: str,
    flow_id: str,
    trigger_type: str = "manual",
    config: dict | None = None,
) -> dict:
    resp = client.put(
        f"/api/v1/flows/{flow_id}/trigger-config",
        json={"trigger_type": trigger_type, "config": config or {}},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    return resp.json()


# ---------------------------------------------------------------------------
# Tests — PUT /flows/{id}/trigger-config
# ---------------------------------------------------------------------------


class TestFlowTriggerConfigPut:
    def test_put_returns_200(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/trigger-config",
                json={"trigger_type": "manual"},
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
                f"/api/v1/flows/{flow_id}/trigger-config",
                json={"trigger_type": "manual", "config": {}},
                headers=_auth(token),
            )
        data = resp.json()
        assert data["flow_id"] == flow_id
        assert data["trigger_type"] == "manual"
        assert "config" in data
        assert "updated_at" in data

    def test_put_trigger_manual(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/trigger-config",
                json={"trigger_type": "manual"},
                headers=_auth(token),
            )
        assert resp.json()["trigger_type"] == "manual"

    def test_put_trigger_webhook(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/trigger-config",
                json={"trigger_type": "webhook"},
                headers=_auth(token),
            )
        assert resp.json()["trigger_type"] == "webhook"

    def test_put_trigger_schedule(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/trigger-config",
                json={"trigger_type": "schedule"},
                headers=_auth(token),
            )
        assert resp.json()["trigger_type"] == "schedule"

    def test_put_trigger_event(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/trigger-config",
                json={"trigger_type": "event"},
                headers=_auth(token),
            )
        assert resp.json()["trigger_type"] == "event"

    def test_put_trigger_api(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/trigger-config",
                json={"trigger_type": "api"},
                headers=_auth(token),
            )
        assert resp.json()["trigger_type"] == "api"

    def test_put_invalid_trigger_type_422(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/trigger-config",
                json={"trigger_type": "cron_job"},
                headers=_auth(token),
            )
        assert resp.status_code == 422
        assert "error" in resp.json()

    def test_put_replaces_existing(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_trigger(client, token, flow_id, "manual")
            resp = client.put(
                f"/api/v1/flows/{flow_id}/trigger-config",
                json={"trigger_type": "webhook"},
                headers=_auth(token),
            )
        assert resp.json()["trigger_type"] == "webhook"

    def test_put_with_config_dict(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/trigger-config",
                json={"trigger_type": "schedule", "config": {"cron": "0 * * * *"}},
                headers=_auth(token),
            )
        assert resp.json()["config"]["cron"] == "0 * * * *"

    def test_put_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.put(
                "/api/v1/flows/nonexistent/trigger-config",
                json={"trigger_type": "manual"},
                headers=_auth(token),
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_put_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/trigger-config",
                json={"trigger_type": "manual"},
            )
        assert resp.status_code == 401
        assert "error" in resp.json()


# ---------------------------------------------------------------------------
# Tests — GET /flows/{id}/trigger-config
# ---------------------------------------------------------------------------


class TestFlowTriggerConfigGet:
    def test_get_returns_config_after_put(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_trigger(client, token, flow_id, "event")
            resp = client.get(f"/api/v1/flows/{flow_id}/trigger-config", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["trigger_type"] == "event"

    def test_get_404_when_no_config(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/trigger-config", headers=_auth(token))
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_get_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get(
                "/api/v1/flows/nonexistent/trigger-config", headers=_auth(token)
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_get_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_trigger(client, token, flow_id)
            resp = client.get(f"/api/v1/flows/{flow_id}/trigger-config")
        assert resp.status_code == 401
        assert "error" in resp.json()


# ---------------------------------------------------------------------------
# Tests — DELETE /flows/{id}/trigger-config
# ---------------------------------------------------------------------------


class TestFlowTriggerConfigDelete:
    def test_delete_removes_config(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_trigger(client, token, flow_id)
            resp = client.delete(
                f"/api/v1/flows/{flow_id}/trigger-config", headers=_auth(token)
            )
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True
        assert resp.json()["flow_id"] == flow_id

    def test_get_404_after_delete(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_trigger(client, token, flow_id)
            client.delete(f"/api/v1/flows/{flow_id}/trigger-config", headers=_auth(token))
            resp = client.get(f"/api/v1/flows/{flow_id}/trigger-config", headers=_auth(token))
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_delete_404_when_no_config(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.delete(
                f"/api/v1/flows/{flow_id}/trigger-config", headers=_auth(token)
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_delete_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.delete(
                "/api/v1/flows/nonexistent/trigger-config", headers=_auth(token)
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_delete_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_trigger(client, token, flow_id)
            resp = client.delete(f"/api/v1/flows/{flow_id}/trigger-config")
        assert resp.status_code == 401
        assert "error" in resp.json()
