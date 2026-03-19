"""Tests for D-78: Workflow Versioning + Rollback.

Covers:
- FlowVersionRegistry unit tests
- _diff_flow_snapshots unit tests
- HTTP endpoint tests for versioning, rollback, and diff
"""

import pytest
from fastapi.testclient import TestClient

from apps.orchestrator.main import (
    FlowVersionRegistry,
    _diff_flow_snapshots,
    app,
    flow_version_registry,
)

# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

SNAP_A = {
    "nodes": [{"id": "n1", "type": "start", "data": {}}],
    "edges": [],
}
SNAP_B = {
    "nodes": [
        {"id": "n1", "type": "start", "data": {}},
        {"id": "n2", "type": "end", "data": {}},
    ],
    "edges": [{"source": "n1", "target": "n2"}],
}

_FLOW_V1 = {
    "id": "ver-test-flow-001",
    "name": "Version Test Flow",
    "nodes": [
        {"id": "start", "type": "start", "position": {"x": 0, "y": 0}, "data": {"label": "Start"}},
        {"id": "end", "type": "end", "position": {"x": 0, "y": 100}, "data": {"label": "End"}},
    ],
    "edges": [{"id": "e1", "source": "start", "target": "end"}],
}
_FLOW_V2_NODES = [
    {"id": "start", "type": "start", "position": {"x": 0, "y": 0}, "data": {"label": "Start"}},
    {"id": "llm1", "type": "llm", "position": {"x": 0, "y": 50}, "data": {"label": "LLM"}},
    {"id": "end", "type": "end", "position": {"x": 0, "y": 100}, "data": {"label": "End"}},
]

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_registry():
    """Reset the global flow_version_registry between every test."""
    flow_version_registry._versions.clear()
    yield
    flow_version_registry._versions.clear()


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def _auth_headers(client):
    client.post(
        "/api/v1/auth/register",
        json={"email": "veruser@test.com", "password": "verpass123"},
    )
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": "veruser@test.com", "password": "verpass123"},
    )
    token = resp.json().get("access_token", "")
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# TestFlowVersionRegistryUnit
# ---------------------------------------------------------------------------


class TestFlowVersionRegistryUnit:
    """Direct unit tests of FlowVersionRegistry."""

    def test_snapshot_returns_entry_with_version_id(self):
        reg = FlowVersionRegistry()
        entry = reg.snapshot("flow-1", {"nodes": [], "edges": []})
        assert "version_id" in entry
        assert entry["version_id"] != ""

    def test_snapshot_increments_version_number(self):
        reg = FlowVersionRegistry()
        e1 = reg.snapshot("flow-1", {"nodes": [], "edges": []})
        e2 = reg.snapshot("flow-1", {"nodes": [{"id": "n1"}], "edges": []})
        assert e1["version"] == 1
        assert e2["version"] == 2

    def test_list_versions_returns_newest_first(self):
        reg = FlowVersionRegistry()
        reg.snapshot("flow-1", {"nodes": [], "edges": []})
        reg.snapshot("flow-1", {"nodes": [{"id": "n1"}], "edges": []})
        versions = reg.list_versions("flow-1")
        assert isinstance(versions, list)
        assert len(versions) >= 2
        assert versions[0]["version"] > versions[1]["version"]

    def test_list_versions_empty_flow(self):
        reg = FlowVersionRegistry()
        versions = reg.list_versions("no-such-flow")
        assert versions == []

    def test_get_version_returns_full_snapshot(self):
        reg = FlowVersionRegistry()
        entry = reg.snapshot("flow-1", {"nodes": [{"id": "x"}], "edges": []})
        vid = entry["version_id"]
        fetched = reg.get_version("flow-1", vid)
        assert fetched is not None
        assert fetched["snapshot"]["nodes"] == [{"id": "x"}]

    def test_get_version_missing_returns_none(self):
        reg = FlowVersionRegistry()
        result = reg.get_version("flow-1", "nonexistent-version-id")
        assert result is None

    def test_get_latest_returns_most_recent(self):
        reg = FlowVersionRegistry()
        reg.snapshot("flow-1", {"nodes": [], "edges": []})
        e2 = reg.snapshot("flow-1", {"nodes": [{"id": "n99"}], "edges": []})
        latest = reg.get_latest("flow-1")
        assert latest is not None
        assert latest["version_id"] == e2["version_id"]

    def test_get_latest_no_versions_returns_none(self):
        reg = FlowVersionRegistry()
        assert reg.get_latest("ghost-flow") is None

    def test_diff_returns_diff_dict(self):
        reg = FlowVersionRegistry()
        ea = reg.snapshot("flow-1", SNAP_A)
        eb = reg.snapshot("flow-1", SNAP_B)
        result = reg.diff("flow-1", ea["version_id"], eb["version_id"])
        assert result is not None
        assert "nodes_added" in result
        assert "n2" in result["nodes_added"]

    def test_diff_missing_version_returns_none(self):
        reg = FlowVersionRegistry()
        reg.snapshot("flow-1", SNAP_A)
        result = reg.diff("flow-1", "bad-id-a", "bad-id-b")
        assert result is None


