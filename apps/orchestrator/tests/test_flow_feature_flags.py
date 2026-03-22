"""
N-191: Flow Feature Flags — PUT/GET/DELETE /flows/{id}/feature-flags/{flag_name}

Tests:
  - PUT creates/updates flag; returns 200
  - PUT response shape (flag_name, flow_id, enabled, rollout_percentage, description, updated_at)
  - PUT enabled=True stored
  - PUT enabled=False stored
  - PUT rollout_percentage stored
  - PUT rollout_percentage=0 allowed
  - PUT rollout_percentage=100 allowed
  - PUT rollout_percentage>100 → 422
  - PUT rollout_percentage<0 → 422
  - PUT description stored
  - PUT replaces existing flag
  - PUT 404 for unknown flow
  - PUT requires auth
  - GET list returns flags
  - GET list empty when none
  - GET list 404 unknown flow
  - GET list requires auth
  - GET single returns flag
  - GET single 404 unknown flag
  - GET single 404 unknown flow
  - GET single requires auth
  - DELETE removes flag; returns {deleted: true, flag_name, flow_id}
  - DELETE 404 not found
  - DELETE 404 unknown flow
  - DELETE requires auth
  - DELETE then GET 404
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
        json={"email": f"ff-{uid}@test.com", "password": "pass1234"},
    )
    assert r.status_code == 201
    return r.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_flow(client: TestClient, token: str) -> str:
    resp = client.post(
        "/api/v1/flows",
        json={"name": "Feature Flag Test Flow", "nodes": [], "edges": []},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _set_flag(
    client: TestClient,
    token: str,
    flow_id: str,
    flag_name: str = "my-feature",
    enabled: bool = True,
    rollout_percentage: int = 100,
    description: str = "",
) -> dict:
    resp = client.put(
        f"/api/v1/flows/{flow_id}/feature-flags/{flag_name}",
        json={"enabled": enabled, "rollout_percentage": rollout_percentage, "description": description},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    return resp.json()


# ---------------------------------------------------------------------------
# Tests — PUT /flows/{id}/feature-flags/{flag_name}
# ---------------------------------------------------------------------------


class TestFlowFeatureFlagPut:
    def test_put_returns_200(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/feature-flags/new-ui",
                json={"enabled": True},
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
                f"/api/v1/flows/{flow_id}/feature-flags/beta",
                json={"enabled": True, "rollout_percentage": 50},
                headers=_auth(token),
            )
        data = resp.json()
        assert data["flag_name"] == "beta"
        assert data["flow_id"] == flow_id
        assert "enabled" in data
        assert "rollout_percentage" in data
        assert "description" in data
        assert "updated_at" in data

    def test_put_enabled_true(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/feature-flags/feat-a",
                json={"enabled": True},
                headers=_auth(token),
            )
        assert resp.json()["enabled"] is True

    def test_put_enabled_false(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/feature-flags/feat-b",
                json={"enabled": False},
                headers=_auth(token),
            )
        assert resp.json()["enabled"] is False

    def test_put_rollout_percentage_stored(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/feature-flags/canary",
                json={"rollout_percentage": 25},
                headers=_auth(token),
            )
        assert resp.json()["rollout_percentage"] == 25

    def test_put_rollout_zero_allowed(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/feature-flags/disabled",
                json={"rollout_percentage": 0},
                headers=_auth(token),
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["flow_id"] == flow_id

    def test_put_rollout_100_allowed(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/feature-flags/full",
                json={"rollout_percentage": 100},
                headers=_auth(token),
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["flow_id"] == flow_id

    def test_put_rollout_over_100_422(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/feature-flags/over",
                json={"rollout_percentage": 101},
                headers=_auth(token),
            )
        assert resp.status_code == 422
        assert "error" in resp.json()

    def test_put_rollout_negative_422(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/feature-flags/neg",
                json={"rollout_percentage": -1},
                headers=_auth(token),
            )
        assert resp.status_code == 422
        assert "error" in resp.json()

    def test_put_description_stored(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/feature-flags/described",
                json={"description": "Enables the new dashboard UI"},
                headers=_auth(token),
            )
        assert resp.json()["description"] == "Enables the new dashboard UI"

    def test_put_replaces_existing(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_flag(client, token, flow_id, rollout_percentage=10)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/feature-flags/my-feature",
                json={"rollout_percentage": 75},
                headers=_auth(token),
            )
        assert resp.json()["rollout_percentage"] == 75

    def test_put_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.put(
                "/api/v1/flows/nonexistent/feature-flags/flag",
                json={"enabled": True},
                headers=_auth(token),
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_put_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/feature-flags/flag",
                json={"enabled": True},
            )
        assert resp.status_code == 401
        assert "error" in resp.json()


# ---------------------------------------------------------------------------
# Tests — GET /flows/{id}/feature-flags (list)
# ---------------------------------------------------------------------------


class TestFlowFeatureFlagList:
    def test_list_returns_flags(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_flag(client, token, flow_id, flag_name="flag-a")
            _set_flag(client, token, flow_id, flag_name="flag-b")
            resp = client.get(f"/api/v1/flows/{flow_id}/feature-flags", headers=_auth(token))
        assert resp.status_code == 200
        assert len(resp.json()) == 2  # Gate 2

    def test_list_empty_when_none(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/feature-flags", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get("/api/v1/flows/nonexistent/feature-flags", headers=_auth(token))
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_list_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/feature-flags")
        assert resp.status_code == 401
        assert "error" in resp.json()


# ---------------------------------------------------------------------------
# Tests — GET /flows/{id}/feature-flags/{flag_name}
# ---------------------------------------------------------------------------


class TestFlowFeatureFlagGet:
    def test_get_returns_flag(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_flag(client, token, flow_id, flag_name="specific", rollout_percentage=42)
            resp = client.get(
                f"/api/v1/flows/{flow_id}/feature-flags/specific", headers=_auth(token)
            )
        assert resp.status_code == 200
        assert resp.json()["rollout_percentage"] == 42

    def test_get_404_unknown_flag(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(
                f"/api/v1/flows/{flow_id}/feature-flags/nonexistent", headers=_auth(token)
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_get_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get(
                "/api/v1/flows/nonexistent/feature-flags/any", headers=_auth(token)
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_get_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_flag(client, token, flow_id)
            resp = client.get(f"/api/v1/flows/{flow_id}/feature-flags/my-feature")
        assert resp.status_code == 401
        assert "error" in resp.json()


# ---------------------------------------------------------------------------
# Tests — DELETE /flows/{id}/feature-flags/{flag_name}
# ---------------------------------------------------------------------------


class TestFlowFeatureFlagDelete:
    def test_delete_removes_flag(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_flag(client, token, flow_id, flag_name="to-delete")
            resp = client.delete(
                f"/api/v1/flows/{flow_id}/feature-flags/to-delete", headers=_auth(token)
            )
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True
        assert resp.json()["flag_name"] == "to-delete"
        assert resp.json()["flow_id"] == flow_id

    def test_delete_then_get_404(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_flag(client, token, flow_id, flag_name="gone")
            client.delete(f"/api/v1/flows/{flow_id}/feature-flags/gone", headers=_auth(token))
            resp = client.get(
                f"/api/v1/flows/{flow_id}/feature-flags/gone", headers=_auth(token)
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_delete_404_not_found(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.delete(
                f"/api/v1/flows/{flow_id}/feature-flags/nonexistent", headers=_auth(token)
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_delete_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.delete(
                "/api/v1/flows/nonexistent/feature-flags/any", headers=_auth(token)
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_delete_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_flag(client, token, flow_id)
            resp = client.delete(f"/api/v1/flows/{flow_id}/feature-flags/my-feature")
        assert resp.status_code == 401
        assert "error" in resp.json()
