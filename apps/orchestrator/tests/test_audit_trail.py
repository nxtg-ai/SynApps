"""
N-30: Audit Trail — Compliance Logging
Tests for AuditLogStore and GET /audit endpoint, wiring into flow CRUD,
execution, and permission changes.
"""

import uuid
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from apps.orchestrator.main import (
    app,
    audit_log_store,
    workflow_permission_store,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FLOW_ID = "audit-test-flow"
SAMPLE_FLOW = {
    "id": FLOW_ID,
    "name": "Audit Test Flow",
    "nodes": [
        {"id": "s", "type": "start", "position": {"x": 0, "y": 0}, "data": {}},
        {"id": "e", "type": "end", "position": {"x": 0, "y": 100}, "data": {}},
    ],
    "edges": [{"id": "e1", "source": "s", "target": "e"}],
}


@pytest.fixture(autouse=True)
def _clean():
    audit_log_store.reset()
    workflow_permission_store.reset()
    yield
    audit_log_store.reset()
    workflow_permission_store.reset()


def _register(client: TestClient, email: str | None = None) -> tuple[str, str]:
    email = email or f"audit-{uuid.uuid4().hex[:8]}@test.com"
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "AuditPass1!"},
    )
    return resp.json()["access_token"], email


# ===========================================================================
# AuditLogStore — unit
# ===========================================================================


class TestAuditLogStoreUnit:
    def test_record_returns_entry_with_id(self):
        e = audit_log_store.record("alice@x.com", "workflow_created", "flow", "f1")
        assert e["id"]  # Gate 2
        assert e["action"] == "workflow_created"
        assert e["actor"] == "alice@x.com"
        assert e["resource_type"] == "flow"
        assert e["resource_id"] == "f1"

    def test_query_all_returns_reverse_chronological(self):
        audit_log_store.record("a@x.com", "workflow_created", "flow", "f1")
        audit_log_store.record("a@x.com", "workflow_updated", "flow", "f1")
        entries = audit_log_store.query()
        assert len(entries) >= 2  # Gate 2
        assert entries[0]["timestamp"] >= entries[1]["timestamp"]

    def test_query_filter_by_actor(self):
        audit_log_store.record("alice@x.com", "workflow_created", "flow", "f1")
        audit_log_store.record("bob@x.com", "workflow_updated", "flow", "f1")
        results = audit_log_store.query(actor="alice@x.com")
        assert len(results) >= 1  # Gate 2
        assert all(r["actor"] == "alice@x.com" for r in results)  # Gate 2

    def test_query_filter_by_action(self):
        audit_log_store.record("a@x.com", "workflow_created", "flow", "f1")
        audit_log_store.record("a@x.com", "workflow_deleted", "flow", "f1")
        results = audit_log_store.query(action="workflow_created")
        assert len(results) >= 1  # Gate 2
        assert all(r["action"] == "workflow_created" for r in results)  # Gate 2

    def test_query_filter_by_resource_id(self):
        audit_log_store.record("a@x.com", "workflow_created", "flow", "f1")
        audit_log_store.record("a@x.com", "workflow_created", "flow", "f2")
        results = audit_log_store.query(resource_id="f1")
        assert len(results) >= 1  # Gate 2
        assert all(r["resource_id"] == "f1" for r in results)  # Gate 2

    def test_query_limit_respected(self):
        for i in range(20):
            audit_log_store.record("a@x.com", "workflow_created", "flow", f"f{i}")
        results = audit_log_store.query(limit=5)
        assert len(results) == 5  # Gate 2

    def test_purge_old_removes_stale_entries(self):
        # Manually inject a stale entry
        stale_ts = (datetime.utcnow() - timedelta(days=100)).isoformat()
        with audit_log_store._lock:
            audit_log_store._entries.append({
                "id": "stale-1",
                "timestamp": stale_ts,
                "actor": "a@x.com",
                "action": "workflow_created",
                "resource_type": "flow",
                "resource_id": "old-flow",
                "detail": "",
            })
        recent = audit_log_store.record("a@x.com", "workflow_created", "flow", "new-flow")
        deleted = audit_log_store.purge_old(retention_days=90)
        assert deleted >= 1  # Gate 2: stale entry removed
        remaining = audit_log_store.query()
        assert all(r["id"] != "stale-1" for r in remaining)  # Gate 2: stale gone
        assert any(r["id"] == recent["id"] for r in remaining)  # Gate 2: recent kept

    def test_reset_clears_all(self):
        audit_log_store.record("a@x.com", "workflow_created", "flow", "f1")
        audit_log_store.reset()
        assert audit_log_store.count() == 0


