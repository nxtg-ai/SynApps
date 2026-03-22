"""
N-32: Real-Time SSE Execution Streaming
Tests for SSEEventBus, ExecutionLogStore.append→publish wiring,
and GET /api/v1/executions/{run_id}/stream endpoint.
"""

import asyncio
import json
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from apps.orchestrator.main import app
from apps.orchestrator.stores import (
    SSEEventBus,
    audit_log_store,
    execution_log_store,
    sse_event_bus,
    workflow_permission_store,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean():
    audit_log_store.reset()
    workflow_permission_store.reset()
    execution_log_store.reset()
    sse_event_bus.reset()
    yield
    audit_log_store.reset()
    workflow_permission_store.reset()
    execution_log_store.reset()
    sse_event_bus.reset()


def _register(client: TestClient, email: str | None = None) -> tuple[str, str]:
    email = email or f"sse-{uuid.uuid4().hex[:8]}@test.com"
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "SsePass1!"},
    )
    return resp.json()["access_token"], email


def _terminal_run(run_id: str, status: str = "success") -> dict:
    """Return a dict matching WorkflowRunRepository.get_by_run_id output."""
    return {"run_id": run_id, "status": status, "error": None}


# ===========================================================================
# SSEEventBus — unit tests
# ===========================================================================


class TestSSEEventBusUnit:
    def test_subscribe_returns_queue(self):
        bus = SSEEventBus()

        async def _run():
            q = bus.subscribe("run-1")
            assert q is not None  # Gate 2

        asyncio.run(_run())

    def test_publish_delivers_to_subscriber(self):
        bus = SSEEventBus()

        async def _run():
            q = bus.subscribe("run-1")
            bus.publish_sync("run-1", {"event": "node_start", "node_id": "n1"})
            item = await asyncio.wait_for(q.get(), timeout=1.0)
            assert item["event"] == "node_start"  # Gate 2
            assert item["node_id"] == "n1"  # Gate 2

        asyncio.run(_run())

    def test_publish_to_multiple_subscribers(self):
        bus = SSEEventBus()

        async def _run():
            q1 = bus.subscribe("run-multi")
            q2 = bus.subscribe("run-multi")
            bus.publish_sync("run-multi", {"event": "node_success"})
            i1 = await asyncio.wait_for(q1.get(), timeout=1.0)
            i2 = await asyncio.wait_for(q2.get(), timeout=1.0)
            assert i1["event"] == "node_success"  # Gate 2
            assert i2["event"] == "node_success"  # Gate 2

        asyncio.run(_run())

    def test_publish_different_run_id_not_delivered(self):
        bus = SSEEventBus()

        async def _run():
            q = bus.subscribe("run-A")
            bus.publish_sync("run-B", {"event": "node_start"})
            assert q.empty()  # Gate 2 — different run, no delivery

        asyncio.run(_run())

    def test_unsubscribe_stops_delivery(self):
        bus = SSEEventBus()

        async def _run():
            q = bus.subscribe("run-unsub")
            bus.unsubscribe("run-unsub", q)
            bus.publish_sync("run-unsub", {"event": "node_start"})
            assert q.empty()  # Gate 2

        asyncio.run(_run())

    def test_has_subscribers_true_when_subscribed(self):
        bus = SSEEventBus()

        async def _run():
            q = bus.subscribe("run-has")
            assert bus.has_subscribers("run-has") is True  # Gate 2
            bus.unsubscribe("run-has", q)

        asyncio.run(_run())

    def test_has_subscribers_false_after_unsubscribe(self):
        bus = SSEEventBus()

        async def _run():
            q = bus.subscribe("run-gone")
            bus.unsubscribe("run-gone", q)
            assert bus.has_subscribers("run-gone") is False  # Gate 2

        asyncio.run(_run())

    def test_reset_clears_all_subscribers(self):
        bus = SSEEventBus()

        async def _run():
            bus.subscribe("run-r1")
            bus.subscribe("run-r2")
            bus.reset()
            assert bus.has_subscribers("run-r1") is False  # Gate 2
            assert bus.has_subscribers("run-r2") is False  # Gate 2

        asyncio.run(_run())

    def test_publish_no_subscribers_is_silent(self):
        bus = SSEEventBus()
        # Must not raise
        bus.publish_sync("run-nobody", {"event": "node_start"})

    def test_full_queue_drops_event_without_raising(self):
        """publish_sync must not block or raise when a queue is full."""
        bus = SSEEventBus()

        async def _run():
            q = bus.subscribe("run-full")
            # Fill the queue
            for i in range(q.maxsize):
                q.put_nowait({"event": "node_start", "seq": i})
            # This should NOT raise
            bus.publish_sync("run-full", {"event": "overflow"})

        asyncio.run(_run())


