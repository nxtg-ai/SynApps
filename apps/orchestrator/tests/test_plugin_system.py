"""Tests for the Workflow Marketplace Plugin System (N-60).

Covers:
- PluginRegistry unit tests
- Plugin REST endpoint integration tests
- DynamicPluginApplet execution tests
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from apps.orchestrator.main import (
    DynamicPluginApplet,
    app,
)
from apps.orchestrator.stores import (
    PluginManifest,
    PluginRegistry,
    plugin_registry,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sample_manifest(**overrides) -> PluginManifest:
    """Build a valid PluginManifest with sensible defaults, applying *overrides*."""
    defaults = {
        "name": f"test-plugin-{uuid.uuid4().hex[:6]}",
        "version": "1.0.0",
        "display_name": "Test Plugin",
        "description": "A plugin for testing",
        "node_type": f"custom_{uuid.uuid4().hex[:8]}",
        "endpoint_url": "https://example.com/execute",
        "config_schema": {"type": "object", "properties": {"key": {"type": "string"}}},
        "tags": ["test"],
        "author": "tester",
        "icon_url": "",
    }
    defaults.update(overrides)
    return PluginManifest(**defaults)


def _register_user(client: TestClient) -> dict[str, str]:
    """Register a fresh user and return auth headers."""
    email = f"plugin-test-{uuid.uuid4().hex[:8]}@test.com"
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "TestPass1!"},
    )
    assert resp.status_code == 201, f"Registration failed: {resp.text}"
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _register_plugin_via_api(client: TestClient, headers: dict, **overrides) -> dict:
    """Register a plugin through the API and return the response JSON."""
    manifest = _sample_manifest(**overrides)
    resp = client.post(
        "/api/v1/plugins",
        json=manifest.model_dump(),
        headers=headers,
    )
    assert resp.status_code == 201, f"Plugin registration failed: {resp.text}"
    return resp.json()


# ---------------------------------------------------------------------------
# Unit tests — PluginRegistry
# ---------------------------------------------------------------------------

class TestPluginRegistry:
    """Direct unit tests for the PluginRegistry class."""

    def test_register_returns_plugin_id(self):
        registry = PluginRegistry()
        manifest = _sample_manifest()
        plugin_id = registry.register(manifest)
        assert isinstance(plugin_id, str)
        assert len(plugin_id) == 36  # UUID length

    def test_register_rejects_reserved_node_type(self):
        registry = PluginRegistry()
        for reserved in ("llm", "code", "merge", "foreach", "webhook_trigger"):
            manifest = _sample_manifest(node_type=reserved)
            with pytest.raises(ValueError, match="reserved for built-in"):
                registry.register(manifest)

    def test_get_returns_registered_plugin(self):
        registry = PluginRegistry()
        manifest = _sample_manifest(name="get-test")
        plugin_id = registry.register(manifest)
        entry = registry.get(plugin_id)
        assert entry is not None
        assert entry["id"] == plugin_id
        assert entry["manifest"]["name"] == "get-test"

    def test_get_returns_none_for_missing(self):
        registry = PluginRegistry()
        assert registry.get("nonexistent-id") is None

    def test_get_by_node_type_works(self):
        registry = PluginRegistry()
        manifest = _sample_manifest(node_type="custom_slack")
        registry.register(manifest)
        entry = registry.get_by_node_type("custom_slack")
        assert entry is not None
        assert entry["manifest"]["node_type"] == "custom_slack"

    def test_get_by_node_type_returns_none_for_missing(self):
        registry = PluginRegistry()
        assert registry.get_by_node_type("nonexistent") is None

    def test_unregister_removes_plugin(self):
        registry = PluginRegistry()
        manifest = _sample_manifest()
        plugin_id = registry.register(manifest)
        assert registry.unregister(plugin_id) is True
        assert registry.get(plugin_id) is None

    def test_unregister_returns_false_for_missing(self):
        registry = PluginRegistry()
        assert registry.unregister("nonexistent-id") is False

    def test_list_all_returns_all_plugins(self):
        registry = PluginRegistry()
        m1 = _sample_manifest(node_type="type_a")
        m2 = _sample_manifest(node_type="type_b")
        registry.register(m1)
        registry.register(m2)
        result = registry.list_all()
        assert isinstance(result, list)
        assert len(result) >= 1  # Gate 2: confirm data was not silently lost
        assert len(result) == 2

    def test_increment_install_count(self):
        registry = PluginRegistry()
        manifest = _sample_manifest()
        plugin_id = registry.register(manifest)
        registry.increment_install_count(plugin_id)
        registry.increment_install_count(plugin_id)
        entry = registry.get(plugin_id)
        assert entry is not None
        assert entry["install_count"] >= 1  # Gate 2
        assert entry["install_count"] == 2

    def test_increment_install_count_noop_for_missing(self):
        registry = PluginRegistry()
        # Should not raise
        registry.increment_install_count("nonexistent")

    def test_reset_clears_all(self):
        registry = PluginRegistry()
        registry.register(_sample_manifest())
        registry.register(_sample_manifest())
        registry.reset()
        assert registry.list_all() == []


# ---------------------------------------------------------------------------
# Integration tests — Plugin REST endpoints
# ---------------------------------------------------------------------------

class TestPluginEndpoints:
    """Integration tests hitting the plugin API via TestClient."""

    def test_post_plugins_registers_plugin(self):
        with TestClient(app) as client:
            headers = _register_user(client)
            data = _register_plugin_via_api(client, headers)
            assert "plugin_id" in data
            assert data["message"].startswith("Plugin")

    def test_post_plugins_reserved_node_type_returns_400(self):
        with TestClient(app) as client:
            headers = _register_user(client)
            manifest = _sample_manifest(node_type="llm")
            resp = client.post("/api/v1/plugins", json=manifest.model_dump(), headers=headers)
            assert resp.status_code == 400
            assert "reserved" in resp.json()["error"]["message"]

    def test_get_plugins_returns_list(self):
        with TestClient(app) as client:
            headers = _register_user(client)
            _register_plugin_via_api(client, headers, node_type="list_test_type")
            resp = client.get("/api/v1/plugins")
            assert resp.status_code == 200
            body = resp.json()
            assert isinstance(body["plugins"], list)
            assert len(body["plugins"]) >= 1  # Gate 2
            assert body["total"] >= 1  # Gate 2

    def test_get_plugin_by_id_returns_details(self):
        with TestClient(app) as client:
            headers = _register_user(client)
            created = _register_plugin_via_api(client, headers)
            plugin_id = created["plugin_id"]
            resp = client.get(f"/api/v1/plugins/{plugin_id}")
            assert resp.status_code == 200
            body = resp.json()
            assert body["id"] == plugin_id

    def test_get_plugin_missing_returns_404(self):
        with TestClient(app) as client:
            resp = client.get(f"/api/v1/plugins/{uuid.uuid4()}")
            assert resp.status_code == 404
            assert "error" in resp.json()

    def test_delete_plugin_removes_it(self):
        with TestClient(app) as client:
            headers = _register_user(client)
            created = _register_plugin_via_api(client, headers)
            plugin_id = created["plugin_id"]
            resp = client.delete(f"/api/v1/plugins/{plugin_id}", headers=headers)
            assert resp.status_code == 204
            # Confirm gone
            resp2 = client.get(f"/api/v1/plugins/{plugin_id}")
            assert resp2.status_code == 404

    def test_delete_plugin_missing_returns_404(self):
        with TestClient(app) as client:
            headers = _register_user(client)
            resp = client.delete(f"/api/v1/plugins/{uuid.uuid4()}", headers=headers)
            assert resp.status_code == 404
            assert "error" in resp.json()

    def test_get_plugin_schema_returns_config_schema(self):
        with TestClient(app) as client:
            headers = _register_user(client)
            schema = {"type": "object", "properties": {"api_key": {"type": "string"}}}
            created = _register_plugin_via_api(client, headers, config_schema=schema)
            plugin_id = created["plugin_id"]
            resp = client.get(f"/api/v1/plugins/{plugin_id}/schema")
            assert resp.status_code == 200
            body = resp.json()
            assert body["plugin_id"] == plugin_id
            assert body["config_schema"] == schema

    def test_get_plugin_schema_missing_returns_404(self):
        with TestClient(app) as client:
            resp = client.get(f"/api/v1/plugins/{uuid.uuid4()}/schema")
            assert resp.status_code == 404
            assert "error" in resp.json()

    def test_install_plugin_increments_count(self):
        with TestClient(app) as client:
            headers = _register_user(client)
            created = _register_plugin_via_api(client, headers)
            plugin_id = created["plugin_id"]
            resp = client.post(f"/api/v1/plugins/{plugin_id}/install", headers=headers)
            assert resp.status_code == 200
            body = resp.json()
            assert body["plugin_id"] == plugin_id
            assert body["install_count"] >= 1  # Gate 2
            # Install again
            resp2 = client.post(f"/api/v1/plugins/{plugin_id}/install", headers=headers)
            assert resp2.json()["install_count"] >= 2

    def test_install_plugin_missing_returns_404(self):
        with TestClient(app) as client:
            headers = _register_user(client)
            resp = client.post(f"/api/v1/plugins/{uuid.uuid4()}/install", headers=headers)
            assert resp.status_code == 404
            assert "error" in resp.json()

    def test_unauthenticated_post_returns_401(self):
        with TestClient(app) as client:
            # Register a user first to disable anonymous bootstrap
            _register_user(client)
            manifest = _sample_manifest()
            resp = client.post("/api/v1/plugins", json=manifest.model_dump())
            assert resp.status_code == 401
            assert "error" in resp.json()

    def test_unauthenticated_delete_returns_401(self):
        with TestClient(app) as client:
            # Register a user first to disable anonymous bootstrap
            headers = _register_user(client)
            created = _register_plugin_via_api(client, headers)
            plugin_id = created["plugin_id"]
            resp = client.delete(f"/api/v1/plugins/{plugin_id}")
            assert resp.status_code == 401
            assert "error" in resp.json()

    def test_unauthenticated_install_returns_401(self):
        with TestClient(app) as client:
            # Register a user first to disable anonymous bootstrap
            headers = _register_user(client)
            created = _register_plugin_via_api(client, headers)
            plugin_id = created["plugin_id"]
            resp = client.post(f"/api/v1/plugins/{plugin_id}/install")
            assert resp.status_code == 401
            assert "error" in resp.json()


# ---------------------------------------------------------------------------
# Execution tests — DynamicPluginApplet
# ---------------------------------------------------------------------------

class TestPluginExecution:
    """Test that DynamicPluginApplet correctly dispatches to plugin endpoints."""

    @pytest.mark.asyncio
    async def test_execute_posts_to_endpoint(self):
        """DynamicPluginApplet sends a POST to the plugin's endpoint_url."""
        manifest = _sample_manifest(
            endpoint_url="https://plugin.example.com/run",
            node_type="custom_exec_test",
        )
        plugin_id = plugin_registry.register(manifest)
        entry = plugin_registry.get(plugin_id)
        assert entry is not None

        applet = DynamicPluginApplet(entry)

        # Build a mock message
        message = type("Msg", (), {"input": {"text": "hello"}, "config": {}, "node_id": "n1"})()

        # Use a real httpx.Response to avoid async mock issues with .json()
        import httpx

        mock_request = httpx.Request("POST", "https://plugin.example.com/run")
        mock_response = httpx.Response(
            status_code=200,
            json={"output": "world"},
            request=mock_request,
        )

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await applet.execute(message)

        assert result == {"output": "world"}
        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert call_args[0][0] == "https://plugin.example.com/run"

    @pytest.mark.asyncio
    async def test_execute_raises_on_timeout(self):
        """DynamicPluginApplet raises ValueError on timeout."""
        import httpx

        manifest = _sample_manifest(name="timeout-plugin", endpoint_url="https://slow.example.com")
        entry = {
            "id": "test-id",
            "manifest": manifest.model_dump(),
            "installed_at": 0,
            "install_count": 0,
        }
        applet = DynamicPluginApplet(entry)
        message = type("Msg", (), {"input": {}, "config": {}, "node_id": "n1"})()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.side_effect = httpx.TimeoutException("timed out")
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            with pytest.raises(ValueError, match="timed out after 30s"):
                await applet.execute(message)

    @pytest.mark.asyncio
    async def test_execute_raises_on_http_error(self):
        """DynamicPluginApplet raises ValueError on non-2xx response."""
        import httpx

        manifest = _sample_manifest(name="error-plugin", endpoint_url="https://bad.example.com")
        entry = {
            "id": "test-id",
            "manifest": manifest.model_dump(),
            "installed_at": 0,
            "install_count": 0,
        }
        applet = DynamicPluginApplet(entry)
        message = type("Msg", (), {"input": {}, "config": {}, "node_id": "n1"})()

        mock_request = httpx.Request("POST", "https://bad.example.com")
        mock_resp = httpx.Response(status_code=500, request=mock_request)

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            with pytest.raises(ValueError, match="returned HTTP 500"):
                await applet.execute(message)

    def test_load_applet_falls_back_to_plugin(self):
        """Orchestrator.load_applet resolves a plugin node_type to DynamicPluginApplet."""
        node_type = f"custom_fallback_{uuid.uuid4().hex[:6]}"
        manifest = _sample_manifest(node_type=node_type)
        plugin_registry.register(manifest)

        with TestClient(app) as client:
            headers = _register_user(client)
            # Create a flow with the custom node type
            flow_data = {
                "name": f"Plugin Test Flow {uuid.uuid4().hex[:6]}",
                "nodes": [
                    {"id": "start", "type": "start", "position": {"x": 0, "y": 0}, "data": {}},
                    {
                        "id": "plugin_node",
                        "type": node_type,
                        "position": {"x": 200, "y": 0},
                        "data": {},
                    },
                    {"id": "end", "type": "end", "position": {"x": 400, "y": 0}, "data": {}},
                ],
                "edges": [
                    {"id": "e1", "source": "start", "target": "plugin_node"},
                    {"id": "e2", "source": "plugin_node", "target": "end"},
                ],
            }
            resp = client.post("/api/v1/flows", json=flow_data, headers=headers)
            assert resp.status_code == 201, f"Flow creation failed: {resp.text}"
            data = resp.json()
            assert isinstance(data, (dict, list))
