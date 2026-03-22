"""
Admin router for SynApps Orchestrator.

Extracted from main.py (Step 3 of M-1 router decomposition).
"""
from __future__ import annotations

import logging
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
    _is_admin,
)
from apps.orchestrator.request_models import (
    AdminKeyCreateRequest,
    ManagedKeyCreateRequest,
    RotateKeyRequest,
    SetSLAPolicyRequest,
    require_master_key,
)
from apps.orchestrator.stores import (
    admin_key_registry,
    execution_dashboard_store,
    sla_store,
)

logger = logging.getLogger("orchestrator")


# Orchestrator and applet_registry are populated by main.py after all modules load.
# They start as None/empty and are set via _setup_router_globals() in main.py.
Orchestrator = None  # type: ignore[assignment]
applet_registry: dict = {}

from apps.orchestrator.api_keys.manager import api_key_manager  # noqa: E402

# emit_event is populated by main.py after module load (it's defined in main.py)
emit_event = None  # type: ignore[assignment]

router = APIRouter()


# ============================================================
# Admin Routes
# ============================================================

@router.post("/admin/keys", status_code=201, tags=["Admin"])
async def create_admin_key(
    body: AdminKeyCreateRequest,
    _master: str = Depends(require_master_key),
):
    """Create an admin API key (requires master key)."""
    result = admin_key_registry.create(
        name=body.name, scopes=body.scopes, rate_limit=body.rate_limit
    )
    return result


@router.get("/admin/keys", tags=["Admin"])
async def list_admin_keys(
    _master: str = Depends(require_master_key),
):
    """List all admin API keys (requires master key). Plain keys are never returned."""
    keys = admin_key_registry.list_keys()
    return {"keys": keys, "total": len(keys)}


@router.delete("/admin/keys/{key_id}", tags=["Admin"])
async def delete_admin_key(
    key_id: str,
    _master: str = Depends(require_master_key),
):
    """Delete (revoke) an admin API key by ID (requires master key)."""
    if not admin_key_registry.delete(key_id):
        raise HTTPException(status_code=404, detail=f"Admin key '{key_id}' not found")
    return {"message": "Admin key deleted", "id": key_id}


