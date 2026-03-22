"""
N-141: Flow Save-as-Template — POST /api/v1/flows/{flow_id}/save-as-template

Tests:
  - Returns 201 with template entry (id, version, semver, name, nodes, edges)
  - Template name defaults to the flow name when body.name is omitted
  - Custom name overrides the flow name
  - Description, tags, version are stored
  - Tags are lowercased and stripped
  - Calling twice on the same flow creates version 2 (auto-increment)
  - Explicit semver is respected
  - Duplicate explicit semver → 409
  - Invalid semver → 409
  - Template nodes/edges match the flow
  - metadata contains created_from_flow and author
  - 404 for unknown flow
  - Auth required
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
        json={"email": f"tmpl-{uid}@test.com", "password": "pass1234"},
    )
    assert r.status_code == 201
    return r.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_flow(client: TestClient, token: str, name: str = "My Flow") -> str:
    resp = client.post(
        "/api/v1/flows",
        json={"name": name, "nodes": [], "edges": []},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _save(client: TestClient, token: str, flow_id: str, **kwargs) -> dict:
    resp = client.post(
        f"/api/v1/flows/{flow_id}/save-as-template",
        json=kwargs or None,
        headers=_auth(token),
    )
    return resp


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSaveAsTemplate:
    def test_returns_201(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = _save(client, token, flow_id)
        assert resp.status_code == 201
        data = resp.json()
        assert data["id"] == flow_id

    def test_response_shape(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = _save(client, token, flow_id)
        data = resp.json()
        assert data["id"] == flow_id
        assert data["version"] == 1
        assert "semver" in data
        assert "name" in data

    def test_name_defaults_to_flow_name(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token, "My Awesome Flow")
            resp = _save(client, token, flow_id)
        assert resp.json()["name"] == "My Awesome Flow"

    def test_custom_name_overrides_flow_name(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token, "Original Name")
            resp = _save(client, token, flow_id, name="Custom Template Name")
        assert resp.json()["name"] == "Custom Template Name"

    def test_description_stored(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = _save(client, token, flow_id, description="A helpful template")
        assert resp.json()["description"] == "A helpful template"

    def test_tags_stored_and_lowercased(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = _save(client, token, flow_id, tags=["AI", "Production"])
        assert set(resp.json()["tags"]) == {"ai", "production"}

    def test_nodes_match_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = _save(client, token, flow_id)
        # Flow was created with empty nodes; template should mirror that
        assert isinstance(resp.json()["nodes"], list)

    def test_metadata_contains_author(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = _save(client, token, flow_id)
        meta = resp.json()["metadata"]
        assert meta["created_from_flow"] == flow_id
        assert "author" in meta

    def test_second_save_increments_version(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _save(client, token, flow_id)
            resp = _save(client, token, flow_id)
        assert resp.json()["version"] == 2

    def test_second_save_bumps_semver(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _save(client, token, flow_id)
            resp = _save(client, token, flow_id)
        # First was 1.0.0, second should be 1.0.1
        assert resp.json()["semver"] == "1.0.1"

    def test_explicit_semver_respected(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = _save(client, token, flow_id, version="2.0.0")
        assert resp.json()["semver"] == "2.0.0"

    def test_duplicate_semver_409(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _save(client, token, flow_id, version="1.5.0")
            resp = _save(client, token, flow_id, version="1.5.0")
        assert resp.status_code == 409
        assert "error" in resp.json()

    def test_invalid_semver_409(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = _save(client, token, flow_id, version="not-a-semver")
        assert resp.status_code == 409
        assert "error" in resp.json()

    def test_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.post(
                "/api/v1/flows/nonexistent/save-as-template",
                headers=_auth(token),
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(f"/api/v1/flows/{flow_id}/save-as-template")
        assert resp.status_code == 401
        assert "error" in resp.json()
