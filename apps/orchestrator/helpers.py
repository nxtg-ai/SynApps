"""
Shared helper functions for SynApps Orchestrator routers.

Extracted from main.py (M-1 router decomposition Step 2).
Functions that depend on Orchestrator use lazy imports inside function bodies
to avoid circular import issues.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import math
import os
import re
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import jwt

from fastapi import HTTPException
from pydantic import BaseModel

from apps.orchestrator.db import get_db_session
from apps.orchestrator.models import (
    RefreshToken as AuthRefreshToken,
)
from apps.orchestrator.repositories import FlowRepository, WorkflowRunRepository
from apps.orchestrator.stores import (
    activity_feed_store,
    audit_log_store,
    collaboration_activity_store,
    debug_session_store,
    execution_log_store,
    execution_quota_store,
    flow_access_log_store,
    flow_alias_store,
    flow_archive_store,
    flow_changelog_store,
    flow_expiry_store,
    flow_rate_limit_store,
    flow_run_preset_store,
    flow_share_store,
    flow_snapshot_store,
    flow_tag_store,
    flow_version_lock_store,
    flow_visibility_store,
    flow_watch_store,
    marketplace_registry,
    rating_store,
    review_store,
    rollback_audit_store,
    sse_event_bus,
    task_queue,
    template_registry,
    usage_tracker,
    workflow_permission_store,
    workflow_secret_store,
    workflow_test_store,
    workflow_version_store,
    workflow_variable_store,
    DebugSession,
    DebugSessionStore,
    ExecutionCostRecord,
    TestSuiteStore,
    WorkflowTestStore,
    WorkflowVersionStore,
)
from apps.orchestrator.dependencies import (
    JWT_ALGORITHM,
    JWT_SECRET_KEY,
    _utc_now,
)

logger = logging.getLogger("orchestrator")

# Orchestrator is populated by main.py after all modules load (to avoid circular imports).
Orchestrator = None  # type: ignore[assignment]

# Get project root for template discovery
_project_root = Path(__file__).parent.parent.parent

# ============================================================
# Constants
# ============================================================

TRACE_RESULTS_KEY = "__trace__"
TRACE_SCHEMA_VERSION = 1
MAX_DIFF_CHANGES = 250
_PERMISSION_RANK: dict[str, int] = {"viewer": 1, "editor": 2, "owner": 3}
_OAUTH2_TOKEN_EXPIRE_SECONDS = 3600
TEMPLATE_EXPORT_VERSION = "1.0.0"
_DEBUG_BREAKPOINT_TIMEOUT_SECONDS = 30.0
# Maps internal execution event names to SSE event type names sent to clients.
_SSE_EVENT_TYPE_MAP: dict[str, str] = {
    "node_start": "node_started",
    "node_success": "node_completed",
    "node_error": "node_failed",
    "node_retry": "node_started",
    "node_fallback": "node_completed",
    "run_start": "execution_started",
    "run_success": "execution_complete",
    "run_error": "execution_complete",
}

_CREDENTIAL_FIELD_NAMES: frozenset[str] = frozenset({
    "api_key", "apikey", "api_secret", "secret", "password", "token",
    "auth_token", "access_token", "refresh_token", "private_key",
    "secret_key", "client_secret", "bearer_token", "authorization",
})

# API version constants (also defined in main.py — kept here for router access)
API_VERSION = "1.0.0"
API_VERSION_DATE = "2026-02-23"
API_SUPPORTED_VERSIONS = ["v1"]
API_SUNSET_GRACE_DAYS = 90
APP_START_TIME = time.time()
API_KEY_VALUE_PREFIX = os.environ.get("API_KEY_PREFIX", "synapps")

# Task / scheduler constants
TASK_STATUSES = ("pending", "running", "completed", "failed")
SUBFLOW_NODE_TYPE = "subflow"

# Validation frozensets used in route handlers
_VALID_SHARE_ROLES: frozenset[str] = frozenset({"viewer", "editor"})
_ALLOWED_REACTIONS: frozenset[str] = frozenset(
    ["👍", "👎", "❤️", "🔥", "🎉", "🚀", "⚠️", "✅", "❌", "🤔"]
)
_CUSTOM_FIELD_TYPES: frozenset[str] = frozenset(["string", "number", "boolean", "date"])
_COLLABORATOR_ROLES: frozenset[str] = frozenset(["owner", "editor", "viewer", "commenter"])
_ENV_NAMES: frozenset[str] = frozenset(["development", "staging", "production"])
_NOTIF_EVENTS: frozenset[str] = frozenset(
    ["run.completed", "run.failed", "flow.updated", "flow.deleted", "collaborator.added"]
)
_NOTIF_CHANNELS: frozenset[str] = frozenset(["email", "slack", "in_app"])
_COST_CURRENCIES: frozenset[str] = frozenset(["USD", "EUR", "GBP", "JPY", "AUD", "CAD"])
_VISIBILITY_LEVELS: frozenset[str] = frozenset(["private", "internal", "public"])

KNOWN_NODE_TYPES = frozenset(
    {
        "start",
        "end",
        "llm",
        "image",
        "image_gen",
        "memory",
        "http_request",
        "code",
        "transform",
        "if_else",
        "merge",
        "for_each",
        "webhook_trigger",
        "scheduler_node",
        "error_handler",
        "custom",
        "subflow",
    }
)

MARKETPLACE_CATEGORIES = {"notification", "data-sync", "monitoring", "content", "devops"}

HISTORY_VALID_STATUSES = frozenset({"idle", "running", "success", "error"})

_WORKFLOW_PATTERNS: list[dict] = [
    {
        "name": "Inbox Triage",
        "description": "Classify and route incoming messages",
        "sequence": ["start", "llm", "code", "memory", "end"],
        "tags": ["classification", "triage", "email"],
    },
    {
        "name": "Content Research Pipeline",
        "description": "Fetch content, summarize, and store",
        "sequence": ["start", "http", "llm", "code", "memory", "end"],
        "tags": ["research", "content", "summarization"],
    },
    {
        "name": "API → Transform → Store",
        "description": "Call external API, transform response, persist result",
        "sequence": ["start", "http", "transform", "memory", "end"],
        "tags": ["api", "etl", "integration"],
    },
    {
        "name": "Scheduled Report",
        "description": "Cron-triggered data fetch and report generation",
        "sequence": ["scheduler", "http", "llm", "http", "end"],
        "tags": ["reporting", "scheduled", "automation"],
    },
    {
        "name": "Conditional Processing",
        "description": "Branch based on content, execute different paths",
        "sequence": ["start", "llm", "ifelse", "code", "end"],
        "tags": ["conditional", "branching", "routing"],
    },
    {
        "name": "Webhook → Enrich → Notify",
        "description": "Receive event, enrich with AI, send notification",
        "sequence": ["webhook_trigger", "llm", "http", "end"],
        "tags": ["webhook", "enrichment", "notification"],
    },
    {
        "name": "Batch Processing",
        "description": "Iterate over list items, process each with AI",
        "sequence": ["start", "http", "foreach", "llm", "merge", "end"],
        "tags": ["batch", "loop", "list"],
    },
    {
        "name": "Image Generation Pipeline",
        "description": "Generate prompt, create image, store result",
        "sequence": ["start", "llm", "imagegen", "memory", "end"],
        "tags": ["image", "generation", "creative"],
    },
]

def paginate(items: list, page: int, page_size: int) -> dict:
    """Apply offset-based pagination to a list of items."""
    total = len(items)
    total_pages = math.ceil(total / page_size) if page_size > 0 else 0
    start = (page - 1) * page_size
    end = start + page_size
    return {
        "items": items[start:end],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }


def _trace_value(value: Any, depth: int = 0) -> Any:
    """Convert arbitrary values into a JSON-serializable structure."""
    if depth >= 8:
        return str(value)

    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, dict):
        return {str(k): _trace_value(v, depth + 1) for k, v in value.items()}

    if isinstance(value, (list, tuple, set)):
        return [_trace_value(v, depth + 1) for v in list(value)]

    if isinstance(value, BaseModel):
        return _trace_value(value.model_dump(), depth + 1)

    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        try:
            return _trace_value(model_dump(), depth + 1)
        except Exception:
            return str(value)

    return str(value)


def _new_execution_trace(
    run_id: str,
    flow_id: str | None,
    input_data: dict[str, Any],
    start_time: float,
) -> dict[str, Any]:
    """Create a baseline execution trace document for a run."""
    return {
        "version": TRACE_SCHEMA_VERSION,
        "run_id": run_id,
        "flow_id": flow_id,
        "status": "running",
        "input": _trace_value(input_data),
        "started_at": float(start_time),
        "ended_at": None,
        "duration_ms": None,
        "nodes": [],
        "errors": [],
    }


def _finalize_execution_trace(trace: dict[str, Any], status: str, end_time: float) -> None:
    """Finalize aggregate timing/status fields in a trace object."""
    trace["status"] = status
    trace["ended_at"] = float(end_time)
    started_at = trace.get("started_at")
    if isinstance(started_at, (int, float)):
        trace["duration_ms"] = max(0.0, (float(end_time) - float(started_at)) * 1000.0)


def _extract_trace_from_run(run: dict[str, Any]) -> dict[str, Any]:
    """Return a normalized execution trace for any run, including legacy runs."""
    run_id = str(run.get("run_id", ""))
    flow_id = run.get("flow_id")
    start_time = run.get("start_time")
    if not isinstance(start_time, (int, float)):
        start_time = time.time()

    input_data = run.get("input_data")
    if not isinstance(input_data, dict):
        input_data = {}

    results = run.get("results")
    if not isinstance(results, dict):
        results = {}

    stored_trace = results.get(TRACE_RESULTS_KEY)
    if isinstance(stored_trace, dict):
        trace = _trace_value(stored_trace)
        if not isinstance(trace, dict):
            trace = _new_execution_trace(run_id, flow_id, input_data, float(start_time))
    else:
        trace = _new_execution_trace(run_id, flow_id, input_data, float(start_time))
        nodes: list[dict[str, Any]] = []
        for node_id, node_result in results.items():
            if node_id == TRACE_RESULTS_KEY:
                continue
            if isinstance(node_result, dict):
                error_payload = node_result.get("error")
                node_errors = []
                if error_payload is not None:
                    node_errors.append(_trace_value(error_payload))
                nodes.append(
                    {
                        "node_id": str(node_id),
                        "node_type": node_result.get("type"),
                        "status": node_result.get("status", "success"),
                        "input": _trace_value(node_result.get("input")),
                        "output": _trace_value(node_result.get("output")),
                        "attempts": node_result.get("attempts", 1),
                        "errors": node_errors,
                        "started_at": node_result.get("started_at"),
                        "ended_at": node_result.get("ended_at"),
                        "duration_ms": node_result.get("duration_ms"),
                    }
                )
            else:
                nodes.append(
                    {
                        "node_id": str(node_id),
                        "node_type": None,
                        "status": "success",
                        "input": None,
                        "output": _trace_value(node_result),
                        "attempts": 1,
                        "errors": [],
                    }
                )
        trace["nodes"] = nodes

    trace["run_id"] = run_id
    trace["flow_id"] = flow_id
    trace["status"] = str(run.get("status", trace.get("status", "unknown")))

    trace_start = trace.get("started_at")
    if not isinstance(trace_start, (int, float)):
        trace_start = float(start_time)
        trace["started_at"] = trace_start

    end_time = run.get("end_time")
    if isinstance(end_time, (int, float)):
        trace["ended_at"] = float(end_time)
        trace["duration_ms"] = max(0.0, (float(end_time) - float(trace_start)) * 1000.0)
    elif trace.get("ended_at") is None and trace.get("status") in {"success", "error"}:
        trace["ended_at"] = float(trace_start)
        trace["duration_ms"] = 0.0

    trace_input = trace.get("input")
    if not isinstance(trace_input, dict):
        trace["input"] = _trace_value(input_data)

    if not isinstance(trace.get("nodes"), list):
        trace["nodes"] = []
    if not isinstance(trace.get("errors"), list):
        trace["errors"] = []

    return trace


def _flatten_for_diff(value: Any, path: str, out: dict[str, Any]) -> None:
    """Flatten nested structures into a path/value map for deterministic diffing."""
    if isinstance(value, dict):
        if not value:
            out[path] = {}
            return
        for key in sorted(value.keys(), key=lambda k: str(k)):
            child_path = f"{path}.{key}"
            _flatten_for_diff(value[key], child_path, out)
        return

    if isinstance(value, list):
        if not value:
            out[path] = []
            return
        for index, item in enumerate(value):
            _flatten_for_diff(item, f"{path}[{index}]", out)
        return

    out[path] = value


def _build_json_diff(left: Any, right: Any, max_changes: int = MAX_DIFF_CHANGES) -> dict[str, Any]:
    """Build a bounded structural diff between two JSON-like values."""
    left_normalized = _trace_value(left)
    right_normalized = _trace_value(right)

    left_flat: dict[str, Any] = {}
    right_flat: dict[str, Any] = {}
    _flatten_for_diff(left_normalized, "$", left_flat)
    _flatten_for_diff(right_normalized, "$", right_flat)

    all_paths = sorted(set(left_flat.keys()) | set(right_flat.keys()))
    changes: list[dict[str, Any]] = []
    total_changes = 0

    for path in all_paths:
        in_left = path in left_flat
        in_right = path in right_flat
        if in_left and in_right and left_flat[path] == right_flat[path]:
            continue

        total_changes += 1
        if len(changes) >= max_changes:
            continue

        if in_left and not in_right:
            change_type = "removed"
        elif in_right and not in_left:
            change_type = "added"
        else:
            change_type = "modified"

        changes.append(
            {
                "path": path,
                "type": change_type,
                "before": left_flat.get(path),
                "after": right_flat.get(path),
            }
        )

    return {
        "changed": total_changes > 0,
        "change_count": total_changes,
        "truncated": total_changes > max_changes,
        "changes": changes,
    }



def _node_result_index(run: dict[str, Any]) -> dict[str, Any]:
    """Return run result payload keyed by node ID, excluding trace metadata."""
    results = run.get("results")
    if not isinstance(results, dict):
        return {}
    return {
        str(node_id): _trace_value(result)
        for node_id, result in results.items()
        if node_id != TRACE_RESULTS_KEY
    }


def _build_run_diff(base_run: dict[str, Any], compare_run: dict[str, Any]) -> dict[str, Any]:
    """Compute an execution diff between two runs."""
    base_trace = _extract_trace_from_run(base_run)
    compare_trace = _extract_trace_from_run(compare_run)

    base_nodes = {
        str(item.get("node_id")): item
        for item in base_trace.get("nodes", [])
        if isinstance(item, dict) and item.get("node_id") is not None
    }
    compare_nodes = {
        str(item.get("node_id")): item
        for item in compare_trace.get("nodes", [])
        if isinstance(item, dict) and item.get("node_id") is not None
    }

    node_diffs: list[dict[str, Any]] = []
    for node_id in sorted(set(base_nodes.keys()) | set(compare_nodes.keys())):
        left = base_nodes.get(node_id)
        right = compare_nodes.get(node_id)
        if left is None:
            node_diffs.append({"node_id": node_id, "type": "added", "after": _trace_value(right)})
            continue
        if right is None:
            node_diffs.append({"node_id": node_id, "type": "removed", "before": _trace_value(left)})
            continue

        left_duration = left.get("duration_ms")
        right_duration = right.get("duration_ms")
        duration_delta = None
        if isinstance(left_duration, (int, float)) and isinstance(right_duration, (int, float)):
            duration_delta = float(right_duration) - float(left_duration)

        status_before = left.get("status")
        status_after = right.get("status")
        attempts_before = left.get("attempts")
        attempts_after = right.get("attempts")

        node_changed = left != right
        if not node_changed:
            continue

        node_diffs.append(
            {
                "node_id": node_id,
                "type": "modified",
                "status": {
                    "before": status_before,
                    "after": status_after,
                    "changed": status_before != status_after,
                },
                "attempts": {
                    "before": attempts_before,
                    "after": attempts_after,
                    "changed": attempts_before != attempts_after,
                },
                "duration_ms": {
                    "before": left_duration,
                    "after": right_duration,
                    "delta_ms": duration_delta,
                },
                "input_changed": left.get("input") != right.get("input"),
                "output_changed": left.get("output") != right.get("output"),
                "errors_changed": left.get("errors") != right.get("errors"),
            }
        )

    base_duration = base_trace.get("duration_ms")
    compare_duration = compare_trace.get("duration_ms")
    duration_delta_ms = None
    if isinstance(base_duration, (int, float)) and isinstance(compare_duration, (int, float)):
        duration_delta_ms = float(compare_duration) - float(base_duration)

    return {
        "base_run_id": base_run.get("run_id"),
        "compare_run_id": compare_run.get("run_id"),
        "flow_id": base_run.get("flow_id") or compare_run.get("flow_id"),
        "summary": {
            "base_status": base_run.get("status"),
            "compare_status": compare_run.get("status"),
            "status_changed": base_run.get("status") != compare_run.get("status"),
            "base_node_count": len(base_nodes),
            "compare_node_count": len(compare_nodes),
            "changed_node_count": len(node_diffs),
        },
        "timing": {
            "base_duration_ms": base_duration,
            "compare_duration_ms": compare_duration,
            "duration_delta_ms": duration_delta_ms,
        },
        "input_diff": _build_json_diff(base_trace.get("input", {}), compare_trace.get("input", {})),
        "output_diff": _build_json_diff(
            _node_result_index(base_run), _node_result_index(compare_run)
        ),
        "trace_diff": _build_json_diff(base_trace, compare_trace),
        "node_diffs": node_diffs,
        "base_trace": base_trace,
        "compare_trace": compare_trace,
    }


def _check_flow_permission(flow_id: str, user_id: str, required: str) -> None:
    """Raise HTTP 403 if user lacks the required role.

    If no permissions are set for the flow (open-access / legacy), always passes.
    Roles in ascending order: viewer < editor < owner.
    """
    if not workflow_permission_store.has_flow(flow_id):
        return  # open access — backwards compatible
    role = workflow_permission_store.get_role(flow_id, user_id)
    if role is None:
        raise HTTPException(
            status_code=403,
            detail="Access denied: you are not a member of this workflow.",
        )
    if _PERMISSION_RANK.get(role, 0) < _PERMISSION_RANK.get(required, 0):
        raise HTTPException(
            status_code=403,
            detail=f"Access denied: '{required}' role required, you have '{role}'.",
        )


def _diff_flow_snapshots(snapshot_a: dict[str, Any], snapshot_b: dict[str, Any]) -> dict[str, Any]:
    """Return a structural diff between two flow snapshots.

    Compares nodes and edges:
    - ``nodes_added``: node IDs present in B but not A
    - ``nodes_removed``: node IDs present in A but not B
    - ``nodes_changed``: node IDs where type or data differ
    - ``edges_added``: edge source→target pairs in B but not A
    - ``edges_removed``: edge source→target pairs in A but not B
    """

    def _node_map(snapshot: dict) -> dict[str, dict]:
        return {n["id"]: n for n in snapshot.get("nodes", []) if isinstance(n, dict) and "id" in n}

    def _edge_key(edge: dict) -> str:
        return f"{edge.get('source', '')}→{edge.get('target', '')}"

    def _edge_set(snapshot: dict) -> set[str]:
        return {_edge_key(e) for e in snapshot.get("edges", []) if isinstance(e, dict)}

    nodes_a = _node_map(snapshot_a)
    nodes_b = _node_map(snapshot_b)
    ids_a = set(nodes_a)
    ids_b = set(nodes_b)

    nodes_added = sorted(ids_b - ids_a)
    nodes_removed = sorted(ids_a - ids_b)
    nodes_changed = []
    for nid in ids_a & ids_b:
        na, nb = nodes_a[nid], nodes_b[nid]
        if na.get("type") != nb.get("type") or na.get("data") != nb.get("data"):
            nodes_changed.append(nid)

    edges_a = _edge_set(snapshot_a)
    edges_b = _edge_set(snapshot_b)

    return {
        "nodes_added": nodes_added,
        "nodes_removed": nodes_removed,
        "nodes_changed": sorted(nodes_changed),
        "edges_added": sorted(edges_b - edges_a),
        "edges_removed": sorted(edges_a - edges_b),
        "summary": {
            "nodes_added": len(nodes_added),
            "nodes_removed": len(nodes_removed),
            "nodes_changed": len(nodes_changed),
            "edges_added": len(edges_b - edges_a),
            "edges_removed": len(edges_a - edges_b),
        },
    }




def validate_template(data: dict[str, Any]) -> dict[str, Any]:
    """Validate a template/flow definition and return a structured report.

    Returns ``{"valid": True/False, "errors": [...], "warnings": [...], "summary": {...}}``.
    """
    errors: list[str] = []
    warnings: list[str] = []

    # --- Required top-level fields ---
    if not isinstance(data.get("name"), str) or not data["name"].strip():
        errors.append("Missing or empty required field: 'name'")
    if not isinstance(data.get("nodes"), list):
        errors.append("Missing or invalid required field: 'nodes' (must be a list)")
        # Can't continue structural checks without nodes
        return {
            "valid": False,
            "errors": errors,
            "warnings": warnings,
            "summary": {"node_count": 0, "edge_count": 0},
        }

    nodes = data["nodes"]
    edges = data.get("edges", [])
    if not isinstance(edges, list):
        errors.append("Invalid field: 'edges' (must be a list)")
        edges = []

    # --- Node validation ---
    node_ids: set[str] = set()
    has_start = False
    has_end = False
    for i, node in enumerate(nodes):
        if not isinstance(node, dict):
            errors.append(f"nodes[{i}]: must be an object")
            continue
        nid = node.get("id")
        if not nid or not isinstance(nid, str):
            errors.append(f"nodes[{i}]: missing or empty 'id'")
            continue
        if nid in node_ids:
            errors.append(f"nodes[{i}]: duplicate node id '{nid}'")
        node_ids.add(nid)

        ntype = node.get("type", "")
        if not ntype:
            errors.append(f"node '{nid}': missing 'type'")
        elif ntype not in KNOWN_NODE_TYPES:
            warnings.append(f"node '{nid}': unknown type '{ntype}'")

        if ntype == "start":
            has_start = True
        if ntype == "end":
            has_end = True

        pos = node.get("position")
        if not isinstance(pos, dict) or "x" not in pos or "y" not in pos:
            warnings.append(f"node '{nid}': missing or invalid 'position'")

    if not has_start:
        errors.append("Template must contain at least one 'start' node")
    if not has_end:
        errors.append("Template must contain at least one 'end' node")

    # --- Edge validation ---
    edge_ids: set[str] = set()
    adjacency: dict[str, list[str]] = {nid: [] for nid in node_ids}
    for i, edge in enumerate(edges):
        if not isinstance(edge, dict):
            errors.append(f"edges[{i}]: must be an object")
            continue
        eid = edge.get("id", f"edge-{i}")
        if eid in edge_ids:
            errors.append(f"edges[{i}]: duplicate edge id '{eid}'")
        edge_ids.add(eid)

        src = edge.get("source", "")
        tgt = edge.get("target", "")
        if not src:
            errors.append(f"edge '{eid}': missing 'source'")
        elif src not in node_ids:
            errors.append(f"edge '{eid}': source '{src}' references unknown node")
        if not tgt:
            errors.append(f"edge '{eid}': missing 'target'")
        elif tgt not in node_ids:
            errors.append(f"edge '{eid}': target '{tgt}' references unknown node")

        if src and tgt and src == tgt:
            errors.append(f"edge '{eid}': self-loop (source == target: '{src}')")

        if src in node_ids and tgt in node_ids:
            adjacency.setdefault(src, []).append(tgt)

    # --- Circular dependency detection (DFS) ---
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {nid: WHITE for nid in node_ids}
    cycle_path: list[str] = []

    def _dfs(node: str) -> bool:
        color[node] = GRAY
        cycle_path.append(node)
        for neighbor in adjacency.get(node, []):
            if color[neighbor] == GRAY:
                # Found cycle — extract the cycle portion
                idx = cycle_path.index(neighbor)
                cycle = cycle_path[idx:] + [neighbor]
                errors.append(f"Circular dependency detected: {' -> '.join(cycle)}")
                return True
            if color[neighbor] == WHITE:
                if _dfs(neighbor):
                    return True
        cycle_path.pop()
        color[node] = BLACK
        return False

    for nid in node_ids:
        if color[nid] == WHITE:
            if _dfs(nid):
                break  # Report first cycle found

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "summary": {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "node_types": sorted({n.get("type", "") for n in nodes if isinstance(n, dict)}),
            "has_start": has_start,
            "has_end": has_end,
        },
    }



_SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def _parse_semver(v: str) -> tuple | None:
    """Parse a semver string into (major, minor, patch) or None."""
    m = _SEMVER_RE.match(v)
    return (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None



def _bump_patch(semver: str) -> str:
    """Increment the patch component of a semver string."""
    parts = _parse_semver(semver)
    if not parts:
        return "1.0.0"
    return f"{parts[0]}.{parts[1]}.{parts[2] + 1}"







def _scrub_node_credentials(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return a copy of nodes with credential fields blanked out.

    Operates on the ``data`` sub-dict of each node. Credential fields are set to
    an empty string so the template consumer knows the field exists but must fill it.
    """
    scrubbed = []
    for node in nodes:
        node_copy = dict(node)
        data = node_copy.get("data")
        if isinstance(data, dict):
            new_data = {}
            for k, v in data.items():
                if k in _CREDENTIAL_FIELD_NAMES or k.lower() in _CREDENTIAL_FIELD_NAMES:
                    new_data[k] = ""  # blank — must be filled by importer
                else:
                    new_data[k] = v
            node_copy["data"] = new_data
        scrubbed.append(node_copy)
    return scrubbed



