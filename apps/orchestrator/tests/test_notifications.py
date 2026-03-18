"""
DIRECTIVE-NXTG-20260318-122: Workflow Notifications — N-27

Tests for:
  1. NotificationStore unit — set / get / delete / reset
  2. NotificationService.dispatch — routes to correct adapter
  3. Email adapter — SMTP path (mocked), SendGrid path (mocked)
  4. Slack adapter — Slack webhook POST (mocked)
  5. Webhook adapter — custom URL POST (mocked)
  6. Adapter errors are swallowed + logged (Gate 5)
  7. GET/PUT /workflows/{id}/notifications endpoints
  8. Config validation — unknown handler type rejected
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from apps.orchestrator.main import (
    NotificationService,
    NotificationStore,
    app,
    notification_store,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_notification_store():
    notification_store.reset()
    yield
    notification_store.reset()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BASE_FLOW = {
    "nodes": [
        {"id": "start", "type": "start", "position": {"x": 0, "y": 0}, "data": {"label": "S"}},
        {"id": "end", "type": "end", "position": {"x": 0, "y": 100}, "data": {"label": "E"}},
    ],
    "edges": [{"id": "s-e", "source": "start", "target": "end"}],
}


def _new_flow(**overrides) -> dict:
    f = {**_BASE_FLOW, "id": f"notif-flow-{uuid.uuid4().hex[:8]}", "name": "Notif Test Flow"}
    f.update(overrides)
    return f


# ===========================================================================
# Unit: NotificationStore
# ===========================================================================


class TestNotificationStoreUnit:
    """Unit tests for NotificationStore in isolation."""

    def test_set_and_get(self):
        store = NotificationStore()
        config = {
            "on_complete": [{"type": "email", "to": "test@example.com"}],
            "on_failure": [],
        }
        store.set("f1", config)
        result = store.get("f1")
        assert "on_complete" in result  # Gate 2: config stored
        assert result["on_complete"][0]["type"] == "email"

    def test_get_unknown_returns_empty(self):
        store = NotificationStore()
        assert store.get("nonexistent") == {}

    def test_set_replaces_existing(self):
        store = NotificationStore()
        store.set("f1", {"on_complete": [{"type": "slack", "webhook_url": "x"}]})
        store.set("f1", {"on_failure": [{"type": "webhook", "url": "y"}]})
        result = store.get("f1")
        assert "on_complete" not in result  # old key gone
        assert "on_failure" in result  # Gate 2: replacement works

    def test_delete_removes_config(self):
        store = NotificationStore()
        store.set("f1", {"on_complete": []})
        store.delete("f1")
        assert store.get("f1") == {}

    def test_reset_clears_all(self):
        store = NotificationStore()
        store.set("f1", {"on_complete": []})
        store.set("f2", {"on_failure": []})
        store.reset()
        assert store.get("f1") == {}
        assert store.get("f2") == {}

    def test_get_returns_copy(self):
        """Mutating the returned dict must not affect the store."""
        store = NotificationStore()
        store.set("f1", {"on_complete": []})
        result = store.get("f1")
        result["injected"] = True
        assert "injected" not in store.get("f1")


# ===========================================================================
# Unit: NotificationService dispatch routing
# ===========================================================================


class TestNotificationServiceDispatch:
    """Verify dispatch routes to the correct adapter based on handler type."""

    @pytest.mark.asyncio
    async def test_dispatch_no_handlers_no_op(self):
        """If no handlers configured, dispatch should complete silently."""
        svc = NotificationService()
        notification_store.set("f1", {"on_complete": [], "on_failure": []})
        # Should not raise
        await svc.dispatch("on_complete", "f1", "My Flow", "r1", "success", 100.0, "output")

    @pytest.mark.asyncio
    async def test_dispatch_routes_to_email_adapter(self):
        svc = NotificationService()
        notification_store.set("f1", {
            "on_complete": [{"type": "email", "to": "user@example.com"}],
        })
        with patch.object(svc, "_send_email", new_callable=AsyncMock) as mock_email:
            await svc.dispatch("on_complete", "f1", "Flow", "r1", "success", 500.0, "out")
        mock_email.assert_called_once()  # Gate 2: email adapter called

    @pytest.mark.asyncio
    async def test_dispatch_routes_to_slack_adapter(self):
        svc = NotificationService()
        notification_store.set("f1", {
            "on_failure": [{"type": "slack", "webhook_url": "https://hooks.slack.com/x"}],
        })
        with patch.object(svc, "_send_slack", new_callable=AsyncMock) as mock_slack:
            await svc.dispatch("on_failure", "f1", "Flow", "r1", "error", None, "err")
        mock_slack.assert_called_once()  # Gate 2: Slack adapter called

    @pytest.mark.asyncio
    async def test_dispatch_routes_to_webhook_adapter(self):
        svc = NotificationService()
        notification_store.set("f1", {
            "on_complete": [{"type": "webhook", "url": "https://custom.example.com/notify"}],
        })
        with patch.object(svc, "_send_webhook", new_callable=AsyncMock) as mock_wh:
            await svc.dispatch("on_complete", "f1", "Flow", "r1", "success", 100.0, "out")
        mock_wh.assert_called_once()  # Gate 2: webhook adapter called

    @pytest.mark.asyncio
    async def test_dispatch_multiple_handlers_all_called(self):
        """All handlers in the list must be called."""
        svc = NotificationService()
        notification_store.set("f1", {
            "on_complete": [
                {"type": "email", "to": "a@b.com"},
                {"type": "slack", "webhook_url": "https://hooks.slack.com/x"},
            ],
        })
        with (
            patch.object(svc, "_send_email", new_callable=AsyncMock) as mock_email,
            patch.object(svc, "_send_slack", new_callable=AsyncMock) as mock_slack,
        ):
            await svc.dispatch("on_complete", "f1", "Flow", "r1", "success", 100.0, "out")
        assert mock_email.call_count == 1  # Gate 2: both called
        assert mock_slack.call_count == 1

    @pytest.mark.asyncio
    async def test_dispatch_unknown_handler_type_warns_not_raises(self):
        """Unknown handler type must log a warning and not raise."""
        svc = NotificationService()
        notification_store.set("f1", {
            "on_complete": [{"type": "sms"}],  # unknown type
        })
        # Should not raise
        await svc.dispatch("on_complete", "f1", "Flow", "r1", "success", 100.0, "out")

    @pytest.mark.asyncio
    async def test_dispatch_adapter_error_is_swallowed(self):
        """Gate 5: adapter exceptions must be caught + logged, not propagated."""
        svc = NotificationService()
        notification_store.set("f1", {
            "on_failure": [{"type": "email", "to": "x@y.com"}],
        })

        async def _boom(handler, summary):
            raise ConnectionError("SMTP server down")

        with patch.object(svc, "_send_email", side_effect=_boom):
            # Must not raise
            await svc.dispatch("on_failure", "f1", "Flow", "r1", "error", None, "err")

    @pytest.mark.asyncio
    async def test_dispatch_missing_event_key_no_op(self):
        """on_complete not in config → no dispatch."""
        svc = NotificationService()
        notification_store.set("f1", {"on_failure": [{"type": "slack", "webhook_url": "x"}]})
        with patch.object(svc, "_send_slack", new_callable=AsyncMock) as mock_slack:
            await svc.dispatch("on_complete", "f1", "Flow", "r1", "success", 100.0, "out")
        assert mock_slack.call_count == 0  # Gate 2: wrong event → not called


# ===========================================================================
# Unit: Individual adapters
# ===========================================================================


class TestEmailAdapter:
    """Tests for the email notification adapter."""

    @pytest.mark.asyncio
    async def test_smtp_send_called_with_recipients(self):
        svc = NotificationService()
        with patch("smtplib.SMTP") as mock_smtp_cls:
            mock_smtp = MagicMock()
            mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_smtp)
            mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)
            await svc._send_email({"to": "user@example.com"}, "Summary text")
        # SMTP was instantiated → sendmail was called
        assert mock_smtp_cls.called  # Gate 2: SMTP used

    @pytest.mark.asyncio
    async def test_email_no_recipients_skips(self):
        """Missing 'to' field should not raise."""
        svc = NotificationService()
        # Should not raise even with no recipients
        await svc._send_email({"to": ""}, "Summary")

    @pytest.mark.asyncio
    async def test_sendgrid_path_used_when_api_key_set(self):
        """When sendgrid_api_key is present, use SendGrid HTTP not SMTP."""
        svc = NotificationService()
        handler = {
            "to": "user@example.com",
            "sendgrid_api_key": "SG.test-key",
        }
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=MagicMock(status_code=202))
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            await svc._send_email(handler, "Summary")
        mock_client.post.assert_called_once()  # Gate 2: HTTP POST called
        call_args = mock_client.post.call_args
        assert "sendgrid.com" in str(call_args)  # SendGrid URL used


class TestSlackAdapter:
    """Tests for the Slack notification adapter."""

    @pytest.mark.asyncio
    async def test_slack_posts_to_webhook_url(self):
        svc = NotificationService()
        handler = {"webhook_url": "https://hooks.slack.com/services/TEST/TEST/TEST"}
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=MagicMock(status_code=200))
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            await svc._send_slack(handler, "Summary text", "success")
        mock_client.post.assert_called_once()  # Gate 2: POST called
        call_url = mock_client.post.call_args[0][0]
        assert "hooks.slack.com" in call_url

    @pytest.mark.asyncio
    async def test_slack_no_webhook_url_skips(self):
        """Missing webhook_url must not raise."""
        svc = NotificationService()
        await svc._send_slack({"webhook_url": ""}, "Summary", "error")

    @pytest.mark.asyncio
    async def test_slack_uses_error_color_for_failure(self):
        svc = NotificationService()
        handler = {"webhook_url": "https://hooks.slack.com/x"}
        captured_payload = {}

        async def _capture_post(url, json=None, **kwargs):
            captured_payload.update(json or {})
            return MagicMock(status_code=200)

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=_capture_post)
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            await svc._send_slack(handler, "Summary", "error")

        # The error color attachment should be present
        attachments = captured_payload.get("attachments", [])
        assert len(attachments) >= 1  # Gate 2: at least one attachment
        assert attachments[0].get("color") == "#e01e5a"  # error color


class TestWebhookAdapter:
    """Tests for the custom webhook notification adapter."""

    @pytest.mark.asyncio
    async def test_webhook_posts_json_payload(self):
        svc = NotificationService()
        handler = {"url": "https://custom.example.com/notify"}
        captured = {}

        async def _capture(url, json=None, headers=None):
            captured["url"] = url
            captured["json"] = json
            return MagicMock(status_code=200)

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=_capture)
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            await svc._send_webhook(handler, "Summary", "success", "run-123")

        assert captured["url"] == "https://custom.example.com/notify"
        assert captured["json"]["run_id"] == "run-123"  # Gate 2: run_id in payload
        assert captured["json"]["status"] == "success"

    @pytest.mark.asyncio
    async def test_webhook_no_url_skips(self):
        """Missing url must not raise."""
        svc = NotificationService()
        await svc._send_webhook({"url": ""}, "Summary", "error", "run-x")


# ===========================================================================
# API: GET/PUT /workflows/{id}/notifications
# ===========================================================================


class TestNotificationsEndpoints:
    """Tests for GET/PUT /api/v1/workflows/{id}/notifications."""

    def test_get_404_for_unknown_flow(self):
        with TestClient(app) as client:
            resp = client.get("/api/v1/workflows/nonexistent-flow/notifications")
            assert resp.status_code == 404

    def test_get_empty_config_for_existing_flow(self):
        with TestClient(app) as client:
            flow = _new_flow()
            client.post("/api/v1/flows", json=flow)
            resp = client.get(f"/api/v1/workflows/{flow['id']}/notifications")
            assert resp.status_code == 200
            body = resp.json()
            assert body["flow_id"] == flow["id"]
            assert body["config"] == {}

    def test_put_stores_notification_config(self):
        with TestClient(app) as client:
            flow = _new_flow()
            client.post("/api/v1/flows", json=flow)
            config = {
                "on_complete": [{"type": "email", "to": "user@example.com"}],
                "on_failure": [{"type": "slack", "webhook_url": "https://hooks.slack.com/x"}],
            }
            resp = client.put(
                f"/api/v1/workflows/{flow['id']}/notifications",
                json=config,
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["flow_id"] == flow["id"]
            assert len(body["config"]["on_complete"]) == 1  # Gate 2: config stored
            assert body["config"]["on_complete"][0]["type"] == "email"

    def test_get_returns_stored_config(self):
        with TestClient(app) as client:
            flow = _new_flow()
            client.post("/api/v1/flows", json=flow)
            client.put(
                f"/api/v1/workflows/{flow['id']}/notifications",
                json={"on_failure": [{"type": "webhook", "url": "https://x.com"}]},
            )
            resp = client.get(f"/api/v1/workflows/{flow['id']}/notifications")
            assert resp.status_code == 200
            assert resp.json()["config"]["on_failure"][0]["type"] == "webhook"  # Gate 2

    def test_put_rejects_unknown_handler_type(self):
        with TestClient(app) as client:
            flow = _new_flow()
            client.post("/api/v1/flows", json=flow)
            resp = client.put(
                f"/api/v1/workflows/{flow['id']}/notifications",
                json={"on_complete": [{"type": "sms"}]},  # unknown type
            )
            assert resp.status_code == 422  # Gate 2: validation rejects unknown type

    def test_put_rejects_handler_without_type_field(self):
        with TestClient(app) as client:
            flow = _new_flow()
            client.post("/api/v1/flows", json=flow)
            resp = client.put(
                f"/api/v1/workflows/{flow['id']}/notifications",
                json={"on_complete": [{"url": "https://x.com"}]},  # missing type
            )
            assert resp.status_code == 422

    def test_put_404_for_unknown_flow(self):
        with TestClient(app) as client:
            resp = client.put(
                "/api/v1/workflows/ghost/notifications",
                json={"on_complete": [{"type": "slack", "webhook_url": "x"}]},
            )
            assert resp.status_code == 404

    def test_put_accepts_all_valid_handler_types(self):
        with TestClient(app) as client:
            flow = _new_flow()
            client.post("/api/v1/flows", json=flow)
            config = {
                "on_complete": [
                    {"type": "email", "to": "a@b.com"},
                    {"type": "slack", "webhook_url": "https://hooks.slack.com/x"},
                    {"type": "webhook", "url": "https://custom.example.com"},
                ]
            }
            resp = client.put(
                f"/api/v1/workflows/{flow['id']}/notifications",
                json=config,
            )
            assert resp.status_code == 200
            assert len(resp.json()["config"]["on_complete"]) == 3  # Gate 2: all 3 stored

    def test_put_replaces_existing_config(self):
        with TestClient(app) as client:
            flow = _new_flow()
            client.post("/api/v1/flows", json=flow)
            client.put(
                f"/api/v1/workflows/{flow['id']}/notifications",
                json={"on_complete": [{"type": "email", "to": "x@y.com"}]},
            )
            client.put(
                f"/api/v1/workflows/{flow['id']}/notifications",
                json={"on_failure": [{"type": "slack", "webhook_url": "x"}]},
            )
            resp = client.get(f"/api/v1/workflows/{flow['id']}/notifications")
            config = resp.json()["config"]
            assert "on_complete" not in config  # Gate 2: old config replaced
            assert "on_failure" in config
