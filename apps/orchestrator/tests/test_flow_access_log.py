"""
N-142: Flow Access Log — GET /api/v1/flows/{flow_id}/access-log

Tests:
  - Returns 200 with entries list and total
  - Empty log on a freshly created flow
  - Reading a flow via GET /flows/{id} appends an entry
  - Multiple reads accumulate entries (newest-first ordering)
  - Correct accessor email is recorded
  - limit/offset pagination works
  - 404 for unknown flow
  - Auth required
"""

import uuid

from fastapi.testclient import TestClient

from apps.orchestrator.main import app

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _register(client: TestClient) -> tuple[str, str]:
    """Register a user; return (token, email)."""
    uid = uuid.uuid4().hex[:8]
    email = f"al-{uid}@test.com"
    r = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "pass1234"},
    )
    assert r.status_code == 201
    return r.json()["access_token"], email


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_flow(client: TestClient, token: str) -> str:
    resp = client.post(
        "/api/v1/flows",
        json={"name": "Access Log Test Flow", "nodes": [], "edges": []},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _read_flow(client: TestClient, token: str, flow_id: str) -> None:
    resp = client.get(f"/api/v1/flows/{flow_id}", headers=_auth(token))
    assert resp.status_code == 200


def _get_log(client: TestClient, token: str, flow_id: str, **params) -> dict:
    resp = client.get(
        f"/api/v1/flows/{flow_id}/access-log",
        params=params,
        headers=_auth(token),
    )
    return resp


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestFlowAccessLog:
    def test_returns_200(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            flow_id = _create_flow(client, token)
            resp = _get_log(client, token, flow_id)
        assert resp.status_code == 200

    def test_response_shape(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            flow_id = _create_flow(client, token)
            resp = _get_log(client, token, flow_id)
        data = resp.json()
        assert "flow_id" in data
        assert "entries" in data
        assert "total" in data
        assert data["flow_id"] == flow_id

    def test_empty_on_fresh_flow(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            flow_id = _create_flow(client, token)
            resp = _get_log(client, token, flow_id)
        data = resp.json()
        assert data["entries"] == []
        assert data["total"] == 0

    def test_read_appends_entry(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            flow_id = _create_flow(client, token)
            _read_flow(client, token, flow_id)
            resp = _get_log(client, token, flow_id)
        data = resp.json()
        assert data["total"] >= 1
        assert len(data["entries"]) >= 1

    def test_entries_have_expected_fields(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            flow_id = _create_flow(client, token)
            _read_flow(client, token, flow_id)
            resp = _get_log(client, token, flow_id)
        entry = resp.json()["entries"][0]
        assert "accessor" in entry
        assert "accessed_at" in entry

    def test_accessor_is_user_email(self):
        with TestClient(app) as client:
            token, email = _register(client)
            flow_id = _create_flow(client, token)
            _read_flow(client, token, flow_id)
            resp = _get_log(client, token, flow_id)
        assert resp.json()["entries"][0]["accessor"] == email

    def test_multiple_reads_accumulate(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            flow_id = _create_flow(client, token)
            _read_flow(client, token, flow_id)
            _read_flow(client, token, flow_id)
            _read_flow(client, token, flow_id)
            resp = _get_log(client, token, flow_id)
        data = resp.json()
        assert data["total"] == 3
        assert len(data["entries"]) == 3

    def test_entries_newest_first(self):
        """Entries should be returned newest-first (most recent access at index 0)."""
        with TestClient(app) as client:
            token, _ = _register(client)
            flow_id = _create_flow(client, token)
            _read_flow(client, token, flow_id)
            _read_flow(client, token, flow_id)
            resp = _get_log(client, token, flow_id)
        entries = resp.json()["entries"]
        # accessed_at is ISO-format; lexicographic comparison is valid for ISO timestamps
        assert entries[0]["accessed_at"] >= entries[1]["accessed_at"]

    def test_limit_pagination(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            flow_id = _create_flow(client, token)
            for _ in range(5):
                _read_flow(client, token, flow_id)
            resp = _get_log(client, token, flow_id, limit=2)
        data = resp.json()
        assert len(data["entries"]) == 2
        assert data["total"] == 5

    def test_offset_pagination(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            flow_id = _create_flow(client, token)
            for _ in range(4):
                _read_flow(client, token, flow_id)
            all_resp = _get_log(client, token, flow_id, limit=4)
            offset_resp = _get_log(client, token, flow_id, limit=4, offset=2)
        all_entries = all_resp.json()["entries"]
        offset_entries = offset_resp.json()["entries"]
        assert len(offset_entries) == 2
        assert offset_entries[0]["accessed_at"] == all_entries[2]["accessed_at"]

    def test_404_unknown_flow(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            resp = client.get(
                "/api/v1/flows/nonexistent/access-log",
                headers=_auth(token),
            )
        assert resp.status_code == 404

    def test_requires_auth(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/access-log")
        assert resp.status_code == 401
