"""
N-164: Flow Notification Preferences — PUT/GET/DELETE /flows/{id}/notification-prefs

Tests:
  - PUT creates prefs; returns 200
  - PUT response shape (flow_id, user, events, channels, updated_at)
  - PUT response includes allowed_events and allowed_channels
  - PUT with empty events and channels succeeds
  - PUT unknown event → 422
  - PUT unknown channel → 422
  - PUT 404 for unknown flow
  - PUT requires auth
  - GET returns prefs after PUT
  - GET 404 when no prefs set
  - GET 404 for unknown flow
  - GET requires auth
  - DELETE removes prefs; returns {deleted: true, flow_id}
  - DELETE 404 when no prefs set
  - DELETE 404 for unknown flow
  - DELETE requires auth
  - Two users have independent prefs on the same flow
  - PUT overwrites existing prefs
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
        json={"email": f"notif-{uid}@test.com", "password": "pass1234"},
    )
    assert r.status_code == 201
    return r.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_flow(client: TestClient, token: str) -> str:
    resp = client.post(
        "/api/v1/flows",
        json={"name": "Notif Prefs Test Flow", "nodes": [], "edges": []},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _set_prefs(
    client: TestClient,
    token: str,
    flow_id: str,
    events: dict | None = None,
    channels: list | None = None,
) -> dict:
    resp = client.put(
        f"/api/v1/flows/{flow_id}/notification-prefs",
        json={
            "events": events if events is not None else {"run.completed": True, "run.failed": True},
            "channels": channels if channels is not None else ["email"],
        },
        headers=_auth(token),
    )
    assert resp.status_code == 200
    return resp.json()


# ---------------------------------------------------------------------------
# Tests — PUT /flows/{id}/notification-prefs
# ---------------------------------------------------------------------------


class TestFlowNotifPrefPut:
    def test_put_returns_200(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/notification-prefs",
                json={"events": {"run.completed": True}, "channels": ["email"]},
                headers=_auth(token),
            )
        assert resp.status_code == 200

    def test_put_response_shape(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/notification-prefs",
                json={"events": {"run.failed": True, "flow.updated": False}, "channels": ["slack"]},
                headers=_auth(token),
            )
        data = resp.json()
        assert data["flow_id"] == flow_id
        assert "user" in data
        assert data["events"]["run.failed"] is True
        assert data["events"]["flow.updated"] is False
        assert data["channels"] == ["slack"]
        assert "updated_at" in data

    def test_put_includes_allowed_lists(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/notification-prefs",
                json={"events": {}, "channels": []},
                headers=_auth(token),
            )
        data = resp.json()
        assert len(data["allowed_events"]) == 5
        assert len(data["allowed_channels"]) == 3

    def test_put_empty_events_and_channels(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/notification-prefs",
                json={"events": {}, "channels": []},
                headers=_auth(token),
            )
        assert resp.status_code == 200
        assert resp.json()["events"] == {}
        assert resp.json()["channels"] == []

    def test_put_unknown_event_422(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/notification-prefs",
                json={"events": {"unknown.event": True}, "channels": []},
                headers=_auth(token),
            )
        assert resp.status_code == 422

    def test_put_unknown_channel_422(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/notification-prefs",
                json={"events": {}, "channels": ["sms"]},
                headers=_auth(token),
            )
        assert resp.status_code == 422

    def test_put_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.put(
                "/api/v1/flows/nonexistent/notification-prefs",
                json={"events": {}, "channels": []},
                headers=_auth(token),
            )
        assert resp.status_code == 404

    def test_put_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/notification-prefs",
                json={"events": {}, "channels": []},
            )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Tests — GET /flows/{id}/notification-prefs
# ---------------------------------------------------------------------------


class TestFlowNotifPrefGet:
    def test_get_returns_prefs_after_put(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_prefs(client, token, flow_id, {"run.completed": True}, ["in_app"])
            resp = client.get(
                f"/api/v1/flows/{flow_id}/notification-prefs", headers=_auth(token)
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["events"]["run.completed"] is True
        assert data["channels"] == ["in_app"]

    def test_get_404_when_no_prefs(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(
                f"/api/v1/flows/{flow_id}/notification-prefs", headers=_auth(token)
            )
        assert resp.status_code == 404

    def test_get_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get(
                "/api/v1/flows/nonexistent/notification-prefs", headers=_auth(token)
            )
        assert resp.status_code == 404

    def test_get_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_prefs(client, token, flow_id)
            resp = client.get(f"/api/v1/flows/{flow_id}/notification-prefs")
        assert resp.status_code == 401

    def test_get_includes_allowed_lists(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_prefs(client, token, flow_id)
            resp = client.get(
                f"/api/v1/flows/{flow_id}/notification-prefs", headers=_auth(token)
            )
        data = resp.json()
        assert "allowed_events" in data
        assert "allowed_channels" in data


# ---------------------------------------------------------------------------
# Tests — DELETE /flows/{id}/notification-prefs
# ---------------------------------------------------------------------------


class TestFlowNotifPrefDelete:
    def test_delete_removes_prefs(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_prefs(client, token, flow_id)
            resp = client.delete(
                f"/api/v1/flows/{flow_id}/notification-prefs", headers=_auth(token)
            )
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True
        assert resp.json()["flow_id"] == flow_id

    def test_get_404_after_delete(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_prefs(client, token, flow_id)
            client.delete(f"/api/v1/flows/{flow_id}/notification-prefs", headers=_auth(token))
            resp = client.get(
                f"/api/v1/flows/{flow_id}/notification-prefs", headers=_auth(token)
            )
        assert resp.status_code == 404

    def test_delete_404_when_no_prefs(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.delete(
                f"/api/v1/flows/{flow_id}/notification-prefs", headers=_auth(token)
            )
        assert resp.status_code == 404

    def test_delete_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.delete(
                "/api/v1/flows/nonexistent/notification-prefs", headers=_auth(token)
            )
        assert resp.status_code == 404

    def test_delete_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_prefs(client, token, flow_id)
            resp = client.delete(f"/api/v1/flows/{flow_id}/notification-prefs")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Tests — Multi-user isolation + overwrite
# ---------------------------------------------------------------------------


class TestFlowNotifPrefIsolation:
    def test_two_users_independent_prefs(self):
        with TestClient(app) as client:
            token_a = _register(client)
            token_b = _register(client)
            flow_id = _create_flow(client, token_a)
            # token_b user can also set prefs on the same flow
            _set_prefs(client, token_a, flow_id, {"run.completed": True}, ["email"])
            _set_prefs(client, token_b, flow_id, {"run.failed": True}, ["slack"])
            resp_a = client.get(
                f"/api/v1/flows/{flow_id}/notification-prefs", headers=_auth(token_a)
            )
            resp_b = client.get(
                f"/api/v1/flows/{flow_id}/notification-prefs", headers=_auth(token_b)
            )
        assert resp_a.json()["channels"] == ["email"]
        assert resp_b.json()["channels"] == ["slack"]
        assert resp_a.json()["user"] != resp_b.json()["user"]

    def test_put_overwrites_existing_prefs(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_prefs(client, token, flow_id, {"run.completed": True}, ["email"])
            _set_prefs(client, token, flow_id, {"run.failed": False}, ["slack", "in_app"])
            resp = client.get(
                f"/api/v1/flows/{flow_id}/notification-prefs", headers=_auth(token)
            )
        data = resp.json()
        assert "run.completed" not in data["events"]
        assert data["events"]["run.failed"] is False
        assert set(data["channels"]) == {"slack", "in_app"}
