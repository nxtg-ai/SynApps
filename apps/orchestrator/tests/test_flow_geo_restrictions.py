"""
N-187: Flow Geographic Restrictions — PUT/GET/DELETE /flows/{id}/geo-restrictions

Tests:
  - PUT sets restrictions; returns 200
  - PUT response shape (flow_id, mode, regions, updated_at)
  - PUT mode "allowlist" succeeds
  - PUT mode "blocklist" succeeds
  - PUT mode "none" succeeds
  - PUT invalid mode → 422
  - PUT with regions list stored
  - PUT deduplicates regions
  - PUT too many regions → 422
  - PUT replaces existing restrictions
  - PUT 404 for unknown flow
  - PUT requires auth
  - GET returns restrictions after PUT
  - GET 404 when no restrictions
  - GET 404 for unknown flow
  - GET requires auth
  - DELETE removes restrictions; returns {deleted: true, flow_id}
  - DELETE 404 when no restrictions
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
        json={"email": f"geo-{uid}@test.com", "password": "pass1234"},
    )
    assert r.status_code == 201
    return r.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_flow(client: TestClient, token: str) -> str:
    resp = client.post(
        "/api/v1/flows",
        json={"name": "Geo Restriction Test Flow", "nodes": [], "edges": []},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _set_geo(
    client: TestClient,
    token: str,
    flow_id: str,
    mode: str = "none",
    regions: list | None = None,
) -> dict:
    resp = client.put(
        f"/api/v1/flows/{flow_id}/geo-restrictions",
        json={"mode": mode, "regions": regions or []},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    return resp.json()


# ---------------------------------------------------------------------------
# Tests — PUT /flows/{id}/geo-restrictions
# ---------------------------------------------------------------------------


class TestFlowGeoRestrictionsPut:
    def test_put_returns_200(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/geo-restrictions",
                json={"mode": "none"},
                headers=_auth(token),
            )
        assert resp.status_code == 200

    def test_put_response_shape(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/geo-restrictions",
                json={"mode": "allowlist", "regions": ["US"]},
                headers=_auth(token),
            )
        data = resp.json()
        assert data["flow_id"] == flow_id
        assert data["mode"] == "allowlist"
        assert "regions" in data
        assert "updated_at" in data

    def test_put_allowlist_mode(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/geo-restrictions",
                json={"mode": "allowlist"},
                headers=_auth(token),
            )
        assert resp.json()["mode"] == "allowlist"

    def test_put_blocklist_mode(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/geo-restrictions",
                json={"mode": "blocklist"},
                headers=_auth(token),
            )
        assert resp.json()["mode"] == "blocklist"

    def test_put_none_mode(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/geo-restrictions",
                json={"mode": "none"},
                headers=_auth(token),
            )
        assert resp.json()["mode"] == "none"

    def test_put_invalid_mode_422(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/geo-restrictions",
                json={"mode": "whitelist"},
                headers=_auth(token),
            )
        assert resp.status_code == 422

    def test_put_stores_regions(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/geo-restrictions",
                json={"mode": "allowlist", "regions": ["US", "CA", "GB"]},
                headers=_auth(token),
            )
        assert len(resp.json()["regions"]) == 3  # Gate 2: non-empty

    def test_put_deduplicates_regions(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/geo-restrictions",
                json={"mode": "blocklist", "regions": ["US", "US", "CA"]},
                headers=_auth(token),
            )
        assert len(resp.json()["regions"]) == 2

    def test_put_too_many_regions_422(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/geo-restrictions",
                json={"mode": "allowlist", "regions": [f"R{i}" for i in range(51)]},
                headers=_auth(token),
            )
        assert resp.status_code == 422

    def test_put_replaces_existing(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_geo(client, token, flow_id, "allowlist", ["US"])
            resp = client.put(
                f"/api/v1/flows/{flow_id}/geo-restrictions",
                json={"mode": "blocklist", "regions": ["CN"]},
                headers=_auth(token),
            )
        assert resp.json()["mode"] == "blocklist"

    def test_put_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.put(
                "/api/v1/flows/nonexistent/geo-restrictions",
                json={"mode": "none"},
                headers=_auth(token),
            )
        assert resp.status_code == 404

    def test_put_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/geo-restrictions",
                json={"mode": "none"},
            )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Tests — GET /flows/{id}/geo-restrictions
# ---------------------------------------------------------------------------


class TestFlowGeoRestrictionsGet:
    def test_get_returns_restrictions_after_put(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_geo(client, token, flow_id, "allowlist", ["DE", "FR"])
            resp = client.get(f"/api/v1/flows/{flow_id}/geo-restrictions", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["mode"] == "allowlist"

    def test_get_404_when_no_restrictions(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/geo-restrictions", headers=_auth(token))
        assert resp.status_code == 404

    def test_get_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get(
                "/api/v1/flows/nonexistent/geo-restrictions", headers=_auth(token)
            )
        assert resp.status_code == 404

    def test_get_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_geo(client, token, flow_id)
            resp = client.get(f"/api/v1/flows/{flow_id}/geo-restrictions")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Tests — DELETE /flows/{id}/geo-restrictions
# ---------------------------------------------------------------------------


class TestFlowGeoRestrictionsDelete:
    def test_delete_removes_restrictions(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_geo(client, token, flow_id)
            resp = client.delete(
                f"/api/v1/flows/{flow_id}/geo-restrictions", headers=_auth(token)
            )
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True
        assert resp.json()["flow_id"] == flow_id

    def test_get_404_after_delete(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_geo(client, token, flow_id)
            client.delete(f"/api/v1/flows/{flow_id}/geo-restrictions", headers=_auth(token))
            resp = client.get(f"/api/v1/flows/{flow_id}/geo-restrictions", headers=_auth(token))
        assert resp.status_code == 404

    def test_delete_404_when_no_restrictions(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.delete(
                f"/api/v1/flows/{flow_id}/geo-restrictions", headers=_auth(token)
            )
        assert resp.status_code == 404

    def test_delete_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.delete(
                "/api/v1/flows/nonexistent/geo-restrictions", headers=_auth(token)
            )
        assert resp.status_code == 404

    def test_delete_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_geo(client, token, flow_id)
            resp = client.delete(f"/api/v1/flows/{flow_id}/geo-restrictions")
        assert resp.status_code == 401
