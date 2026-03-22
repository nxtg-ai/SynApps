"""
N-181: Flow Execution Mode — PUT/GET/DELETE /flows/{id}/execution-mode

Tests:
  - PUT sets mode; returns 200
  - PUT response shape (flow_id, mode, debug, updated_at)
  - PUT mode "async" succeeds
  - PUT mode "sync" succeeds
  - PUT mode "dry_run" succeeds
  - PUT invalid mode → 422
  - PUT debug=True stored
  - PUT debug=False stored
  - PUT replaces existing mode
  - PUT 404 for unknown flow
  - PUT requires auth
  - GET returns mode after PUT
  - GET 404 when no mode set
  - GET 404 for unknown flow
  - GET requires auth
  - DELETE removes mode; returns {deleted: true, flow_id}
  - DELETE 404 when no mode
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
        json={"email": f"execmode-{uid}@test.com", "password": "pass1234"},
    )
    assert r.status_code == 201
    return r.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_flow(client: TestClient, token: str) -> str:
    resp = client.post(
        "/api/v1/flows",
        json={"name": "Execution Mode Test Flow", "nodes": [], "edges": []},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _set_mode(
    client: TestClient,
    token: str,
    flow_id: str,
    mode: str = "async",
    debug: bool = False,
) -> dict:
    resp = client.put(
        f"/api/v1/flows/{flow_id}/execution-mode",
        json={"mode": mode, "debug": debug},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    return resp.json()


# ---------------------------------------------------------------------------
# Tests — PUT /flows/{id}/execution-mode
# ---------------------------------------------------------------------------


class TestFlowExecutionModePut:
    def test_put_returns_200(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/execution-mode",
                json={"mode": "async"},
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
                f"/api/v1/flows/{flow_id}/execution-mode",
                json={"mode": "sync", "debug": False},
                headers=_auth(token),
            )
        data = resp.json()
        assert data["flow_id"] == flow_id
        assert data["mode"] == "sync"
        assert "debug" in data
        assert "updated_at" in data

    def test_put_async_mode(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/execution-mode",
                json={"mode": "async"},
                headers=_auth(token),
            )
        assert resp.json()["mode"] == "async"

    def test_put_sync_mode(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/execution-mode",
                json={"mode": "sync"},
                headers=_auth(token),
            )
        assert resp.json()["mode"] == "sync"

    def test_put_dry_run_mode(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/execution-mode",
                json={"mode": "dry_run"},
                headers=_auth(token),
            )
        assert resp.json()["mode"] == "dry_run"

    def test_put_invalid_mode_422(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/execution-mode",
                json={"mode": "turbo"},
                headers=_auth(token),
            )
        assert resp.status_code == 422
        assert "error" in resp.json()

    def test_put_debug_true(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/execution-mode",
                json={"mode": "async", "debug": True},
                headers=_auth(token),
            )
        assert resp.json()["debug"] is True

    def test_put_debug_false(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/execution-mode",
                json={"mode": "async", "debug": False},
                headers=_auth(token),
            )
        assert resp.json()["debug"] is False

    def test_put_replaces_existing(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_mode(client, token, flow_id, "async")
            resp = client.put(
                f"/api/v1/flows/{flow_id}/execution-mode",
                json={"mode": "dry_run"},
                headers=_auth(token),
            )
        assert resp.json()["mode"] == "dry_run"

    def test_put_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.put(
                "/api/v1/flows/nonexistent/execution-mode",
                json={"mode": "async"},
                headers=_auth(token),
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_put_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/execution-mode",
                json={"mode": "async"},
            )
        assert resp.status_code == 401
        assert "error" in resp.json()


# ---------------------------------------------------------------------------
# Tests — GET /flows/{id}/execution-mode
# ---------------------------------------------------------------------------


class TestFlowExecutionModeGet:
    def test_get_returns_mode_after_put(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_mode(client, token, flow_id, "sync", debug=True)
            resp = client.get(
                f"/api/v1/flows/{flow_id}/execution-mode", headers=_auth(token)
            )
        assert resp.status_code == 200
        assert resp.json()["mode"] == "sync"
        assert resp.json()["debug"] is True

    def test_get_404_when_no_mode(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(
                f"/api/v1/flows/{flow_id}/execution-mode", headers=_auth(token)
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_get_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get(
                "/api/v1/flows/nonexistent/execution-mode", headers=_auth(token)
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_get_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_mode(client, token, flow_id)
            resp = client.get(f"/api/v1/flows/{flow_id}/execution-mode")
        assert resp.status_code == 401
        assert "error" in resp.json()


# ---------------------------------------------------------------------------
# Tests — DELETE /flows/{id}/execution-mode
# ---------------------------------------------------------------------------


class TestFlowExecutionModeDelete:
    def test_delete_removes_mode(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_mode(client, token, flow_id)
            resp = client.delete(
                f"/api/v1/flows/{flow_id}/execution-mode", headers=_auth(token)
            )
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True
        assert resp.json()["flow_id"] == flow_id

    def test_get_404_after_delete(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_mode(client, token, flow_id)
            client.delete(f"/api/v1/flows/{flow_id}/execution-mode", headers=_auth(token))
            resp = client.get(f"/api/v1/flows/{flow_id}/execution-mode", headers=_auth(token))
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_delete_404_when_no_mode(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.delete(
                f"/api/v1/flows/{flow_id}/execution-mode", headers=_auth(token)
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_delete_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.delete(
                "/api/v1/flows/nonexistent/execution-mode", headers=_auth(token)
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_delete_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_mode(client, token, flow_id)
            resp = client.delete(f"/api/v1/flows/{flow_id}/execution-mode")
        assert resp.status_code == 401
        assert "error" in resp.json()
