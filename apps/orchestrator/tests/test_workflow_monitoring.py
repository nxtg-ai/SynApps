"""
N-35: Workflow Monitoring — Health Checks + Alerts
Tests for WorkflowHealthService, AlertRuleStore, AlertEngine, and monitoring endpoints.
"""

import time
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from apps.orchestrator.main import app
from apps.orchestrator.request_models import WorkflowHealthService
from apps.orchestrator.stores import (
    AlertEngine,
    AlertRuleStore,
    alert_rule_store,
    audit_log_store,
    sse_event_bus,
    workflow_permission_store,
)

# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_stores():
    """Reset shared in-memory stores before and after every test."""
    alert_rule_store.reset()
    audit_log_store.reset()
    workflow_permission_store.reset()
    sse_event_bus.reset()
    yield
    alert_rule_store.reset()
    audit_log_store.reset()
    workflow_permission_store.reset()
    sse_event_bus.reset()


def _register(client: TestClient, email: str | None = None) -> str:
    """Register a user and return the access token."""
    email = email or f"mon-{uuid.uuid4().hex[:8]}@test.com"
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "MonPass1!"},
    )
    return resp.json()["access_token"]


def _mock_runs(runs: list[dict]):
    """Patch WorkflowRunRepository.get_all to return *runs*."""
    return patch(
        "apps.orchestrator.main.WorkflowRunRepository.get_all",
        new_callable=AsyncMock,
        return_value=runs,
    )


def _make_run(
    flow_id: str,
    status: str = "success",
    offset_seconds: float = 0.0,
    duration_seconds: float = 1.0,
) -> dict:
    """Build a minimal workflow run dict for testing."""
    start = time.time() - offset_seconds
    return {
        "flow_id": flow_id,
        "status": status,
        "start_time": start,
        "end_time": start + duration_seconds,
    }


def _minimal_rule(**kwargs) -> dict:
    """Return a minimal valid alert rule body."""
    defaults: dict = {
        "workflow_id": "*",
        "metric": "error_rate",
        "operator": ">",
        "threshold": 0.3,
        "window_minutes": 60,
        "action_type": "log",
        "action_config": {},
    }
    defaults.update(kwargs)
    return defaults


# ===========================================================================
# TestWorkflowHealthService
# ===========================================================================


