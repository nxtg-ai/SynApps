"""Tests for N-43 Workflow Diff + N-44 Node Performance Profiler.

Covers:
- _diff_workflows: structural diffing of workflow snapshots
- WorkflowVersionStore: save, list, get, reset
- WorkflowProfilerService: profile_workflow, profile_execution
- Endpoints: POST /diff, POST /versions, GET /version-history,
             GET /versions/{id}, GET /profile, GET /executions/{id}/profile
"""

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from fastapi.testclient import TestClient

from apps.orchestrator.helpers import _diff_workflows
from apps.orchestrator.main import app
from apps.orchestrator.request_models import WorkflowProfilerService
from apps.orchestrator.stores import (
    WorkflowVersionStore,
    execution_log_store,
    workflow_version_store,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _register(client: TestClient, email: str | None = None) -> str:
    """Register a user and return the access_token."""
    email = email or f"profiler-{uuid.uuid4().hex[:8]}@test.com"
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Profiler1!"},
    )
    assert resp.status_code in (200, 201), resp.text
    return resp.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# TestDiffEngine — 8 tests
# ---------------------------------------------------------------------------


class TestDiffEngine:
    def test_identical_workflows_is_identical_true(self):
        wf = {
            "nodes": [{"id": "n1", "type": "llm", "data": {}}],
            "edges": [{"id": "e1", "source": "n1", "target": "n2"}],
        }
        result = _diff_workflows(wf, wf)
        assert result["summary"]["is_identical"] is True

    def test_empty_workflows_are_identical(self):
        result = _diff_workflows({}, {})
        assert result["summary"]["is_identical"] is True
        assert result["added_nodes"] == []
        assert result["removed_nodes"] == []

    def test_added_node_detected(self):
        v1 = {"nodes": [{"id": "n1", "type": "llm"}], "edges": []}
        v2 = {"nodes": [{"id": "n1", "type": "llm"}, {"id": "n2", "type": "http"}], "edges": []}
        result = _diff_workflows(v1, v2)
        assert len(result["added_nodes"]) == 1
        assert result["added_nodes"][0]["id"] == "n2"
        assert result["summary"]["nodes_added"] == 1
        assert result["summary"]["is_identical"] is False

    def test_removed_node_detected(self):
        v1 = {"nodes": [{"id": "n1", "type": "llm"}, {"id": "n2", "type": "http"}], "edges": []}
        v2 = {"nodes": [{"id": "n1", "type": "llm"}], "edges": []}
        result = _diff_workflows(v1, v2)
        assert len(result["removed_nodes"]) == 1
        assert result["removed_nodes"][0]["id"] == "n2"
        assert result["summary"]["nodes_removed"] == 1

    def test_modified_node_detected(self):
        v1 = {"nodes": [{"id": "n1", "type": "llm", "data": {"prompt": "hello"}}], "edges": []}
        v2 = {"nodes": [{"id": "n1", "type": "llm", "data": {"prompt": "world"}}], "edges": []}
        result = _diff_workflows(v1, v2)
        assert len(result["modified_nodes"]) == 1
        assert result["modified_nodes"][0]["id"] == "n1"
        assert result["summary"]["nodes_modified"] == 1

    def test_added_edge_detected(self):
        v1 = {"nodes": [], "edges": []}
        v2 = {"nodes": [], "edges": [{"source": "n1", "target": "n2", "id": "e1"}]}
        result = _diff_workflows(v1, v2)
        assert len(result["added_edges"]) == 1
        assert result["summary"]["edges_added"] == 1

    def test_removed_edge_detected(self):
        v1 = {"nodes": [], "edges": [{"source": "n1", "target": "n2", "id": "e1"}]}
        v2 = {"nodes": [], "edges": []}
        result = _diff_workflows(v1, v2)
        assert len(result["removed_edges"]) == 1
        assert result["summary"]["edges_removed"] == 1

    def test_summary_counts_accurate(self):
        v1 = {
            "nodes": [
                {"id": "n1", "type": "llm"},
                {"id": "n2", "type": "http"},
            ],
            "edges": [{"source": "n1", "target": "n2"}],
        }
        v2 = {
            "nodes": [
                {"id": "n1", "type": "code"},  # modified
                {"id": "n3", "type": "transform"},  # added
            ],
            "edges": [
                {"source": "n1", "target": "n3"}
            ],  # edge target changed -> old removed, new added
        }
        result = _diff_workflows(v1, v2)
        s = result["summary"]
        assert s["nodes_modified"] == 1  # n1 changed
        assert s["nodes_removed"] == 1  # n2 gone
        assert s["nodes_added"] == 1  # n3 added
        assert s["is_identical"] is False


