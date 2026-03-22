"""
N-189: Flow Data Classification — PUT/GET/DELETE /flows/{id}/data-classification

Tests:
  - PUT sets classification; returns 200
  - PUT response shape (flow_id, level, pii_flag, updated_at)
  - PUT level "public" stored
  - PUT level "internal" stored
  - PUT level "confidential" stored
  - PUT level "restricted" stored
  - PUT invalid level → 422
  - PUT pii_flag=True stored
  - PUT pii_flag=False stored (default)
  - PUT replaces existing
  - PUT 404 for unknown flow
  - PUT requires auth
  - GET returns classification after PUT
  - GET 404 when none set
  - GET 404 for unknown flow
  - GET requires auth
  - DELETE removes classification; returns {deleted: true, flow_id}
  - DELETE 404 when none set
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
        json={"email": f"dc-{uid}@test.com", "password": "pass1234"},
    )
    assert r.status_code == 201
    return r.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_flow(client: TestClient, token: str) -> str:
    resp = client.post(
        "/api/v1/flows",
        json={"name": "Data Classification Test Flow", "nodes": [], "edges": []},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _set_classification(
    client: TestClient,
    token: str,
    flow_id: str,
    level: str = "internal",
    pii_flag: bool = False,
) -> dict:
    resp = client.put(
        f"/api/v1/flows/{flow_id}/data-classification",
        json={"level": level, "pii_flag": pii_flag},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    return resp.json()


# ---------------------------------------------------------------------------
# Tests — PUT /flows/{id}/data-classification
# ---------------------------------------------------------------------------


class TestFlowDataClassificationPut:
    def test_put_returns_200(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/data-classification",
                json={"level": "public"},
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
                f"/api/v1/flows/{flow_id}/data-classification",
                json={"level": "internal"},
                headers=_auth(token),
            )
        data = resp.json()
        assert data["flow_id"] == flow_id
        assert "level" in data
        assert "pii_flag" in data
        assert "updated_at" in data

    def test_put_level_public(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/data-classification",
                json={"level": "public"},
                headers=_auth(token),
            )
        assert resp.json()["level"] == "public"

    def test_put_level_internal(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/data-classification",
                json={"level": "internal"},
                headers=_auth(token),
            )
        assert resp.json()["level"] == "internal"

    def test_put_level_confidential(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/data-classification",
                json={"level": "confidential"},
                headers=_auth(token),
            )
        assert resp.json()["level"] == "confidential"

    def test_put_level_restricted(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/data-classification",
                json={"level": "restricted"},
                headers=_auth(token),
            )
        assert resp.json()["level"] == "restricted"

    def test_put_invalid_level_422(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/data-classification",
                json={"level": "top-secret"},
                headers=_auth(token),
            )
        assert resp.status_code == 422
        assert "error" in resp.json()

    def test_put_pii_flag_true(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/data-classification",
                json={"level": "confidential", "pii_flag": True},
                headers=_auth(token),
            )
        assert resp.json()["pii_flag"] is True

    def test_put_pii_flag_false_default(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/data-classification",
                json={"level": "public"},
                headers=_auth(token),
            )
        assert resp.json()["pii_flag"] is False

    def test_put_replaces_existing(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_classification(client, token, flow_id, level="public")
            resp = client.put(
                f"/api/v1/flows/{flow_id}/data-classification",
                json={"level": "restricted", "pii_flag": True},
                headers=_auth(token),
            )
        assert resp.json()["level"] == "restricted"
        assert resp.json()["pii_flag"] is True

    def test_put_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.put(
                "/api/v1/flows/nonexistent/data-classification",
                json={"level": "public"},
                headers=_auth(token),
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_put_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/data-classification",
                json={"level": "public"},
            )
        assert resp.status_code == 401
        assert "error" in resp.json()


# ---------------------------------------------------------------------------
# Tests — GET /flows/{id}/data-classification
# ---------------------------------------------------------------------------


class TestFlowDataClassificationGet:
    def test_get_returns_classification_after_put(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_classification(client, token, flow_id, level="restricted", pii_flag=True)
            resp = client.get(
                f"/api/v1/flows/{flow_id}/data-classification", headers=_auth(token)
            )
        assert resp.status_code == 200
        assert resp.json()["level"] == "restricted"
        assert resp.json()["pii_flag"] is True

    def test_get_404_when_none_set(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(
                f"/api/v1/flows/{flow_id}/data-classification", headers=_auth(token)
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_get_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get(
                "/api/v1/flows/nonexistent/data-classification", headers=_auth(token)
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_get_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_classification(client, token, flow_id)
            resp = client.get(f"/api/v1/flows/{flow_id}/data-classification")
        assert resp.status_code == 401
        assert "error" in resp.json()


# ---------------------------------------------------------------------------
# Tests — DELETE /flows/{id}/data-classification
# ---------------------------------------------------------------------------


class TestFlowDataClassificationDelete:
    def test_delete_removes_classification(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_classification(client, token, flow_id)
            resp = client.delete(
                f"/api/v1/flows/{flow_id}/data-classification", headers=_auth(token)
            )
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True
        assert resp.json()["flow_id"] == flow_id

    def test_get_404_after_delete(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_classification(client, token, flow_id)
            client.delete(
                f"/api/v1/flows/{flow_id}/data-classification", headers=_auth(token)
            )
            resp = client.get(
                f"/api/v1/flows/{flow_id}/data-classification", headers=_auth(token)
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_delete_404_when_none_set(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.delete(
                f"/api/v1/flows/{flow_id}/data-classification", headers=_auth(token)
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_delete_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.delete(
                "/api/v1/flows/nonexistent/data-classification", headers=_auth(token)
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_delete_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_classification(client, token, flow_id)
            resp = client.delete(f"/api/v1/flows/{flow_id}/data-classification")
        assert resp.status_code == 401
        assert "error" in resp.json()