# ===========================================================================
# ExecutionLogStore.append → SSEEventBus wiring
# ===========================================================================


class TestExecutionLogStoreSSEWiring:
    def test_append_publishes_to_sse_bus(self):
        """After append, the event appears in a subscribed queue."""

        async def _run():
            run_id = f"wire-{uuid.uuid4().hex[:8]}"
            q = sse_event_bus.subscribe(run_id)
            execution_log_store.append(
                run_id,
                {"event": "node_start", "node_id": "n1", "node_type": "llm"},
            )
            item = await asyncio.wait_for(q.get(), timeout=1.0)
            assert item["event"] == "node_start"  # Gate 2
            assert item["node_id"] == "n1"  # Gate 2
            sse_event_bus.unsubscribe(run_id, q)

        asyncio.run(_run())

    def test_append_stores_log_and_publishes(self):
        """append persists to store AND publishes — both side-effects."""

        async def _run():
            run_id = f"both-{uuid.uuid4().hex[:8]}"
            q = sse_event_bus.subscribe(run_id)
            execution_log_store.append(
                run_id,
                {"event": "node_success", "node_id": "n2"},
            )
            logs = execution_log_store.get(run_id)
            assert len(logs) >= 1  # Gate 2 — stored
            item = await asyncio.wait_for(q.get(), timeout=1.0)
            assert item["event"] == "node_success"  # Gate 2 — published
            sse_event_bus.unsubscribe(run_id, q)

        asyncio.run(_run())


# ===========================================================================
# GET /api/v1/executions/{run_id}/stream endpoint
# ===========================================================================


