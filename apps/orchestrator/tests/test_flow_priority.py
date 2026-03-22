"""
N-147: Flow Priority — GET/PUT/DELETE /api/v1/flows/{flow_id}/priority

Tests:
  - GET returns null priority on fresh flow
  - PUT sets priority; GET returns it
  - PUT all valid values: critical, high, medium, low
  - PUT invalid value → 422
  - DELETE removes priority; returns null
  - DELETE when no priority set → 404
  - GET after DELETE shows null
  - GET /flows?priority= filters by priority
  - ?priority= filter is case-insensitive
  - ?priority= with no match returns empty
  - 404 for unknown flow on all endpoints
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
        json={"email": f"prio-{uid}@test.com", "password": "pass1234"},
    )
    assert r.status_code == 201
    return r.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_flow(client: TestClient, token: str, name: str = "Priority Flow") -> str:
    resp = client.post(
        "/api/v1/flows",
        json={"name": name, "nodes": [], "edges": []},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


# ---------------------------------------------------------------------------
# Tests — GET/PUT/DELETE /flows/{id}/priority
# ---------------------------------------------------------------------------


class TestFlowPriorityCrud:
    def test_get_null_by_default(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/priority", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["priority"] is None

    def test_put_sets_priority(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/priority",
                json={"priority": "high"},
                headers=_auth(token),
            )
        assert resp.status_code == 200
        assert resp.json()["priority"] == "high"

    def test_get_after_put_returns_priority(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            client.put(
                f"/api/v1/flows/{flow_id}/priority",
                json={"priority": "critical"},
                headers=_auth(token),
            )
            resp = client.get(f"/api/v1/flows/{flow_id}/priority", headers=_auth(token))
        assert resp.json()["priority"] == "critical"

    def test_put_all_valid_values(self):
        for level in ("critical", "high", "medium", "low"):
            with TestClient(app) as client:
                token = _register(client)
                flow_id = _create_flow(client, token)
                resp = client.put(
                    f"/api/v1/flows/{flow_id}/priority",
                    json={"priority": level},
                    headers=_auth(token),
                )
            assert resp.json()["priority"] == level

    def test_put_replaces_existing(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            client.put(
                f"/api/v1/flows/{flow_id}/priority",
                json={"priority": "low"},
                headers=_auth(token),
            )
            resp = client.put(
                f"/api/v1/flows/{flow_id}/priority",
                json={"priority": "critical"},
                headers=_auth(token),
            )
        assert resp.json()["priority"] == "critical"

    def test_put_invalid_value_422(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/priority",
                json={"priority": "urgent"},
                headers=_auth(token),
            )
        assert resp.status_code == 422
        assert "error" in resp.json()

    def test_delete_removes_priority(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            client.put(
                f"/api/v1/flows/{flow_id}/priority",
                json={"priority": "high"},
                headers=_auth(token),
            )
            resp = client.delete(f"/api/v1/flows/{flow_id}/priority", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["priority"] is None

    def test_get_after_delete_shows_null(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            client.put(
                f"/api/v1/flows/{flow_id}/priority",
                json={"priority": "medium"},
                headers=_auth(token),
            )
            client.delete(f"/api/v1/flows/{flow_id}/priority", headers=_auth(token))
            resp = client.get(f"/api/v1/flows/{flow_id}/priority", headers=_auth(token))
        assert resp.json()["priority"] is None

    def test_delete_no_priority_404(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.delete(f"/api/v1/flows/{flow_id}/priority", headers=_auth(token))
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_get_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get("/api/v1/flows/nonexistent/priority", headers=_auth(token))
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_put_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.put(
                "/api/v1/flows/nonexistent/priority",
                json={"priority": "high"},
                headers=_auth(token),
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_get_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/priority")
        assert resp.status_code == 401
        assert "error" in resp.json()

    def test_put_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(f"/api/v1/flows/{flow_id}/priority", json={"priority": "high"})
        assert resp.status_code == 401
        assert "error" in resp.json()


# ---------------------------------------------------------------------------
# Tests — GET /flows?priority= filter
# ---------------------------------------------------------------------------


class TestFlowPriorityFilter:
    def test_filter_returns_matching_flows(self):
        with TestClient(app) as client:
            token = _register(client)
            f1 = _create_flow(client, token, "High Flow")
            f2 = _create_flow(client, token, "Low Flow")
            client.put(
                f"/api/v1/flows/{f1}/priority",
                json={"priority": "high"},
                headers=_auth(token),
            )
            client.put(
                f"/api/v1/flows/{f2}/priority",
                json={"priority": "low"},
                headers=_auth(token),
            )
            resp = client.get("/api/v1/flows?priority=high", headers=_auth(token))
        ids = [f["id"] for f in resp.json()["items"]]
        assert f1 in ids
        assert f2 not in ids

    def test_filter_case_insensitive(self):
        with TestClient(app) as client:
            token = _register(client)
            f1 = _create_flow(client, token, "Critical Flow")
            client.put(
                f"/api/v1/flows/{f1}/priority",
                json={"priority": "critical"},
                headers=_auth(token),
            )
            resp = client.get("/api/v1/flows?priority=CRITICAL", headers=_auth(token))
        ids = [f["id"] for f in resp.json()["items"]]
        assert f1 in ids

    def test_filter_no_match_returns_empty(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get("/api/v1/flows?priority=critical", headers=_auth(token))
        assert resp.json()["items"] == []
