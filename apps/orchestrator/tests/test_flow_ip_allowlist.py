"""
N-188: Flow IP Allowlist — PUT/GET/DELETE /flows/{id}/ip-allowlist

Tests:
  - PUT sets allowlist; returns 200
  - PUT response shape (flow_id, enabled, cidrs, updated_at)
  - PUT enabled=True stored
  - PUT enabled=False stored
  - PUT with CIDR entries stored
  - PUT deduplicates cidrs
  - PUT empty cidrs allowed
  - PUT too many cidrs → 422
  - PUT replaces existing allowlist
  - PUT 404 for unknown flow
  - PUT requires auth
  - GET returns allowlist after PUT
  - GET 404 when no allowlist
  - GET 404 for unknown flow
  - GET requires auth
  - DELETE removes allowlist; returns {deleted: true, flow_id}
  - DELETE 404 when no allowlist
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
        json={"email": f"ipal-{uid}@test.com", "password": "pass1234"},
    )
    assert r.status_code == 201
    return r.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_flow(client: TestClient, token: str) -> str:
    resp = client.post(
        "/api/v1/flows",
        json={"name": "IP Allowlist Test Flow", "nodes": [], "edges": []},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _set_allowlist(
    client: TestClient,
    token: str,
    flow_id: str,
    enabled: bool = True,
    cidrs: list | None = None,
) -> dict:
    resp = client.put(
        f"/api/v1/flows/{flow_id}/ip-allowlist",
        json={"enabled": enabled, "cidrs": cidrs or []},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    return resp.json()


# ---------------------------------------------------------------------------
# Tests — PUT /flows/{id}/ip-allowlist
# ---------------------------------------------------------------------------


class TestFlowIpAllowlistPut:
    def test_put_returns_200(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/ip-allowlist",
                json={"enabled": True, "cidrs": ["10.0.0.0/8"]},
                headers=_auth(token),
            )
        assert resp.status_code == 200

    def test_put_response_shape(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/ip-allowlist",
                json={"enabled": True, "cidrs": []},
                headers=_auth(token),
            )
        data = resp.json()
        assert data["flow_id"] == flow_id
        assert "enabled" in data
        assert "cidrs" in data
        assert "updated_at" in data

    def test_put_enabled_true(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/ip-allowlist",
                json={"enabled": True},
                headers=_auth(token),
            )
        assert resp.json()["enabled"] is True

    def test_put_enabled_false(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/ip-allowlist",
                json={"enabled": False},
                headers=_auth(token),
            )
        assert resp.json()["enabled"] is False

    def test_put_stores_cidrs(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/ip-allowlist",
                json={"cidrs": ["192.168.0.0/24", "10.0.0.1/32"]},
                headers=_auth(token),
            )
        assert len(resp.json()["cidrs"]) == 2  # Gate 2

    def test_put_deduplicates_cidrs(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/ip-allowlist",
                json={"cidrs": ["10.0.0.0/8", "10.0.0.0/8", "172.16.0.0/12"]},
                headers=_auth(token),
            )
        assert len(resp.json()["cidrs"]) == 2

    def test_put_empty_cidrs_allowed(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/ip-allowlist",
                json={"cidrs": []},
                headers=_auth(token),
            )
        assert resp.status_code == 200

    def test_put_too_many_cidrs_422(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/ip-allowlist",
                json={"cidrs": [f"10.0.{i}.0/24" for i in range(101)]},
                headers=_auth(token),
            )
        assert resp.status_code == 422

    def test_put_replaces_existing(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_allowlist(client, token, flow_id, cidrs=["10.0.0.0/8"])
            resp = client.put(
                f"/api/v1/flows/{flow_id}/ip-allowlist",
                json={"cidrs": ["192.168.1.0/24"]},
                headers=_auth(token),
            )
        assert resp.json()["cidrs"] == ["192.168.1.0/24"]

    def test_put_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.put(
                "/api/v1/flows/nonexistent/ip-allowlist",
                json={"cidrs": []},
                headers=_auth(token),
            )
        assert resp.status_code == 404

    def test_put_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/ip-allowlist",
                json={"cidrs": []},
            )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Tests — GET /flows/{id}/ip-allowlist
# ---------------------------------------------------------------------------


class TestFlowIpAllowlistGet:
    def test_get_returns_allowlist_after_put(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_allowlist(client, token, flow_id, cidrs=["172.16.0.0/12"])
            resp = client.get(f"/api/v1/flows/{flow_id}/ip-allowlist", headers=_auth(token))
        assert resp.status_code == 200
        assert "172.16.0.0/12" in resp.json()["cidrs"]

    def test_get_404_when_no_allowlist(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/ip-allowlist", headers=_auth(token))
        assert resp.status_code == 404

    def test_get_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get("/api/v1/flows/nonexistent/ip-allowlist", headers=_auth(token))
        assert resp.status_code == 404

    def test_get_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_allowlist(client, token, flow_id)
            resp = client.get(f"/api/v1/flows/{flow_id}/ip-allowlist")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Tests — DELETE /flows/{id}/ip-allowlist
# ---------------------------------------------------------------------------


class TestFlowIpAllowlistDelete:
    def test_delete_removes_allowlist(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_allowlist(client, token, flow_id)
            resp = client.delete(f"/api/v1/flows/{flow_id}/ip-allowlist", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True
        assert resp.json()["flow_id"] == flow_id

    def test_get_404_after_delete(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_allowlist(client, token, flow_id)
            client.delete(f"/api/v1/flows/{flow_id}/ip-allowlist", headers=_auth(token))
            resp = client.get(f"/api/v1/flows/{flow_id}/ip-allowlist", headers=_auth(token))
        assert resp.status_code == 404

    def test_delete_404_when_no_allowlist(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.delete(f"/api/v1/flows/{flow_id}/ip-allowlist", headers=_auth(token))
        assert resp.status_code == 404

    def test_delete_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.delete(
                "/api/v1/flows/nonexistent/ip-allowlist", headers=_auth(token)
            )
        assert resp.status_code == 404

    def test_delete_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_allowlist(client, token, flow_id)
            resp = client.delete(f"/api/v1/flows/{flow_id}/ip-allowlist")
        assert resp.status_code == 401
