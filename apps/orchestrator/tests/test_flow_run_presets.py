"""
N-153: Flow Run Presets — POST/GET /flows/{id}/presets
                           GET/DELETE /flows/{id}/presets/{preset_id}
                           POST /flows/{id}/runs?preset_id={id}

Tests:
  - POST creates preset; returns 201
  - POST response includes id, flow_id, name, description, input, created_at
  - GET returns empty list on fresh flow
  - GET lists all presets
  - GET single preset by id
  - GET single preset 404 for unknown id
  - DELETE removes preset
  - DELETE 404 for unknown preset
  - POST/GET/DELETE 404 for unknown flow
  - Auth required on all endpoints
  - POST /runs?preset_id= loads preset input
  - POST /runs?preset_id= 404 for unknown preset
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
        json={"email": f"preset-{uid}@test.com", "password": "pass1234"},
    )
    assert r.status_code == 201
    return r.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_flow(client: TestClient, token: str) -> str:
    resp = client.post(
        "/api/v1/flows",
        json={"name": "Preset Test Flow", "nodes": [], "edges": []},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _add_preset(
    client: TestClient,
    token: str,
    flow_id: str,
    name: str = "My Preset",
    input_data: dict | None = None,
) -> dict:
    resp = client.post(
        f"/api/v1/flows/{flow_id}/presets",
        json={"name": name, "input": input_data or {"key": "value"}},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    return resp.json()


# ---------------------------------------------------------------------------
# Tests — POST /flows/{id}/presets
# ---------------------------------------------------------------------------


class TestFlowRunPresetPost:
    def test_post_returns_201(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/presets",
                json={"name": "Quick Run", "input": {"prompt": "hello"}},
                headers=_auth(token),
            )
        assert resp.status_code == 201

    def test_post_response_shape(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/presets",
                json={"name": "Shape Test", "description": "My desc", "input": {"x": 1}},
                headers=_auth(token),
            )
        data = resp.json()
        assert "id" in data
        assert data["flow_id"] == flow_id
        assert data["name"] == "Shape Test"
        assert data["description"] == "My desc"
        assert data["input"] == {"x": 1}
        assert "created_at" in data

    def test_post_empty_description_defaults(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/presets",
                json={"name": "No Desc", "input": {}},
                headers=_auth(token),
            )
        assert resp.json()["description"] == ""

    def test_post_empty_name_422(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/presets",
                json={"name": "", "input": {}},
                headers=_auth(token),
            )
        assert resp.status_code == 422

    def test_post_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.post(
                "/api/v1/flows/nonexistent/presets",
                json={"name": "x", "input": {}},
                headers=_auth(token),
            )
        assert resp.status_code == 404

    def test_post_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/presets",
                json={"name": "x", "input": {}},
            )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Tests — GET /flows/{id}/presets
# ---------------------------------------------------------------------------


class TestFlowRunPresetList:
    def test_get_empty_on_fresh_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/presets", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["items"] == []

    def test_get_lists_presets(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _add_preset(client, token, flow_id, "Preset A")
            _add_preset(client, token, flow_id, "Preset B")
            resp = client.get(f"/api/v1/flows/{flow_id}/presets", headers=_auth(token))
        items = resp.json()["items"]
        assert len(items) == 2
        names = {p["name"] for p in items}
        assert names == {"Preset A", "Preset B"}

    def test_get_flow_id_in_response(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/presets", headers=_auth(token))
        assert resp.json()["flow_id"] == flow_id

    def test_get_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get("/api/v1/flows/nonexistent/presets", headers=_auth(token))
        assert resp.status_code == 404

    def test_get_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/presets")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Tests — GET /flows/{id}/presets/{preset_id}
# ---------------------------------------------------------------------------


class TestFlowRunPresetGetOne:
    def test_get_single_returns_200(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            preset = _add_preset(client, token, flow_id)
            resp = client.get(
                f"/api/v1/flows/{flow_id}/presets/{preset['id']}", headers=_auth(token)
            )
        assert resp.status_code == 200

    def test_get_single_correct_data(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            preset = _add_preset(client, token, flow_id, "Named Preset", {"z": 99})
            resp = client.get(
                f"/api/v1/flows/{flow_id}/presets/{preset['id']}", headers=_auth(token)
            )
        data = resp.json()
        assert data["name"] == "Named Preset"
        assert data["input"] == {"z": 99}

    def test_get_single_404_unknown_preset(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(
                f"/api/v1/flows/{flow_id}/presets/nonexistent", headers=_auth(token)
            )
        assert resp.status_code == 404

    def test_get_single_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            preset = _add_preset(client, token, flow_id)
            resp = client.get(f"/api/v1/flows/{flow_id}/presets/{preset['id']}")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Tests — DELETE /flows/{id}/presets/{preset_id}
# ---------------------------------------------------------------------------


class TestFlowRunPresetDelete:
    def test_delete_removes_preset(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            preset = _add_preset(client, token, flow_id)
            resp = client.delete(
                f"/api/v1/flows/{flow_id}/presets/{preset['id']}", headers=_auth(token)
            )
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True

    def test_get_after_delete_shows_empty(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            preset = _add_preset(client, token, flow_id)
            client.delete(
                f"/api/v1/flows/{flow_id}/presets/{preset['id']}", headers=_auth(token)
            )
            resp = client.get(f"/api/v1/flows/{flow_id}/presets", headers=_auth(token))
        assert resp.json()["items"] == []

    def test_delete_404_unknown_preset(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.delete(
                f"/api/v1/flows/{flow_id}/presets/nonexistent", headers=_auth(token)
            )
        assert resp.status_code == 404

    def test_delete_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.delete(
                "/api/v1/flows/nonexistent/presets/any-id", headers=_auth(token)
            )
        assert resp.status_code == 404

    def test_delete_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            preset = _add_preset(client, token, flow_id)
            resp = client.delete(f"/api/v1/flows/{flow_id}/presets/{preset['id']}")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Tests — POST /flows/{id}/runs?preset_id=
# ---------------------------------------------------------------------------


class TestFlowRunWithPreset:
    def test_run_with_preset_returns_202(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            preset = _add_preset(client, token, flow_id, input_data={"hello": "world"})
            resp = client.post(
                f"/api/v1/flows/{flow_id}/runs?preset_id={preset['id']}",
                json={},
                headers=_auth(token),
            )
        assert resp.status_code == 202

    def test_run_unknown_preset_404(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/runs?preset_id=nonexistent",
                json={},
                headers=_auth(token),
            )
        assert resp.status_code == 404
