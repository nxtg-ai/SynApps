"""Tests for Multi-User Workflow Collaboration — N-59.

Covers:
  - PresenceStore unit tests (join, heartbeat, leave, get_presence, expiry)
  - NodeLockStore unit tests (acquire, release, conflict, release_all)
  - CollaborationActivityStore unit tests (record, get_activity, limit)
  - Integration tests via TestClient for all 8 collaboration endpoints
"""

import time
import uuid

from fastapi.testclient import TestClient

from apps.orchestrator.helpers import _user_color
from apps.orchestrator.main import app
from apps.orchestrator.stores import (
    CollaborationActivityStore,
    NodeLockStore,
    PresenceStore,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _register(client: TestClient) -> tuple[str, str]:
    """Register a fresh user. Returns (access_token, user_id)."""
    email = f"collab-{uuid.uuid4().hex[:8]}@example.com"
    resp = client.post("/api/v1/auth/register", json={"email": email, "password": "Pass1234!"})
    assert resp.status_code == 201, resp.text
    token = resp.json()["access_token"]
    me_resp = client.get("/api/v1/auth/me", headers=_auth_header(token))
    assert me_resp.status_code == 200, me_resp.text
    return token, me_resp.json()["id"]


def _auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Unit Tests: PresenceStore
# ---------------------------------------------------------------------------


class TestPresenceStore:
    """Unit tests for the PresenceStore class."""

    def test_join_and_get_presence(self) -> None:
        store = PresenceStore()
        store.join("flow-1", "user-a", "alice@test.com", "#FF6B6B")
        result = store.get_presence("flow-1")
        assert isinstance(result, list)
        assert len(result) >= 1  # Gate 2
        assert result[0]["user_id"] == "user-a"
        assert result[0]["username"] == "alice@test.com"
        assert result[0]["color"] == "#FF6B6B"

    def test_join_multiple_users(self) -> None:
        store = PresenceStore()
        store.join("flow-1", "user-a", "alice", "#FF6B6B")
        store.join("flow-1", "user-b", "bob", "#4ECDC4")
        result = store.get_presence("flow-1")
        assert isinstance(result, list)
        assert len(result) >= 2  # Gate 2

    def test_leave_removes_user(self) -> None:
        store = PresenceStore()
        store.join("flow-1", "user-a", "alice", "#FF6B6B")
        store.join("flow-1", "user-b", "bob", "#4ECDC4")
        store.leave("flow-1", "user-a")
        result = store.get_presence("flow-1")
        assert len(result) == 1
        assert result[0]["user_id"] == "user-b"

    def test_heartbeat_updates_last_seen(self) -> None:
        store = PresenceStore()
        store.join("flow-1", "user-a", "alice", "#FF6B6B")
        before = store.get_presence("flow-1")[0]["last_seen"]
        time.sleep(0.05)
        store.heartbeat("flow-1", "user-a")
        after = store.get_presence("flow-1")[0]["last_seen"]
        assert after > before

    def test_expired_users_filtered(self) -> None:
        store = PresenceStore()
        store.join("flow-1", "user-a", "alice", "#FF6B6B")
        # Manually set last_seen to the past
        store._presence["flow-1"]["user-a"]["last_seen"] = time.time() - 60
        result = store.get_presence("flow-1")
        assert result == []

    def test_get_presence_empty_flow(self) -> None:
        store = PresenceStore()
        assert store.get_presence("nonexistent") == []

    def test_reset_clears_all(self) -> None:
        store = PresenceStore()
        store.join("flow-1", "user-a", "alice", "#FF6B6B")
        store.reset()
        assert store.get_presence("flow-1") == []


# ---------------------------------------------------------------------------
# Unit Tests: NodeLockStore
# ---------------------------------------------------------------------------


class TestNodeLockStore:
    """Unit tests for the NodeLockStore class."""

    def test_acquire_succeeds(self) -> None:
        store = NodeLockStore()
        assert store.acquire("flow-1", "node-1", "user-a", "alice") is True

    def test_acquire_same_user_idempotent(self) -> None:
        store = NodeLockStore()
        store.acquire("flow-1", "node-1", "user-a", "alice")
        assert store.acquire("flow-1", "node-1", "user-a", "alice") is True

    def test_acquire_conflict(self) -> None:
        store = NodeLockStore()
        store.acquire("flow-1", "node-1", "user-a", "alice")
        assert store.acquire("flow-1", "node-1", "user-b", "bob") is False

    def test_release_by_owner(self) -> None:
        store = NodeLockStore()
        store.acquire("flow-1", "node-1", "user-a", "alice")
        assert store.release("flow-1", "node-1", "user-a") is True
        locks = store.get_locks("flow-1")
        assert "node-1" not in locks

    def test_release_by_non_owner_fails(self) -> None:
        store = NodeLockStore()
        store.acquire("flow-1", "node-1", "user-a", "alice")
        assert store.release("flow-1", "node-1", "user-b") is False

    def test_release_all_for_user(self) -> None:
        store = NodeLockStore()
        store.acquire("flow-1", "node-1", "user-a", "alice")
        store.acquire("flow-1", "node-2", "user-a", "alice")
        store.acquire("flow-1", "node-3", "user-b", "bob")
        released = store.release_all_for_user("flow-1", "user-a")
        assert released == 2
        locks = store.get_locks("flow-1")
        assert "node-1" not in locks
        assert "node-2" not in locks
        assert "node-3" in locks

    def test_get_locks(self) -> None:
        store = NodeLockStore()
        store.acquire("flow-1", "node-1", "user-a", "alice")
        locks = store.get_locks("flow-1")
        assert isinstance(locks, dict)
        assert len(locks) >= 1  # Gate 2
        assert locks["node-1"]["user_id"] == "user-a"

    def test_reset_clears_all(self) -> None:
        store = NodeLockStore()
        store.acquire("flow-1", "node-1", "user-a", "alice")
        store.reset()
        assert store.get_locks("flow-1") == {}


# ---------------------------------------------------------------------------
# Unit Tests: CollaborationActivityStore
# ---------------------------------------------------------------------------


class TestCollaborationActivityStore:
    """Unit tests for the CollaborationActivityStore class."""

    def test_record_and_get(self) -> None:
        store = CollaborationActivityStore()
        store.record("flow-1", "user-a", "alice", "joined")
        result = store.get_activity("flow-1")
        assert isinstance(result, list)
        assert len(result) >= 1  # Gate 2
        assert result[0]["action"] == "joined"
        assert result[0]["user_id"] == "user-a"

    def test_get_activity_most_recent_first(self) -> None:
        store = CollaborationActivityStore()
        store.record("flow-1", "user-a", "alice", "joined")
        store.record("flow-1", "user-b", "bob", "joined")
        store.record("flow-1", "user-a", "alice", "locked_node", "node-1")
        result = store.get_activity("flow-1")
        assert len(result) >= 3  # Gate 2
        assert result[0]["action"] == "locked_node"

    def test_get_activity_limit(self) -> None:
        store = CollaborationActivityStore()
        for i in range(10):
            store.record("flow-1", f"user-{i}", f"user{i}", "joined")
        result = store.get_activity("flow-1", limit=3)
        assert len(result) == 3

    def test_max_events_per_flow(self) -> None:
        store = CollaborationActivityStore()
        for i in range(60):
            store.record("flow-1", f"user-{i}", f"user{i}", "joined")
        # Only the last 50 should remain
        result = store.get_activity("flow-1", limit=100)
        assert len(result) == 50

    def test_reset_clears_all(self) -> None:
        store = CollaborationActivityStore()
        store.record("flow-1", "user-a", "alice", "joined")
        store.reset()
        assert store.get_activity("flow-1") == []


# ---------------------------------------------------------------------------
# Unit Tests: _user_color
# ---------------------------------------------------------------------------


class TestUserColor:
    """Unit tests for the deterministic color assignment helper."""

    def test_returns_hex_string(self) -> None:
        color = _user_color("user-123")
        assert color.startswith("#")
        assert len(color) == 7

    def test_deterministic(self) -> None:
        assert _user_color("user-abc") == _user_color("user-abc")

    def test_different_users_can_differ(self) -> None:
        # Not guaranteed to differ, but with many users most will
        colors = {_user_color(f"user-{i}") for i in range(100)}
        assert len(colors) > 1


# ---------------------------------------------------------------------------
# Integration Tests: Collaboration Endpoints
# ---------------------------------------------------------------------------


class TestCollaborationEndpoints:
    """Integration tests for the collaboration REST endpoints via TestClient."""

    def test_join_returns_collaborators(self) -> None:
        with TestClient(app) as client:
            token, user_id = _register(client)
            resp = client.post(
                "/api/v1/flows/flow-x/collaboration/join",
                headers=_auth_header(token),
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["user_id"] == user_id
            assert data["color"].startswith("#")
            assert isinstance(data["collaborators"], list)
            assert len(data["collaborators"]) >= 1  # Gate 2

    def test_heartbeat_returns_200(self) -> None:
        with TestClient(app) as client:
            token, _ = _register(client)
            # Must join first so heartbeat has something to update
            client.post(
                "/api/v1/flows/flow-x/collaboration/join",
                headers=_auth_header(token),
            )
            resp = client.post(
                "/api/v1/flows/flow-x/collaboration/heartbeat",
                headers=_auth_header(token),
            )
            assert resp.status_code == 200
            assert resp.json()["status"] == "ok"

    def test_leave_removes_user(self) -> None:
        with TestClient(app) as client:
            token, _ = _register(client)
            client.post(
                "/api/v1/flows/flow-x/collaboration/join",
                headers=_auth_header(token),
            )
            resp = client.delete(
                "/api/v1/flows/flow-x/collaboration/leave",
                headers=_auth_header(token),
            )
            assert resp.status_code == 200
            assert resp.json()["status"] == "left"
            # Verify presence is empty
            resp2 = client.get(
                "/api/v1/flows/flow-x/collaboration/presence",
                headers=_auth_header(token),
            )
            assert resp2.status_code == 200
            assert resp2.json()["collaborators"] == []

    def test_presence_shows_active_users(self) -> None:
        with TestClient(app) as client:
            token1, uid1 = _register(client)
            token2, uid2 = _register(client)
            client.post(
                "/api/v1/flows/flow-x/collaboration/join",
                headers=_auth_header(token1),
            )
            client.post(
                "/api/v1/flows/flow-x/collaboration/join",
                headers=_auth_header(token2),
            )
            resp = client.get(
                "/api/v1/flows/flow-x/collaboration/presence",
                headers=_auth_header(token1),
            )
            assert resp.status_code == 200
            collabs = resp.json()["collaborators"]
            assert isinstance(collabs, list)
            assert len(collabs) >= 2  # Gate 2
            user_ids = {c["user_id"] for c in collabs}
            assert uid1 in user_ids
            assert uid2 in user_ids

    def test_lock_node_succeeds(self) -> None:
        with TestClient(app) as client:
            token, user_id = _register(client)
            resp = client.post(
                "/api/v1/flows/flow-x/collaboration/lock/node-1",
                headers=_auth_header(token),
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["locked"] is True
            assert data["node_id"] == "node-1"

    def test_lock_node_conflict_409(self) -> None:
        with TestClient(app) as client:
            token1, _ = _register(client)
            token2, _ = _register(client)
            resp1 = client.post(
                "/api/v1/flows/flow-x/collaboration/lock/node-1",
                headers=_auth_header(token1),
            )
            assert resp1.status_code == 200
            resp2 = client.post(
                "/api/v1/flows/flow-x/collaboration/lock/node-1",
                headers=_auth_header(token2),
            )
            assert resp2.status_code == 409

    def test_release_lock_works(self) -> None:
        with TestClient(app) as client:
            token, _ = _register(client)
            client.post(
                "/api/v1/flows/flow-x/collaboration/lock/node-1",
                headers=_auth_header(token),
            )
            resp = client.delete(
                "/api/v1/flows/flow-x/collaboration/lock/node-1",
                headers=_auth_header(token),
            )
            assert resp.status_code == 200
            assert resp.json()["released"] is True

    def test_get_locks_returns_active_locks(self) -> None:
        with TestClient(app) as client:
            token, user_id = _register(client)
            client.post(
                "/api/v1/flows/flow-x/collaboration/lock/node-1",
                headers=_auth_header(token),
            )
            resp = client.get(
                "/api/v1/flows/flow-x/collaboration/locks",
                headers=_auth_header(token),
            )
            assert resp.status_code == 200
            locks = resp.json()["locks"]
            assert isinstance(locks, dict)
            assert len(locks) >= 1  # Gate 2
            assert "node-1" in locks
            assert locks["node-1"]["user_id"] == user_id

    def test_activity_feed_records_events(self) -> None:
        with TestClient(app) as client:
            token, _ = _register(client)
            # Join (records "joined"), lock (records "locked_node")
            client.post(
                "/api/v1/flows/flow-x/collaboration/join",
                headers=_auth_header(token),
            )
            client.post(
                "/api/v1/flows/flow-x/collaboration/lock/node-1",
                headers=_auth_header(token),
            )
            resp = client.get(
                "/api/v1/flows/flow-x/collaboration/activity",
                headers=_auth_header(token),
            )
            assert resp.status_code == 200
            activity = resp.json()["activity"]
            assert isinstance(activity, list)
            assert len(activity) >= 2  # Gate 2: joined + locked_node
            actions = [a["action"] for a in activity]
            assert "joined" in actions
            assert "locked_node" in actions

    def test_two_users_cannot_lock_same_node(self) -> None:
        with TestClient(app) as client:
            token1, _ = _register(client)
            token2, _ = _register(client)
            resp1 = client.post(
                "/api/v1/flows/flow-x/collaboration/lock/node-5",
                headers=_auth_header(token1),
            )
            assert resp1.status_code == 200
            resp2 = client.post(
                "/api/v1/flows/flow-x/collaboration/lock/node-5",
                headers=_auth_header(token2),
            )
            assert resp2.status_code == 409
            body = resp2.json()
            # Custom error handler wraps detail in {"error": {"message": ...}}
            error_msg = body.get("detail", "")
            if not error_msg and "error" in body:
                error_msg = body["error"].get("message", "")
            assert "already locked" in error_msg

    def test_leave_releases_all_user_locks(self) -> None:
        with TestClient(app) as client:
            token, _ = _register(client)
            client.post(
                "/api/v1/flows/flow-x/collaboration/join",
                headers=_auth_header(token),
            )
            client.post(
                "/api/v1/flows/flow-x/collaboration/lock/node-1",
                headers=_auth_header(token),
            )
            client.post(
                "/api/v1/flows/flow-x/collaboration/lock/node-2",
                headers=_auth_header(token),
            )
            # Leave should release all locks
            client.delete(
                "/api/v1/flows/flow-x/collaboration/leave",
                headers=_auth_header(token),
            )
            # Re-register to check locks (need auth)
            token2, _ = _register(client)
            resp = client.get(
                "/api/v1/flows/flow-x/collaboration/locks",
                headers=_auth_header(token2),
            )
            assert resp.status_code == 200
            assert resp.json()["locks"] == {}

    def test_unauthenticated_request_rejected(self) -> None:
        with TestClient(app) as client:
            # Register a user first so anonymous bootstrap is disabled
            _register(client)
            resp = client.post("/api/v1/flows/flow-x/collaboration/join")
            assert resp.status_code in (401, 403)
