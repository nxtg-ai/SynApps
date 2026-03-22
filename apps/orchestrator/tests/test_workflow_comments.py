"""
N-28: Workflow Comments + Activity Feed
Tests for NodeCommentStore, ActivityFeedStore, and all comment/activity endpoints.
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from apps.orchestrator.main import app
from apps.orchestrator.stores import (
    activity_feed_store,
    node_comment_store,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FLOW_ID = "comments-test-flow"
NODE_ID = "node-1"

SAMPLE_FLOW = {
    "id": FLOW_ID,
    "name": "Comments Test Flow",
    "nodes": [
        {"id": NODE_ID, "type": "start", "position": {"x": 0, "y": 0}, "data": {}},
        {"id": "end", "type": "end", "position": {"x": 0, "y": 100}, "data": {}},
    ],
    "edges": [{"id": "e1", "source": NODE_ID, "target": "end"}],
}


@pytest.fixture(autouse=True)
def _clean():
    node_comment_store.reset()
    activity_feed_store.reset()
    yield
    node_comment_store.reset()
    activity_feed_store.reset()


def _get_token(client: TestClient) -> str:
    email = f"comments-{uuid.uuid4().hex[:8]}@test.com"
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "TestPass1!"},
    )
    return resp.json()["access_token"]


# ===========================================================================
# NodeCommentStore — unit
# ===========================================================================


class TestNodeCommentStoreUnit:
    def test_add_returns_comment_with_id(self):
        c = node_comment_store.add("f1", "n1", "user@test.com", "Hello")
        assert c["id"]  # Gate 2
        assert c["content"] == "Hello"
        assert c["author"] == "user@test.com"
        assert c["node_id"] == "n1"

    def test_get_returns_added_comment(self):
        node_comment_store.add("f1", "n1", "user@test.com", "Hello")
        comments = node_comment_store.get("f1", "n1")
        assert len(comments) >= 1  # Gate 2
        assert comments[0]["content"] == "Hello"

    def test_get_empty_node_returns_empty_list(self):
        comments = node_comment_store.get("f1", "nonode")
        assert comments == []

    def test_threaded_comment_stores_parent_id(self):
        parent = node_comment_store.add("f1", "n1", "a@test.com", "Parent")
        child = node_comment_store.add("f1", "n1", "b@test.com", "Child", parent_id=parent["id"])
        assert child["parent_id"] == parent["id"]  # Gate 2

    def test_get_all_for_flow_across_nodes(self):
        node_comment_store.add("f1", "n1", "a@test.com", "On n1")
        node_comment_store.add("f1", "n2", "a@test.com", "On n2")
        all_comments = node_comment_store.get_all_for_flow("f1")
        assert len(all_comments) >= 2  # Gate 2

    def test_get_all_for_flow_sorted_by_created_at(self):
        node_comment_store.add("f1", "n1", "a@test.com", "First")
        node_comment_store.add("f1", "n2", "a@test.com", "Second")
        comments = node_comment_store.get_all_for_flow("f1")
        timestamps = [c["created_at"] for c in comments]
        assert timestamps == sorted(timestamps)  # Gate 2: ascending order

    def test_delete_removes_comment(self):
        c = node_comment_store.add("f1", "n1", "a@test.com", "To delete")
        result = node_comment_store.delete("f1", "n1", c["id"])
        assert result is True
        remaining = node_comment_store.get("f1", "n1")
        assert all(r["id"] != c["id"] for r in remaining)  # Gate 2

    def test_reset_clears_all_comments(self):
        node_comment_store.add("f1", "n1", "a@test.com", "Test")
        node_comment_store.reset()
        assert node_comment_store.get("f1", "n1") == []


# ===========================================================================
# ActivityFeedStore — unit
# ===========================================================================


class TestActivityFeedStoreUnit:
    def test_record_returns_event_with_id(self):
        e = activity_feed_store.record(
            "f1", actor="a@test.com", action="flow_edited", detail="test"
        )
        assert e["id"]  # Gate 2
        assert e["action"] == "flow_edited"
        assert e["actor"] == "a@test.com"

    def test_get_returns_most_recent_first(self):
        activity_feed_store.record("f1", actor="sys", action="run_started", detail="r1")
        activity_feed_store.record("f1", actor="sys", action="run_completed", detail="r1")
        events = activity_feed_store.get("f1")
        assert len(events) >= 2  # Gate 2
        assert events[0]["timestamp"] >= events[1]["timestamp"]

    def test_get_empty_flow_returns_empty(self):
        events = activity_feed_store.get("nonexistent-flow")
        assert events == []

    def test_limit_is_respected(self):
        for i in range(10):
            activity_feed_store.record("f1", actor="sys", action="run_started", detail=str(i))
        events = activity_feed_store.get("f1", limit=3)
        assert len(events) == 3  # Gate 2

    def test_reset_clears_all_events(self):
        activity_feed_store.record("f1", actor="sys", action="run_started", detail="")
        activity_feed_store.reset()
        assert activity_feed_store.get("f1") == []


# ===========================================================================
# Comment endpoints
# ===========================================================================


class TestCommentEndpoints:
    def test_post_comment_returns_201(self):
        with TestClient(app) as client:
            client.post("/api/v1/flows", json=SAMPLE_FLOW)
            token = _get_token(client)
            resp = client.post(
                f"/api/v1/workflows/{FLOW_ID}/nodes/{NODE_ID}/comments",
                json={"content": "Looks good!"},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 201
            body = resp.json()
            assert body["id"]  # Gate 2
            assert body["content"] == "Looks good!"
            assert body["node_id"] == NODE_ID
            assert body["flow_id"] == FLOW_ID

    def test_post_comment_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _get_token(client)
            resp = client.post(
                "/api/v1/workflows/nonexistent-flow/nodes/n1/comments",
                json={"content": "hello"},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 404
            assert "error" in resp.json()

    def test_get_node_comments_returns_200_with_data(self):
        with TestClient(app) as client:
            client.post("/api/v1/flows", json=SAMPLE_FLOW)
            token = _get_token(client)
            auth = {"Authorization": f"Bearer {token}"}
            client.post(
                f"/api/v1/workflows/{FLOW_ID}/nodes/{NODE_ID}/comments",
                json={"content": "First comment"},
                headers=auth,
            )
            resp = client.get(
                f"/api/v1/workflows/{FLOW_ID}/nodes/{NODE_ID}/comments",
                headers=auth,
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["count"] >= 1  # Gate 2
            assert body["comments"][0]["content"] == "First comment"

    def test_threaded_comment_preserves_parent_id(self):
        with TestClient(app) as client:
            client.post("/api/v1/flows", json=SAMPLE_FLOW)
            token = _get_token(client)
            auth = {"Authorization": f"Bearer {token}"}
            parent_resp = client.post(
                f"/api/v1/workflows/{FLOW_ID}/nodes/{NODE_ID}/comments",
                json={"content": "Parent comment"},
                headers=auth,
            )
            parent_id = parent_resp.json()["id"]
            child_resp = client.post(
                f"/api/v1/workflows/{FLOW_ID}/nodes/{NODE_ID}/comments",
                json={"content": "Child reply", "parent_id": parent_id},
                headers=auth,
            )
            assert child_resp.status_code == 201
            assert child_resp.json()["parent_id"] == parent_id  # Gate 2

    def test_list_flow_comments_aggregates_all_nodes(self):
        flow = {
            **SAMPLE_FLOW,
            "nodes": [
                *SAMPLE_FLOW["nodes"],
                {"id": "node-2", "type": "llm", "position": {"x": 0, "y": 200}, "data": {}},
            ],
        }
        with TestClient(app) as client:
            client.post("/api/v1/flows", json=flow)
            token = _get_token(client)
            auth = {"Authorization": f"Bearer {token}"}
            client.post(
                f"/api/v1/workflows/{FLOW_ID}/nodes/{NODE_ID}/comments",
                json={"content": "On node 1"},
                headers=auth,
            )
            client.post(
                f"/api/v1/workflows/{FLOW_ID}/nodes/node-2/comments",
                json={"content": "On node 2"},
                headers=auth,
            )
            resp = client.get(f"/api/v1/workflows/{FLOW_ID}/comments", headers=auth)
            assert resp.status_code == 200
            assert resp.json()["count"] >= 2  # Gate 2

    def test_get_node_comments_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _get_token(client)
            resp = client.get(
                "/api/v1/workflows/nonexistent/nodes/n1/comments",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 404
            assert "error" in resp.json()

    def test_post_comment_requires_auth(self):
        with TestClient(app) as client:
            # Register a user to disable anonymous bootstrap, then test without token
            _get_token(client)
            client.post("/api/v1/flows", json=SAMPLE_FLOW)
            resp = client.post(
                f"/api/v1/workflows/{FLOW_ID}/nodes/{NODE_ID}/comments",
                json={"content": "no auth"},
            )
            assert resp.status_code in (401, 403)
            assert "error" in resp.json()

    def test_post_comment_records_node_commented_activity(self):
        with TestClient(app) as client:
            client.post("/api/v1/flows", json=SAMPLE_FLOW)
            token = _get_token(client)
            auth = {"Authorization": f"Bearer {token}"}
            client.post(
                f"/api/v1/workflows/{FLOW_ID}/nodes/{NODE_ID}/comments",
                json={"content": "Reviewing this node"},
                headers=auth,
            )
            resp = client.get(f"/api/v1/workflows/{FLOW_ID}/activity", headers=auth)
            assert resp.status_code == 200
            actions = [e["action"] for e in resp.json()["events"]]
            assert "node_commented" in actions  # Gate 2


# ===========================================================================
# Activity feed endpoint
# ===========================================================================


class TestActivityFeedEndpoint:
    def test_get_activity_returns_200(self):
        with TestClient(app) as client:
            client.post("/api/v1/flows", json=SAMPLE_FLOW)
            token = _get_token(client)
            auth = {"Authorization": f"Bearer {token}"}
            resp = client.get(f"/api/v1/workflows/{FLOW_ID}/activity", headers=auth)
            assert resp.status_code == 200
            body = resp.json()
            assert "events" in body  # Gate 2
            assert body["flow_id"] == FLOW_ID

    def test_get_activity_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _get_token(client)
            resp = client.get(
                "/api/v1/workflows/nonexistent/activity",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 404
            assert "error" in resp.json()

    def test_flow_edit_appears_in_activity(self):
        with TestClient(app) as client:
            client.post("/api/v1/flows", json=SAMPLE_FLOW)
            token = _get_token(client)
            auth = {"Authorization": f"Bearer {token}"}
            client.put(
                f"/api/v1/flows/{FLOW_ID}",
                json={
                    "name": "Updated Flow",
                    "nodes": SAMPLE_FLOW["nodes"],
                    "edges": SAMPLE_FLOW["edges"],
                },
                headers=auth,
            )
            resp = client.get(f"/api/v1/workflows/{FLOW_ID}/activity", headers=auth)
            actions = [e["action"] for e in resp.json()["events"]]
            assert "flow_edited" in actions  # Gate 2

    def test_run_start_appears_in_activity(self):
        import time

        with TestClient(app) as client:
            client.post("/api/v1/flows", json=SAMPLE_FLOW)
            token = _get_token(client)
            auth = {"Authorization": f"Bearer {token}"}
            with patch("apps.orchestrator.main.broadcast_status", new_callable=AsyncMock):
                run_resp = client.post(
                    f"/api/v1/flows/{FLOW_ID}/runs",
                    json={"input": {}},
                    headers=auth,
                )
            run_id = run_resp.json()["run_id"]
            # Poll until terminal to avoid background task error on teardown
            deadline = time.time() + 5.0
            while time.time() < deadline:
                time.sleep(0.1)
                r = client.get(f"/api/v1/runs/{run_id}")
                if r.status_code == 200 and r.json().get("status") in ("success", "error"):
                    break
            resp = client.get(f"/api/v1/workflows/{FLOW_ID}/activity", headers=auth)
            actions = [e["action"] for e in resp.json()["events"]]
            assert "run_started" in actions  # Gate 2

    def test_activity_limit_param(self):
        with TestClient(app) as client:
            client.post("/api/v1/flows", json=SAMPLE_FLOW)
            token = _get_token(client)
            auth = {"Authorization": f"Bearer {token}"}
            for _ in range(10):
                activity_feed_store.record(FLOW_ID, actor="sys", action="run_started", detail="")
            resp = client.get(
                f"/api/v1/workflows/{FLOW_ID}/activity?limit=3",
                headers=auth,
            )
            assert resp.json()["count"] == 3  # Gate 2

    def test_activity_requires_auth(self):
        with TestClient(app) as client:
            # Register a user to disable anonymous bootstrap, then test without token
            _get_token(client)
            client.post("/api/v1/flows", json=SAMPLE_FLOW)
            resp = client.get(f"/api/v1/workflows/{FLOW_ID}/activity")
            assert resp.status_code in (401, 403)
            assert "error" in resp.json()
