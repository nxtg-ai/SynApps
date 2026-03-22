"""
Flows router for SynApps Orchestrator.

Extracted from main.py (Step 3 of M-1 router decomposition).
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
)

from apps.orchestrator.dependencies import (
    get_authenticated_user,
)
from apps.orchestrator.helpers import (
    SUBFLOW_NODE_TYPE,
    _check_flow_permission,
    _share_record_response,
    paginate,
)
from apps.orchestrator.repositories import FlowRepository
from apps.orchestrator.request_models import (
    CreateFlowRequest,
    FlowUpdateRequest,
    SubflowValidateRequest,
)
from apps.orchestrator.stores import (
    activity_feed_store,
    audit_log_store,
    flow_access_log_store,
    flow_archive_store,
    flow_edit_lock_store,
    flow_expiry_store,
    flow_favorite_store,
    flow_group_store,
    flow_pin_store,
    flow_priority_store,
    flow_share_store,
    flow_tag_store,
    flow_watch_store,
    workflow_permission_store,
)

logger = logging.getLogger("orchestrator")


# Orchestrator and applet_registry are populated by main.py after all modules load.
# They start as None/empty and are set via _setup_router_globals() in main.py.
Orchestrator = None  # type: ignore[assignment]
applet_registry: dict = {}

# flow_version_registry is populated by main.py after module load
flow_version_registry = None  # type: ignore[assignment]

router = APIRouter()


# ============================================================
# Flows Routes
# ============================================================

@router.post("/flows", status_code=201, tags=["Flows"])
async def create_flow(
    flow: CreateFlowRequest,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Create or update a flow with strict validation."""
    flow_id = flow.id if flow.id else str(uuid.uuid4())

    flow_dict = flow.model_dump()
    flow_dict["id"] = flow_id
    flow_dict, migrated = Orchestrator.migrate_legacy_nodes(flow_dict)
    if migrated:
        logger.info("Applied legacy node migration while creating flow '%s'", flow_id)
    await FlowRepository.save(flow_dict)
    # Set ownership when created by an authenticated (non-anonymous) user
    user_email = current_user.get("email", "")
    if user_email and user_email != "anonymous@local":
        workflow_permission_store.set_owner(flow_id, user_email)
    audit_log_store.record(
        user_email or "anonymous",
        "workflow_created",
        "flow",
        flow_id,
        detail=f"Flow '{flow_dict.get('name', flow_id)}' created.",
    )
    return {"message": "Flow created", "id": flow_id}


