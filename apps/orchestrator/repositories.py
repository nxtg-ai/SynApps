"""
Repository classes for database operations.

This module provides repository classes that handle database operations for the various models.
"""

import hashlib
import logging
import time
import uuid
from typing import Any

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.orm import selectinload

from apps.orchestrator.db import get_db_session
from apps.orchestrator.models import (
    AdminKey,
    AuditLogEntry,
    Flow,
    FlowEdge,
    FlowNode,
    FlowTag,
    MarketplaceListing,
    WorkflowPermission,
    WorkflowRun,
)

# Configure logging
logger = logging.getLogger("repositories")


class FlowRepository:
    """Async repository for Flow operations."""

    @staticmethod
    async def save(flow_data: dict[str, Any]) -> dict[str, Any]:
        flow_id = flow_data.get("id") or str(uuid.uuid4())
        async with get_db_session() as session:
            # Check if flow exists
            result = await session.execute(select(Flow).where(Flow.id == flow_id))
            flow = result.scalars().first()
            if flow:
                # Update existing
                flow.name = flow_data.get("name", flow.name)
                await session.execute(delete(FlowNode).where(FlowNode.flow_id == flow_id))
                await session.execute(delete(FlowEdge).where(FlowEdge.flow_id == flow_id))
            else:
                flow = Flow(id=flow_id, name=flow_data.get("name", "Unnamed Flow"))
                session.add(flow)
                await session.flush()
            # Add nodes
            for node_data in flow_data.get("nodes", []):
                pos = node_data.get("position", {"x": 0, "y": 0})
                node = FlowNode(
                    id=node_data.get("id", str(uuid.uuid4())),
                    flow_id=flow.id,
                    type=node_data.get("type", "unknown"),
                    position_x=pos.get("x", 0),
                    position_y=pos.get("y", 0),
                    data=node_data.get("data", {}),
                )
                session.add(node)
            # Add edges
            for edge_data in flow_data.get("edges", []):
                edge = FlowEdge(
                    id=edge_data.get("id", str(uuid.uuid4())),
                    flow_id=flow.id,
                    source=edge_data.get("source", ""),
                    target=edge_data.get("target", ""),
                    animated=edge_data.get("animated", False),
                )
                session.add(edge)
            await session.commit()
            result = await session.execute(
                select(Flow)
                .options(selectinload(Flow.nodes), selectinload(Flow.edges))
                .where(Flow.id == flow.id)
            )
            complete_flow = result.scalars().first()
            return complete_flow.to_dict()

    @staticmethod
    async def get_by_id(flow_id: str) -> dict[str, Any] | None:
        async with get_db_session() as session:
            result = await session.execute(
                select(Flow)
                .options(selectinload(Flow.nodes), selectinload(Flow.edges))
                .where(Flow.id == flow_id)
            )
            flow = result.scalars().first()
            return flow.to_dict() if flow else None

    @staticmethod
    async def get_all() -> list[dict[str, Any]]:
        async with get_db_session() as session:
            result = await session.execute(
                select(Flow).options(selectinload(Flow.nodes), selectinload(Flow.edges))
            )
            flows = result.scalars().all()
            return [flow.to_dict() for flow in flows]

    @staticmethod
    async def delete(flow_id: str) -> bool:
        async with get_db_session() as session:
            result = await session.execute(select(Flow).where(Flow.id == flow_id))
            flow = result.scalars().first()
            if not flow:
                return False
            await session.delete(flow)
            await session.commit()
            return True


