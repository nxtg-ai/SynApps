"""
Marketplace router for SynApps Orchestrator.

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
    _is_admin,
    _scrub_node_credentials,
    validate_template,
)
from apps.orchestrator.repositories import FlowRepository
from apps.orchestrator.request_models import (
    CostCalculator,
    EstimateCostRequest,
    FeatureListingRequest,
    InstallMarketplaceRequest,
    MarketplaceSearchEngine,
    PublisherAnalyticsService,
    PublishMarketplaceRequest,
    ValidateTemplateRequest,
)
from apps.orchestrator.stores import (
    CreditLedger,
    credit_ledger,
    featured_store,
    marketplace_registry,
    rating_store,
)

logger = logging.getLogger("orchestrator")


# Orchestrator and applet_registry are populated by main.py after all modules load.
# They start as None/empty and are set via _setup_router_globals() in main.py.
Orchestrator = None  # type: ignore[assignment]
applet_registry: dict = {}

# publisher_analytics_service is a module-level instance
publisher_analytics_service = PublisherAnalyticsService()
search_engine = MarketplaceSearchEngine()

router = APIRouter()


# ============================================================
# Marketplace Routes
# ============================================================

@router.post("/templates/validate", tags=["Dashboard"])
async def validate_template_endpoint(
    payload: ValidateTemplateRequest,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Dry-run validation of a template/flow definition without execution."""
    data = payload.model_dump()
    result = validate_template(data)
    return result


