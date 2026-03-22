"""
N-179: Flow Resource Limits — PUT/GET/DELETE /flows/{id}/resource-limits

Tests:
  - PUT sets limits; returns 200
  - PUT response shape (flow_id, memory_mb, cpu_millicores, timeout_s, updated_at)
  - PUT with memory_mb only
  - PUT with cpu_millicores only
  - PUT with timeout_s only
  - PUT with all three limits
  - PUT all None values allowed
  - PUT memory_mb=0 → 422
  - PUT memory_mb=16385 → 422
  - PUT cpu_millicores=0 → 422
  - PUT timeout_s=0 → 422
  - PUT replaces existing limits
  - PUT 404 for unknown flow
  - PUT requires auth
  - GET returns limits after PUT
  - GET 404 when no limits set
  - GET 404 for unknown flow
  - GET requires auth
  - DELETE removes limits; returns {deleted: true, flow_id}
  - DELETE 404 when no limits
  - DELETE 404 unknown flow
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
        json={"email": f"reslim-{uid}@test.com", "password": "pass1234"},
    )
    assert r.status_code == 201
    return r.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_flow(client: TestClient, token: str) -> str:
    resp = client.post(
        "/api/v1/flows",
        json={"name": "Resource Limits Test Flow", "nodes": [], "edges": []},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _set_limits(
    client: TestClient,
    token: str,
    flow_id: str,
    memory_mb: int | None = 512,
    cpu_millicores: int | None = None,
    timeout_s: int | None = None,
) -> dict:
    payload: dict = {}
    if memory_mb is not None:
        payload["memory_mb"] = memory_mb
    if cpu_millicores is not None:
        payload["cpu_millicores"] = cpu_millicores
    if timeout_s is not None:
        payload["timeout_s"] = timeout_s
    resp = client.put(
        f"/api/v1/flows/{flow_id}/resource-limits",
        json=payload,
        headers=_auth(token),
    )
    assert resp.status_code == 200
    return resp.json()


# ---------------------------------------------------------------------------
# Tests — PUT /flows/{id}/resource-limits
# ---------------------------------------------------------------------------


class TestFlowResourceLimitsPut:
    def test_put_returns_200(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/resource-limits",
                json={"memory_mb": 256},
                headers=_auth(token),
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["flow_id"] == flow_id

    def test_put_response_shape(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/resource-limits",
                json={"memory_mb": 512},
                headers=_auth(token),
            )
        data = resp.json()
        assert data["flow_id"] == flow_id
        assert "memory_mb" in data
        assert "cpu_millicores" in data
        assert "timeout_s" in data
        assert "updated_at" in data

    def test_put_memory_mb_only(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/resource-limits",
                json={"memory_mb": 1024},
                headers=_auth(token),
            )
        assert resp.json()["memory_mb"] == 1024

    def test_put_cpu_millicores_only(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/resource-limits",
                json={"cpu_millicores": 500},
                headers=_auth(token),
            )
        assert resp.json()["cpu_millicores"] == 500

    def test_put_timeout_s_only(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/resource-limits",
                json={"timeout_s": 3600},
                headers=_auth(token),
            )
        assert resp.json()["timeout_s"] == 3600

    def test_put_all_three_limits(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/resource-limits",
                json={"memory_mb": 2048, "cpu_millicores": 1000, "timeout_s": 300},
                headers=_auth(token),
            )
        data = resp.json()
        assert data["memory_mb"] == 2048
        assert data["cpu_millicores"] == 1000
        assert data["timeout_s"] == 300

    def test_put_all_none(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/resource-limits",
                json={},
                headers=_auth(token),
            )
        assert resp.status_code == 200
        assert resp.json()["memory_mb"] is None

    def test_put_memory_zero_422(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/resource-limits",
                json={"memory_mb": 0},
                headers=_auth(token),
            )
        assert resp.status_code == 422
        assert "error" in resp.json()

    def test_put_memory_too_large_422(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/resource-limits",
                json={"memory_mb": 16385},
                headers=_auth(token),
            )
        assert resp.status_code == 422
        assert "error" in resp.json()

    def test_put_cpu_zero_422(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/resource-limits",
                json={"cpu_millicores": 0},
                headers=_auth(token),
            )
        assert resp.status_code == 422
        assert "error" in resp.json()

    def test_put_timeout_zero_422(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/resource-limits",
                json={"timeout_s": 0},
                headers=_auth(token),
            )
        assert resp.status_code == 422
        assert "error" in resp.json()

    def test_put_replaces_existing(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_limits(client, token, flow_id, memory_mb=256)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/resource-limits",
                json={"memory_mb": 4096},
                headers=_auth(token),
            )
        assert resp.json()["memory_mb"] == 4096

    def test_put_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.put(
                "/api/v1/flows/nonexistent/resource-limits",
                json={"memory_mb": 512},
                headers=_auth(token),
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_put_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/resource-limits",
                json={"memory_mb": 512},
            )
        assert resp.status_code == 401
        assert "error" in resp.json()


# ---------------------------------------------------------------------------
# Tests — GET /flows/{id}/resource-limits
# ---------------------------------------------------------------------------


class TestFlowResourceLimitsGet:
    def test_get_returns_limits_after_put(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_limits(client, token, flow_id, memory_mb=768)
            resp = client.get(f"/api/v1/flows/{flow_id}/resource-limits", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["memory_mb"] == 768

    def test_get_404_when_no_limits(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/resource-limits", headers=_auth(token))
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_get_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get(
                "/api/v1/flows/nonexistent/resource-limits", headers=_auth(token)
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_get_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_limits(client, token, flow_id)
            resp = client.get(f"/api/v1/flows/{flow_id}/resource-limits")
        assert resp.status_code == 401
        assert "error" in resp.json()


# ---------------------------------------------------------------------------
# Tests — DELETE /flows/{id}/resource-limits
# ---------------------------------------------------------------------------


class TestFlowResourceLimitsDelete:
    def test_delete_removes_limits(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_limits(client, token, flow_id)
            resp = client.delete(
                f"/api/v1/flows/{flow_id}/resource-limits", headers=_auth(token)
            )
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True
        assert resp.json()["flow_id"] == flow_id

    def test_get_404_after_delete(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_limits(client, token, flow_id)
            client.delete(f"/api/v1/flows/{flow_id}/resource-limits", headers=_auth(token))
            resp = client.get(f"/api/v1/flows/{flow_id}/resource-limits", headers=_auth(token))
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_delete_404_when_no_limits(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.delete(
                f"/api/v1/flows/{flow_id}/resource-limits", headers=_auth(token)
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_delete_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.delete(
                "/api/v1/flows/nonexistent/resource-limits", headers=_auth(token)
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_delete_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_limits(client, token, flow_id)
            resp = client.delete(f"/api/v1/flows/{flow_id}/resource-limits")
        assert resp.status_code == 401
        assert "error" in resp.json()
