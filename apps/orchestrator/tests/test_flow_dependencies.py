"""
N-155: Flow Dependencies — POST/GET /flows/{id}/dependencies
                            GET /flows/{id}/dependents
                            DELETE /flows/{id}/dependencies/{dep_id}

Tests:
  - POST adds dependency; returns 201
  - POST response shape (id, from_flow_id, to_flow_id, label, created_at)
  - GET /dependencies returns empty list on fresh flow
  - GET /dependencies lists dependencies after add
  - GET /dependents shows reverse lookup
  - POST duplicate dependency → 409
  - POST cycle detection → 409 (A→B when B→A exists)
  - POST self-loop → 422
  - POST dep flow not found → 404
  - DELETE removes dependency
  - DELETE 404 for unknown dep_id
  - POST/GET 404 for unknown flow
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
        json={"email": f"dep-{uid}@test.com", "password": "pass1234"},
    )
    assert r.status_code == 201
    return r.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_flow(client: TestClient, token: str) -> str:
    resp = client.post(
        "/api/v1/flows",
        json={"name": "Dep Test Flow", "nodes": [], "edges": []},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _add_dep(
    client: TestClient,
    token: str,
    from_id: str,
    to_id: str,
    label: str = "",
) -> dict:
    resp = client.post(
        f"/api/v1/flows/{from_id}/dependencies",
        json={"to_flow_id": to_id, "label": label},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    return resp.json()


# ---------------------------------------------------------------------------
# Tests — POST /flows/{id}/dependencies
# ---------------------------------------------------------------------------


class TestFlowDependencyPost:
    def test_post_returns_201(self):
        with TestClient(app) as client:
            token = _register(client)
            f1 = _create_flow(client, token)
            f2 = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{f1}/dependencies",
                json={"to_flow_id": f2},
                headers=_auth(token),
            )
        assert resp.status_code == 201

    def test_post_response_shape(self):
        with TestClient(app) as client:
            token = _register(client)
            f1 = _create_flow(client, token)
            f2 = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{f1}/dependencies",
                json={"to_flow_id": f2, "label": "uses data"},
                headers=_auth(token),
            )
        data = resp.json()
        assert "id" in data
        assert data["from_flow_id"] == f1
        assert data["to_flow_id"] == f2
        assert data["label"] == "uses data"
        assert "created_at" in data

    def test_post_duplicate_409(self):
        with TestClient(app) as client:
            token = _register(client)
            f1 = _create_flow(client, token)
            f2 = _create_flow(client, token)
            _add_dep(client, token, f1, f2)
            resp = client.post(
                f"/api/v1/flows/{f1}/dependencies",
                json={"to_flow_id": f2},
                headers=_auth(token),
            )
        assert resp.status_code == 409

    def test_post_cycle_detection_409(self):
        """A→B then B→A should be rejected as a cycle."""
        with TestClient(app) as client:
            token = _register(client)
            f1 = _create_flow(client, token)
            f2 = _create_flow(client, token)
            _add_dep(client, token, f1, f2)  # A→B
            resp = client.post(
                f"/api/v1/flows/{f2}/dependencies",
                json={"to_flow_id": f1},  # B→A — cycle!
                headers=_auth(token),
            )
        assert resp.status_code == 409

    def test_post_transitive_cycle_409(self):
        """A→B→C then C→A should be rejected."""
        with TestClient(app) as client:
            token = _register(client)
            f1 = _create_flow(client, token)
            f2 = _create_flow(client, token)
            f3 = _create_flow(client, token)
            _add_dep(client, token, f1, f2)  # A→B
            _add_dep(client, token, f2, f3)  # B→C
            resp = client.post(
                f"/api/v1/flows/{f3}/dependencies",
                json={"to_flow_id": f1},  # C→A — cycle!
                headers=_auth(token),
            )
        assert resp.status_code == 409

    def test_post_self_loop_422(self):
        with TestClient(app) as client:
            token = _register(client)
            f1 = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{f1}/dependencies",
                json={"to_flow_id": f1},
                headers=_auth(token),
            )
        assert resp.status_code == 422

    def test_post_dep_flow_not_found_404(self):
        with TestClient(app) as client:
            token = _register(client)
            f1 = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{f1}/dependencies",
                json={"to_flow_id": "nonexistent"},
                headers=_auth(token),
            )
        assert resp.status_code == 404

    def test_post_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            f2 = _create_flow(client, token)
            resp = client.post(
                "/api/v1/flows/nonexistent/dependencies",
                json={"to_flow_id": f2},
                headers=_auth(token),
            )
        assert resp.status_code == 404

    def test_post_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            f1 = _create_flow(client, token)
            f2 = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{f1}/dependencies",
                json={"to_flow_id": f2},
            )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Tests — GET /flows/{id}/dependencies
# ---------------------------------------------------------------------------


class TestFlowDependencyList:
    def test_get_empty_on_fresh_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            f1 = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{f1}/dependencies", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["items"] == []

    def test_get_lists_dependencies(self):
        with TestClient(app) as client:
            token = _register(client)
            f1 = _create_flow(client, token)
            f2 = _create_flow(client, token)
            f3 = _create_flow(client, token)
            _add_dep(client, token, f1, f2)
            _add_dep(client, token, f1, f3)
            resp = client.get(f"/api/v1/flows/{f1}/dependencies", headers=_auth(token))
        items = resp.json()["items"]
        assert len(items) == 2
        targets = {e["to_flow_id"] for e in items}
        assert targets == {f2, f3}

    def test_get_flow_id_in_response(self):
        with TestClient(app) as client:
            token = _register(client)
            f1 = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{f1}/dependencies", headers=_auth(token))
        assert resp.json()["flow_id"] == f1

    def test_get_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get("/api/v1/flows/nonexistent/dependencies", headers=_auth(token))
        assert resp.status_code == 404

    def test_get_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            f1 = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{f1}/dependencies")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Tests — GET /flows/{id}/dependents
# ---------------------------------------------------------------------------


class TestFlowDependentsList:
    def test_get_dependents_empty_on_fresh_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            f1 = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{f1}/dependents", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["items"] == []

    def test_get_dependents_shows_incoming(self):
        """f2 depends on f1 → f1's dependents includes f2."""
        with TestClient(app) as client:
            token = _register(client)
            f1 = _create_flow(client, token)
            f2 = _create_flow(client, token)
            _add_dep(client, token, f2, f1)  # f2 → f1
            resp = client.get(f"/api/v1/flows/{f1}/dependents", headers=_auth(token))
        items = resp.json()["items"]
        assert len(items) == 1
        assert items[0]["from_flow_id"] == f2

    def test_get_dependents_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get("/api/v1/flows/nonexistent/dependents", headers=_auth(token))
        assert resp.status_code == 404

    def test_get_dependents_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            f1 = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{f1}/dependents")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Tests — DELETE /flows/{id}/dependencies/{dep_id}