@router.post("/marketplace/publish", status_code=201, tags=["Marketplace"])
async def marketplace_publish(
    body: PublishMarketplaceRequest,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Publish an existing flow as a marketplace listing.

    Snapshots the flow's nodes and edges, scrubs credentials, and creates
    a new listing entry. Returns the listing with install_count=0.
    """
    flow = await FlowRepository.get_by_id(body.flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail=f"Flow '{body.flow_id}' not found")

    listing_data = {
        "name": body.name,
        "description": body.description,
        "category": body.category,
        "tags": body.tags,
        "author": body.author,
        "publisher_id": current_user["id"],
        "nodes": _scrub_node_credentials(flow.get("nodes", [])),
        "edges": flow.get("edges", []),
    }

    try:
        entry = marketplace_registry.publish(listing_data)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return entry


@router.get("/marketplace/search", tags=["Marketplace"])
async def marketplace_search(
    q: str | None = Query(None, description="Text search on name, description, and tags"),
    category: str | None = Query(None, description="Filter by category"),
    tags: str | None = Query(None, description="Comma-separated tags to filter by"),
    min_rating: float = Query(0.0, ge=0.0, description="Minimum average rating"),
    min_installs: int = Query(0, ge=0, description="Minimum install count"),
    sort_by: str = Query("relevance", description="Sort: relevance|installs|rating|newest"),
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    per_page: int = Query(20, ge=1, le=100, description="Results per page (max 100)"),
):
    """Search marketplace listings with optional filters and pagination."""
    tag_list: list[str] | None = None
    if tags:
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]

    all_listings = marketplace_registry.list_all()
    offset = (page - 1) * per_page

    result = search_engine.search(
        listings=all_listings,
        q=q or "",
        category=category or "",
        min_rating=min_rating,
        min_installs=min_installs,
        sort_by=sort_by,
        limit=per_page,
        offset=offset,
        tags=tag_list,
        rating_lookup=rating_store,
    )

    # Enrich each listing with avg_rating, rating_count, and is_featured
    enriched = []
    for item in result["items"]:
        lid = item.get("listing_id", item.get("id", ""))
        stats = rating_store.get_stats(lid)
        enriched.append(
            {
                **item,
                "avg_rating": stats["avg_rating"],
                "rating_count": stats["rating_count"],
                "is_featured": featured_store.is_featured(lid),
            }
        )
    return {
        "items": enriched,
        "total": result["total"],
        "page": page,
        "per_page": per_page,
        "query": result["query"],
        "filters_applied": result["filters_applied"],
    }


@router.get("/marketplace/featured", tags=["Marketplace"])
async def marketplace_featured(
    limit: int = Query(0, ge=0, description="Max items to return (0 = all)"),
):
    """Return admin-curated featured listings, enriched with listing metadata.

    Each returned item merges the full marketplace listing data with the
    featured metadata (blurb, featured_at, featured_by) and adds
    ``is_featured: true``.  Results are sorted by ``featured_at`` descending.
    """
    featured_entries = featured_store.list_featured()
    enriched: list[dict[str, Any]] = []
    for entry in featured_entries:
        listing = marketplace_registry.get(entry["listing_id"])
        if listing is None:
            continue
        enriched.append(
            {
                **listing,
                "blurb": entry["blurb"],
                "featured_at": entry["featured_at"],
                "featured_by": entry["featured_by"],
                "is_featured": True,
            }
        )
    if limit > 0:
        enriched = enriched[:limit]
    return {"items": enriched, "total": len(enriched)}


@router.post("/marketplace/install/{listing_id}", status_code=201, tags=["Marketplace"])
async def marketplace_install(
    listing_id: str,
    body: InstallMarketplaceRequest,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Install a marketplace listing into the user's workspace.

    Clones the listing's nodes and edges into a new flow, re-mapping all
    node IDs to avoid collisions. Increments the listing's install_count.
    """
    listing = marketplace_registry.get(listing_id)
    if not listing:
        raise HTTPException(status_code=404, detail=f"Listing '{listing_id}' not found")

    # Re-map node IDs to avoid collisions
    id_map: dict[str, str] = {}
    new_nodes = []
    for node in listing.get("nodes", []):
        old_id = node.get("id", str(uuid.uuid4()))
        new_node_id = str(uuid.uuid4())
        id_map[old_id] = new_node_id
        new_node = {**node, "id": new_node_id}

        # Apply connector overrides for this node
        if old_id in body.connector_overrides:
            overrides = body.connector_overrides[old_id]
            existing_data = new_node.get("data", {})
            if isinstance(existing_data, dict) and isinstance(overrides, dict):
                new_node["data"] = {**existing_data, **overrides}
            else:
                new_node["data"] = overrides

        new_nodes.append(new_node)

    # Re-map edge source/target references
    new_edges = []
    for edge in listing.get("edges", []):
        new_edges.append(
            {
                "id": str(uuid.uuid4()),
                "source": id_map.get(edge.get("source", ""), edge.get("source", "")),
                "target": id_map.get(edge.get("target", ""), edge.get("target", "")),
                "animated": edge.get("animated", False),
            }
        )

    flow_name = body.flow_name or listing.get("name", "Unnamed Flow")
    new_flow_id = str(uuid.uuid4())
    flow_data = {
        "id": new_flow_id,
        "name": flow_name,
        "nodes": new_nodes,
        "edges": new_edges,
    }

    await FlowRepository.save(flow_data)
    marketplace_registry.increment_install(listing_id)

    # Award credits to the listing publisher (N-47 revenue)
    publisher_id = listing.get("publisher_id")
    if publisher_id:
        credit_ledger.credit(
            publisher_id,
            listing_id,
            listing.get("name", ""),
            CreditLedger.CREDITS_PER_INSTALL,
        )

    return {
        "message": "Flow created from marketplace listing",
        "flow_id": new_flow_id,
        "listing_id": listing_id,
        "listing_name": listing.get("name"),
    }


@router.get("/marketplace/publisher/analytics", tags=["Marketplace"])
async def publisher_analytics(
    days: int = Query(30, ge=1, le=365, description="Growth trend window in days"),
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict[str, Any]:
    """Return aggregated analytics for the authenticated publisher."""
    pub_id = current_user["id"]
    return {
        "summary": publisher_analytics_service.summary(pub_id),
        "per_listing": publisher_analytics_service.per_listing(pub_id),
        "growth_trend": publisher_analytics_service.growth_trend(pub_id, days=days),
        "top_templates": publisher_analytics_service.top_templates(pub_id),
    }


@router.get("/marketplace/publisher/analytics/{listing_id}", tags=["Marketplace"])
async def publisher_listing_analytics(
    listing_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict[str, Any]:
    """Return detailed analytics for a single listing owned by the caller."""
    try:
        result = publisher_analytics_service.listing_detail(current_user["id"], listing_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=403, detail="Listing not owned by current user"
        ) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Listing not found")
    return result


@router.post("/marketplace/{listing_id}/feature", tags=["Marketplace"])
async def feature_listing(
    listing_id: str,
    body: FeatureListingRequest,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict[str, Any]:
    """Mark a marketplace listing as admin-curated featured (admin only)."""
    if not _is_admin(current_user):
        raise HTTPException(status_code=403, detail="Admin access required")
    listing = marketplace_registry.get(listing_id)
    if listing is None:
        raise HTTPException(status_code=404, detail=f"Listing '{listing_id}' not found")
    entry = featured_store.feature(listing_id, current_user["id"], body.blurb)
    return entry


@router.delete("/marketplace/{listing_id}/feature", status_code=204, tags=["Marketplace"])
async def unfeature_listing(
    listing_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> None:
    """Remove a marketplace listing from the featured list (admin only)."""
    if not _is_admin(current_user):
        raise HTTPException(status_code=403, detail="Admin access required")
    featured_store.unfeature(listing_id)
    return None


@router.get("/marketplace/autocomplete", tags=["Marketplace"])
async def marketplace_autocomplete(
    q: str = Query("", description="Prefix query for autocomplete suggestions"),
    limit: int = Query(8, ge=1, le=50, description="Max suggestions to return"),
):
    """Return autocomplete suggestions matching prefix of listing names or tags."""
    all_listings = marketplace_registry.list_all()
    suggestions = search_engine.autocomplete(listings=all_listings, q=q, limit=limit)
    return {"suggestions": suggestions}


@router.post("/flows/estimate-cost", tags=["Flows"])
async def estimate_cost_arbitrary(
    body: EstimateCostRequest,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Estimate execution cost for an arbitrary list of nodes (before flow is saved)."""
    return CostCalculator.estimate(body.nodes, body.foreach_iterations)

