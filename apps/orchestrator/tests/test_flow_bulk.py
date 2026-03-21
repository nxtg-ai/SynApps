"""
N-136: Flow Bulk Operations — POST /api/v1/flows/bulk/{action}

Actions:
  - bulk/archive  — archive multiple flows
  - bulk/restore  — restore multiple archived flows
  - bulk/delete   — permanently delete multiple flows
  - bulk/tag      — add a tag to multiple flows

Tests:
  - All four actions return {action, succeeded, failed, total, success_count, failure_count}
  - Success path: all flows processed correctly
  - Partial failure: mix of valid and not_found IDs
  - Bulk archive: already_archived flows reported as failed
  - Bulk restore: not_archived flows reported as failed
  - Bulk delete: flows are actually gone (404 on subsequent GET)
  - Bulk tag: tags appear on GET /flows/{id}/tags
  - Empty flow_ids → 422 (min_length=1)
  - Too many flow_ids → 422 (max_length=100)
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
        json={"email": f"bulk-{uid}@test.com", "password": "pass1234"},
    )
    assert r.status_code == 201
    return r.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_flow(client: TestClient, token: str, name: str = "Bulk Test Flow") -> str:
    resp = client.post(
        "/api/v1/flows",
        json={"name": name, "nodes": [], "edges": []},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


# ---------------------------------------------------------------------------
# Bulk Archive
# ---------------------------------------------------------------------------


class TestBulkArchive:
    def test_archive_all_succeed(self):
        with TestClient(app) as client:
            token = _register(client)
            ids = [_create_flow(client, token, f"Flow {i}") for i in range(3)]
            resp = client.post(
                "/api/v1/flows/bulk/archive",
                json={"flow_ids": ids},
                headers=_auth(token),
            )
        data = resp.json()
        assert resp.status_code == 200
        assert data["action"] == "archive"
        assert data["success_count"] == 3
        assert data["failure_count"] == 0
        assert set(data["succeeded"]) == set(ids)

    def test_archive_partial_not_found(self):
        with TestClient(app) as client:
            token = _register(client)
            fid = _create_flow(client, token)
            resp = client.post(
                "/api/v1/flows/bulk/archive",
                json={"flow_ids": [fid, "ghost"]},
                headers=_auth(token),
            )
        data = resp.json()
        assert data["success_count"] == 1
        assert data["failure_count"] == 1
        assert data["failed"][0]["reason"] == "not_found"

    def test_archive_already_archived_fails(self):
        with TestClient(app) as client:
            token = _register(client)
            fid = _create_flow(client, token)
            client.post(f"/api/v1/flows/{fid}/archive", headers=_auth(token))
            resp = client.post(
                "/api/v1/flows/bulk/archive",
                json={"flow_ids": [fid]},
                headers=_auth(token),
            )
        data = resp.json()
        assert data["failure_count"] == 1
        assert data["failed"][0]["reason"] == "already_archived"

    def test_archive_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            fid = _create_flow(client, token)
            resp = client.post("/api/v1/flows/bulk/archive", json={"flow_ids": [fid]})
        assert resp.status_code == 401

    def test_archive_empty_ids_422(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.post(
                "/api/v1/flows/bulk/archive",
                json={"flow_ids": []},
                headers=_auth(token),
            )
        assert resp.status_code == 422

    def test_archive_too_many_ids_422(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.post(
                "/api/v1/flows/bulk/archive",
                json={"flow_ids": [str(i) for i in range(101)]},
                headers=_auth(token),
            )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Bulk Restore
# ---------------------------------------------------------------------------


class TestBulkRestore:
    def test_restore_all_succeed(self):
        with TestClient(app) as client:
            token = _register(client)
            ids = [_create_flow(client, token, f"Flow {i}") for i in range(3)]
            for fid in ids:
                client.post(f"/api/v1/flows/{fid}/archive", headers=_auth(token))
            resp = client.post(
                "/api/v1/flows/bulk/restore",
                json={"flow_ids": ids},
                headers=_auth(token),
            )
        data = resp.json()
        assert resp.status_code == 200
        assert data["action"] == "restore"
        assert data["success_count"] == 3
        assert data["failure_count"] == 0

    def test_restore_not_archived_fails(self):
        with TestClient(app) as client:
            token = _register(client)
            fid = _create_flow(client, token)
            resp = client.post(
                "/api/v1/flows/bulk/restore",
                json={"flow_ids": [fid]},
                headers=_auth(token),
            )
        data = resp.json()
        assert data["failure_count"] == 1
        assert data["failed"][0]["reason"] == "not_archived"

    def test_restore_not_found_fails(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.post(
                "/api/v1/flows/bulk/restore",
                json={"flow_ids": ["ghost"]},
                headers=_auth(token),
            )
        assert resp.json()["failed"][0]["reason"] == "not_found"

    def test_restore_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            fid = _create_flow(client, token)
            resp = client.post("/api/v1/flows/bulk/restore", json={"flow_ids": [fid]})
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Bulk Delete
# ---------------------------------------------------------------------------


class TestBulkDelete:
    def test_delete_all_succeed(self):
        with TestClient(app) as client:
            token = _register(client)
            ids = [_create_flow(client, token, f"Del {i}") for i in range(3)]
            resp = client.post(
                "/api/v1/flows/bulk/delete",
                json={"flow_ids": ids},
                headers=_auth(token),
            )
        data = resp.json()
        assert resp.status_code == 200
        assert data["action"] == "delete"
        assert data["success_count"] == 3

    def test_delete_flows_are_gone(self):
        with TestClient(app) as client:
            token = _register(client)
            fid = _create_flow(client, token)
            client.post(
                "/api/v1/flows/bulk/delete",
                json={"flow_ids": [fid]},
                headers=_auth(token),
            )
            resp = client.get(f"/api/v1/flows/{fid}", headers=_auth(token))
        assert resp.status_code == 404

    def test_delete_not_found_fails(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.post(
                "/api/v1/flows/bulk/delete",
                json={"flow_ids": ["ghost"]},
                headers=_auth(token),
            )
        assert resp.json()["failed"][0]["reason"] == "not_found"

    def test_delete_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            fid = _create_flow(client, token)
            resp = client.post("/api/v1/flows/bulk/delete", json={"flow_ids": [fid]})
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Bulk Tag
# ---------------------------------------------------------------------------


class TestBulkTag:
    def test_tag_all_succeed(self):
        with TestClient(app) as client:
            token = _register(client)
            ids = [_create_flow(client, token, f"Tag {i}") for i in range(3)]
            resp = client.post(
                "/api/v1/flows/bulk/tag",
                json={"flow_ids": ids, "tag": "production"},
                headers=_auth(token),
            )
        data = resp.json()
        assert resp.status_code == 200
        assert data["action"] == "tag"
        assert data["success_count"] == 3

    def test_tag_appears_on_flows(self):
        with TestClient(app) as client:
            token = _register(client)
            ids = [_create_flow(client, token, f"Tagged {i}") for i in range(2)]
            client.post(
                "/api/v1/flows/bulk/tag",
                json={"flow_ids": ids, "tag": "checked"},
                headers=_auth(token),
            )
            for fid in ids:
                tags_resp = client.get(f"/api/v1/flows/{fid}/tags", headers=_auth(token))
                assert "checked" in tags_resp.json()["tags"]

    def test_tag_not_found_fails(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.post(
                "/api/v1/flows/bulk/tag",
                json={"flow_ids": ["ghost"], "tag": "x"},
                headers=_auth(token),
            )
        assert resp.json()["failed"][0]["reason"] == "not_found"

    def test_tag_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            fid = _create_flow(client, token)
            resp = client.post("/api/v1/flows/bulk/tag", json={"flow_ids": [fid], "tag": "x"})
        assert resp.status_code == 401
