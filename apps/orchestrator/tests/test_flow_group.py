"""
N-140: Flow Groups — GET/PUT/DELETE /api/v1/flows/{flow_id}/group
                     GET /api/v1/flows/groups
                     GET /api/v1/flows?group=<name>

Tests:
  - GET /flows/{id}/group returns null by default
  - PUT assigns flow to group; name is lowercased
  - GET after PUT returns group name
  - PUT replaces existing group assignment
  - DELETE removes group; returns null
  - DELETE on ungrouped flow → 404
  - GET /flows/groups lists all groups with flow counts
  - GET /flows?group=name filters by group
  - GET /flows?group=name — group filter is case-insensitive
  - GET/PUT/DELETE return 404 for unknown flow
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
        json={"email": f"grp-{uid}@test.com", "password": "pass1234"},
    )
    assert r.status_code == 201
    return r.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_flow(client: TestClient, token: str, name: str = "Group Test Flow") -> str:
    resp = client.post(
        "/api/v1/flows",
        json={"name": name, "nodes": [], "edges": []},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


# ---------------------------------------------------------------------------
# Tests — GET/PUT/DELETE /flows/{id}/group
# ---------------------------------------------------------------------------


class TestFlowGroupCrud:
    def test_get_returns_null_by_default(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/group", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["group"] is None

    def test_put_assigns_group(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/group",
                json={"group": "Production"},
                headers=_auth(token),
            )
        assert resp.status_code == 200
        assert resp.json()["group"] == "production"

    def test_put_lowercases_group_name(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            client.put(
                f"/api/v1/flows/{flow_id}/group",
                json={"group": "UPPER CASE"},
                headers=_auth(token),
            )
            resp = client.get(f"/api/v1/flows/{flow_id}/group", headers=_auth(token))
        assert resp.json()["group"] == "upper case"

    def test_get_after_put_returns_group(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            client.put(
                f"/api/v1/flows/{flow_id}/group",
                json={"group": "dev"},
                headers=_auth(token),
            )
            resp = client.get(f"/api/v1/flows/{flow_id}/group", headers=_auth(token))
        assert resp.json()["group"] == "dev"

    def test_put_replaces_existing_group(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            client.put(
                f"/api/v1/flows/{flow_id}/group",
                json={"group": "old"},
                headers=_auth(token),
            )
            client.put(
                f"/api/v1/flows/{flow_id}/group",
                json={"group": "new"},
                headers=_auth(token),
            )
            resp = client.get(f"/api/v1/flows/{flow_id}/group", headers=_auth(token))
        assert resp.json()["group"] == "new"

    def test_delete_removes_group(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            client.put(
                f"/api/v1/flows/{flow_id}/group",
                json={"group": "temp"},
                headers=_auth(token),
            )
            resp = client.delete(f"/api/v1/flows/{flow_id}/group", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["group"] is None

    def test_delete_clears_assignment(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            client.put(
                f"/api/v1/flows/{flow_id}/group",
                json={"group": "temp"},
                headers=_auth(token),
            )
            client.delete(f"/api/v1/flows/{flow_id}/group", headers=_auth(token))
            resp = client.get(f"/api/v1/flows/{flow_id}/group", headers=_auth(token))
        assert resp.json()["group"] is None

    def test_delete_ungrouped_404(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.delete(f"/api/v1/flows/{flow_id}/group", headers=_auth(token))
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_get_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get("/api/v1/flows/nonexistent/group", headers=_auth(token))
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_put_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.put(
                "/api/v1/flows/nonexistent/group",
                json={"group": "x"},
                headers=_auth(token),
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_put_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(f"/api/v1/flows/{flow_id}/group", json={"group": "x"})
        assert resp.status_code == 401
        assert "error" in resp.json()


# ---------------------------------------------------------------------------
# Tests — GET /flows/groups
# ---------------------------------------------------------------------------


class TestListGroups:
    def test_list_groups_empty(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get("/api/v1/flows/groups", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["groups"] == []
        assert resp.json()["total"] == 0

    def test_list_groups_shows_all(self):
        with TestClient(app) as client:
            token = _register(client)
            f1 = _create_flow(client, token, "F1")
            f2 = _create_flow(client, token, "F2")
            f3 = _create_flow(client, token, "F3")
            client.put(f"/api/v1/flows/{f1}/group", json={"group": "alpha"}, headers=_auth(token))
            client.put(f"/api/v1/flows/{f2}/group", json={"group": "alpha"}, headers=_auth(token))
            client.put(f"/api/v1/flows/{f3}/group", json={"group": "beta"}, headers=_auth(token))
            resp = client.get("/api/v1/flows/groups", headers=_auth(token))
        data = resp.json()
        assert data["total"] == 2
        names = {g["name"]: g["flow_count"] for g in data["groups"]}
        assert names["alpha"] == 2
        assert names["beta"] == 1

    def test_list_groups_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            _create_flow(client, token)
            resp = client.get("/api/v1/flows/groups")
        assert resp.status_code == 401
        assert "error" in resp.json()


# ---------------------------------------------------------------------------
# Tests — GET /flows?group=
# ---------------------------------------------------------------------------


class TestFlowGroupFilter:
    def test_group_filter_returns_matching_flows(self):
        with TestClient(app) as client:
            token = _register(client)
            f1 = _create_flow(client, token, "In Group")
            f2 = _create_flow(client, token, "Not In Group")
            client.put(f"/api/v1/flows/{f1}/group", json={"group": "ops"}, headers=_auth(token))
            resp = client.get("/api/v1/flows?group=ops", headers=_auth(token))
        ids = [f["id"] for f in resp.json()["items"]]
        assert f1 in ids
        assert f2 not in ids

    def test_group_filter_case_insensitive(self):
        with TestClient(app) as client:
            token = _register(client)
            f1 = _create_flow(client, token, "Flow A")
            client.put(f"/api/v1/flows/{f1}/group", json={"group": "ops"}, headers=_auth(token))
            resp = client.get("/api/v1/flows?group=OPS", headers=_auth(token))
        ids = [f["id"] for f in resp.json()["items"]]
        assert f1 in ids

    def test_group_filter_no_match_returns_empty(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get("/api/v1/flows?group=nonexistent", headers=_auth(token))
        assert resp.json()["items"] == []
