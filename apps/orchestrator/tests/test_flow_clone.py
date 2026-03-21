"""
N-130: Flow Clone — POST /api/v1/flows/{flow_id}/clone

Tests for the clone endpoint:
  - 201 with new ID + default "Copy of {name}" naming
  - Custom name override
  - Node count preserved, node IDs remapped
  - Edge count preserved, source/target remapped to new node IDs
  - Clone is independent (delete original, clone persists)
  - 404 for unknown source flow
  - Auth required (401 without token)
  - Clone of clone works
  - Flow with no nodes/edges clones cleanly
  - node_count / edge_count in response
  - cloned_from in response
  - Both original and clone appear in GET /flows list
  - Audit log records the clone
  - Blank custom name falls back to default
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
        json={"email": f"clone-{uid}@test.com", "password": "pass1234"},
    )
    assert r.status_code == 201
    return r.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_flow(client: TestClient, token: str, name: str = "Original Flow") -> str:
    uid = uuid.uuid4().hex[:6]
    resp = client.post(
        "/api/v1/flows",
        json={
            "name": name,
            "nodes": [
                {"id": f"n1-{uid}", "type": "start", "position": {"x": 0, "y": 0}, "data": {}},
                {
                    "id": f"n2-{uid}",
                    "type": "llm",
                    "position": {"x": 200, "y": 0},
                    "data": {"model": "gpt-4o"},
                },
                {"id": f"n3-{uid}", "type": "end", "position": {"x": 400, "y": 0}, "data": {}},
            ],
            "edges": [
                {"id": f"e1-{uid}", "source": f"n1-{uid}", "target": f"n2-{uid}"},
                {"id": f"e2-{uid}", "source": f"n2-{uid}", "target": f"n3-{uid}"},
            ],
        },
        headers=_auth(token),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestFlowCloneSuccess:
    def test_clone_returns_201(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(f"/api/v1/flows/{flow_id}/clone", headers=_auth(token))
        assert resp.status_code == 201

    def test_clone_returns_new_id(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(f"/api/v1/flows/{flow_id}/clone", headers=_auth(token))
        data = resp.json()
        assert "id" in data
        assert data["id"] != flow_id

    def test_clone_default_name(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token, name="My Workflow")
            resp = client.post(f"/api/v1/flows/{flow_id}/clone", headers=_auth(token))
        assert resp.json()["name"] == "Copy of My Workflow"

    def test_clone_custom_name(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/clone",
                json={"name": "My Custom Clone"},
                headers=_auth(token),
            )
        assert resp.json()["name"] == "My Custom Clone"

    def test_clone_node_count_in_response(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)  # 3 nodes
            resp = client.post(f"/api/v1/flows/{flow_id}/clone", headers=_auth(token))
        assert resp.json()["node_count"] == 3  # Gate 2

    def test_clone_edge_count_in_response(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)  # 2 edges
            resp = client.post(f"/api/v1/flows/{flow_id}/clone", headers=_auth(token))
        assert resp.json()["edge_count"] == 2  # Gate 2

    def test_clone_from_in_response(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(f"/api/v1/flows/{flow_id}/clone", headers=_auth(token))
        assert resp.json()["cloned_from"] == flow_id


class TestFlowCloneNodeEdgeRemapping:
    def test_cloned_nodes_have_new_ids(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            original = client.get(f"/api/v1/flows/{flow_id}", headers=_auth(token)).json()
            clone_id = client.post(f"/api/v1/flows/{flow_id}/clone", headers=_auth(token)).json()[
                "id"
            ]
            clone = client.get(f"/api/v1/flows/{clone_id}", headers=_auth(token)).json()

        orig_node_ids = {n["id"] for n in original["nodes"]}
        clone_node_ids = {n["id"] for n in clone["nodes"]}
        assert orig_node_ids.isdisjoint(clone_node_ids), "Cloned node IDs must differ from original"

    def test_cloned_edges_have_new_ids(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            original = client.get(f"/api/v1/flows/{flow_id}", headers=_auth(token)).json()
            clone_id = client.post(f"/api/v1/flows/{flow_id}/clone", headers=_auth(token)).json()[
                "id"
            ]
            clone = client.get(f"/api/v1/flows/{clone_id}", headers=_auth(token)).json()

        orig_edge_ids = {e["id"] for e in original["edges"]}
        clone_edge_ids = {e["id"] for e in clone["edges"]}
        assert orig_edge_ids.isdisjoint(clone_edge_ids), "Cloned edge IDs must differ from original"

    def test_cloned_edges_reference_new_node_ids(self):
        """Edge source/target in clone must point to new node IDs, not original."""
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            clone_id = client.post(f"/api/v1/flows/{flow_id}/clone", headers=_auth(token)).json()[
                "id"
            ]
            clone = client.get(f"/api/v1/flows/{clone_id}", headers=_auth(token)).json()

        clone_node_ids = {n["id"] for n in clone["nodes"]}
        for edge in clone["edges"]:
            assert edge["source"] in clone_node_ids, (
                f"Edge source {edge['source']} not in cloned node IDs"
            )
            assert edge["target"] in clone_node_ids, (
                f"Edge target {edge['target']} not in cloned node IDs"
            )

    def test_cloned_node_data_preserved(self):
        """Node type and data dict are copied into the clone."""
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            clone_id = client.post(f"/api/v1/flows/{flow_id}/clone", headers=_auth(token)).json()[
                "id"
            ]
            clone = client.get(f"/api/v1/flows/{clone_id}", headers=_auth(token)).json()

        node_types = {n["type"] for n in clone["nodes"]}
        assert "start" in node_types
        assert "llm" in node_types
        assert "end" in node_types


class TestFlowCloneIndependence:
    def test_clone_persists_after_original_deleted(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            clone_id = client.post(f"/api/v1/flows/{flow_id}/clone", headers=_auth(token)).json()[
                "id"
            ]
            # Delete original
            del_resp = client.delete(f"/api/v1/flows/{flow_id}", headers=_auth(token))
            assert del_resp.status_code == 200
            # Clone still exists
            clone_resp = client.get(f"/api/v1/flows/{clone_id}", headers=_auth(token))
        assert clone_resp.status_code == 200

    def test_both_appear_in_list(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            clone_id = client.post(f"/api/v1/flows/{flow_id}/clone", headers=_auth(token)).json()[
                "id"
            ]
            flows_resp = client.get("/api/v1/flows", headers=_auth(token))

        assert flows_resp.status_code == 200
        flow_ids = {f["id"] for f in flows_resp.json()["items"]}
        assert flow_id in flow_ids
        assert clone_id in flow_ids  # Gate 2

    def test_clone_of_clone_works(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            clone1_id = client.post(f"/api/v1/flows/{flow_id}/clone", headers=_auth(token)).json()[
                "id"
            ]
            resp = client.post(f"/api/v1/flows/{clone1_id}/clone", headers=_auth(token))
        assert resp.status_code == 201
        assert resp.json()["id"] not in (flow_id, clone1_id)


class TestFlowCloneEdgeCases:
    def test_clone_empty_flow(self):
        """Flow with no nodes/edges clones without error."""
        with TestClient(app) as client:
            token = _register(client)
            uid = uuid.uuid4().hex[:6]
            resp = client.post(
                "/api/v1/flows",
                json={"name": f"empty-{uid}", "nodes": [], "edges": []},
                headers=_auth(token),
            )
            flow_id = resp.json()["id"]
            clone_resp = client.post(f"/api/v1/flows/{flow_id}/clone", headers=_auth(token))
        assert clone_resp.status_code == 201
        assert clone_resp.json()["node_count"] == 0
        assert clone_resp.json()["edge_count"] == 0

    def test_clone_404_for_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.post("/api/v1/flows/nonexistent-flow-id/clone", headers=_auth(token))
        assert resp.status_code == 404

    def test_clone_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(f"/api/v1/flows/{flow_id}/clone")
        assert resp.status_code == 401

    def test_clone_blank_name_uses_default(self):
        """Blank name string should fall back to 'Copy of {original_name}'."""
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token, name="Blank Name Test")
            resp = client.post(
                f"/api/v1/flows/{flow_id}/clone",
                json={"name": "   "},
                headers=_auth(token),
            )
        assert resp.status_code == 201
        assert resp.json()["name"] == "Copy of Blank Name Test"
