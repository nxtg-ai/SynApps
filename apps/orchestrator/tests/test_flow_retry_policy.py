"""
N-166: Flow Retry Policy — PUT/GET/DELETE /flows/{id}/retry-policy

Tests:
  - PUT creates retry policy; returns 200
  - PUT response shape (flow_id, max_retries, retry_delay_s, backoff_multiplier, updated_at)
  - PUT max_retries=0 (no retry) succeeds
  - PUT max_retries=10 (maximum) succeeds
  - PUT max_retries above max → 422
  - PUT retry_delay_s=0 succeeds
  - PUT retry_delay_s=300 (max) succeeds
  - PUT retry_delay_s above max → 422
  - PUT backoff_multiplier=1.0 (constant) succeeds
  - PUT backoff_multiplier below 1.0 → 422
  - PUT replaces existing policy
  - PUT 404 for unknown flow
  - PUT requires auth
  - GET returns policy after PUT
  - GET 404 when no policy set
  - GET 404 for unknown flow
  - GET requires auth
  - DELETE removes policy; returns {deleted: true, flow_id}
  - DELETE 404 when no policy set
  - DELETE requires auth
  - GET 404 after DELETE
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
        json={"email": f"retry-{uid}@test.com", "password": "pass1234"},
    )
    assert r.status_code == 201
    return r.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_flow(client: TestClient, token: str) -> str:
    resp = client.post(
        "/api/v1/flows",
        json={"name": "Retry Policy Test Flow", "nodes": [], "edges": []},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _set_policy(
    client: TestClient,
    token: str,
    flow_id: str,
    max_retries: int = 3,
    retry_delay_s: int = 5,
    backoff_multiplier: float = 2.0,
) -> dict:
    resp = client.put(
        f"/api/v1/flows/{flow_id}/retry-policy",
        json={
            "max_retries": max_retries,
            "retry_delay_s": retry_delay_s,
            "backoff_multiplier": backoff_multiplier,
        },
        headers=_auth(token),
    )
    assert resp.status_code == 200
    return resp.json()


# ---------------------------------------------------------------------------
# Tests — PUT /flows/{id}/retry-policy
# ---------------------------------------------------------------------------


class TestFlowRetryPolicyPut:
    def test_put_returns_200(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/retry-policy",
                json={"max_retries": 3, "retry_delay_s": 10, "backoff_multiplier": 2.0},
                headers=_auth(token),
            )
        assert resp.status_code == 200

    def test_put_response_shape(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/retry-policy",
                json={"max_retries": 5, "retry_delay_s": 30, "backoff_multiplier": 1.5},
                headers=_auth(token),
            )
        data = resp.json()
        assert data["flow_id"] == flow_id
        assert data["max_retries"] == 5
        assert data["retry_delay_s"] == 30
        assert data["backoff_multiplier"] == 1.5
        assert "updated_at" in data

    def test_put_max_retries_zero(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/retry-policy",
                json={"max_retries": 0, "retry_delay_s": 0, "backoff_multiplier": 1.0},
                headers=_auth(token),
            )
        assert resp.status_code == 200
        assert resp.json()["max_retries"] == 0

    def test_put_max_retries_maximum(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/retry-policy",
                json={"max_retries": 10, "retry_delay_s": 0, "backoff_multiplier": 1.0},
                headers=_auth(token),
            )
        assert resp.status_code == 200

    def test_put_max_retries_above_max_422(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/retry-policy",
                json={"max_retries": 11, "retry_delay_s": 0, "backoff_multiplier": 1.0},
                headers=_auth(token),
            )
        assert resp.status_code == 422

    def test_put_delay_zero(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/retry-policy",
                json={"max_retries": 1, "retry_delay_s": 0, "backoff_multiplier": 1.0},
                headers=_auth(token),
            )
        assert resp.status_code == 200

    def test_put_delay_maximum(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/retry-policy",
                json={"max_retries": 1, "retry_delay_s": 300, "backoff_multiplier": 1.0},
                headers=_auth(token),
            )
        assert resp.status_code == 200

    def test_put_delay_above_max_422(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/retry-policy",
                json={"max_retries": 1, "retry_delay_s": 301, "backoff_multiplier": 1.0},
                headers=_auth(token),
            )
        assert resp.status_code == 422

    def test_put_backoff_constant(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/retry-policy",
                json={"max_retries": 2, "retry_delay_s": 5, "backoff_multiplier": 1.0},
                headers=_auth(token),
            )
        assert resp.status_code == 200
        assert resp.json()["backoff_multiplier"] == 1.0

    def test_put_backoff_below_one_422(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/retry-policy",
                json={"max_retries": 1, "retry_delay_s": 1, "backoff_multiplier": 0.5},
                headers=_auth(token),
            )
        assert resp.status_code == 422

    def test_put_replaces_existing(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_policy(client, token, flow_id, max_retries=2)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/retry-policy",
                json={"max_retries": 7, "retry_delay_s": 60, "backoff_multiplier": 3.0},
                headers=_auth(token),
            )
        assert resp.json()["max_retries"] == 7

    def test_put_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.put(
                "/api/v1/flows/nonexistent/retry-policy",
                json={"max_retries": 3, "retry_delay_s": 5, "backoff_multiplier": 2.0},
                headers=_auth(token),
            )
        assert resp.status_code == 404

    def test_put_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/retry-policy",
                json={"max_retries": 1, "retry_delay_s": 0, "backoff_multiplier": 1.0},
            )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Tests — GET /flows/{id}/retry-policy
# ---------------------------------------------------------------------------


class TestFlowRetryPolicyGet:
    def test_get_returns_policy_after_put(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_policy(client, token, flow_id, max_retries=4, retry_delay_s=15)
            resp = client.get(f"/api/v1/flows/{flow_id}/retry-policy", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["max_retries"] == 4
        assert resp.json()["retry_delay_s"] == 15

    def test_get_404_when_no_policy(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/retry-policy", headers=_auth(token))
        assert resp.status_code == 404

    def test_get_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get("/api/v1/flows/nonexistent/retry-policy", headers=_auth(token))
        assert resp.status_code == 404

    def test_get_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_policy(client, token, flow_id)
            resp = client.get(f"/api/v1/flows/{flow_id}/retry-policy")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Tests — DELETE /flows/{id}/retry-policy
# ---------------------------------------------------------------------------


class TestFlowRetryPolicyDelete:
    def test_delete_removes_policy(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_policy(client, token, flow_id)
            resp = client.delete(f"/api/v1/flows/{flow_id}/retry-policy", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True
        assert resp.json()["flow_id"] == flow_id

    def test_get_404_after_delete(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_policy(client, token, flow_id)
            client.delete(f"/api/v1/flows/{flow_id}/retry-policy", headers=_auth(token))
            resp = client.get(f"/api/v1/flows/{flow_id}/retry-policy", headers=_auth(token))
        assert resp.status_code == 404

    def test_delete_404_when_no_policy(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.delete(f"/api/v1/flows/{flow_id}/retry-policy", headers=_auth(token))
        assert resp.status_code == 404

    def test_delete_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_policy(client, token, flow_id)
            resp = client.delete(f"/api/v1/flows/{flow_id}/retry-policy")
        assert resp.status_code == 401
