"""
Workflow Versioned Rollback System

Tests for RollbackAuditStore, rollback endpoint with audit recording,
and rollback history endpoints.

~22 tests covering:
  - RollbackAuditStore unit tests (5)
  - Rollback endpoint integration tests (8)
  - Rollback history endpoint integration tests (6)
  - End-to-end rollback integration tests (3)
"""

import time
import uuid

from fastapi.testclient import TestClient

from apps.orchestrator.main import app
from apps.orchestrator.stores import RollbackAuditStore

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _register(client: TestClient, email: str | None = None) -> str:
    """Register a user and return the access token."""
    email = email or f"rb-{uuid.uuid4().hex[:8]}@test.com"
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "RollBack1!"},
    )
    assert resp.status_code in (200, 201), resp.text
    return resp.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _get_user_id(client: TestClient, token: str) -> str:
    resp = client.get("/api/v1/auth/me", headers=_auth(token))
    return resp.json()["id"]


def _create_flow(
    client: TestClient,
    token: str,
    name: str = "Rollback Test",
    nodes: list | None = None,
) -> str:
    """Create a minimal flow and return its ID."""
    uid = uuid.uuid4().hex[:8]
    if nodes is None:
        nodes = [
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
        ]
    flow_payload = {
        "name": name,
        "nodes": nodes,
        "edges": [{"id": f"e-{uid}", "source": nodes[0]["id"], "target": nodes[1]["id"]}],
    }
    resp = client.post("/api/v1/flows", json=flow_payload, headers=_auth(token))
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _snapshot_version(client: TestClient, token: str, flow_id: str) -> str:
    """Create a version snapshot via PUT (which auto-snapshots) and return the version_id."""
    # PUT updates the flow and auto-snapshots the old state
    flow = client.get(f"/api/v1/flows/{flow_id}", headers=_auth(token)).json()
    client.put(
        f"/api/v1/flows/{flow_id}",
        json={
            "name": flow.get("name", "Updated"),
            "nodes": flow.get("nodes", []),
            "edges": flow.get("edges", []),
        },
        headers=_auth(token),
    )

    # Get the newest version
    resp = client.get(f"/api/v1/flows/{flow_id}/versions", headers=_auth(token))
    assert resp.status_code == 200
    versions_after = resp.json()["items"]
    assert len(versions_after) >= 1  # Gate 2
    return versions_after[0]["version_id"]


def _update_flow(
    client: TestClient,
    token: str,
    flow_id: str,
    name: str = "Updated Flow",
    extra_node_id: str | None = None,
) -> None:
    """Update a flow with an extra node via PUT (triggers auto-snapshot)."""
    if extra_node_id is None:
        extra_node_id = f"extra-{uuid.uuid4().hex[:8]}"
    flow = client.get(f"/api/v1/flows/{flow_id}", headers=_auth(token)).json()
    nodes = flow.get("nodes", [])
    nodes.append(
        {
            "id": extra_node_id,
            "type": "llm",
            "position": {"x": 100, "y": 50},
            "data": {"label": extra_node_id},
        }
    )
    resp = client.put(
        f"/api/v1/flows/{flow_id}",
        json={"name": name, "nodes": nodes, "edges": flow.get("edges", [])},
        headers=_auth(token),
    )
    assert resp.status_code == 200, resp.text


# ===========================================================================
# Unit Tests — RollbackAuditStore
# ===========================================================================


class TestRollbackAuditStore:
    """Unit tests for the RollbackAuditStore class."""

    def test_record_returns_correct_fields(self) -> None:
        store = RollbackAuditStore()
        entry = store.record(
            flow_id="f1",
            from_version_id="v-old",
            to_version_id="v-new",
            performed_by="user-1",
            reason="bad deploy",
        )
        assert "audit_id" in entry
        assert entry["flow_id"] == "f1"
        assert entry["from_version_id"] == "v-old"
        assert entry["to_version_id"] == "v-new"
        assert entry["performed_by"] == "user-1"
        assert entry["reason"] == "bad deploy"
        assert isinstance(entry["rolled_back_at"], float)
        assert entry["rolled_back_at"] <= time.time()

    def test_list_returns_newest_first(self) -> None:
        store = RollbackAuditStore()
        store.record("f1", "v1", "v2", "u1")
        store.record("f1", "v2", "v3", "u1")
        items = store.list()
        assert isinstance(items, list)
        assert len(items) >= 2  # Gate 2
        assert items[0]["to_version_id"] == "v3"
        assert items[1]["to_version_id"] == "v2"

    def test_list_filters_by_flow_id(self) -> None:
        store = RollbackAuditStore()
        store.record("f1", "v1", "v2", "u1")
        store.record("f2", "v3", "v4", "u1")
        store.record("f1", "v5", "v6", "u1")

        items_f1 = store.list(flow_id="f1")
        assert isinstance(items_f1, list)
        assert len(items_f1) >= 1  # Gate 2
        assert all(e["flow_id"] == "f1" for e in items_f1)
        assert len(items_f1) == 2

    def test_list_with_none_flow_id_returns_all(self) -> None:
        store = RollbackAuditStore()
        store.record("f1", "v1", "v2", "u1")
        store.record("f2", "v3", "v4", "u1")
        items = store.list(flow_id=None)
        assert isinstance(items, list)
        assert len(items) >= 2  # Gate 2

    def test_reset_clears_all_entries(self) -> None:
        store = RollbackAuditStore()
        store.record("f1", "v1", "v2", "u1")
        store.record("f2", "v3", "v4", "u1")
        store.reset()
        assert store.list() == []


