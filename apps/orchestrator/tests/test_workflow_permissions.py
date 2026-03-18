"""
N-29: Workflow Permissions — Team Access Control
Tests for WorkflowPermissionStore, _check_flow_permission, and all permission endpoints.
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from apps.orchestrator.main import (
    _check_flow_permission,
    app,
    workflow_permission_store,
)
from fastapi import HTTPException

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FLOW_ID = "perm-test-flow"

SAMPLE_FLOW = {
    "id": FLOW_ID,
    "name": "Permission Test Flow",
    "nodes": [
        {"id": "start", "type": "start", "position": {"x": 0, "y": 0}, "data": {}},
        {"id": "end", "type": "end", "position": {"x": 0, "y": 100}, "data": {}},
    ],
    "edges": [{"id": "e1", "source": "start", "target": "end"}],
}


@pytest.fixture(autouse=True)
def _clean():
    workflow_permission_store.reset()
    yield
    workflow_permission_store.reset()


def _register(client: TestClient, email: str | None = None) -> tuple[str, str]:
    """Register a user and return (token, user_email)."""
    email = email or f"user-{uuid.uuid4().hex[:8]}@test.com"
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "TestPass1!"},
    )
    return resp.json()["access_token"], email


# ===========================================================================
# WorkflowPermissionStore — unit
# ===========================================================================


class TestWorkflowPermissionStoreUnit:
    def test_set_owner_and_get_role(self):
        workflow_permission_store.set_owner("f1", "alice@x.com")
        assert workflow_permission_store.get_role("f1", "alice@x.com") == "owner"  # Gate 2

    def test_grant_editor(self):
        workflow_permission_store.set_owner("f1", "alice@x.com")
        workflow_permission_store.grant("f1", "bob@x.com", "editor")
        assert workflow_permission_store.get_role("f1", "bob@x.com") == "editor"  # Gate 2

    def test_grant_viewer(self):
        workflow_permission_store.set_owner("f1", "alice@x.com")
        workflow_permission_store.grant("f1", "carol@x.com", "viewer")
        assert workflow_permission_store.get_role("f1", "carol@x.com") == "viewer"  # Gate 2

    def test_revoke_removes_grant(self):
        workflow_permission_store.set_owner("f1", "alice@x.com")
        workflow_permission_store.grant("f1", "bob@x.com", "editor")
        workflow_permission_store.revoke("f1", "bob@x.com")
        assert workflow_permission_store.get_role("f1", "bob@x.com") is None  # Gate 2

    def test_no_permissions_set_returns_none(self):
        assert workflow_permission_store.get_role("no-such-flow", "alice@x.com") is None

    def test_has_flow_true_after_set_owner(self):
        workflow_permission_store.set_owner("f1", "alice@x.com")
        assert workflow_permission_store.has_flow("f1") is True  # Gate 2

    def test_has_flow_false_when_not_set(self):
        assert workflow_permission_store.has_flow("unknown") is False

    def test_get_permissions_returns_owner_and_grants(self):
        workflow_permission_store.set_owner("f1", "alice@x.com")
        workflow_permission_store.grant("f1", "bob@x.com", "viewer")
        perms = workflow_permission_store.get_permissions("f1")
        assert perms["owner"] == "alice@x.com"  # Gate 2
        assert perms["grants"]["bob@x.com"] == "viewer"  # Gate 2

    def test_reset_clears_all(self):
        workflow_permission_store.set_owner("f1", "alice@x.com")
        workflow_permission_store.reset()
        assert not workflow_permission_store.has_flow("f1")


# ===========================================================================
# _check_flow_permission helper
# ===========================================================================


class TestCheckFlowPermission:
    def test_open_flow_allows_all(self):
        # No permissions set → always passes
        _check_flow_permission("open-flow", "anyone@x.com", "owner")  # should not raise

    def test_owner_passes_all_levels(self):
        workflow_permission_store.set_owner("f1", "alice@x.com")
        _check_flow_permission("f1", "alice@x.com", "owner")
        _check_flow_permission("f1", "alice@x.com", "editor")
        _check_flow_permission("f1", "alice@x.com", "viewer")  # no raise

    def test_editor_passes_viewer_and_editor(self):
        workflow_permission_store.set_owner("f1", "alice@x.com")
        workflow_permission_store.grant("f1", "bob@x.com", "editor")
        _check_flow_permission("f1", "bob@x.com", "editor")
        _check_flow_permission("f1", "bob@x.com", "viewer")  # no raise

    def test_editor_fails_owner(self):
        workflow_permission_store.set_owner("f1", "alice@x.com")
        workflow_permission_store.grant("f1", "bob@x.com", "editor")
        with pytest.raises(HTTPException) as exc:
            _check_flow_permission("f1", "bob@x.com", "owner")
        assert exc.value.status_code == 403  # Gate 2

    def test_viewer_fails_editor(self):
        workflow_permission_store.set_owner("f1", "alice@x.com")
        workflow_permission_store.grant("f1", "carol@x.com", "viewer")
        with pytest.raises(HTTPException) as exc:
            _check_flow_permission("f1", "carol@x.com", "editor")
        assert exc.value.status_code == 403  # Gate 2

    def test_non_member_gets_403(self):
        workflow_permission_store.set_owner("f1", "alice@x.com")
        with pytest.raises(HTTPException) as exc:
            _check_flow_permission("f1", "stranger@x.com", "viewer")
        assert exc.value.status_code == 403  # Gate 2


# ===========================================================================
# Permission endpoints
# ===========================================================================


class TestPermissionEndpoints:
    def test_get_permissions_open_flow(self):
        with TestClient(app) as client:
            client.post("/api/v1/flows", json=SAMPLE_FLOW)
            token, _ = _register(client)
            resp = client.get(
                f"/api/v1/workflows/{FLOW_ID}/permissions",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["flow_id"] == FLOW_ID  # Gate 2

    def test_get_permissions_404_unknown_flow(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            resp = client.get(
                "/api/v1/workflows/nonexistent/permissions",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 404

    def test_create_flow_sets_owner(self):
        with TestClient(app) as client:
            token, email = _register(client)
            auth = {"Authorization": f"Bearer {token}"}
            resp = client.post("/api/v1/flows", json=SAMPLE_FLOW, headers=auth)
            assert resp.status_code == 201
            perms_resp = client.get(
                f"/api/v1/workflows/{FLOW_ID}/permissions",
                headers=auth,
            )
            perms = perms_resp.json()["permissions"]
            assert perms.get("owner") == email  # Gate 2: creator is owner

    def test_owner_can_share_with_editor(self):
        with TestClient(app) as client:
            owner_token, owner_email = _register(client)
            _, editor_email = _register(client)
            auth = {"Authorization": f"Bearer {owner_token}"}
            client.post("/api/v1/flows", json=SAMPLE_FLOW, headers=auth)
            resp = client.post(
                f"/api/v1/workflows/{FLOW_ID}/share",
                json={"user_id": editor_email, "role": "editor"},
                headers=auth,
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["shared_with"] == editor_email  # Gate 2
            assert body["permissions"]["grants"][editor_email] == "editor"  # Gate 2

    def test_owner_can_share_with_viewer(self):
        with TestClient(app) as client:
            owner_token, _ = _register(client)
            _, viewer_email = _register(client)
            auth = {"Authorization": f"Bearer {owner_token}"}
            client.post("/api/v1/flows", json=SAMPLE_FLOW, headers=auth)
            resp = client.post(
                f"/api/v1/workflows/{FLOW_ID}/share",
                json={"user_id": viewer_email, "role": "viewer"},
                headers=auth,
            )
            assert resp.status_code == 200
            grants = resp.json()["permissions"]["grants"]
            assert grants[viewer_email] == "viewer"  # Gate 2

    def test_invalid_role_returns_422(self):
        with TestClient(app) as client:
            owner_token, _ = _register(client)
            auth = {"Authorization": f"Bearer {owner_token}"}
            client.post("/api/v1/flows", json=SAMPLE_FLOW, headers=auth)
            resp = client.post(
                f"/api/v1/workflows/{FLOW_ID}/share",
                json={"user_id": "someone@x.com", "role": "superadmin"},
                headers=auth,
            )
            assert resp.status_code == 422

    def test_owner_can_revoke_access(self):
        with TestClient(app) as client:
            owner_token, _ = _register(client)
            _, editor_email = _register(client)
            auth = {"Authorization": f"Bearer {owner_token}"}
            client.post("/api/v1/flows", json=SAMPLE_FLOW, headers=auth)
            client.post(
                f"/api/v1/workflows/{FLOW_ID}/share",
                json={"user_id": editor_email, "role": "editor"},
                headers=auth,
            )
            resp = client.delete(
                f"/api/v1/workflows/{FLOW_ID}/share/{editor_email}",
                headers=auth,
            )
            assert resp.status_code == 200
            grants = resp.json()["permissions"]["grants"]
            assert editor_email not in grants  # Gate 2: access revoked


# ===========================================================================
# Permission enforcement on existing endpoints
# ===========================================================================


class TestPermissionEnforcement:
    def test_editor_can_update_flow(self):
        with TestClient(app) as client:
            owner_token, _ = _register(client)
            editor_token, editor_email = _register(client)
            owner_auth = {"Authorization": f"Bearer {owner_token}"}
            editor_auth = {"Authorization": f"Bearer {editor_token}"}

            client.post("/api/v1/flows", json=SAMPLE_FLOW, headers=owner_auth)
            client.post(
                f"/api/v1/workflows/{FLOW_ID}/share",
                json={"user_id": editor_email, "role": "editor"},
                headers=owner_auth,
            )

            resp = client.put(
                f"/api/v1/flows/{FLOW_ID}",
                json={"name": "Updated", "nodes": SAMPLE_FLOW["nodes"], "edges": SAMPLE_FLOW["edges"]},
                headers=editor_auth,
            )
            assert resp.status_code == 200  # Gate 2: editor can edit

    def test_viewer_cannot_update_flow(self):
        with TestClient(app) as client:
            owner_token, _ = _register(client)
            viewer_token, viewer_email = _register(client)
            owner_auth = {"Authorization": f"Bearer {owner_token}"}
            viewer_auth = {"Authorization": f"Bearer {viewer_token}"}

            client.post("/api/v1/flows", json=SAMPLE_FLOW, headers=owner_auth)
            client.post(
                f"/api/v1/workflows/{FLOW_ID}/share",
                json={"user_id": viewer_email, "role": "viewer"},
                headers=owner_auth,
            )

            resp = client.put(
                f"/api/v1/flows/{FLOW_ID}",
                json={"name": "Hacked", "nodes": SAMPLE_FLOW["nodes"], "edges": SAMPLE_FLOW["edges"]},
                headers=viewer_auth,
            )
            assert resp.status_code == 403  # Gate 2: viewer blocked

    def test_non_member_cannot_update_flow(self):
        with TestClient(app) as client:
            owner_token, _ = _register(client)
            stranger_token, _ = _register(client)
            owner_auth = {"Authorization": f"Bearer {owner_token}"}
            stranger_auth = {"Authorization": f"Bearer {stranger_token}"}

            client.post("/api/v1/flows", json=SAMPLE_FLOW, headers=owner_auth)

            resp = client.put(
                f"/api/v1/flows/{FLOW_ID}",
                json={"name": "Hijack", "nodes": SAMPLE_FLOW["nodes"], "edges": SAMPLE_FLOW["edges"]},
                headers=stranger_auth,
            )
            assert resp.status_code == 403  # Gate 2: non-member blocked

    def test_editor_cannot_share(self):
        with TestClient(app) as client:
            owner_token, _ = _register(client)
            editor_token, editor_email = _register(client)
            _, third_email = _register(client)
            owner_auth = {"Authorization": f"Bearer {owner_token}"}
            editor_auth = {"Authorization": f"Bearer {editor_token}"}

            client.post("/api/v1/flows", json=SAMPLE_FLOW, headers=owner_auth)
            client.post(
                f"/api/v1/workflows/{FLOW_ID}/share",
                json={"user_id": editor_email, "role": "editor"},
                headers=owner_auth,
            )

            resp = client.post(
                f"/api/v1/workflows/{FLOW_ID}/share",
                json={"user_id": third_email, "role": "viewer"},
                headers=editor_auth,
            )
            assert resp.status_code == 403  # Gate 2: editor cannot share
