"""
N-34: Workflow Testing Framework — Automated Validation
Tests for WorkflowAssertionEngine, WorkflowTestStore, and testing endpoints.
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from apps.orchestrator.main import (
    WorkflowAssertionEngine,
    WorkflowTestStore,
    app,
    audit_log_store,
    workflow_permission_store,
    workflow_test_store,
)


@pytest.fixture(autouse=True)
def _clean():
    audit_log_store.reset()
    workflow_permission_store.reset()
    workflow_test_store.reset()
    yield
    audit_log_store.reset()
    workflow_permission_store.reset()
    workflow_test_store.reset()


def _register(client: TestClient, email: str | None = None) -> tuple[str, str]:
    email = email or f"test-{uuid.uuid4().hex[:8]}@test.com"
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "TestPass1!"},
    )
    return resp.json()["access_token"], email


def _create_simple_flow(client: TestClient, token: str) -> str:
    flow = {
        "name": f"Test Flow {uuid.uuid4().hex[:6]}",
        "nodes": [
            {
                "id": "start",
                "type": "start",
                "position": {"x": 0, "y": 0},
                "data": {"label": "Start"},
            },
            {"id": "end", "type": "end", "position": {"x": 0, "y": 100}, "data": {"label": "End"}},
        ],
        "edges": [{"id": "s-e", "source": "start", "target": "end"}],
    }
    resp = client.post("/api/v1/flows", json=flow, headers={"Authorization": f"Bearer {token}"})
    return resp.json()["id"]


# ===========================================================================
# WorkflowAssertionEngine unit tests
# ===========================================================================


class TestAssertionParser:
    def _run(self, status="success", results=None):
        return {"status": status, "results": results or {}}

    def test_equality_string(self):
        run = self._run(status="success")
        r = WorkflowAssertionEngine.evaluate("status == success", run)
        assert r["passed"] is True  # Gate 2

    def test_equality_fails(self):
        run = self._run(status="error")
        r = WorkflowAssertionEngine.evaluate("status == success", run)
        assert r["passed"] is False  # Gate 2

    def test_not_equal(self):
        run = self._run(status="success")
        r = WorkflowAssertionEngine.evaluate("status != error", run)
        assert r["passed"] is True  # Gate 2

    def test_greater_than_numeric(self):
        run = self._run(results={"n1": {"output": {"count": 10}, "status": "success"}})
        r = WorkflowAssertionEngine.evaluate("output.count > 5", run)
        assert r["passed"] is True  # Gate 2

    def test_greater_than_fails(self):
        run = self._run(results={"n1": {"output": {"count": 3}, "status": "success"}})
        r = WorkflowAssertionEngine.evaluate("output.count > 5", run)
        assert r["passed"] is False  # Gate 2

    def test_gte(self):
        run = self._run(results={"n1": {"output": {"score": 0.8}, "status": "success"}})
        r = WorkflowAssertionEngine.evaluate("output.score >= 0.8", run)
        assert r["passed"] is True  # Gate 2

    def test_lte(self):
        run = self._run(results={"n1": {"output": {"score": 0.5}, "status": "success"}})
        r = WorkflowAssertionEngine.evaluate("output.score <= 0.8", run)
        assert r["passed"] is True  # Gate 2

    def test_output_field_equality(self):
        run = self._run(results={"n1": {"output": {"text": "hello"}, "status": "success"}})
        r = WorkflowAssertionEngine.evaluate("output.text == hello", run)
        assert r["passed"] is True  # Gate 2

    def test_results_node_path(self):
        run = self._run(results={"node1": {"output": {"val": 42}, "status": "success"}})
        r = WorkflowAssertionEngine.evaluate("results.node1.output.val == 42", run)
        assert r["passed"] is True  # Gate 2

    def test_results_node_status(self):
        run = self._run(results={"node1": {"output": {}, "status": "success"}})
        r = WorkflowAssertionEngine.evaluate("results.node1.status == success", run)
        assert r["passed"] is True  # Gate 2

    def test_type_check_list(self):
        run = self._run(results={"n1": {"output": {"items": [1, 2, 3]}, "status": "success"}})
        r = WorkflowAssertionEngine.evaluate("type(output.items) == list", run)
        assert r["passed"] is True  # Gate 2

    def test_type_check_string(self):
        run = self._run(results={"n1": {"output": {"text": "hello"}, "status": "success"}})
        r = WorkflowAssertionEngine.evaluate("type(output.text) == string", run)
        assert r["passed"] is True  # Gate 2

    def test_type_check_number(self):
        run = self._run(results={"n1": {"output": {"n": 42}, "status": "success"}})
        r = WorkflowAssertionEngine.evaluate("type(output.n) == number", run)
        assert r["passed"] is True  # Gate 2

    def test_unknown_path_returns_error(self):
        run = self._run()
        r = WorkflowAssertionEngine.evaluate("output.nonexistent == x", run)
        assert r["error"] is not None  # Gate 2
        assert r["passed"] is False  # Gate 2

    def test_assertion_returns_actual_value(self):
        run = self._run(status="success")
        r = WorkflowAssertionEngine.evaluate("status == success", run)
        assert r["actual"] == "success"  # Gate 2

    def test_quoted_string_value_stripped(self):
        run = self._run(results={"n1": {"output": {"text": "hello"}, "status": "success"}})
        r = WorkflowAssertionEngine.evaluate('output.text == "hello"', run)
        assert r["passed"] is True  # Gate 2


class TestWorkflowTestStore:
    def test_record_and_get_history(self):
        store = WorkflowTestStore()
        store.record_result("flow-1", {"id": "r1", "passed": True})
        history = store.get_history("flow-1")
        assert len(history) >= 1  # Gate 2
        assert history[0]["passed"] is True  # Gate 2

    def test_history_most_recent_first(self):
        store = WorkflowTestStore()
        store.record_result("flow-1", {"id": "r1", "passed": True, "ts": 1})
        store.record_result("flow-1", {"id": "r2", "passed": False, "ts": 2})
        history = store.get_history("flow-1")
        assert history[0]["id"] == "r2"  # Gate 2 — most recent first

    def test_save_and_list_suites(self):
        store = WorkflowTestStore()
        store.save_suite("flow-1", {"name": "Suite A", "assertions": ["status == success"]})
        suites = store.list_suites("flow-1")
        assert len(suites) >= 1  # Gate 2

    def test_reset_clears_all(self):
        store = WorkflowTestStore()
        store.record_result("flow-1", {"id": "r1"})
        store.reset()
        assert store.get_history("flow-1") == []  # Gate 2


# ===========================================================================
# POST /workflows/{id}/test endpoint
# ===========================================================================


class TestRunWorkflowTest:
    def test_returns_200(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            flow_id = _create_simple_flow(client, token)
            resp = client.post(
                f"/api/v1/workflows/{flow_id}/test",
                json={"assertions": ["status == success"], "input": {}},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 200  # Gate 2

    def test_returns_assertion_results(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            flow_id = _create_simple_flow(client, token)
            resp = client.post(
                f"/api/v1/workflows/{flow_id}/test",
                json={"assertions": ["status == success"], "input": {}},
                headers={"Authorization": f"Bearer {token}"},
            )
            body = resp.json()
            assert "assertion_results" in body  # Gate 2
            assert len(body["assertion_results"]) >= 1  # Gate 2

    def test_passed_field_is_bool(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            flow_id = _create_simple_flow(client, token)
            resp = client.post(
                f"/api/v1/workflows/{flow_id}/test",
                json={"assertions": ["status == success"], "input": {}},
                headers={"Authorization": f"Bearer {token}"},
            )
            body = resp.json()
            assert isinstance(body["passed"], bool)  # Gate 2

    def test_pass_count_and_fail_count_present(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            flow_id = _create_simple_flow(client, token)
            resp = client.post(
                f"/api/v1/workflows/{flow_id}/test",
                json={"assertions": ["status == success", "status != error"], "input": {}},
                headers={"Authorization": f"Bearer {token}"},
            )
            body = resp.json()
            assert "pass_count" in body  # Gate 2
            assert "fail_count" in body  # Gate 2
            assert body["pass_count"] + body["fail_count"] == 2  # Gate 2

    def test_save_result_true_stores_in_history(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            flow_id = _create_simple_flow(client, token)
            client.post(
                f"/api/v1/workflows/{flow_id}/test",
                json={"assertions": ["status == success"], "save_result": True, "input": {}},
                headers={"Authorization": f"Bearer {token}"},
            )
            history = workflow_test_store.get_history(flow_id)
            assert len(history) >= 1  # Gate 2

    def test_save_result_false_does_not_store(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            flow_id = _create_simple_flow(client, token)
            client.post(
                f"/api/v1/workflows/{flow_id}/test",
                json={"assertions": ["status == success"], "save_result": False, "input": {}},
                headers={"Authorization": f"Bearer {token}"},
            )
            history = workflow_test_store.get_history(flow_id)
            assert len(history) == 0  # Gate 2 — save_result=False means no storage

    def test_nonexistent_flow_returns_404(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            resp = client.post(
                "/api/v1/workflows/nonexistent-flow/test",
                json={"assertions": ["status == success"], "input": {}},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 404  # Gate 2

    def test_requires_auth(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            flow_id = _create_simple_flow(client, token)
            resp = client.post(
                f"/api/v1/workflows/{flow_id}/test",
                json={"assertions": ["status == success"], "input": {}},
            )
            assert resp.status_code in (401, 403)  # Gate 2


# ===========================================================================
# GET /workflows/{id}/test-history
# ===========================================================================


class TestGetWorkflowTestHistory:
    def test_returns_200(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            flow_id = _create_simple_flow(client, token)
            resp = client.get(
                f"/api/v1/workflows/{flow_id}/test-history",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 200  # Gate 2

    def test_returns_history_list(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            flow_id = _create_simple_flow(client, token)
            resp = client.get(
                f"/api/v1/workflows/{flow_id}/test-history",
                headers={"Authorization": f"Bearer {token}"},
            )
            body = resp.json()
            assert "history" in body  # Gate 2
            assert isinstance(body["history"], list)  # Gate 2

    def test_history_grows_after_test_run(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            flow_id = _create_simple_flow(client, token)
            # Run a test
            client.post(
                f"/api/v1/workflows/{flow_id}/test",
                json={"assertions": ["status == success"], "input": {}},
                headers={"Authorization": f"Bearer {token}"},
            )
            resp = client.get(
                f"/api/v1/workflows/{flow_id}/test-history",
                headers={"Authorization": f"Bearer {token}"},
            )
            body = resp.json()
            assert body["total"] >= 1  # Gate 2

    def test_nonexistent_flow_returns_404(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            resp = client.get(
                "/api/v1/workflows/no-such-flow/test-history",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 404  # Gate 2


# ===========================================================================
# POST /workflows/{id}/test-suites + GET
# ===========================================================================


class TestTestSuites:
    def test_save_suite_returns_201_or_200(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            flow_id = _create_simple_flow(client, token)
            resp = client.post(
                f"/api/v1/workflows/{flow_id}/test-suites",
                json={"name": "Smoke Test", "assertions": ["status == success"]},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code in (200, 201)  # Gate 2

    def test_save_suite_stores_name(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            flow_id = _create_simple_flow(client, token)
            client.post(
                f"/api/v1/workflows/{flow_id}/test-suites",
                json={"name": "Smoke Test", "assertions": ["status == success"]},
                headers={"Authorization": f"Bearer {token}"},
            )
            resp = client.get(
                f"/api/v1/workflows/{flow_id}/test-suites",
                headers={"Authorization": f"Bearer {token}"},
            )
            body = resp.json()
            assert body["total"] >= 1  # Gate 2
            assert any(s["name"] == "Smoke Test" for s in body["suites"])  # Gate 2

    def test_list_suites_empty_for_new_flow(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            flow_id = _create_simple_flow(client, token)
            resp = client.get(
                f"/api/v1/workflows/{flow_id}/test-suites",
                headers={"Authorization": f"Bearer {token}"},
            )
            body = resp.json()
            assert body["total"] == 0  # Gate 2 — empty state
            assert body["suites"] == []  # Gate 2
