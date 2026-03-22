"""
N-195: Flow Audit Export — POST/GET /flows/{id}/audit-export[/{job_id}]

Tests:
  - POST creates export job; returns 202
  - POST response shape (job_id, flow_id, format, from_ts, to_ts, status, created_at)
  - POST format json stored
  - POST format csv stored
  - POST invalid format → 422
  - POST from_ts and to_ts stored
  - POST without timestamps defaults None
  - POST status is pending on creation
  - POST 404 for unknown flow
  - POST requires auth
  - POST too many exports → 422
  - GET list returns exports (Gate 2)
  - GET list empty when none
  - GET list 404 unknown flow
  - GET list requires auth
  - GET single returns job
  - GET single 404 unknown job
  - GET single 404 for wrong flow
  - GET single 404 unknown flow
  - GET single requires auth
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
        json={"email": f"audexp-{uid}@test.com", "password": "pass1234"},
    )
    assert r.status_code == 201
    return r.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_flow(client: TestClient, token: str) -> str:
    resp = client.post(
        "/api/v1/flows",
        json={"name": "Audit Export Test Flow", "nodes": [], "edges": []},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _create_export(
    client: TestClient,
    token: str,
    flow_id: str,
    format: str = "json",
    from_ts: str | None = None,
    to_ts: str | None = None,
) -> dict:
    body: dict = {"format": format}
    if from_ts:
        body["from_ts"] = from_ts
    if to_ts:
        body["to_ts"] = to_ts
    resp = client.post(
        f"/api/v1/flows/{flow_id}/audit-export",
        json=body,
        headers=_auth(token),
    )
    assert resp.status_code == 202
    return resp.json()


# ---------------------------------------------------------------------------
# Tests — POST /flows/{id}/audit-export
# ---------------------------------------------------------------------------


class TestFlowAuditExportPost:
    def test_post_returns_202(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/audit-export",
                json={"format": "json"},
                headers=_auth(token),
            )
        assert resp.status_code == 202

    def test_post_response_shape(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/audit-export",
                json={"format": "json"},
                headers=_auth(token),
            )
        data = resp.json()
        assert data["flow_id"] == flow_id
        assert "job_id" in data
        assert "format" in data
        assert "from_ts" in data
        assert "to_ts" in data
        assert "status" in data
        assert "created_at" in data

    def test_post_format_json(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/audit-export",
                json={"format": "json"},
                headers=_auth(token),
            )
        assert resp.json()["format"] == "json"

    def test_post_format_csv(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/audit-export",
                json={"format": "csv"},
                headers=_auth(token),
            )
        assert resp.json()["format"] == "csv"

    def test_post_invalid_format_422(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/audit-export",
                json={"format": "xml"},
                headers=_auth(token),
            )
        assert resp.status_code == 422

    def test_post_timestamps_stored(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/audit-export",
                json={
                    "format": "json",
                    "from_ts": "2026-01-01T00:00:00Z",
                    "to_ts": "2026-03-01T00:00:00Z",
                },
                headers=_auth(token),
            )
        assert resp.json()["from_ts"] == "2026-01-01T00:00:00Z"
        assert resp.json()["to_ts"] == "2026-03-01T00:00:00Z"

    def test_post_without_timestamps_defaults_none(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/audit-export",
                json={"format": "json"},
                headers=_auth(token),
            )
        assert resp.json()["from_ts"] is None
        assert resp.json()["to_ts"] is None

    def test_post_status_is_pending(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/audit-export",
                json={"format": "json"},
                headers=_auth(token),
            )
        assert resp.json()["status"] == "pending"

    def test_post_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.post(
                "/api/v1/flows/nonexistent/audit-export",
                json={"format": "json"},
                headers=_auth(token),
            )
        assert resp.status_code == 404

    def test_post_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/audit-export",
                json={"format": "json"},
            )
        assert resp.status_code == 401

    def test_post_too_many_exports_422(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            for _ in range(20):
                _create_export(client, token, flow_id)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/audit-export",
                json={"format": "json"},
                headers=_auth(token),
            )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Tests — GET /flows/{id}/audit-export
# ---------------------------------------------------------------------------


class TestFlowAuditExportList:
    def test_list_returns_exports(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _create_export(client, token, flow_id)
            _create_export(client, token, flow_id, format="csv")
            resp = client.get(f"/api/v1/flows/{flow_id}/audit-export", headers=_auth(token))
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["exports"]) >= 1  # Gate 2

    def test_list_empty_when_none(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/audit-export", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["exports"] == []

    def test_list_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get(
                "/api/v1/flows/nonexistent/audit-export", headers=_auth(token)
            )
        assert resp.status_code == 404

    def test_list_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/audit-export")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Tests — GET /flows/{id}/audit-export/{job_id}
# ---------------------------------------------------------------------------


class TestFlowAuditExportGet:
    def test_get_returns_job(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            job = _create_export(client, token, flow_id)
            job_id = job["job_id"]
            resp = client.get(
                f"/api/v1/flows/{flow_id}/audit-export/{job_id}", headers=_auth(token)
            )
        assert resp.status_code == 200
        assert resp.json()["job_id"] == job_id

    def test_get_404_unknown_job(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(
                f"/api/v1/flows/{flow_id}/audit-export/no-such-job", headers=_auth(token)
            )
        assert resp.status_code == 404

    def test_get_404_wrong_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id_1 = _create_flow(client, token)
            flow_id_2 = _create_flow(client, token)
            job = _create_export(client, token, flow_id_1)
            job_id = job["job_id"]
            resp = client.get(
                f"/api/v1/flows/{flow_id_2}/audit-export/{job_id}", headers=_auth(token)
            )
        assert resp.status_code == 404

    def test_get_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get(
                "/api/v1/flows/nonexistent/audit-export/any-id", headers=_auth(token)
            )
        assert resp.status_code == 404

    def test_get_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            job = _create_export(client, token, flow_id)
            job_id = job["job_id"]
            resp = client.get(f"/api/v1/flows/{flow_id}/audit-export/{job_id}")
        assert resp.status_code == 401
