"""
Collaboration router for SynApps Orchestrator.

Extracted from main.py (Step 3 of M-1 router decomposition).
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
)

from apps.orchestrator.dependencies import (
    get_authenticated_user,
)
from apps.orchestrator.helpers import (
    _user_color,
)
from apps.orchestrator.stores import (
    collaboration_activity_store,
    node_lock_store,
    presence_store,
)

logger = logging.getLogger("orchestrator")


# Orchestrator and applet_registry are populated by main.py after all modules load.
# They start as None/empty and are set via _setup_router_globals() in main.py.
Orchestrator = None  # type: ignore[assignment]
applet_registry: dict = {}

router = APIRouter()


# ============================================================
# Collaboration Routes
# ============================================================

@router.post("/flows/{flow_id}/collaboration/join", tags=["Collaboration"])
async def collaboration_join(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict[str, Any]:
    """Join a flow's collaboration session.

    Registers the current user's presence and records a 'joined' activity event.
    Returns the user's assigned color and the current list of collaborators.
    """
    user_id = current_user["id"]
    username = current_user.get("email", user_id)
    color = _user_color(user_id)
    presence_store.join(flow_id, user_id, username, color)
    collaboration_activity_store.record(flow_id, user_id, username, "joined")
    collaborators = presence_store.get_presence(flow_id)
    return {"user_id": user_id, "color": color, "collaborators": collaborators}


@router.delete("/flows/{flow_id}/collaboration/leave", tags=["Collaboration"])
async def collaboration_leave(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict[str, str]:
    """Leave a flow's collaboration session.

    Removes the user's presence, releases all held node locks,
    and records a 'left' activity event.
    """
    user_id = current_user["id"]
    username = current_user.get("email", user_id)
    presence_store.leave(flow_id, user_id)
    node_lock_store.release_all_for_user(flow_id, user_id)
    collaboration_activity_store.record(flow_id, user_id, username, "left")
    return {"status": "left"}


@router.post("/flows/{flow_id}/collaboration/heartbeat", tags=["Collaboration"])
async def collaboration_heartbeat(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict[str, str]:
    """Update the authenticated user's last-seen timestamp for presence."""
    presence_store.heartbeat(flow_id, current_user["id"])
    return {"status": "ok"}


@router.get("/flows/{flow_id}/collaboration/presence", tags=["Collaboration"])
async def collaboration_presence(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict[str, Any]:
    """Return the list of collaborators currently active on a flow."""
    collaborators = presence_store.get_presence(flow_id)
    return {"collaborators": collaborators}


@router.post("/flows/{flow_id}/collaboration/lock/{node_id}", tags=["Collaboration"])
async def collaboration_lock_acquire(
    flow_id: str,
    node_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict[str, Any]:
    """Acquire an optimistic lock on a workflow node.

    Returns 200 if the lock was acquired, 409 if already locked by another user.
    """
    user_id = current_user["id"]
    username = current_user.get("email", user_id)
    acquired = node_lock_store.acquire(flow_id, node_id, user_id, username)
    if not acquired:
        raise HTTPException(
            status_code=409,
            detail="Node is already locked by another user",
        )
    collaboration_activity_store.record(
        flow_id, user_id, username, "locked_node", node_id,
    )
    return {"locked": True, "node_id": node_id, "user_id": user_id}


@router.delete("/flows/{flow_id}/collaboration/lock/{node_id}", tags=["Collaboration"])
async def collaboration_lock_release(
    flow_id: str,
    node_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict[str, Any]:
    """Release an optimistic lock on a workflow node."""
    user_id = current_user["id"]
    username = current_user.get("email", user_id)
    released = node_lock_store.release(flow_id, node_id, user_id)
    if released:
        collaboration_activity_store.record(
            flow_id, user_id, username, "released_node", node_id,
        )
    return {"released": released, "node_id": node_id}


@router.get("/flows/{flow_id}/collaboration/locks", tags=["Collaboration"])
async def collaboration_locks(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict[str, Any]:
    """Return all active node locks for a flow."""
    locks = node_lock_store.get_locks(flow_id)
    return {"locks": locks}


@router.get("/flows/{flow_id}/collaboration/activity", tags=["Collaboration"])
async def collaboration_activity(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict[str, Any]:
    """Return the most recent 20 activity events for a flow."""
    activity = collaboration_activity_store.get_activity(flow_id, limit=20)
    return {"activity": activity}