class TestWorkflowHealthService:
    @pytest.mark.asyncio
    async def test_healthy_classification(self):
        """Flows with error_rate < 0.1 are classified as healthy."""
        # 19 success + 1 error = error_rate of 1/20 = 0.05, strictly < 0.1 → healthy
        runs = [_make_run("flow-A", "success")] * 19 + [_make_run("flow-A", "error")]
        with _mock_runs(runs):
            result = await WorkflowHealthService.get_health()
        assert isinstance(result, list)  # Gate 2
        assert len(result) >= 1  # Gate 2
        flow_a = next(r for r in result if r["flow_id"] == "flow-A")
        assert flow_a["health_status"] == "healthy"  # Gate 2
        assert flow_a["error_rate"] == pytest.approx(0.05, rel=1e-3)

    @pytest.mark.asyncio
    async def test_degraded_classification(self):
        """Flows with 0.1 <= error_rate <= 0.3 are classified as degraded."""
        # 2 errors out of 10 = 20% error rate
        runs = [_make_run("flow-B", "success")] * 8 + [_make_run("flow-B", "error")] * 2
        with _mock_runs(runs):
            result = await WorkflowHealthService.get_health()
        assert len(result) >= 1  # Gate 2
        flow_b = next(r for r in result if r["flow_id"] == "flow-B")
        assert flow_b["health_status"] == "degraded"  # Gate 2

    @pytest.mark.asyncio
    async def test_critical_classification(self):
        """Flows with error_rate > 0.3 are classified as critical."""
        runs = [_make_run("flow-C", "success")] * 3 + [_make_run("flow-C", "error")] * 7
        with _mock_runs(runs):
            result = await WorkflowHealthService.get_health()
        assert len(result) >= 1  # Gate 2
        flow_c = next(r for r in result if r["flow_id"] == "flow-C")
        assert flow_c["health_status"] == "critical"  # Gate 2
        assert flow_c["error_rate"] == pytest.approx(0.7, rel=1e-3)

    @pytest.mark.asyncio
    async def test_empty_state_returns_empty_list(self):
        """When there are no runs, get_health returns an empty list."""
        with _mock_runs([]):
            result = await WorkflowHealthService.get_health()
        assert isinstance(result, list)  # Gate 2
        assert result == []

    @pytest.mark.asyncio
    async def test_window_filtering_excludes_old_runs(self):
        """Runs older than window_hours should not appear in results."""
        now = time.time()
        old_run = {
            "flow_id": "flow-old",
            "status": "error",
            "start_time": now - 25 * 3600,  # 25 hours ago — outside 24h window
            "end_time": now - 25 * 3600 + 1,
        }
        recent_run = {
            "flow_id": "flow-new",
            "status": "success",
            "start_time": now - 1800,  # 30 minutes ago — inside 24h window
            "end_time": now - 1799,
        }
        with _mock_runs([old_run, recent_run]):
            result = await WorkflowHealthService.get_health(window_hours=24)
        assert isinstance(result, list)  # Gate 2
        flow_ids = {r["flow_id"] for r in result}
        assert "flow-old" not in flow_ids  # Gate 2 — excluded by window
        assert "flow-new" in flow_ids  # Gate 2 — included in window

    @pytest.mark.asyncio
    async def test_p95_duration_computed(self):
        """p95_duration_seconds should be populated for flows with completed runs."""
        # 20 runs with deterministic durations
        runs = []
        now = time.time()
        for i in range(1, 21):
            runs.append(
                {
                    "flow_id": "flow-dur",
                    "status": "success",
                    "start_time": now - i,
                    "end_time": now - i + i,  # duration == i seconds
                }
            )
        with _mock_runs(runs):
            result = await WorkflowHealthService.get_health()
        assert len(result) >= 1  # Gate 2
        flow_dur = next(r for r in result if r["flow_id"] == "flow-dur")
        assert flow_dur["p95_duration_seconds"] is not None  # Gate 2
        # p95 of 1..20 sorted = index ceil(0.95*20)-1 = index 18 = value 19
        assert flow_dur["p95_duration_seconds"] == pytest.approx(19.0, rel=1e-3)


# ===========================================================================
# TestAlertRuleStore
# ===========================================================================


class TestAlertRuleStore:
    def test_create_returns_rule_with_id(self):
        """Creating a rule assigns a uuid id and returns the stored dict."""
        store = AlertRuleStore()
        rule = store.create(_minimal_rule())
        assert "id" in rule  # Gate 2
        assert len(rule["id"]) == 36  # uuid4 format
        assert rule["metric"] == "error_rate"  # Gate 2
        assert rule["enabled"] is True  # Gate 2

    def test_list_all_returns_created_rules(self):
        """list_all returns every created rule."""
        store = AlertRuleStore()
        store.create(_minimal_rule(metric="error_rate"))
        store.create(_minimal_rule(metric="run_count"))
        rules = store.list_all()
        assert isinstance(rules, list)  # Gate 2
        assert len(rules) >= 2  # Gate 2 — both rules present
        metrics = {r["metric"] for r in rules}
        assert "error_rate" in metrics  # Gate 2
        assert "run_count" in metrics  # Gate 2

    def test_update_modifies_threshold(self):
        """update() changes the threshold of an existing rule."""
        store = AlertRuleStore()
        rule = store.create(_minimal_rule(threshold=0.3))
        updated = store.update(rule["id"], {"threshold": 0.5})
        assert updated is not None  # Gate 2
        assert updated["threshold"] == pytest.approx(0.5)  # Gate 2
        # Verify the store reflects the update
        fetched = store.get(rule["id"])
        assert fetched is not None  # Gate 2
        assert fetched["threshold"] == pytest.approx(0.5)  # Gate 2

    def test_delete_removes_rule(self):
        """delete() removes the rule and returns True; subsequent get returns None."""
        store = AlertRuleStore()
        rule = store.create(_minimal_rule())
        result = store.delete(rule["id"])
        assert result is True  # Gate 2
        assert store.get(rule["id"]) is None  # Gate 2

    def test_delete_nonexistent_returns_false(self):
        """delete() returns False for unknown rule ids."""
        store = AlertRuleStore()
        result = store.delete("nonexistent-id")
        assert result is False  # Gate 2

    def test_update_nonexistent_returns_none(self):
        """update() returns None when the rule does not exist."""
        store = AlertRuleStore()
        result = store.update("no-such-id", {"threshold": 0.9})
        assert result is None  # Gate 2


