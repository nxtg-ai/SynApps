"""Tests for N-19 Webhook Trigger Node — inbound webhook → flow execution.

Covers:
  - WebhookTriggerRegistry: register, list, get, delete, verify_signature
  - REST endpoints: POST/GET/DELETE /webhook-triggers, POST /receive
  - HMAC-SHA256 signature verification (signed and unsigned)
  - Flow-not-found guard on register
  - receive: JSON body, non-JSON body, empty body
  - receive: missing signature when secret required → 401
  - receive: valid signature accepted
  - Node type registered in applet_registry and KNOWN_NODE_TYPES
  - WebhookTriggerNodeApplet.on_message passthrough
  - Orchestrator.load_applet recognises "webhook_trigger" and aliases
"""

import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient

from apps.orchestrator.main import (
    KNOWN_NODE_TYPES,
    AppletMessage,
    WebhookTriggerNodeApplet,
    WebhookTriggerRegistry,
    app,
    applet_registry,
    webhook_trigger_registry,
)


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _reset_trigger_registry():
    """Clear trigger registry between tests."""
    with webhook_trigger_registry._lock:
        webhook_trigger_registry._triggers.clear()
    yield
    with webhook_trigger_registry._lock:
        webhook_trigger_registry._triggers.clear()


_FLOW_PAYLOAD = {
    "id": "wt-test-flow",
    "name": "Webhook Test Flow",
    "nodes": [
        {"id": "n1", "type": "start", "position": {"x": 0, "y": 0}, "data": {"label": "Start"}},
        {"id": "n2", "type": "end", "position": {"x": 0, "y": 100}, "data": {"label": "End"}},
    ],
    "edges": [{"id": "e1", "source": "n1", "target": "n2"}],
}


@pytest.fixture
def flow_id(client):
    """Create a minimal flow and return its ID."""
    resp = client.post("/api/v1/flows", json=_FLOW_PAYLOAD)
    assert resp.status_code in (200, 201), f"Flow creation failed: {resp.text}"
    return "wt-test-flow"


# ===========================================================================
# WebhookTriggerRegistry — unit tests (no HTTP)
# ===========================================================================


