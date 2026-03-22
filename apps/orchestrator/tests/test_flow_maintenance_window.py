"""
N-186: Flow Maintenance Window — PUT/GET/DELETE /flows/{id}/maintenance-window

Tests:
  - PUT sets maintenance window; returns 200
  - PUT response shape (flow_id, start, end, reason, active, updated_at)
  - PUT with start and end stored
  - PUT with reason stored
  - PUT without reason defaults empty
  - PUT reason too long → 422
  - PUT replaces existing window
  - PUT active field is True on creation
  - PUT 404 for unknown flow
  - PUT requires auth
  - GET returns window after PUT
  - GET 404 when no window
  - GET 404 for unknown flow
  - GET requires auth
  - DELETE removes window; returns {deleted: true, flow_id}
  - DELETE 404 when no window
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
        json={"email": f"maint-{uid}@test.com", "password": "pass1234"},
    )
    assert r.status_code == 201
    return r.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_flow(client: TestClient, token: str) -> str:
    resp = client.post(
        "/api/v1/flows",
        json={"name": "Maintenance Window Test Flow", "nodes": [], "edges": []},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _set_window(
    client: TestClient,
    token: str,
    flow_id: str,
    start: str = "2026-04-01T00:00:00Z",
    end: str = "2026-04-01T02:00:00Z",
    reason: str = "",
) -> dict:
    resp = client.put(
        f"/api/v1/flows/{flow_id}/maintenance-window",
        json={"start": start, "end": end, "reason": reason},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    return resp.json()


# ---------------------------------------------------------------------------
# Tests — PUT /flows/{id}/maintenance-window
# ---------------------------------------------------------------------------


class TestFlowMaintenanceWindowPut:
    def test_put_returns_200(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/maintenance-window",
                json={"start": "2026-05-01T00:00:00Z", "end": "2026-05-01T04:00:00Z"},
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
                f"/api/v1/flows/{flow_id}/maintenance-window",
                json={"start": "2026-05-01T00:00:00Z", "end": "2026-05-01T04:00:00Z"},
                headers=_auth(token),
            )
        data = resp.json()
        assert data["flow_id"] == flow_id
        assert "start" in data
        assert "end" in data
        assert "reason" in data
        assert "active" in data
        assert "updated_at" in data

    def test_put_stores_start_end(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/maintenance-window",
                json={"start": "2026-06-01T10:00:00Z", "end": "2026-06-01T12:00:00Z"},
                headers=_auth(token),
            )
        assert resp.json()["start"] == "2026-06-01T10:00:00Z"
        assert resp.json()["end"] == "2026-06-01T12:00:00Z"

    def test_put_with_reason(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/maintenance-window",
                json={
                    "start": "2026-05-01T00:00:00Z",
                    "end": "2026-05-01T02:00:00Z",
                    "reason": "DB upgrade",
                },
                headers=_auth(token),
            )
        assert resp.json()["reason"] == "DB upgrade"

    def test_put_without_reason_defaults_empty(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/maintenance-window",
                json={"start": "2026-05-01T00:00:00Z", "end": "2026-05-01T02:00:00Z"},
                headers=_auth(token),
            )
        assert resp.json()["reason"] == ""

    def test_put_reason_too_long_422(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/maintenance-window",
                json={
                    "start": "2026-05-01T00:00:00Z",
                    "end": "2026-05-01T02:00:00Z",
                    "reason": "x" * 501,
                },
                headers=_auth(token),
            )
        assert resp.status_code == 422
        assert "error" in resp.json()

    def test_put_active_is_true(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/maintenance-window",
                json={"start": "2026-05-01T00:00:00Z", "end": "2026-05-01T02:00:00Z"},
                headers=_auth(token),
            )
        assert resp.json()["active"] is True

    def test_put_replaces_existing(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_window(client, token, flow_id, end="2026-04-01T01:00:00Z")
            resp = client.put(
                f"/api/v1/flows/{flow_id}/maintenance-window",
                json={"start": "2026-07-01T00:00:00Z", "end": "2026-07-01T06:00:00Z"},
                headers=_auth(token),
            )
        assert "2026-07-01" in resp.json()["start"]

    def test_put_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.put(
                "/api/v1/flows/nonexistent/maintenance-window",
                json={"start": "2026-05-01T00:00:00Z", "end": "2026-05-01T02:00:00Z"},
                headers=_auth(token),
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_put_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/maintenance-window",
                json={"start": "2026-05-01T00:00:00Z", "end": "2026-05-01T02:00:00Z"},
            )
        assert resp.status_code == 401
        assert "error" in resp.json()


# ---------------------------------------------------------------------------
# Tests — GET /flows/{id}/maintenance-window
# ---------------------------------------------------------------------------


class TestFlowMaintenanceWindowGet:
    def test_get_returns_window_after_put(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_window(client, token, flow_id, reason="Deploy")
            resp = client.get(
                f"/api/v1/flows/{flow_id}/maintenance-window", headers=_auth(token)
            )
        assert resp.status_code == 200
        assert resp.json()["reason"] == "Deploy"

    def test_get_404_when_no_window(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(
                f"/api/v1/flows/{flow_id}/maintenance-window", headers=_auth(token)
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_get_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get(
                "/api/v1/flows/nonexistent/maintenance-window", headers=_auth(token)
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_get_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_window(client, token, flow_id)
            resp = client.get(f"/api/v1/flows/{flow_id}/maintenance-window")
        assert resp.status_code == 401
        assert "error" in resp.json()


# ---------------------------------------------------------------------------
# Tests — DELETE /flows/{id}/maintenance-window
# ---------------------------------------------------------------------------


class TestFlowMaintenanceWindowDelete:
    def test_delete_removes_window(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_window(client, token, flow_id)
            resp = client.delete(
                f"/api/v1/flows/{flow_id}/maintenance-window", headers=_auth(token)
            )
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True
        assert resp.json()["flow_id"] == flow_id

    def test_get_404_after_delete(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_window(client, token, flow_id)
            client.delete(f"/api/v1/flows/{flow_id}/maintenance-window", headers=_auth(token))
            resp = client.get(
                f"/api/v1/flows/{flow_id}/maintenance-window", headers=_auth(token)
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_delete_404_when_no_window(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.delete(
                f"/api/v1/flows/{flow_id}/maintenance-window", headers=_auth(token)
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_delete_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.delete(
                "/api/v1/flows/nonexistent/maintenance-window", headers=_auth(token)
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_delete_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_window(client, token, flow_id)
            resp = client.delete(f"/api/v1/flows/{flow_id}/maintenance-window")
        assert resp.status_code == 401
        assert "error" in resp.json()