def _load_yaml_template(template_id: str) -> dict[str, Any] | None:
    """Load a YAML template by its ID (filename stem or 'id' field)."""
    import yaml

    templates_dir = _project_root / "templates"
    if not templates_dir.is_dir():
        return None
    for path in templates_dir.glob("*.yaml"):
        try:
            with open(path) as f:
                data = yaml.safe_load(f)
            if not isinstance(data, dict):
                continue
            tid = data.get("id", path.stem)
            if tid == template_id:
                return data
        except Exception as exc:
            logger.warning("Failed to load template from %s: %s", path, exc)
            continue
    return None



async def _run_task_background(
    task_id: str, template_data: dict[str, Any], input_data: dict[str, Any]
) -> None:
    """Background coroutine that runs a template and updates task state."""
    task_queue.update(task_id, status="running", started_at=time.time(), progress_pct=10)
    try:
        flow_dict = {
            "id": str(uuid.uuid4()),
            "name": template_data.get("name", ""),
            "nodes": template_data.get("nodes", []),
            "edges": template_data.get("edges", []),
        }
        await FlowRepository.save(flow_dict)
        task_queue.update(task_id, progress_pct=30)

        run_id = await Orchestrator.execute_flow(flow_dict, input_data)
        task_queue.update(task_id, run_id=run_id, progress_pct=50)

        # Poll for completion (up to 60s)
        for _ in range(120):
            await asyncio.sleep(0.5)
            run = await WorkflowRunRepository.get_by_run_id(run_id)
            if run and run.get("status") in ("success", "error"):
                break

        run = await WorkflowRunRepository.get_by_run_id(run_id)
        run_status = run.get("status", "unknown") if run else "unknown"

        if run_status == "success":
            task_queue.update(
                task_id,
                status="completed",
                progress_pct=100,
                result={"run_id": run_id, "run_status": run_status},
                completed_at=time.time(),
            )
        else:
            task_queue.update(
                task_id,
                status="failed",
                progress_pct=100,
                error=run.get("error", "Execution failed") if run else "Run not found",
                result={"run_id": run_id, "run_status": run_status},
                completed_at=time.time(),
            )
    except Exception as e:
        task_queue.update(
            task_id,
            status="failed",
            progress_pct=100,
            error=str(e),
            completed_at=time.time(),
        )