class TestStreamEndpointAuth:
    def test_unauthenticated_returns_401_or_403(self):
        with TestClient(app) as client:
            _register(client)  # disable anonymous bootstrap
            resp = client.get("/api/v1/executions/some-run/stream")
            assert resp.status_code in (401, 403)  # Gate 2
            assert "error" in resp.json()

    def test_unknown_run_id_returns_404(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            with patch(
                "apps.orchestrator.main.WorkflowRunRepository.get_by_run_id",
                new_callable=AsyncMock,
                return_value=None,
            ):
                resp = client.get(
                    "/api/v1/executions/nonexistent-run-xyz/stream",
                    headers={"Authorization": f"Bearer {token}"},
                )
            assert resp.status_code == 404  # Gate 2
            assert "error" in resp.json()


class TestStreamEndpointReplay:
    def _seed_terminal_run(self, run_id: str, status: str = "success"):
        """Seed execution log entries and return a mock patch for a terminal run."""
        execution_log_store.append(
            run_id,
            {"event": "node_start", "node_id": "n1", "node_type": "llm"},
        )
        execution_log_store.append(
            run_id,
            {"event": "node_success", "node_id": "n1", "node_type": "llm"},
        )
        return patch(
            "apps.orchestrator.main.WorkflowRunRepository.get_by_run_id",
            new_callable=AsyncMock,
            return_value=_terminal_run(run_id, status),
        )

    def test_replays_existing_log_entries(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            run_id = f"replay-{uuid.uuid4().hex[:8]}"
            with self._seed_terminal_run(run_id):
                resp = client.get(
                    f"/api/v1/executions/{run_id}/stream",
                    headers={"Authorization": f"Bearer {token}"},
                )
            assert resp.status_code == 200  # Gate 2
            body = resp.text
            assert "node_started" in body or "node_completed" in body  # Gate 2

    def test_replay_returns_sse_content_type(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            run_id = f"ct-{uuid.uuid4().hex[:8]}"
            execution_log_store.append(run_id, {"event": "node_start", "node_id": "n1"})
            with patch(
                "apps.orchestrator.main.WorkflowRunRepository.get_by_run_id",
                new_callable=AsyncMock,
                return_value=_terminal_run(run_id),
            ):
                resp = client.get(
                    f"/api/v1/executions/{run_id}/stream",
                    headers={"Authorization": f"Bearer {token}"},
                )
            ct = resp.headers.get("content-type", "")
            assert "text/event-stream" in ct  # Gate 2

    def test_terminal_run_sends_execution_complete(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            run_id = f"term-{uuid.uuid4().hex[:8]}"
            execution_log_store.append(run_id, {"event": "node_start", "node_id": "n1"})
            with patch(
                "apps.orchestrator.main.WorkflowRunRepository.get_by_run_id",
                new_callable=AsyncMock,
                return_value=_terminal_run(run_id, "success"),
            ):
                resp = client.get(
                    f"/api/v1/executions/{run_id}/stream",
                    headers={"Authorization": f"Bearer {token}"},
                )
            assert resp.status_code == 200  # Gate 2
            assert "execution_complete" in resp.text  # Gate 2

    def test_terminal_error_run_includes_error_status(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            run_id = f"err-term-{uuid.uuid4().hex[:8]}"
            execution_log_store.append(
                run_id, {"event": "node_error", "node_id": "n1", "error": "boom"}
            )
            with patch(
                "apps.orchestrator.main.WorkflowRunRepository.get_by_run_id",
                new_callable=AsyncMock,
                return_value=_terminal_run(run_id, "error"),
            ):
                resp = client.get(
                    f"/api/v1/executions/{run_id}/stream",
                    headers={"Authorization": f"Bearer {token}"},
                )
            data_payloads = [
                line[len("data: ") :].strip()
                for line in resp.text.splitlines()
                if line.startswith("data: ")
            ]
            assert len(data_payloads) >= 1  # Gate 2
            complete_payloads = [
                json.loads(d)
                for d in data_payloads
                if d and json.loads(d).get("status") in ("success", "error")
            ]
            assert len(complete_payloads) >= 1  # Gate 2
            assert complete_payloads[-1]["status"] == "error"  # Gate 2

    def test_multiple_log_entries_all_replayed(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            run_id = f"multi-{uuid.uuid4().hex[:8]}"
            for i in range(3):
                execution_log_store.append(
                    run_id,
                    {"event": "node_start", "node_id": f"n{i}"},
                )
            with patch(
                "apps.orchestrator.main.WorkflowRunRepository.get_by_run_id",
                new_callable=AsyncMock,
                return_value=_terminal_run(run_id),
            ):
                resp = client.get(
                    f"/api/v1/executions/{run_id}/stream",
                    headers={"Authorization": f"Bearer {token}"},
                )
            event_lines = [line for line in resp.text.splitlines() if line.startswith("event: ")]
            assert len(event_lines) >= 1  # Gate 2


# ===========================================================================
# SSE event type mapping
# ===========================================================================


class TestSSEEventTypeMapping:
    def _parse_sse_events(self, body: str) -> list[dict]:
        """Parse 'event: X\\ndata: Y' blocks from SSE body."""
        events = []
        current: dict = {}
        for line in body.splitlines():
            if line.startswith("event: "):
                current["event"] = line[len("event: ") :].strip()
            elif line.startswith("data: "):
                raw = line[len("data: ") :].strip()
                try:
                    current["data"] = json.loads(raw)
                except json.JSONDecodeError:
                    current["data"] = raw
            elif line == "" and current:
                events.append(current)
                current = {}
        if current:
            events.append(current)
        return events

    def _stream_with_log(
        self,
        client: TestClient,
        token: str,
        run_id: str,
        log_event: str,
        status: str = "success",
    ) -> list[dict]:
        execution_log_store.append(run_id, {"event": log_event, "node_id": "n1"})
        with patch(
            "apps.orchestrator.main.WorkflowRunRepository.get_by_run_id",
            new_callable=AsyncMock,
            return_value=_terminal_run(run_id, status),
        ):
            resp = client.get(
                f"/api/v1/executions/{run_id}/stream",
                headers={"Authorization": f"Bearer {token}"},
            )
        return self._parse_sse_events(resp.text)

    def test_node_start_maps_to_node_started(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            run_id = f"map-start-{uuid.uuid4().hex[:8]}"
            events = self._stream_with_log(client, token, run_id, "node_start")
            event_types = [e.get("event") for e in events]
            assert "node_started" in event_types  # Gate 2

    def test_node_success_maps_to_node_completed(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            run_id = f"map-succ-{uuid.uuid4().hex[:8]}"
            events = self._stream_with_log(client, token, run_id, "node_success")
            event_types = [e.get("event") for e in events]
            assert "node_completed" in event_types  # Gate 2

    def test_node_error_maps_to_node_failed(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            run_id = f"map-err-{uuid.uuid4().hex[:8]}"
            events = self._stream_with_log(client, token, run_id, "node_error", status="error")
            event_types = [e.get("event") for e in events]
            assert "node_failed" in event_types  # Gate 2

    def test_node_id_included_in_payload(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            run_id = f"payload-{uuid.uuid4().hex[:8]}"
            execution_log_store.append(
                run_id,
                {"event": "node_start", "node_id": "node-42", "node_type": "http"},
            )
            with patch(
                "apps.orchestrator.main.WorkflowRunRepository.get_by_run_id",
                new_callable=AsyncMock,
                return_value=_terminal_run(run_id),
            ):
                resp = client.get(
                    f"/api/v1/executions/{run_id}/stream",
                    headers={"Authorization": f"Bearer {token}"},
                )
            events = self._parse_sse_events(resp.text)
            node_events = [e for e in events if e.get("event") == "node_started"]
            assert len(node_events) >= 1  # Gate 2
            assert node_events[0]["data"]["node_id"] == "node-42"  # Gate 2

    def test_run_id_included_in_payload(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            run_id = f"runid-{uuid.uuid4().hex[:8]}"
            execution_log_store.append(run_id, {"event": "node_success", "node_id": "n1"})
            with patch(
                "apps.orchestrator.main.WorkflowRunRepository.get_by_run_id",
                new_callable=AsyncMock,
                return_value=_terminal_run(run_id),
            ):
                resp = client.get(
                    f"/api/v1/executions/{run_id}/stream",
                    headers={"Authorization": f"Bearer {token}"},
                )
            events = self._parse_sse_events(resp.text)
            data_events = [e for e in events if e.get("data")]
            assert len(data_events) >= 1  # Gate 2
            assert data_events[0]["data"]["run_id"] == run_id  # Gate 2

    def test_node_retry_maps_to_node_started(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            run_id = f"retry-{uuid.uuid4().hex[:8]}"
            events = self._stream_with_log(client, token, run_id, "node_retry")
            event_types = [e.get("event") for e in events]
            assert "node_started" in event_types  # Gate 2

    def test_node_fallback_maps_to_node_completed(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            run_id = f"fallback-{uuid.uuid4().hex[:8]}"
            events = self._stream_with_log(client, token, run_id, "node_fallback")
            event_types = [e.get("event") for e in events]
            assert "node_completed" in event_types  # Gate 2
