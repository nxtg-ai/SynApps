"""Tests for Execution Dashboard — real-time admin execution monitoring.

Covers:
  - ExecutionDashboardStore unit tests (7 tests)
  - Admin endpoints integration tests (9 tests)
  - Execution registration integration tests (4 tests)

Total: 20 tests.
"""

import time
import uuid

from fastapi.testclient import TestClient

from apps.orchestrator.main import app
from apps.orchestrator.stores import (
    ExecutionDashboardStore,
    execution_dashboard_store,
)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _register(client: TestClient) -> str:
    """Register a non-admin user and return the access_token."""
    email = f"user-{uuid.uuid4().hex[:8]}@example.com"
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Pass1234!"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["access_token"]


def _register_admin(client: TestClient) -> str:
    """Register an admin user (email starts with 'admin') and return the access_token."""
    email = f"admin{uuid.uuid4().hex[:6]}@test.com"
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "P@ss1234"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["access_token"]


# ---------------------------------------------------------------------------
# Unit tests — ExecutionDashboardStore
# ---------------------------------------------------------------------------


class TestExecutionDashboardStore:
    """Unit tests for ExecutionDashboardStore."""

    def test_register_creates_entry_with_correct_fields(self) -> None:
        store = ExecutionDashboardStore()
        entry = store.register(
            run_id="run-1",
            flow_id="flow-1",
            flow_name="My Flow",
            user_id="user-1",
            node_count=5,
            input_size_bytes=128,
        )
        assert entry["run_id"] == "run-1"
        assert entry["flow_id"] == "flow-1"
        assert entry["flow_name"] == "My Flow"
        assert entry["user_id"] == "user-1"
        assert entry["status"] == "running"
        assert entry["node_count"] == 5
        assert entry["completed_nodes"] == 0
        assert entry["input_size_bytes"] == 128
        assert entry["output_size_bytes"] == 0
        assert entry["paused"] is False
        assert entry["killed"] is False
        assert entry["progress_pct"] == 0.0
        assert isinstance(entry["duration_ms"], float)
        assert isinstance(entry["started_at"], float)
        assert isinstance(entry["updated_at"], float)

    def test_update_status_updates_status_and_progress(self) -> None:
        store = ExecutionDashboardStore()
        store.register("run-1", "f1", "Flow", "u1", node_count=4)
        ok = store.update_status("run-1", "completed", completed_nodes=4, output_size_bytes=256)
        assert ok is True
        entry = store.get("run-1")
        assert entry is not None
        assert entry["status"] == "completed"
        assert entry["completed_nodes"] == 4
        assert entry["progress_pct"] == 100.0
        assert entry["output_size_bytes"] == 256

    def test_pause_and_resume_toggle(self) -> None:
        store = ExecutionDashboardStore()
        store.register("run-1", "f1", "Flow", "u1", node_count=2)
        assert store.pause("run-1") is True
        entry = store.get("run-1")
        assert entry is not None
        assert entry["paused"] is True
        assert entry["status"] == "paused"
        assert store.resume("run-1") is True
        entry = store.get("run-1")
        assert entry is not None
        assert entry["paused"] is False
        assert entry["status"] == "running"

    def test_kill_sets_killed_and_status(self) -> None:
        store = ExecutionDashboardStore()
        store.register("run-1", "f1", "Flow", "u1", node_count=2)
        assert store.kill("run-1") is True
        entry = store.get("run-1")
        assert entry is not None
        assert entry["killed"] is True
        assert entry["status"] == "killed"

    def test_list_active_only_returns_running_or_paused(self) -> None:
        store = ExecutionDashboardStore()
        store.register("run-1", "f1", "Flow", "u1", node_count=2)
        store.register("run-2", "f2", "Flow2", "u2", node_count=3)
        store.register("run-3", "f3", "Flow3", "u3", node_count=1)
        store.update_status("run-2", "completed", completed_nodes=3)
        store.pause("run-3")

        active = store.list_active()
        assert isinstance(active, list)
        assert len(active) >= 1  # Gate 2
        active_ids = {e["run_id"] for e in active}
        assert "run-1" in active_ids
        assert "run-3" in active_ids
        assert "run-2" not in active_ids

    def test_list_recent_newest_first(self) -> None:
        store = ExecutionDashboardStore()
        store.register("run-old", "f1", "Old", "u1", node_count=1)
        time.sleep(0.01)
        store.register("run-new", "f2", "New", "u2", node_count=1)

        recent = store.list_recent()
        assert isinstance(recent, list)
        assert len(recent) >= 2  # Gate 2
        assert recent[0]["run_id"] == "run-new"
        assert recent[1]["run_id"] == "run-old"

    def test_stats_returns_active_count(self) -> None:
        store = ExecutionDashboardStore()
        store.register("run-1", "f1", "Flow", "u1", node_count=2)
        store.register("run-2", "f2", "Flow2", "u2", node_count=3)
        store.update_status("run-2", "completed", completed_nodes=3)

        s = store.stats()
        assert s["active_count"] == 1
        assert "total_today" in s
        assert "avg_duration_ms" in s
        assert "kill_count" in s
        assert s["kill_count"] == 0


