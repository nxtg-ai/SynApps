"""
N-131: Flow Tags — POST/GET/DELETE /api/v1/flows/{flow_id}/tags

Tests:
  - POST adds a tag; response includes sorted tag list
  - GET returns tags for a flow
  - Tags are lowercased and deduplicated
  - Multiple tags can be added
  - DELETE removes a specific tag
  - DELETE returns 404 for unknown tag
  - POST/GET/DELETE return 404 for unknown flow
  - Auth required (401 without token)
  - Deleting flow clears its tags (independence)
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
        json={"email": f"tags-{uid}@test.com", "password": "pass1234"},
    )
    assert r.status_code == 201
    return r.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_flow(client: TestClient, token: str) -> str:
    uid = uuid.uuid4().hex[:6]
    resp = client.post(
        "/api/v1/flows",
        json={"name": f"tag-test-{uid}", "nodes": [], "edges": []},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestFlowTagAdd:
    def test_add_tag_returns_201(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/tags",
                json={"tag": "production"},
                headers=_auth(token),
            )
        assert resp.status_code == 201

    def test_add_tag_appears_in_response(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/tags",
                json={"tag": "production"},
                headers=_auth(token),
            )
        assert "production" in resp.json()["tags"]

    def test_add_tag_lowercased(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/tags",
                json={"tag": "UPPER"},
                headers=_auth(token),
            )
        assert "upper" in resp.json()["tags"]
        assert "UPPER" not in resp.json()["tags"]

    def test_add_duplicate_tag_idempotent(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            client.post(
                f"/api/v1/flows/{flow_id}/tags",
                json={"tag": "dup"},
                headers=_auth(token),
            )
            resp = client.post(
                f"/api/v1/flows/{flow_id}/tags",
                json={"tag": "dup"},
                headers=_auth(token),
            )
        assert resp.json()["tags"].count("dup") == 1  # Gate 2: exactly one copy

    def test_add_multiple_tags(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            for tag in ("alpha", "beta", "gamma"):
                client.post(
                    f"/api/v1/flows/{flow_id}/tags",
                    json={"tag": tag},
                    headers=_auth(token),
                )
            resp = client.get(f"/api/v1/flows/{flow_id}/tags", headers=_auth(token))
        tags = resp.json()["tags"]
        assert len(tags) == 3  # Gate 2: all three tags present
        assert set(tags) == {"alpha", "beta", "gamma"}

    def test_add_tag_returns_sorted_list(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            for tag in ("zebra", "apple", "mango"):
                client.post(
                    f"/api/v1/flows/{flow_id}/tags",
                    json={"tag": tag},
                    headers=_auth(token),
                )
            resp = client.get(f"/api/v1/flows/{flow_id}/tags", headers=_auth(token))
        tags = resp.json()["tags"]
        assert tags == sorted(tags)

    def test_add_tag_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.post(
                "/api/v1/flows/nonexistent-id/tags",
                json={"tag": "x"},
                headers=_auth(token),
            )
        assert resp.status_code == 404

    def test_add_tag_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/tags",
                json={"tag": "x"},
            )
        assert resp.status_code == 401


class TestFlowTagGet:
    def test_get_tags_empty_by_default(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/tags", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["tags"] == []

    def test_get_tags_returns_added_tags(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            client.post(
                f"/api/v1/flows/{flow_id}/tags",
                json={"tag": "v1"},
                headers=_auth(token),
            )
            resp = client.get(f"/api/v1/flows/{flow_id}/tags", headers=_auth(token))
        assert "v1" in resp.json()["tags"]

    def test_get_tags_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get(
                "/api/v1/flows/nonexistent/tags",
                headers=_auth(token),
            )
        assert resp.status_code == 404

    def test_get_tags_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/tags")
        assert resp.status_code == 401


class TestFlowTagDelete:
    def test_delete_tag_removes_it(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            client.post(
                f"/api/v1/flows/{flow_id}/tags",
                json={"tag": "remove-me"},
                headers=_auth(token),
            )
            del_resp = client.delete(
                f"/api/v1/flows/{flow_id}/tags/remove-me",
                headers=_auth(token),
            )
            get_resp = client.get(f"/api/v1/flows/{flow_id}/tags", headers=_auth(token))
        assert del_resp.status_code == 200
        assert "remove-me" not in get_resp.json()["tags"]

    def test_delete_tag_response_has_remaining_tags(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            for tag in ("keep", "drop"):
                client.post(
                    f"/api/v1/flows/{flow_id}/tags",
                    json={"tag": tag},
                    headers=_auth(token),
                )
            resp = client.delete(
                f"/api/v1/flows/{flow_id}/tags/drop",
                headers=_auth(token),
            )
        assert resp.json()["tags"] == ["keep"]

    def test_delete_unknown_tag_returns_404(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.delete(
                f"/api/v1/flows/{flow_id}/tags/no-such-tag",
                headers=_auth(token),
            )
        assert resp.status_code == 404

    def test_delete_tag_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.delete(
                "/api/v1/flows/nonexistent/tags/tag",
                headers=_auth(token),
            )
        assert resp.status_code == 404

    def test_delete_tag_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            client.post(
                f"/api/v1/flows/{flow_id}/tags",
                json={"tag": "x"},
                headers=_auth(token),
            )
            resp = client.delete(f"/api/v1/flows/{flow_id}/tags/x")
        assert resp.status_code == 401

    def test_delete_tag_case_insensitive(self):
        """Tags are stored lowercase; deleting with original case must work."""
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            client.post(
                f"/api/v1/flows/{flow_id}/tags",
                json={"tag": "MyTag"},
                headers=_auth(token),
            )
            resp = client.delete(
                f"/api/v1/flows/{flow_id}/tags/MyTag",
                headers=_auth(token),
            )
        assert resp.status_code == 200
        assert resp.json()["tags"] == []
