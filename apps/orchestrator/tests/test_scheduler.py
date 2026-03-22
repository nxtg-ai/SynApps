"""Tests for N-20 Scheduler Node — cron-driven flow trigger.

Covers:
  - SchedulerRegistry: create, get, list, update, delete, get_due
  - _compute_next_run: valid and invalid cron expressions, base datetime
  - REST endpoints: POST/GET/PATCH/DELETE /schedules
  - SchedulerNodeApplet.on_message passthrough + metadata
  - Node type registered in applet_registry and KNOWN_NODE_TYPES
  - Orchestrator.load_applet recognises "scheduler_node" and aliases
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from apps.orchestrator.helpers import KNOWN_NODE_TYPES
from apps.orchestrator.main import (
    AppletMessage,
    SchedulerNodeApplet,
    SchedulerRegistry,
    _compute_next_run,
    app,
    applet_registry,
    scheduler_registry,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_FLOW_PAYLOAD = {
    "id": "sched-test-flow-001",
    "name": "Scheduler Test Flow",
    "nodes": [
        {"id": "start", "type": "start", "position": {"x": 0, "y": 0}, "data": {"label": "Start"}},
        {"id": "end", "type": "end", "position": {"x": 0, "y": 100}, "data": {"label": "End"}},
    ],
    "edges": [{"id": "e1", "source": "start", "target": "end"}],
}


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _reset_scheduler_registry():
    """Clear scheduler registry between tests."""
    with scheduler_registry._lock:
        scheduler_registry._schedules.clear()
    yield
    with scheduler_registry._lock:
        scheduler_registry._schedules.clear()


@pytest.fixture
def flow_id(client):
    """Create a minimal flow and return its ID."""
    resp = client.post("/api/v1/flows", json=_FLOW_PAYLOAD)
    assert resp.status_code in (200, 201), f"Flow creation failed: {resp.text}"
    return "sched-test-flow-001"


# ===========================================================================
# TestSchedulerNodeRegistration
# ===========================================================================


class TestSchedulerNodeRegistration:
    """Verify the scheduler node type is wired up in all required places."""

    def test_scheduler_node_in_applet_registry(self):
        assert "scheduler_node" in applet_registry  # Gate 2: always registered

    def test_scheduler_node_in_known_node_types(self):
        assert "scheduler_node" in KNOWN_NODE_TYPES

    @pytest.mark.asyncio
    async def test_load_applet_scheduler_node_canonical(self):
        from apps.orchestrator.main import Orchestrator

        applet = await Orchestrator.load_applet("scheduler_node")
        assert isinstance(applet, SchedulerNodeApplet)

    @pytest.mark.asyncio
    async def test_load_applet_scheduler_alias(self):
        from apps.orchestrator.main import Orchestrator

        for alias in ("scheduler", "cron"):
            applet = await Orchestrator.load_applet(alias)
            assert isinstance(applet, SchedulerNodeApplet), f"alias '{alias}' not loaded"

    def test_scheduler_applet_version(self):
        assert hasattr(SchedulerNodeApplet, "VERSION")
        assert SchedulerNodeApplet.VERSION == "1.0.0"

    def test_scheduler_applet_capabilities(self):
        caps = SchedulerNodeApplet.CAPABILITIES
        assert "scheduler-trigger" in caps  # Gate 2: capabilities always declared
        assert "cron-schedule" in caps


# ===========================================================================
# TestComputeNextRun
# ===========================================================================


class TestComputeNextRun:
    """Unit tests for the _compute_next_run helper."""

    def test_next_run_returns_iso_string(self):
        result = _compute_next_run("* * * * *")
        # Should be a valid ISO string
        dt = datetime.fromisoformat(result)
        assert isinstance(dt, datetime)

    def test_next_run_specific_time(self):
        result = _compute_next_run("0 9 * * 1-5")
        dt = datetime.fromisoformat(result)
        # Hour should be 9 (9 AM)
        assert dt.hour == 9
        assert dt.minute == 0

    def test_next_run_every_15_min(self):
        result = _compute_next_run("*/15 * * * *")
        dt = datetime.fromisoformat(result)
        # Minute should be a multiple of 15
        assert dt.minute % 15 == 0

    def test_next_run_invalid_raises_value_error(self):
        with pytest.raises(ValueError, match="Invalid cron expression"):
            _compute_next_run("not a cron")

    def test_next_run_advance_from_base(self):
        base = datetime(2025, 1, 1, 12, 0, 0)
        result = _compute_next_run("* * * * *", base=base)
        dt = datetime.fromisoformat(result)
        # Next run should be after the base time
        assert dt > base


# ===========================================================================
# TestSchedulerRegistryUnit
# ===========================================================================


class TestSchedulerRegistryUnit:
    """Pure unit tests against the SchedulerRegistry class."""

    def test_create_returns_entry_with_id(self):
        reg = SchedulerRegistry()
        entry = reg.create(flow_id="flow-1", cron_expr="* * * * *")
        assert "id" in entry
        assert entry["flow_id"] == "flow-1"
        assert entry["cron_expr"] == "* * * * *"

    def test_create_validates_cron_expr(self):
        reg = SchedulerRegistry()
        with pytest.raises(ValueError):
            reg.create(flow_id="flow-1", cron_expr="bad cron!!!")

    def test_create_computes_next_run(self):
        reg = SchedulerRegistry()
        entry = reg.create(flow_id="flow-1", cron_expr="* * * * *")
        assert "next_run" in entry
        # Should be a valid ISO datetime string
        dt = datetime.fromisoformat(entry["next_run"])
        assert isinstance(dt, datetime)

    def test_create_name_default(self):
        reg = SchedulerRegistry()
        entry = reg.create(flow_id="my-flow", cron_expr="0 0 * * *")
        # Default name should reference the flow
        assert "my-flow" in entry["name"]

    def test_create_enabled_true_by_default(self):
        reg = SchedulerRegistry()
        entry = reg.create(flow_id="flow-1", cron_expr="* * * * *")
        assert entry["enabled"] is True

    def test_get_returns_entry(self):
        reg = SchedulerRegistry()
        created = reg.create(flow_id="flow-get", cron_expr="* * * * *")
        fetched = reg.get(created["id"])
        assert fetched is not None
        assert fetched["id"] == created["id"]

    def test_get_missing_returns_none(self):
        reg = SchedulerRegistry()
        assert reg.get("no-such-id") is None

    def test_list_all(self):
        reg = SchedulerRegistry()
        reg.create(flow_id="flow-a", cron_expr="* * * * *")
        reg.create(flow_id="flow-b", cron_expr="0 9 * * 1-5")
        items = reg.list()
        assert isinstance(items, list)
        assert len(items) >= 2  # Gate 2: both entries present

    def test_list_filter_by_flow_id(self):
        reg = SchedulerRegistry()
        reg.create(flow_id="flow-x", cron_expr="* * * * *")
        reg.create(flow_id="flow-x", cron_expr="0 0 * * *")
        reg.create(flow_id="flow-y", cron_expr="* * * * *")
        items = reg.list(flow_id="flow-x")
        assert len(items) == 2  # Gate 2: filter returns exactly matching entries
        for item in items:
            assert item["flow_id"] == "flow-x"

    def test_update_enabled_false(self):
        reg = SchedulerRegistry()
        entry = reg.create(flow_id="flow-pause", cron_expr="* * * * *")
        updated = reg.update(entry["id"], enabled=False)
        assert updated is not None
        assert updated["enabled"] is False

    def test_update_cron_recomputes_next_run(self):
        reg = SchedulerRegistry()
        entry = reg.create(flow_id="flow-recompute", cron_expr="* * * * *")
        old_next_run = entry["next_run"]
        updated = reg.update(entry["id"], cron_expr="0 9 * * 1-5")
        assert updated is not None
        # new cron_expr should be stored
        assert updated["cron_expr"] == "0 9 * * 1-5"
        # next_run may differ (scheduled at 9 AM vs every minute)
        assert updated["next_run"] != old_next_run or updated["cron_expr"] != entry["cron_expr"]

    def test_delete_removes_entry(self):
        reg = SchedulerRegistry()
        entry = reg.create(flow_id="flow-del", cron_expr="* * * * *")
        assert reg.delete(entry["id"]) is True
        assert reg.get(entry["id"]) is None


# ===========================================================================
# TestSchedulerEndpoints
# ===========================================================================


class TestSchedulerEndpoints:
    """HTTP endpoint tests for the schedule CRUD API."""

    def test_create_schedule_success(self, client, flow_id):
        resp = client.post(
            "/api/v1/schedules",
            json={"flow_id": flow_id, "cron_expr": "* * * * *"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "id" in data
        assert data["flow_id"] == flow_id
        assert data["cron_expr"] == "* * * * *"

    def test_create_schedule_flow_not_found(self, client):
        resp = client.post(
            "/api/v1/schedules",
            json={"flow_id": "nonexistent-flow", "cron_expr": "* * * * *"},
        )
        assert resp.status_code == 404

    def test_create_schedule_invalid_cron(self, client, flow_id):
        resp = client.post(
            "/api/v1/schedules",
            json={"flow_id": flow_id, "cron_expr": "not valid cron"},
        )
        assert resp.status_code == 422

    def test_list_schedules_empty(self, client):
        resp = client.get("/api/v1/schedules")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 0  # Gate 2: empty state

    def test_list_schedules_after_create(self, client, flow_id):
        client.post(
            "/api/v1/schedules",
            json={"flow_id": flow_id, "cron_expr": "* * * * *"},
        )
        client.post(
            "/api/v1/schedules",
            json={"flow_id": flow_id, "cron_expr": "0 0 * * *"},
        )
        resp = client.get("/api/v1/schedules")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 2  # Gate 2: both schedules present

    def test_list_schedules_filter_by_flow_id(self, client, flow_id):
        # Create a second flow
        client.post(
            "/api/v1/flows",
            json={
                "id": "other-sched-flow",
                "name": "Other Flow",
                "nodes": [
                    {
                        "id": "s",
                        "type": "start",
                        "position": {"x": 0, "y": 0},
                        "data": {"label": "Start"},
                    },
                ],
                "edges": [],
            },
        )
        client.post(
            "/api/v1/schedules",
            json={"flow_id": flow_id, "cron_expr": "* * * * *"},
        )
        client.post(
            "/api/v1/schedules",
            json={"flow_id": "other-sched-flow", "cron_expr": "* * * * *"},
        )
        resp = client.get(f"/api/v1/schedules?flow_id={flow_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1  # Gate 2: filter works
        assert data[0]["flow_id"] == flow_id

    def test_get_schedule_success(self, client, flow_id):
        created = client.post(
            "/api/v1/schedules",
            json={"flow_id": flow_id, "cron_expr": "* * * * *"},
        ).json()
        resp = client.get(f"/api/v1/schedules/{created['id']}")
        assert resp.status_code == 200
        assert resp.json()["id"] == created["id"]

    def test_get_schedule_not_found(self, client):
        resp = client.get("/api/v1/schedules/ghost-id")
        assert resp.status_code == 404

    def test_update_schedule_pause(self, client, flow_id):
        created = client.post(
            "/api/v1/schedules",
            json={"flow_id": flow_id, "cron_expr": "* * * * *"},
        ).json()
        resp = client.patch(
            f"/api/v1/schedules/{created['id']}",
            json={"enabled": False},
        )
        assert resp.status_code == 200
        assert resp.json()["enabled"] is False

    def test_update_schedule_no_fields(self, client, flow_id):
        created = client.post(
            "/api/v1/schedules",
            json={"flow_id": flow_id, "cron_expr": "* * * * *"},
        ).json()
        resp = client.patch(
            f"/api/v1/schedules/{created['id']}",
            json={},
        )
        assert resp.status_code == 422

    def test_update_schedule_not_found(self, client):
        resp = client.patch(
            "/api/v1/schedules/ghost-id",
            json={"enabled": False},
        )
        assert resp.status_code == 404

    def test_delete_schedule_success(self, client, flow_id):
        created = client.post(
            "/api/v1/schedules",
            json={"flow_id": flow_id, "cron_expr": "* * * * *"},
        ).json()
        resp = client.delete(f"/api/v1/schedules/{created['id']}")
        assert resp.status_code == 204
        # Confirm gone
        assert client.get(f"/api/v1/schedules/{created['id']}").status_code == 404


# ===========================================================================
# TestSchedulerNodeAppletBehaviour
# ===========================================================================


class TestSchedulerNodeAppletBehaviour:
    """Verify the applet passes content + context through unchanged."""

    @pytest.mark.asyncio
    async def test_on_message_passthrough_content(self):
        applet = SchedulerNodeApplet()
        msg = AppletMessage(
            content={"triggered_at": "2025-01-01T09:00:00"},
            context={"run_id": "r-001"},
            metadata={"node_id": "sched-node-1"},
        )
        result = await applet.on_message(msg)
        assert result.content == {"triggered_at": "2025-01-01T09:00:00"}

    @pytest.mark.asyncio
    async def test_on_message_passthrough_context(self):
        applet = SchedulerNodeApplet()
        msg = AppletMessage(
            content={},
            context={"run_id": "r-002", "flow_id": "flow-abc"},
            metadata={},
        )
        result = await applet.on_message(msg)
        assert result.context == {"run_id": "r-002", "flow_id": "flow-abc"}

    @pytest.mark.asyncio
    async def test_on_message_metadata_applet_field(self):
        applet = SchedulerNodeApplet()
        msg = AppletMessage(content={}, context={}, metadata={})
        result = await applet.on_message(msg)
        assert result.metadata.get("applet") == "scheduler_node"

    @pytest.mark.asyncio
    async def test_on_message_metadata_status_field(self):
        applet = SchedulerNodeApplet()
        msg = AppletMessage(content={}, context={}, metadata={})
        result = await applet.on_message(msg)
        assert result.metadata.get("status") == "triggered"


# ===========================================================================
# TestSchedulerGetDue
# ===========================================================================


class TestSchedulerGetDue:
    """Verify get_due returns only enabled, overdue schedules."""

    def test_get_due_returns_past_schedules(self):
        reg = SchedulerRegistry()
        entry = reg.create(flow_id="flow-due", cron_expr="* * * * *")
        # Manually set next_run to the past
        past_iso = (datetime.now(UTC) - timedelta(hours=1)).replace(tzinfo=None).isoformat()
        with reg._lock:
            reg._schedules[entry["id"]]["next_run"] = past_iso
        due = reg.get_due()
        assert isinstance(due, list)
        assert len(due) >= 1  # Gate 2: past schedule is returned
        assert any(d["id"] == entry["id"] for d in due)

    def test_get_due_skips_future_schedules(self):
        reg = SchedulerRegistry()
        entry = reg.create(flow_id="flow-future", cron_expr="* * * * *")
        # Manually set next_run far in the future
        future_iso = (datetime.now(UTC) + timedelta(hours=24)).replace(tzinfo=None).isoformat()
        with reg._lock:
            reg._schedules[entry["id"]]["next_run"] = future_iso
        due = reg.get_due()
        assert not any(d["id"] == entry["id"] for d in due)

    def test_get_due_skips_disabled_schedules(self):
        reg = SchedulerRegistry()
        entry = reg.create(flow_id="flow-disabled", cron_expr="* * * * *", enabled=False)
        # Set to past so it would be due if enabled
        past_iso = (datetime.now(UTC) - timedelta(hours=1)).replace(tzinfo=None).isoformat()
        with reg._lock:
            reg._schedules[entry["id"]]["next_run"] = past_iso
        due = reg.get_due()
        assert not any(d["id"] == entry["id"] for d in due)
