"""
N-154: Flow Annotations — POST/GET /flows/{id}/annotations
                           PATCH/DELETE /flows/{id}/annotations/{ann_id}

Tests:
  - POST creates annotation; returns 201
  - POST response includes id, flow_id, content, x, y, color, author, created_at, updated_at
  - POST default color is #FFFF99
  - POST invalid hex color → 422
  - POST empty content → 422
  - GET returns empty list on fresh flow
  - GET lists annotations with flow_id
  - PATCH updates content
  - PATCH updates position (x, y)
  - PATCH updates color
  - PATCH partial (only content)
  - PATCH 404 for unknown annotation
  - DELETE removes annotation
  - GET after DELETE shows empty
  - DELETE 404 for unknown annotation
  - POST/GET/PATCH/DELETE 404 for unknown flow
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
        json={"email": f"ann-{uid}@test.com", "password": "pass1234"},
    )
    assert r.status_code == 201
    return r.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_flow(client: TestClient, token: str) -> str:
    resp = client.post(
        "/api/v1/flows",
        json={"name": "Annotation Test Flow", "nodes": [], "edges": []},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _add_annotation(
    client: TestClient,
    token: str,
    flow_id: str,
    content: str = "A note",
    x: float = 100.0,
    y: float = 200.0,
) -> dict:
    resp = client.post(
        f"/api/v1/flows/{flow_id}/annotations",
        json={"content": content, "x": x, "y": y},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    return resp.json()


# ---------------------------------------------------------------------------
# Tests — POST /flows/{id}/annotations
# ---------------------------------------------------------------------------


class TestFlowAnnotationPost:
    def test_post_returns_201(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/annotations",
                json={"content": "Remember to optimize", "x": 50.0, "y": 75.0},
                headers=_auth(token),
            )
        assert resp.status_code == 201

    def test_post_response_shape(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/annotations",
                json={"content": "Shape test", "x": 10.0, "y": 20.0, "color": "#FF0000"},
                headers=_auth(token),
            )
        data = resp.json()
        assert "id" in data
        assert data["flow_id"] == flow_id
        assert data["content"] == "Shape test"
        assert data["x"] == 10.0
        assert data["y"] == 20.0
        assert data["color"] == "#FF0000"
        assert "author" in data
        assert "created_at" in data
        assert "updated_at" in data

    def test_post_default_color(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/annotations",
                json={"content": "Default color", "x": 0.0, "y": 0.0},
                headers=_auth(token),
            )
        assert resp.json()["color"] == "#FFFF99"

    def test_post_invalid_color_422(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/annotations",
                json={"content": "test", "x": 0.0, "y": 0.0, "color": "not-a-color"},
                headers=_auth(token),
            )
        assert resp.status_code == 422

    def test_post_empty_content_422(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/annotations",
                json={"content": "", "x": 0.0, "y": 0.0},
                headers=_auth(token),
            )
        assert resp.status_code == 422

    def test_post_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.post(
                "/api/v1/flows/nonexistent/annotations",
                json={"content": "test", "x": 0.0, "y": 0.0},
                headers=_auth(token),
            )
        assert resp.status_code == 404

    def test_post_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/annotations",
                json={"content": "test", "x": 0.0, "y": 0.0},
            )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Tests — GET /flows/{id}/annotations
# ---------------------------------------------------------------------------


class TestFlowAnnotationGet:
    def test_get_empty_on_fresh_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/annotations", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["items"] == []

    def test_get_lists_annotations(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _add_annotation(client, token, flow_id, "Note A")
            _add_annotation(client, token, flow_id, "Note B")
            resp = client.get(f"/api/v1/flows/{flow_id}/annotations", headers=_auth(token))
        items = resp.json()["items"]
        assert len(items) == 2

    def test_get_flow_id_in_response(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/annotations", headers=_auth(token))
        assert resp.json()["flow_id"] == flow_id

    def test_get_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get("/api/v1/flows/nonexistent/annotations", headers=_auth(token))
        assert resp.status_code == 404

    def test_get_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/annotations")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Tests — PATCH /flows/{id}/annotations/{ann_id}
# ---------------------------------------------------------------------------


class TestFlowAnnotationPatch:
    def test_patch_updates_content(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            ann = _add_annotation(client, token, flow_id, "Old content")
            resp = client.patch(
                f"/api/v1/flows/{flow_id}/annotations/{ann['id']}",
                json={"content": "New content"},
                headers=_auth(token),
            )
        assert resp.status_code == 200
        assert resp.json()["content"] == "New content"

    def test_patch_updates_position(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            ann = _add_annotation(client, token, flow_id, x=0.0, y=0.0)
            resp = client.patch(
                f"/api/v1/flows/{flow_id}/annotations/{ann['id']}",
                json={"x": 999.0, "y": 888.0},
                headers=_auth(token),
            )
        assert resp.json()["x"] == 999.0
        assert resp.json()["y"] == 888.0

    def test_patch_updates_color(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            ann = _add_annotation(client, token, flow_id)
            resp = client.patch(
                f"/api/v1/flows/{flow_id}/annotations/{ann['id']}",
                json={"color": "#00FF00"},
                headers=_auth(token),
            )
        assert resp.json()["color"] == "#00FF00"

    def test_patch_updates_updated_at(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            ann = _add_annotation(client, token, flow_id)
            resp = client.patch(
                f"/api/v1/flows/{flow_id}/annotations/{ann['id']}",
                json={"content": "changed"},
                headers=_auth(token),
            )
        # updated_at should be a valid ISO string
        assert "T" in resp.json()["updated_at"]

    def test_patch_404_unknown_annotation(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.patch(
                f"/api/v1/flows/{flow_id}/annotations/nonexistent",
                json={"content": "x"},
                headers=_auth(token),
            )
        assert resp.status_code == 404

    def test_patch_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.patch(
                "/api/v1/flows/nonexistent/annotations/any-id",
                json={"content": "x"},
                headers=_auth(token),
            )
        assert resp.status_code == 404

    def test_patch_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            ann = _add_annotation(client, token, flow_id)
            resp = client.patch(
                f"/api/v1/flows/{flow_id}/annotations/{ann['id']}",
                json={"content": "no-auth"},
            )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Tests — DELETE /flows/{id}/annotations/{ann_id}
# ---------------------------------------------------------------------------


class TestFlowAnnotationDelete:
    def test_delete_removes_annotation(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            ann = _add_annotation(client, token, flow_id)
            resp = client.delete(
                f"/api/v1/flows/{flow_id}/annotations/{ann['id']}", headers=_auth(token)
            )
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True

    def test_get_after_delete_shows_empty(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            ann = _add_annotation(client, token, flow_id)
            client.delete(
                f"/api/v1/flows/{flow_id}/annotations/{ann['id']}", headers=_auth(token)
            )
            resp = client.get(f"/api/v1/flows/{flow_id}/annotations", headers=_auth(token))
        assert resp.json()["items"] == []

    def test_delete_404_unknown_annotation(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.delete(
                f"/api/v1/flows/{flow_id}/annotations/nonexistent", headers=_auth(token)
            )
        assert resp.status_code == 404

    def test_delete_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.delete(
                "/api/v1/flows/nonexistent/annotations/any-id", headers=_auth(token)
            )
        assert resp.status_code == 404

    def test_delete_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            ann = _add_annotation(client, token, flow_id)
            resp = client.delete(f"/api/v1/flows/{flow_id}/annotations/{ann['id']}")
        assert resp.status_code == 401
