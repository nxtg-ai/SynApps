"""
N-149: Flow Expiry — GET/PUT/DELETE /api/v1/flows/{flow_id}/expiry
                      GET /flows/{id} returns 410 when expired

Tests:
  - GET returns null expires_at and expired:False on fresh flow
  - PUT sets expiry; GET returns it
  - PUT with past datetime → 422
  - PUT with invalid datetime string → 422
  - DELETE removes expiry; returns null
  - DELETE when no expiry → 404
  - GET /flows/{id} returns 200 before expiry
  - GET /flows/{id} returns 410 after expiry (manual store patch)
  - 404 for unknown flow on GET/PUT/DELETE
  - Auth required on all endpoints
"""

import time
import uuid

from fastapi.testclient import TestClient

from apps.orchestrator.main import app
from apps.orchestrator.stores import flow_expiry_store

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FUTURE_ISO = "2099-12-31T23:59:59+00:00"


def _register(client: TestClient) -> str:
    uid = uuid.uuid4().hex[:8]
    r = client.post(
        "/api/v1/auth/register",
        json={"email": f"expiry-{uid}@test.com", "password": "pass1234"},
    )
    assert r.status_code == 201
    return r.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_flow(client: TestClient, token: str) -> str:
    resp = client.post(
        "/api/v1/flows",
        json={"name": "Expiry Test Flow", "nodes": [], "edges": []},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


# ---------------------------------------------------------------------------
# Tests — GET /flows/{id}/expiry
# ---------------------------------------------------------------------------


class TestFlowExpiryGet:
    def test_null_by_default(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/expiry", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["expires_at"] is None
        assert resp.json()["expired"] is False

    def test_flow_id_in_response(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/expiry", headers=_auth(token))
        assert resp.json()["flow_id"] == flow_id

    def test_get_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get("/api/v1/flows/nonexistent/expiry", headers=_auth(token))
        assert resp.status_code == 404

    def test_get_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/expiry")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Tests — PUT /flows/{id}/expiry
# ---------------------------------------------------------------------------


class TestFlowExpiryPut:
    def test_put_returns_200(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/expiry",
                json={"expires_at": FUTURE_ISO},
                headers=_auth(token),
            )
        assert resp.status_code == 200

    def test_put_stores_expiry(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            client.put(
                f"/api/v1/flows/{flow_id}/expiry",
                json={"expires_at": FUTURE_ISO},
                headers=_auth(token),
            )
            resp = client.get(f"/api/v1/flows/{flow_id}/expiry", headers=_auth(token))
        assert resp.json()["expires_at"] is not None

    def test_put_expired_false_for_future(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/expiry",
                json={"expires_at": FUTURE_ISO},
                headers=_auth(token),
            )
        assert resp.json()["expired"] is False

    def test_put_past_datetime_422(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/expiry",
                json={"expires_at": "2000-01-01T00:00:00+00:00"},
                headers=_auth(token),
            )
        assert resp.status_code == 422

    def test_put_invalid_datetime_422(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/expiry",
                json={"expires_at": "not-a-date"},
                headers=_auth(token),
            )
        assert resp.status_code == 422

    def test_put_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.put(
                "/api/v1/flows/nonexistent/expiry",
                json={"expires_at": FUTURE_ISO},
                headers=_auth(token),
            )
        assert resp.status_code == 404

    def test_put_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/expiry",
                json={"expires_at": FUTURE_ISO},
            )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Tests — DELETE /flows/{id}/expiry
# ---------------------------------------------------------------------------


class TestFlowExpiryDelete:
    def test_delete_removes_expiry(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            client.put(
                f"/api/v1/flows/{flow_id}/expiry",
                json={"expires_at": FUTURE_ISO},
                headers=_auth(token),
            )
            resp = client.delete(f"/api/v1/flows/{flow_id}/expiry", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["expires_at"] is None

    def test_get_after_delete_shows_null(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            client.put(
                f"/api/v1/flows/{flow_id}/expiry",
                json={"expires_at": FUTURE_ISO},
                headers=_auth(token),
            )
            client.delete(f"/api/v1/flows/{flow_id}/expiry", headers=_auth(token))
            resp = client.get(f"/api/v1/flows/{flow_id}/expiry", headers=_auth(token))
        assert resp.json()["expires_at"] is None

    def test_delete_no_expiry_404(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.delete(f"/api/v1/flows/{flow_id}/expiry", headers=_auth(token))
        assert resp.status_code == 404

    def test_delete_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.delete(
                "/api/v1/flows/nonexistent/expiry", headers=_auth(token)
            )
        assert resp.status_code == 404

    def test_delete_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            client.put(
                f"/api/v1/flows/{flow_id}/expiry",
                json={"expires_at": FUTURE_ISO},
                headers=_auth(token),
            )
            resp = client.delete(f"/api/v1/flows/{flow_id}/expiry")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Tests — GET /flows/{id} returns 410 when expired
# ---------------------------------------------------------------------------


class TestFlowExpiryEnforcement:
    def test_get_flow_ok_before_expiry(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            client.put(
                f"/api/v1/flows/{flow_id}/expiry",
                json={"expires_at": FUTURE_ISO},
                headers=_auth(token),
            )
            resp = client.get(f"/api/v1/flows/{flow_id}", headers=_auth(token))
        assert resp.status_code == 200

    def test_get_flow_410_when_expired(self):
        """Directly seed the store with a past timestamp to simulate expiry."""
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            # Set expiry to 1 second in the past
            flow_expiry_store.set(flow_id, time.time() - 1.0)
            resp = client.get(f"/api/v1/flows/{flow_id}", headers=_auth(token))
        assert resp.status_code == 410

    def test_get_flow_ok_after_expiry_cleared(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            flow_expiry_store.set(flow_id, time.time() - 1.0)
            client.delete(f"/api/v1/flows/{flow_id}/expiry", headers=_auth(token))
            resp = client.get(f"/api/v1/flows/{flow_id}", headers=_auth(token))
        assert resp.status_code == 200