_BUILTIN_LISTINGS: list[dict[str, Any]] = [
    {
        "name": "Social Media Monitor",
        "description": (
            "Monitor social media mentions, analyze sentiment with an LLM, and automatically "
            "alert your Slack channel when negative sentiment is detected."
        ),
        "category": "monitoring",
        "tags": ["social-media", "monitoring", "sentiment", "slack"],
        "author": "SynApps Team",
        "nodes": [
            {
                "id": "trigger",
                "type": "webhook_trigger",
                "position": {"x": 300, "y": 25},
                "data": {"label": "Mention Webhook"},
            },
            {
                "id": "sentiment",
                "type": "llm",
                "position": {"x": 300, "y": 150},
                "data": {
                    "label": "Sentiment Analysis",
                    "provider": "openai",
                    "model": "gpt-4o-mini",
                    "temperature": 0.1,
                    "max_tokens": 256,
                    "system_prompt": (
                        "You are a sentiment analysis engine. Analyze the social media mention "
                        'and respond with JSON: {"sentiment": "positive"|"neutral"|"negative", '
                        '"score": 0.0-1.0, "reason": "<brief reason>"}. Respond ONLY with valid JSON.'
                    ),
                },
            },
            {
                "id": "check_sentiment",
                "type": "ifelse",
                "position": {"x": 300, "y": 300},
                "data": {
                    "label": "Negative?",
                    "condition": 'data.sentiment == "negative"',
                },
            },
            {
                "id": "slack_alert",
                "type": "http_request",
                "position": {"x": 150, "y": 450},
                "data": {
                    "label": "Slack Alert",
                    "method": "POST",
                    "url": "{{SLACK_WEBHOOK_URL}}",
                    "headers": {"Content-Type": "application/json"},
                    "body": (
                        '{"text": ":rotating_light: Negative mention detected '
                        '(score: {{data.score}})\\n> {{input.text}}\\nReason: {{data.reason}}"}'
                    ),
                    "timeout_seconds": 15,
                    "max_retries": 2,
                },
            },
            {
                "id": "end",
                "type": "end",
                "position": {"x": 300, "y": 600},
                "data": {"label": "End"},
            },
        ],
        "edges": [
            {"id": "trigger-sentiment", "source": "trigger", "target": "sentiment"},
            {"id": "sentiment-check", "source": "sentiment", "target": "check_sentiment"},
            {
                "id": "check-slack",
                "source": "check_sentiment",
                "target": "slack_alert",
                "sourceHandle": "true",
            },
            {
                "id": "check-end",
                "source": "check_sentiment",
                "target": "end",
                "sourceHandle": "false",
            },
            {"id": "slack-end", "source": "slack_alert", "target": "end"},
        ],
    },
    {
        "name": "Document Processor",
        "description": (
            "Process incoming documents: extract and parse text from the webhook payload, "
            "summarize with an LLM, then email the summary using SendGrid."
        ),
        "category": "content",
        "tags": ["document", "ocr", "summarization", "email"],
        "author": "SynApps Team",
        "nodes": [
            {
                "id": "trigger",
                "type": "webhook_trigger",
                "position": {"x": 300, "y": 25},
                "data": {"label": "Document Webhook"},
            },
            {
                "id": "extract",
                "type": "code",
                "position": {"x": 300, "y": 150},
                "data": {
                    "label": "Extract Text",
                    "language": "python",
                    "timeout_seconds": 10,
                    "memory_limit_mb": 256,
                    "code": (
                        "import json, base64\n"
                        "payload = context.get('input', {})\n"
                        "if isinstance(payload, str):\n"
                        "    try:\n"
                        "        payload = json.loads(payload)\n"
                        "    except Exception:\n"
                        "        payload = {'text': payload}\n"
                        "raw = payload.get('text') or payload.get('content') or ''\n"
                        "if payload.get('encoding') == 'base64' and raw:\n"
                        "    try:\n"
                        "        raw = base64.b64decode(raw).decode('utf-8', errors='replace')\n"
                        "    except Exception:\n"
                        "        pass\n"
                        "filename = payload.get('filename', 'document')\n"
                        "result = {'filename': filename, 'text': raw.strip(), 'char_count': len(raw)}\n"
                    ),
                },
            },
            {
                "id": "summarize",
                "type": "llm",
                "position": {"x": 300, "y": 325},
                "data": {
                    "label": "Summarize",
                    "provider": "openai",
                    "model": "gpt-4o-mini",
                    "temperature": 0.3,
                    "max_tokens": 1024,
                    "system_prompt": (
                        "You are a professional document analyst. Summarize the provided document "
                        "text clearly and concisely. Include: key points (bullet list), main "
                        "conclusions, and any action items. Keep the summary under 300 words."
                    ),
                },
            },
            {
                "id": "email",
                "type": "http_request",
                "position": {"x": 300, "y": 475},
                "data": {
                    "label": "Send Email (SendGrid)",
                    "method": "POST",
                    "url": "https://api.sendgrid.com/v3/mail/send",
                    "headers": {
                        "Content-Type": "application/json",
                        "Authorization": "Bearer {{SENDGRID_API_KEY}}",
                    },
                    "body": (
                        '{"personalizations":[{"to":[{"email":"{{TO_EMAIL}}"}]}],'
                        '"from":{"email":"{{FROM_EMAIL}}"},'
                        '"subject":"Document Summary: {{extract.filename}}",'
                        '"content":[{"type":"text/plain","value":"{{data}}"}]}'
                    ),
                    "timeout_seconds": 20,
                    "max_retries": 2,
                },
            },
            {
                "id": "end",
                "type": "end",
                "position": {"x": 300, "y": 600},
                "data": {"label": "End"},
            },
        ],
        "edges": [
            {"id": "trigger-extract", "source": "trigger", "target": "extract"},
            {"id": "extract-summarize", "source": "extract", "target": "summarize"},
            {"id": "summarize-email", "source": "summarize", "target": "email"},
            {"id": "email-end", "source": "email", "target": "end"},
        ],
    },
    {
        "name": "Data Pipeline",
        "description": (
            "Scheduled ETL pipeline: fetch data from an external API on a cron schedule, "
            "reshape with Transform, and persist the result in memory store for downstream consumers."
        ),
        "category": "data-sync",
        "tags": ["data", "pipeline", "etl", "scheduled"],
        "author": "SynApps Team",
        "nodes": [
            {
                "id": "scheduler",
                "type": "scheduler",
                "position": {"x": 300, "y": 25},
                "data": {
                    "label": "Hourly Trigger",
                    "cron": "{{CRON_SCHEDULE}}",
                },
            },
            {
                "id": "fetch",
                "type": "http_request",
                "position": {"x": 300, "y": 150},
                "data": {
                    "label": "Fetch Data",
                    "method": "GET",
                    "url": "{{DATA_API_URL}}",
                    "headers": {
                        "Accept": "application/json",
                        "X-Api-Key": "{{DATA_API_KEY}}",
                    },
                    "timeout_seconds": 30,
                    "max_retries": 3,
                },
            },
            {
                "id": "reshape",
                "type": "transform",
                "position": {"x": 300, "y": 300},
                "data": {
                    "label": "Reshape Data",
                    "operation": "json_path",
                    "json_path": "$.data",
                },
            },
            {
                "id": "store",
                "type": "memory",
                "position": {"x": 300, "y": 450},
                "data": {
                    "label": "Store Result",
                    "operation": "store",
                    "key": "pipeline-latest",
                    "namespace": "data-pipeline",
                },
            },
            {
                "id": "end",
                "type": "end",
                "position": {"x": 300, "y": 575},
                "data": {"label": "End"},
            },
        ],
        "edges": [
            {"id": "scheduler-fetch", "source": "scheduler", "target": "fetch"},
            {"id": "fetch-reshape", "source": "fetch", "target": "reshape"},
            {"id": "reshape-store", "source": "reshape", "target": "store"},
            {"id": "store-end", "source": "store", "target": "end"},
        ],
    },
]