class WorkflowRunRepository:
    """Async repository for WorkflowRun operations."""

    @staticmethod
    async def save(run_data: dict[str, Any]) -> dict[str, Any]:
        run_id = run_data.get("run_id") or str(uuid.uuid4())
        async with get_db_session() as session:
            result = await session.execute(select(WorkflowRun).where(WorkflowRun.id == run_id))
            run = result.scalars().first()
            if run:
                # Update
                for field in [
                    "status",
                    "current_applet",
                    "progress",
                    "total_steps",
                    "end_time",
                    "results",
                    "error",
                    "error_details",
                    "input_data",
                    "completed_applets",
                ]:
                    if field in run_data:
                        setattr(run, field, run_data[field])
            else:
                run = WorkflowRun(
                    id=run_id,
                    flow_id=run_data.get("flow_id"),
                    status=run_data.get("status", "idle"),
                    current_applet=run_data.get("current_applet"),
                    progress=run_data.get("progress", 0),
                    total_steps=run_data.get("total_steps", 0),
                    start_time=run_data.get("start_time", time.time()),
                    end_time=run_data.get("end_time"),
                    results=run_data.get("results", {}),
                    error=run_data.get("error"),
                    error_details=run_data.get("error_details", {}),
                    input_data=run_data.get("input_data"),
                    completed_applets=run_data.get("completed_applets", []),
                )
                session.add(run)
            await session.commit()
            return run.to_dict()

    @staticmethod
    async def get_by_run_id(run_id: str) -> dict[str, Any] | None:
        async with get_db_session() as session:
            result = await session.execute(select(WorkflowRun).where(WorkflowRun.id == run_id))
            run = result.scalars().first()
            return run.to_dict() if run else None

    @staticmethod
    async def get_all() -> list[dict[str, Any]]:
        async with get_db_session() as session:
            result = await session.execute(select(WorkflowRun))
            runs = result.scalars().all()
            return [run.to_dict() for run in runs]


class FlowTagRepository:
    """Async repository for FlowTag persistence (M-2)."""

    @staticmethod
    async def add(flow_id: str, tag: str) -> None:
        """Add a tag to a flow; no-op if already exists."""
        tag = tag.strip().lower()
        async with get_db_session() as session:
            exists = await session.execute(
                select(FlowTag).where(FlowTag.flow_id == flow_id, FlowTag.tag == tag)
            )
            if not exists.scalars().first():
                session.add(FlowTag(flow_id=flow_id, tag=tag))
                await session.commit()

    @staticmethod
    async def remove(flow_id: str, tag: str) -> bool:
        """Remove a tag from a flow. Returns True if the tag existed."""
        tag = tag.strip().lower()
        async with get_db_session() as session:
            result = await session.execute(
                delete(FlowTag)
                .where(FlowTag.flow_id == flow_id, FlowTag.tag == tag)
                .returning(FlowTag.tag)
            )
            await session.commit()
            return result.rowcount > 0

    @staticmethod
    async def get(flow_id: str) -> list[str]:
        """Return sorted list of tags for a flow."""
        async with get_db_session() as session:
            result = await session.execute(
                select(FlowTag.tag).where(FlowTag.flow_id == flow_id).order_by(FlowTag.tag)
            )
            return list(result.scalars().all())

    @staticmethod
    async def delete_flow(flow_id: str) -> None:
        """Remove all tags for a flow (called on flow deletion)."""
        async with get_db_session() as session:
            await session.execute(delete(FlowTag).where(FlowTag.flow_id == flow_id))
            await session.commit()

    @staticmethod
    async def list_all() -> list[dict[str, Any]]:
        """Return all flow-tag pairs (used for store hydration)."""
        async with get_db_session() as session:
            result = await session.execute(select(FlowTag))
            return [r.to_dict() for r in result.scalars().all()]


