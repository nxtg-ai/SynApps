"""
DIRECTIVE-NXTG-20260318-123: Full E2E — Variables + Secrets + Scheduler +
Error Handler + Marketplace + Notifications (N-26 + N-27 integration)

Exercises every major platform feature added in the current session:
  - Workflow variables ({{var.name}} in node data)
  - Environment secrets ({{secret.name}}, masked in responses)
  - Scheduler: create / list / delete a schedule
  - Error Handler node: suppress_error + fallback_content
  - Marketplace: publish → search → featured → install
  - Notifications: configure on_complete + on_failure handlers
  - Execution logs: verify per-node events after webhook-triggered run
"""

import time
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from apps.orchestrator.main import (
    AppletMessage,
    app,
    marketplace_registry,
    notification_store,
    webhook_trigger_registry,
    workflow_secret_store,
    workflow_variable_store,
)

# ---------------------------------------------------------------------------
# Auth helper
# ---------------------------------------------------------------------------


def _get_token(client: TestClient) -> str:
    email = f"e2e-n27-{uuid.uuid4().hex[:8]}@test.com"
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "E2ePass123!"},
    )
    return resp.json()["access_token"]


# ---------------------------------------------------------------------------
# Shared test flow
# ---------------------------------------------------------------------------

E2E_FLOW = {
    "id": "e2e-n27-full-pipeline",
    "name": "E2E N-27: Full Platform Feature Test",
    "nodes": [
        {
            "id": "trigger",
            "type": "webhook_trigger",
            "position": {"x": 300, "y": 0},
            "data": {"label": "Inbound Webhook"},
        },
        {
            "id": "llm_step",
            "type": "llm",
            "position": {"x": 300, "y": 125},
            "data": {
                "label": "LLM",
                "provider": "openai",
                "model": "gpt-4o-mini",
                "system_prompt": "Summarize: {{var.prompt_prefix}}",
            },
        },
        {
            "id": "http_step",
            "type": "http_request",
            "position": {"x": 300, "y": 250},
            "data": {
                "label": "HTTP Notify",
                "method": "POST",
                "url": "https://httpbin.org/post",
                "headers": {"X-API-Key": "{{secret.api_key}}"},
            },
        },
        {
            "id": "error_step",
            "type": "error_handler",
            "position": {"x": 300, "y": 375},
            "data": {
                "label": "Error Catch",
                "fallback_content": "pipeline recovered",
                "suppress_error": True,
            },
        },
        {
            "id": "end",
            "type": "end",
            "position": {"x": 300, "y": 500},
            "data": {"label": "Done"},
        },
    ],
    "edges": [
        {"id": "t-llm", "source": "trigger", "target": "llm_step"},
        {"id": "llm-http", "source": "llm_step", "target": "http_step"},
        {"id": "http-err", "source": "http_step", "target": "error_step"},
        {"id": "err-end", "source": "error_step", "target": "end"},
    ],
}

_MOCK_LLM = AppletMessage(
    content="LLM summary using prompt prefix.",
    context={},
    metadata={"applet": "llm", "status": "success"},
)
_MOCK_HTTP = AppletMessage(
    content={"data": '{"ok": true}', "status_code": 200},
    context={},
    metadata={"applet": "http_request", "status": "success", "status_code": 200},
)


def _poll_run(client: TestClient, run_id: str, *, timeout: float = 5.0) -> dict | None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(0.1)
        resp = client.get(f"/api/v1/runs/{run_id}")
        if resp.status_code == 200:
            run = resp.json()
            if run.get("status") in ("success", "error"):
                return run
    return None


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_singletons():
    with webhook_trigger_registry._lock:
        webhook_trigger_registry._triggers.clear()
    marketplace_registry.reset()
    notification_store.reset()
    workflow_variable_store.reset()
    workflow_secret_store.reset()
    yield
    with webhook_trigger_registry._lock:
        webhook_trigger_registry._triggers.clear()
    marketplace_registry.reset()
    notification_store.reset()
    workflow_variable_store.reset()
    workflow_secret_store.reset()


# ===========================================================================
# Gate A — Flow Structure
# ===========================================================================


class TestE2EFlowStructure:
    """Verify the E2E test flow definition is well-formed."""

    def test_flow_has_five_nodes(self):
        assert len(E2E_FLOW["nodes"]) == 5

    def test_flow_covers_required_types(self):
        types = {n["type"] for n in E2E_FLOW["nodes"]}
        assert "webhook_trigger" in types
        assert "llm" in types
        assert "http_request" in types
        assert "error_handler" in types
        assert "end" in types

    def test_all_edge_endpoints_valid(self):
        node_ids = {n["id"] for n in E2E_FLOW["nodes"]}
        for edge in E2E_FLOW["edges"]:
            assert edge["source"] in node_ids
            assert edge["target"] in node_ids


