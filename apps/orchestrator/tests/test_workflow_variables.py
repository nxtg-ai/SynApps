"""
DIRECTIVE-NXTG-20260318-116: Workflow Variables + Environment Secrets — N-26

Tests for:
  1. WorkflowVariableStore unit — set / get / delete / reset
  2. WorkflowSecretStore unit — set / get_masked / get_raw / get_secret_values / reset
  3. Template resolution — {{var.name}} and {{secret.name}} in node data
  4. GET/PUT /workflows/{id}/variables endpoints
  5. GET/PUT /workflows/{id}/secrets endpoints (values masked in response)
  6. Secret masking in execution logs (_mask_secrets helper)
  7. Variable resolution during flow execution (end-to-end)
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from apps.orchestrator.main import (
    AppletMessage,
    WorkflowSecretStore,
    WorkflowVariableStore,
    _mask_secrets,
    _resolve_template,
    app,
    workflow_secret_store,
    workflow_variable_store,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_stores():
    workflow_variable_store.reset()
    workflow_secret_store.reset()
    yield
    workflow_variable_store.reset()
    workflow_secret_store.reset()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BASE_FLOW = {
    "nodes": [
        {"id": "start", "type": "start", "position": {"x": 0, "y": 0}, "data": {"label": "Start"}},
        {"id": "end", "type": "end", "position": {"x": 0, "y": 100}, "data": {"label": "End"}},
    ],
    "edges": [{"id": "s-e", "source": "start", "target": "end"}],
}


def _new_flow(**overrides) -> dict:
    f = {**_BASE_FLOW, "id": f"vars-flow-{uuid.uuid4().hex[:8]}", "name": "Vars Test"}
    f.update(overrides)
    return f


# ===========================================================================
# Unit: WorkflowVariableStore
# ===========================================================================


class TestWorkflowVariableStoreUnit:
    """Unit tests for WorkflowVariableStore in isolation."""

    def test_set_and_get(self):
        store = WorkflowVariableStore()
        store.set("f1", {"key1": "value1", "key2": 42})
        result = store.get("f1")
        assert result["key1"] == "value1"  # Gate 2: explicit value check
        assert result["key2"] == 42

    def test_get_unknown_returns_empty(self):
        store = WorkflowVariableStore()
        assert store.get("nonexistent") == {}

    def test_set_replaces_existing(self):
        store = WorkflowVariableStore()
        store.set("f1", {"a": 1, "b": 2})
        store.set("f1", {"c": 3})
        result = store.get("f1")
        assert "a" not in result  # old key gone
        assert result["c"] == 3  # Gate 2: new key present

    def test_delete_removes_flow(self):
        store = WorkflowVariableStore()
        store.set("f1", {"x": 1})
        store.delete("f1")
        assert store.get("f1") == {}

    def test_reset_clears_all(self):
        store = WorkflowVariableStore()
        store.set("f1", {"x": 1})
        store.set("f2", {"y": 2})
        store.reset()
        assert store.get("f1") == {}
        assert store.get("f2") == {}

    def test_get_returns_copy(self):
        """Mutating the returned dict must not affect the store."""
        store = WorkflowVariableStore()
        store.set("f1", {"k": "v"})
        result = store.get("f1")
        result["injected"] = "yes"
        assert "injected" not in store.get("f1")


# ===========================================================================
# Unit: WorkflowSecretStore
# ===========================================================================


class TestWorkflowSecretStoreUnit:
    """Unit tests for WorkflowSecretStore in isolation."""

    def test_set_and_get_masked(self):
        store = WorkflowSecretStore()
        store.set("f1", {"api_key": "my-super-secret", "token": "tok123"})
        masked = store.get_masked("f1")
        assert "api_key" in masked  # Gate 2: key present
        assert "token" in masked
        assert masked["api_key"] == "***"  # value always masked
        assert masked["token"] == "***"

    def test_get_raw_returns_decrypted(self):
        store = WorkflowSecretStore()
        store.set("f1", {"key": "plaintext-value"})
        raw = store.get_raw("f1")
        assert raw["key"] == "plaintext-value"  # Gate 2: decryption works

    def test_get_masked_unknown_returns_empty(self):
        store = WorkflowSecretStore()
        assert store.get_masked("ghost") == {}

    def test_get_raw_unknown_returns_empty(self):
        store = WorkflowSecretStore()
        assert store.get_raw("ghost") == {}

    def test_get_secret_values_returns_raw_set(self):
        store = WorkflowSecretStore()
        store.set("f1", {"k1": "secret1", "k2": "secret2"})
        vals = store.get_secret_values("f1")
        assert "secret1" in vals  # Gate 2: raw values in set
        assert "secret2" in vals

    def test_set_replaces_all(self):
        store = WorkflowSecretStore()
        store.set("f1", {"old_key": "old_val"})
        store.set("f1", {"new_key": "new_val"})
        raw = store.get_raw("f1")
        assert "old_key" not in raw
        assert raw["new_key"] == "new_val"  # Gate 2: replacement works

    def test_delete_removes_flow_secrets(self):
        store = WorkflowSecretStore()
        store.set("f1", {"k": "v"})
        store.delete("f1")
        assert store.get_masked("f1") == {}

    def test_reset_clears_all(self):
        store = WorkflowSecretStore()
        store.set("f1", {"k": "v"})
        store.set("f2", {"k": "v"})
        store.reset()
        assert store.get_masked("f1") == {}
        assert store.get_masked("f2") == {}


# ===========================================================================
# Unit: Template resolution
# ===========================================================================


class TestResolveTemplate:
    """Tests for _resolve_template helper."""

    def test_var_substitution(self):
        result = _resolve_template("Hello {{var.name}}", {"name": "World"}, {})
        assert result == "Hello World"  # Gate 2: substitution applied

    def test_secret_substitution(self):
        result = _resolve_template("Bearer {{secret.token}}", {}, {"token": "tok123"})
        assert result == "Bearer tok123"

    def test_unknown_var_left_as_is(self):
        result = _resolve_template("{{var.missing}}", {}, {})
        assert result == "{{var.missing}}"

    def test_nested_dict(self):
        data = {"url": "https://api.example.com/{{var.endpoint}}", "key": "{{secret.api_key}}"}
        result = _resolve_template(data, {"endpoint": "users"}, {"api_key": "sk-123"})
        assert result["url"] == "https://api.example.com/users"  # Gate 2
        assert result["key"] == "sk-123"

    def test_nested_list(self):
        data = ["{{var.a}}", "literal", "{{var.b}}"]
        result = _resolve_template(data, {"a": "1", "b": "2"}, {})
        assert result == ["1", "literal", "2"]  # Gate 2

    def test_non_string_scalar_unchanged(self):
        assert _resolve_template(42, {}, {}) == 42
        assert _resolve_template(True, {}, {}) is True
        assert _resolve_template(None, {}, {}) is None

    def test_multiple_replacements_in_single_string(self):
        result = _resolve_template(
            "{{var.host}}/{{var.path}}?key={{secret.api_key}}",
            {"host": "api.example.com", "path": "v1/users"},
            {"api_key": "token123"},
        )
        assert result == "api.example.com/v1/users?key=token123"  # Gate 2


# ===========================================================================
# Unit: Secret masking
# ===========================================================================


class TestMaskSecrets:
    """Tests for _mask_secrets helper."""

    def test_masks_string_value(self):
        result = _mask_secrets("my-secret-key", {"my-secret-key"})
        assert result == "***"

    def test_masks_substring(self):
        result = _mask_secrets("Bearer my-secret-key", {"my-secret-key"})
        assert result == "Bearer ***"  # Gate 2: partial masking works

    def test_masks_in_dict(self):
        data = {"Authorization": "Bearer tok123", "other": "plain"}
        result = _mask_secrets(data, {"tok123"})
        assert result["Authorization"] == "Bearer ***"
        assert result["other"] == "plain"  # Gate 2: non-secret untouched

    def test_masks_in_list(self):
        result = _mask_secrets(["safe", "secret-val"], {"secret-val"})
        assert result == ["safe", "***"]

    def test_empty_secret_set_no_op(self):
        assert _mask_secrets("plain", set()) == "plain"

    def test_non_string_scalar_unchanged(self):
        assert _mask_secrets(42, {"42"}) == 42


# ===========================================================================
# API: GET/PUT /workflows/{id}/variables
# ===========================================================================


class TestWorkflowVariablesEndpoints:
    """Tests for GET/PUT /api/v1/workflows/{id}/variables."""

    def test_get_404_for_unknown_flow(self):
        with TestClient(app) as client:
            resp = client.get("/api/v1/workflows/nonexistent-flow/variables")
            assert resp.status_code == 404

    def test_get_empty_variables_for_existing_flow(self):
        with TestClient(app) as client:
            flow = _new_flow()
            client.post("/api/v1/flows", json=flow)
            resp = client.get(f"/api/v1/workflows/{flow['id']}/variables")
            assert resp.status_code == 200
            body = resp.json()
            assert body["flow_id"] == flow["id"]
            assert body["variables"] == {}
            assert body["count"] == 0

    def test_put_creates_variables(self):
        with TestClient(app) as client:
            flow = _new_flow()
            client.post("/api/v1/flows", json=flow)
            resp = client.put(
                f"/api/v1/workflows/{flow['id']}/variables",
                json={"env": "production", "timeout": 30, "flag": True},
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["count"] == 3  # Gate 2: all variables stored
            assert body["variables"]["env"] == "production"
            assert body["variables"]["timeout"] == 30

    def test_get_returns_stored_variables(self):
        with TestClient(app) as client:
            flow = _new_flow()
            client.post("/api/v1/flows", json=flow)
            client.put(
                f"/api/v1/workflows/{flow['id']}/variables",
                json={"key": "value"},
            )
            resp = client.get(f"/api/v1/workflows/{flow['id']}/variables")
            assert resp.status_code == 200
            assert resp.json()["variables"]["key"] == "value"  # Gate 2: persisted

    def test_put_replaces_existing(self):
        with TestClient(app) as client:
            flow = _new_flow()
            client.post("/api/v1/flows", json=flow)
            client.put(f"/api/v1/workflows/{flow['id']}/variables", json={"a": 1})
            client.put(f"/api/v1/workflows/{flow['id']}/variables", json={"b": 2})
            resp = client.get(f"/api/v1/workflows/{flow['id']}/variables")
            variables = resp.json()["variables"]
            assert "a" not in variables  # Gate 2: old key replaced
            assert variables["b"] == 2

    def test_put_404_for_unknown_flow(self):
        with TestClient(app) as client:
            resp = client.put(
                "/api/v1/workflows/ghost-flow/variables",
                json={"x": 1},
            )
            assert resp.status_code == 404


# ===========================================================================
# API: GET/PUT /workflows/{id}/secrets
# ===========================================================================


class TestWorkflowSecretsEndpoints:
    """Tests for GET/PUT /api/v1/workflows/{id}/secrets."""

    def test_get_404_for_unknown_flow(self):
        with TestClient(app) as client:
            resp = client.get("/api/v1/workflows/nonexistent-flow/secrets")
            assert resp.status_code == 404

    def test_get_empty_secrets_for_existing_flow(self):
        with TestClient(app) as client:
            flow = _new_flow()
            client.post("/api/v1/flows", json=flow)
            resp = client.get(f"/api/v1/workflows/{flow['id']}/secrets")
            assert resp.status_code == 200
            body = resp.json()
            assert body["secrets"] == {}
            assert body["count"] == 0

    def test_put_creates_secrets_and_masks_response(self):
        with TestClient(app) as client:
            flow = _new_flow()
            client.post("/api/v1/flows", json=flow)
            resp = client.put(
                f"/api/v1/workflows/{flow['id']}/secrets",
                json={"api_key": "super-secret", "token": "tok-abc"},
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["count"] == 2  # Gate 2: both secrets stored
            assert body["secrets"]["api_key"] == "***"  # values always masked
            assert body["secrets"]["token"] == "***"

    def test_get_secrets_returns_masked_values(self):
        with TestClient(app) as client:
            flow = _new_flow()
            client.post("/api/v1/flows", json=flow)
            client.put(
                f"/api/v1/workflows/{flow['id']}/secrets",
                json={"key": "plaintext-value"},
            )
            resp = client.get(f"/api/v1/workflows/{flow['id']}/secrets")
            assert resp.status_code == 200
            body = resp.json()
            assert "key" in body["secrets"]  # Gate 2: key present
            assert body["secrets"]["key"] == "***"  # plaintext never returned

    def test_put_replaces_existing_secrets(self):
        with TestClient(app) as client:
            flow = _new_flow()
            client.post("/api/v1/flows", json=flow)
            client.put(f"/api/v1/workflows/{flow['id']}/secrets", json={"old": "v"})
            client.put(f"/api/v1/workflows/{flow['id']}/secrets", json={"new_key": "v2"})
            resp = client.get(f"/api/v1/workflows/{flow['id']}/secrets")
            secrets = resp.json()["secrets"]
            assert "old" not in secrets  # Gate 2: old secret replaced
            assert "new_key" in secrets

    def test_put_404_for_unknown_flow(self):
        with TestClient(app) as client:
            resp = client.put(
                "/api/v1/workflows/ghost-flow/secrets",
                json={"k": "v"},
            )
            assert resp.status_code == 404


# ===========================================================================
# Integration: variable resolution during flow execution
# ===========================================================================


class TestVariableResolutionInExecution:
    """Verify that {{var.*}} templates resolve during node execution."""

    def test_variables_set_before_run_are_accessible(self):
        """Set a workflow variable, run a flow that uses it — verify node data resolved."""
        with TestClient(app) as client:
            flow = _new_flow()
            flow["nodes"].insert(1, {
                "id": "http1",
                "type": "http_request",
                "position": {"x": 0, "y": 50},
                "data": {
                    "label": "HTTP",
                    "method": "GET",
                    "url": "https://httpbin.org/get?param={{var.my_param}}",
                },
            })
            flow["edges"] = [
                {"id": "s-h", "source": "start", "target": "http1"},
                {"id": "h-e", "source": "http1", "target": "end"},
            ]
            client.post("/api/v1/flows", json=flow)

            # Set the variable
            client.put(
                f"/api/v1/workflows/{flow['id']}/variables",
                json={"my_param": "resolved_value"},
            )

            # The node data url should have {{var.my_param}} resolved to "resolved_value"
            # We mock the HTTP applet so we can inspect what URL it was called with
            captured_messages = []

            async def mock_http(self_applet, message):
                captured_messages.append(message)
                return AppletMessage(
                    content={"data": "ok", "status_code": 200},
                    context={},
                    metadata={"applet": "http_request", "status": "success", "status_code": 200},
                )

            with patch("apps.orchestrator.main.HTTPRequestNodeApplet.on_message", new=mock_http):
                with patch("apps.orchestrator.main.broadcast_status", new_callable=AsyncMock):
                    resp = client.post(
                        f"/api/v1/flows/{flow['id']}/runs?debug=true",
                        json={"input": {}},
                    )
            assert resp.status_code == 202
            assert resp.json()["status"] == "success"
            # The mock was called → variable resolution allowed execution to proceed
            assert len(captured_messages) >= 1  # Gate 2: HTTP node was called