def _seed_marketplace_listings() -> None:
    """Pre-populate the marketplace registry with built-in SynApps Team templates.

    Idempotent: skips any listing whose name already exists in the registry.
    Called once during app startup via the lifespan handler.
    """
    existing_names = {entry["name"] for entry in marketplace_registry._listings.values()}
    seeded = 0
    for listing_data in _BUILTIN_LISTINGS:
        if listing_data["name"] in existing_names:
            continue  # idempotent — already present (e.g. hot-reload)
        try:
            marketplace_registry.publish(listing_data)
            seeded += 1
        except Exception as exc:
            logger.warning("Failed to seed marketplace listing '%s': %s", listing_data["name"], exc)
    if seeded:
        logger.info("Marketplace: seeded %d built-in listing(s)", seeded)



def _share_record_response(record: dict[str, Any]) -> dict[str, Any]:
    expires_at_iso = datetime.fromtimestamp(record["expires_at"], tz=UTC).isoformat()
    return {
        "token": record["token"],
        "flow_id": record["flow_id"],
        "expires_at": expires_at_iso,
        "ttl": record["ttl"],
    }



def _lock_response(flow_id: str, record: dict[str, Any] | None) -> dict[str, Any]:
    if record is None:
        return {"flow_id": flow_id, "locked": False, "lock": None}
    return {
        "flow_id": flow_id,
        "locked": True,
        "lock": {
            "locked_by": record["locked_by"],
            "reason": record["reason"],
            "locked_at": datetime.fromtimestamp(record["locked_at"], tz=UTC).isoformat(),
        },
    }



