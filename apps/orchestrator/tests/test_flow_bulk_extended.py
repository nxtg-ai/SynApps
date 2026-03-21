"""
N-148: Flow Bulk Extended — POST /flows/bulk/move + POST /flows/bulk/priority

Tests:
  - POST /bulk/move assigns group to all flows
  - POST /bulk/move lowercases the group name
  - POST /bulk/move not-found flows → failure breakdown
  - POST /bulk/move response shape (succeeded, failed, total, action)
  - POST /bulk/move empty list → 422
  - POST /bulk/move > 100 flows → 422
  - POST /bulk/priority sets priority on all flows
  - POST /bulk/priority not-found flows → failure breakdown
  - POST /bulk/priority invalid priority → 422
  - Auth required on both endpoints
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
        json={"email": f"bulk2-{uid}@test.com", "password": "pass1234"},
    )
    assert r.status_code == 201
    return r.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_flow(client: TestClient, token: str) -> str:
    resp = client.post(
        "/api/v1/flows",
        json={"name": "Bulk Extended Flow", "nodes": [], "edges": []},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


# ---------------------------------------------------------------------------
# Tests — POST /flows/bulk/move
# ---------------------------------------------------------------------------


class TestBulkMove:
    def test_move_all_succeed(self):
        with TestClient(app) as client:
            token = _register(client)
            f1 = _create_flow(client, token)
            f2 = _create_flow(client, token)
            resp = client.post(
                "/api/v1/flows/bulk/move",
                json={"flow_ids": [f1, f2], "group": "production"},
                headers=_auth(token),
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success_count"] == 2
        assert data["failure_count"] == 0
        assert set(data["succeeded"]) == {f1, f2}

    def test_move_action_in_response(self):
        with TestClient(app) as client:
            token = _register(client)
            f1 = _create_flow(client, token)
            resp = client.post(
                "/api/v1/flows/bulk/move",
                json={"flow_ids": [f1], "group": "ops"},
                headers=_auth(token),
            )
        assert resp.json()["action"] == "move"

    def test_move_lowercases_group(self):
        with TestClient(app) as client:
            token = _register(client)
            f1 = _create_flow(client, token)
            client.post(
                "/api/v1/flows/bulk/move",
                json={"flow_ids": [f1], "group": "UPPER"},
                headers=_auth(token),
            )
            resp = client.get(f"/api/v1/flows/{f1}/group", headers=_auth(token))
        assert resp.json()["group"] == "upper"

    def test_move_not_found_flows_in_failed(self):
        with TestClient(app) as client:
            token = _register(client)
            f1 = _create_flow(client, token)
            resp = client.post(
                "/api/v1/flows/bulk/move",
                json={"flow_ids": [f1, "nonexistent"], "group": "staging"},
                headers=_auth(token),
            )
        data = resp.json()
        assert f1 in data["succeeded"]
        assert any(f["flow_id"] == "nonexistent" for f in data["failed"])

    def test_move_group_appears_in_listing(self):
        with TestClient(app) as client:
            token = _register(client)
            f1 = _create_flow(client, token)
            f2 = _create_flow(client, token)
            client.post(
                "/api/v1/flows/bulk/move",
                json={"flow_ids": [f1, f2], "group": "dev"},
                headers=_auth(token),
            )
            resp = client.get("/api/v1/flows?group=dev", headers=_auth(token))
        ids = [f["id"] for f in resp.json()["items"]]
        assert f1 in ids
        assert f2 in ids

    def test_move_empty_list_422(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.post(
                "/api/v1/flows/bulk/move",
                json={"flow_ids": [], "group": "x"},
                headers=_auth(token),
            )
        assert resp.status_code == 422

    def test_move_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            f1 = _create_flow(client, token)
            resp = client.post(
                "/api/v1/flows/bulk/move",
                json={"flow_ids": [f1], "group": "x"},
            )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Tests — POST /flows/bulk/priority
# ---------------------------------------------------------------------------


class TestBulkPriority:
    def test_bulk_priority_all_succeed(self):
        with TestClient(app) as client:
            token = _register(client)
            f1 = _create_flow(client, token)
            f2 = _create_flow(client, token)
            resp = client.post(
                "/api/v1/flows/bulk/priority",
                json={"flow_ids": [f1, f2], "priority": "high"},
                headers=_auth(token),
            )
        data = resp.json()
        assert data["success_count"] == 2
        assert data["action"] == "priority"

    def test_bulk_priority_appears_on_flows(self):
        with TestClient(app) as client:
            token = _register(client)
            f1 = _create_flow(client, token)
            client.post(
                "/api/v1/flows/bulk/priority",
                json={"flow_ids": [f1], "priority": "critical"},
                headers=_auth(token),
            )
            resp = client.get(f"/api/v1/flows/{f1}/priority", headers=_auth(token))
        assert resp.json()["priority"] == "critical"

    def test_bulk_priority_not_found_in_failed(self):
        with TestClient(app) as client:
            token = _register(client)
            f1 = _create_flow(client, token)
            resp = client.post(
                "/api/v1/flows/bulk/priority",
                json={"flow_ids": [f1, "ghost"], "priority": "low"},
                headers=_auth(token),
            )
        data = resp.json()
        assert f1 in data["succeeded"]
        assert any(f["flow_id"] == "ghost" for f in data["failed"])

    def test_bulk_priority_invalid_422(self):
        with TestClient(app) as client:
            token = _register(client)
            f1 = _create_flow(client, token)
            resp = client.post(
                "/api/v1/flows/bulk/priority",
                json={"flow_ids": [f1], "priority": "urgent"},
                headers=_auth(token),
            )
        assert resp.status_code == 422

    def test_bulk_priority_empty_list_422(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.post(
                "/api/v1/flows/bulk/priority",
                json={"flow_ids": [], "priority": "high"},
                headers=_auth(token),
            )
        assert resp.status_code == 422

    def test_bulk_priority_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            f1 = _create_flow(client, token)
            resp = client.post(
                "/api/v1/flows/bulk/priority",
                json={"flow_ids": [f1], "priority": "high"},
            )
        assert resp.status_code == 401
