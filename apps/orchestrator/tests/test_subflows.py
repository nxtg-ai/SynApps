"""
N-38: Workflow Subflows — Reusable Components
Tests for SubflowRegistry, SubflowApplet, and subflow endpoints.
"""

import asyncio
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from apps.orchestrator.main import (
    AppletMessage,
    FlowRepository,
    SubflowApplet,
    SubflowRegistry,
    app,
    subflow_registry,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _register(client: TestClient, email: str | None = None) -> str:
    """Register a user and return the access token."""
    email = email or f"subflow-{uuid.uuid4().hex[:8]}@test.com"
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "SubPass1!"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _make_message(
    content: object = "hello",
    context: dict | None = None,
    node_data: dict | None = None,
) -> AppletMessage:
    return AppletMessage(
        content=content,
        context=context or {},
        metadata={"node_id": "n1", "node_data": node_data or {}},
    )


def _simple_flow(flow_id: str = "sub-flow-1") -> dict:
    """A minimal two-node (start → end) subflow."""
    return {
        "id": flow_id,
        "name": "Simple Subflow",
        "nodes": [
            {"id": "s1", "type": "start", "position": {"x": 0, "y": 0}},
            {"id": "e1", "type": "end", "position": {"x": 200, "y": 0}},
        ],
        "edges": [{"id": "ed1", "source": "s1", "target": "e1"}],
    }


# ---------------------------------------------------------------------------
# TestSubflowRegistry (5 tests)
# ---------------------------------------------------------------------------


class TestSubflowRegistry:
    """Unit tests for SubflowRegistry enter/exit/reset semantics."""

    def setup_method(self):
        subflow_registry.reset()

    def teardown_method(self):
        subflow_registry.reset()

    def test_enter_records_active_execution(self):
        """enter() adds (run, flow) without raising when first call."""
        reg = SubflowRegistry()
        reg.enter("run-1", "flow-A")
        # Verify state via re-entry raising — if it's tracked, second enter raises
        with pytest.raises(RuntimeError, match="Circular"):
            reg.enter("run-1", "flow-A")

    def test_exit_removes_entry(self):
        """exit() removes the tracked (run, flow) so re-entry is safe."""
        reg = SubflowRegistry()
        reg.enter("run-1", "flow-A")
        reg.exit("run-1", "flow-A")
        # After exit, entering the same combo again must not raise
        reg.enter("run-1", "flow-A")  # should not raise

    def test_circular_reference_detected(self):
        """enter() raises RuntimeError when same run re-enters same flow."""
        reg = SubflowRegistry()
        reg.enter("run-1", "flow-X")
        with pytest.raises(RuntimeError, match="Circular subflow reference detected"):
            reg.enter("run-1", "flow-X")

    def test_nested_different_flows_ok(self):
        """Same run may enter different flows (A then B) without error."""
        reg = SubflowRegistry()
        reg.enter("run-1", "flow-A")
        reg.enter("run-1", "flow-B")  # should not raise
        reg.exit("run-1", "flow-A")
        reg.exit("run-1", "flow-B")

    def test_reset_clears_all_state(self):
        """reset() removes all entries; subsequent enter() must succeed."""
        reg = SubflowRegistry()
        reg.enter("run-1", "flow-A")
        reg.enter("run-2", "flow-B")
        reg.reset()
        # Both entries must be gone
        reg.enter("run-1", "flow-A")  # should not raise
        reg.enter("run-2", "flow-B")  # should not raise

    def test_multiple_parents_independent(self):
        """Different parent run IDs may each independently execute the same flow."""
        reg = SubflowRegistry()
        reg.enter("run-1", "flow-X")
        reg.enter("run-2", "flow-X")  # different parent — must not raise
        reg.exit("run-1", "flow-X")
        reg.exit("run-2", "flow-X")


# ---------------------------------------------------------------------------
# TestSubflowApplet (8 tests)
# ---------------------------------------------------------------------------


class TestSubflowApplet:
    """Unit tests for SubflowApplet.on_message()."""

    def setup_method(self):
        subflow_registry.reset()

    def teardown_method(self):
        subflow_registry.reset()

    @pytest.mark.asyncio
    async def test_basic_execution_returns_output(self):
        """on_message() with valid workflow_id returns a result dict."""
        flow_id = f"flow-{uuid.uuid4().hex[:8]}"
        flow = _simple_flow(flow_id)

        with patch.object(FlowRepository, "get_by_id", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = flow
            applet = SubflowApplet()
            msg = _make_message(
                content={"prompt": "hi"},
                context={"run_id": "parent-run-1"},
                node_data={"workflow_id": flow_id, "output_key": "result"},
            )
            response = await applet.on_message(msg)

        assert isinstance(response.content, dict)
        assert "result" in response.content
        assert response.content["_subflow_id"] == flow_id

    @pytest.mark.asyncio
    async def test_depth_limit_exceeded_raises(self):
        """on_message() raises ValueError when _subflow_depth >= max_depth."""
        applet = SubflowApplet()
        msg = _make_message(
            context={"run_id": "r1", "_subflow_depth": 3},
            node_data={"workflow_id": "any-flow", "max_depth": 3},
        )
        with pytest.raises(ValueError, match="Maximum subflow depth"):
            await applet.on_message(msg)

    @pytest.mark.asyncio
    async def test_workflow_not_found_raises(self):
        """on_message() raises ValueError when the target workflow doesn't exist."""
        with patch.object(FlowRepository, "get_by_id", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None
            applet = SubflowApplet()
            msg = _make_message(
                context={"run_id": "r1"},
                node_data={"workflow_id": "missing-flow"},
            )
            with pytest.raises(ValueError, match="not found"):
                await applet.on_message(msg)

    @pytest.mark.asyncio
    async def test_input_mapping_resolves_templates(self):
        """input_mapping values are rendered using template expressions."""
        flow_id = f"flow-{uuid.uuid4().hex[:8]}"
        flow = _simple_flow(flow_id)

        captured_inputs: list[dict] = []

        async def _fake_execute(flow_dict, input_data, sub_ctx):
            captured_inputs.append(input_data)
            return "sub-output"

        with patch.object(FlowRepository, "get_by_id", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = flow
            with patch.object(SubflowApplet, "_execute_inline", new=_fake_execute):
                applet = SubflowApplet()
                msg = _make_message(
                    content={"user_query": "What is AI?"},
                    context={"run_id": "r1"},
                    node_data={
                        "workflow_id": flow_id,
                        "input_mapping": {"topic": "{{user_query}}"},
                    },
                )
                await applet.on_message(msg)

        assert len(captured_inputs) >= 1
        assert captured_inputs[0].get("topic") == "What is AI?"

    @pytest.mark.asyncio
    async def test_output_key_in_result(self):
        """Result dict uses the configured output_key."""
        flow_id = "flow-key-test"
        flow = _simple_flow(flow_id)

        async def _fake_execute(flow_dict, input_data, sub_ctx):
            return {"answer": 42}

        with patch.object(FlowRepository, "get_by_id", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = flow
            with patch.object(SubflowApplet, "_execute_inline", new=_fake_execute):
                applet = SubflowApplet()
                msg = _make_message(
                    context={"run_id": "r1"},
                    node_data={"workflow_id": flow_id, "output_key": "my_custom_key"},
                )
                response = await applet.on_message(msg)

        assert "my_custom_key" in response.content
        assert response.content["my_custom_key"] == {"answer": 42}

    @pytest.mark.asyncio
    async def test_circular_detection_via_registry(self):
        """SubflowRegistry detects when same run+flow pair enters twice."""
        flow_id = "circular-flow"
        flow = _simple_flow(flow_id)

        # Manually pre-register the entry to simulate circular invocation
        subflow_registry.enter("parent-run", flow_id)

        with patch.object(FlowRepository, "get_by_id", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = flow
            applet = SubflowApplet()
            msg = _make_message(
                context={"run_id": "parent-run"},
                node_data={"workflow_id": flow_id},
            )
            with pytest.raises(RuntimeError, match="Circular"):
                await applet.on_message(msg)

    @pytest.mark.asyncio
    async def test_timeout_raises_timeout_error(self):
        """on_message() propagates TimeoutError when _execute_inline is too slow."""
        flow_id = "slow-flow"
        flow = _simple_flow(flow_id)

        async def _slow_execute(flow_dict, input_data, sub_ctx):
            await asyncio.sleep(999)

        with patch.object(FlowRepository, "get_by_id", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = flow
            with patch.object(SubflowApplet, "_execute_inline", new=_slow_execute):
                applet = SubflowApplet()
                msg = _make_message(
                    context={"run_id": "r1"},
                    node_data={"workflow_id": flow_id, "timeout_seconds": 0.05},
                )
                with pytest.raises((asyncio.TimeoutError, TimeoutError)):
                    await applet.on_message(msg)

    @pytest.mark.asyncio
    async def test_nested_depth_tracking(self):
        """Sub-context carries _subflow_depth incremented by one."""
        flow_id = "depth-track-flow"
        flow = _simple_flow(flow_id)
        captured_contexts: list[dict] = []

        async def _capture_execute(flow_dict, input_data, sub_ctx):
            captured_contexts.append(dict(sub_ctx))
            return "ok"

        with patch.object(FlowRepository, "get_by_id", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = flow
            with patch.object(SubflowApplet, "_execute_inline", new=_capture_execute):
                applet = SubflowApplet()
                msg = _make_message(
                    context={"run_id": "r1", "_subflow_depth": 1},
                    node_data={"workflow_id": flow_id},
                )
                await applet.on_message(msg)

        assert len(captured_contexts) >= 1
        assert captured_contexts[0]["_subflow_depth"] == 2


# ---------------------------------------------------------------------------
# TestSubflowEndpoints (7 tests)
# ---------------------------------------------------------------------------


class TestSubflowEndpoints:
    """Integration tests against the HTTP endpoints."""

    def setup_method(self):
        subflow_registry.reset()

    def teardown_method(self):
        subflow_registry.reset()

    def test_list_subflows_returns_list(self):
        """GET /subflows returns a list with at least a total count."""
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get("/api/v1/subflows", headers=_auth(token))

        assert resp.status_code == 200
        data = resp.json()
        assert "flows" in data
        assert isinstance(data["flows"], list)
        assert "total" in data
        assert isinstance(data["total"], int)
        assert data["total"] >= 0  # Gate 2: explicit count check

    def test_list_subflows_requires_auth(self):
        """GET /subflows without auth returns 401 (after bootstrap disabled)."""
        with TestClient(app) as client:
            _register(client)  # register a user to disable anonymous bootstrap
            resp = client.get("/api/v1/subflows")
        assert resp.status_code in (401, 403)

    def test_list_subflows_includes_flag(self):
        """Each entry in GET /subflows carries is_subflow_compatible: true."""
        flow_id = f"sf-{uuid.uuid4().hex[:8]}"
        flow_data = {
            "id": flow_id,
            "name": "A Subflow",
            "nodes": [],
            "edges": [],
        }

        async def _get_all():
            return [flow_data]

        with patch.object(FlowRepository, "get_all", new=_get_all):
            with TestClient(app) as client:
                token = _register(client)
                resp = client.get("/api/v1/subflows", headers=_auth(token))

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["flows"]) >= 1  # Gate 2
        assert data["flows"][0]["is_subflow_compatible"] is True

    def test_validate_subflow_valid_case(self):
        """POST /subflows/validate returns valid=true for non-circular pair."""
        parent_id = f"parent-{uuid.uuid4().hex[:8]}"
        child_id = f"child-{uuid.uuid4().hex[:8]}"

        parent_flow = {"id": parent_id, "name": "Parent", "nodes": [], "edges": []}
        child_flow = {"id": child_id, "name": "Child", "nodes": [], "edges": []}

        async def _get_by_id(fid):
            if fid == parent_id:
                return parent_flow
            if fid == child_id:
                return child_flow
            return None

        with patch.object(FlowRepository, "get_by_id", new=_get_by_id):
            with TestClient(app) as client:
                token = _register(client)
                resp = client.post(
                    "/api/v1/subflows/validate",
                    json={"parent_flow_id": parent_id, "subflow_id": child_id},
                    headers=_auth(token),
                )

        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True
        assert data["error"] is None

    def test_validate_subflow_circular_case(self):
        """POST /subflows/validate returns valid=false when child references parent."""
        parent_id = f"parent-{uuid.uuid4().hex[:8]}"
        child_id = f"child-{uuid.uuid4().hex[:8]}"

        parent_flow = {"id": parent_id, "name": "Parent", "nodes": [], "edges": []}
        # Child flow contains a subflow node pointing back to the parent
        child_flow = {
            "id": child_id,
            "name": "Child",
            "nodes": [
                {
                    "id": "sf-node",
                    "type": "subflow",
                    "data": {"workflow_id": parent_id},
                }
            ],
            "edges": [],
        }

        async def _get_by_id(fid):
            if fid == parent_id:
                return parent_flow
            if fid == child_id:
                return child_flow
            return None

        with patch.object(FlowRepository, "get_by_id", new=_get_by_id):
            with TestClient(app) as client:
                token = _register(client)
                resp = client.post(
                    "/api/v1/subflows/validate",
                    json={"parent_flow_id": parent_id, "subflow_id": child_id},
                    headers=_auth(token),
                )

        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is False
        assert data["error"] is not None
        assert len(data["error"]) > 0

    def test_validate_subflow_missing_workflow(self):
        """POST /subflows/validate returns valid=false when subflow_id doesn't exist."""
        parent_id = f"parent-{uuid.uuid4().hex[:8]}"
        parent_flow = {"id": parent_id, "name": "Parent", "nodes": [], "edges": []}

        async def _get_by_id(fid):
            if fid == parent_id:
                return parent_flow
            return None

        with patch.object(FlowRepository, "get_by_id", new=_get_by_id):
            with TestClient(app) as client:
                token = _register(client)
                resp = client.post(
                    "/api/v1/subflows/validate",
                    json={"parent_flow_id": parent_id, "subflow_id": "nonexistent-id"},
                    headers=_auth(token),
                )

        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is False
        assert data["error"] is not None

    def test_validate_subflow_self_reference(self):
        """POST /subflows/validate returns valid=false when parent_flow_id == subflow_id."""
        flow_id = f"flow-{uuid.uuid4().hex[:8]}"
        flow = {"id": flow_id, "name": "SomeFlow", "nodes": [], "edges": []}

        async def _get_by_id(fid):
            return flow if fid == flow_id else None

        with patch.object(FlowRepository, "get_by_id", new=_get_by_id):
            with TestClient(app) as client:
                token = _register(client)
                resp = client.post(
                    "/api/v1/subflows/validate",
                    json={"parent_flow_id": flow_id, "subflow_id": flow_id},
                    headers=_auth(token),
                )

        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is False
        assert "itself" in (data["error"] or "")
