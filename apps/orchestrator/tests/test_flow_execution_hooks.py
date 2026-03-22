"""
N-192: Flow Execution Hooks — POST/GET/DELETE /flows/{id}/execution-hooks[/{hook_id}]

Tests:
  - POST adds hook; returns 201
  - POST response shape (hook_id, flow_id, hook_type, url, event, enabled, headers, created_at)
  - POST hook_type pre_execution stored
  - POST hook_type post_execution stored
  - POST hook_type on_error stored
  - POST invalid hook_type → 422
  - POST enabled=False stored
  - POST event stored
  - POST headers stored
  - POST 404 for unknown flow
  - POST requires auth
  - POST too many hooks → 422
  - GET list returns hooks (Gate 2)
  - GET list empty when none
  - GET list 404 unknown flow
  - GET list requires auth
  - GET single returns hook
  - GET single 404 unknown hook
  - GET single 404 unknown flow
  - GET single requires auth
  - DELETE removes hook; returns {deleted: true, hook_id, flow_id}
  - DELETE 404 when not found
  - DELETE 404 unknown flow
  - DELETE requires auth
  - GET single 404 after DELETE
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
        json={"email": f"exhook-{uid}@test.com", "password": "pass1234"},
    )
    assert r.status_code == 201
    return r.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_flow(client: TestClient, token: str) -> str:
    resp = client.post(
        "/api/v1/flows",
        json={"name": "Execution Hook Test Flow", "nodes": [], "edges": []},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _add_hook(
    client: TestClient,
    token: str,
    flow_id: str,
    hook_type: str = "pre_execution",
    url: str = "https://example.com/hook",
    event: str = "",
    enabled: bool = True,
    headers: dict | None = None,
) -> dict:
    resp = client.post(
        f"/api/v1/flows/{flow_id}/execution-hooks",
        json={
            "hook_type": hook_type,
            "url": url,
            "event": event,
            "enabled": enabled,
            "headers": headers or {},
        },
        headers=_auth(token),
    )
    assert resp.status_code == 201
    return resp.json()


# ---------------------------------------------------------------------------
# Tests — POST /flows/{id}/execution-hooks
# ---------------------------------------------------------------------------


class TestFlowExecutionHookPost:
    def test_post_returns_201(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/execution-hooks",
                json={"hook_type": "pre_execution", "url": "https://example.com/pre"},
                headers=_auth(token),
            )
        assert resp.status_code == 201

    def test_post_response_shape(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/execution-hooks",
                json={"hook_type": "post_execution", "url": "https://example.com/post"},
                headers=_auth(token),
            )
        data = resp.json()
        assert data["flow_id"] == flow_id
        assert "hook_id" in data
        assert "hook_type" in data
        assert "url" in data
        assert "event" in data
        assert "enabled" in data
        assert "headers" in data
        assert "created_at" in data

    def test_post_pre_execution_type(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/execution-hooks",
                json={"hook_type": "pre_execution", "url": "https://example.com/hook"},
                headers=_auth(token),
            )
        assert resp.json()["hook_type"] == "pre_execution"

    def test_post_post_execution_type(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/execution-hooks",
                json={"hook_type": "post_execution", "url": "https://example.com/hook"},
                headers=_auth(token),
            )
        assert resp.json()["hook_type"] == "post_execution"

    def test_post_on_error_type(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/execution-hooks",
                json={"hook_type": "on_error", "url": "https://example.com/hook"},
                headers=_auth(token),
            )
        assert resp.json()["hook_type"] == "on_error"

    def test_post_invalid_type_422(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/execution-hooks",
                json={"hook_type": "before_run", "url": "https://example.com/hook"},
                headers=_auth(token),
            )
        assert resp.status_code == 422

    def test_post_enabled_false(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/execution-hooks",
                json={
                    "hook_type": "pre_execution",
                    "url": "https://example.com/hook",
                    "enabled": False,
                },
                headers=_auth(token),
            )
        assert resp.json()["enabled"] is False

    def test_post_event_stored(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/execution-hooks",
                json={
                    "hook_type": "on_error",
                    "url": "https://example.com/hook",
                    "event": "timeout",
                },
                headers=_auth(token),
            )
        assert resp.json()["event"] == "timeout"

    def test_post_headers_stored(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/execution-hooks",
                json={
                    "hook_type": "pre_execution",
                    "url": "https://example.com/hook",
                    "headers": {"X-Secret": "abc123"},
                },
                headers=_auth(token),
            )
        assert resp.json()["headers"].get("X-Secret") == "abc123"

    def test_post_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.post(
                "/api/v1/flows/nonexistent/execution-hooks",
                json={"hook_type": "pre_execution", "url": "https://example.com/hook"},
                headers=_auth(token),
            )
        assert resp.status_code == 404

    def test_post_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/execution-hooks",
                json={"hook_type": "pre_execution", "url": "https://example.com/hook"},
            )
        assert resp.status_code == 401

    def test_post_too_many_hooks_422(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            for i in range(20):
                _add_hook(client, token, flow_id, url=f"https://example.com/hook/{i}")
            resp = client.post(
                f"/api/v1/flows/{flow_id}/execution-hooks",
                json={"hook_type": "pre_execution", "url": "https://example.com/hook/21"},
                headers=_auth(token),
            )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Tests — GET /flows/{id}/execution-hooks
# ---------------------------------------------------------------------------


class TestFlowExecutionHookList:
    def test_list_returns_hooks(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            _add_hook(client, token, flow_id)
            _add_hook(client, token, flow_id, hook_type="post_execution")
            resp = client.get(f"/api/v1/flows/{flow_id}/execution-hooks", headers=_auth(token))
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["hooks"]) >= 1  # Gate 2

    def test_list_empty_when_none(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/execution-hooks", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["hooks"] == []

    def test_list_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get(
                "/api/v1/flows/nonexistent/execution-hooks", headers=_auth(token)
            )
        assert resp.status_code == 404

    def test_list_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/execution-hooks")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Tests — GET /flows/{id}/execution-hooks/{hook_id}
# ---------------------------------------------------------------------------


class TestFlowExecutionHookGet:
    def test_get_returns_hook(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            hook = _add_hook(client, token, flow_id)
            hook_id = hook["hook_id"]
            resp = client.get(
                f"/api/v1/flows/{flow_id}/execution-hooks/{hook_id}", headers=_auth(token)
            )
        assert resp.status_code == 200
        assert resp.json()["hook_id"] == hook_id

    def test_get_404_unknown_hook(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(
                f"/api/v1/flows/{flow_id}/execution-hooks/no-such-hook", headers=_auth(token)
            )
        assert resp.status_code == 404

    def test_get_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get(
                "/api/v1/flows/nonexistent/execution-hooks/any-id", headers=_auth(token)
            )
        assert resp.status_code == 404

    def test_get_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            hook = _add_hook(client, token, flow_id)
            hook_id = hook["hook_id"]
            resp = client.get(f"/api/v1/flows/{flow_id}/execution-hooks/{hook_id}")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Tests — DELETE /flows/{id}/execution-hooks/{hook_id}
# ---------------------------------------------------------------------------


class TestFlowExecutionHookDelete:
    def test_delete_removes_hook(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            hook = _add_hook(client, token, flow_id)
            hook_id = hook["hook_id"]
            resp = client.delete(
                f"/api/v1/flows/{flow_id}/execution-hooks/{hook_id}", headers=_auth(token)
            )
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True
        assert resp.json()["hook_id"] == hook_id
        assert resp.json()["flow_id"] == flow_id

    def test_delete_then_get_404(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            hook = _add_hook(client, token, flow_id)
            hook_id = hook["hook_id"]
            client.delete(
                f"/api/v1/flows/{flow_id}/execution-hooks/{hook_id}", headers=_auth(token)
            )
            resp = client.get(
                f"/api/v1/flows/{flow_id}/execution-hooks/{hook_id}", headers=_auth(token)
            )
        assert resp.status_code == 404

    def test_delete_404_not_found(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.delete(
                f"/api/v1/flows/{flow_id}/execution-hooks/no-such-hook", headers=_auth(token)
            )
        assert resp.status_code == 404

    def test_delete_404_unknown_flow(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.delete(
                "/api/v1/flows/nonexistent/execution-hooks/any-id", headers=_auth(token)
            )
        assert resp.status_code == 404

    def test_delete_requires_auth(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            hook = _add_hook(client, token, flow_id)
            hook_id = hook["hook_id"]
            resp = client.delete(f"/api/v1/flows/{flow_id}/execution-hooks/{hook_id}")
        assert resp.status_code == 401
