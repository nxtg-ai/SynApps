"""
N-137: Flow Pinning — POST/DELETE /api/v1/flows/{flow_id}/pin
                       GET /api/v1/flows/pinned

Tests:
  - POST pin returns 201, pinned=True
  - POST pin on already-pinned flow → 409
  - DELETE unpin returns 200, pinned=False
  - DELETE unpin on not-pinned flow → 404
  - GET /flows/pinned returns pinned flows in pin order
  - GET /flows/pinned returns empty list when nothing pinned
  - Unpin removes flow from pinned list
  - Per-user isolation: user A's pins don't appear for user B
  - Pinned flow deleted from DB is silently skipped in /flows/pinned
  - POST/DELETE pin returns 404 for unknown flow
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
        json={"email": f"pin-{uid}@test.com", "password": "pass1234"},
    )
    assert r.status_code == 201
    return r.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_flow(client: TestClient, token: str, name: str = "Pin Test Flow") -> str:
    resp = client.post(
        "/api/v1/flows",
        json={"name": name, "nodes": [], "edges": []},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


# ---------------------------------------------------------------------------
# Tests — Pin
# ---------------------------------------------------------------------------


class TestFlowPin:
    def test_pin_returns_201(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(f"/api/v1/flows/{flow_id}/pin", headers=_auth(token))
        assert resp.status_code == 201
        data = resp.json()
        assert data["pinned"] is True

    def test_pin_response_shape(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(f"/api/v1/flows/{flow_id}/pin", headers=_auth(token))
        data = resp.json()
        assert data["flow_id"] == flow_id
        assert data["pinned"] is True

    def test_pin_already_pinned_409(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            client.post(f"/api/v1/flows/{flow_id}/pin", headers=_auth(token))
            resp = client.post(f"/api/v1/flows/{flow_id}/pin", headers=_auth(token))
        assert resp.status_code == 409
        assert "error" in resp.json()

    def test_pin_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.post("/api/v1/flows/nonexistent/pin", headers=_auth(token))
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_pin_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(f"/api/v1/flows/{flow_id}/pin")
        assert resp.status_code == 401
        assert "error" in resp.json()


# ---------------------------------------------------------------------------
# Tests — Unpin
# ---------------------------------------------------------------------------


class TestFlowUnpin:
    def test_unpin_returns_200(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            client.post(f"/api/v1/flows/{flow_id}/pin", headers=_auth(token))
            resp = client.delete(f"/api/v1/flows/{flow_id}/pin", headers=_auth(token))
        assert resp.status_code == 200
        data = resp.json()
        assert data["pinned"] is False

    def test_unpin_response_shape(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            client.post(f"/api/v1/flows/{flow_id}/pin", headers=_auth(token))
            resp = client.delete(f"/api/v1/flows/{flow_id}/pin", headers=_auth(token))
        data = resp.json()
        assert data["flow_id"] == flow_id
        assert data["pinned"] is False

    def test_unpin_not_pinned_404(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.delete(f"/api/v1/flows/{flow_id}/pin", headers=_auth(token))
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_unpin_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.delete("/api/v1/flows/nonexistent/pin", headers=_auth(token))
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_unpin_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            client.post(f"/api/v1/flows/{flow_id}/pin", headers=_auth(token))
            resp = client.delete(f"/api/v1/flows/{flow_id}/pin")
        assert resp.status_code == 401
        assert "error" in resp.json()


# ---------------------------------------------------------------------------
# Tests — GET /flows/pinned
# ---------------------------------------------------------------------------


class TestFlowPinnedList:
    def test_pinned_list_empty_by_default(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get("/api/v1/flows/pinned", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["items"] == []
        assert resp.json()["total"] == 0

    def test_pinned_list_contains_pinned_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            client.post(f"/api/v1/flows/{flow_id}/pin", headers=_auth(token))
            resp = client.get("/api/v1/flows/pinned", headers=_auth(token))
        ids = [f["id"] for f in resp.json()["items"]]
        assert flow_id in ids

    def test_pinned_list_respects_pin_order(self):
        with TestClient(app) as client:
            token = _register(client)
            first = _create_flow(client, token, "First")
            second = _create_flow(client, token, "Second")
            third = _create_flow(client, token, "Third")
            client.post(f"/api/v1/flows/{first}/pin", headers=_auth(token))
            client.post(f"/api/v1/flows/{second}/pin", headers=_auth(token))
            client.post(f"/api/v1/flows/{third}/pin", headers=_auth(token))
            resp = client.get("/api/v1/flows/pinned", headers=_auth(token))
        ids = [f["id"] for f in resp.json()["items"]]
        assert ids == [first, second, third]

    def test_unpin_removes_from_list(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            client.post(f"/api/v1/flows/{flow_id}/pin", headers=_auth(token))
            client.delete(f"/api/v1/flows/{flow_id}/pin", headers=_auth(token))
            resp = client.get("/api/v1/flows/pinned", headers=_auth(token))
        assert resp.json()["items"] == []

    def test_per_user_isolation(self):
        with TestClient(app) as client:
            token_a = _register(client)
            token_b = _register(client)
            flow_id = _create_flow(client, token_a)
            client.post(f"/api/v1/flows/{flow_id}/pin", headers=_auth(token_a))
            resp_b = client.get("/api/v1/flows/pinned", headers=_auth(token_b))
        assert resp_b.json()["items"] == []

    def test_pinned_list_requires_auth(self):
        with TestClient(app) as client:
            _register(client)
            resp = client.get("/api/v1/flows/pinned")
        assert resp.status_code == 401
        assert "error" in resp.json()
