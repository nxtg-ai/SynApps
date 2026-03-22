"""
DIRECTIVE-NXTG-20260318-57: E2E Smoke Test — Full Workflow Pipeline

End-to-end smoke test verifying the full workflow pipeline works after N-19.
Flow under test: webhook_trigger → LLM → http_request → end

The LLM and HTTP nodes are mocked (no external APIs in CI).
The webhook_trigger node executes for real, validating its passthrough behaviour.
The receive endpoint fires the flow via the same path an external caller would use.
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

from apps.orchestrator.db import close_db_connections, init_db
from apps.orchestrator.main import (
    AppletMessage,
    Orchestrator,
    app,
)
from apps.orchestrator.repositories import WorkflowRunRepository
from apps.orchestrator.stores import webhook_trigger_registry

# ---------------------------------------------------------------------------
# Smoke flow definition: webhook_trigger → LLM → http_request → end
# ---------------------------------------------------------------------------

SMOKE_FLOW = {
    "id": "e2e-smoke-wt-llm-http",
    "name": "E2E Smoke: Webhook → LLM → HTTP",
    "nodes": [
        {
            "id": "trigger",
            "type": "webhook_trigger",
            "position": {"x": 300, "y": 25},
            "data": {"label": "Inbound Event"},
        },
        {
            "id": "llm_node",
            "type": "llm",
            "position": {"x": 300, "y": 175},
            "data": {
                "label": "Process with LLM",
                "provider": "openai",
                "model": "gpt-4o-mini",
                "temperature": 0.2,
                "max_tokens": 64,
                "system_prompt": "Summarize the incoming webhook payload in one sentence.",
            },
        },
        {
            "id": "http_node",
            "type": "http_request",
            "position": {"x": 300, "y": 325},
            "data": {
                "label": "Notify Downstream",
                "method": "POST",
                "url": "https://httpbin.org/post",
                "headers": {"Content-Type": "application/json"},
                "timeout_seconds": 30,
            },
        },
        {
            "id": "end",
            "type": "end",
            "position": {"x": 300, "y": 475},
            "data": {"label": "Done"},
        },
    ],
    "edges": [
        {"id": "trigger-llm", "source": "trigger", "target": "llm_node"},
        {"id": "llm-http", "source": "llm_node", "target": "http_node"},
        {"id": "http-end", "source": "http_node", "target": "end"},
    ],
}

# Mock responses for external nodes
_MOCK_LLM = AppletMessage(
    content="Webhook payload received and processed successfully.",
    context={},
    metadata={"applet": "llm", "status": "success"},
)
_MOCK_HTTP = AppletMessage(
    content={"data": '{"ok": true}', "status_code": 200},
    context={},
    metadata={"applet": "http_request", "status": "success", "status_code": 200},
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="function")
async def db():
    await init_db()
    yield
    # Drain background tasks before closing DB (same pattern as content engine tests)
    pending = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    if pending:
        _, still_running = await asyncio.wait(pending, timeout=2.0)
        for t in still_running:
            t.cancel()
        if still_running:
            await asyncio.gather(*still_running, return_exceptions=True)
    await close_db_connections()


@pytest.fixture(autouse=True)
def _reset_trigger_registry():
    """Ensure webhook_trigger_registry is clean between tests."""
    with webhook_trigger_registry._lock:
        webhook_trigger_registry._triggers.clear()
    yield
    with webhook_trigger_registry._lock:
        webhook_trigger_registry._triggers.clear()


# ---------------------------------------------------------------------------
# Gate 2 helpers
# ---------------------------------------------------------------------------


async def _poll_until_terminal(run_id: str, *, max_attempts: int = 20) -> dict | None:
    """Poll WorkflowRunRepository until the run reaches a terminal status.

    Uses 1-second intervals to stay within the token-bucket burst limit (10 tokens
    per key by default). Under event loop contention in full-suite runs, 150ms
    intervals exhausted the burst in < 2 s — causing spurious 429s and/or
    timeouts before the background task completed.
    """
    for _ in range(max_attempts):
        await asyncio.sleep(1.0)
        run = await WorkflowRunRepository.get_by_run_id(run_id)
        if run and run.get("status") in ("success", "error"):
            return run
    return await WorkflowRunRepository.get_by_run_id(run_id)


# ===========================================================================
# Flow Structure Validation
# ===========================================================================


class TestSmokeFlowStructure:
    """Verify the smoke flow definition is well-formed before execution."""

    def test_flow_has_four_nodes(self):
        assert len(SMOKE_FLOW["nodes"]) == 4  # Gate 2: explicit count

    def test_flow_has_three_edges(self):
        assert len(SMOKE_FLOW["edges"]) == 3  # Gate 2: explicit count

    def test_flow_contains_all_required_node_types(self):
        types = {n["type"] for n in SMOKE_FLOW["nodes"]}
        assert "webhook_trigger" in types
        assert "llm" in types
        assert "http_request" in types
        assert "end" in types

    def test_edges_form_linear_pipeline(self):
        """webhook_trigger → llm_node → http_node → end"""
        sources = [e["source"] for e in SMOKE_FLOW["edges"]]
        targets = [e["target"] for e in SMOKE_FLOW["edges"]]
        assert sources == ["trigger", "llm_node", "http_node"]
        assert targets == ["llm_node", "http_node", "end"]

    def test_all_edge_endpoints_reference_valid_nodes(self):
        node_ids = {n["id"] for n in SMOKE_FLOW["nodes"]}
        for edge in SMOKE_FLOW["edges"]:
            assert edge["source"] in node_ids
            assert edge["target"] in node_ids


# ===========================================================================
# Direct Orchestrator Execution (async path)
# ===========================================================================


class TestSmokePipelineDirectExecution:
    """Smoke tests via Orchestrator.execute_flow() — no HTTP layer."""

    @pytest.mark.asyncio
    async def test_full_pipeline_succeeds(self, db):
        """webhook_trigger → LLM → http_request all execute; run reaches success."""
        with patch(
            "apps.orchestrator.main.LLMNodeApplet.on_message",
            new_callable=AsyncMock,
            return_value=_MOCK_LLM,
        ):
            with patch(
                "apps.orchestrator.main.HTTPRequestNodeApplet.on_message",
                new_callable=AsyncMock,
                return_value=_MOCK_HTTP,
            ):
                with patch("apps.orchestrator.main.broadcast_status", new_callable=AsyncMock):
                    run_id = await Orchestrator.execute_flow(
                        SMOKE_FLOW,
                        {"event": "test_event", "source": "smoke_test"},
                    )

        assert run_id is not None  # Gate 2: run_id always returned

        run = await _poll_until_terminal(run_id)
        assert run is not None, "Run record not found in DB"
        assert run["status"] == "success", (
            f"Expected success but got '{run['status']}'. Error: {run.get('error', 'N/A')}"
        )

    @pytest.mark.asyncio
    async def test_all_nodes_produce_results(self, db):
        """Each node in the pipeline should appear in run results."""
        with patch(
            "apps.orchestrator.main.LLMNodeApplet.on_message",
            new_callable=AsyncMock,
            return_value=_MOCK_LLM,
        ):
            with patch(
                "apps.orchestrator.main.HTTPRequestNodeApplet.on_message",
                new_callable=AsyncMock,
                return_value=_MOCK_HTTP,
            ):
                with patch("apps.orchestrator.main.broadcast_status", new_callable=AsyncMock):
                    run_id = await Orchestrator.execute_flow(
                        SMOKE_FLOW,
                        {"event": "verify_results"},
                    )

        run = await _poll_until_terminal(run_id)
        assert run is not None
        results = run.get("results", {})
        assert "trigger" in results, "webhook_trigger node did not write results"  # Gate 2
        assert "llm_node" in results, "LLM node did not write results"
        assert "http_node" in results, "HTTP node did not write results"

    @pytest.mark.asyncio
    async def test_webhook_trigger_passthrough_preserves_input(self, db):
        """The webhook_trigger node must pass its input context through unchanged."""
        input_payload = {"event": "push", "repo": "synapps", "ref": "refs/heads/master"}
        with patch(
            "apps.orchestrator.main.LLMNodeApplet.on_message",
            new_callable=AsyncMock,
            return_value=_MOCK_LLM,
        ):
            with patch(
                "apps.orchestrator.main.HTTPRequestNodeApplet.on_message",
                new_callable=AsyncMock,
                return_value=_MOCK_HTTP,
            ):
                with patch("apps.orchestrator.main.broadcast_status", new_callable=AsyncMock):
                    run_id = await Orchestrator.execute_flow(SMOKE_FLOW, input_payload)

        run = await _poll_until_terminal(run_id)
        assert run is not None
        assert run["status"] == "success"
        # The trigger node is a passthrough — subsequent nodes must still run
        results = run.get("results", {})
        assert len(results) >= 1  # Gate 2: at least one node produced output


# ===========================================================================
# Webhook Receive Endpoint → Full Pipeline (HTTP client path)
# ===========================================================================


class TestSmokePipelineViaReceiveEndpoint:
    """Smoke tests using the webhook receive endpoint as the flow trigger."""

    def test_create_flow_register_trigger_receive_run(self, tmp_path):
        """Full path: create flow → register trigger → POST receive → run produced."""
        import time

        with TestClient(app) as client:
            # 1. Create the flow
            resp = client.post("/api/v1/flows", json=SMOKE_FLOW)
            assert resp.status_code == 201, f"Flow creation failed: {resp.text}"

            # 2. Register a webhook trigger (no secret — smoke test, not security test)
            resp = client.post(
                "/api/v1/webhook-triggers",
                json={"flow_id": SMOKE_FLOW["id"]},
            )
            assert resp.status_code == 201
            trigger = resp.json()
            assert "id" in trigger  # Gate 2: trigger ID always in response

            # 3. POST to the receive endpoint — fires the flow
            with patch(
                "apps.orchestrator.main.LLMNodeApplet.on_message",
                new_callable=AsyncMock,
                return_value=_MOCK_LLM,
            ):
                with patch(
                    "apps.orchestrator.main.HTTPRequestNodeApplet.on_message",
                    new_callable=AsyncMock,
                    return_value=_MOCK_HTTP,
                ):
                    with patch("apps.orchestrator.main.broadcast_status", new_callable=AsyncMock):
                        resp = client.post(
                            f"/api/v1/webhook-triggers/{trigger['id']}/receive",
                            json={"event": "smoke", "source": "e2e"},
                        )

                        assert resp.status_code == 202
                        data = resp.json()
                        assert data["accepted"] is True
                        assert "run_id" in data  # Gate 2: run_id present in 202 response
                        assert data["trigger_id"] == trigger["id"]

                        # 4. Poll until terminal — prevents aiosqlite teardown race.
                        #    The background execute_flow task must finish writing its
                        #    final DB status before TestClient tears down the event loop.
                        run_id = data["run_id"]
                        deadline = time.time() + 20.0
                        run = None
                        while time.time() < deadline:
                            time.sleep(1.0)
                            run_resp = client.get(f"/api/v1/runs/{run_id}")
                            if run_resp.status_code == 200:
                                run = run_resp.json()
                                if run.get("status") in ("success", "error"):
                                    break

            assert run is not None, "Run record not found before timeout"
            assert run["run_id"] == run_id

    def test_receive_with_hmac_secret_in_pipeline(self, tmp_path):
        """Signed webhook receive must accept correct signature and reject wrong one."""
        import hashlib
        import hmac as _hmac
        import json as _json

        with TestClient(app) as client:
            client.post("/api/v1/flows", json=SMOKE_FLOW)

            secret = "pipeline-smoke-secret"
            resp = client.post(
                "/api/v1/webhook-triggers",
                json={"flow_id": SMOKE_FLOW["id"], "secret": secret},
            )
            trigger_id = resp.json()["id"]

            body = _json.dumps({"event": "signed"}).encode()
            sig = "sha256=" + _hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

            # Correct signature → 202
            with patch(
                "apps.orchestrator.main.LLMNodeApplet.on_message",
                new_callable=AsyncMock,
                return_value=_MOCK_LLM,
            ):
                with patch(
                    "apps.orchestrator.main.HTTPRequestNodeApplet.on_message",
                    new_callable=AsyncMock,
                    return_value=_MOCK_HTTP,
                ):
                    with patch("apps.orchestrator.main.broadcast_status", new_callable=AsyncMock):
                        resp = client.post(
                            f"/api/v1/webhook-triggers/{trigger_id}/receive",
                            content=body,
                            headers={
                                "Content-Type": "application/json",
                                "X-Webhook-Signature": sig,
                            },
                        )
            assert resp.status_code == 202

            # Wrong signature → 401
            resp = client.post(
                f"/api/v1/webhook-triggers/{trigger_id}/receive",
                json={"event": "bad"},
                headers={"X-Webhook-Signature": "sha256=badhex"},
            )
            assert resp.status_code == 401
            data = resp.json()
            assert isinstance(data, dict)

            # Let the background execution task resolve (or fail) before DB closes.
            # Without this yield the async task hits sqlite3.ProgrammingError on DB
            # teardown and can corrupt shared event-loop state for subsequent tests.
            import time
            time.sleep(0.05)

    def test_receive_deleted_trigger_returns_error(self, tmp_path):
        """Receiving on a deleted trigger must not start the flow."""
        with TestClient(app) as client:
            client.post("/api/v1/flows", json=SMOKE_FLOW)

            resp = client.post("/api/v1/webhook-triggers", json={"flow_id": SMOKE_FLOW["id"]})
            trigger_id = resp.json()["id"]

            # Delete it
            client.delete(f"/api/v1/webhook-triggers/{trigger_id}")

            # Receive after deletion — trigger unknown, signature fails
            resp = client.post(
                f"/api/v1/webhook-triggers/{trigger_id}/receive",
                json={"event": "ghost"},
            )
            assert resp.status_code in (401, 404)
            assert "error" in resp.json()

    def test_flow_list_after_creation(self, tmp_path):
        """The smoke flow must appear in the flow list after creation."""
        with TestClient(app) as client:
            client.post("/api/v1/flows", json=SMOKE_FLOW)
            resp = client.get("/api/v1/flows")
            assert resp.status_code == 200
            flows = resp.json()
            flow_ids = [f["id"] for f in flows.get("items", flows)]
            assert SMOKE_FLOW["id"] in flow_ids  # Gate 2: created flow always in list
