"""
N-177: Flow Error Alert Recipients — PUT/GET/DELETE /flows/{id}/error-alerts

Tests:
  - PUT sets alert config; returns 200
  - PUT response shape (flow_id, emails, slack_channels, updated_at)
  - PUT with email list stores correctly
  - PUT with slack_channels stores correctly
  - PUT with both emails and slack_channels
  - PUT with empty lists stores empty
  - PUT too many emails → 422
  - PUT too many slack_channels → 422
  - PUT replaces existing config
  - PUT 404 for unknown flow
  - PUT requires auth
  - GET returns config after PUT
  - GET 404 when no config
  - GET 404 for unknown flow
  - GET requires auth
  - DELETE removes config; returns {deleted: true, flow_id}
  - DELETE 404 when no config
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
        json={"email": f"ealert-{uid}@test.com", "password": "pass1234"},
    )
    assert r.status_code == 201
    return r.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_flow(client: TestClient, token: str) -> str:
    resp = client.post(
        "/api/v1/flows",
        json={"name": "Error Alert Test Flow", "nodes": [], "edges": []},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _set_alerts(
    client: TestClient,
    token: str,
    flow_id: str,
    emails: list | None = None,
    slack_channels: list | None = None,
) -> dict:
    resp = client.put(
        f"/api/v1/flows/{flow_id}/error-alerts",
        json={"emails": emails or [], "slack_channels": slack_channels or []},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    return resp.json()


# ---------------------------------------------------------------------------
# Tests — PUT /flows/{id}/error-alerts
# ---------------------------------------------------------------------------


class TestFlowErrorAlertsPut:
    def test_put_returns_200(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/error-alerts",
                json={"emails": ["ops@example.com"]},
                headers=_auth(token),
            )
        assert resp.status_code == 200

    def test_put_response_shape(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/error-alerts",
                json={"emails": [], "slack_channels": []},
                headers=_auth(token),
            )
        data = resp.json()
        assert data["flow_id"] == flow_id
        assert "emails" in data
        assert "slack_channels" in data
        assert "updated_at" in data

    def test_put_stores_emails(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/error-alerts",
                json={"emails": ["a@test.com", "b@test.com"]},
                headers=_auth(token),
            )
        assert resp.json()["emails"] == ["a@test.com", "b@test.com"]

    def test_put_stores_slack_channels(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/error-alerts",
                json={"slack_channels": ["#alerts", "#ops"]},
                headers=_auth(token),
            )
        assert resp.json()["slack_channels"] == ["#alerts", "#ops"]

    def test_put_both_emails_and_slack(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/error-alerts",
                json={"emails": ["team@co.com"], "slack_channels": ["#dev"]},
                headers=_auth(token),
            )
        data = resp.json()
        assert len(data["emails"]) == 1
        assert len(data["slack_channels"]) == 1

    def test_put_empty_lists(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/error-alerts",
                json={"emails": [], "slack_channels": []},
                headers=_auth(token),
            )
        assert resp.json()["emails"] == []
        assert resp.json()["slack_channels"] == []

    def test_put_too_many_emails_422(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/error-alerts",
                json={"emails": [f"e{i}@test.com" for i in range(21)]},
                headers=_auth(token),
            )
        assert resp.status_code == 422

    def test_put_too_many_slack_channels_422(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/error-alerts",
                json={"slack_channels": [f"#ch{i}" for i in range(21)]},
                headers=_auth(token),
            )
        assert resp.status_code == 422

    def test_put_replaces_existing(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_alerts(client, token, flow_id, emails=["old@test.com"])
            resp = client.put(
                f"/api/v1/flows/{flow_id}/error-alerts",
                json={"emails": ["new@test.com"]},
                headers=_auth(token),
            )
        assert resp.json()["emails"] == ["new@test.com"]

    def test_put_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.put(
                "/api/v1/flows/nonexistent/error-alerts",
                json={"emails": []},
                headers=_auth(token),
            )
        assert resp.status_code == 404

    def test_put_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.put(
                f"/api/v1/flows/{flow_id}/error-alerts",
                json={"emails": []},
            )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Tests — GET /flows/{id}/error-alerts
# ---------------------------------------------------------------------------


class TestFlowErrorAlertsGet:
    def test_get_returns_config_after_put(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_alerts(client, token, flow_id, emails=["check@test.com"])
            resp = client.get(f"/api/v1/flows/{flow_id}/error-alerts", headers=_auth(token))
        assert resp.status_code == 200
        assert "check@test.com" in resp.json()["emails"]

    def test_get_404_when_no_config(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/error-alerts", headers=_auth(token))
        assert resp.status_code == 404

    def test_get_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get("/api/v1/flows/nonexistent/error-alerts", headers=_auth(token))
        assert resp.status_code == 404

    def test_get_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_alerts(client, token, flow_id)
            resp = client.get(f"/api/v1/flows/{flow_id}/error-alerts")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Tests — DELETE /flows/{id}/error-alerts
# ---------------------------------------------------------------------------


class TestFlowErrorAlertsDelete:
    def test_delete_removes_config(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_alerts(client, token, flow_id)
            resp = client.delete(f"/api/v1/flows/{flow_id}/error-alerts", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True
        assert resp.json()["flow_id"] == flow_id

    def test_get_404_after_delete(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_alerts(client, token, flow_id)
            client.delete(f"/api/v1/flows/{flow_id}/error-alerts", headers=_auth(token))
            resp = client.get(f"/api/v1/flows/{flow_id}/error-alerts", headers=_auth(token))
        assert resp.status_code == 404

    def test_delete_404_when_no_config(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.delete(f"/api/v1/flows/{flow_id}/error-alerts", headers=_auth(token))
        assert resp.status_code == 404

    def test_delete_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.delete(
                "/api/v1/flows/nonexistent/error-alerts", headers=_auth(token)
            )
        assert resp.status_code == 404

    def test_delete_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _set_alerts(client, token, flow_id)
            resp = client.delete(f"/api/v1/flows/{flow_id}/error-alerts")
        assert resp.status_code == 401