# ---------------------------------------------------------------------------
# Integration tests — admin endpoints
# ---------------------------------------------------------------------------


class TestAdminEndpoints:
    """Integration tests for /admin/executions endpoints."""

    def test_list_executions_200_for_admin(self) -> None:
        with TestClient(app) as client:
            token = _register_admin(client)
            resp = client.get(
                "/api/v1/admin/executions",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert "items" in data

    def test_list_executions_403_for_regular_user(self) -> None:
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get(
                "/api/v1/admin/executions",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 403

    def test_active_executions_200(self) -> None:
        with TestClient(app) as client:
            token = _register_admin(client)
            resp = client.get(
                "/api/v1/admin/executions/active",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 200
            assert "items" in resp.json()

    def test_stats_has_active_count_key(self) -> None:
        with TestClient(app) as client:
            token = _register_admin(client)
            resp = client.get(
                "/api/v1/admin/executions/stats",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert "active_count" in data

    def test_pause_returns_200(self) -> None:
        execution_dashboard_store.register("run-p1", "f1", "Flow", "u1", node_count=2)
        with TestClient(app) as client:
            token = _register_admin(client)
            resp = client.post(
                "/api/v1/admin/executions/run-p1/pause",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 200
            assert resp.json()["status"] == "paused"

    def test_resume_returns_200(self) -> None:
        execution_dashboard_store.register("run-r1", "f1", "Flow", "u1", node_count=2)
        execution_dashboard_store.pause("run-r1")
        with TestClient(app) as client:
            token = _register_admin(client)
            resp = client.post(
                "/api/v1/admin/executions/run-r1/resume",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 200
            assert resp.json()["status"] == "running"

    def test_kill_returns_200(self) -> None:
        execution_dashboard_store.register("run-k1", "f1", "Flow", "u1", node_count=2)
        with TestClient(app) as client:
            token = _register_admin(client)
            resp = client.post(
                "/api/v1/admin/executions/run-k1/kill",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 200
            assert resp.json()["status"] == "killed"

    def test_get_execution_returns_entry(self) -> None:
        execution_dashboard_store.register("run-g1", "f1", "TestFlow", "u1", node_count=3)
        with TestClient(app) as client:
            token = _register_admin(client)
            resp = client.get(
                "/api/v1/admin/executions/run-g1",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["run_id"] == "run-g1"
            assert data["flow_name"] == "TestFlow"

    def test_get_execution_404_for_unknown(self) -> None:
        with TestClient(app) as client:
            token = _register_admin(client)
            resp = client.get(
                "/api/v1/admin/executions/nonexistent-run",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Integration tests — execution registration
# ---------------------------------------------------------------------------


class TestExecutionRegistration:
    """Tests that executions are registered in the dashboard store."""

    def test_running_flow_appears_in_executions(self) -> None:
        """Registered executions appear in the admin executions list."""
        execution_dashboard_store.register(
            "run-reg1", "f1", "Dashboard Test Flow", "u1", node_count=3
        )
        with TestClient(app) as client:
            token = _register_admin(client)
            dash_resp = client.get(
                "/api/v1/admin/executions",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert dash_resp.status_code == 200
            items = dash_resp.json()["items"]
            assert isinstance(items, list)
            assert len(items) >= 1  # Gate 2: confirm data was not silently lost
            run_ids = [e["run_id"] for e in items]
            assert "run-reg1" in run_ids

    def test_completed_run_has_completed_status(self) -> None:
        """A completed run should show status='completed' in the dashboard."""
        execution_dashboard_store.register("run-c1", "f1", "Flow", "u1", node_count=2)
        execution_dashboard_store.update_status("run-c1", "completed", completed_nodes=2)
        recent = execution_dashboard_store.list_recent()
        assert isinstance(recent, list)
        assert len(recent) >= 1  # Gate 2
        entry = next((e for e in recent if e["run_id"] == "run-c1"), None)
        assert entry is not None
        assert entry["status"] == "completed"

    def test_stats_total_today_increments(self) -> None:
        """Registering executions should increment total_today."""
        execution_dashboard_store.register("run-t1", "f1", "Flow1", "u1", node_count=1)
        execution_dashboard_store.register("run-t2", "f2", "Flow2", "u2", node_count=1)
        stats = execution_dashboard_store.stats()
        assert stats["total_today"] >= 2

    def test_active_count_zero_when_no_running(self) -> None:
        """active_count should be 0 when no executions are running."""
        stats = execution_dashboard_store.stats()
        assert stats["active_count"] == 0
