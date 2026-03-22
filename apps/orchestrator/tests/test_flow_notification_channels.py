"""
N-190: Flow Notification Channels — POST/GET/DELETE /flows/{id}/notification-channels

Tests:
  - POST creates channel; returns 201
  - POST response shape (channel_id, flow_id, type, target, events, enabled, created_at)
  - POST type "email" stored
  - POST type "slack" stored
  - POST type "webhook" stored
  - POST type "pagerduty" stored
  - POST invalid type → 422
  - POST invalid event → 422
  - POST deduplicates events
  - POST default enabled=True
  - POST too many channels → 422
  - POST 404 for unknown flow
  - POST requires auth
  - GET list returns all channels
  - GET list empty when none
  - GET list 404 unknown flow
  - GET list requires auth
  - GET single returns channel
  - GET single 404 unknown channel
  - GET single 404 unknown flow
  - GET single requires auth
  - DELETE removes channel; returns {deleted: true, channel_id, flow_id}
  - DELETE 404 not found
  - DELETE 404 unknown flow
  - DELETE requires auth
  - DELETE then GET 404
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
        json={"email": f"nc-{uid}@test.com", "password": "pass1234"},
    )
    assert r.status_code == 201
    return r.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_flow(client: TestClient, token: str) -> str:
    resp = client.post(
        "/api/v1/flows",
        json={"name": "Notification Channel Test Flow", "nodes": [], "edges": []},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _create_channel(
    client: TestClient,
    token: str,
    flow_id: str,
    channel_type: str = "email",
    target: str = "ops@example.com",
    events: list | None = None,
    enabled: bool = True,
) -> dict:
    resp = client.post(
        f"/api/v1/flows/{flow_id}/notification-channels",
        json={"type": channel_type, "target": target, "events": events or [], "enabled": enabled},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    return resp.json()


# ---------------------------------------------------------------------------
# Tests — POST /flows/{id}/notification-channels
# ---------------------------------------------------------------------------


class TestFlowNotificationChannelPost:
    def test_post_returns_201(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/notification-channels",
                json={"type": "email", "target": "a@b.com"},
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
                f"/api/v1/flows/{flow_id}/notification-channels",
                json={"type": "slack", "target": "#ops"},
                headers=_auth(token),
            )
        data = resp.json()
        assert "channel_id" in data
        assert data["flow_id"] == flow_id
        assert "type" in data
        assert "target" in data
        assert "events" in data
        assert "enabled" in data
        assert "created_at" in data

    def test_post_type_email(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/notification-channels",
                json={"type": "email", "target": "x@y.com"},
                headers=_auth(token),
            )
        assert resp.json()["type"] == "email"

    def test_post_type_slack(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/notification-channels",
                json={"type": "slack", "target": "#channel"},
                headers=_auth(token),
            )
        assert resp.json()["type"] == "slack"

    def test_post_type_webhook(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/notification-channels",
                json={"type": "webhook", "target": "https://hook.example.com"},
                headers=_auth(token),
            )
        assert resp.json()["type"] == "webhook"

    def test_post_type_pagerduty(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/notification-channels",
                json={"type": "pagerduty", "target": "pd-key-abc"},
                headers=_auth(token),
            )
        assert resp.json()["type"] == "pagerduty"

    def test_post_invalid_type_422(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/notification-channels",
                json={"type": "telegram", "target": "chat123"},
                headers=_auth(token),
            )
        assert resp.status_code == 422
        assert "error" in resp.json()

    def test_post_invalid_event_422(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/notification-channels",
                json={"type": "email", "target": "a@b.com", "events": ["not.an.event"]},
                headers=_auth(token),
            )
        assert resp.status_code == 422
        assert "error" in resp.json()

    def test_post_deduplicates_events(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/notification-channels",
                json={"type": "email", "target": "a@b.com", "events": ["run.failed", "run.failed", "run.completed"]},
                headers=_auth(token),
            )
        assert len(resp.json()["events"]) == 2  # Gate 2

    def test_post_default_enabled_true(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/notification-channels",
                json={"type": "slack", "target": "#ops"},
                headers=_auth(token),
            )
        assert resp.json()["enabled"] is True

    def test_post_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.post(
                "/api/v1/flows/nonexistent/notification-channels",
                json={"type": "email", "target": "a@b.com"},
                headers=_auth(token),
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_post_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/notification-channels",
                json={"type": "email", "target": "a@b.com"},
            )
        assert resp.status_code == 401
        assert "error" in resp.json()


# ---------------------------------------------------------------------------
# Tests — GET /flows/{id}/notification-channels (list)
# ---------------------------------------------------------------------------


class TestFlowNotificationChannelList:
    def test_list_returns_channels(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _create_channel(client, token, flow_id, target="a@b.com")
            _create_channel(client, token, flow_id, channel_type="slack", target="#ops")
            resp = client.get(
                f"/api/v1/flows/{flow_id}/notification-channels", headers=_auth(token)
            )
        assert resp.status_code == 200
        assert len(resp.json()) == 2  # Gate 2

    def test_list_empty_when_none(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(
                f"/api/v1/flows/{flow_id}/notification-channels", headers=_auth(token)
            )
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get(
                "/api/v1/flows/nonexistent/notification-channels", headers=_auth(token)
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_list_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/notification-channels")
        assert resp.status_code == 401
        assert "error" in resp.json()


# ---------------------------------------------------------------------------
# Tests — GET /flows/{id}/notification-channels/{channel_id}
# ---------------------------------------------------------------------------


class TestFlowNotificationChannelGet:
    def test_get_returns_channel(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            created = _create_channel(client, token, flow_id)
            cid = created["channel_id"]
            resp = client.get(
                f"/api/v1/flows/{flow_id}/notification-channels/{cid}", headers=_auth(token)
            )
        assert resp.status_code == 200
        assert resp.json()["channel_id"] == cid

    def test_get_404_unknown_channel(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(
                f"/api/v1/flows/{flow_id}/notification-channels/nonexistent", headers=_auth(token)
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_get_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get(
                "/api/v1/flows/nonexistent/notification-channels/any", headers=_auth(token)
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_get_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            created = _create_channel(client, token, flow_id)
            resp = client.get(
                f"/api/v1/flows/{flow_id}/notification-channels/{created['channel_id']}"
            )
        assert resp.status_code == 401
        assert "error" in resp.json()


# ---------------------------------------------------------------------------
# Tests — DELETE /flows/{id}/notification-channels/{channel_id}
# ---------------------------------------------------------------------------


class TestFlowNotificationChannelDelete:
    def test_delete_removes_channel(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            created = _create_channel(client, token, flow_id)
            cid = created["channel_id"]
            resp = client.delete(
                f"/api/v1/flows/{flow_id}/notification-channels/{cid}", headers=_auth(token)
            )
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True
        assert resp.json()["channel_id"] == cid
        assert resp.json()["flow_id"] == flow_id

    def test_delete_then_get_404(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            created = _create_channel(client, token, flow_id)
            cid = created["channel_id"]
            client.delete(
                f"/api/v1/flows/{flow_id}/notification-channels/{cid}", headers=_auth(token)
            )
            resp = client.get(
                f"/api/v1/flows/{flow_id}/notification-channels/{cid}", headers=_auth(token)
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_delete_404_not_found(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.delete(
                f"/api/v1/flows/{flow_id}/notification-channels/nonexistent", headers=_auth(token)
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_delete_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.delete(
                "/api/v1/flows/nonexistent/notification-channels/any", headers=_auth(token)
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_delete_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            created = _create_channel(client, token, flow_id)
            resp = client.delete(
                f"/api/v1/flows/{flow_id}/notification-channels/{created['channel_id']}"
            )
        assert resp.status_code == 401
        assert "error" in resp.json()