class AdminKeyRepository:
    """Async repository for AdminKey persistence (M-2)."""

    @staticmethod
    def _hash_key(plain_key: str) -> str:
        return hashlib.sha256(plain_key.encode()).hexdigest()

    @staticmethod
    async def create(key_data: dict[str, Any], plain_key: str) -> dict[str, Any]:
        """Persist a new admin key. plain_key is hashed before storage."""
        async with get_db_session() as session:
            row = AdminKey(
                id=key_data["id"],
                name=key_data["name"],
                key_prefix=key_data["key_prefix"],
                key_hash=AdminKeyRepository._hash_key(plain_key),
                scopes=key_data.get("scopes", ["read", "write"]),
                rate_limit=key_data.get("rate_limit"),
                is_active=key_data.get("is_active", True),
                created_at=key_data.get("created_at", time.time()),
                last_used_at=key_data.get("last_used_at"),
                expires_at=key_data.get("expires_at"),
            )
            session.add(row)
            await session.commit()
            return row.to_dict()

    @staticmethod
    async def get(key_id: str) -> dict[str, Any] | None:
        async with get_db_session() as session:
            result = await session.execute(select(AdminKey).where(AdminKey.id == key_id))
            row = result.scalars().first()
            return row.to_dict() if row else None

    @staticmethod
    async def list_keys() -> list[dict[str, Any]]:
        async with get_db_session() as session:
            result = await session.execute(
                select(AdminKey).where(AdminKey.is_active == True).order_by(AdminKey.created_at)  # noqa: E712
            )
            return [r.to_dict() for r in result.scalars().all()]

    @staticmethod
    async def revoke(key_id: str) -> bool:
        async with get_db_session() as session:
            result = await session.execute(
                update(AdminKey)
                .where(AdminKey.id == key_id)
                .values(is_active=False)
                .returning(AdminKey.id)
            )
            await session.commit()
            return result.rowcount > 0

    @staticmethod
    async def delete(key_id: str) -> bool:
        async with get_db_session() as session:
            result = await session.execute(
                delete(AdminKey).where(AdminKey.id == key_id).returning(AdminKey.id)
            )
            await session.commit()
            return result.rowcount > 0

    @staticmethod
    async def touch_last_used(key_id: str) -> None:
        async with get_db_session() as session:
            await session.execute(
                update(AdminKey).where(AdminKey.id == key_id).values(last_used_at=time.time())
            )
            await session.commit()

    @staticmethod
    async def validate_key(plain_key: str) -> dict[str, Any] | None:
        """Look up an active key by prefix then verify the hash."""
        if not plain_key.startswith("sk-"):
            return None
        prefix = plain_key[:12]
        key_hash = AdminKeyRepository._hash_key(plain_key)
        async with get_db_session() as session:
            result = await session.execute(
                select(AdminKey).where(
                    AdminKey.key_prefix == prefix,
                    AdminKey.key_hash == key_hash,
                    AdminKey.is_active == True,  # noqa: E712
                )
            )
            row = result.scalars().first()
            return row.to_dict() if row else None

    @staticmethod
    async def list_all() -> list[dict[str, Any]]:
        """Return all admin keys (used for store hydration)."""
        async with get_db_session() as session:
            result = await session.execute(select(AdminKey))
            return [r.to_dict() for r in result.scalars().all()]


