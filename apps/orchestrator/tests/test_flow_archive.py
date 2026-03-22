"""
N-135: Flow Archiving — POST/DELETE /api/v1/flows/{flow_id}/archive
                         GET /api/v1/flows?archived=true

Tests:
  - Archive a flow → 200, archived=True, archived_at present
  - Archiving an already-archived flow → 409
  - Restore an archived flow → 200, archived=False
  - Restoring a non-archived flow → 409
  - GET /flows excludes archived flows by default
  - GET /flows?archived=true returns only archived flows
  - GET /flows?archived=false returns only non-archived flows (explicit)
  - Archived flow can still be fetched by ID
  - 404 on unknown flow for archive and restore
  - Auth required on archive, restore
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
        json={"email": f"arch-{uid}@test.com", "password": "pass1234"},
    )
    assert r.status_code == 201
    return r.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_flow(client: TestClient, token: str, name: str = "Archive Test Flow") -> str:
    resp = client.post(
        "/api/v1/flows",
        json={"name": name, "nodes": [], "edges": []},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


# ---------------------------------------------------------------------------
# Tests — Archive
# ---------------------------------------------------------------------------


class TestFlowArchive:
    def test_archive_returns_200(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(f"/api/v1/flows/{flow_id}/archive", headers=_auth(token))
        assert resp.status_code == 200
        data = resp.json()
        assert data["archived"] is True

    def test_archive_response_shape(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(f"/api/v1/flows/{flow_id}/archive", headers=_auth(token))
        data = resp.json()
        assert data["flow_id"] == flow_id
        assert data["archived"] is True
        assert "archived_at" in data

    def test_archive_idempotency_409(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            client.post(f"/api/v1/flows/{flow_id}/archive", headers=_auth(token))
            resp = client.post(f"/api/v1/flows/{flow_id}/archive", headers=_auth(token))
        assert resp.status_code == 409
        assert "error" in resp.json()

    def test_archive_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.post("/api/v1/flows/nonexistent/archive", headers=_auth(token))
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_archive_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(f"/api/v1/flows/{flow_id}/archive")
        assert resp.status_code == 401
        assert "error" in resp.json()


# ---------------------------------------------------------------------------
# Tests — Restore
# ---------------------------------------------------------------------------


class TestFlowRestore:
    def test_restore_returns_200(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            client.post(f"/api/v1/flows/{flow_id}/archive", headers=_auth(token))
            resp = client.delete(f"/api/v1/flows/{flow_id}/archive", headers=_auth(token))
        assert resp.status_code == 200
        data = resp.json()
        assert data["archived"] is False

    def test_restore_response_shape(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            client.post(f"/api/v1/flows/{flow_id}/archive", headers=_auth(token))
            resp = client.delete(f"/api/v1/flows/{flow_id}/archive", headers=_auth(token))
        data = resp.json()
        assert data["flow_id"] == flow_id
        assert data["archived"] is False

    def test_restore_non_archived_409(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.delete(f"/api/v1/flows/{flow_id}/archive", headers=_auth(token))
        assert resp.status_code == 409
        assert "error" in resp.json()

    def test_restore_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.delete("/api/v1/flows/nonexistent/archive", headers=_auth(token))
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_restore_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            client.post(f"/api/v1/flows/{flow_id}/archive", headers=_auth(token))
            resp = client.delete(f"/api/v1/flows/{flow_id}/archive")
        assert resp.status_code == 401
        assert "error" in resp.json()


# ---------------------------------------------------------------------------
# Tests — GET /flows filter integration
# ---------------------------------------------------------------------------


class TestFlowArchiveListFilter:
    def test_default_listing_excludes_archived(self):
        with TestClient(app) as client:
            token = _register(client)
            active_id = _create_flow(client, token, "Active Flow")
            archived_id = _create_flow(client, token, "Archived Flow")
            client.post(f"/api/v1/flows/{archived_id}/archive", headers=_auth(token))
            resp = client.get("/api/v1/flows", headers=_auth(token))
        data = resp.json()
        ids = [f["id"] for f in data["items"]]
        assert active_id in ids
        assert archived_id not in ids

    def test_archived_filter_returns_archived(self):
        with TestClient(app) as client:
            token = _register(client)
            active_id = _create_flow(client, token, "Active Flow")
            archived_id = _create_flow(client, token, "Archived Flow")
            client.post(f"/api/v1/flows/{archived_id}/archive", headers=_auth(token))
            resp = client.get("/api/v1/flows?archived=true", headers=_auth(token))
        data = resp.json()
        ids = [f["id"] for f in data["items"]]
        assert archived_id in ids
        assert active_id not in ids

    def test_explicit_false_returns_only_active(self):
        with TestClient(app) as client:
            token = _register(client)
            active_id = _create_flow(client, token, "Active Flow")
            archived_id = _create_flow(client, token, "Archived Flow")
            client.post(f"/api/v1/flows/{archived_id}/archive", headers=_auth(token))
            resp = client.get("/api/v1/flows?archived=false", headers=_auth(token))
        data = resp.json()
        ids = [f["id"] for f in data["items"]]
        assert active_id in ids
        assert archived_id not in ids

    def test_restore_makes_flow_visible_again(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token, "Round-trip Flow")
            client.post(f"/api/v1/flows/{flow_id}/archive", headers=_auth(token))
            client.delete(f"/api/v1/flows/{flow_id}/archive", headers=_auth(token))
            resp = client.get("/api/v1/flows", headers=_auth(token))
        ids = [f["id"] for f in resp.json()["items"]]
        assert flow_id in ids

    def test_archived_flow_still_fetchable_by_id(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            client.post(f"/api/v1/flows/{flow_id}/archive", headers=_auth(token))
            resp = client.get(f"/api/v1/flows/{flow_id}", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["id"] == flow_id