@router.get("/flows", tags=["Flows"])
async def list_flows(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    archived: bool = Query(False, description="If true, return only archived flows. Default returns only non-archived flows."),
    group: str | None = Query(None, description="Filter by group name (case-insensitive). Omit to return all groups."),
    priority: str | None = Query(None, description="Filter by priority (critical/high/medium/low)."),
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """List flows with pagination.

    - Default (archived=false): only non-archived flows.
    - archived=true: only archived flows.
    - group=<name>: only flows in the given group.
    - priority=<level>: only flows with the given priority level.
    """
    flows = await FlowRepository.get_all()
    migrated_flows: list[dict[str, Any]] = []
    group_norm = group.lower().strip() if group else None
    priority_norm = priority.lower().strip() if priority else None
    for flow in flows:
        migrated_flow = await Orchestrator.auto_migrate_legacy_nodes(flow, persist=True)
        if isinstance(migrated_flow, dict):
            fid = migrated_flow["id"]
            is_archived = flow_archive_store.is_archived(fid)
            if is_archived != archived:
                continue
            if group_norm is not None and flow_group_store.get(fid) != group_norm:
                continue
            if priority_norm is not None and flow_priority_store.get(fid) != priority_norm:
                continue
            migrated_flows.append(migrated_flow)
    return paginate(migrated_flows, page, page_size)


@router.get("/flows/search", tags=["Flows"])
async def search_flows(
    q: str = Query("", description="Search term matched against flow name (case-insensitive substring)."),
    tag: list[str] = Query([], description="Filter by tag(s). Multiple values = AND logic."),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Search flows by name and/or tags.

    - `q` — substring match on flow name (case-insensitive).
    - `tag` — one or more tag values; flow must have ALL specified tags (AND logic).
    - Both filters are optional; omitting both returns all flows (same as GET /flows).
    """
    flows = await FlowRepository.get_all()
    results: list[dict[str, Any]] = []
    q_lower = q.strip().lower()
    tag_set = {t.lower().strip() for t in tag if t.strip()}
    for flow in flows:
        if q_lower and q_lower not in flow.get("name", "").lower():
            continue
        if tag_set:
            flow_tags = set(flow_tag_store.get(flow["id"]))
            if not tag_set.issubset(flow_tags):
                continue
        results.append(flow)
    return paginate(results, page, page_size)


@router.get("/flows/favorites", tags=["Flows"])
async def list_favorite_flows(
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Return all flows the current user has favorited, sorted by name."""
    user_email = current_user.get("email", "anonymous@local")
    fav_ids = flow_favorite_store.get(user_email)
    flows: list[dict[str, Any]] = []
    for fid in fav_ids:
        flow = await FlowRepository.get_by_id(fid)
        if flow:
            flows.append(flow)
    flows.sort(key=lambda f: f.get("name", "").lower())
    return {"items": flows, "total": len(flows)}


@router.get("/flows/pinned", tags=["Flows"])
async def list_pinned_flows(
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Return all flows the current user has pinned, in pin order (oldest first)."""
    user_email = current_user.get("email", "anonymous@local")
    pin_ids = flow_pin_store.get(user_email)
    flows: list[dict[str, Any]] = []
    for fid in pin_ids:
        flow = await FlowRepository.get_by_id(fid)
        if flow:
            flows.append(flow)
    return {"items": flows, "total": len(flows)}


@router.get("/flows/groups", tags=["Flows"])
async def list_flow_groups(
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Return all group names with their flow counts.

    Registered before /flows/{flow_id} to prevent path shadowing.
    """
    groups = flow_group_store.all_groups()
    return {
        "groups": [{"name": name, "flow_count": count} for name, count in sorted(groups.items())],
        "total": len(groups),
    }


@router.get("/flows/watched", tags=["Flows"])
async def list_watched_flows(
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Return the list of flows the authenticated user is watching.

    Registered before /flows/{flow_id} to prevent path shadowing.
    """
    user = current_user.get("email", "anonymous@local")
    flow_ids = flow_watch_store.watched_by_user(user)
    return {"flow_ids": flow_ids, "total": len(flow_ids)}


@router.get("/flows/shared/{token}", tags=["Flows"])
async def get_shared_flow_early(token: str):
    """Fetch a flow via a share token. No authentication required.

    Returns 404 if the token does not exist or has expired.
    Registered before /flows/{flow_id} to prevent path shadowing.
    """
    record = flow_share_store.get(token)
    if not record:
        raise HTTPException(status_code=404, detail="Share token not found or expired")
    flow = await FlowRepository.get_by_id(record["flow_id"])
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
    return {"flow": flow, "share": _share_record_response(record)}


@router.get("/flows/{flow_id}", tags=["Flows"])
async def get_flow(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Get a flow by ID.

    Returns 410 Gone if the flow has an expiry set and that expiry is in the past.
    """
    flow = await FlowRepository.get_by_id(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
    if flow_expiry_store.is_expired(flow_id):
        raise HTTPException(status_code=410, detail="Flow has expired")
    flow = await Orchestrator.auto_migrate_legacy_nodes(flow, persist=True)
    flow_access_log_store.record(flow_id, current_user.get("email", "anonymous@local"))
    return flow


@router.delete("/flows/{flow_id}", tags=["Flows"])
async def delete_flow(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Delete a flow."""
    flow = await FlowRepository.get_by_id(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
    await FlowRepository.delete(flow_id)
    actor = current_user.get("email", "unknown")
    audit_log_store.record(
        actor,
        "workflow_deleted",
        "flow",
        flow_id,
        detail=f"Flow '{flow.get('name', flow_id)}' deleted.",
    )
    return {"message": "Flow deleted"}


@router.put("/flows/{flow_id}", tags=["Flows"])
async def update_flow(
    flow_id: str,
    body: FlowUpdateRequest,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Replace a flow's nodes and edges, saving the previous version to history.

    If the flow exists, its current state is snapshotted in ``FlowVersionRegistry``
    before being overwritten. If it does not exist, a new flow is created (no
    snapshot is taken).
    """
    _check_flow_permission(flow_id, current_user.get("email", ""), "editor")
    if flow_edit_lock_store.is_locked(flow_id):
        lock = flow_edit_lock_store.get(flow_id)
        raise HTTPException(
            status_code=423,
            detail=f"Flow is locked by {lock['locked_by']}",
        )
    existing = await FlowRepository.get_by_id(flow_id)
    if existing:
        flow_version_registry.snapshot(flow_id, existing)

    flow_data: dict[str, Any] = {
        "id": flow_id,
        "name": body.name or (existing.get("name") if existing else "Unnamed Flow"),
        "nodes": body.nodes,
        "edges": body.edges,
    }
    saved = await FlowRepository.save(flow_data)
    actor = current_user.get("email", "unknown") if current_user else "unknown"
    activity_feed_store.record(
        flow_id,
        actor=actor,
        action="flow_edited",
        detail=f"Flow '{flow_data['name']}' updated.",
    )
    audit_log_store.record(
        actor, "workflow_updated", "flow", flow_id, detail=f"Flow '{flow_data['name']}' updated."
    )
    return saved


@router.get("/subflows", tags=["Subflows"])
async def list_subflows(
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict[str, Any]:
    """List all workflows available to use as subflows.

    Returns the same format as GET /flows but with an additional
    ``is_subflow_compatible: true`` flag on each entry.
    """
    flows = await FlowRepository.get_all()
    result: list[dict[str, Any]] = []
    for flow in flows:
        if not isinstance(flow, dict):
            continue
        entry = dict(flow)
        entry["is_subflow_compatible"] = True
        result.append(entry)
    return {"flows": result, "total": len(result)}


@router.post("/subflows/validate", tags=["Subflows"])
async def validate_subflow(
    body: SubflowValidateRequest,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict[str, Any]:
    """Validate that using subflow_id inside parent_flow_id would not create a cycle.

    Returns ``{"valid": true, "error": null}`` when safe, or
    ``{"valid": false, "error": "<reason>"}`` when a circular dependency is detected.
    """
    parent_flow = await FlowRepository.get_by_id(body.parent_flow_id)
    if parent_flow is None:
        return {"valid": False, "error": f"Parent workflow '{body.parent_flow_id}' not found"}

    subflow = await FlowRepository.get_by_id(body.subflow_id)
    if subflow is None:
        return {"valid": False, "error": f"Subflow workflow '{body.subflow_id}' not found"}

    # Detect direct self-reference
    if body.parent_flow_id == body.subflow_id:
        return {
            "valid": False,
            "error": f"Workflow '{body.parent_flow_id}' cannot reference itself as a subflow",
        }

    # Walk the subflow's node graph: if any subflow node inside it references
    # the parent, that is a circular dependency.
    def _collect_subflow_ids(flow_dict: dict[str, Any]) -> set[str]:
        ids: set[str] = set()
        for node in flow_dict.get("nodes", []):
            if not isinstance(node, dict):
                continue
            if str(node.get("type", "")).lower() == SUBFLOW_NODE_TYPE:
                node_data = node.get("data", {})
                if isinstance(node_data, dict):
                    wid = node_data.get("workflow_id")
                    if wid:
                        ids.add(str(wid))
        return ids

    # BFS over the subflow graph to check for the parent appearing anywhere
    visited_flows: set[str] = {body.subflow_id}
    queue: list[str] = [body.subflow_id]
    while queue:
        current_id = queue.pop(0)
        current_flow = await FlowRepository.get_by_id(current_id)
        if current_flow is None:
            continue
        child_ids = _collect_subflow_ids(current_flow)
        for cid in child_ids:
            if cid == body.parent_flow_id:
                return {
                    "valid": False,
                    "error": (
                        f"Circular dependency detected: '{body.subflow_id}' "
                        f"transitively references '{body.parent_flow_id}'"
                    ),
                }
            if cid not in visited_flows:
                visited_flows.add(cid)
                queue.append(cid)

    return {"valid": True, "error": None}