# ---------------------------------------------------------------------------
# TestVersionStore — 6 tests
# ---------------------------------------------------------------------------


class TestVersionStore:
    def setup_method(self):
        workflow_version_store.reset()

    def teardown_method(self):
        workflow_version_store.reset()

    def test_save_version_returns_version_id(self):
        store = WorkflowVersionStore()
        rec = store.save_version("flow-1", {"nodes": [], "edges": []})
        assert "version_id" in rec
        assert rec["version_id"]  # non-empty string

    def test_list_versions_omits_snapshot(self):
        store = WorkflowVersionStore()
        store.save_version("flow-1", {"nodes": [{"id": "n1"}], "edges": []}, label="v1")
        versions = store.list_versions("flow-1")
        assert isinstance(versions, list)
        assert len(versions) >= 1  # Gate 2
        assert "snapshot" not in versions[0]
        assert "node_count" in versions[0]

    def test_get_version_returns_snapshot(self):
        store = WorkflowVersionStore()
        snapshot = {"nodes": [{"id": "n1"}], "edges": []}
        rec = store.save_version("flow-1", snapshot, label="initial")
        vid = rec["version_id"]
        full = store.get_version("flow-1", vid)
        assert full is not None
        assert "snapshot" in full
        assert full["snapshot"] == snapshot

    def test_get_version_unknown_returns_none(self):
        store = WorkflowVersionStore()
        result = store.get_version("flow-1", "nonexistent-id")
        assert result is None

    def test_reset_clears_all_versions(self):
        store = WorkflowVersionStore()
        store.save_version("flow-1", {"nodes": [], "edges": []})
        store.reset()
        assert store.list_versions("flow-1") == []

    def test_multiple_versions_same_flow(self):
        store = WorkflowVersionStore()
        store.save_version("flow-1", {"nodes": [], "edges": []}, label="v1")
        store.save_version("flow-1", {"nodes": [{"id": "n1"}], "edges": []}, label="v2")
        versions = store.list_versions("flow-1")
        assert isinstance(versions, list)
        assert len(versions) == 2  # Gate 2
        labels = [v["label"] for v in versions]
        assert "v1" in labels
        assert "v2" in labels


# ---------------------------------------------------------------------------
# TestWorkflowProfilerService — 6 tests
# ---------------------------------------------------------------------------