# ---------------------------------------------------------------------------


class TestFlowDependencyDelete:
    def test_delete_removes_dependency(self):
        with TestClient(app) as client:
            token = _register(client)
            f1 = _create_flow(client, token)
            f2 = _create_flow(client, token)
            dep = _add_dep(client, token, f1, f2)
            resp = client.delete(
                f"/api/v1/flows/{f1}/dependencies/{dep['id']}", headers=_auth(token)
            )
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True

    def test_get_after_delete_shows_empty(self):
        with TestClient(app) as client:
            token = _register(client)
            f1 = _create_flow(client, token)
            f2 = _create_flow(client, token)
            dep = _add_dep(client, token, f1, f2)
            client.delete(
                f"/api/v1/flows/{f1}/dependencies/{dep['id']}", headers=_auth(token)
            )
            resp = client.get(f"/api/v1/flows/{f1}/dependencies", headers=_auth(token))
        assert resp.json()["items"] == []

    def test_delete_allows_re_add_after_removal(self):
        """After removing A→B, adding A→B again should succeed."""
        with TestClient(app) as client:
            token = _register(client)
            f1 = _create_flow(client, token)
            f2 = _create_flow(client, token)
            dep = _add_dep(client, token, f1, f2)
            client.delete(
                f"/api/v1/flows/{f1}/dependencies/{dep['id']}", headers=_auth(token)
            )
            resp = client.post(
                f"/api/v1/flows/{f1}/dependencies",
                json={"to_flow_id": f2},
                headers=_auth(token),
            )
        assert resp.status_code == 201

    def test_delete_404_unknown_dep(self):
        with TestClient(app) as client:
            token = _register(client)
            f1 = _create_flow(client, token)
            resp = client.delete(
                f"/api/v1/flows/{f1}/dependencies/nonexistent", headers=_auth(token)
            )
        assert resp.status_code == 404

    def test_delete_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.delete(
                "/api/v1/flows/nonexistent/dependencies/any-id", headers=_auth(token)
            )
        assert resp.status_code == 404

    def test_delete_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            f1 = _create_flow(client, token)
            f2 = _create_flow(client, token)
            dep = _add_dep(client, token, f1, f2)
            resp = client.delete(f"/api/v1/flows/{f1}/dependencies/{dep['id']}")
        assert resp.status_code == 401
