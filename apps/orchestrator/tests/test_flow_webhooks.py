"""
N-160: Flow Outbound Webhooks — POST/GET /flows/{id}/webhooks
                                  GET/PATCH/DELETE /flows/{id}/webhooks/{hook_id}

Tests:
  - POST creates webhook; returns 201
  - POST response shape (id, flow_id, url, events, secret, label, enabled, created_at)
  - POST invalid URL → 422
  - POST unknown event → 422
  - POST empty events list → 422
  - GET returns empty list on fresh flow
  - GET lists webhooks after create
  - GET returns flow_id, total, allowed_events
  - GET single webhook by ID
  - GET single 404 for unknown ID
  - PATCH updates url
  - PATCH updates events
  - PATCH toggles enabled
  - PATCH 404 for unknown hook
  - PATCH invalid url → 422
  - PATCH unknown event → 422
  - DELETE removes webhook; returns {deleted: true}
  - DELETE 404 for unknown webhook
  - GET after DELETE shows empty list
  - POST/GET/DELETE 404 for unknown flow
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
        json={"email": f"wh-{uid}@test.com", "password": "pass1234"},
    )
    assert r.status_code == 201
    return r.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_flow(client: TestClient, token: str) -> str:
    resp = client.post(
        "/api/v1/flows",
        json={"name": "Webhook Test Flow", "nodes": [], "edges": []},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _add_webhook(
    client: TestClient,
    token: str,
    flow_id: str,
    url: str = "https://example.com/hook",
    events: list | None = None,
    label: str = "",
) -> dict:
    body: dict = {
        "url": url,
        "events": events or ["run.completed"],
        "label": label,
    }
    resp = client.post(
        f"/api/v1/flows/{flow_id}/webhooks",
        json=body,
        headers=_auth(token),
    )
    assert resp.status_code == 201
    return resp.json()


# ---------------------------------------------------------------------------
# Tests — POST /flows/{id}/webhooks
# ---------------------------------------------------------------------------


class TestFlowWebhookPost:
    def test_post_returns_201(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/webhooks",
                json={"url": "https://hook.example.com", "events": ["run.completed"]},
                headers=_auth(token),
            )
        assert resp.status_code == 201

    def test_post_response_shape(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/webhooks",
                json={
                    "url": "https://hook.example.com/notify",
                    "events": ["run.started", "run.failed"],
                    "label": "CI notifier",
                },
                headers=_auth(token),
            )
        data = resp.json()
        assert "id" in data
        assert data["flow_id"] == flow_id
        assert data["url"] == "https://hook.example.com/notify"
        assert set(data["events"]) == {"run.started", "run.failed"}
        assert data["label"] == "CI notifier"
        assert data["enabled"] is True
        assert "created_at" in data

    def test_post_invalid_url_422(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/webhooks",
                json={"url": "not-a-url", "events": ["run.completed"]},
                headers=_auth(token),
            )
        assert resp.status_code == 422

    def test_post_unknown_event_422(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/webhooks",
                json={"url": "https://hook.example.com", "events": ["unknown.event"]},
                headers=_auth(token),
            )
        assert resp.status_code == 422

    def test_post_empty_events_422(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/webhooks",
                json={"url": "https://hook.example.com", "events": []},
                headers=_auth(token),
            )
        assert resp.status_code == 422

    def test_post_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.post(
                "/api/v1/flows/nonexistent/webhooks",
                json={"url": "https://hook.example.com", "events": ["run.completed"]},
                headers=_auth(token),
            )
        assert resp.status_code == 404

    def test_post_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/webhooks",
                json={"url": "https://hook.example.com", "events": ["run.completed"]},
            )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Tests — GET /flows/{id}/webhooks
# ---------------------------------------------------------------------------


class TestFlowWebhookList:
    def test_get_empty_on_fresh_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/webhooks", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["items"] == []

    def test_get_lists_webhooks(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _add_webhook(client, token, flow_id, url="https://a.example.com/hook")
            _add_webhook(client, token, flow_id, url="https://b.example.com/hook")
            resp = client.get(f"/api/v1/flows/{flow_id}/webhooks", headers=_auth(token))
        data = resp.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2

    def test_get_response_has_allowed_events(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/webhooks", headers=_auth(token))
        assert len(resp.json()["allowed_events"]) >= 5

    def test_get_flow_id_in_response(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/webhooks", headers=_auth(token))
        assert resp.json()["flow_id"] == flow_id

    def test_get_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get("/api/v1/flows/nonexistent/webhooks", headers=_auth(token))
        assert resp.status_code == 404

    def test_get_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/webhooks")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Tests — GET /flows/{id}/webhooks/{hook_id}
# ---------------------------------------------------------------------------


class TestFlowWebhookGetOne:
    def test_get_single_webhook(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            hook = _add_webhook(client, token, flow_id, label="Single Test")
            resp = client.get(
                f"/api/v1/flows/{flow_id}/webhooks/{hook['id']}", headers=_auth(token)
            )
        assert resp.status_code == 200
        assert resp.json()["label"] == "Single Test"

    def test_get_single_404_unknown(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(
                f"/api/v1/flows/{flow_id}/webhooks/nonexistent", headers=_auth(token)
            )
        assert resp.status_code == 404

    def test_get_single_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            hook = _add_webhook(client, token, flow_id)
            resp = client.get(f"/api/v1/flows/{flow_id}/webhooks/{hook['id']}")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Tests — PATCH /flows/{id}/webhooks/{hook_id}
# ---------------------------------------------------------------------------


class TestFlowWebhookPatch:
    def test_patch_updates_url(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            hook = _add_webhook(client, token, flow_id)
            resp = client.patch(
                f"/api/v1/flows/{flow_id}/webhooks/{hook['id']}",
                json={"url": "https://new.example.com/hook"},
                headers=_auth(token),
            )
        assert resp.status_code == 200
        assert resp.json()["url"] == "https://new.example.com/hook"

    def test_patch_updates_events(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            hook = _add_webhook(client, token, flow_id, events=["run.completed"])
            resp = client.patch(
                f"/api/v1/flows/{flow_id}/webhooks/{hook['id']}",
                json={"events": ["run.started", "run.failed"]},
                headers=_auth(token),
            )
        assert set(resp.json()["events"]) == {"run.started", "run.failed"}

    def test_patch_toggles_enabled(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            hook = _add_webhook(client, token, flow_id)
            resp = client.patch(
                f"/api/v1/flows/{flow_id}/webhooks/{hook['id']}",
                json={"enabled": False},
                headers=_auth(token),
            )
        assert resp.json()["enabled"] is False

    def test_patch_invalid_url_422(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            hook = _add_webhook(client, token, flow_id)
            resp = client.patch(
                f"/api/v1/flows/{flow_id}/webhooks/{hook['id']}",
                json={"url": "not-a-url"},
                headers=_auth(token),
            )
        assert resp.status_code == 422

    def test_patch_unknown_event_422(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            hook = _add_webhook(client, token, flow_id)
            resp = client.patch(
                f"/api/v1/flows/{flow_id}/webhooks/{hook['id']}",
                json={"events": ["mystery.event"]},
                headers=_auth(token),
            )
        assert resp.status_code == 422

    def test_patch_404_unknown_hook(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.patch(
                f"/api/v1/flows/{flow_id}/webhooks/nonexistent",
                json={"enabled": False},
                headers=_auth(token),
            )
        assert resp.status_code == 404

    def test_patch_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            hook = _add_webhook(client, token, flow_id)
            resp = client.patch(
                f"/api/v1/flows/{flow_id}/webhooks/{hook['id']}",
                json={"enabled": False},
            )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Tests — DELETE /flows/{id}/webhooks/{hook_id}
# ---------------------------------------------------------------------------


class TestFlowWebhookDelete:
    def test_delete_removes_webhook(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            hook = _add_webhook(client, token, flow_id)
            resp = client.delete(
                f"/api/v1/flows/{flow_id}/webhooks/{hook['id']}", headers=_auth(token)
            )
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True

    def test_get_after_delete_shows_empty(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            hook = _add_webhook(client, token, flow_id)
            client.delete(
                f"/api/v1/flows/{flow_id}/webhooks/{hook['id']}", headers=_auth(token)
            )
            resp = client.get(f"/api/v1/flows/{flow_id}/webhooks", headers=_auth(token))
        assert resp.json()["items"] == []

    def test_delete_404_unknown_webhook(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.delete(
                f"/api/v1/flows/{flow_id}/webhooks/nonexistent", headers=_auth(token)
            )
        assert resp.status_code == 404

    def test_delete_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.delete(
                "/api/v1/flows/nonexistent/webhooks/any-id", headers=_auth(token)
            )
        assert resp.status_code == 404

    def test_delete_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            hook = _add_webhook(client, token, flow_id)
            resp = client.delete(f"/api/v1/flows/{flow_id}/webhooks/{hook['id']}")
        assert resp.status_code == 401