def _bulk_result(
    succeeded: list[str],
    failed: list[dict[str, str]],
    action: str,
) -> dict[str, Any]:
    return {
        "action": action,
        "succeeded": succeeded,
        "failed": failed,
        "total": len(succeeded) + len(failed),
        "success_count": len(succeeded),
        "failure_count": len(failed),
    }



def _expiry_response(flow_id: str, ts: float | None) -> dict[str, Any]:
    return {
        "flow_id": flow_id,
        "expires_at": datetime.fromtimestamp(ts, tz=UTC).isoformat() if ts else None,
        "expired": flow_expiry_store.is_expired(flow_id),
    }



def _alias_response(flow_id: str) -> dict[str, Any]:
    return {"flow_id": flow_id, "alias": flow_alias_store.get(flow_id)}



def _rate_limit_response(flow_id: str) -> dict[str, Any]:
    cfg = flow_rate_limit_store.get(flow_id)
    return {
        "flow_id": flow_id,
        "max_runs": cfg["max_runs"] if cfg else None,
        "window_seconds": cfg["window_seconds"] if cfg else None,
        "current_count": flow_rate_limit_store.current_count(flow_id),
    }



def _fmt_entry(e: dict[str, Any]) -> dict[str, Any]:
    return {
        **e,
        "created_at": datetime.fromtimestamp(e["created_at"], tz=UTC).isoformat(),
    }



def _fmt_preset(p: dict[str, Any]) -> dict[str, Any]:
    return {
        **p,
        "created_at": datetime.fromtimestamp(p["created_at"], tz=UTC).isoformat(),
    }



def _fmt_ann(a: dict[str, Any]) -> dict[str, Any]:
    return {
        **a,
        "created_at": datetime.fromtimestamp(a["created_at"], tz=UTC).isoformat(),
        "updated_at": datetime.fromtimestamp(a["updated_at"], tz=UTC).isoformat(),
    }



def _fmt_dep(e: dict[str, Any]) -> dict[str, Any]:
    return {
        **e,
        "created_at": datetime.fromtimestamp(e["created_at"], tz=UTC).isoformat(),
    }



def _fmt_bm(b: dict[str, Any]) -> dict[str, Any]:
    return {
        **b,
        "created_at": datetime.fromtimestamp(b["created_at"], tz=UTC).isoformat(),
    }



