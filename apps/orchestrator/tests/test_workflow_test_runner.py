"""
N-33b: Workflow Test Runner — CI-compatible test suite for workflows.

Tests for TestSuiteStore, _match_output, and all /flows/{flow_id}/tests/* endpoints.
"""

import time
import uuid
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from apps.orchestrator.helpers import _match_output
from apps.orchestrator.main import app
from apps.orchestrator.stores import TestSuiteStore

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _register(client: TestClient, email: str | None = None) -> str:
    """Register a user and return the access token."""
    email = email or f"trun-{uuid.uuid4().hex[:8]}@test.com"
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "TestRun1!"},
    )
    assert resp.status_code in (200, 201), resp.text
    return resp.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_flow(client: TestClient, token: str, name: str = "TR Flow") -> str:
    """Create a minimal start->end flow and return its ID."""
    uid = uuid.uuid4().hex[:8]
    flow_payload = {
        "name": name,
        "nodes": [
            {
                "id": f"start-{uid}",
                "type": "start",
                "position": {"x": 0, "y": 0},
                "data": {"label": "Start"},
            },
            {
                "id": f"end-{uid}",
                "type": "end",
                "position": {"x": 0, "y": 100},
                "data": {"label": "End"},
            },
        ],
        "edges": [
            {"id": f"e-{uid}", "source": f"start-{uid}", "target": f"end-{uid}"},
        ],
    }
    resp = client.post("/api/v1/flows", json=flow_payload, headers=_auth(token))
    assert resp.status_code == 201
    return resp.json()["id"]


# ===========================================================================
# TestSuiteStore unit tests
# ===========================================================================


class TestTestSuiteStore:
    def test_add_test_returns_correct_fields(self):
        store = TestSuiteStore()
        result = store.add_test(
            flow_id="flow-1",
            name="Check output",
            description="Verifies greeting",
            input_data={"prompt": "hi"},
            expected_output={"text": "hello"},
            match_mode="contains",
            created_by="user@test.com",
        )
        assert result["test_id"]
        assert result["flow_id"] == "flow-1"
        assert result["name"] == "Check output"
        assert result["description"] == "Verifies greeting"
        assert result["input"] == {"prompt": "hi"}
        assert result["expected_output"] == {"text": "hello"}
        assert result["match_mode"] == "contains"
        assert result["created_by"] == "user@test.com"
        assert isinstance(result["created_at"], float)

    def test_get_test_returns_none_for_unknown(self):
        store = TestSuiteStore()
        assert store.get_test("nonexistent-id") is None

    def test_list_tests_filters_by_flow_id(self):
        store = TestSuiteStore()
        store.add_test("flow-A", "Test A1", "", {}, {})
        store.add_test("flow-A", "Test A2", "", {}, {})
        store.add_test("flow-B", "Test B1", "", {}, {})

        a_tests = store.list_tests("flow-A")
        assert isinstance(a_tests, list)
        assert len(a_tests) >= 1  # Gate 2
        assert len(a_tests) == 2
        assert all(t["flow_id"] == "flow-A" for t in a_tests)

        b_tests = store.list_tests("flow-B")
        assert len(b_tests) == 1

    def test_delete_test_returns_false_for_unknown(self):
        store = TestSuiteStore()
        assert store.delete_test("no-such-id") is False

    def test_delete_test_returns_true_when_found(self):
        store = TestSuiteStore()
        t = store.add_test("flow-1", "to delete", "", {}, {})
        assert store.delete_test(t["test_id"]) is True
        assert store.get_test(t["test_id"]) is None

    def test_add_result_stores_result(self):
        store = TestSuiteStore()
        r = store.add_result({
            "test_id": "t1",
            "flow_id": "flow-1",
            "status": "pass",
            "ran_at": time.time(),
        })
        assert "result_id" in r
        results = store.list_results(flow_id="flow-1")
        assert isinstance(results, list)
        assert len(results) >= 1  # Gate 2

    def test_suite_summary_returns_correct_pass_rate(self):
        store = TestSuiteStore()
        store.add_result({"test_id": "t1", "flow_id": "f1", "status": "pass"})
        store.add_result({"test_id": "t2", "flow_id": "f1", "status": "pass"})
        store.add_result({"test_id": "t3", "flow_id": "f1", "status": "fail"})
        store.add_result({"test_id": "t4", "flow_id": "f1", "status": "error"})

        summary = store.suite_summary("f1")
        assert summary["total"] == 4
        assert summary["passed"] == 2
        assert summary["failed"] == 1
        assert summary["error"] == 1
        assert summary["pass_rate_pct"] == 50.0

    def test_reset_clears_all(self):
        store = TestSuiteStore()
        store.add_test("flow-1", "t", "", {}, {})
        store.add_result({"test_id": "t1", "flow_id": "flow-1", "status": "pass"})
        store.reset()
        assert store.list_tests("flow-1") == []
        assert store.list_results(flow_id="flow-1") == []


