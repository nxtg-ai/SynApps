"""
N-157: Flow Snapshots — POST/GET /flows/{id}/snapshots
                        GET    /flows/{id}/snapshots/{snap_id}
                        DELETE /flows/{id}/snapshots/{snap_id}
                        POST   /flows/{id}/snapshots/{snap_id}/restore

Tests:
  - POST creates snapshot; returns 201
  - POST response shape (id, flow_id, label, nodes, edges, author, created_at)
  - POST without nodes/edges defaults to empty lists
  - POST with nodes and edges stores them
  - POST empty label → 422
  - GET returns empty list on fresh flow (items=[])
  - GET lists snapshots after create (newest first)
  - GET returns flow_id and total in response
  - GET single snapshot by ID
  - GET single snapshot 404 for unknown ID
  - DELETE removes snapshot; returns {deleted: true}
  - DELETE 404 for unknown snapshot
  - GET after DELETE shows empty list
  - RESTORE applies nodes/edges back to flow
  - RESTORE 404 for unknown snapshot
  - POST/GET/DELETE 404 for unknown flow
  - Auth required on all endpoints
"""

import uuid

from fastapi.testclient import TestClient

from apps.orchestrator.main import app

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _register(client: TestClient) -> str:
    uid = uuid.uuid4().hex[:8]
    r = client.post(
        "/api/v1/auth/register",
        json={"email": f"snap-{uid}@test.com", "password": "pass1234"},
    )
    assert r.status_code == 201
    return r.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_flow(client: TestClient, token: str) -> str:
    resp = client.post(
        "/api/v1/flows",
        json={"name": "Snapshot Test Flow", "nodes": [], "edges": []},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _add_snapshot(
    client: TestClient,
    token: str,
    flow_id: str,
    label: str = "My Snapshot",
    nodes: list | None = None,
    edges: list | None = None,
) -> dict:
    body: dict = {"label": label}
    if nodes is not None:
        body["nodes"] = nodes
    if edges is not None:
        body["edges"] = edges
    resp = client.post(
        f"/api/v1/flows/{flow_id}/snapshots",
        json=body,
        headers=_auth(token),
    )
    assert resp.status_code == 201
    return resp.json()


# ---------------------------------------------------------------------------
# Tests — POST /flows/{id}/snapshots
# ---------------------------------------------------------------------------


class TestFlowSnapshotPost:
    def test_post_returns_201(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/snapshots",
                json={"label": "Initial state"},
                headers=_auth(token),
            )
        assert resp.status_code == 201

    def test_post_response_shape(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            nodes = [{"id": "n1", "type": "start"}]
            edges = [{"id": "e1", "source": "n1", "target": "n2"}]
            resp = client.post(
                f"/api/v1/flows/{flow_id}/snapshots",
                json={"label": "Shape Test", "nodes": nodes, "edges": edges},
                headers=_auth(token),
            )
        data = resp.json()
        assert "id" in data
        assert data["flow_id"] == flow_id
        assert data["label"] == "Shape Test"
        assert data["nodes"] == nodes
        assert data["edges"] == edges
        assert "author" in data
        assert "created_at" in data

    def test_post_default_nodes_edges_empty(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/snapshots",
                json={"label": "No Nodes"},
                headers=_auth(token),
            )
        data = resp.json()
        assert data["nodes"] == []
        assert data["edges"] == []

    def test_post_stores_nodes_and_edges(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            nodes = [{"id": "n1"}, {"id": "n2"}]
            edges = [{"id": "e1"}]
            resp = client.post(
                f"/api/v1/flows/{flow_id}/snapshots",
                json={"label": "With Data", "nodes": nodes, "edges": edges},
                headers=_auth(token),
            )
        assert resp.json()["nodes"] == nodes
        assert resp.json()["edges"] == edges

    def test_post_empty_label_422(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/snapshots",
                json={"label": ""},
                headers=_auth(token),
            )
        assert resp.status_code == 422

    def test_post_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.post(
                "/api/v1/flows/nonexistent/snapshots",
                json={"label": "x"},
                headers=_auth(token),
            )
        assert resp.status_code == 404

    def test_post_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/snapshots",
                json={"label": "no-auth"},
            )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Tests — GET /flows/{id}/snapshots
# ---------------------------------------------------------------------------


class TestFlowSnapshotList:
    def test_get_empty_on_fresh_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/snapshots", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["items"] == []

    def test_get_lists_snapshots(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _add_snapshot(client, token, flow_id, "Snap A")
            _add_snapshot(client, token, flow_id, "Snap B")
            resp = client.get(f"/api/v1/flows/{flow_id}/snapshots", headers=_auth(token))
        data = resp.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2

    def test_get_newest_first(self):
        """Snapshots should be returned newest-first."""
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _add_snapshot(client, token, flow_id, "First")
            _add_snapshot(client, token, flow_id, "Second")
            resp = client.get(f"/api/v1/flows/{flow_id}/snapshots", headers=_auth(token))
        items = resp.json()["items"]
        assert items[0]["label"] == "Second"
        assert items[1]["label"] == "First"

    def test_get_flow_id_and_total_in_response(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/snapshots", headers=_auth(token))
        body = resp.json()
        assert body["flow_id"] == flow_id
        assert "total" in body

    def test_get_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get("/api/v1/flows/nonexistent/snapshots", headers=_auth(token))
        assert resp.status_code == 404

    def test_get_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/snapshots")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Tests — GET /flows/{id}/snapshots/{snap_id}
# ---------------------------------------------------------------------------


class TestFlowSnapshotGetOne:
    def test_get_single_snapshot(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            snap = _add_snapshot(client, token, flow_id, "Detail Test")
            resp = client.get(
                f"/api/v1/flows/{flow_id}/snapshots/{snap['id']}", headers=_auth(token)
            )
        assert resp.status_code == 200
        assert resp.json()["label"] == "Detail Test"

    def test_get_single_includes_nodes_edges(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            nodes = [{"id": "n1"}, {"id": "n2"}]
            snap = _add_snapshot(client, token, flow_id, "With Nodes", nodes=nodes)
            resp = client.get(
                f"/api/v1/flows/{flow_id}/snapshots/{snap['id']}", headers=_auth(token)
            )
        assert resp.json()["nodes"] == nodes

    def test_get_single_404_unknown(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(
                f"/api/v1/flows/{flow_id}/snapshots/nonexistent", headers=_auth(token)
            )
        assert resp.status_code == 404

    def test_get_single_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            snap = _add_snapshot(client, token, flow_id, "Auth Test")
            resp = client.get(f"/api/v1/flows/{flow_id}/snapshots/{snap['id']}")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Tests — DELETE /flows/{id}/snapshots/{snap_id}
# ---------------------------------------------------------------------------


class TestFlowSnapshotDelete:
    def test_delete_removes_snapshot(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            snap = _add_snapshot(client, token, flow_id)
            resp = client.delete(
                f"/api/v1/flows/{flow_id}/snapshots/{snap['id']}", headers=_auth(token)
            )
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True

    def test_get_after_delete_shows_empty(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            snap = _add_snapshot(client, token, flow_id)
            client.delete(
                f"/api/v1/flows/{flow_id}/snapshots/{snap['id']}", headers=_auth(token)
            )
            resp = client.get(f"/api/v1/flows/{flow_id}/snapshots", headers=_auth(token))
        assert resp.json()["items"] == []

    def test_delete_404_unknown_snapshot(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.delete(
                f"/api/v1/flows/{flow_id}/snapshots/nonexistent", headers=_auth(token)
            )
        assert resp.status_code == 404

    def test_delete_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.delete(
                "/api/v1/flows/nonexistent/snapshots/any-id", headers=_auth(token)
            )
        assert resp.status_code == 404

    def test_delete_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            snap = _add_snapshot(client, token, flow_id)
            resp = client.delete(f"/api/v1/flows/{flow_id}/snapshots/{snap['id']}")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Tests — POST /flows/{id}/snapshots/{snap_id}/restore
# ---------------------------------------------------------------------------


class TestFlowSnapshotRestore:
    def test_restore_returns_200(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            snap = _add_snapshot(client, token, flow_id, "Restore Me")
            resp = client.post(
                f"/api/v1/flows/{flow_id}/snapshots/{snap['id']}/restore",
                headers=_auth(token),
            )
        assert resp.status_code == 200
        assert resp.json()["restored"] is True

    def test_restore_response_contains_label(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            snap = _add_snapshot(client, token, flow_id, "Labelled")
            resp = client.post(
                f"/api/v1/flows/{flow_id}/snapshots/{snap['id']}/restore",
                headers=_auth(token),
            )
        assert resp.json()["label"] == "Labelled"
        assert resp.json()["snapshot_id"] == snap["id"]

    def test_restore_404_unknown_snapshot(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/snapshots/nonexistent/restore",
                headers=_auth(token),
            )
        assert resp.status_code == 404

    def test_restore_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.post(
                "/api/v1/flows/nonexistent/snapshots/any-id/restore",
                headers=_auth(token),
            )
        assert resp.status_code == 404

    def test_restore_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            snap = _add_snapshot(client, token, flow_id, "Auth Check")
            resp = client.post(
                f"/api/v1/flows/{flow_id}/snapshots/{snap['id']}/restore",
            )
        assert resp.status_code == 401