@router.post("/managed-keys", status_code=201, tags=["API Keys"])
async def create_managed_key(
    body: ManagedKeyCreateRequest,
    _master: str = Depends(require_master_key),
):
    """Create a Fernet-encrypted managed API key with scoped permissions."""
    try:
        result = api_key_manager.create(
            name=body.name,
            scopes=body.scopes,
            expires_in=body.expires_in,
            rate_limit=body.rate_limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return result


@router.get("/managed-keys", tags=["API Keys"])
async def list_managed_keys(
    include_inactive: bool = Query(False, description="Include revoked/expired keys"),
    _master: str = Depends(require_master_key),
):
    """List all managed API keys with usage stats."""
    keys = api_key_manager.list_keys(include_inactive=include_inactive)
    return {"keys": keys, "total": len(keys)}


@router.get("/managed-keys/{key_id}", tags=["API Keys"])
async def get_managed_key(
    key_id: str,
    _master: str = Depends(require_master_key),
):
    """Get a single managed API key by ID."""
    entry = api_key_manager.get(key_id)
    if not entry:
        raise HTTPException(status_code=404, detail=f"Managed key '{key_id}' not found")
    return entry


@router.post("/managed-keys/{key_id}/rotate", tags=["API Keys"])
async def rotate_managed_key(
    key_id: str,
    body: RotateKeyRequest,
    _master: str = Depends(require_master_key),
):
    """Rotate a managed key. Old key remains valid for the grace period."""
    result = api_key_manager.rotate(key_id, grace_period=body.grace_period)
    if not result:
        raise HTTPException(status_code=404, detail=f"Managed key '{key_id}' not found or inactive")
    await emit_event(
        "key.rotated",
        {
            "key_id": key_id,
            "grace_period": body.grace_period,
        },
    )
    return result


@router.post("/managed-keys/{key_id}/revoke", tags=["API Keys"])
async def revoke_managed_key(
    key_id: str,
    _master: str = Depends(require_master_key),
):
    """Revoke (deactivate) a managed key immediately."""
    if not api_key_manager.revoke(key_id):
        raise HTTPException(status_code=404, detail=f"Managed key '{key_id}' not found")
    return {"message": "Key revoked", "id": key_id}


@router.delete("/managed-keys/{key_id}", tags=["API Keys"])
async def delete_managed_key(
    key_id: str,
    _master: str = Depends(require_master_key),
):
    """Permanently delete a managed key."""
    if not api_key_manager.delete(key_id):
        raise HTTPException(status_code=404, detail=f"Managed key '{key_id}' not found")
    return {"message": "Key deleted", "id": key_id}


@router.put("/sla/policies/{flow_id}", tags=["SLA"])
async def set_sla_policy(
    flow_id: str,
    body: SetSLAPolicyRequest,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict[str, Any]:
    """Create or update an SLA policy for a workflow."""
    policy = sla_store.set_policy(
        flow_id=flow_id,
        owner_id=current_user["id"],
        max_duration_seconds=body.max_duration_seconds,
        alert_threshold_pct=body.alert_threshold_pct,
    )
    return policy


@router.get("/sla/policies/{flow_id}", tags=["SLA"])
async def get_sla_policy(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict[str, Any]:
    """Get the SLA policy for a workflow."""
    policy = sla_store.get_policy(flow_id)
    if policy is None:
        raise HTTPException(status_code=404, detail="No SLA policy for this flow")
    return policy


@router.delete("/sla/policies/{flow_id}", status_code=204, tags=["SLA"])
async def delete_sla_policy(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> None:
    """Delete the SLA policy for a workflow."""
    sla_store.delete_policy(flow_id)
    return None


@router.get("/sla/policies", tags=["SLA"])
async def list_sla_policies(
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> list[dict[str, Any]]:
    """List all SLA policies owned by the authenticated user."""
    return sla_store.list_policies(current_user["id"])


@router.get("/sla/violations", tags=["SLA"])
async def list_sla_violations(
    flow_id: str | None = None,
    limit: int = 50,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> list[dict[str, Any]]:
    """List SLA violations for the authenticated user, newest first."""
    return sla_store.list_violations(flow_id=flow_id, owner_id=current_user["id"], limit=limit)


@router.get("/sla/dashboard", tags=["SLA"])
async def sla_dashboard(
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict[str, Any]:
    """Return SLA compliance statistics for the authenticated user."""
    return sla_store.compliance_stats(current_user["id"])


@router.get("/admin/executions", tags=["Admin"])
async def admin_list_executions(
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict[str, Any]:
    """List all recent executions (admin only)."""
    if not _is_admin(current_user):
        raise HTTPException(status_code=403, detail="Admin access required")
    return {"items": execution_dashboard_store.list_recent()}


@router.get("/admin/executions/active", tags=["Admin"])
async def admin_list_active_executions(
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict[str, Any]:
    """List currently active (running/paused) executions (admin only)."""
    if not _is_admin(current_user):
        raise HTTPException(status_code=403, detail="Admin access required")
    return {"items": execution_dashboard_store.list_active()}


@router.get("/admin/executions/stats", tags=["Admin"])
async def admin_execution_stats(
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict[str, Any]:
    """Return aggregate execution statistics (admin only)."""
    if not _is_admin(current_user):
        raise HTTPException(status_code=403, detail="Admin access required")
    return execution_dashboard_store.stats()


@router.get("/admin/executions/{run_id}", tags=["Admin"])
async def admin_get_execution(
    run_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict[str, Any]:
    """Get a single execution entry by run_id (admin only)."""
    if not _is_admin(current_user):
        raise HTTPException(status_code=403, detail="Admin access required")
    entry = execution_dashboard_store.get(run_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Execution not found")
    return entry


@router.post("/admin/executions/{run_id}/pause", tags=["Admin"])
async def admin_pause_execution(
    run_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict[str, Any]:
    """Pause a running execution (admin only)."""
    if not _is_admin(current_user):
        raise HTTPException(status_code=403, detail="Admin access required")
    if not execution_dashboard_store.pause(run_id):
        raise HTTPException(status_code=404, detail="Execution not found")
    return {"status": "paused", "run_id": run_id}


@router.post("/admin/executions/{run_id}/resume", tags=["Admin"])
async def admin_resume_execution(
    run_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict[str, Any]:
    """Resume a paused execution (admin only)."""
    if not _is_admin(current_user):
        raise HTTPException(status_code=403, detail="Admin access required")
    if not execution_dashboard_store.resume(run_id):
        raise HTTPException(status_code=404, detail="Execution not found")
    return {"status": "running", "run_id": run_id}


@router.post("/admin/executions/{run_id}/kill", tags=["Admin"])
async def admin_kill_execution(
    run_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict[str, Any]:
    """Kill a running execution (admin only)."""
    if not _is_admin(current_user):
        raise HTTPException(status_code=403, detail="Admin access required")
    if not execution_dashboard_store.kill(run_id):
        raise HTTPException(status_code=404, detail="Execution not found")
    return {"status": "killed", "run_id": run_id}