class TestWebhookTriggerRegistryUnit:
    """Pure unit tests against the WebhookTriggerRegistry class."""

    def test_register_returns_public_view(self):
        reg = WebhookTriggerRegistry()
        result = reg.register("flow-abc", secret="mysecret")
        assert "id" in result
        assert result["flow_id"] == "flow-abc"
        assert "_enc_secret" not in result  # Gate 2: secret never leaked
        assert "created_at" in result

    def test_register_without_secret(self):
        reg = WebhookTriggerRegistry()
        result = reg.register("flow-xyz")
        assert result["flow_id"] == "flow-xyz"
        assert "_enc_secret" not in result

    def test_list_all_triggers(self):
        reg = WebhookTriggerRegistry()
        reg.register("flow-1")
        reg.register("flow-2")
        items = reg.list_triggers()
        assert len(items) >= 2  # Gate 2: all registered triggers present

    def test_list_filtered_by_flow_id(self):
        reg = WebhookTriggerRegistry()
        reg.register("flow-A")
        reg.register("flow-A")
        reg.register("flow-B")
        items = reg.list_triggers(flow_id="flow-A")
        assert len(items) == 2  # Gate 2: filter returns exactly matching triggers
        for item in items:
            assert item["flow_id"] == "flow-A"

    def test_get_existing(self):
        reg = WebhookTriggerRegistry()
        created = reg.register("flow-get")
        fetched = reg.get(created["id"])
        assert fetched is not None
        assert fetched["id"] == created["id"]

    def test_get_nonexistent_returns_none(self):
        reg = WebhookTriggerRegistry()
        assert reg.get("does-not-exist") is None

    def test_delete_existing(self):
        reg = WebhookTriggerRegistry()
        t = reg.register("flow-del")
        assert reg.delete(t["id"]) is True
        assert reg.get(t["id"]) is None

    def test_delete_nonexistent_returns_false(self):
        reg = WebhookTriggerRegistry()
        assert reg.delete("ghost-id") is False

    def test_delete_removes_from_list(self):
        reg = WebhookTriggerRegistry()
        t = reg.register("flow-dl")
        reg.delete(t["id"])
        items = reg.list_triggers(flow_id="flow-dl")
        assert len(items) == 0  # Gate 2: empty after delete

    def test_verify_signature_no_secret_always_true(self):
        reg = WebhookTriggerRegistry()
        t = reg.register("flow-nosec")
        assert reg.verify_signature(t["id"], b"body", None) is True
        assert reg.verify_signature(t["id"], b"body", "sha256=whatever") is True

    def test_verify_signature_with_secret_correct(self):
        reg = WebhookTriggerRegistry()
        secret = "test-secret-abc"
        t = reg.register("flow-sig", secret=secret)
        body = b'{"event": "ping"}'
        sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        assert reg.verify_signature(t["id"], body, sig) is True

    def test_verify_signature_with_secret_wrong_sig(self):
        reg = WebhookTriggerRegistry()
        t = reg.register("flow-badsig", secret="correct-secret")
        assert reg.verify_signature(t["id"], b"body", "sha256=badhex") is False

    def test_verify_signature_with_secret_missing_header(self):
        reg = WebhookTriggerRegistry()
        t = reg.register("flow-nosig", secret="some-secret")
        assert reg.verify_signature(t["id"], b"body", None) is False

    def test_verify_signature_unknown_trigger_returns_false(self):
        reg = WebhookTriggerRegistry()
        assert reg.verify_signature("fake-id", b"body", None) is False

    def test_fernet_encryption_roundtrip(self):
        from apps.orchestrator.main import _get_fernet_encrypt

        enc, dec = _get_fernet_encrypt()
        reg = WebhookTriggerRegistry(encrypt_fn=enc, decrypt_fn=dec)
        secret = "super-secret-123"
        t = reg.register("flow-enc", secret=secret)

        # The raw record should store encrypted secret
        with reg._lock:
            raw = reg._triggers[t["id"]]
        enc_val = raw.get("_enc_secret")
        assert enc_val is not None
        assert enc_val != secret  # Gate 2: stored encrypted, not plaintext

        # Signature verification should work correctly
        body = b"hello"
        sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        assert reg.verify_signature(t["id"], body, sig) is True


# ===========================================================================
# REST Endpoints — authenticated CRUD
# ===========================================================================