# ===========================================================================
# Audit wiring — flow events
# ===========================================================================


class TestAuditWiringFlowEvents:
    def test_create_flow_records_workflow_created(self):
        with TestClient(app) as client:
            token, email = _register(client)
            client.post("/api/v1/flows", json=SAMPLE_FLOW, headers={"Authorization": f"Bearer {token}"})
            entries = audit_log_store.query(action="workflow_created")
            assert len(entries) >= 1  # Gate 2
            assert any(e["resource_id"] == FLOW_ID for e in entries)  # Gate 2

    def test_update_flow_records_workflow_updated(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            auth = {"Authorization": f"Bearer {token}"}
            client.post("/api/v1/flows", json=SAMPLE_FLOW, headers=auth)
            client.put(
                f"/api/v1/flows/{FLOW_ID}",
                json={"name": "Updated", "nodes": SAMPLE_FLOW["nodes"], "edges": SAMPLE_FLOW["edges"]},
                headers=auth,
            )
            entries = audit_log_store.query(action="workflow_updated")
            assert len(entries) >= 1  # Gate 2

    def test_delete_flow_records_workflow_deleted(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            auth = {"Authorization": f"Bearer {token}"}
            client.post("/api/v1/flows", json=SAMPLE_FLOW, headers=auth)
            client.delete(f"/api/v1/flows/{FLOW_ID}", headers=auth)
            entries = audit_log_store.query(action="workflow_deleted")
            assert len(entries) >= 1  # Gate 2

    def test_run_flow_records_workflow_run_started(self):
        import time

        with TestClient(app) as client:
            token, _ = _register(client)
            auth = {"Authorization": f"Bearer {token}"}
            client.post("/api/v1/flows", json=SAMPLE_FLOW, headers=auth)
            with patch("apps.orchestrator.main.broadcast_status", new_callable=AsyncMock):
                run_resp = client.post(
                    f"/api/v1/flows/{FLOW_ID}/runs",
                    json={"input": {}},
                    headers=auth,
                )
            run_id = run_resp.json()["run_id"]
            # Poll to terminal to avoid teardown race
            deadline = time.time() + 5.0
            while time.time() < deadline:
                time.sleep(0.1)
                r = client.get(f"/api/v1/runs/{run_id}")
                if r.status_code == 200 and r.json().get("status") in ("success", "error"):
                    break
            entries = audit_log_store.query(action="workflow_run_started")
            assert len(entries) >= 1  # Gate 2

    def test_share_records_permission_granted(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            _, editor_email = _register(client)
            auth = {"Authorization": f"Bearer {token}"}
            client.post("/api/v1/flows", json=SAMPLE_FLOW, headers=auth)
            client.post(
                f"/api/v1/workflows/{FLOW_ID}/share",
                json={"user_id": editor_email, "role": "editor"},
                headers=auth,
            )
            entries = audit_log_store.query(action="permission_granted")
            assert len(entries) >= 1  # Gate 2
            assert any(editor_email in e["detail"] for e in entries)  # Gate 2

    def test_revoke_records_permission_revoked(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            _, editor_email = _register(client)
            auth = {"Authorization": f"Bearer {token}"}
            client.post("/api/v1/flows", json=SAMPLE_FLOW, headers=auth)
            client.post(
                f"/api/v1/workflows/{FLOW_ID}/share",
                json={"user_id": editor_email, "role": "editor"},
                headers=auth,
            )
            client.delete(
                f"/api/v1/workflows/{FLOW_ID}/share/{editor_email}",
                headers=auth,
            )
            entries = audit_log_store.query(action="permission_revoked")
            assert len(entries) >= 1  # Gate 2


# ===========================================================================
# GET /audit endpoint
# ===========================================================================


class TestAuditEndpoint:
    def test_get_audit_returns_200(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            resp = client.get(
                "/api/v1/audit",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 200
            body = resp.json()
            assert "entries" in body  # Gate 2
            assert "count" in body  # Gate 2

    def test_audit_filter_by_action(self):
        audit_log_store.record("a@x.com", "workflow_created", "flow", "f1")
        audit_log_store.record("a@x.com", "workflow_deleted", "flow", "f2")
        with TestClient(app) as client:
            token, _ = _register(client)
            resp = client.get(
                "/api/v1/audit?action=workflow_created",
                headers={"Authorization": f"Bearer {token}"},
            )
            entries = resp.json()["entries"]
            assert len(entries) >= 1  # Gate 2
            assert all(e["action"] == "workflow_created" for e in entries)  # Gate 2

    def test_audit_filter_by_actor(self):
        audit_log_store.record("alice@x.com", "workflow_created", "flow", "f1")
        audit_log_store.record("bob@x.com", "workflow_created", "flow", "f2")
        with TestClient(app) as client:
            token, _ = _register(client)
            resp = client.get(
                "/api/v1/audit?actor=alice@x.com",
                headers={"Authorization": f"Bearer {token}"},
            )
            entries = resp.json()["entries"]
            assert len(entries) >= 1  # Gate 2
            assert all(e["actor"] == "alice@x.com" for e in entries)  # Gate 2

    def test_audit_filter_by_resource_id(self):
        audit_log_store.record("a@x.com", "workflow_created", "flow", "target-flow")
        audit_log_store.record("a@x.com", "workflow_created", "flow", "other-flow")
        with TestClient(app) as client:
            token, _ = _register(client)
            resp = client.get(
                "/api/v1/audit?resource_id=target-flow",
                headers={"Authorization": f"Bearer {token}"},
            )
            entries = resp.json()["entries"]
            assert len(entries) >= 1  # Gate 2
            assert all(e["resource_id"] == "target-flow" for e in entries)  # Gate 2

    def test_audit_limit_param(self):
        for i in range(15):
            audit_log_store.record("a@x.com", "workflow_created", "flow", f"f{i}")
        with TestClient(app) as client:
            token, _ = _register(client)
            resp = client.get(
                "/api/v1/audit?limit=5",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.json()["count"] == 5  # Gate 2

    def test_audit_requires_auth(self):
        with TestClient(app) as client:
            _register(client)  # disable anonymous bootstrap
            resp = client.get("/api/v1/audit")
            assert resp.status_code in (401, 403)

    def test_audit_since_filter(self):
        # Inject a clearly old entry
        old_ts = (datetime.utcnow() - timedelta(hours=2)).isoformat()
        with audit_log_store._lock:
            audit_log_store._entries.append({
                "id": "old-1",
                "timestamp": old_ts,
                "actor": "a@x.com",
                "action": "workflow_created",
                "resource_type": "flow",
                "resource_id": "old-flow",
                "detail": "",
            })
        audit_log_store.record("a@x.com", "workflow_created", "flow", "new-flow")
        since = (datetime.utcnow() - timedelta(hours=1)).isoformat()
        with TestClient(app) as client:
            token, _ = _register(client)
            resp = client.get(
                f"/api/v1/audit?since={since}",
                headers={"Authorization": f"Bearer {token}"},
            )
            entries = resp.json()["entries"]
            assert all(e["id"] != "old-1" for e in entries)  # Gate 2: old entry excluded
