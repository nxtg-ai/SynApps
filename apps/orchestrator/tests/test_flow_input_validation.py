"""
N-182: Flow Input Validation Rules — PUT/GET/DELETE /flows/{id}/input-validation

Tests:
  - PUT sets validation; returns 200
  - PUT response shape (flow_id, rules, strict, rule_count, updated_at)
  - PUT with rules list stored
  - PUT with strict=True stored
  - PUT with strict=False stored
  - PUT empty rules list allowed
  - PUT too many rules → 422
  - PUT replaces existing validation
  - PUT 404 for unknown flow
  - PUT requires auth
  - GET returns validation after PUT
  - GET rule_count matches rules list length
  - GET 404 when no validation set
  - GET 404 for unknown flow
  - GET requires auth
  - DELETE removes validation; returns {deleted: true, flow_id}
  - DELETE 404 when no validation
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
        json={"email": f"inval-{uid}@test.com", "password": "pass1234"},
    )
    assert r.status_code == 201
    return r.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_flow(client: TestClient, token: str) -> str:
    resp = client.post(
        "/api/v1/flows",
        json={"name": "Input Validation Test Flow", "nodes": [], "edges": []},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _set_validation(
    client: TestClient,
    token: str,
    flow_id: str,
    rules: list | None = None,
    strict: bool = False,
) -> dict:
    resp = client.put(
        f"/api/v1/flows/{flow_id}/input-validation",
        json={"rules": rules or [], "strict": strict},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    return resp.json()


# ---------------------------------------------------------------------------
# Tests — PUT /flows/{id}/input-validation
# ---------------------------------------------------------------------------


class TestFlowInputValidationPut:
    def test_put_returns_200(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/input-validation",
                json={"rules": [], "strict": False},
                headers=_auth(token),
            )
        assert resp.status_code == 200

    def test_put_response_shape(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/input-validation",
                json={"rules": [{"field": "name", "type": "string"}], "strict": True},
                headers=_auth(token),
            )
        data = resp.json()
        assert data["flow_id"] == flow_id
        assert "rules" in data
        assert "strict" in data
        assert "rule_count" in data
        assert "updated_at" in data

    def test_put_stores_rules(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            rules = [{"field": "age", "type": "integer", "min": 0}]
            resp = client.put(
                f"/api/v1/flows/{flow_id}/input-validation",
                json={"rules": rules},
                headers=_auth(token),
            )
        assert len(resp.json()["rules"]) == 1
        assert resp.json()["rules"][0]["field"] == "age"

    def test_put_strict_true(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/input-validation",
                json={"rules": [], "strict": True},
                headers=_auth(token),
            )
        assert resp.json()["strict"] is True

    def test_put_strict_false(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/input-validation",
                json={"rules": [], "strict": False},
                headers=_auth(token),
            )
        assert resp.json()["strict"] is False

    def test_put_empty_rules_allowed(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/input-validation",
                json={"rules": []},
                headers=_auth(token),
            )
        assert resp.status_code == 200
        assert resp.json()["rule_count"] == 0

    def test_put_too_many_rules_422(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/input-validation",
                json={"rules": [{"field": f"f{i}"} for i in range(51)]},
                headers=_auth(token),
            )
        assert resp.status_code == 422

    def test_put_replaces_existing(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_validation(client, token, flow_id, [{"field": "old"}])
            resp = client.put(
                f"/api/v1/flows/{flow_id}/input-validation",
                json={"rules": [{"field": "new1"}, {"field": "new2"}]},
                headers=_auth(token),
            )
        assert resp.json()["rule_count"] == 2

    def test_put_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.put(
                "/api/v1/flows/nonexistent/input-validation",
                json={"rules": []},
                headers=_auth(token),
            )
        assert resp.status_code == 404

    def test_put_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/input-validation",
                json={"rules": []},
            )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Tests — GET /flows/{id}/input-validation
# ---------------------------------------------------------------------------


class TestFlowInputValidationGet:
    def test_get_returns_validation_after_put(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_validation(client, token, flow_id, [{"field": "x"}], strict=True)
            resp = client.get(
                f"/api/v1/flows/{flow_id}/input-validation", headers=_auth(token)
            )
        assert resp.status_code == 200
        assert resp.json()["strict"] is True

    def test_get_rule_count_matches(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_validation(client, token, flow_id, [{"f": 1}, {"f": 2}, {"f": 3}])
            resp = client.get(
                f"/api/v1/flows/{flow_id}/input-validation", headers=_auth(token)
            )
        assert resp.json()["rule_count"] == 3
        assert len(resp.json()["rules"]) == 3  # Gate 2: non-empty check

    def test_get_404_when_no_validation(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(
                f"/api/v1/flows/{flow_id}/input-validation", headers=_auth(token)
            )
        assert resp.status_code == 404

    def test_get_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get(
                "/api/v1/flows/nonexistent/input-validation", headers=_auth(token)
            )
        assert resp.status_code == 404

    def test_get_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_validation(client, token, flow_id)
            resp = client.get(f"/api/v1/flows/{flow_id}/input-validation")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Tests — DELETE /flows/{id}/input-validation
# ---------------------------------------------------------------------------


class TestFlowInputValidationDelete:
    def test_delete_removes_validation(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_validation(client, token, flow_id)
            resp = client.delete(
                f"/api/v1/flows/{flow_id}/input-validation", headers=_auth(token)
            )
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True
        assert resp.json()["flow_id"] == flow_id

    def test_get_404_after_delete(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_validation(client, token, flow_id)
            client.delete(f"/api/v1/flows/{flow_id}/input-validation", headers=_auth(token))
            resp = client.get(
                f"/api/v1/flows/{flow_id}/input-validation", headers=_auth(token)
            )
        assert resp.status_code == 404

    def test_delete_404_when_no_validation(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.delete(
                f"/api/v1/flows/{flow_id}/input-validation", headers=_auth(token)
            )
        assert resp.status_code == 404

    def test_delete_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.delete(
                "/api/v1/flows/nonexistent/input-validation", headers=_auth(token)
            )
        assert resp.status_code == 404

    def test_delete_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_validation(client, token, flow_id)
            resp = client.delete(f"/api/v1/flows/{flow_id}/input-validation")
        assert resp.status_code == 401