class MarketplaceListingRepository:
    """Async repository for MarketplaceListing persistence (M-2)."""

    @staticmethod
    async def publish(data: dict[str, Any]) -> dict[str, Any]:
        """Insert or update a marketplace listing."""
        async with get_db_session() as session:
            listing_id = data.get("id") or str(uuid.uuid4())
            result = await session.execute(
                select(MarketplaceListing).where(MarketplaceListing.id == listing_id)
            )
            row = result.scalars().first()
            if row:
                for field in [
                    "name", "description", "category", "tags", "author",
                    "publisher_id", "nodes", "edges", "featured",
                ]:
                    if field in data:
                        setattr(row, field, data[field])
            else:
                row = MarketplaceListing(
                    id=listing_id,
                    name=data.get("name", "Untitled"),
                    description=data.get("description", ""),
                    category=data.get("category", "general"),
                    tags=data.get("tags", []),
                    author=data.get("author", "anonymous"),
                    publisher_id=data.get("publisher_id"),
                    nodes=data.get("nodes", []),
                    edges=data.get("edges", []),
                    install_count=data.get("install_count", 0),
                    install_timestamps=data.get("install_timestamps", []),
                    featured=data.get("featured", False),
                    published_at=data.get("published_at", time.time()),
                    is_builtin=data.get("is_builtin", False),
                )
                session.add(row)
            await session.commit()
            return row.to_dict()

    @staticmethod
    async def get(listing_id: str) -> dict[str, Any] | None:
        async with get_db_session() as session:
            result = await session.execute(
                select(MarketplaceListing).where(MarketplaceListing.id == listing_id)
            )
            row = result.scalars().first()
            return row.to_dict() if row else None

    @staticmethod
    async def list_all() -> list[dict[str, Any]]:
        async with get_db_session() as session:
            result = await session.execute(
                select(MarketplaceListing).order_by(MarketplaceListing.published_at.desc())
            )
            return [r.to_dict() for r in result.scalars().all()]

    @staticmethod
    async def search(
        q: str = "",
        category: str = "",
        tags: list[str] | None = None,
        page: int = 1,
        per_page: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        """Search listings; returns (results, total_count)."""
        async with get_db_session() as session:
            stmt = select(MarketplaceListing)
            if q:
                q_lower = f"%{q.lower()}%"
                stmt = stmt.where(
                    or_(
                        func.lower(MarketplaceListing.name).like(q_lower),
                        func.lower(MarketplaceListing.description).like(q_lower),
                    )
                )
            if category:
                stmt = stmt.where(
                    func.lower(MarketplaceListing.category) == category.lower()
                )
            # Total count
            count_result = await session.execute(
                select(func.count()).select_from(stmt.subquery())
            )
            total = count_result.scalar() or 0
            # Paginate
            stmt = (
                stmt.order_by(
                    MarketplaceListing.featured.desc(),
                    MarketplaceListing.install_count.desc(),
                    MarketplaceListing.published_at.desc(),
                )
                .offset((page - 1) * per_page)
                .limit(per_page)
            )
            result = await session.execute(stmt)
            rows = result.scalars().all()
            # Filter by tags (JSON column — done in Python for SQLite compat)
            if tags:
                tag_set = {t.lower() for t in tags}
                rows = [r for r in rows if tag_set.issubset({t.lower() for t in (r.tags or [])})]
            return [r.to_dict() for r in rows], total

    @staticmethod
    async def increment_install(listing_id: str, ts: float) -> bool:
        async with get_db_session() as session:
            result = await session.execute(
                select(MarketplaceListing).where(MarketplaceListing.id == listing_id)
            )
            row = result.scalars().first()
            if not row:
                return False
            row.install_count += 1
            row.install_timestamps = list(row.install_timestamps or []) + [ts]
            await session.commit()
            return True

    @staticmethod
    async def featured() -> list[dict[str, Any]]:
        async with get_db_session() as session:
            result = await session.execute(
                select(MarketplaceListing)
                .order_by(
                    MarketplaceListing.install_count.desc(),
                    MarketplaceListing.published_at.desc(),
                )
                .limit(10)
            )
            return [r.to_dict() for r in result.scalars().all()]


class WorkflowPermissionRepository:
    """Async repository for WorkflowPermission persistence (M-2)."""

    @staticmethod
    async def upsert(flow_id: str, owner_id: str, grants: dict[str, str]) -> None:
        """Insert or update the permission record for a flow."""
        async with get_db_session() as session:
            result = await session.execute(
                select(WorkflowPermission).where(WorkflowPermission.flow_id == flow_id)
            )
            row = result.scalars().first()
            if row:
                row.owner_id = owner_id
                row.grants = grants
            else:
                session.add(
                    WorkflowPermission(flow_id=flow_id, owner_id=owner_id, grants=grants)
                )
            await session.commit()

    @staticmethod
    async def get(flow_id: str) -> dict[str, Any] | None:
        async with get_db_session() as session:
            result = await session.execute(
                select(WorkflowPermission).where(WorkflowPermission.flow_id == flow_id)
            )
            row = result.scalars().first()
            return row.to_dict() if row else None

    @staticmethod
    async def delete(flow_id: str) -> None:
        async with get_db_session() as session:
            await session.execute(
                delete(WorkflowPermission).where(WorkflowPermission.flow_id == flow_id)
            )
            await session.commit()

    @staticmethod
    async def list_all() -> list[dict[str, Any]]:
        """Return all permission records (used for store hydration)."""
        async with get_db_session() as session:
            result = await session.execute(select(WorkflowPermission))
            return [r.to_dict() for r in result.scalars().all()]


class AuditLogRepository:
    """Async repository for AuditLogEntry persistence (M-2)."""

    @staticmethod
    async def append(entry: dict[str, Any]) -> None:
        """Insert one audit log entry."""
        async with get_db_session() as session:
            session.add(
                AuditLogEntry(
                    id=entry["id"],
                    timestamp=entry["timestamp"],
                    actor=entry["actor"],
                    action=entry["action"],
                    resource_type=entry["resource_type"],
                    resource_id=entry["resource_id"],
                    detail=entry.get("detail", ""),
                )
            )
            await session.commit()

    @staticmethod
    async def purge_before(cutoff_timestamp: str) -> int:
        """Delete entries with timestamp < cutoff. Returns count deleted."""
        async with get_db_session() as session:
            result = await session.execute(
                delete(AuditLogEntry)
                .where(AuditLogEntry.timestamp < cutoff_timestamp)
                .returning(AuditLogEntry.id)
            )
            await session.commit()
            return result.rowcount

    @staticmethod
    async def list_all(max_entries: int = 50_000) -> list[dict[str, Any]]:
        """Return all audit log entries in chronological order (used for hydration)."""
        async with get_db_session() as session:
            result = await session.execute(
                select(AuditLogEntry)
                .order_by(AuditLogEntry.timestamp.asc())
                .limit(max_entries)
            )
            return [r.to_dict() for r in result.scalars().all()]
