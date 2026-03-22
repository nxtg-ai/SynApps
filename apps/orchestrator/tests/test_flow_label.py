"""
N-138: Flow Labels — GET/PUT/DELETE /api/v1/flows/{flow_id}/label

Tests:
  - GET returns null label by default
  - PUT sets label, response contains color and icon
  - GET after PUT returns the label
  - PUT replaces existing label
  - PUT with empty icon is valid (icon is optional)
  - PUT with invalid color (not hex) → 422
  - PUT with icon longer than 2 chars → 422
  - DELETE removes label, returns null
  - DELETE when no label → 404
  - GET/PUT/DELETE return 404 for unknown flow
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
        json={"email": f"label-{uid}@test.com", "password": "pass1234"},
    )
    assert r.status_code == 201
    return r.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_flow(client: TestClient, token: str) -> str:
    resp = client.post(
        "/api/v1/flows",
        json={"name": "Label Test Flow", "nodes": [], "edges": []},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


# ---------------------------------------------------------------------------
# Tests — GET
# ---------------------------------------------------------------------------


class TestFlowLabelGet:
    def test_get_returns_null_by_default(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/label", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["label"] is None

    def test_get_includes_flow_id(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/label", headers=_auth(token))
        assert resp.json()["flow_id"] == flow_id

    def test_get_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get("/api/v1/flows/nonexistent/label", headers=_auth(token))
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_get_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/label")
        assert resp.status_code == 401
        assert "error" in resp.json()


# ---------------------------------------------------------------------------
# Tests — PUT
# ---------------------------------------------------------------------------


class TestFlowLabelSet:
    def test_put_returns_200(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/label",
                json={"color": "#ff5733"},
                headers=_auth(token),
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["flow_id"] == flow_id

    def test_put_response_contains_label(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/label",
                json={"color": "#00aaff", "icon": "🔥"},
                headers=_auth(token),
            )
        label = resp.json()["label"]
        assert label["color"] == "#00aaff"
        assert label["icon"] == "🔥"

    def test_put_icon_optional(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/label",
                json={"color": "#123456"},
                headers=_auth(token),
            )
        assert resp.status_code == 200
        assert resp.json()["label"]["icon"] == ""

    def test_get_after_put_returns_label(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            client.put(
                f"/api/v1/flows/{flow_id}/label",
                json={"color": "#abcdef"},
                headers=_auth(token),
            )
            resp = client.get(f"/api/v1/flows/{flow_id}/label", headers=_auth(token))
        assert resp.json()["label"]["color"] == "#abcdef"

    def test_put_replaces_existing(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            client.put(
                f"/api/v1/flows/{flow_id}/label",
                json={"color": "#111111"},
                headers=_auth(token),
            )
            client.put(
                f"/api/v1/flows/{flow_id}/label",
                json={"color": "#222222"},
                headers=_auth(token),
            )
            resp = client.get(f"/api/v1/flows/{flow_id}/label", headers=_auth(token))
        assert resp.json()["label"]["color"] == "#222222"

    def test_put_invalid_color_422(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/label",
                json={"color": "red"},
                headers=_auth(token),
            )
        assert resp.status_code == 422
        assert "error" in resp.json()

    def test_put_icon_too_long_422(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/label",
                json={"color": "#ff0000", "icon": "abc"},
                headers=_auth(token),
            )
        assert resp.status_code == 422
        assert "error" in resp.json()

    def test_put_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.put(
                "/api/v1/flows/nonexistent/label",
                json={"color": "#ff0000"},
                headers=_auth(token),
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_put_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/label",
                json={"color": "#ff0000"},
            )
        assert resp.status_code == 401
        assert "error" in resp.json()


# ---------------------------------------------------------------------------
# Tests — DELETE
# ---------------------------------------------------------------------------


class TestFlowLabelDelete:
    def test_delete_returns_200(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            client.put(
                f"/api/v1/flows/{flow_id}/label",
                json={"color": "#ff0000"},
                headers=_auth(token),
            )
            resp = client.delete(f"/api/v1/flows/{flow_id}/label", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["label"] is None

    def test_delete_clears_label(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            client.put(
                f"/api/v1/flows/{flow_id}/label",
                json={"color": "#ff0000"},
                headers=_auth(token),
            )
            client.delete(f"/api/v1/flows/{flow_id}/label", headers=_auth(token))
            resp = client.get(f"/api/v1/flows/{flow_id}/label", headers=_auth(token))
        assert resp.json()["label"] is None

    def test_delete_no_label_404(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.delete(f"/api/v1/flows/{flow_id}/label", headers=_auth(token))
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_delete_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.delete("/api/v1/flows/nonexistent/label", headers=_auth(token))
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_delete_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            client.put(
                f"/api/v1/flows/{flow_id}/label",
                json={"color": "#ff0000"},
                headers=_auth(token),
            )
            resp = client.delete(f"/api/v1/flows/{flow_id}/label")
        assert resp.status_code == 401
        assert "error" in resp.json()