class TestWorkflowProfilerService:
    def setup_method(self):
        execution_log_store.reset()

    def teardown_method(self):
        execution_log_store.reset()

    def test_empty_store_returns_no_nodes(self):
        svc = WorkflowProfilerService()
        result = svc.profile_workflow("flow-1")
        assert result["nodes"] == []
        assert result["total_node_types_profiled"] == 0

    def test_with_duration_ms_computes_avg(self):
        run_id = str(uuid.uuid4())
        execution_log_store.append(
            run_id,
            {"event": "node_success", "node_id": "n1", "duration_ms": 100.0},
        )
        execution_log_store.append(
            run_id,
            {"event": "node_success", "node_id": "n1", "duration_ms": 200.0},
        )
        svc = WorkflowProfilerService()
        result = svc.profile_workflow("flow-1")
        assert isinstance(result["nodes"], list)
        assert len(result["nodes"]) >= 1  # Gate 2
        node = next(n for n in result["nodes"] if n["node_id"] == "n1")
        assert node["avg_ms"] == 150.0
        assert node["run_count"] == 2

    def test_p95_computed_correctly(self):
        run_id = str(uuid.uuid4())
        # 20 entries: 10, 20, ..., 200 ms
        for i in range(1, 21):
            execution_log_store.append(
                run_id,
                {"event": "node_success", "node_id": "n_perf", "duration_ms": float(i * 10)},
            )
        svc = WorkflowProfilerService()
        result = svc.profile_workflow("flow-1")
        node = next(n for n in result["nodes"] if n["node_id"] == "n_perf")
        # p95 of 20 values [10,20,...,200]: index = min(int(0.95*20),19) = min(19,19) = 19 => 200
        assert node["p95_ms"] == 200.0
        assert node["min_ms"] == 10.0
        assert node["max_ms"] == 200.0

    def test_bottleneck_identified_correctly(self):
        eid = str(uuid.uuid4())
        execution_log_store.append(
            eid, {"event": "node_success", "node_id": "fast_node", "duration_ms": 50.0}
        )
        execution_log_store.append(
            eid, {"event": "node_success", "node_id": "slow_node", "duration_ms": 500.0}
        )
        svc = WorkflowProfilerService()
        result = svc.profile_execution(eid)
        assert result is not None
        assert result["bottleneck_node_id"] == "slow_node"
        bottleneck_nodes = [n for n in result["nodes"] if n["is_bottleneck"]]
        assert len(bottleneck_nodes) == 1
        assert bottleneck_nodes[0]["node_id"] == "slow_node"

    def test_profile_execution_unknown_returns_none(self):
        svc = WorkflowProfilerService()
        result = svc.profile_execution("nonexistent-execution-id")
        assert result is None

    def test_profile_workflow_returns_all_nodes_seen(self):
        run_id = str(uuid.uuid4())
        for node_id in ["alpha", "beta", "gamma"]:
            execution_log_store.append(
                run_id,
                {"event": "node_success", "node_id": node_id, "duration_ms": 10.0},
            )
        svc = WorkflowProfilerService()
        result = svc.profile_workflow("flow-x")
        node_ids = {n["node_id"] for n in result["nodes"]}
        assert "alpha" in node_ids
        assert "beta" in node_ids
        assert "gamma" in node_ids
        assert result["total_node_types_profiled"] == 3


# ---------------------------------------------------------------------------
# TestDiffEndpoints — 6 tests (auth x2 + 4 functional)
# ---------------------------------------------------------------------------


