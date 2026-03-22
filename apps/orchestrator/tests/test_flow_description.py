"""
N-134: Flow Descriptions — GET/PUT /api/v1/flows/{flow_id}/description

Tests:
  - GET returns empty string by default
  - PUT sets description, response contains new text
  - GET after PUT returns the set description
  - PUT replaces existing description
  - PUT with empty string clears the description
  - Description is truncated at 4000 chars
  - GET/PUT return 404 for unknown flow
  - Auth required on both endpoints
"""

import uuid

from fastapi.testclient import TestClient

from apps.orchestrator.main import app
from apps.orchestrator.stores import FlowDescriptionStore

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _register(client: TestClient) -> str:
    uid = uuid.uuid4().hex[:8]
    r = client.post(
        "/api/v1/auth/register",
        json={"email": f"desc-{uid}@test.com", "password": "pass1234"},
    )
    assert r.status_code == 201
    return r.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_flow(client: TestClient, token: str) -> str:
    resp = client.post(
        "/api/v1/flows",
        json={"name": "Desc Test Flow", "nodes": [], "edges": []},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestFlowDescriptionGet:
    def test_get_returns_empty_by_default(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/description", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["description"] == ""

    def test_get_includes_flow_id(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/description", headers=_auth(token))
        assert resp.json()["flow_id"] == flow_id

    def test_get_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get("/api/v1/flows/nonexistent/description", headers=_auth(token))
        assert resp.status_code == 404

    def test_get_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/description")
        assert resp.status_code == 401


class TestFlowDescriptionSet:
    def test_put_returns_200(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/description",
                json={"description": "Hello world"},
                headers=_auth(token),
            )
        assert resp.status_code == 200

    def test_put_response_contains_description(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/description",
                json={"description": "My description"},
                headers=_auth(token),
            )
        assert resp.json()["description"] == "My description"

    def test_get_after_put_returns_description(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            client.put(
                f"/api/v1/flows/{flow_id}/description",
                json={"description": "Persisted text"},
                headers=_auth(token),
            )
            resp = client.get(f"/api/v1/flows/{flow_id}/description", headers=_auth(token))
        assert resp.json()["description"] == "Persisted text"

    def test_put_replaces_existing(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            client.put(
                f"/api/v1/flows/{flow_id}/description",
                json={"description": "First"},
                headers=_auth(token),
            )
            client.put(
                f"/api/v1/flows/{flow_id}/description",
                json={"description": "Second"},
                headers=_auth(token),
            )
            resp = client.get(f"/api/v1/flows/{flow_id}/description", headers=_auth(token))
        assert resp.json()["description"] == "Second"

    def test_put_empty_string_clears_description(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            client.put(
                f"/api/v1/flows/{flow_id}/description",
                json={"description": "Will be cleared"},
                headers=_auth(token),
            )
            client.put(
                f"/api/v1/flows/{flow_id}/description",
                json={"description": ""},
                headers=_auth(token),
            )
            resp = client.get(f"/api/v1/flows/{flow_id}/description", headers=_auth(token))
        assert resp.json()["description"] == ""

    def test_put_accepts_exactly_max_len(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            text = "x" * FlowDescriptionStore.MAX_LEN
            resp = client.put(
                f"/api/v1/flows/{flow_id}/description",
                json={"description": text},
                headers=_auth(token),
            )
        assert resp.status_code == 200
        assert len(resp.json()["description"]) == FlowDescriptionStore.MAX_LEN

    def test_put_rejects_over_max_len(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            over_limit = "x" * (FlowDescriptionStore.MAX_LEN + 1)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/description",
                json={"description": over_limit},
                headers=_auth(token),
            )
        assert resp.status_code == 422

    def test_put_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.put(
                "/api/v1/flows/nonexistent/description",
                json={"description": "x"},
                headers=_auth(token),
            )
        assert resp.status_code == 404

    def test_put_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/description",
                json={"description": "x"},
            )
        assert resp.status_code == 401
