"""
N-33: Workflow Analytics Dashboard — Execution Insights
Tests for WorkflowAnalyticsDashboard and GET /analytics/dashboard endpoint.
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from apps.orchestrator.main import app
from apps.orchestrator.request_models import WorkflowAnalyticsDashboard
from apps.orchestrator.stores import (
    audit_log_store,
    cost_tracker_store,
    execution_log_store,
    sse_event_bus,
    workflow_permission_store,
)


@pytest.fixture(autouse=True)
def _clean():
    audit_log_store.reset()
    workflow_permission_store.reset()
    execution_log_store.reset()
    sse_event_bus.reset()
    cost_tracker_store.reset()
    yield
    audit_log_store.reset()
    workflow_permission_store.reset()
    execution_log_store.reset()
    sse_event_bus.reset()
    cost_tracker_store.reset()


def _register(client: TestClient, email: str | None = None) -> str:
    email = email or f"dash-{uuid.uuid4().hex[:8]}@test.com"
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "DashPass1!"},
    )
    return resp.json()["access_token"]


def _mock_runs(runs: list[dict]):
    return patch(
        "apps.orchestrator.main.WorkflowRunRepository.get_all",
        new_callable=AsyncMock,
        return_value=runs,
    )


# ===========================================================================
# WorkflowAnalyticsDashboard unit tests
# ===========================================================================


class TestTopWorkflows:
    @pytest.mark.asyncio
    async def test_top_workflows_returns_list(self):
        with _mock_runs([]):
            result = await WorkflowAnalyticsDashboard.top_workflows()
        assert isinstance(result, list)  # Gate 2

    @pytest.mark.asyncio
    async def test_top_workflows_sorted_by_run_count(self):
        import time

        now = time.time()
        runs = [
            {"flow_id": "flow-A", "status": "success", "start_time": now, "end_time": now + 1}
        ] * 5 + [
            {"flow_id": "flow-B", "status": "success", "start_time": now, "end_time": now + 1}
        ] * 3
        with _mock_runs(runs):
            result = await WorkflowAnalyticsDashboard.top_workflows()
        assert len(result) >= 1  # Gate 2
        assert result[0]["flow_id"] == "flow-A"  # Gate 2
        assert result[0]["run_count"] == 5  # Gate 2

    @pytest.mark.asyncio
    async def test_top_workflows_respects_limit(self):
        import time

        now = time.time()
        runs = [
            {"flow_id": f"flow-{i}", "status": "success", "start_time": now, "end_time": now + 1}
            for i in range(20)
        ]
        with _mock_runs(runs):
            result = await WorkflowAnalyticsDashboard.top_workflows(limit=5)
        assert len(result) <= 5  # Gate 2


class TestAvgDurationByNodeType:
    def test_returns_empty_when_no_logs(self):
        import asyncio

        result = asyncio.run(WorkflowAnalyticsDashboard.avg_duration_by_node_type())
        assert isinstance(result, list)  # Gate 2

    def test_aggregates_by_node_type(self):
        import asyncio

        run_id = f"dur-{uuid.uuid4().hex[:8]}"
        execution_log_store.append(
            run_id, {"event": "node_success", "node_type": "llm", "duration_ms": 200.0}
        )
        execution_log_store.append(
            run_id, {"event": "node_success", "node_type": "llm", "duration_ms": 400.0}
        )
        execution_log_store.append(
            run_id, {"event": "node_success", "node_type": "http", "duration_ms": 100.0}
        )
        result = asyncio.run(WorkflowAnalyticsDashboard.avg_duration_by_node_type())
        assert len(result) >= 1  # Gate 2
        llm_entries = [r for r in result if r["node_type"] == "llm"]
        assert len(llm_entries) >= 1  # Gate 2
        assert llm_entries[0]["avg_duration_ms"] == 300.0  # Gate 2 — (200+400)/2


class TestErrorRateTrends:
    @pytest.mark.asyncio
    async def test_returns_24_hour_buckets(self):
        with _mock_runs([]):
            result = await WorkflowAnalyticsDashboard.error_rate_trends()
        assert len(result) == 24  # Gate 2

    @pytest.mark.asyncio
    async def test_counts_errors_in_current_hour(self):
        import time

        now = time.time()
        runs = [
            {"flow_id": "f1", "status": "error", "start_time": now},
            {"flow_id": "f1", "status": "success", "start_time": now},
        ]
        with _mock_runs(runs):
            result = await WorkflowAnalyticsDashboard.error_rate_trends()
        # Current hour should have 2 total, 1 error
        current_hour = result[-1]  # last = most recent
        assert current_hour["total"] == 2  # Gate 2
        assert current_hour["errors"] == 1  # Gate 2
        assert current_hour["error_rate"] == 0.5  # Gate 2


class TestPeakUsageHours:
    @pytest.mark.asyncio
    async def test_returns_24_hours(self):
        with _mock_runs([]):
            result = await WorkflowAnalyticsDashboard.peak_usage_hours()
        assert len(result) == 24  # Gate 2

    @pytest.mark.asyncio
    async def test_hour_0_to_23(self):
        with _mock_runs([]):
            result = await WorkflowAnalyticsDashboard.peak_usage_hours()
        hours = [r["hour"] for r in result]
        assert 0 in hours  # Gate 2
        assert 23 in hours  # Gate 2


# ===========================================================================
# GET /analytics/dashboard endpoint
# ===========================================================================


class TestAnalyticsDashboardEndpoint:
    def test_requires_auth(self):
        with TestClient(app) as client:
            _register(client)
            resp = client.get("/api/v1/analytics/dashboard")
            assert resp.status_code in (401, 403)  # Gate 2

    def test_returns_200_with_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            with _mock_runs([]):
                resp = client.get(
                    "/api/v1/analytics/dashboard",
                    headers={"Authorization": f"Bearer {token}"},
                )
            assert resp.status_code == 200  # Gate 2

    def test_response_contains_all_sections(self):
        with TestClient(app) as client:
            token = _register(client)
            with _mock_runs([]):
                resp = client.get(
                    "/api/v1/analytics/dashboard",
                    headers={"Authorization": f"Bearer {token}"},
                )
            body = resp.json()
            assert "top_workflows" in body  # Gate 2
            assert "avg_duration_by_node_type" in body  # Gate 2
            assert "error_rate_trends" in body  # Gate 2
            assert "peak_usage_hours" in body  # Gate 2

    def test_top_workflows_is_list(self):
        with TestClient(app) as client:
            token = _register(client)
            with _mock_runs([]):
                resp = client.get(
                    "/api/v1/analytics/dashboard",
                    headers={"Authorization": f"Bearer {token}"},
                )
            assert isinstance(resp.json()["top_workflows"], list)  # Gate 2

    def test_error_rate_trends_has_24_buckets(self):
        with TestClient(app) as client:
            token = _register(client)
            with _mock_runs([]):
                resp = client.get(
                    "/api/v1/analytics/dashboard",
                    headers={"Authorization": f"Bearer {token}"},
                )
            trends = resp.json()["error_rate_trends"]
            assert len(trends) == 24  # Gate 2

    def test_peak_usage_hours_has_24_entries(self):
        with TestClient(app) as client:
            token = _register(client)
            with _mock_runs([]):
                resp = client.get(
                    "/api/v1/analytics/dashboard",
                    headers={"Authorization": f"Bearer {token}"},
                )
            peak = resp.json()["peak_usage_hours"]
            assert len(peak) == 24  # Gate 2


# ===========================================================================
# Dashboard cost_summary field (N-41 integration)
# ===========================================================================


class TestAnalyticsDashboardCostSummary:
    def test_cost_summary_present_in_dashboard(self):
        with TestClient(app) as client:
            token = _register(client)
            with _mock_runs([]):
                resp = client.get(
                    "/api/v1/analytics/dashboard",
                    headers={"Authorization": f"Bearer {token}"},
                )
        assert resp.status_code == 200
        body = resp.json()
        assert "cost_summary" in body  # Gate 2

    def test_cost_summary_total_usd_is_float(self):
        cost_tracker_store.record(
            "exec-dash-1",
            "flow-dash-A",
            [
                {
                    "node_id": "n1",
                    "node_type": "llm",
                    "token_input": 100,
                    "token_output": 50,
                    "model": "gpt-4o",
                    "estimated_usd": 0.001250,
                    "api_calls": 0,
                }
            ],
        )
        with TestClient(app) as client:
            token = _register(client)
            with _mock_runs([]):
                resp = client.get(
                    "/api/v1/analytics/dashboard",
                    headers={"Authorization": f"Bearer {token}"},
                )
        assert resp.status_code == 200
        cost_summary = resp.json()["cost_summary"]
        assert isinstance(cost_summary["total_usd"], float)  # Gate 2
        assert cost_summary["total_usd"] >= 0.0  # Gate 2


# ===========================================================================
# GET /analytics/dashboard/export.csv
# ===========================================================================


class TestAnalyticsDashboardExportCsv:
    def test_returns_200_csv(self):
        with TestClient(app) as client:
            token = _register(client)
            with _mock_runs([]):
                resp = client.get(
                    "/api/v1/analytics/dashboard/export.csv",
                    headers={"Authorization": f"Bearer {token}"},
                )
            assert resp.status_code == 200  # Gate 2
            assert "text/csv" in resp.headers.get("content-type", "")  # Gate 2

    def test_csv_contains_header_row(self):
        with TestClient(app) as client:
            token = _register(client)
            with _mock_runs([]):
                resp = client.get(
                    "/api/v1/analytics/dashboard/export.csv",
                    headers={"Authorization": f"Bearer {token}"},
                )
            assert "flow_id" in resp.text  # Gate 2

    def test_csv_requires_auth(self):
        with TestClient(app) as client:
            _register(client)
            resp = client.get("/api/v1/analytics/dashboard/export.csv")
            assert resp.status_code in (401, 403)  # Gate 2
