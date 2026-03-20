"""
N-34: Webhook Debugger
Tests for WebhookDebugStore, debug endpoints, and integration with webhook triggers.
"""

import time
import uuid

from fastapi.testclient import TestClient

from apps.orchestrator.main import (
    WebhookDebugStore,
    app,
    webhook_debug_store,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _register(client: TestClient, email: str | None = None) -> str:
    """Register a user and return the access token."""
    email = email or f"whdbg-{uuid.uuid4().hex[:8]}@test.com"
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "WebHook1!"},
    )
    assert resp.status_code in (200, 201), resp.text
    return resp.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_flow(client: TestClient, token: str, name: str = "WH Debug") -> str:
    """Create a minimal flow with start/end nodes and return its ID."""
    uid = uuid.uuid4().hex[:8]
    flow_payload = {
        "name": name,
        "nodes": [
            {
                "id": f"start-{uid}",
                "type": "start",
                "position": {"x": 0, "y": 0},
                "data": {"label": "Start"},
            },
            {
                "id": f"end-{uid}",
                "type": "end",
                "position": {"x": 0, "y": 100},
                "data": {"label": "End"},
            },
        ],
        "edges": [
            {"id": f"e-{uid}", "source": f"start-{uid}", "target": f"end-{uid}"},
        ],
    }
    resp = client.post("/api/v1/flows", json=flow_payload, headers=_auth(token))
    assert resp.status_code == 201
    return resp.json()["id"]