class TestDiffEndpoints:
    def setup_method(self):
        workflow_version_store.reset()

    def teardown_method(self):
        workflow_version_store.reset()

    def test_diff_requires_auth(self):
        with TestClient(app) as client:
            _register(client)  # ensure non-trivial DB state (disables anonymous bootstrap)
            resp = client.post(
                "/api/v1/workflows/flow-1/diff",
                json={"v1": {}, "v2": {}},
            )
            assert resp.status_code in (401, 403)
            assert "error" in resp.json()

    def test_versions_post_requires_auth(self):
        with TestClient(app) as client:
            _register(client)  # ensure non-trivial DB state (disables anonymous bootstrap)
            resp = client.post(
                "/api/v1/workflows/flow-1/versions",
                json={"snapshot": {}, "label": "v1"},
            )
            assert resp.status_code in (401, 403)
            assert "error" in resp.json()

    def test_diff_identical_workflows_is_identical(self):
        with TestClient(app) as client:
            token = _register(client)
            wf = {"nodes": [{"id": "n1", "type": "llm"}], "edges": []}
            resp = client.post(
                "/api/v1/workflows/flow-1/diff",
                json={"v1": wf, "v2": wf},
                headers=_auth(token),
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["summary"]["is_identical"] is True

    def test_diff_detects_added_node(self):
        with TestClient(app) as client:
            token = _register(client)
            v1 = {"nodes": [], "edges": []}
            v2 = {"nodes": [{"id": "n1", "type": "llm"}], "edges": []}
            resp = client.post(
                "/api/v1/workflows/flow-1/diff",
                json={"v1": v1, "v2": v2},
                headers=_auth(token),
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["summary"]["nodes_added"] == 1

    def test_versions_post_returns_version_id(self):
        with TestClient(app) as client:
            token = _register(client)
            snapshot = {"nodes": [{"id": "n1"}], "edges": []}
            resp = client.post(
                "/api/v1/workflows/flow-abc/versions",
                json={"snapshot": snapshot, "label": "first"},
                headers=_auth(token),
            )
            assert resp.status_code == 200
            data = resp.json()
            assert "version_id" in data
            assert data["flow_id"] == "flow-abc"
            assert data["node_count"] == 1

    def test_version_history_returns_total(self):
        with TestClient(app) as client:
            token = _register(client)
            fid = f"flow-{uuid.uuid4().hex[:8]}"
            # Save two versions
            for lbl in ("v1", "v2"):
                resp = client.post(
                    f"/api/v1/workflows/{fid}/versions",
                    json={"snapshot": {"nodes": [], "edges": []}, "label": lbl},
                    headers=_auth(token),
                )
                assert resp.status_code == 200

            resp = client.get(
                f"/api/v1/workflows/{fid}/version-history",
                headers=_auth(token),
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["total"] == 2
            assert isinstance(data["versions"], list)
            assert len(data["versions"]) >= 1  # Gate 2
            assert data["flow_id"] == fid

    def test_get_specific_version_200_and_404(self):
        with TestClient(app) as client:
            token = _register(client)
            fid = f"flow-{uuid.uuid4().hex[:8]}"
            snapshot = {"nodes": [{"id": "n99"}], "edges": []}
            # Save version
            save_resp = client.post(
                f"/api/v1/workflows/{fid}/versions",
                json={"snapshot": snapshot, "label": "release"},
                headers=_auth(token),
            )
            assert save_resp.status_code == 200
            vid = save_resp.json()["version_id"]

            # Fetch existing version
            resp = client.get(
                f"/api/v1/workflows/{fid}/versions/{vid}",
                headers=_auth(token),
            )
            assert resp.status_code == 200
            assert resp.json()["version_id"] == vid

            # Fetch nonexistent version
            resp404 = client.get(
                f"/api/v1/workflows/{fid}/versions/does-not-exist",
                headers=_auth(token),
            )
            assert resp404.status_code == 404


# ---------------------------------------------------------------------------
# TestProfilerEndpoints — 6 tests (auth x2 + 4 functional)
# ---------------------------------------------------------------------------


class TestProfilerEndpoints:
    def setup_method(self):
        execution_log_store.reset()

    def teardown_method(self):
        execution_log_store.reset()

    def test_workflow_profile_requires_auth(self):
        with TestClient(app) as client:
            _register(client)  # ensure non-trivial DB state (disables anonymous bootstrap)
            resp = client.get("/api/v1/workflows/flow-1/profile")
            assert resp.status_code in (401, 403)
            assert "error" in resp.json()

    def test_execution_profile_requires_auth(self):
        with TestClient(app) as client:
            _register(client)  # ensure non-trivial DB state (disables anonymous bootstrap)
            resp = client.get("/api/v1/executions/eid-1/profile")
            assert resp.status_code in (401, 403)
            assert "error" in resp.json()

    def test_workflow_profile_returns_200_with_nodes_list(self):
        run_id = str(uuid.uuid4())
        execution_log_store.append(
            run_id,
            {"event": "node_success", "node_id": "my_node", "duration_ms": 42.0},
        )
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get(
                "/api/v1/workflows/any-flow/profile",
                headers=_auth(token),
            )
            assert resp.status_code == 200
            data = resp.json()
            assert "nodes" in data
            assert isinstance(data["nodes"], list)
            assert len(data["nodes"]) >= 1  # Gate 2

    def test_workflow_profile_empty_store_returns_200(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get(
                "/api/v1/workflows/empty-flow/profile",
                headers=_auth(token),
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["nodes"] == []
            assert data["total_node_types_profiled"] == 0

    def test_execution_profile_404_unknown(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get(
                "/api/v1/executions/unknown-exec-id/profile",
                headers=_auth(token),
            )
            assert resp.status_code == 404
            assert "error" in resp.json()

    def test_execution_profile_returns_bottleneck_node_id(self):
        eid = str(uuid.uuid4())
        execution_log_store.append(
            eid, {"event": "node_success", "node_id": "fast", "duration_ms": 10.0}
        )
        execution_log_store.append(
            eid, {"event": "node_success", "node_id": "slow", "duration_ms": 999.0}
        )
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get(
                f"/api/v1/executions/{eid}/profile",
                headers=_auth(token),
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["bottleneck_node_id"] == "slow"
            assert data["total_duration_ms"] == pytest.approx(1009.0)
            assert isinstance(data["nodes"], list)
            assert len(data["nodes"]) >= 1  # Gate 2


# needed for approx
import pytest  # noqa: E402