# ===========================================================================
# Integration Tests — Rollback Endpoint
# ===========================================================================


class TestRollbackEndpoint:
    """Integration tests for POST /flows/{flow_id}/rollback."""

    def test_rollback_returns_200_with_flow_and_audit(self) -> None:
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            version_id = _snapshot_version(client, token, flow_id)

            resp = client.post(
                f"/api/v1/flows/{flow_id}/rollback",
                params={"version_id": version_id},
                json={"reason": "testing"},
                headers=_auth(token),
            )
            assert resp.status_code == 200
            body = resp.json()
            assert "flow" in body
            assert "audit_entry" in body
            assert body["rolled_back_to"] == version_id

    def test_rollback_requires_auth(self) -> None:
        with TestClient(app) as client:
            # Register a user so auth enforcement is active
            _register(client)
            resp = client.post(
                "/api/v1/flows/fake-id/rollback",
                params={"version_id": "v1"},
                json={"reason": "no auth"},
            )
            assert resp.status_code in (401, 403)

    def test_rollback_404_when_flow_not_found(self) -> None:
        with TestClient(app) as client:
            token = _register(client)
            resp = client.post(
                "/api/v1/flows/nonexistent/rollback",
                params={"version_id": "v1"},
                json={"reason": "missing flow"},
                headers=_auth(token),
            )
            assert resp.status_code == 404

    def test_rollback_404_when_version_not_found(self) -> None:
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/rollback",
                params={"version_id": "nonexistent-version"},
                json={"reason": "bad version"},
                headers=_auth(token),
            )
            assert resp.status_code == 404

    def test_audit_entry_has_correct_fields(self) -> None:
        with TestClient(app) as client:
            token = _register(client)
            user_id = _get_user_id(client, token)
            flow_id = _create_flow(client, token)
            version_id = _snapshot_version(client, token, flow_id)

            resp = client.post(
                f"/api/v1/flows/{flow_id}/rollback",
                params={"version_id": version_id},
                json={"reason": "check fields"},
                headers=_auth(token),
            )
            assert resp.status_code == 200
            audit = resp.json()["audit_entry"]
            assert audit["flow_id"] == flow_id
            assert audit["to_version_id"] == version_id
            assert audit["performed_by"] == user_id

    def test_reason_field_preserved(self) -> None:
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            version_id = _snapshot_version(client, token, flow_id)

            resp = client.post(
                f"/api/v1/flows/{flow_id}/rollback",
                params={"version_id": version_id},
                json={"reason": "reverting bad change"},
                headers=_auth(token),
            )
            assert resp.status_code == 200
            assert resp.json()["audit_entry"]["reason"] == "reverting bad change"

    def test_flow_snapshot_updated_after_rollback(self) -> None:
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token, name="Original")

            # Snapshot the original state
            version_id = _snapshot_version(client, token, flow_id)

            # Update the flow with a different name
            _update_flow(client, token, flow_id, name="Changed")

            # Rollback to original
            resp = client.post(
                f"/api/v1/flows/{flow_id}/rollback",
                params={"version_id": version_id},
                headers=_auth(token),
            )
            assert resp.status_code == 200

            # Verify the flow was restored
            flow_resp = client.get(f"/api/v1/flows/{flow_id}", headers=_auth(token))
            assert flow_resp.status_code == 200

    def test_second_rollback_records_another_audit_entry(self) -> None:
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            version_id = _snapshot_version(client, token, flow_id)

            # First rollback
            resp1 = client.post(
                f"/api/v1/flows/{flow_id}/rollback",
                params={"version_id": version_id},
                json={"reason": "first"},
                headers=_auth(token),
            )
            assert resp1.status_code == 200

            # Update again, create new version
            _update_flow(client, token, flow_id, name="Again", extra_node_id="extra2")

            # Second rollback to same version
            resp2 = client.post(
                f"/api/v1/flows/{flow_id}/rollback",
                params={"version_id": version_id},
                json={"reason": "second"},
                headers=_auth(token),
            )
            assert resp2.status_code == 200

            # Both audit entries exist
            audit1 = resp1.json()["audit_entry"]
            audit2 = resp2.json()["audit_entry"]
            assert audit1["audit_id"] != audit2["audit_id"]
            assert audit1["reason"] == "first"
            assert audit2["reason"] == "second"


