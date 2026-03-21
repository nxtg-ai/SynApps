"""
N-171: Flow Cost Estimate Config — PUT/GET/DELETE /flows/{id}/cost-config

Tests:
  - PUT creates cost config; returns 200
  - PUT response shape (flow_id, cost_per_run, currency, billing_note, updated_at)
  - PUT response includes allowed_currencies
  - PUT cost_per_run=0.0 succeeds
  - PUT with billing_note succeeds
  - PUT invalid currency → 422
  - PUT negative cost_per_run → 422
  - PUT replaces existing config
  - PUT 404 for unknown flow
  - PUT requires auth
  - GET returns config after PUT
  - GET response includes allowed_currencies
  - GET 404 when no config set
  - GET 404 for unknown flow
  - GET requires auth
  - DELETE removes config; returns {deleted: true, flow_id}
  - DELETE 404 when no config set
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
        json={"email": f"cost-{uid}@test.com", "password": "pass1234"},
    )
    assert r.status_code == 201
    return r.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_flow(client: TestClient, token: str) -> str:
    resp = client.post(
        "/api/v1/flows",
        json={"name": "Cost Config Test Flow", "nodes": [], "edges": []},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _set_cost_config(
    client: TestClient,
    token: str,
    flow_id: str,
    cost_per_run: float = 0.05,
    currency: str = "USD",
    billing_note: str = "",
) -> dict:
    resp = client.put(
        f"/api/v1/flows/{flow_id}/cost-config",
        json={
            "cost_per_run": cost_per_run,
            "currency": currency,
            "billing_note": billing_note,
        },
        headers=_auth(token),
    )
    assert resp.status_code == 200
    return resp.json()


# ---------------------------------------------------------------------------
# Tests — PUT /flows/{id}/cost-config
# ---------------------------------------------------------------------------


class TestFlowCostConfigPut:
    def test_put_returns_200(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/cost-config",
                json={"cost_per_run": 0.10, "currency": "USD"},
                headers=_auth(token),
            )
        assert resp.status_code == 200

    def test_put_response_shape(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/cost-config",
                json={"cost_per_run": 1.25, "currency": "EUR", "billing_note": "LLM cost only"},
                headers=_auth(token),
            )
        data = resp.json()
        assert data["flow_id"] == flow_id
        assert data["cost_per_run"] == 1.25
        assert data["currency"] == "EUR"
        assert data["billing_note"] == "LLM cost only"
        assert "updated_at" in data

    def test_put_response_includes_allowed_currencies(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/cost-config",
                json={"cost_per_run": 0.0, "currency": "USD"},
                headers=_auth(token),
            )
        assert len(resp.json()["allowed_currencies"]) == 6

    def test_put_zero_cost_succeeds(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/cost-config",
                json={"cost_per_run": 0.0, "currency": "GBP"},
                headers=_auth(token),
            )
        assert resp.status_code == 200
        assert resp.json()["cost_per_run"] == 0.0

    def test_put_with_billing_note(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/cost-config",
                json={"cost_per_run": 0.5, "currency": "USD", "billing_note": "Includes GPU time"},
                headers=_auth(token),
            )
        assert resp.json()["billing_note"] == "Includes GPU time"

    def test_put_invalid_currency_422(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/cost-config",
                json={"cost_per_run": 1.0, "currency": "BTC"},
                headers=_auth(token),
            )
        assert resp.status_code == 422

    def test_put_negative_cost_422(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/cost-config",
                json={"cost_per_run": -0.01, "currency": "USD"},
                headers=_auth(token),
            )
        assert resp.status_code == 422

    def test_put_replaces_existing(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_cost_config(client, token, flow_id, cost_per_run=0.01, currency="USD")
            resp = client.put(
                f"/api/v1/flows/{flow_id}/cost-config",
                json={"cost_per_run": 5.0, "currency": "JPY"},
                headers=_auth(token),
            )
        assert resp.json()["currency"] == "JPY"
        assert resp.json()["cost_per_run"] == 5.0

    def test_put_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.put(
                "/api/v1/flows/nonexistent/cost-config",
                json={"cost_per_run": 1.0, "currency": "USD"},
                headers=_auth(token),
            )
        assert resp.status_code == 404

    def test_put_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/cost-config",
                json={"cost_per_run": 1.0, "currency": "USD"},
            )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Tests — GET /flows/{id}/cost-config
# ---------------------------------------------------------------------------


class TestFlowCostConfigGet:
    def test_get_returns_config_after_put(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_cost_config(client, token, flow_id, cost_per_run=2.50, currency="AUD")
            resp = client.get(f"/api/v1/flows/{flow_id}/cost-config", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["cost_per_run"] == 2.50
        assert resp.json()["currency"] == "AUD"

    def test_get_includes_allowed_currencies(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_cost_config(client, token, flow_id)
            resp = client.get(f"/api/v1/flows/{flow_id}/cost-config", headers=_auth(token))
        assert "allowed_currencies" in resp.json()

    def test_get_404_when_no_config(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/cost-config", headers=_auth(token))
        assert resp.status_code == 404

    def test_get_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get("/api/v1/flows/nonexistent/cost-config", headers=_auth(token))
        assert resp.status_code == 404

    def test_get_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_cost_config(client, token, flow_id)
            resp = client.get(f"/api/v1/flows/{flow_id}/cost-config")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Tests — DELETE /flows/{id}/cost-config
# ---------------------------------------------------------------------------


class TestFlowCostConfigDelete:
    def test_delete_removes_config(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_cost_config(client, token, flow_id)
            resp = client.delete(f"/api/v1/flows/{flow_id}/cost-config", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True
        assert resp.json()["flow_id"] == flow_id

    def test_get_404_after_delete(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_cost_config(client, token, flow_id)
            client.delete(f"/api/v1/flows/{flow_id}/cost-config", headers=_auth(token))
            resp = client.get(f"/api/v1/flows/{flow_id}/cost-config", headers=_auth(token))
        assert resp.status_code == 404

    def test_delete_404_when_no_config(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.delete(f"/api/v1/flows/{flow_id}/cost-config", headers=_auth(token))
        assert resp.status_code == 404

    def test_delete_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_cost_config(client, token, flow_id)
            resp = client.delete(f"/api/v1/flows/{flow_id}/cost-config")
        assert resp.status_code == 401