def _register_webhook_trigger(
    client: TestClient, token: str, flow_id: str
) -> dict:
    """Register an inbound webhook trigger for *flow_id* and return trigger info."""
    resp = client.post(
        "/api/v1/webhook-triggers",
        json={"flow_id": flow_id},
        headers=_auth(token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _make_entry(
    entry_id: str | None = None,
    flow_id: str | None = "flow-1",
    status_code: int = 202,
) -> dict:
    """Build a synthetic WebhookDebugEntry dict for unit tests."""
    return {
        "entry_id": entry_id or str(uuid.uuid4()),
        "flow_id": flow_id,
        "received_at": time.time(),
        "method": "POST",
        "path": "/api/v1/webhook-triggers/t1/receive",
        "headers": {"content-type": "application/json"},
        "body": '{"hello": "world"}',
        "body_size": 18,
        "status_code": status_code,
        "response_body": '{"accepted": true}',
        "duration_ms": 12.5,
        "retry_count": 0,
        "last_retry_at": None,
    }


# ===========================================================================
# TestWebhookDebugStore — 6 unit tests
# ===========================================================================


class TestWebhookDebugStore:
    """Unit tests for the in-memory WebhookDebugStore."""

    def test_record_adds_entry(self) -> None:
        store = WebhookDebugStore()
        entry = _make_entry(entry_id="e1")
        result = store.record(entry)
        assert result["entry_id"] == "e1"
        items = store.list()
        assert isinstance(items, list)
        assert len(items) >= 1  # Gate 2

    def test_list_returns_newest_first(self) -> None:
        store = WebhookDebugStore()
        store.record(_make_entry(entry_id="old"))
        store.record(_make_entry(entry_id="new"))
        items = store.list()
        assert isinstance(items, list)
        assert len(items) >= 2  # Gate 2
        assert items[0]["entry_id"] == "new"
        assert items[1]["entry_id"] == "old"

    def test_list_filters_by_flow_id(self) -> None:
        store = WebhookDebugStore()
        store.record(_make_entry(entry_id="a", flow_id="f1"))
        store.record(_make_entry(entry_id="b", flow_id="f2"))
        store.record(_make_entry(entry_id="c", flow_id="f1"))
        items = store.list(flow_id="f1")
        assert isinstance(items, list)
        assert len(items) >= 1  # Gate 2
        assert all(e["flow_id"] == "f1" for e in items)
        assert len(items) == 2

    def test_get_returns_none_for_unknown(self) -> None:
        store = WebhookDebugStore()
        assert store.get("nonexistent") is None

    def test_clear_empties_store(self) -> None:
        store = WebhookDebugStore()
        store.record(_make_entry())
        store.clear()
        assert store.list() == []

    def test_max_entries_evicts_oldest(self) -> None:
        store = WebhookDebugStore()
        for i in range(201):
            store.record(_make_entry(entry_id=f"e-{i}"))
        items = store.list(limit=300)
        assert len(items) == 200
        # Oldest entry (e-0) should have been evicted
        ids = {e["entry_id"] for e in items}
        assert "e-0" not in ids
        assert "e-200" in ids


# ===========================================================================
# TestWebhookDebugEndpoints — 8 integration tests
# ===========================================================================


class TestWebhookDebugEndpoints:
    """Integration tests for the webhook debug REST endpoints."""

    def test_list_returns_200_with_items(self) -> None:
        with TestClient(app) as client:
            token = _register(client)
            # Seed an entry directly
            webhook_debug_store.record(_make_entry(entry_id="seed-1"))
            resp = client.get("/api/v1/webhooks/debug", headers=_auth(token))
            assert resp.status_code == 200
            data = resp.json()
            assert isinstance(data["items"], list)
            assert len(data["items"]) >= 1  # Gate 2

    def test_get_returns_200_for_known_entry(self) -> None:
        with TestClient(app) as client:
            token = _register(client)
            webhook_debug_store.record(_make_entry(entry_id="known-1"))
            resp = client.get("/api/v1/webhooks/debug/known-1", headers=_auth(token))
            assert resp.status_code == 200
            assert resp.json()["entry_id"] == "known-1"

    def test_get_returns_404_for_unknown(self) -> None:
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get("/api/v1/webhooks/debug/no-such-id", headers=_auth(token))
            assert resp.status_code == 404

    def test_delete_returns_204_and_clears(self) -> None:
        with TestClient(app) as client:
            token = _register(client)
            webhook_debug_store.record(_make_entry())
            resp = client.delete("/api/v1/webhooks/debug", headers=_auth(token))
            assert resp.status_code == 204
            items = webhook_debug_store.list()
            assert items == []

    def test_list_requires_auth(self) -> None:
        with TestClient(app) as client:
            # Register a user first so anonymous bootstrap is disabled
            _register(client)
            resp = client.get("/api/v1/webhooks/debug")
            assert resp.status_code in (401, 403)

    def test_get_requires_auth(self) -> None:
        with TestClient(app) as client:
            # Register a user first so anonymous bootstrap is disabled
            _register(client)
            resp = client.get("/api/v1/webhooks/debug/any-id")
            assert resp.status_code in (401, 403)

    def test_retry_increments_retry_count(self) -> None:
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            entry = _make_entry(entry_id="retry-me", flow_id=flow_id)
            webhook_debug_store.record(entry)
            resp = client.post(
                "/api/v1/webhooks/debug/retry-me/retry",
                headers=_auth(token),
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["retry_count"] >= 1
            assert data["last_retry_at"] is not None

    def test_headers_do_not_expose_authorization(self) -> None:
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            trigger = _register_webhook_trigger(client, token, flow_id)
            trigger_id = trigger["id"]
            # Send a webhook with an Authorization header
            client.post(
                f"/api/v1/webhook-triggers/{trigger_id}/receive",
                json={"test": True},
                headers={"Authorization": "Bearer secret-value"},
            )
            items = webhook_debug_store.list()
            assert isinstance(items, list)
            assert len(items) >= 1  # Gate 2
            entry = items[0]
            auth_val = entry["headers"].get("authorization", "")
            assert "secret-value" not in auth_val
            assert auth_val == "[REDACTED]"

    def test_entry_includes_correct_method_and_path(self) -> None:
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            trigger = _register_webhook_trigger(client, token, flow_id)
            trigger_id = trigger["id"]
            client.post(
                f"/api/v1/webhook-triggers/{trigger_id}/receive",
                json={"data": 1},
            )
            items = webhook_debug_store.list()
            assert isinstance(items, list)
            assert len(items) >= 1  # Gate 2
            entry = items[0]
            assert entry["method"] == "POST"
            assert trigger_id in entry["path"]


# ===========================================================================
# TestWebhookDebuggingIntegration — 5 integration tests
# ===========================================================================


class TestWebhookDebuggingIntegration:
    """End-to-end tests: trigger a real webhook and inspect debug entries."""

    def test_triggering_webhook_records_entry(self) -> None:
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            trigger = _register_webhook_trigger(client, token, flow_id)
            trigger_id = trigger["id"]
            client.post(
                f"/api/v1/webhook-triggers/{trigger_id}/receive",
                json={"msg": "hello"},
            )
            items = webhook_debug_store.list()
            assert isinstance(items, list)
            assert len(items) >= 1  # Gate 2

    def test_entry_body_contains_sent_payload(self) -> None:
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            trigger = _register_webhook_trigger(client, token, flow_id)
            trigger_id = trigger["id"]
            client.post(
                f"/api/v1/webhook-triggers/{trigger_id}/receive",
                json={"color": "blue"},
            )
            items = webhook_debug_store.list()
            assert isinstance(items, list)
            assert len(items) >= 1  # Gate 2
            assert "blue" in items[0]["body"]

    def test_entry_status_code_reflects_response(self) -> None:
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            trigger = _register_webhook_trigger(client, token, flow_id)
            trigger_id = trigger["id"]
            resp = client.post(
                f"/api/v1/webhook-triggers/{trigger_id}/receive",
                json={"ok": True},
            )
            items = webhook_debug_store.list()
            assert isinstance(items, list)
            assert len(items) >= 1  # Gate 2
            assert items[0]["status_code"] == resp.status_code

    def test_multiple_webhooks_recorded_separately(self) -> None:
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            trigger = _register_webhook_trigger(client, token, flow_id)
            trigger_id = trigger["id"]
            client.post(
                f"/api/v1/webhook-triggers/{trigger_id}/receive",
                json={"n": 1},
            )
            client.post(
                f"/api/v1/webhook-triggers/{trigger_id}/receive",
                json={"n": 2},
            )
            items = webhook_debug_store.list()
            assert isinstance(items, list)
            assert len(items) >= 2  # Gate 2
            ids = {e["entry_id"] for e in items}
            assert len(ids) == len(items)  # all unique IDs

    def test_flow_id_filter_returns_only_matching(self) -> None:
        with TestClient(app) as client:
            token = _register(client)
            flow_a = _create_flow(client, token, "Flow A")
            flow_b = _create_flow(client, token, "Flow B")
            trig_a = _register_webhook_trigger(client, token, flow_a)
            trig_b = _register_webhook_trigger(client, token, flow_b)
            client.post(
                f"/api/v1/webhook-triggers/{trig_a['id']}/receive",
                json={"src": "a"},
            )
            client.post(
                f"/api/v1/webhook-triggers/{trig_b['id']}/receive",
                json={"src": "b"},
            )
            items_a = webhook_debug_store.list(flow_id=flow_a)
            assert isinstance(items_a, list)
            assert len(items_a) >= 1  # Gate 2
            assert all(e["flow_id"] == flow_a for e in items_a)