# ---------------------------------------------------------------------------
# TestDiffFlowSnapshots
# ---------------------------------------------------------------------------


class TestDiffFlowSnapshots:
    """Unit tests for _diff_flow_snapshots."""

    def test_diff_nodes_added(self):
        result = _diff_flow_snapshots(SNAP_A, SNAP_B)
        assert "n2" in result["nodes_added"]

    def test_diff_nodes_removed(self):
        result = _diff_flow_snapshots(SNAP_B, SNAP_A)
        assert "n2" in result["nodes_removed"]

    def test_diff_nodes_changed_type(self):
        snap_x = {"nodes": [{"id": "n1", "type": "start", "data": {}}], "edges": []}
        snap_y = {"nodes": [{"id": "n1", "type": "llm", "data": {}}], "edges": []}
        result = _diff_flow_snapshots(snap_x, snap_y)
        assert "n1" in result["nodes_changed"]

    def test_diff_nodes_changed_data(self):
        snap_x = {"nodes": [{"id": "n1", "type": "start", "data": {"label": "A"}}], "edges": []}
        snap_y = {"nodes": [{"id": "n1", "type": "start", "data": {"label": "B"}}], "edges": []}
        result = _diff_flow_snapshots(snap_x, snap_y)
        assert "n1" in result["nodes_changed"]

    def test_diff_edges_added(self):
        result = _diff_flow_snapshots(SNAP_A, SNAP_B)
        assert result["summary"]["edges_added"] == 1

    def test_diff_no_changes_empty_diffs(self):
        result = _diff_flow_snapshots(SNAP_A, SNAP_A)
        assert result["nodes_added"] == []
        assert result["nodes_removed"] == []
        assert result["nodes_changed"] == []
        assert result["edges_added"] == []
        assert result["edges_removed"] == []


# ---------------------------------------------------------------------------
# TestFlowVersioningEndpoints
# ---------------------------------------------------------------------------


