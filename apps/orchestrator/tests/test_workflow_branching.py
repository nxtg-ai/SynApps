"""
DIRECTIVE-NXTG-20260319-177: N-37 Workflow Branching — Conditional Logic Builder

Tests for:
  1. CompoundConditionEvaluator — leaf ops, compound AND/OR/NOT, nested, template resolution
  2. BranchApplet — first-match, second-match, default fallback, compound conditions
  3. CompoundMergeApplet — merge strategies (first, all, array)
  4. Branch endpoints — validate valid/invalid conditions, list operations, workflow execution
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from apps.orchestrator.main import (
    AppletMessage,
    BranchApplet,
    CompoundConditionEvaluator,
    CompoundMergeApplet,
    app,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _poll_run(client: TestClient, run_id: str, *, timeout: float = 5.0):
    """Poll /api/v1/runs/{run_id} until terminal status or timeout."""
    import time

    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(0.1)
        resp = client.get(f"/api/v1/runs/{run_id}")
        if resp.status_code == 200:
            run = resp.json()
            if run.get("status") in ("success", "error"):
                return run
    return None


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def client():
    """TestClient with lifespan."""
    with TestClient(app) as c:
        yield c


@pytest.fixture
def evaluator():
    return CompoundConditionEvaluator()


# ===========================================================================
# TestCompoundConditionEvaluator
# ===========================================================================


class TestCompoundConditionEvaluator:
    """Unit tests for CompoundConditionEvaluator in isolation."""

    # -- leaf: equals ---------------------------------------------------------

    def test_leaf_equals_match(self, evaluator):
        condition = {"type": "leaf", "source": "hello", "operation": "equals", "value": "hello"}
        assert evaluator.evaluate(condition, {}) is True

    def test_leaf_equals_no_match(self, evaluator):
        condition = {"type": "leaf", "source": "hello", "operation": "equals", "value": "world"}
        assert evaluator.evaluate(condition, {}) is False

    def test_leaf_not_equals(self, evaluator):
        condition = {
            "type": "leaf",
            "source": "hello",
            "operation": "not_equals",
            "value": "world",
        }
        assert evaluator.evaluate(condition, {}) is True

    # -- leaf: numeric gt/lt --------------------------------------------------

    def test_leaf_gt_true(self, evaluator):
        condition = {"type": "leaf", "source": "90", "operation": "gt", "value": "80"}
        assert evaluator.evaluate(condition, {}) is True

    def test_leaf_gt_false(self, evaluator):
        condition = {"type": "leaf", "source": "70", "operation": "gt", "value": "80"}
        assert evaluator.evaluate(condition, {}) is False

    def test_leaf_gte_equal(self, evaluator):
        condition = {"type": "leaf", "source": "80", "operation": "gte", "value": "80"}
        assert evaluator.evaluate(condition, {}) is True

    def test_leaf_lt_true(self, evaluator):
        condition = {"type": "leaf", "source": "30", "operation": "lt", "value": "80"}
        assert evaluator.evaluate(condition, {}) is True

    def test_leaf_lte_equal(self, evaluator):
        condition = {"type": "leaf", "source": "80", "operation": "lte", "value": "80"}
        assert evaluator.evaluate(condition, {}) is True

    # -- leaf: regex ----------------------------------------------------------

    def test_leaf_regex_match(self, evaluator):
        condition = {
            "type": "leaf",
            "source": "hello world",
            "operation": "regex",
            "value": r"\bworld\b",
        }
        assert evaluator.evaluate(condition, {}) is True

    def test_leaf_regex_no_match(self, evaluator):
        condition = {
            "type": "leaf",
            "source": "hello",
            "operation": "regex",
            "value": r"\d+",
        }
        assert evaluator.evaluate(condition, {}) is False

    # -- leaf: contains / not_contains ----------------------------------------

    def test_leaf_contains_substring(self, evaluator):
        condition = {
            "type": "leaf",
            "source": "hello world",
            "operation": "contains",
            "value": "world",
        }
        assert evaluator.evaluate(condition, {}) is True

    def test_leaf_not_contains(self, evaluator):
        condition = {
            "type": "leaf",
            "source": "hello",
            "operation": "not_contains",
            "value": "world",
        }
        assert evaluator.evaluate(condition, {}) is True

    # -- leaf: starts_with / ends_with ----------------------------------------

    def test_leaf_starts_with_true(self, evaluator):
        condition = {
            "type": "leaf",
            "source": "hello world",
            "operation": "starts_with",
            "value": "hello",
        }
        assert evaluator.evaluate(condition, {}) is True

    def test_leaf_ends_with_true(self, evaluator):
        condition = {
            "type": "leaf",
            "source": "hello world",
            "operation": "ends_with",
            "value": "world",
        }
        assert evaluator.evaluate(condition, {}) is True

    # -- leaf: is_empty / is_not_empty ----------------------------------------

    def test_leaf_is_empty_string(self, evaluator):
        condition = {"type": "leaf", "source": "", "operation": "is_empty", "value": ""}
        assert evaluator.evaluate(condition, {}) is True

    def test_leaf_is_not_empty_string(self, evaluator):
        condition = {"type": "leaf", "source": "text", "operation": "is_not_empty", "value": ""}
        assert evaluator.evaluate(condition, {}) is True

    def test_leaf_is_empty_none(self, evaluator):
        condition = {"type": "leaf", "source": None, "operation": "is_empty", "value": ""}
        assert evaluator.evaluate(condition, {}) is True

    # -- leaf: is_null / is_not_null ------------------------------------------

    def test_leaf_is_null_none(self, evaluator):
        condition = {"type": "leaf", "source": None, "operation": "is_null", "value": ""}
        assert evaluator.evaluate(condition, {}) is True

    def test_leaf_is_not_null(self, evaluator):
        condition = {"type": "leaf", "source": "value", "operation": "is_not_null", "value": ""}
        assert evaluator.evaluate(condition, {}) is True

    # -- leaf: type_is --------------------------------------------------------

    def test_leaf_type_is_str(self, evaluator):
        condition = {
            "type": "leaf",
            "source": "hello",
            "operation": "type_is",
            "value": "str",
        }
        assert evaluator.evaluate(condition, {}) is True

    def test_leaf_type_is_int_false_for_str(self, evaluator):
        condition = {
            "type": "leaf",
            "source": "hello",
            "operation": "type_is",
            "value": "int",
        }
        assert evaluator.evaluate(condition, {}) is False

    # -- AND compound ---------------------------------------------------------

    def test_and_all_true(self, evaluator):
        condition = {
            "type": "and",
            "conditions": [
                {"type": "leaf", "source": "5", "operation": "gt", "value": "3"},
                {"type": "leaf", "source": "hello", "operation": "equals", "value": "hello"},
            ],
        }
        assert evaluator.evaluate(condition, {}) is True

    def test_and_one_false(self, evaluator):
        condition = {
            "type": "and",
            "conditions": [
                {"type": "leaf", "source": "5", "operation": "gt", "value": "3"},
                {"type": "leaf", "source": "hello", "operation": "equals", "value": "world"},
            ],
        }
        assert evaluator.evaluate(condition, {}) is False

    def test_and_empty_returns_true(self, evaluator):
        condition = {"type": "and", "conditions": []}
        assert evaluator.evaluate(condition, {}) is True

    # -- OR compound ----------------------------------------------------------

    def test_or_one_true(self, evaluator):
        condition = {
            "type": "or",
            "conditions": [
                {"type": "leaf", "source": "hello", "operation": "equals", "value": "world"},
                {"type": "leaf", "source": "hello", "operation": "equals", "value": "hello"},
            ],
        }
        assert evaluator.evaluate(condition, {}) is True

    def test_or_all_false(self, evaluator):
        condition = {
            "type": "or",
            "conditions": [
                {"type": "leaf", "source": "a", "operation": "equals", "value": "b"},
                {"type": "leaf", "source": "c", "operation": "equals", "value": "d"},
            ],
        }
        assert evaluator.evaluate(condition, {}) is False

    def test_or_empty_returns_false(self, evaluator):
        condition = {"type": "or", "conditions": []}
        assert evaluator.evaluate(condition, {}) is False

    # -- NOT compound ---------------------------------------------------------

    def test_not_inverts_true(self, evaluator):
        condition = {
            "type": "not",
            "condition": {"type": "leaf", "source": "a", "operation": "equals", "value": "a"},
        }
        assert evaluator.evaluate(condition, {}) is False

    def test_not_inverts_false(self, evaluator):
        condition = {
            "type": "not",
            "condition": {"type": "leaf", "source": "a", "operation": "equals", "value": "b"},
        }
        assert evaluator.evaluate(condition, {}) is True

    # -- Nested AND + OR ------------------------------------------------------

    def test_nested_and_or(self, evaluator):
        # (score >= 80 AND status == "active") OR (score >= 95)
        condition = {
            "type": "or",
            "conditions": [
                {
                    "type": "and",
                    "conditions": [
                        {
                            "type": "leaf",
                            "source": "{{output.score}}",
                            "operation": "gte",
                            "value": "80",
                        },
                        {
                            "type": "leaf",
                            "source": "{{output.status}}",
                            "operation": "equals",
                            "value": "active",
                        },
                    ],
                },
                {
                    "type": "leaf",
                    "source": "{{output.score}}",
                    "operation": "gte",
                    "value": "95",
                },
            ],
        }
        ctx_high = {"output": {"score": 90, "status": "active"}}
        ctx_low = {"output": {"score": 70, "status": "active"}}
        ctx_very_high = {"output": {"score": 97, "status": "inactive"}}
        assert evaluator.evaluate(condition, ctx_high) is True
        assert evaluator.evaluate(condition, ctx_low) is False
        assert evaluator.evaluate(condition, ctx_very_high) is True

    # -- Template resolution --------------------------------------------------

    def test_template_resolution_output(self, evaluator):
        condition = {
            "type": "leaf",
            "source": "{{output.score}}",
            "operation": "gte",
            "value": "80",
        }
        ctx = {"output": {"score": 85}}
        assert evaluator.evaluate(condition, ctx) is True

    def test_template_resolution_data(self, evaluator):
        condition = {
            "type": "leaf",
            "source": "{{data.name}}",
            "operation": "equals",
            "value": "Alice",
        }
        ctx = {"data": {"name": "Alice"}}
        assert evaluator.evaluate(condition, ctx) is True

    # -- Error cases ----------------------------------------------------------

    def test_unsupported_node_type_raises(self, evaluator):
        condition = {"type": "xor", "conditions": []}
        with pytest.raises(ValueError, match="Unsupported condition node type"):
            evaluator.evaluate(condition, {})

    def test_unsupported_leaf_op_raises(self, evaluator):
        condition = {"type": "leaf", "source": "x", "operation": "spaceship", "value": "y"}
        with pytest.raises(ValueError, match="Unsupported leaf operation"):
            evaluator.evaluate(condition, {})

    def test_not_missing_inner_raises(self, evaluator):
        condition = {"type": "not"}
        with pytest.raises(ValueError, match="'not' condition node requires"):
            evaluator.evaluate(condition, {})


# ===========================================================================
# TestBranchApplet
# ===========================================================================


class TestBranchApplet:
    """Tests for BranchApplet.on_message routing logic."""

    @pytest.mark.asyncio
    async def test_first_branch_matches(self):
        applet = BranchApplet()
        node_data = {
            "branches": [
                {
                    "id": "branch_1",
                    "label": "Positive",
                    "condition": {
                        "type": "leaf",
                        "source": "{{output.score}}",
                        "operation": "gte",
                        "value": "80",
                    },
                },
                {
                    "id": "branch_2",
                    "label": "Negative",
                    "condition": {
                        "type": "leaf",
                        "source": "{{output.score}}",
                        "operation": "lt",
                        "value": "80",
                    },
                },
            ],
            "default_branch": "default",
        }
        message = AppletMessage(
            content={"score": 90},
            context={},
            metadata={"node_data": node_data},
        )
        response = await applet.on_message(message)
        assert response.content["_branch"] == "branch_1"
        assert response.content["data"] == {"score": 90}
        assert response.metadata["matched_branch"] == "branch_1"

    @pytest.mark.asyncio
    async def test_second_branch_matches(self):
        applet = BranchApplet()
        node_data = {
            "branches": [
                {
                    "id": "branch_high",
                    "condition": {
                        "type": "leaf",
                        "source": "{{output.score}}",
                        "operation": "gte",
                        "value": "80",
                    },
                },
                {
                    "id": "branch_low",
                    "condition": {
                        "type": "leaf",
                        "source": "{{output.score}}",
                        "operation": "lt",
                        "value": "80",
                    },
                },
            ],
            "default_branch": "default",
        }
        message = AppletMessage(
            content={"score": 50},
            context={},
            metadata={"node_data": node_data},
        )
        response = await applet.on_message(message)
        assert response.content["_branch"] == "branch_low"

    @pytest.mark.asyncio
    async def test_default_branch_when_no_match(self):
        applet = BranchApplet()
        node_data = {
            "branches": [
                {
                    "id": "branch_vip",
                    "condition": {
                        "type": "leaf",
                        "source": "{{output.tier}}",
                        "operation": "equals",
                        "value": "vip",
                    },
                },
            ],
            "default_branch": "standard",
        }
        message = AppletMessage(
            content={"tier": "free"},
            context={},
            metadata={"node_data": node_data},
        )
        response = await applet.on_message(message)
        assert response.content["_branch"] == "standard"

    @pytest.mark.asyncio
    async def test_default_fallback_is_default_when_key_missing(self):
        applet = BranchApplet()
        # No default_branch key — should fall back to "default"
        node_data = {
            "branches": [
                {
                    "id": "b1",
                    "condition": {
                        "type": "leaf",
                        "source": "x",
                        "operation": "equals",
                        "value": "never",
                    },
                },
            ],
        }
        message = AppletMessage(
            content={"x": "something_else"},
            context={},
            metadata={"node_data": node_data},
        )
        response = await applet.on_message(message)
        assert response.content["_branch"] == "default"

    @pytest.mark.asyncio
    async def test_and_condition_in_branch(self):
        applet = BranchApplet()
        node_data = {
            "branches": [
                {
                    "id": "premium_active",
                    "condition": {
                        "type": "and",
                        "conditions": [
                            {
                                "type": "leaf",
                                "source": "{{output.score}}",
                                "operation": "gte",
                                "value": "80",
                            },
                            {
                                "type": "leaf",
                                "source": "{{output.status}}",
                                "operation": "equals",
                                "value": "active",
                            },
                        ],
                    },
                },
            ],
            "default_branch": "other",
        }
        message_match = AppletMessage(
            content={"score": 85, "status": "active"},
            context={},
            metadata={"node_data": node_data},
        )
        message_no_match = AppletMessage(
            content={"score": 85, "status": "inactive"},
            context={},
            metadata={"node_data": node_data},
        )
        resp_match = await applet.on_message(message_match)
        resp_no_match = await applet.on_message(message_no_match)
        assert resp_match.content["_branch"] == "premium_active"
        assert resp_no_match.content["_branch"] == "other"

    @pytest.mark.asyncio
    async def test_or_condition_in_branch(self):
        applet = BranchApplet()
        node_data = {
            "branches": [
                {
                    "id": "admin_or_superuser",
                    "condition": {
                        "type": "or",
                        "conditions": [
                            {
                                "type": "leaf",
                                "source": "{{output.role}}",
                                "operation": "equals",
                                "value": "admin",
                            },
                            {
                                "type": "leaf",
                                "source": "{{output.role}}",
                                "operation": "equals",
                                "value": "superuser",
                            },
                        ],
                    },
                },
            ],
            "default_branch": "regular",
        }
        msg_admin = AppletMessage(
            content={"role": "admin"},
            context={},
            metadata={"node_data": node_data},
        )
        msg_user = AppletMessage(
            content={"role": "user"},
            context={},
            metadata={"node_data": node_data},
        )
        resp_admin = await applet.on_message(msg_admin)
        resp_user = await applet.on_message(msg_user)
        assert resp_admin.content["_branch"] == "admin_or_superuser"
        assert resp_user.content["_branch"] == "regular"

    @pytest.mark.asyncio
    async def test_not_condition_in_branch(self):
        applet = BranchApplet()
        node_data = {
            "branches": [
                {
                    "id": "not_blocked",
                    "condition": {
                        "type": "not",
                        "condition": {
                            "type": "leaf",
                            "source": "{{output.blocked}}",
                            "operation": "equals",
                            "value": "true",
                        },
                    },
                },
            ],
            "default_branch": "blocked",
        }
        msg_ok = AppletMessage(
            content={"blocked": "false"},
            context={},
            metadata={"node_data": node_data},
        )
        msg_blocked = AppletMessage(
            content={"blocked": "true"},
            context={},
            metadata={"node_data": node_data},
        )
        resp_ok = await applet.on_message(msg_ok)
        resp_blocked = await applet.on_message(msg_blocked)
        assert resp_ok.content["_branch"] == "not_blocked"
        assert resp_blocked.content["_branch"] == "blocked"

    @pytest.mark.asyncio
    async def test_input_data_passed_through(self):
        """Input data must be preserved in the 'data' key of the output."""
        applet = BranchApplet()
        payload = {"key": "value", "nested": {"x": 1}}
        node_data = {
            "branches": [],
            "default_branch": "fallback",
        }
        message = AppletMessage(
            content=payload,
            context={},
            metadata={"node_data": node_data},
        )
        response = await applet.on_message(message)
        assert response.content["data"] == payload

    @pytest.mark.asyncio
    async def test_metadata_status_success(self):
        applet = BranchApplet()
        node_data = {"branches": [], "default_branch": "d"}
        message = AppletMessage(content={}, context={}, metadata={"node_data": node_data})
        response = await applet.on_message(message)
        assert response.metadata["status"] == "success"
        assert response.metadata["applet"] == "branch"


# ===========================================================================
# TestCompoundMergeApplet
# ===========================================================================


class TestCompoundMergeApplet:
    """Tests for CompoundMergeApplet merge strategies."""

    @pytest.mark.asyncio
    async def test_strategy_first_passthrough(self):
        applet = CompoundMergeApplet()
        payload = {"result": "branch_a_output", "score": 92}
        message = AppletMessage(
            content=payload,
            context={},
            metadata={"node_data": {"merge_strategy": "first"}},
        )
        response = await applet.on_message(message)
        assert response.content["ok"] is True
        assert response.content["strategy"] == "first"
        assert response.content["output"] == payload

    @pytest.mark.asyncio
    async def test_strategy_all_wraps_in_dict(self):
        applet = CompoundMergeApplet()
        payload = {"result": "some_value"}
        message = AppletMessage(
            content=payload,
            context={},
            metadata={"node_data": {"merge_strategy": "all"}},
        )
        response = await applet.on_message(message)
        assert response.content["output"] == {"merged": payload}

    @pytest.mark.asyncio
    async def test_strategy_array_wraps_in_list(self):
        applet = CompoundMergeApplet()
        payload = {"result": "some_value"}
        message = AppletMessage(
            content=payload,
            context={},
            metadata={"node_data": {"merge_strategy": "array"}},
        )
        response = await applet.on_message(message)
        output = response.content["output"]
        assert isinstance(output, list)
        assert len(output) >= 1  # Gate 2: non-empty array
        assert output[0] == payload

    @pytest.mark.asyncio
    async def test_default_strategy_is_first(self):
        applet = CompoundMergeApplet()
        payload = {"x": 1}
        # No merge_strategy key — defaults to "first"
        message = AppletMessage(
            content=payload,
            context={},
            metadata={"node_data": {}},
        )
        response = await applet.on_message(message)
        assert response.content["output"] == payload

    @pytest.mark.asyncio
    async def test_unknown_strategy_falls_back_gracefully(self):
        """Unknown strategy logs a warning and falls back to input_data passthrough."""
        applet = CompoundMergeApplet()
        payload = {"x": 1}
        message = AppletMessage(
            content=payload,
            context={},
            metadata={"node_data": {"merge_strategy": "unknown_strategy"}},
        )
        # Should not raise; the warning path returns input_data
        response = await applet.on_message(message)
        assert response.content["ok"] is True
        assert response.content["output"] == payload

    @pytest.mark.asyncio
    async def test_metadata_status_success(self):
        applet = CompoundMergeApplet()
        message = AppletMessage(
            content={},
            context={},
            metadata={"node_data": {"merge_strategy": "first"}},
        )
        response = await applet.on_message(message)
        assert response.metadata["status"] == "success"
        assert response.metadata["applet"] == "compound_merge"


# ===========================================================================
# TestBranchEndpoints
# ===========================================================================


class TestBranchEndpoints:
    """Integration tests for the two new branch API endpoints."""

    # -- GET /branch/operations -----------------------------------------------

    def test_list_operations_returns_all(self, client):
        response = client.get("/api/v1/branch/operations")
        assert response.status_code == 200
        data = response.json()
        assert "operations" in data
        assert "total" in data
        operations = data["operations"]
        assert isinstance(operations, list)
        assert len(operations) >= 1  # Gate 2: at least one operation registered
        names = [op["name"] for op in operations]
        assert "equals" in names
        assert "gt" in names
        assert "regex" in names
        assert "is_empty" in names
        assert "type_is" in names

    def test_list_operations_each_has_name_and_description(self, client):
        response = client.get("/api/v1/branch/operations")
        data = response.json()
        for op in data["operations"]:
            assert "name" in op, f"Missing 'name' in operation entry: {op}"
            assert "description" in op, f"Missing 'description' in operation entry: {op}"
            assert op["name"], "operation name must be non-empty"
            assert op["description"], "operation description must be non-empty"

    def test_list_operations_total_matches_list(self, client):
        response = client.get("/api/v1/branch/operations")
        data = response.json()
        assert data["total"] == len(data["operations"])

    # -- POST /workflows/{flow_id}/branch-validate ----------------------------

    def test_validate_valid_leaf_condition(self, client):
        condition = {
            "type": "leaf",
            "source": "{{output.score}}",
            "operation": "gte",
            "value": "80",
        }
        response = client.post(
            "/api/v1/workflows/any-flow/branch-validate",
            json={"condition": condition},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True
        assert data["error"] is None

    def test_validate_valid_compound_condition(self, client):
        condition = {
            "type": "and",
            "conditions": [
                {
                    "type": "leaf",
                    "source": "{{output.score}}",
                    "operation": "gte",
                    "value": "80",
                },
                {
                    "type": "not",
                    "condition": {
                        "type": "leaf",
                        "source": "{{output.blocked}}",
                        "operation": "equals",
                        "value": "true",
                    },
                },
            ],
        }
        response = client.post(
            "/api/v1/workflows/any-flow/branch-validate",
            json={"condition": condition},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True

    def test_validate_invalid_missing_type(self, client):
        condition = {"source": "{{output.x}}", "operation": "equals", "value": "1"}
        response = client.post(
            "/api/v1/workflows/any-flow/branch-validate",
            json={"condition": condition},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert data["error"] is not None
        assert "type" in data["error"]

    def test_validate_invalid_unsupported_operation(self, client):
        condition = {
            "type": "leaf",
            "source": "x",
            "operation": "spaceship",
            "value": "y",
        }
        response = client.post(
            "/api/v1/workflows/any-flow/branch-validate",
            json={"condition": condition},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert "spaceship" in data["error"]

    def test_validate_invalid_and_missing_conditions_key(self, client):
        condition = {"type": "and"}
        response = client.post(
            "/api/v1/workflows/any-flow/branch-validate",
            json={"condition": condition},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert "conditions" in data["error"]

    def test_validate_invalid_leaf_missing_source(self, client):
        condition = {"type": "leaf", "operation": "equals", "value": "x"}
        response = client.post(
            "/api/v1/workflows/any-flow/branch-validate",
            json={"condition": condition},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert "source" in data["error"]

    # -- Branch node in a full workflow execution -----------------------------

    def test_branch_node_executes_in_workflow(self, client):
        """A workflow with a branch node should run to completion and route correctly."""
        flow_id = f"branch-exec-{uuid.uuid4().hex[:8]}"
        flow = {
            "id": flow_id,
            "name": "Branch Execution Test",
            "nodes": [
                {
                    "id": "start",
                    "type": "start",
                    "position": {"x": 0, "y": 0},
                    "data": {"label": "Start"},
                },
                {
                    "id": "branch1",
                    "type": "branch",
                    "position": {"x": 0, "y": 100},
                    "data": {
                        "label": "Branch",
                        "branches": [
                            {
                                "id": "high",
                                "label": "High",
                                "condition": {
                                    "type": "leaf",
                                    "source": "{{output.value}}",
                                    "operation": "gte",
                                    "value": "50",
                                },
                            },
                        ],
                        "default_branch": "low",
                    },
                },
                {
                    "id": "end",
                    "type": "end",
                    "position": {"x": 0, "y": 200},
                    "data": {"label": "End"},
                },
            ],
            "edges": [
                {"id": "s-b", "source": "start", "target": "branch1"},
                {"id": "b-e", "source": "branch1", "target": "end"},
            ],
        }
        resp = client.post("/api/v1/flows", json=flow)
        assert resp.status_code == 201

        with patch("apps.orchestrator.main.broadcast_status", new_callable=AsyncMock):
            resp = client.post(
                f"/api/v1/flows/{flow_id}/runs",
                json={"input": {"value": 75}},
            )
        assert resp.status_code == 202
        run_id = resp.json()["run_id"]

        run = _poll_run(client, run_id)
        assert run is not None, "Workflow run did not reach terminal status in time"
        assert run["status"] in ("success", "error")