class TestWebhookTriggerEndpoints:
    """HTTP endpoint tests for the webhook trigger CRUD API."""

    def test_register_trigger_flow_not_found(self, client):
        resp = client.post(
            "/api/v1/webhook-triggers",
            json={"flow_id": "nonexistent-flow"},
        )
        assert resp.status_code == 404

    def test_register_trigger_success(self, client, flow_id):
        resp = client.post(
            "/api/v1/webhook-triggers",
            json={"flow_id": flow_id},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "id" in data
        assert data["flow_id"] == flow_id
        assert "_enc_secret" not in data

    def test_register_trigger_with_secret(self, client, flow_id):
        resp = client.post(
            "/api/v1/webhook-triggers",
            json={"flow_id": flow_id, "secret": "my-hmac-secret"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "id" in data
        # Secret must never be returned
        assert "secret" not in data
        assert "_enc_secret" not in data

    def test_list_triggers_empty(self, client):
        resp = client.get("/api/v1/webhook-triggers")
        assert resp.status_code == 200
        data = resp.json()
        assert data["triggers"] == []
        assert data["total"] == 0

    def test_list_triggers_after_register(self, client, flow_id):
        client.post("/api/v1/webhook-triggers", json={"flow_id": flow_id})
        client.post("/api/v1/webhook-triggers", json={"flow_id": flow_id})
        resp = client.get("/api/v1/webhook-triggers")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 2  # Gate 2: both triggers present

    def test_list_triggers_filtered_by_flow(self, client, flow_id):
        # Create a second flow
        client.post(
            "/api/v1/flows",
            json={
                "id": "other-flow",
                "name": "Other Flow",
                "nodes": [
                    {"id": "s", "type": "start", "position": {"x": 0, "y": 0}, "data": {}},
                ],
                "edges": [],
            },
        )
        client.post("/api/v1/webhook-triggers", json={"flow_id": flow_id})
        client.post("/api/v1/webhook-triggers", json={"flow_id": "other-flow"})
        resp = client.get(f"/api/v1/webhook-triggers?flow_id={flow_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1  # Gate 2: filter works
        assert data["triggers"][0]["flow_id"] == flow_id

    def test_get_trigger(self, client, flow_id):
        reg = client.post("/api/v1/webhook-triggers", json={"flow_id": flow_id}).json()
        resp = client.get(f"/api/v1/webhook-triggers/{reg['id']}")
        assert resp.status_code == 200
        assert resp.json()["id"] == reg["id"]

    def test_get_trigger_not_found(self, client):
        resp = client.get("/api/v1/webhook-triggers/ghost-id")
        assert resp.status_code == 404

    def test_delete_trigger(self, client, flow_id):
        reg = client.post("/api/v1/webhook-triggers", json={"flow_id": flow_id}).json()
        resp = client.delete(f"/api/v1/webhook-triggers/{reg['id']}")
        assert resp.status_code == 200
        assert resp.json()["id"] == reg["id"]
        # Confirm gone
        assert client.get(f"/api/v1/webhook-triggers/{reg['id']}").status_code == 404

    def test_delete_trigger_not_found(self, client):
        resp = client.delete("/api/v1/webhook-triggers/no-such-id")
        assert resp.status_code == 404


# ===========================================================================
# Receive Endpoint — trigger flow execution
# ===========================================================================


class TestWebhookTriggerReceive:
    """Tests for POST /webhook-triggers/{id}/receive."""

    def test_receive_unknown_trigger(self, client):
        resp = client.post("/api/v1/webhook-triggers/ghost/receive", json={})
        # verify_signature returns False for unknown trigger
        assert resp.status_code in (401, 404)

    def test_receive_unsigned_trigger_no_secret(self, client, flow_id):
        reg = client.post("/api/v1/webhook-triggers", json={"flow_id": flow_id}).json()
        resp = client.post(
            f"/api/v1/webhook-triggers/{reg['id']}/receive",
            json={"hello": "world"},
        )
        assert resp.status_code == 202
        data = resp.json()
        assert data["accepted"] is True
        assert "run_id" in data
        assert data["trigger_id"] == reg["id"]

    def test_receive_with_correct_signature(self, client, flow_id):
        secret = "integration-secret"
        reg = client.post(
            "/api/v1/webhook-triggers",
            json={"flow_id": flow_id, "secret": secret},
        ).json()

        body = json.dumps({"event": "test"}).encode()
        sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        resp = client.post(
            f"/api/v1/webhook-triggers/{reg['id']}/receive",
            content=body,
            headers={"Content-Type": "application/json", "X-Webhook-Signature": sig},
        )
        assert resp.status_code == 202
        assert resp.json()["accepted"] is True

    def test_receive_with_wrong_signature(self, client, flow_id):
        reg = client.post(
            "/api/v1/webhook-triggers",
            json={"flow_id": flow_id, "secret": "correct-secret"},
        ).json()
        resp = client.post(
            f"/api/v1/webhook-triggers/{reg['id']}/receive",
            json={"x": 1},
            headers={"X-Webhook-Signature": "sha256=deadbeef"},
        )
        assert resp.status_code == 401

    def test_receive_without_signature_when_required(self, client, flow_id):
        reg = client.post(
            "/api/v1/webhook-triggers",
            json={"flow_id": flow_id, "secret": "required-secret"},
        ).json()
        resp = client.post(
            f"/api/v1/webhook-triggers/{reg['id']}/receive",
            json={"payload": "no-sig"},
        )
        assert resp.status_code == 401

    def test_receive_non_json_body(self, client, flow_id):
        reg = client.post("/api/v1/webhook-triggers", json={"flow_id": flow_id}).json()
        resp = client.post(
            f"/api/v1/webhook-triggers/{reg['id']}/receive",
            content=b"plain text body",
            headers={"Content-Type": "text/plain"},
        )
        assert resp.status_code == 202
        assert resp.json()["accepted"] is True

    def test_receive_empty_body(self, client, flow_id):
        reg = client.post("/api/v1/webhook-triggers", json={"flow_id": flow_id}).json()
        resp = client.post(
            f"/api/v1/webhook-triggers/{reg['id']}/receive",
            content=b"",
        )
        assert resp.status_code == 202

    def test_receive_array_json_body(self, client, flow_id):
        reg = client.post("/api/v1/webhook-triggers", json={"flow_id": flow_id}).json()
        resp = client.post(
            f"/api/v1/webhook-triggers/{reg['id']}/receive",
            json=[1, 2, 3],
        )
        assert resp.status_code == 202


# ===========================================================================
# Node type registration — applet_registry and KNOWN_NODE_TYPES
# ===========================================================================


class TestWebhookTriggerNodeRegistration:
    """Verify the node type is wired up everywhere it needs to be."""

    def test_node_type_in_known_node_types(self):
        assert "webhook_trigger" in KNOWN_NODE_TYPES

    def test_node_type_in_applet_registry(self):
        assert "webhook_trigger" in applet_registry  # Gate 2: always registered

    def test_applet_registry_value_is_correct_class(self):
        assert applet_registry["webhook_trigger"] is WebhookTriggerNodeApplet

    @pytest.mark.asyncio
    async def test_load_applet_webhook_trigger(self):
        from apps.orchestrator.main import Orchestrator

        applet = await Orchestrator.load_applet("webhook_trigger")
        assert isinstance(applet, WebhookTriggerNodeApplet)

    @pytest.mark.asyncio
    async def test_load_applet_alias_hyphen(self):
        from apps.orchestrator.main import Orchestrator

        applet = await Orchestrator.load_applet("webhook-trigger")
        assert isinstance(applet, WebhookTriggerNodeApplet)

    @pytest.mark.asyncio
    async def test_load_applet_alias_with_node_suffix(self):
        from apps.orchestrator.main import Orchestrator

        applet = await Orchestrator.load_applet("webhook_trigger_node")
        assert isinstance(applet, WebhookTriggerNodeApplet)


# ===========================================================================
# WebhookTriggerNodeApplet.on_message passthrough
# ===========================================================================


class TestWebhookTriggerNodeAppletBehaviour:
    """Verify the applet passes content + context through unchanged."""

    @pytest.mark.asyncio
    async def test_on_message_passthrough_content(self):
        applet = WebhookTriggerNodeApplet()
        msg = AppletMessage(
            content={"payload": {"event": "push"}},
            context={"run_id": "r1"},
            metadata={"node_id": "node-1"},
        )
        result = await applet.on_message(msg)
        assert result.content == {"payload": {"event": "push"}}
        assert result.context == {"run_id": "r1"}

    @pytest.mark.asyncio
    async def test_on_message_sets_applet_metadata(self):
        applet = WebhookTriggerNodeApplet()
        msg = AppletMessage(content={}, context={}, metadata={})
        result = await applet.on_message(msg)
        assert result.metadata.get("applet") == "webhook_trigger"
        assert result.metadata.get("status") == "triggered"

    def test_applet_has_version(self):
        assert hasattr(WebhookTriggerNodeApplet, "VERSION")
        assert WebhookTriggerNodeApplet.VERSION == "1.0.0"

    def test_applet_has_capabilities(self):
        caps = WebhookTriggerNodeApplet.CAPABILITIES
        assert "webhook-trigger" in caps  # Gate 2: capabilities always declared
        assert "hmac-sha256-verification" in caps