# ===========================================================================
# TestAlertEngine
# ===========================================================================


class TestAlertEngine:
    def test_evaluate_matching_rule_fires_log_action(self):
        """A triggered log rule calls logger.warning with the flow id."""
        store = AlertRuleStore()
        store.create(
            _minimal_rule(
                workflow_id="flow-X",
                metric="error_rate",
                operator=">",
                threshold=0.2,
                action_type="log",
            )
        )
        engine = AlertEngine(store)
        health = [
            {
                "flow_id": "flow-X",
                "error_rate": 0.5,
                "avg_duration_seconds": 2.0,
                "run_count": 10,
                "health_status": "critical",
            }
        ]
        with patch("apps.orchestrator.main.logger") as mock_logger:
            engine.evaluate(health)
        # logger.warning must have been called at least once
        assert mock_logger.warning.called  # Gate 2
        # The call args should reference the triggered flow
        call_args_str = str(mock_logger.warning.call_args_list)
        assert "flow-X" in call_args_str  # Gate 2

    def test_evaluate_nonmatching_rule_does_not_trigger(self, caplog):
        """A rule whose condition is not met produces no warning log."""
        import logging

        store = AlertRuleStore()
        store.create(
            _minimal_rule(
                workflow_id="flow-Y",
                metric="error_rate",
                operator=">",
                threshold=0.9,  # Very high — not matched
                action_type="log",
            )
        )
        engine = AlertEngine(store)
        health = [
            {
                "flow_id": "flow-Y",
                "error_rate": 0.1,
                "avg_duration_seconds": 1.0,
                "run_count": 5,
                "health_status": "healthy",
            }
        ]
        with caplog.at_level(logging.WARNING):
            engine.evaluate(health)
        # No AlertEngine warning for flow-Y should appear
        matching = [
            r
            for r in caplog.records
            if "flow-Y" in r.getMessage() and "AlertEngine" in r.getMessage()
        ]
        assert len(matching) == 0  # Gate 2

    def test_evaluate_webhook_action_calls_httpx_post(self):
        """A triggered webhook rule fires httpx.post with a payload."""
        store = AlertRuleStore()
        store.create(
            _minimal_rule(
                workflow_id="*",
                metric="error_rate",
                operator=">",
                threshold=0.05,
                action_type="webhook",
                action_config={"url": "http://example.com/webhook"},
            )
        )
        engine = AlertEngine(store)
        health = [
            {
                "flow_id": "flow-W",
                "error_rate": 0.5,
                "avg_duration_seconds": 1.0,
                "run_count": 4,
                "health_status": "critical",
            }
        ]
        mock_post = MagicMock(return_value=MagicMock(status_code=200))
        with patch("apps.orchestrator.main.httpx.post", mock_post):
            engine.evaluate(health)
            # Give the daemon thread a moment to execute
            import time as _time

            deadline = _time.time() + 2.0
            while mock_post.call_count == 0 and _time.time() < deadline:
                _time.sleep(0.05)
        assert mock_post.call_count >= 1  # Gate 2 — webhook was fired

    def test_evaluate_disabled_rule_is_skipped(self, caplog):
        """Disabled rules must not trigger any action."""
        import logging

        store = AlertRuleStore()
        store.create(
            _minimal_rule(
                metric="error_rate",
                operator=">",
                threshold=0.0,
                action_type="log",
                enabled=False,
            )
        )
        engine = AlertEngine(store)
        health = [
            {
                "flow_id": "flow-Z",
                "error_rate": 0.9,
                "avg_duration_seconds": 1.0,
                "run_count": 10,
                "health_status": "critical",
            }
        ]
        with caplog.at_level(logging.WARNING):
            engine.evaluate(health)
        matching = [
            r
            for r in caplog.records
            if "flow-Z" in r.getMessage() and "AlertEngine" in r.getMessage()
        ]
        assert len(matching) == 0  # Gate 2 — disabled rule must not fire

    def test_evaluate_updates_last_triggered_at(self):
        """last_triggered_at is set when a rule fires."""
        store = AlertRuleStore()
        rule = store.create(
            _minimal_rule(
                metric="error_rate",
                operator=">",
                threshold=0.1,
                action_type="log",
            )
        )
        assert rule["last_triggered_at"] is None  # Gate 2 — not yet triggered
        engine = AlertEngine(store)
        health = [
            {
                "flow_id": "flow-T",
                "error_rate": 0.5,
                "avg_duration_seconds": 1.0,
                "run_count": 2,
                "health_status": "critical",
            }
        ]
        engine.evaluate(health)
        updated = store.get(rule["id"])
        assert updated is not None  # Gate 2
        assert updated["last_triggered_at"] is not None  # Gate 2 — timestamp set