class TestFlowVersioningEndpoints:
    """HTTP endpoint tests for versioning, rollback, and diff."""

    def test_put_creates_flow_if_not_exists(self, client):
        headers = _auth_headers(client)
        resp = client.put(
            f"/api/v1/flows/{_FLOW_V1['id']}",
            json={"name": _FLOW_V1["name"], "nodes": _FLOW_V1["nodes"], "edges": _FLOW_V1["edges"]},
            headers=headers,
        )
        assert resp.status_code in (200, 201)
        data = resp.json()
        assert data["id"] == _FLOW_V1["id"]

    def test_put_updates_existing_flow(self, client):
        headers = _auth_headers(client)
        fid = _FLOW_V1["id"]
        client.put(
            f"/api/v1/flows/{fid}",
            json={"name": _FLOW_V1["name"], "nodes": _FLOW_V1["nodes"], "edges": _FLOW_V1["edges"]},
            headers=headers,
        )
        resp = client.put(
            f"/api/v1/flows/{fid}",
            json={"name": "Updated Name", "nodes": _FLOW_V2_NODES, "edges": []},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated Name"

    def test_put_creates_version_snapshot_on_update(self, client):
        headers = _auth_headers(client)
        fid = _FLOW_V1["id"]
        # First PUT (creates)
        client.put(
            f"/api/v1/flows/{fid}",
            json={"name": _FLOW_V1["name"], "nodes": _FLOW_V1["nodes"], "edges": _FLOW_V1["edges"]},
            headers=headers,
        )
        # Second PUT (updates — should snapshot the first state)
        client.put(
            f"/api/v1/flows/{fid}",
            json={"name": "V2", "nodes": _FLOW_V2_NODES, "edges": []},
            headers=headers,
        )
        versions = flow_version_registry.list_versions(fid)
        assert isinstance(versions, list)
        assert len(versions) >= 1

    def test_list_versions_empty_initially(self, client):
        headers = _auth_headers(client)
        fid = _FLOW_V1["id"]
        client.put(
            f"/api/v1/flows/{fid}",
            json={"name": _FLOW_V1["name"], "nodes": _FLOW_V1["nodes"], "edges": _FLOW_V1["edges"]},
            headers=headers,
        )
        resp = client.get(f"/api/v1/flows/{fid}/versions", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["items"] == []

    def test_list_versions_after_update(self, client):
        headers = _auth_headers(client)
        fid = _FLOW_V1["id"]
        client.put(
            f"/api/v1/flows/{fid}",
            json={"name": _FLOW_V1["name"], "nodes": _FLOW_V1["nodes"], "edges": _FLOW_V1["edges"]},
            headers=headers,
        )
        client.put(
            f"/api/v1/flows/{fid}",
            json={"name": "V2", "nodes": _FLOW_V2_NODES, "edges": []},
            headers=headers,
        )
        resp = client.get(f"/api/v1/flows/{fid}/versions", headers=headers)
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert isinstance(items, list)
        assert len(items) >= 1

    def test_list_versions_flow_not_found(self, client):
        headers = _auth_headers(client)
        resp = client.get("/api/v1/flows/nonexistent-flow-xyz/versions", headers=headers)
        assert resp.status_code == 404

    def test_get_version_success(self, client):
        headers = _auth_headers(client)
        fid = _FLOW_V1["id"]
        client.put(
            f"/api/v1/flows/{fid}",
            json={"name": _FLOW_V1["name"], "nodes": _FLOW_V1["nodes"], "edges": _FLOW_V1["edges"]},
            headers=headers,
        )
        client.put(
            f"/api/v1/flows/{fid}",
            json={"name": "V2", "nodes": _FLOW_V2_NODES, "edges": []},
            headers=headers,
        )
        versions = flow_version_registry.list_versions(fid)
        assert len(versions) >= 1
        vid = versions[0]["version_id"]
        resp = client.get(f"/api/v1/flows/{fid}/versions/{vid}", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["version_id"] == vid

    def test_get_version_not_found(self, client):
        headers = _auth_headers(client)
        fid = _FLOW_V1["id"]
        client.put(
            f"/api/v1/flows/{fid}",
            json={"name": _FLOW_V1["name"], "nodes": _FLOW_V1["nodes"], "edges": _FLOW_V1["edges"]},
            headers=headers,
        )
        resp = client.get(f"/api/v1/flows/{fid}/versions/no-such-version", headers=headers)
        assert resp.status_code == 404

    def test_get_version_snapshot_contains_nodes(self, client):
        headers = _auth_headers(client)
        fid = _FLOW_V1["id"]
        client.put(
            f"/api/v1/flows/{fid}",
            json={"name": _FLOW_V1["name"], "nodes": _FLOW_V1["nodes"], "edges": _FLOW_V1["edges"]},
            headers=headers,
        )
        client.put(
            f"/api/v1/flows/{fid}",
            json={"name": "V2", "nodes": _FLOW_V2_NODES, "edges": []},
            headers=headers,
        )
        versions = flow_version_registry.list_versions(fid)
        assert len(versions) >= 1
        vid = versions[0]["version_id"]
        resp = client.get(f"/api/v1/flows/{fid}/versions/{vid}", headers=headers)
        assert resp.status_code == 200
        snapshot = resp.json()["snapshot"]
        assert "nodes" in snapshot

    def test_rollback_restores_previous_version(self, client):
        headers = _auth_headers(client)
        fid = _FLOW_V1["id"]
        # Create V1
        client.put(
            f"/api/v1/flows/{fid}",
            json={"name": _FLOW_V1["name"], "nodes": _FLOW_V1["nodes"], "edges": _FLOW_V1["edges"]},
            headers=headers,
        )
        # Update to V2 (this snapshots V1)
        client.put(
            f"/api/v1/flows/{fid}",
            json={"name": "V2", "nodes": _FLOW_V2_NODES, "edges": []},
            headers=headers,
        )
        # Get the V1 snapshot version id
        versions = flow_version_registry.list_versions(fid)
        assert len(versions) >= 1
        vid = versions[0]["version_id"]
        # Rollback
        resp = client.post(f"/api/v1/flows/{fid}/rollback?version_id={vid}", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "flow" in data
        assert data["rolled_back_to"] == vid

    def test_rollback_version_not_found(self, client):
        headers = _auth_headers(client)
        fid = _FLOW_V1["id"]
        client.put(
            f"/api/v1/flows/{fid}",
            json={"name": _FLOW_V1["name"], "nodes": _FLOW_V1["nodes"], "edges": _FLOW_V1["edges"]},
            headers=headers,
        )
        resp = client.post(
            f"/api/v1/flows/{fid}/rollback?version_id=bad-version-id", headers=headers
        )
        assert resp.status_code == 404

    def test_rollback_creates_snapshot_of_current(self, client):
        headers = _auth_headers(client)
        fid = _FLOW_V1["id"]
        client.put(
            f"/api/v1/flows/{fid}",
            json={"name": _FLOW_V1["name"], "nodes": _FLOW_V1["nodes"], "edges": _FLOW_V1["edges"]},
            headers=headers,
        )
        client.put(
            f"/api/v1/flows/{fid}",
            json={"name": "V2", "nodes": _FLOW_V2_NODES, "edges": []},
            headers=headers,
        )
        count_before = len(flow_version_registry.list_versions(fid))
        vid = flow_version_registry.list_versions(fid)[0]["version_id"]
        client.post(f"/api/v1/flows/{fid}/rollback?version_id={vid}", headers=headers)
        count_after = len(flow_version_registry.list_versions(fid))
        assert count_after == count_before + 1

    def test_diff_between_two_versions(self, client):
        headers = _auth_headers(client)
        fid = _FLOW_V1["id"]
        client.put(
            f"/api/v1/flows/{fid}",
            json={"name": _FLOW_V1["name"], "nodes": _FLOW_V1["nodes"], "edges": _FLOW_V1["edges"]},
            headers=headers,
        )
        client.put(
            f"/api/v1/flows/{fid}",
            json={"name": "V2", "nodes": _FLOW_V2_NODES, "edges": []},
            headers=headers,
        )
        # Need two snapshots to diff
        client.put(
            f"/api/v1/flows/{fid}",
            json={"name": "V3", "nodes": _FLOW_V1["nodes"], "edges": _FLOW_V1["edges"]},
            headers=headers,
        )
        versions = flow_version_registry.list_versions(fid)
        assert len(versions) >= 2
        vid_a = versions[-1]["version_id"]  # oldest
        vid_b = versions[0]["version_id"]  # newest
        resp = client.get(
            f"/api/v1/flows/{fid}/diff?version_a={vid_a}&version_b={vid_b}", headers=headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "summary" in data

    def test_diff_version_a_not_found(self, client):
        headers = _auth_headers(client)
        fid = _FLOW_V1["id"]
        client.put(
            f"/api/v1/flows/{fid}",
            json={"name": _FLOW_V1["name"], "nodes": _FLOW_V1["nodes"], "edges": _FLOW_V1["edges"]},
            headers=headers,
        )
        client.put(
            f"/api/v1/flows/{fid}",
            json={"name": "V2", "nodes": _FLOW_V2_NODES, "edges": []},
            headers=headers,
        )
        versions = flow_version_registry.list_versions(fid)
        assert len(versions) >= 1
        vid_b = versions[0]["version_id"]
        resp = client.get(
            f"/api/v1/flows/{fid}/diff?version_a=bad-version-a&version_b={vid_b}",
            headers=headers,
        )
        assert resp.status_code == 404

    def test_diff_version_b_not_found(self, client):
        headers = _auth_headers(client)
        fid = _FLOW_V1["id"]
        client.put(
            f"/api/v1/flows/{fid}",
            json={"name": _FLOW_V1["name"], "nodes": _FLOW_V1["nodes"], "edges": _FLOW_V1["edges"]},
            headers=headers,
        )
        client.put(
            f"/api/v1/flows/{fid}",
            json={"name": "V2", "nodes": _FLOW_V2_NODES, "edges": []},
            headers=headers,
        )
        versions = flow_version_registry.list_versions(fid)
        assert len(versions) >= 1
        vid_a = versions[0]["version_id"]
        resp = client.get(
            f"/api/v1/flows/{fid}/diff?version_a={vid_a}&version_b=bad-version-b",
            headers=headers,
        )
        assert resp.status_code == 404

    def test_diff_against_current_using_keyword(self, client):
        headers = _auth_headers(client)
        fid = _FLOW_V1["id"]
        client.put(
            f"/api/v1/flows/{fid}",
            json={"name": _FLOW_V1["name"], "nodes": _FLOW_V1["nodes"], "edges": _FLOW_V1["edges"]},
            headers=headers,
        )
        client.put(
            f"/api/v1/flows/{fid}",
            json={"name": "V2", "nodes": _FLOW_V2_NODES, "edges": []},
            headers=headers,
        )
        versions = flow_version_registry.list_versions(fid)
        assert len(versions) >= 1
        vid_a = versions[0]["version_id"]
        resp = client.get(
            f"/api/v1/flows/{fid}/diff?version_a={vid_a}&version_b=current",
            headers=headers,
        )
        assert resp.status_code == 200
        assert "nodes_added" in resp.json()

    def test_diff_summary_keys_present(self, client):
        headers = _auth_headers(client)
        fid = _FLOW_V1["id"]
        client.put(
            f"/api/v1/flows/{fid}",
            json={"name": _FLOW_V1["name"], "nodes": _FLOW_V1["nodes"], "edges": _FLOW_V1["edges"]},
            headers=headers,
        )
        client.put(
            f"/api/v1/flows/{fid}",
            json={"name": "V2", "nodes": _FLOW_V2_NODES, "edges": []},
            headers=headers,
        )
        versions = flow_version_registry.list_versions(fid)
        assert len(versions) >= 1
        vid_a = versions[0]["version_id"]
        resp = client.get(
            f"/api/v1/flows/{fid}/diff?version_a={vid_a}&version_b=current",
            headers=headers,
        )
        assert resp.status_code == 200
        summary = resp.json()["summary"]
        for key in (
            "nodes_added",
            "nodes_removed",
            "nodes_changed",
            "edges_added",
            "edges_removed",
        ):
            assert key in summary

    def test_list_versions_returns_items_key(self, client):
        headers = _auth_headers(client)
        fid = _FLOW_V1["id"]
        client.put(
            f"/api/v1/flows/{fid}",
            json={"name": _FLOW_V1["name"], "nodes": _FLOW_V1["nodes"], "edges": _FLOW_V1["edges"]},
            headers=headers,
        )
        resp = client.get(f"/api/v1/flows/{fid}/versions", headers=headers)
        assert resp.status_code == 200
        assert "items" in resp.json()

    def test_put_flow_name_preserved_if_not_provided(self, client):
        headers = _auth_headers(client)
        fid = _FLOW_V1["id"]
        client.put(
            f"/api/v1/flows/{fid}",
            json={"name": "Preserved Name", "nodes": _FLOW_V1["nodes"], "edges": _FLOW_V1["edges"]},
            headers=headers,
        )
        # Update without providing a name
        resp = client.put(
            f"/api/v1/flows/{fid}",
            json={"nodes": _FLOW_V2_NODES, "edges": []},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Preserved Name"