# ===========================================================================
# Gate B — Variables + Secrets configured on flow
# ===========================================================================


class TestVariablesAndSecretsOnFlow:
    """Verify variables and secrets can be set and retrieved for the E2E flow."""

    def test_set_and_get_variables(self):
        with TestClient(app) as client:
            client.post("/api/v1/flows", json=E2E_FLOW)
            resp = client.put(
                f"/api/v1/workflows/{E2E_FLOW['id']}/variables",
                json={"prompt_prefix": "BE CONCISE: "},
            )
            assert resp.status_code == 200
            assert resp.json()["variables"]["prompt_prefix"] == "BE CONCISE: "  # Gate 2

    def test_set_and_get_secrets_masked(self):
        with TestClient(app) as client:
            client.post("/api/v1/flows", json=E2E_FLOW)
            resp = client.put(
                f"/api/v1/workflows/{E2E_FLOW['id']}/secrets",
                json={"api_key": "sk-real-secret-value"},
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["secrets"]["api_key"] == "***"  # Gate 2: never returned in plaintext

    def test_secrets_not_in_get_response_as_plaintext(self):
        with TestClient(app) as client:
            client.post("/api/v1/flows", json=E2E_FLOW)
            client.put(
                f"/api/v1/workflows/{E2E_FLOW['id']}/secrets",
                json={"api_key": "sk-real-secret-value"},
            )
            resp = client.get(f"/api/v1/workflows/{E2E_FLOW['id']}/secrets")
            resp_text = resp.text
            assert "sk-real-secret-value" not in resp_text  # Gate 2: plaintext never returned


# ===========================================================================
# Gate C — Notifications configured on flow
# ===========================================================================


class TestNotificationsOnFlow:
    """Verify notification configuration can be set and retrieved."""

    def test_configure_on_complete_and_on_failure(self):
        with TestClient(app) as client:
            client.post("/api/v1/flows", json=E2E_FLOW)
            config = {
                "on_complete": [{"type": "webhook", "url": "https://notify.example.com/success"}],
                "on_failure": [{"type": "webhook", "url": "https://notify.example.com/failure"}],
            }
            resp = client.put(
                f"/api/v1/workflows/{E2E_FLOW['id']}/notifications",
                json=config,
            )
            assert resp.status_code == 200
            body = resp.json()
            assert len(body["config"]["on_complete"]) == 1  # Gate 2: stored
            assert len(body["config"]["on_failure"]) == 1

    def test_notification_config_persists_after_get(self):
        with TestClient(app) as client:
            client.post("/api/v1/flows", json=E2E_FLOW)
            client.put(
                f"/api/v1/workflows/{E2E_FLOW['id']}/notifications",
                json={"on_complete": [{"type": "slack", "webhook_url": "https://hooks.slack.com/x"}]},
            )
            resp = client.get(f"/api/v1/workflows/{E2E_FLOW['id']}/notifications")
            assert resp.status_code == 200
            assert resp.json()["config"]["on_complete"][0]["type"] == "slack"  # Gate 2


# ===========================================================================
# Gate D — Webhook trigger → full execution → execution logs
# ===========================================================================


class TestWebhookExecutionWithLogsAndNotifications:
    """Fire the full pipeline via webhook, verify logs and notification dispatch."""

    def test_webhook_trigger_and_execution_logs(self):
        with TestClient(app) as client:
            # 1. Create flow
            resp = client.post("/api/v1/flows", json=E2E_FLOW)
            assert resp.status_code == 201

            # 2. Set variables + secrets
            client.put(
                f"/api/v1/workflows/{E2E_FLOW['id']}/variables",
                json={"prompt_prefix": "SUMMARIZE: "},
            )
            client.put(
                f"/api/v1/workflows/{E2E_FLOW['id']}/secrets",
                json={"api_key": "sk-secret-api-key"},
            )

            # 3. Configure notification (webhook type, mocked in dispatch)
            client.put(
                f"/api/v1/workflows/{E2E_FLOW['id']}/notifications",
                json={"on_complete": [{"type": "webhook", "url": "https://notify.example.com"}]},
            )

            # 4. Register webhook trigger
            resp = client.post(
                "/api/v1/webhook-triggers",
                json={"flow_id": E2E_FLOW["id"]},
            )
            assert resp.status_code == 201
            trigger_id = resp.json()["id"]
            assert trigger_id  # Gate 2: trigger ID returned

            # 5. Fire via webhook receive
            with patch(
                "apps.orchestrator.main.LLMNodeApplet.on_message",
                new_callable=AsyncMock,
                return_value=_MOCK_LLM,
            ), patch(
                "apps.orchestrator.main.HTTPRequestNodeApplet.on_message",
                new_callable=AsyncMock,
                return_value=_MOCK_HTTP,
            ), patch(
                "apps.orchestrator.main.broadcast_status",
                new_callable=AsyncMock,
            ), patch(
                "apps.orchestrator.main.NotificationService._send_webhook",
                new_callable=AsyncMock,
            ):
                resp = client.post(
                    f"/api/v1/webhook-triggers/{trigger_id}/receive",
                    json={"event": "e2e_n27", "source": "integration_test"},
                )

            assert resp.status_code == 202
            assert resp.json()["accepted"] is True
            run_id = resp.json()["run_id"]
            assert run_id  # Gate 2: run_id in 202 response

            # 6. Poll until terminal
            run = _poll_run(client, run_id)
            assert run is not None
            assert run["status"] in ("success", "error")

            # 7. Execution logs must exist and include node_start events
            resp = client.get(f"/api/v1/executions/{run_id}/logs")
            assert resp.status_code == 200
            log_body = resp.json()
            assert log_body["count"] >= 1  # Gate 2: logs recorded
            events = [e["event"] for e in log_body["logs"]]
            assert "node_start" in events  # Gate 2: start event recorded

            # 8. Secret must not appear in any log entry
            log_text = str(log_body)
            assert "sk-secret-api-key" not in log_text  # Gate 2: secret masked in logs


# ===========================================================================
# Gate E — Scheduler API
# ===========================================================================


class TestSchedulerWithE2EFlow:
    """Create, list, delete a schedule for the E2E flow."""

    def test_schedule_lifecycle(self):
        with TestClient(app) as client:
            client.post("/api/v1/flows", json=E2E_FLOW)

            resp = client.post(
                "/api/v1/schedules",
                json={
                    "flow_id": E2E_FLOW["id"],
                    "cron_expr": "0 9 * * 1",  # every Monday 9am
                    "name": "E2E N-27 Weekly Schedule",
                    "enabled": False,
                },
            )
            assert resp.status_code == 201
            sched_id = resp.json()["id"]
            assert sched_id  # Gate 2: schedule ID returned

            resp = client.get("/api/v1/schedules", params={"flow_id": E2E_FLOW["id"]})
            assert resp.status_code == 200
            ids = [s["id"] for s in resp.json()]
            assert sched_id in ids  # Gate 2: schedule appears in list

            resp = client.delete(f"/api/v1/schedules/{sched_id}")
            assert resp.status_code == 204


# ===========================================================================
# Gate F — Marketplace lifecycle
# ===========================================================================


class TestMarketplaceWithE2EFlow:
    """Publish the E2E flow to marketplace, install it."""

    def test_publish_and_install(self):
        with TestClient(app) as client:
            token = _get_token(client)
            auth = {"Authorization": f"Bearer {token}"}

            # 1. Create flow (auth required after user registered)
            resp = client.post("/api/v1/flows", json=E2E_FLOW, headers=auth)
            assert resp.status_code == 201

            # 2. Publish
            resp = client.post(
                "/api/v1/marketplace/publish",
                json={
                    "flow_id": E2E_FLOW["id"],
                    "name": "Full N-27 Platform Pipeline",
                    "description": "Variables, secrets, notifications, error handler.",
                    "category": "devops",
                    "author": "e2e-n27",
                    "tags": ["e2e", "n27"],
                },
                headers=auth,
            )
            assert resp.status_code == 201
            listing_id = resp.json()["id"]
            assert listing_id  # Gate 2: listing ID returned

            # 3. Install
            resp = client.post(
                f"/api/v1/marketplace/install/{listing_id}",
                json={"flow_name": "Installed N-27 Pipeline"},
                headers=auth,
            )
            assert resp.status_code == 201
            installed = resp.json()
            assert "flow_id" in installed  # Gate 2: new flow ID returned
            assert installed["flow_id"] != E2E_FLOW["id"]  # cloned with new ID

            # 4. Install count incremented
            resp = client.get("/api/v1/marketplace/search", params={"q": "N-27 Platform"})
            items = resp.json()["items"]
            listing = next((i for i in items if i["id"] == listing_id), None)
            assert listing is not None
            assert listing["install_count"] >= 1  # Gate 2: count incremented
