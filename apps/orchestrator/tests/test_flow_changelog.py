"""
N-152: Flow Changelog — POST/GET /api/v1/flows/{flow_id}/changelog
                         DELETE /api/v1/flows/{flow_id}/changelog/{entry_id}

Tests:
  - POST adds entry; returns 201
  - POST response includes id, flow_id, author, type, message, created_at
  - GET returns empty list on fresh flow
  - GET returns entries newest-first
  - GET total reflects actual count
  - GET limit/offset pagination
  - POST invalid type → 422
  - POST empty message → 422
  - DELETE removes entry; returns {deleted: true, entry_id}
  - DELETE 404 for unknown entry
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
        json={"email": f"clog-{uid}@test.com", "password": "pass1234"},
    )
    assert r.status_code == 201
    return r.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_flow(client: TestClient, token: str) -> str:
    resp = client.post(
        "/api/v1/flows",
        json={"name": "Changelog Test Flow", "nodes": [], "edges": []},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _add_entry(client: TestClient, token: str, flow_id: str, msg: str = "test note") -> dict:
    resp = client.post(
        f"/api/v1/flows/{flow_id}/changelog",
        json={"message": msg, "type": "note"},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    return resp.json()


# ---------------------------------------------------------------------------
# Tests — POST /flows/{id}/changelog
# ---------------------------------------------------------------------------


class TestFlowChangelogPost:
    def test_post_returns_201(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/changelog",
                json={"message": "Deployed to prod", "type": "deployment"},
                headers=_auth(token),
            )
        assert resp.status_code == 201
        data = resp.json()
        assert data["flow_id"] == flow_id

    def test_post_response_shape(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/changelog",
                json={"message": "Fixed bug in node X", "type": "fix"},
                headers=_auth(token),
            )
        data = resp.json()
        assert "id" in data
        assert data["flow_id"] == flow_id
        assert data["message"] == "Fixed bug in node X"
        assert data["type"] == "fix"
        assert "author" in data
        assert "created_at" in data

    def test_post_default_type_is_note(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/changelog",
                json={"message": "Just a note"},
                headers=_auth(token),
            )
        assert resp.json()["type"] == "note"

    def test_post_invalid_type_422(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/changelog",
                json={"message": "test", "type": "unknown"},
                headers=_auth(token),
            )
        assert resp.status_code == 422
        assert "error" in resp.json()

    def test_post_empty_message_422(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/changelog",
                json={"message": ""},
                headers=_auth(token),
            )
        assert resp.status_code == 422
        assert "error" in resp.json()

    def test_post_all_valid_types(self):
        for entry_type in ("note", "fix", "improvement", "breaking", "deployment"):
            with TestClient(app) as client:
                token = _register(client)
                flow_id = _create_flow(client, token)
                resp = client.post(
                    f"/api/v1/flows/{flow_id}/changelog",
                    json={"message": f"a {entry_type}", "type": entry_type},
                    headers=_auth(token),
                )
            assert resp.status_code == 201, f"type '{entry_type}' should be valid"
            data = resp.json()
            assert data["flow_id"] == flow_id

    def test_post_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.post(
                "/api/v1/flows/nonexistent/changelog",
                json={"message": "test"},
                headers=_auth(token),
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_post_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/changelog",
                json={"message": "no auth"},
            )
        assert resp.status_code == 401
        assert "error" in resp.json()


# ---------------------------------------------------------------------------
# Tests — GET /flows/{id}/changelog
# ---------------------------------------------------------------------------


class TestFlowChangelogGet:
    def test_get_empty_on_fresh_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/changelog", headers=_auth(token))
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0

    def test_get_newest_first(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _add_entry(client, token, flow_id, "first")
            _add_entry(client, token, flow_id, "second")
            resp = client.get(f"/api/v1/flows/{flow_id}/changelog", headers=_auth(token))
        items = resp.json()["items"]
        assert len(items) == 2
        assert items[0]["message"] == "second"
        assert items[1]["message"] == "first"

    def test_get_total_reflects_count(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _add_entry(client, token, flow_id)
            _add_entry(client, token, flow_id)
            _add_entry(client, token, flow_id)
            resp = client.get(f"/api/v1/flows/{flow_id}/changelog", headers=_auth(token))
        assert resp.json()["total"] == 3

    def test_get_limit_pagination(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            for i in range(5):
                _add_entry(client, token, flow_id, f"entry {i}")
            resp = client.get(
                f"/api/v1/flows/{flow_id}/changelog?limit=2", headers=_auth(token)
            )
        assert len(resp.json()["items"]) == 2

    def test_get_offset_pagination(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            for i in range(4):
                _add_entry(client, token, flow_id, f"entry {i}")
            resp = client.get(
                f"/api/v1/flows/{flow_id}/changelog?limit=2&offset=2", headers=_auth(token)
            )
        assert len(resp.json()["items"]) == 2

    def test_get_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get("/api/v1/flows/nonexistent/changelog", headers=_auth(token))
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_get_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/changelog")
        assert resp.status_code == 401
        assert "error" in resp.json()


# ---------------------------------------------------------------------------
# Tests — DELETE /flows/{id}/changelog/{entry_id}
# ---------------------------------------------------------------------------


class TestFlowChangelogDelete:
    def test_delete_removes_entry(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            entry = _add_entry(client, token, flow_id)
            resp = client.delete(
                f"/api/v1/flows/{flow_id}/changelog/{entry['id']}", headers=_auth(token)
            )
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True
        assert resp.json()["entry_id"] == entry["id"]

    def test_get_after_delete_shows_empty(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            entry = _add_entry(client, token, flow_id)
            client.delete(
                f"/api/v1/flows/{flow_id}/changelog/{entry['id']}", headers=_auth(token)
            )
            resp = client.get(f"/api/v1/flows/{flow_id}/changelog", headers=_auth(token))
        assert resp.json()["items"] == []

    def test_delete_404_unknown_entry(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.delete(
                f"/api/v1/flows/{flow_id}/changelog/nonexistent", headers=_auth(token)
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_delete_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.delete(
                "/api/v1/flows/nonexistent/changelog/any-id", headers=_auth(token)
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_delete_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            entry = _add_entry(client, token, flow_id)
            resp = client.delete(f"/api/v1/flows/{flow_id}/changelog/{entry['id']}")
        assert resp.status_code == 401
        assert "error" in resp.json()