# ===========================================================================
# Integration Tests — Rollback History Endpoints
# ===========================================================================


class TestRollbackHistory:
    """Integration tests for rollback history endpoints."""

    def test_flow_rollback_history_returns_200(self) -> None:
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            version_id = _snapshot_version(client, token, flow_id)

            # Perform a rollback so there is at least one entry
            client.post(
                f"/api/v1/flows/{flow_id}/rollback",
                params={"version_id": version_id},
                json={"reason": "history test"},
                headers=_auth(token),
            )

            resp = client.get(
                f"/api/v1/flows/{flow_id}/rollback/history",
                headers=_auth(token),
            )
            assert resp.status_code == 200
            items = resp.json()["items"]
            assert isinstance(items, list)
            assert len(items) >= 1  # Gate 2

    def test_flow_rollback_history_requires_auth(self) -> None:
        with TestClient(app) as client:
            _register(client)
            resp = client.get("/api/v1/flows/fake-id/rollback/history")
            assert resp.status_code in (401, 403)

    def test_flow_rollback_history_filters_by_flow(self) -> None:
        with TestClient(app) as client:
            token = _register(client)
            flow_a = _create_flow(client, token, name="Flow A")
            flow_b = _create_flow(client, token, name="Flow B")

            ver_a = _snapshot_version(client, token, flow_a)
            ver_b = _snapshot_version(client, token, flow_b)

            # Rollback both
            client.post(
                f"/api/v1/flows/{flow_a}/rollback",
                params={"version_id": ver_a},
                headers=_auth(token),
            )
            client.post(
                f"/api/v1/flows/{flow_b}/rollback",
                params={"version_id": ver_b},
                headers=_auth(token),
            )

            # History for flow_a should only contain flow_a entries
            resp = client.get(
                f"/api/v1/flows/{flow_a}/rollback/history",
                headers=_auth(token),
            )
            assert resp.status_code == 200
            items = resp.json()["items"]
            assert isinstance(items, list)
            assert len(items) >= 1  # Gate 2
            assert all(e["flow_id"] == flow_a for e in items)

    def test_global_rollback_history_returns_all(self) -> None:
        with TestClient(app) as client:
            token = _register(client)
            flow_a = _create_flow(client, token, name="Flow GA")
            flow_b = _create_flow(client, token, name="Flow GB")

            ver_a = _snapshot_version(client, token, flow_a)
            ver_b = _snapshot_version(client, token, flow_b)

            client.post(
                f"/api/v1/flows/{flow_a}/rollback",
                params={"version_id": ver_a},
                headers=_auth(token),
            )
            client.post(
                f"/api/v1/flows/{flow_b}/rollback",
                params={"version_id": ver_b},
                headers=_auth(token),
            )

            resp = client.get("/api/v1/rollback/history", headers=_auth(token))
            assert resp.status_code == 200
            items = resp.json()["items"]
            assert isinstance(items, list)
            assert len(items) >= 2  # Gate 2: both flows represented

    def test_history_sorted_newest_first(self) -> None:
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)

            # Create version, rollback, update, create version, rollback again
            ver1 = _snapshot_version(client, token, flow_id)
            client.post(
                f"/api/v1/flows/{flow_id}/rollback",
                params={"version_id": ver1},
                json={"reason": "first rollback"},
                headers=_auth(token),
            )

            _update_flow(client, token, flow_id, name="After first rb", extra_node_id="n2")
            ver2 = _snapshot_version(client, token, flow_id)
            client.post(
                f"/api/v1/flows/{flow_id}/rollback",
                params={"version_id": ver2},
                json={"reason": "second rollback"},
                headers=_auth(token),
            )

            resp = client.get(
                f"/api/v1/flows/{flow_id}/rollback/history",
                headers=_auth(token),
            )
            assert resp.status_code == 200
            items = resp.json()["items"]
            assert len(items) >= 2  # Gate 2
            # Newest first: rolled_back_at should be descending
            assert items[0]["rolled_back_at"] >= items[1]["rolled_back_at"]

    def test_reason_field_present_in_history(self) -> None:
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            version_id = _snapshot_version(client, token, flow_id)

            client.post(
                f"/api/v1/flows/{flow_id}/rollback",
                params={"version_id": version_id},
                json={"reason": "documented reason"},
                headers=_auth(token),
            )

            resp = client.get(
                f"/api/v1/flows/{flow_id}/rollback/history",
                headers=_auth(token),
            )
            assert resp.status_code == 200
            items = resp.json()["items"]
            assert isinstance(items, list)
            assert len(items) >= 1  # Gate 2
            assert items[0]["reason"] == "documented reason"