# ===========================================================================
# _match_output unit tests
# ===========================================================================


class TestMatchOutput:
    def test_exact_match_passes(self):
        passed, diff = _match_output({"a": 1, "b": 2}, {"a": 1, "b": 2}, "exact")
        assert passed is True
        assert diff == {}

    def test_exact_match_fails_on_difference(self):
        passed, diff = _match_output({"a": 1}, {"a": 2}, "exact")
        assert passed is False
        assert "a" in diff

    def test_contains_match_passes(self):
        passed, diff = _match_output({"a": 1, "b": 2, "c": 3}, {"a": 1}, "contains")
        assert passed is True

    def test_contains_match_fails_missing_key(self):
        passed, diff = _match_output({"a": 1}, {"b": 2}, "contains")
        assert passed is False
        assert "b" in diff

    def test_keys_present_passes(self):
        passed, diff = _match_output({"a": 99, "b": 42}, {"a": 0, "b": 0}, "keys_present")
        assert passed is True

    def test_keys_present_fails_missing(self):
        passed, diff = _match_output({"a": 1}, {"a": 0, "x": 0}, "keys_present")
        assert passed is False
        assert "x" in diff


# ===========================================================================
# Test Case endpoint integration tests
# ===========================================================================


class TestTestCaseEndpoints:
    def test_post_returns_201(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/tests",
                json={
                    "name": "Smoke test",
                    "input": {"prompt": "hi"},
                    "expected_output": {"text": "hello"},
                    "match_mode": "contains",
                },
                headers=_auth(token),
            )
            assert resp.status_code == 201
            data = resp.json()
            assert data["name"] == "Smoke test"
            assert data["test_id"]

    def test_get_list_returns_tests(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            # Add a test case
            client.post(
                f"/api/v1/flows/{flow_id}/tests",
                json={"name": "Test 1", "expected_output": {"key": "val"}},
                headers=_auth(token),
            )
            resp = client.get(f"/api/v1/flows/{flow_id}/tests", headers=_auth(token))
            assert resp.status_code == 200
            tests = resp.json()["tests"]
            assert isinstance(tests, list)
            assert len(tests) >= 1  # Gate 2

    def test_get_single_test_200(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            create_resp = client.post(
                f"/api/v1/flows/{flow_id}/tests",
                json={"name": "Single get"},
                headers=_auth(token),
            )
            test_id = create_resp.json()["test_id"]
            resp = client.get(
                f"/api/v1/flows/{flow_id}/tests/{test_id}",
                headers=_auth(token),
            )
            assert resp.status_code == 200
            assert resp.json()["name"] == "Single get"

    def test_get_single_test_404_unknown(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(
                f"/api/v1/flows/{flow_id}/tests/nonexistent-id",
                headers=_auth(token),
            )
            assert resp.status_code == 404
            assert "error" in resp.json()

    def test_delete_returns_204(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            create_resp = client.post(
                f"/api/v1/flows/{flow_id}/tests",
                json={"name": "To delete"},
                headers=_auth(token),
            )
            test_id = create_resp.json()["test_id"]
            resp = client.delete(
                f"/api/v1/flows/{flow_id}/tests/{test_id}",
                headers=_auth(token),
            )
            assert resp.status_code == 204

    def test_delete_unknown_returns_404(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.delete(
                f"/api/v1/flows/{flow_id}/tests/nonexistent",
                headers=_auth(token),
            )
            assert resp.status_code == 404
            assert "error" in resp.json()

    def test_endpoints_require_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            # No auth header
            r1 = client.post(
                f"/api/v1/flows/{flow_id}/tests",
                json={"name": "no auth"},
            )
            assert r1.status_code in (401, 403)
            assert "error" in r1.json()
            r2 = client.get(f"/api/v1/flows/{flow_id}/tests")
            assert r2.status_code in (401, 403)
            assert "error" in r2.json()

    def test_post_validates_name_required(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/tests",
                json={"name": "", "expected_output": {}},
                headers=_auth(token),
            )
            assert resp.status_code == 422
            assert "error" in resp.json()


# ===========================================================================
# Run Test Suite integration tests
# ===========================================================================


def _mock_execute_flow(run_id: str = "mock-run-1", output: dict | None = None):
    """Return a context manager that patches Orchestrator.execute_flow
    to complete immediately with the given output."""
    actual_output = output if output is not None else {}

    async def _execute(flow, input_data):
        return run_id

    run_data = {
        "run_id": run_id,
        "status": "success",
        "results": {
            "node-1": {"output": actual_output},
        },
    }

    return (
        patch("apps.orchestrator.main.Orchestrator.execute_flow", new=_execute),
        patch(
            "apps.orchestrator.main.WorkflowRunRepository.get_by_run_id",
            new_callable=AsyncMock,
            return_value=run_data,
        ),
    )


class TestRunTestSuite:
    def test_run_returns_results_list(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            # Add a test case with empty expected (always passes with contains)
            client.post(
                f"/api/v1/flows/{flow_id}/tests",
                json={"name": "t1", "expected_output": {}, "match_mode": "contains"},
                headers=_auth(token),
            )
            p1, p2 = _mock_execute_flow(output={})
            with p1, p2:
                resp = client.post(
                    f"/api/v1/flows/{flow_id}/tests/run",
                    json={},
                    headers=_auth(token),
                )
            assert resp.status_code == 200
            data = resp.json()
            assert isinstance(data["results"], list)
            assert len(data["results"]) >= 1  # Gate 2

    def test_pass_rate_100_when_all_pass(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            client.post(
                f"/api/v1/flows/{flow_id}/tests",
                json={"name": "t1", "expected_output": {"key": "val"}, "match_mode": "contains"},
                headers=_auth(token),
            )
            p1, p2 = _mock_execute_flow(output={"key": "val", "extra": 1})
            with p1, p2:
                resp = client.post(
                    f"/api/v1/flows/{flow_id}/tests/run",
                    json={},
                    headers=_auth(token),
                )
            data = resp.json()
            assert data["summary"]["pass_rate_pct"] == 100.0

    def test_exit_code_0_when_all_pass(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            client.post(
                f"/api/v1/flows/{flow_id}/tests",
                json={"name": "t1", "expected_output": {}, "match_mode": "contains"},
                headers=_auth(token),
            )
            p1, p2 = _mock_execute_flow(output={"anything": True})
            with p1, p2:
                resp = client.post(
                    f"/api/v1/flows/{flow_id}/tests/run",
                    json={},
                    headers=_auth(token),
                )
            assert resp.json()["exit_code"] == 0

    def test_exit_code_1_when_fail(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            client.post(
                f"/api/v1/flows/{flow_id}/tests",
                json={
                    "name": "t1",
                    "expected_output": {"answer": 42},
                    "match_mode": "exact",
                },
                headers=_auth(token),
            )
            p1, p2 = _mock_execute_flow(output={"answer": 99})
            with p1, p2:
                resp = client.post(
                    f"/api/v1/flows/{flow_id}/tests/run",
                    json={},
                    headers=_auth(token),
                )
            assert resp.json()["exit_code"] == 1

    def test_keys_present_passes_when_keys_exist(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            client.post(
                f"/api/v1/flows/{flow_id}/tests",
                json={
                    "name": "keys test",
                    "expected_output": {"a": 0, "b": 0},
                    "match_mode": "keys_present",
                },
                headers=_auth(token),
            )
            p1, p2 = _mock_execute_flow(output={"a": 999, "b": "hello", "c": True})
            with p1, p2:
                resp = client.post(
                    f"/api/v1/flows/{flow_id}/tests/run",
                    json={},
                    headers=_auth(token),
                )
            results = resp.json()["results"]
            assert len(results) >= 1  # Gate 2
            assert results[0]["status"] == "pass"

    def test_exact_fails_when_values_differ(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            client.post(
                f"/api/v1/flows/{flow_id}/tests",
                json={
                    "name": "exact mismatch",
                    "expected_output": {"x": 1},
                    "match_mode": "exact",
                },
                headers=_auth(token),
            )
            p1, p2 = _mock_execute_flow(output={"x": 2})
            with p1, p2:
                resp = client.post(
                    f"/api/v1/flows/{flow_id}/tests/run",
                    json={},
                    headers=_auth(token),
                )
            results = resp.json()["results"]
            assert results[0]["status"] == "fail"
            assert "x" in results[0]["diff"]

    def test_results_in_get_results(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            client.post(
                f"/api/v1/flows/{flow_id}/tests",
                json={"name": "stored", "expected_output": {}, "match_mode": "contains"},
                headers=_auth(token),
            )
            p1, p2 = _mock_execute_flow(output={})
            with p1, p2:
                client.post(
                    f"/api/v1/flows/{flow_id}/tests/run",
                    json={},
                    headers=_auth(token),
                )
            resp = client.get(
                f"/api/v1/flows/{flow_id}/tests/results",
                headers=_auth(token),
            )
            assert resp.status_code == 200
            results = resp.json()["results"]
            assert isinstance(results, list)
            assert len(results) >= 1  # Gate 2


# ===========================================================================
# CI Compatibility tests
# ===========================================================================


class TestCICompatibility:
    def test_empty_suite_exit_code_0(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            p1, p2 = _mock_execute_flow()
            with p1, p2:
                resp = client.post(
                    f"/api/v1/flows/{flow_id}/tests/run",
                    json={},
                    headers=_auth(token),
                )
            assert resp.json()["exit_code"] == 0
            assert resp.json()["results"] == []

    def test_run_with_test_ids_runs_only_specified(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            r1 = client.post(
                f"/api/v1/flows/{flow_id}/tests",
                json={"name": "t1", "expected_output": {}},
                headers=_auth(token),
            ).json()
            client.post(
                f"/api/v1/flows/{flow_id}/tests",
                json={"name": "t2", "expected_output": {}},
                headers=_auth(token),
            )
            p1, p2 = _mock_execute_flow(output={})
            with p1, p2:
                resp = client.post(
                    f"/api/v1/flows/{flow_id}/tests/run",
                    json={"test_ids": [r1["test_id"]]},
                    headers=_auth(token),
                )
            results = resp.json()["results"]
            assert len(results) == 1
            assert results[0]["test_id"] == r1["test_id"]

    def test_summary_reflects_cumulative_results(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            # Two test cases: one will pass, one will fail
            client.post(
                f"/api/v1/flows/{flow_id}/tests",
                json={"name": "pass", "expected_output": {}, "match_mode": "contains"},
                headers=_auth(token),
            )
            client.post(
                f"/api/v1/flows/{flow_id}/tests",
                json={
                    "name": "fail",
                    "expected_output": {"must": "exist"},
                    "match_mode": "exact",
                },
                headers=_auth(token),
            )
            p1, p2 = _mock_execute_flow(output={"other": "data"})
            with p1, p2:
                resp = client.post(
                    f"/api/v1/flows/{flow_id}/tests/run",
                    json={},
                    headers=_auth(token),
                )
            summary = resp.json()["summary"]
            assert summary["total"] == 2
            assert summary["passed"] >= 1  # Gate 2
            assert summary["failed"] >= 1

            # Summary endpoint should reflect the same
            sum_resp = client.get(
                f"/api/v1/flows/{flow_id}/tests/summary",
                headers=_auth(token),
            )
            assert sum_resp.status_code == 200
            assert sum_resp.json()["total"] == 2