async def _run_flow_impl(
    flow_id: str,
    body: RunFlowRequest,
    current_user: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Execute a flow and return a run identifier."""
    _check_flow_permission(flow_id, current_user.get("email", "") if current_user else "", "editor")
    if current_user:
        execution_quota_store.check_and_record(current_user.get("email", "anonymous"))
    try:
        flow_rate_limit_store.check_and_record(flow_id)
    except ValueError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    flow = await FlowRepository.get_by_id(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
    flow = await Orchestrator.auto_migrate_legacy_nodes(flow, persist=True)
    run_id = await Orchestrator.execute_flow(flow, body.input)
    execution_log_store.record_input(run_id, flow_id, body.input or {})
    actor = current_user.get("email", "system") if current_user else "system"
    audit_log_store.record(
        actor, "workflow_run_started", "flow", flow_id, detail=f"Run {run_id} started."
    )
    activity_feed_store.record(
        flow_id,
        actor=actor,
        action="run_started",
        detail=f"Run {run_id} started.",
    )
    return {"run_id": run_id}



async def _build_history_entry(run: dict[str, Any]) -> dict[str, Any]:
    """Build a history entry from a run dict, enriched with flow name."""
    flow_id = run.get("flow_id")
    flow_name = None
    node_count = 0
    if flow_id:
        flow = await FlowRepository.get_by_id(flow_id)
        if flow:
            flow_name = flow.get("name")
            node_count = len(flow.get("nodes", []))

    trace = _extract_trace_from_run(run)
    step_count = len(trace.get("nodes", []))
    steps_succeeded = sum(1 for n in trace.get("nodes", []) if n.get("status") == "success")
    steps_failed = sum(1 for n in trace.get("nodes", []) if n.get("status") == "error")

    input_data = run.get("input_data")
    input_summary = None
    if isinstance(input_data, dict):
        input_summary = {
            k: (str(v)[:100] if isinstance(v, str) and len(v) > 100 else v)
            for k, v in list(input_data.items())[:10]
        }

    output_summary = None
    results = run.get("results")
    if isinstance(results, dict):
        output_keys = [k for k in results.keys() if k != TRACE_RESULTS_KEY]
        output_summary = {"keys": output_keys[:10], "total_keys": len(output_keys)}

    return {
        "run_id": run.get("run_id") or run.get("id"),
        "flow_id": flow_id,
        "flow_name": flow_name,
        "status": run.get("status"),
        "start_time": run.get("start_time"),
        "end_time": run.get("end_time"),
        "duration_ms": trace.get("duration_ms"),
        "node_count": node_count,
        "step_count": step_count,
        "steps_succeeded": steps_succeeded,
        "steps_failed": steps_failed,
        "error": run.get("error"),
        "input_summary": input_summary,
        "output_summary": output_summary,
    }



def _discover_yaml_templates() -> list[dict[str, Any]]:
    """Scan templates/ for YAML workflow definitions."""
    import yaml

    templates_dir = _project_root / "templates"
    results: list[dict[str, Any]] = []
    if not templates_dir.is_dir():
        return results
    for path in sorted(templates_dir.glob("*.yaml")):
        try:
            with open(path) as f:
                data = yaml.safe_load(f)
            if not isinstance(data, dict):
                continue
            results.append(
                {
                    "id": data.get("id", path.stem),
                    "name": data.get("name", path.stem),
                    "description": data.get("description", ""),
                    "tags": data.get("tags", []),
                    "source": f"templates/{path.name}",
                    "node_count": len(data.get("nodes", [])),
                    "edge_count": len(data.get("edges", [])),
                }
            )
        except Exception as exc:
            logger.warning("Failed to load template from %s: %s", path, exc)
            continue
    return results



async def _get_last_run_for_flow_name(flow_name: str) -> dict[str, Any] | None:
    """Find the most recent run whose flow matches *flow_name*."""
    flows = await FlowRepository.get_all()
    matching_flow_ids = [f["id"] for f in flows if f.get("name") == flow_name]
    if not matching_flow_ids:
        return None
    runs = await WorkflowRunRepository.get_all()
    matching = [r for r in runs if r.get("flow_id") in matching_flow_ids]
    if not matching:
        return None
    matching.sort(key=lambda r: r.get("start_time", 0), reverse=True)
    latest = matching[0]
    return {
        "run_id": latest.get("run_id") or latest.get("id"),
        "flow_id": latest.get("flow_id"),
        "status": latest.get("status"),
        "started_at": latest.get("start_time"),
        "ended_at": latest.get("end_time"),
    }



def _create_oauth2_token(
    sub: str,
    client_id: str,
    scope: str,
    expires_in: int = _OAUTH2_TOKEN_EXPIRE_SECONDS,
) -> str:
    """Issue a JWT for an OAuth2 grant with token_type='oauth2'."""
    now = int(time.time())
    payload: dict[str, Any] = {
        "sub": sub,
        "token_type": "oauth2",
        "oauth2_client_id": client_id,
        "scope": scope,
        "iat": now,
        "exp": now + expires_in,
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


# --- Pydantic request models ---



def _estimate_node_cost(node_type: str, node_data: dict, output: dict) -> dict:
    """Estimate cost metrics for a single node execution.

    Args:
        node_type: The type identifier of the node (e.g. "llm", "http").
        node_data: The node's configuration data dict.
        output: The node's output dict from the execution log.

    Returns:
        A dict with keys: token_input, token_output, model, estimated_usd, api_calls.
    """
    ntype = str(node_type).lower().strip()
    if ntype == "llm":
        token_input = len(str(node_data.get("prompt", ""))) // 4
        token_output = len(str(output)) // 4
        model = str(node_data.get("model", "gpt-4o"))
        estimated_usd = float(token_input * 0.000005 + token_output * 0.000015)
        return {
            "token_input": token_input,
            "token_output": token_output,
            "model": model,
            "estimated_usd": estimated_usd,
            "api_calls": 0,
        }
    if ntype == "http":
        return {
            "token_input": 0,
            "token_output": 0,
            "model": "",
            "estimated_usd": 0.0,
            "api_calls": 1,
        }
    return {
        "token_input": 0,
        "token_output": 0,
        "model": "",
        "estimated_usd": 0.0,
        "api_calls": 0,
    }






# ---------------------------------------------------------------------------
# N-41: Pre-execution cost estimation
# ---------------------------------------------------------------------------



def _diff_workflows(v1: dict, v2: dict) -> dict:
    """Compute a structural diff between two workflow snapshots.

    Compares nodes by id and edges by (source, target) tuple, returning
    added/removed/modified sets plus a summary with an is_identical flag.
    """
    v1_nodes: dict[str, dict] = {
        n["id"]: n for n in v1.get("nodes", []) if isinstance(n, dict) and "id" in n
    }
    v2_nodes: dict[str, dict] = {
        n["id"]: n for n in v2.get("nodes", []) if isinstance(n, dict) and "id" in n
    }

    added_nodes = [v2_nodes[nid] for nid in v2_nodes if nid not in v1_nodes]
    removed_nodes = [v1_nodes[nid] for nid in v1_nodes if nid not in v2_nodes]
    modified_nodes: list[dict] = []
    for nid in v1_nodes:
        if nid not in v2_nodes:
            continue
        v1n = v1_nodes[nid]
        v2n = v2_nodes[nid]
        if v1n == v2n:
            continue
        all_keys = set(list(v1n.keys()) + list(v2n.keys()))
        changes = {
            k: {"from": v1n.get(k), "to": v2n.get(k)} for k in all_keys if v1n.get(k) != v2n.get(k)
        }
        modified_nodes.append({"id": nid, "changes": changes})

    def _edge_key(e: dict) -> tuple:
        return (e.get("source", ""), e.get("target", ""))

    v1_edges: dict[tuple, dict] = {
        _edge_key(e): e for e in v1.get("edges", []) if isinstance(e, dict)
    }
    v2_edges: dict[tuple, dict] = {
        _edge_key(e): e for e in v2.get("edges", []) if isinstance(e, dict)
    }

    added_edges = [v2_edges[k] for k in v2_edges if k not in v1_edges]
    removed_edges = [v1_edges[k] for k in v1_edges if k not in v2_edges]
    modified_edges: list[dict] = []
    for ek in v1_edges:
        if ek not in v2_edges:
            continue
        v1e = v1_edges[ek]
        v2e = v2_edges[ek]
        if v1e == v2e:
            continue
        all_keys = set(list(v1e.keys()) + list(v2e.keys()))
        changes = {
            k: {"from": v1e.get(k), "to": v2e.get(k)} for k in all_keys if v1e.get(k) != v2e.get(k)
        }
        modified_edges.append({"source": ek[0], "target": ek[1], "changes": changes})

    summary = {
        "nodes_added": len(added_nodes),
        "nodes_removed": len(removed_nodes),
        "nodes_modified": len(modified_nodes),
        "edges_added": len(added_edges),
        "edges_removed": len(removed_edges),
        "edges_modified": len(modified_edges),
        "is_identical": (
            len(added_nodes) == 0
            and len(removed_nodes) == 0
            and len(modified_nodes) == 0
            and len(added_edges) == 0
            and len(removed_edges) == 0
            and len(modified_edges) == 0
        ),
    }

    return {
        "added_nodes": added_nodes,
        "removed_nodes": removed_nodes,
        "modified_nodes": modified_nodes,
        "added_edges": added_edges,
        "removed_edges": removed_edges,
        "modified_edges": modified_edges,
        "summary": summary,
    }







# Static transition weights: probability that a given node type is followed by another.
# Higher weight → higher default suggestion rank.
_NODE_TRANSITION_WEIGHTS: dict[str, dict[str, float]] = {
    "start": {"llm": 3.0, "http": 2.5, "code": 2.0, "transform": 1.5, "ifelse": 1.0},
    "llm": {"code": 2.5, "http": 2.0, "memory": 2.0, "transform": 1.5, "ifelse": 2.0, "imagegen": 1.0, "end": 1.5},
    "http": {"llm": 2.5, "transform": 2.5, "code": 2.0, "memory": 1.5, "ifelse": 1.5, "end": 1.0},
    "code": {"llm": 2.0, "http": 2.0, "transform": 2.0, "memory": 1.5, "end": 2.0, "ifelse": 1.5},
    "transform": {"llm": 2.0, "code": 1.5, "memory": 2.0, "http": 1.5, "end": 2.0},
    "memory": {"llm": 2.0, "code": 1.5, "end": 2.0, "http": 1.0},
    "ifelse": {"llm": 1.5, "code": 1.5, "http": 1.5, "transform": 1.5, "end": 2.0, "merge": 2.0},
    "imagegen": {"memory": 2.0, "http": 1.5, "code": 1.5, "end": 2.0},
    "foreach": {"llm": 2.0, "code": 2.0, "http": 2.0, "merge": 3.0},
    "merge": {"llm": 1.5, "code": 1.5, "transform": 1.5, "end": 3.0},
    "webhook_trigger": {"llm": 2.5, "code": 2.0, "http": 2.0, "transform": 1.5},
    "scheduler": {"http": 2.5, "llm": 2.0, "code": 2.0},
}

# Keyword → node-type mapping used to infer node suggestions from natural language.
_KEYWORD_NODE_MAP: list[tuple[list[str], str]] = [
    (["llm", "language model", "gpt", "claude", "ai", "generate text", "chat", "summarize", "classify"], "llm"),
    (["image", "picture", "generate image", "dall-e", "stable diffusion", "midjourney"], "imagegen"),
    (["http", "api", "request", "fetch", "rest", "endpoint", "call", "webhook"], "http"),
    (["code", "script", "python", "javascript", "execute", "run", "compute"], "code"),
    (["transform", "convert", "format", "map", "reshape", "jinja", "template"], "transform"),
    (["memory", "store", "save", "retrieve", "database", "vector", "search"], "memory"),
    (["condition", "branch", "if", "else", "decision", "route", "check"], "ifelse"),
    (["foreach", "loop", "iterate", "batch", "list", "each"], "foreach"),
    (["merge", "join", "combine", "aggregate", "collect"], "merge"),
    (["schedule", "cron", "timer", "periodic", "interval"], "scheduler"),
    (["trigger", "event", "webhook trigger", "incoming"], "webhook_trigger"),
    (["end", "finish", "complete", "output", "result"], "end"),
]

# Minimal config templates used as hints for newly added nodes.
_NODE_CONFIG_TEMPLATES: dict[str, dict] = {
    "llm": {"provider": "openai", "model": "gpt-4o-mini", "system_prompt": "", "temperature": 0.7},
    "imagegen": {"provider": "openai", "model": "dall-e-3", "size": "1024x1024"},
    "http": {"method": "GET", "url": "", "headers": {}},
    "code": {"language": "python", "code": "# your code here\nresult = input_data"},
    "transform": {"template": "{{ input_data }}"},
    "memory": {"backend": "in_memory", "operation": "store"},
    "ifelse": {"condition": "{{ input_data.value == true }}"},
    "foreach": {"items_path": "$.items"},
    "merge": {"strategy": "concat"},
    "scheduler": {"cron": "0 * * * *"},
    "webhook_trigger": {"path": "/webhook", "method": "POST"},
    "end": {},
}


def _score_node_suggestions(
    current_node_type: str,
    existing_node_types: list[str],
) -> list[dict]:
    """Return ranked next-node suggestions for *current_node_type*.

    Combines the static transition table with a recency penalty for node
    types that already appear many times in the workflow.
    """
    base_weights = _NODE_TRANSITION_WEIGHTS.get(current_node_type, {})
    if not base_weights:
        # Fallback: generic suggestions
        base_weights = {"llm": 2.0, "code": 1.5, "http": 1.5, "transform": 1.0, "end": 1.0}

    # Count existing occurrences for penalty
    type_counts: dict[str, int] = {}
    for t in existing_node_types:
        type_counts[t] = type_counts.get(t, 0) + 1

    scored: list[tuple[float, str]] = []
    for node_type, weight in base_weights.items():
        penalty = 0.3 * type_counts.get(node_type, 0)
        final_score = max(0.0, weight - penalty)
        scored.append((final_score, node_type))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [
        {
            "node_type": nt,
            "score": round(score, 3),
            "config_template": _NODE_CONFIG_TEMPLATES.get(nt, {}),
        }
        for score, nt in scored
        if score > 0
    ]



def _match_description_to_node(description: str) -> list[dict]:
    """Return node suggestions ranked by keyword overlap with *description*."""
    desc_lower = description.lower()
    scores: dict[str, float] = {}
    for keywords, node_type in _KEYWORD_NODE_MAP:
        for kw in keywords:
            if kw in desc_lower:
                scores[node_type] = scores.get(node_type, 0.0) + 1.0
    if not scores:
        return []
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [
        {
            "node_type": nt,
            "confidence": round(score / max(scores.values()), 3),
            "config_template": _NODE_CONFIG_TEMPLATES.get(nt, {}),
        }
        for nt, score in ranked
    ]



async def _run_flow_debug(
    flow_id: str,
    run_id: str,
    session_id: str,
    input_data: dict[str, Any],
) -> None:
    """Self-contained debug execution function.

    Iterates over a flow's nodes in topological order. Before each node it
    checks whether a breakpoint is set. If so, the execution pauses and waits
    for the /continue or /skip signal. After each node it records the result
    in the session's execution_history.

    This function is designed to run as a background asyncio task. It never
    modifies the main execution engine.

    Args:
        flow_id: The flow to execute.
        run_id: The pre-generated run ID returned to the caller.
        session_id: The DebugSession to drive.
        input_data: Initial input passed to each node.
    """
    try:
        await _run_flow_debug_inner(flow_id, run_id, session_id, input_data)
    except asyncio.CancelledError:
        # Task was cancelled (e.g. TestClient teardown). Absorb silently so asyncio
        # does not report an unhandled exception in the task.
        logger.debug("Debug background task %s: cancelled (teardown)", run_id)
    except Exception as exc:
        # Background task: DB may be closed (e.g. during test teardown). Log at
        # WARNING so asyncio does not escalate to an unhandled-task-exception ERROR.
        logger.warning("Debug background task %s: unexpected error: %s", run_id, exc)



async def _run_flow_debug_inner(
    flow_id: str,
    run_id: str,
    session_id: str,
    input_data: dict[str, Any],
) -> None:
    """Inner body of _run_flow_debug — separated so the outer function can wrap it."""
    session = debug_session_store.get(session_id)
    if session is None:
        logger.warning("Debug background task: session %s not found, aborting", session_id)
        return

    # Persist a stub WorkflowRun so GET /runs/{run_id} works
    workflow_run_repo = WorkflowRunRepository()
    stub_status: dict[str, Any] = {
        "run_id": run_id,
        "flow_id": flow_id,
        "status": "running",
        "current_applet": None,
        "progress": 0,
        "total_steps": 0,
        "start_time": time.time(),
        "results": {},
        "input_data": input_data,
        "completed_applets": [],
    }
    try:
        await workflow_run_repo.save(stub_status)
    except Exception as exc:
        logger.warning("Debug run %s: failed to persist stub status: %s", run_id, exc)
        # DB is unavailable (e.g. test teardown with closed connection); abort
        # immediately rather than continuing with more DB calls that will also fail.
        session.status = "aborted"
        return

    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        logger.error("Debug run %s: flow %s not found", run_id, flow_id)
        session.status = "aborted"
        session._resume_event.set()
        return

    flow = await Orchestrator.auto_migrate_legacy_nodes(flow, persist=False) or flow

    flow_nodes: list[dict[str, Any]] = flow.get("nodes", [])
    flow_edges: list[dict[str, Any]] = flow.get("edges", [])

    # Build adjacency structures for topological sort
    nodes_by_id: dict[str, dict[str, Any]] = {
        n["id"]: n for n in flow_nodes if isinstance(n, dict) and isinstance(n.get("id"), str)
    }
    edges_by_source: dict[str, list[dict[str, Any]]] = {}
    incoming_sources_by_target: dict[str, list[str]] = {}
    for edge in flow_edges:
        if not isinstance(edge, dict):
            continue
        src = edge.get("source")
        tgt = edge.get("target")
        if not isinstance(src, str) or not isinstance(tgt, str):
            continue
        edges_by_source.setdefault(src, []).append(edge)
        srcs = incoming_sources_by_target.setdefault(tgt, [])
        if src not in srcs:
            srcs.append(src)

    # Produce a flat linear order via topological layers
    layers = Orchestrator._topological_layers(
        nodes_by_id, edges_by_source, incoming_sources_by_target
    )
    ordered_node_ids: list[str] = [nid for layer in layers for nid in layer]

    stub_status["total_steps"] = len(ordered_node_ids)
    try:
        await workflow_run_repo.save(stub_status)
    except Exception as exc:
        logger.warning("Debug run %s: failed to update total_steps: %s", run_id, exc)

    context: dict[str, Any] = {"input": input_data, "results": {}, "run_id": run_id}

    for node_id in ordered_node_ids:
        # Check abort before every node
        if session.status == "aborted":
            logger.info("Debug session %s aborted before node %s", session_id, node_id)
            return

        node = nodes_by_id.get(node_id)
        if not isinstance(node, dict):
            continue

        node_type = str(node.get("type", "")).strip().lower()

        # ---- Breakpoint gate ----
        if node_id in session.breakpoints:
            session.status = "paused"
            session.current_node_id = node_id
            session.current_node_input = dict(input_data)
            session.current_node_output = {}
            session.paused_at = time.time()
            session._resume_event.clear()
            session._skip_flag = False

            logger.info("Debug session %s paused at node %s (breakpoint)", session_id, node_id)

            try:
                await asyncio.wait_for(
                    session._resume_event.wait(),
                    timeout=_DEBUG_BREAKPOINT_TIMEOUT_SECONDS,
                )
            except TimeoutError:
                logger.warning(
                    "Debug session %s timed out waiting at node %s; aborting",
                    session_id,
                    node_id,
                )
                session.status = "aborted"
                return

            # Re-check abort after resume
            if session.status == "aborted":
                logger.info(
                    "Debug session %s aborted after resume signal at node %s",
                    session_id,
                    node_id,
                )
                return

        # ---- Skip or execute ----
        skipped = session._skip_flag
        node_output: dict[str, Any] = {}

        if skipped:
            node_output = {}
            logger.info("Debug session %s skipping node %s", session_id, node_id)
        else:
            if node_type in ("start", "end"):
                node_output = dict(input_data)
            else:
                try:
                    applet = await Orchestrator.load_applet(node_type)
                    node_data = node.get("data", {})
                    if not isinstance(node_data, dict):
                        node_data = {}

                    message = AppletMessage(
                        content=input_data,
                        context=context,
                        metadata={"node_id": node_id, "run_id": run_id, "node_data": node_data},
                    )

                    response: AppletMessage = await asyncio.wait_for(
                        applet.on_message(message),
                        timeout=float(node_data.get("timeout_seconds", 60.0)),
                    )
                    node_output = (
                        response.content
                        if isinstance(response.content, dict)
                        else {"output": response.content}
                    )
                    context.update(response.context)
                    context["results"][node_id] = node_output
                except TimeoutError:
                    logger.warning(
                        "Debug session %s: node %s timed out during execution",
                        session_id,
                        node_id,
                    )
                    node_output = {"error": "timeout"}
                except Exception as exc:
                    logger.error(
                        "Debug session %s: node %s execution error: %s",
                        session_id,
                        node_id,
                        exc,
                    )
                    node_output = {"error": str(exc)}

        # ---- Record history ----
        history_entry: dict[str, Any] = {
            "node_id": node_id,
            "input": dict(input_data),
            "output": node_output,
            "skipped": skipped,
            "timestamp": time.time(),
        }
        session.execution_history.append(history_entry)

        # Update current_node_output so GET reflects the completed node
        if session.current_node_id == node_id:
            session.current_node_output = node_output

        # Reset skip flag for the next node
        session._skip_flag = False

        # Use node output as next input for simple linear flows
        if node_output and not skipped:
            input_data = node_output

        if session.status not in ("paused", "aborted"):
            session.status = "running"

    # All nodes done
    session.status = "completed"
    session.current_node_id = None

    try:
        stub_status["status"] = "success"
        stub_status["end_time"] = time.time()
        await workflow_run_repo.save(stub_status)
    except Exception as exc:
        logger.warning("Debug run %s: failed to persist final status: %s", run_id, exc)

    logger.info("Debug session %s completed (run_id=%s)", session_id, run_id)


# ---- Pydantic request models ----



def _is_admin(user: dict[str, Any]) -> bool:
    """Check if the authenticated user is an admin.

    For now, any user whose email starts with 'admin' is treated as admin.
    """
    return user.get("email", "").startswith("admin")



def _match_output(
    actual: dict[str, Any],
    expected: dict[str, Any],
    mode: str,
) -> tuple[bool, dict[str, Any]]:
    """Compare actual output against expected using the specified match mode.

    Returns (passed, diff_dict). diff_dict maps keys to {expected, actual} for
    any mismatches found.
    """
    diff: dict[str, Any] = {}

    if mode == "exact":
        if actual == expected:
            return True, {}
        # Build diff for all keys in expected
        all_keys = set(expected.keys()) | set(actual.keys())
        for key in all_keys:
            exp_val = expected.get(key)
            act_val = actual.get(key)
            if exp_val != act_val:
                diff[key] = {"expected": exp_val, "actual": act_val}
        return False, diff

    if mode == "keys_present":
        for key in expected:
            if key not in actual:
                diff[key] = {"expected": "(key present)", "actual": "(missing)"}
        return len(diff) == 0, diff

    # Default: "contains" — all expected keys exist with matching values
    for key, exp_val in expected.items():
        if key not in actual:
            diff[key] = {"expected": exp_val, "actual": "(missing)"}
        elif actual[key] != exp_val:
            diff[key] = {"expected": exp_val, "actual": actual[key]}
    return len(diff) == 0, diff



def _extract_final_output(run: dict[str, Any]) -> dict[str, Any]:
    """Extract the output dict from a completed workflow run.

    The run's results dict contains per-node outputs keyed by node ID.
    We look for the last node output that has an 'output' field, falling
    back to the whole results dict if nothing matches.
    """
    results = run.get("results", {})
    if not isinstance(results, dict):
        return {}

    # Collect node outputs (skip the __execution_trace__ key)
    last_output: dict[str, Any] = {}
    for key, val in results.items():
        if key == TRACE_RESULTS_KEY:
            continue
        if isinstance(val, dict) and "output" in val:
            last_output = val["output"] if isinstance(val["output"], dict) else {}

    return last_output if last_output else results


# ---------------------------------------------------------------------------
# Execution Dashboard (N-XX) — real-time admin execution monitoring
# ---------------------------------------------------------------------------






# ---------------------------------------------------------------------------
# Marketplace Analytics (N-45) — stores and models
# Defined here (before routes) so route functions can reference them.
# ---------------------------------------------------------------------------







COLLAB_COLORS: list[str] = [
    "#e57373", "#f06292", "#ba68c8", "#9575cd", "#7986cb",
    "#64b5f6", "#4dd0e1", "#4db6ac", "#81c784", "#aed581",
    "#ffb74d", "#ff8a65", "#a1887f", "#90a4ae", "#78909c",
    "#f44336", "#e91e63", "#9c27b0", "#673ab7", "#3f51b5",
]


def _user_color(user_id: str) -> str:
    """Deterministically assign a color to a user based on their ID hash."""
    idx = int(hashlib.md5(user_id.encode()).hexdigest(), 16) % len(COLLAB_COLORS)
    return COLLAB_COLORS[idx]