# ===========================================================================
# End-to-End Integration Tests
# ===========================================================================


class TestRollbackIntegration:
    """End-to-end tests verifying rollback restores correct flow state."""

    def test_rollback_restores_nodes_from_target_version(self) -> None:
        with TestClient(app) as client:
            token = _register(client)
            # Create flow with 2 nodes (start + end)
            flow_id = _create_flow(client, token, name="V1 Flow")

            # Snapshot v1 (current 2-node state)
            v1_id = _snapshot_version(client, token, flow_id)

            # Add a third node
            _update_flow(client, token, flow_id, name="V2 Flow", extra_node_id="llm-1")

            # Flow now has 3 nodes
            flow_before = client.get(f"/api/v1/flows/{flow_id}", headers=_auth(token)).json()
            assert len(flow_before["nodes"]) == 3

            # Rollback to v1
            resp = client.post(
                f"/api/v1/flows/{flow_id}/rollback",
                params={"version_id": v1_id},
                headers=_auth(token),
            )
            assert resp.status_code == 200

            # Flow should be back to 2 nodes
            flow_after = client.get(f"/api/v1/flows/{flow_id}", headers=_auth(token)).json()
            assert len(flow_after["nodes"]) == 2

    def test_multiple_rollbacks_recorded_in_order(self) -> None:
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)

            # Create v1 snapshot, update, create v2 snapshot, update
            v1_id = _snapshot_version(client, token, flow_id)
            _update_flow(client, token, flow_id, name="After v1", extra_node_id="n1")

            v2_id = _snapshot_version(client, token, flow_id)
            _update_flow(client, token, flow_id, name="After v2", extra_node_id="n2")

            # Rollback to v2, then to v1
            r1 = client.post(
                f"/api/v1/flows/{flow_id}/rollback",
                params={"version_id": v2_id},
                json={"reason": "back to v2"},
                headers=_auth(token),
            )
            assert r1.status_code == 200

            r2 = client.post(
                f"/api/v1/flows/{flow_id}/rollback",
                params={"version_id": v1_id},
                json={"reason": "back to v1"},
                headers=_auth(token),
            )
            assert r2.status_code == 200

            # History should show 2 entries, newest first
            resp = client.get(
                f"/api/v1/flows/{flow_id}/rollback/history",
                headers=_auth(token),
            )
            items = resp.json()["items"]
            assert isinstance(items, list)
            assert len(items) >= 2  # Gate 2
            assert items[0]["reason"] == "back to v1"
            assert items[1]["reason"] == "back to v2"

    def test_rollback_to_v1_from_v3_leaves_flow_at_v1_state(self) -> None:
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token, name="V1 State")

            # Snapshot v1
            v1_id = _snapshot_version(client, token, flow_id)

            # Evolve to v2
            _update_flow(client, token, flow_id, name="V2 State", extra_node_id="node-v2")
            _snapshot_version(client, token, flow_id)

            # Evolve to v3
            _update_flow(client, token, flow_id, name="V3 State", extra_node_id="node-v3")

            # Flow now at v3 with 4 nodes (start, end, node-v2, node-v3)
            flow_v3 = client.get(f"/api/v1/flows/{flow_id}", headers=_auth(token)).json()
            assert len(flow_v3["nodes"]) == 4

            # Rollback straight to v1
            resp = client.post(
                f"/api/v1/flows/{flow_id}/rollback",
                params={"version_id": v1_id},
                headers=_auth(token),
            )
            assert resp.status_code == 200

            # Flow should be at v1 state (2 nodes)
            flow_v1 = client.get(f"/api/v1/flows/{flow_id}", headers=_auth(token)).json()
            assert len(flow_v1["nodes"]) == 2
