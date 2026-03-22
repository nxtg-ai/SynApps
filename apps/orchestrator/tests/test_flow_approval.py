"""
N-174: Flow Approval Workflow — POST/GET/DELETE /flows/{id}/approval/...

Tests:
  - POST /approval/request returns 200 with pending status
  - POST /approval/request response shape (flow_id, status, submitted_by, note, requested_at)
  - POST /approval/request with note
  - POST /approval/request without note defaults empty
  - POST /approval/request note too long → 422
  - POST /approval/request 404 unknown flow
  - POST /approval/request requires auth
  - POST /approval/approve returns 200 with approved status
  - POST /approval/approve response has reviewer field
  - POST /approval/approve 404 when no approval pending
  - POST /approval/approve 404 unknown flow
  - POST /approval/approve requires auth
  - POST /approval/reject returns 200 with rejected status
  - POST /approval/reject response has review_comment
  - POST /approval/reject 404 when no approval pending
  - POST /approval/reject 404 unknown flow
  - POST /approval/reject requires auth
  - GET /approval returns approval record
  - GET /approval 404 when no record
  - GET /approval 404 unknown flow
  - GET /approval requires auth
  - DELETE /approval removes record; returns {deleted: true, flow_id}
  - DELETE /approval 404 when no record
  - DELETE /approval 404 unknown flow
  - DELETE /approval requires auth
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
        json={"email": f"appr-{uid}@test.com", "password": "pass1234"},
    )
    assert r.status_code == 201
    return r.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_flow(client: TestClient, token: str) -> str:
    resp = client.post(
        "/api/v1/flows",
        json={"name": "Approval Test Flow", "nodes": [], "edges": []},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _request_approval(
    client: TestClient, token: str, flow_id: str, note: str = ""
) -> dict:
    resp = client.post(
        f"/api/v1/flows/{flow_id}/approval/request",
        json={"note": note},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    return resp.json()


# ---------------------------------------------------------------------------
# Tests — POST /flows/{id}/approval/request
# ---------------------------------------------------------------------------


class TestFlowApprovalRequest:
    def test_request_returns_200(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/approval/request",
                json={"note": "Ready for review"},
                headers=_auth(token),
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["flow_id"] == flow_id

    def test_request_status_is_pending(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/approval/request",
                json={},
                headers=_auth(token),
            )
        assert resp.json()["status"] == "pending"

    def test_request_response_shape(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/approval/request",
                json={"note": "Ship it"},
                headers=_auth(token),
            )
        data = resp.json()
        assert data["flow_id"] == flow_id
        assert data["status"] == "pending"
        assert "submitted_by" in data
        assert data["note"] == "Ship it"
        assert "requested_at" in data

    def test_request_with_note(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/approval/request",
                json={"note": "Production ready"},
                headers=_auth(token),
            )
        assert resp.json()["note"] == "Production ready"

    def test_request_without_note_defaults_empty(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/approval/request",
                json={},
                headers=_auth(token),
            )
        assert resp.json()["note"] == ""

    def test_request_note_too_long_422(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/approval/request",
                json={"note": "x" * 501},
                headers=_auth(token),
            )
        assert resp.status_code == 422
        assert "error" in resp.json()

    def test_request_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.post(
                "/api/v1/flows/nonexistent/approval/request",
                json={},
                headers=_auth(token),
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_request_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/approval/request",
                json={},
            )
        assert resp.status_code == 401
        assert "error" in resp.json()


# ---------------------------------------------------------------------------
# Tests — POST /flows/{id}/approval/approve
# ---------------------------------------------------------------------------


class TestFlowApprovalApprove:
    def test_approve_returns_200(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _request_approval(client, token, flow_id)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/approval/approve",
                json={"comment": "LGTM"},
                headers=_auth(token),
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["flow_id"] == flow_id

    def test_approve_status_is_approved(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _request_approval(client, token, flow_id)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/approval/approve",
                json={},
                headers=_auth(token),
            )
        assert resp.json()["status"] == "approved"

    def test_approve_response_has_reviewer(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _request_approval(client, token, flow_id)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/approval/approve",
                json={"comment": "Approved!"},
                headers=_auth(token),
            )
        data = resp.json()
        assert "@" in data["reviewer"]
        assert data["review_comment"] == "Approved!"
        assert "reviewed_at" in data

    def test_approve_404_when_no_approval(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/approval/approve",
                json={},
                headers=_auth(token),
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_approve_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.post(
                "/api/v1/flows/nonexistent/approval/approve",
                json={},
                headers=_auth(token),
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_approve_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _request_approval(client, token, flow_id)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/approval/approve",
                json={},
            )
        assert resp.status_code == 401
        assert "error" in resp.json()


# ---------------------------------------------------------------------------
# Tests — POST /flows/{id}/approval/reject
# ---------------------------------------------------------------------------


class TestFlowApprovalReject:
    def test_reject_returns_200(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _request_approval(client, token, flow_id)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/approval/reject",
                json={"comment": "Needs more work"},
                headers=_auth(token),
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["flow_id"] == flow_id

    def test_reject_status_is_rejected(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _request_approval(client, token, flow_id)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/approval/reject",
                json={},
                headers=_auth(token),
            )
        assert resp.json()["status"] == "rejected"

    def test_reject_response_has_comment(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _request_approval(client, token, flow_id)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/approval/reject",
                json={"comment": "Fix the bugs first"},
                headers=_auth(token),
            )
        assert resp.json()["review_comment"] == "Fix the bugs first"

    def test_reject_404_when_no_approval(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/approval/reject",
                json={},
                headers=_auth(token),
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_reject_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.post(
                "/api/v1/flows/nonexistent/approval/reject",
                json={},
                headers=_auth(token),
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_reject_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _request_approval(client, token, flow_id)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/approval/reject",
                json={},
            )
        assert resp.status_code == 401
        assert "error" in resp.json()


# ---------------------------------------------------------------------------
# Tests — GET /flows/{id}/approval
# ---------------------------------------------------------------------------


class TestFlowApprovalGet:
    def test_get_returns_approval_after_request(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _request_approval(client, token, flow_id, "Check this out")
            resp = client.get(f"/api/v1/flows/{flow_id}/approval", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["note"] == "Check this out"

    def test_get_404_when_no_record(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/approval", headers=_auth(token))
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_get_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get("/api/v1/flows/nonexistent/approval", headers=_auth(token))
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_get_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _request_approval(client, token, flow_id)
            resp = client.get(f"/api/v1/flows/{flow_id}/approval")
        assert resp.status_code == 401
        assert "error" in resp.json()


# ---------------------------------------------------------------------------
# Tests — DELETE /flows/{id}/approval
# ---------------------------------------------------------------------------


class TestFlowApprovalDelete:
    def test_delete_removes_record(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _request_approval(client, token, flow_id)
            resp = client.delete(f"/api/v1/flows/{flow_id}/approval", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True
        assert resp.json()["flow_id"] == flow_id

    def test_get_404_after_delete(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _request_approval(client, token, flow_id)
            client.delete(f"/api/v1/flows/{flow_id}/approval", headers=_auth(token))
            resp = client.get(f"/api/v1/flows/{flow_id}/approval", headers=_auth(token))
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_delete_404_when_no_record(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.delete(f"/api/v1/flows/{flow_id}/approval", headers=_auth(token))
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_delete_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.delete(
                "/api/v1/flows/nonexistent/approval", headers=_auth(token)
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_delete_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _request_approval(client, token, flow_id)
            resp = client.delete(f"/api/v1/flows/{flow_id}/approval")
        assert resp.status_code == 401
        assert "error" in resp.json()