# ===========================================================================
# TestMonitoringEndpoints
# ===========================================================================


class TestMonitoringEndpoints:
    def test_get_workflows_requires_auth(self):
        """GET /monitoring/workflows returns 401 without a token once a user exists."""
        with TestClient(app) as client:
            # Register a user first to disable the anonymous bootstrap bypass
            _register(client)
            resp = client.get("/api/v1/monitoring/workflows")
        assert resp.status_code in (401, 403)  # Gate 2
        assert "error" in resp.json()

    def test_get_workflows_returns_200_with_auth(self):
        """GET /monitoring/workflows returns 200 with a valid token."""
        with TestClient(app) as client:
            token = _register(client)
            with _mock_runs([]):
                resp = client.get(
                    "/api/v1/monitoring/workflows",
                    headers={"Authorization": f"Bearer {token}"},
                )
        assert resp.status_code == 200  # Gate 2
        body = resp.json()
        assert "workflows" in body  # Gate 2
        assert "total" in body  # Gate 2

    def test_get_workflows_filters_by_flow_id(self):
        """GET /monitoring/workflows?flow_id=X returns only that flow."""
        runs = [_make_run("flow-1")] * 2 + [_make_run("flow-2")]
        with TestClient(app) as client:
            token = _register(client)
            with _mock_runs(runs):
                resp = client.get(
                    "/api/v1/monitoring/workflows?flow_id=flow-1",
                    headers={"Authorization": f"Bearer {token}"},
                )
        assert resp.status_code == 200  # Gate 2
        body = resp.json()
        assert isinstance(body["workflows"], list)  # Gate 2
        assert len(body["workflows"]) >= 1  # Gate 2
        assert all(w["flow_id"] == "flow-1" for w in body["workflows"])  # Gate 2

    def test_get_workflow_detail_returns_single_flow(self):
        """GET /monitoring/workflows/{flow_id} returns a single workflow dict."""
        runs = [_make_run("flow-detail")]
        with TestClient(app) as client:
            token = _register(client)
            with _mock_runs(runs):
                resp = client.get(
                    "/api/v1/monitoring/workflows/flow-detail",
                    headers={"Authorization": f"Bearer {token}"},
                )
        assert resp.status_code == 200  # Gate 2
        body = resp.json()
        assert "workflow" in body  # Gate 2
        assert body["workflow"]["flow_id"] == "flow-detail"  # Gate 2

    def test_get_workflow_detail_404_for_unknown_flow(self):
        """GET /monitoring/workflows/{flow_id} returns 404 when no runs exist."""
        with TestClient(app) as client:
            token = _register(client)
            with _mock_runs([]):
                resp = client.get(
                    "/api/v1/monitoring/workflows/no-such-flow",
                    headers={"Authorization": f"Bearer {token}"},
                )
        assert resp.status_code == 404  # Gate 2
        assert "error" in resp.json()

    def test_post_alert_creates_rule(self):
        """POST /monitoring/alerts creates a rule and returns 201."""
        with TestClient(app) as client:
            token = _register(client)
            resp = client.post(
                "/api/v1/monitoring/alerts",
                json=_minimal_rule(),
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 201  # Gate 2
        body = resp.json()
        assert "rule" in body  # Gate 2
        assert "id" in body["rule"]  # Gate 2

    def test_post_alert_validates_invalid_metric(self):
        """POST /monitoring/alerts returns 422 for an invalid metric."""
        with TestClient(app) as client:
            token = _register(client)
            resp = client.post(
                "/api/v1/monitoring/alerts",
                json=_minimal_rule(metric="not_a_metric"),
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 422  # Gate 2
        assert "error" in resp.json()

    def test_get_alerts_lists_rules(self):
        """GET /monitoring/alerts returns all alert rules."""
        with TestClient(app) as client:
            token = _register(client)
            # Create two rules
            for _ in range(2):
                client.post(
                    "/api/v1/monitoring/alerts",
                    json=_minimal_rule(),
                    headers={"Authorization": f"Bearer {token}"},
                )
            resp = client.get(
                "/api/v1/monitoring/alerts",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 200  # Gate 2
        body = resp.json()
        assert isinstance(body["rules"], list)  # Gate 2
        assert len(body["rules"]) >= 2  # Gate 2

    def test_put_alert_updates_threshold(self):
        """PUT /monitoring/alerts/{id} updates the threshold."""
        with TestClient(app) as client:
            token = _register(client)
            create_resp = client.post(
                "/api/v1/monitoring/alerts",
                json=_minimal_rule(threshold=0.3),
                headers={"Authorization": f"Bearer {token}"},
            )
            rule_id = create_resp.json()["rule"]["id"]
            update_resp = client.put(
                f"/api/v1/monitoring/alerts/{rule_id}",
                json={"threshold": 0.8},
                headers={"Authorization": f"Bearer {token}"},
            )
        assert update_resp.status_code == 200  # Gate 2
        assert update_resp.json()["rule"]["threshold"] == pytest.approx(0.8)  # Gate 2

    def test_put_alert_404_for_unknown_id(self):
        """PUT /monitoring/alerts/{id} returns 404 for a missing rule."""
        with TestClient(app) as client:
            token = _register(client)
            resp = client.put(
                "/api/v1/monitoring/alerts/no-such-rule",
                json={"threshold": 0.5},
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 404  # Gate 2
        assert "error" in resp.json()

    def test_delete_alert_removes_rule(self):
        """DELETE /monitoring/alerts/{id} removes the rule (204) and GET no longer lists it."""
        with TestClient(app) as client:
            token = _register(client)
            create_resp = client.post(
                "/api/v1/monitoring/alerts",
                json=_minimal_rule(),
                headers={"Authorization": f"Bearer {token}"},
            )
            rule_id = create_resp.json()["rule"]["id"]
            del_resp = client.delete(
                f"/api/v1/monitoring/alerts/{rule_id}",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert del_resp.status_code == 204  # Gate 2
            list_resp = client.get(
                "/api/v1/monitoring/alerts",
                headers={"Authorization": f"Bearer {token}"},
            )
        ids = [r["id"] for r in list_resp.json()["rules"]]
        assert rule_id not in ids  # Gate 2 — rule has been deleted

    def test_delete_alert_404_for_unknown_id(self):
        """DELETE /monitoring/alerts/{id} returns 404 for a missing rule."""
        with TestClient(app) as client:
            token = _register(client)
            resp = client.delete(
                "/api/v1/monitoring/alerts/ghost-id",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 404  # Gate 2
        assert "error" in resp.json()

    def test_get_workflows_health_status_field_present(self):
        """Health response includes health_status field for each workflow."""
        runs = [_make_run("flow-hs")]
        with TestClient(app) as client:
            token = _register(client)
            with _mock_runs(runs):
                resp = client.get(
                    "/api/v1/monitoring/workflows",
                    headers={"Authorization": f"Bearer {token}"},
                )
        assert resp.status_code == 200  # Gate 2
        workflows = resp.json()["workflows"]
        assert len(workflows) >= 1  # Gate 2
        assert "health_status" in workflows[0]  # Gate 2
        assert workflows[0]["health_status"] in {"healthy", "degraded", "critical"}  # Gate 2
