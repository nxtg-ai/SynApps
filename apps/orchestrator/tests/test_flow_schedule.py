"""
N-159: Flow Scheduled Runs — PUT/GET/PATCH/DELETE /flows/{id}/schedule

Tests:
  - PUT creates schedule; returns 200
  - PUT response shape (flow_id, cron, enabled, label, created_at, updated_at)
  - PUT invalid cron expression → 422
  - PUT replaces existing schedule
  - GET returns schedule after PUT
  - GET 404 when no schedule set
  - PATCH toggles enabled flag
  - PATCH updates cron expression
  - PATCH updates label
  - PATCH invalid cron → 422
  - PATCH 404 when no schedule set
  - DELETE removes schedule; returns {deleted: true}
  - DELETE 404 when no schedule set
  - GET 404 after DELETE
  - PUT/GET/PATCH/DELETE 404 for unknown flow
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
        json={"email": f"sched-{uid}@test.com", "password": "pass1234"},
    )
    assert r.status_code == 201
    return r.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_flow(client: TestClient, token: str) -> str:
    resp = client.post(
        "/api/v1/flows",
        json={"name": "Schedule Test Flow", "nodes": [], "edges": []},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _set_schedule(
    client: TestClient,
    token: str,
    flow_id: str,
    cron: str = "0 9 * * 1-5",
    enabled: bool = True,
    label: str = "",
) -> dict:
    resp = client.put(
        f"/api/v1/flows/{flow_id}/schedule",
        json={"cron": cron, "enabled": enabled, "label": label},
        headers=_auth(token),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# Tests — PUT /flows/{id}/schedule
# ---------------------------------------------------------------------------


class TestFlowSchedulePut:
    def test_put_returns_200(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/schedule",
                json={"cron": "0 9 * * 1-5"},
                headers=_auth(token),
            )
        assert resp.status_code == 200

    def test_put_response_shape(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/schedule",
                json={"cron": "*/15 * * * *", "label": "Every 15 min"},
                headers=_auth(token),
            )
        data = resp.json()
        assert data["flow_id"] == flow_id
        assert data["cron"] == "*/15 * * * *"
        assert data["label"] == "Every 15 min"
        assert data["enabled"] is True
        assert "created_at" in data
        assert "updated_at" in data

    def test_put_invalid_cron_422(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/schedule",
                json={"cron": "not-a-cron"},
                headers=_auth(token),
            )
        assert resp.status_code == 422

    def test_put_replaces_existing(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_schedule(client, token, flow_id, "0 9 * * *")
            resp = client.put(
                f"/api/v1/flows/{flow_id}/schedule",
                json={"cron": "0 18 * * *"},
                headers=_auth(token),
            )
        assert resp.json()["cron"] == "0 18 * * *"

    def test_put_enabled_false(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/schedule",
                json={"cron": "0 0 * * *", "enabled": False},
                headers=_auth(token),
            )
        assert resp.json()["enabled"] is False

    def test_put_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.put(
                "/api/v1/flows/nonexistent/schedule",
                json={"cron": "0 9 * * *"},
                headers=_auth(token),
            )
        assert resp.status_code == 404

    def test_put_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/schedule",
                json={"cron": "0 9 * * *"},
            )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Tests — GET /flows/{id}/schedule
# ---------------------------------------------------------------------------


class TestFlowScheduleGet:
    def test_get_returns_schedule(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_schedule(client, token, flow_id, "0 12 * * *")
            resp = client.get(f"/api/v1/flows/{flow_id}/schedule", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["cron"] == "0 12 * * *"

    def test_get_404_no_schedule(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/schedule", headers=_auth(token))
        assert resp.status_code == 404

    def test_get_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get("/api/v1/flows/nonexistent/schedule", headers=_auth(token))
        assert resp.status_code == 404

    def test_get_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/schedule")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Tests — PATCH /flows/{id}/schedule
# ---------------------------------------------------------------------------


class TestFlowSchedulePatch:
    def test_patch_toggles_enabled(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_schedule(client, token, flow_id)
            resp = client.patch(
                f"/api/v1/flows/{flow_id}/schedule",
                json={"enabled": False},
                headers=_auth(token),
            )
        assert resp.status_code == 200
        assert resp.json()["enabled"] is False

    def test_patch_updates_cron(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_schedule(client, token, flow_id, "0 9 * * *")
            resp = client.patch(
                f"/api/v1/flows/{flow_id}/schedule",
                json={"cron": "0 22 * * *"},
                headers=_auth(token),
            )
        assert resp.json()["cron"] == "0 22 * * *"

    def test_patch_updates_label(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_schedule(client, token, flow_id)
            resp = client.patch(
                f"/api/v1/flows/{flow_id}/schedule",
                json={"label": "Nightly run"},
                headers=_auth(token),
            )
        assert resp.json()["label"] == "Nightly run"

    def test_patch_invalid_cron_422(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_schedule(client, token, flow_id)
            resp = client.patch(
                f"/api/v1/flows/{flow_id}/schedule",
                json={"cron": "bad-expr"},
                headers=_auth(token),
            )
        assert resp.status_code == 422

    def test_patch_404_no_schedule(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.patch(
                f"/api/v1/flows/{flow_id}/schedule",
                json={"enabled": False},
                headers=_auth(token),
            )
        assert resp.status_code == 404

    def test_patch_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_schedule(client, token, flow_id)
            resp = client.patch(
                f"/api/v1/flows/{flow_id}/schedule",
                json={"enabled": False},
            )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Tests — DELETE /flows/{id}/schedule
# ---------------------------------------------------------------------------


class TestFlowScheduleDelete:
    def test_delete_removes_schedule(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_schedule(client, token, flow_id)
            resp = client.delete(f"/api/v1/flows/{flow_id}/schedule", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True

    def test_get_404_after_delete(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_schedule(client, token, flow_id)
            client.delete(f"/api/v1/flows/{flow_id}/schedule", headers=_auth(token))
            resp = client.get(f"/api/v1/flows/{flow_id}/schedule", headers=_auth(token))
        assert resp.status_code == 404

    def test_delete_404_no_schedule(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.delete(f"/api/v1/flows/{flow_id}/schedule", headers=_auth(token))
        assert resp.status_code == 404

    def test_delete_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.delete("/api/v1/flows/nonexistent/schedule", headers=_auth(token))
        assert resp.status_code == 404

    def test_delete_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_schedule(client, token, flow_id)
            resp = client.delete(f"/api/v1/flows/{flow_id}/schedule")
        assert resp.status_code == 401
