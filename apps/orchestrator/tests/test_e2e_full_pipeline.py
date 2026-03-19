"""
DIRECTIVE-NXTG-20260318-93: E2E Integration Test — Full Session Pipeline

End-to-end integration test covering the complete SynApps feature set shipped
in this session: all node types, webhook execution, analytics, marketplace.

Flow under test:
    webhook_trigger → llm → http_request → error_handler → end

Session features exercised:
    - All 5 node types: webhook_trigger, llm, http_request, error_handler, end
    - Scheduler node API (create/list/delete — trigger type, not wired into flow)
    - Webhook trigger registration → receive → execution
    - Execution analytics (workflow + node level)
    - Marketplace: publish flow → search → install → verify new flow in DB
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
    webhook_trigger_registry,
)

# ---------------------------------------------------------------------------
# Auth helper — register + login to get a real JWT
# ---------------------------------------------------------------------------


def _get_token(client: TestClient) -> str:
    email = f"e2e-full-{uuid.uuid4().hex[:8]}@test.com"
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "E2ePass123!"},
    )
    return resp.json()["access_token"]


# ---------------------------------------------------------------------------
# Full-session flow — all 5 active node types in one definition
# ---------------------------------------------------------------------------

E2E_FULL_FLOW = {
    "id": "e2e-full-session-pipeline",
    "name": "E2E Full Session: All Node Types",
    "nodes": [
        {
            "id": "trigger",
            "type": "webhook_trigger",
            "position": {"x": 300, "y": 25},
            "data": {"label": "Inbound Webhook"},
        },
        {
            "id": "llm_step",
            "type": "llm",
            "position": {"x": 300, "y": 150},
            "data": {
                "label": "LLM Processing",
                "provider": "openai",
                "model": "gpt-4o-mini",
                "system_prompt": "Summarize the input.",
            },
        },
        {
            "id": "http_step",
            "type": "http_request",
            "position": {"x": 300, "y": 275},
            "data": {
                "label": "Downstream Notify",
                "method": "POST",
                "url": "https://httpbin.org/post",
                "headers": {"Content-Type": "application/json"},
            },
        },
        {
            "id": "error_step",
            "type": "error_handler",
            "position": {"x": 300, "y": 400},
            "data": {
                "label": "Error Catch",
                "fallback_content": "pipeline recovered",
                "suppress_error": True,
            },
        },
        {
            "id": "end",
            "type": "end",
            "position": {"x": 300, "y": 525},
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
    content="LLM summary of payload.",
    context={},
    metadata={"applet": "llm", "status": "success"},
)
_MOCK_HTTP = AppletMessage(
    content={"data": '{"ok": true}', "status_code": 200},
    context={},
    metadata={"applet": "http_request", "status": "success", "status_code": 200},
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _poll_run(client: TestClient, run_id: str, *, timeout: float = 5.0) -> dict | None:
    """Poll GET /runs/{run_id} until terminal status or timeout."""
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
def _clean_registries():
    """Reset in-memory singletons between tests."""
    with webhook_trigger_registry._lock:
        webhook_trigger_registry._triggers.clear()
    marketplace_registry.reset()
    yield
    with webhook_trigger_registry._lock:
        webhook_trigger_registry._triggers.clear()
    marketplace_registry.reset()


# ===========================================================================
# Gate A — Flow Structure
# ===========================================================================


class TestFullPipelineStructure:
    """Verify the full-session flow is well-formed."""

    def test_flow_covers_all_five_node_types(self):
        types = {n["type"] for n in E2E_FULL_FLOW["nodes"]}
        assert "webhook_trigger" in types
        assert "llm" in types
        assert "http_request" in types
        assert "error_handler" in types
        assert "end" in types

    def test_flow_has_five_nodes(self):
        assert len(E2E_FULL_FLOW["nodes"]) == 5  # Gate 2: explicit count

    def test_flow_has_four_edges(self):
        assert len(E2E_FULL_FLOW["edges"]) == 4  # Gate 2: explicit count

    def test_all_edge_endpoints_are_valid_node_ids(self):
        node_ids = {n["id"] for n in E2E_FULL_FLOW["nodes"]}
        for edge in E2E_FULL_FLOW["edges"]:
            assert edge["source"] in node_ids, f"source {edge['source']} unknown"
            assert edge["target"] in node_ids, f"target {edge['target']} unknown"


# ===========================================================================
# Gate B — Webhook Trigger → Execution → Analytics
# ===========================================================================


class TestWebhookTriggerAndAnalytics:
    """Fire the full pipeline via webhook receive, then verify analytics."""

    def test_webhook_trigger_execute_and_analytics(self):
        """Full path: create → register → receive → run → analytics → marketplace."""
        with TestClient(app) as client:
            # 1. Create the flow
            resp = client.post("/api/v1/flows", json=E2E_FULL_FLOW)
            assert resp.status_code == 201, f"Flow creation failed: {resp.text}"

            # 2. Register webhook trigger
            resp = client.post(
                "/api/v1/webhook-triggers",
                json={"flow_id": E2E_FULL_FLOW["id"]},
            )
            assert resp.status_code == 201
            trigger_id = resp.json()["id"]
            assert trigger_id  # Gate 2: trigger ID must be non-empty

            # 3. Fire via webhook receive (mock LLM + HTTP to avoid real APIs)
            with (
                patch(
                    "apps.orchestrator.main.LLMNodeApplet.on_message",
                    new_callable=AsyncMock,
                    return_value=_MOCK_LLM,
                ),
                patch(
                    "apps.orchestrator.main.HTTPRequestNodeApplet.on_message",
                    new_callable=AsyncMock,
                    return_value=_MOCK_HTTP,
                ),
                patch(
                    "apps.orchestrator.main.broadcast_status",
                    new_callable=AsyncMock,
                ),
            ):
                resp = client.post(
                    f"/api/v1/webhook-triggers/{trigger_id}/receive",
                    json={"event": "e2e_full", "source": "integration_test"},
                )

            assert resp.status_code == 202
            data = resp.json()
            assert data["accepted"] is True
            assert "run_id" in data  # Gate 2: run_id in 202 response
            run_id = data["run_id"]

            # 4. Poll until terminal
            run = _poll_run(client, run_id)
            assert run is not None, "Run did not reach terminal state before timeout"
            assert run["run_id"] == run_id

            # 5. Analytics — workflow level
            resp = client.get(
                "/api/v1/analytics/workflows",
                params={"flow_id": E2E_FULL_FLOW["id"]},
            )
            assert resp.status_code == 200
            body = resp.json()
            assert "workflows" in body
            assert body["total_flows"] >= 1  # Gate 2: our flow must appear
            wf = next(
                (w for w in body["workflows"] if w["flow_id"] == E2E_FULL_FLOW["id"]),
                None,
            )
            assert wf is not None, "Flow not found in analytics"
            assert wf["run_count"] >= 1  # Gate 2: at least one run recorded

            # 6. Analytics — node level
            resp = client.get(
                "/api/v1/analytics/nodes",
                params={"flow_id": E2E_FULL_FLOW["id"]},
            )
            assert resp.status_code == 200
            node_body = resp.json()
            assert "nodes" in node_body
            assert node_body["total_nodes"] >= 1  # Gate 2: at least one node seen


# ===========================================================================
# Gate C — Scheduler Node API
# ===========================================================================


class TestSchedulerNodeIntegration:
    """Verify the scheduler node type is accepted in flows and the schedule API works."""

    def test_create_schedule_for_full_flow(self):
        """Create a schedule for the full-session flow and verify it appears in list."""
        with TestClient(app) as client:
            # Create the flow first
            resp = client.post("/api/v1/flows", json=E2E_FULL_FLOW)
            assert resp.status_code == 201

            # Create a paused schedule (won't fire in tests)
            # Field names: flow_id, cron_expr, name, enabled (not paused/cron)
            resp = client.post(
                "/api/v1/schedules",
                json={
                    "flow_id": E2E_FULL_FLOW["id"],
                    "cron_expr": "0 * * * *",  # every hour
                    "name": "E2E Hourly Test Schedule",
                    "enabled": False,
                },
            )
            assert resp.status_code == 201
            sched = resp.json()
            assert "id" in sched  # Gate 2: ID always returned
            sched_id = sched["id"]

            # Verify it appears in the list
            resp = client.get(
                "/api/v1/schedules",
                params={"flow_id": E2E_FULL_FLOW["id"]},
            )
            assert resp.status_code == 200
            items = resp.json()
            sched_ids = [s["id"] for s in items]
            assert sched_id in sched_ids  # Gate 2: created schedule in list

            # Clean up
            resp = client.delete(f"/api/v1/schedules/{sched_id}")
            assert resp.status_code == 204


# ===========================================================================
# Gate D — Marketplace: Publish → Search → Install
# ===========================================================================


class TestMarketplaceIntegration:
    """Publish the full-session flow to marketplace and install it."""

    def test_publish_search_install_lifecycle(self):
        """Full marketplace lifecycle: publish → search → install → new flow in DB."""
        with TestClient(app) as client:
            token = _get_token(client)
            auth = {"Authorization": f"Bearer {token}"}

            # 1. Create the flow (auth required after user exists — bootstrap off)
            resp = client.post("/api/v1/flows", json=E2E_FULL_FLOW, headers=auth)
            assert resp.status_code == 201

            # 2. Publish to marketplace
            resp = client.post(
                "/api/v1/marketplace/publish",
                json={
                    "flow_id": E2E_FULL_FLOW["id"],
                    "name": "Full Session Pipeline",
                    "description": "All node types: webhook, LLM, HTTP, error handler.",
                    "category": "devops",
                    "author": "e2e-test",
                    "tags": ["integration", "all-nodes"],
                },
                headers=auth,
            )
            assert resp.status_code == 201, f"Publish failed: {resp.text}"
            listing = resp.json()
            assert "id" in listing  # Gate 2: listing ID returned
            listing_id = listing["id"]
            assert listing["install_count"] == 0

            # 3. Search — should appear in results
            resp = client.get(
                "/api/v1/marketplace/search",
                params={"q": "Full Session", "category": "devops"},
            )
            assert resp.status_code == 200
            search_body = resp.json()
            assert "items" in search_body
            assert search_body["total"] >= 1  # Gate 2: our listing must appear
            ids_found = [item["id"] for item in search_body["items"]]
            assert listing_id in ids_found

            # 4. Featured — listing should appear (it's the only one)
            resp = client.get("/api/v1/marketplace/featured")
            assert resp.status_code == 200
            featured = resp.json()
            assert len(featured) >= 1  # Gate 2: at least one featured listing

            # 5. Install — clones the flow
            resp = client.post(
                f"/api/v1/marketplace/install/{listing_id}",
                json={"flow_name": "Installed Pipeline Copy"},
                headers=auth,
            )
            assert resp.status_code == 201, f"Install failed: {resp.text}"
            install_result = resp.json()
            # Install endpoint returns {flow_id, listing_id, listing_name, message}
            assert "flow_id" in install_result  # Gate 2: new flow ID returned
            installed_flow_id = install_result["flow_id"]
            assert installed_flow_id != E2E_FULL_FLOW["id"]  # different ID

            # 6. Installed flow appears in flows list
            resp = client.get("/api/v1/flows", headers=auth)
            assert resp.status_code == 200
            flows = resp.json()
            flow_list = flows.get("items", flows) if isinstance(flows, dict) else flows
            flow_ids = [f["id"] for f in flow_list]
            assert installed_flow_id in flow_ids  # Gate 2: new flow in DB

            # 7. Install count incremented
            resp = client.get(
                "/api/v1/marketplace/search",
                params={"q": "Full Session"},
            )
            updated = next((i for i in resp.json()["items"] if i["id"] == listing_id), None)
            assert updated is not None
            assert updated["install_count"] >= 1  # Gate 2: install count updated
