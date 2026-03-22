"""
Marketplace router for SynApps Orchestrator.

Extracted from main.py (Step 3 of M-1 router decomposition).
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import math
import os
import re
import secrets
import time
import uuid
from typing import Any

import jwt
from fastapi import APIRouter, BackgroundTasks, Body, Depends, Form, Header, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sse_starlette.sse import EventSourceResponse

from apps.orchestrator.db import get_db_session
from apps.orchestrator.models import (
    SUPPORTED_IMAGE_PROVIDERS,
    SUPPORTED_LLM_PROVIDERS,
    SUPPORTED_MEMORY_BACKENDS,
    APIKeyCreateRequestModel,
    APIKeyCreateResponseModel,
    APIKeyResponseModel,
    AuthLoginRequestModel,
    AuthRefreshRequestModel,
    AuthRegisterRequestModel,
    AuthTokenResponseModel,
    CodeNodeConfigModel,
    FlowModel,
    ForEachNodeConfigModel,
    HTTPRequestNodeConfigModel,
    IfElseNodeConfigModel,
    ImageGenNodeConfigModel,
    ImageGenRequestModel,
    ImageGenResponseModel,
    ImageModelInfoModel,
    ImageProviderInfoModel,
    LLMMessageModel,
    LLMModelInfoModel,
    LLMNodeConfigModel,
    LLMProviderInfoModel,
    LLMRequestModel,
    LLMResponseModel,
    LLMStreamChunkModel,
    LLMUsageModel,
    MemoryNodeConfigModel,
    MemorySearchResultModel,
    MergeNodeConfigModel,
    TransformNodeConfigModel,
    UserProfileModel,
    WorkflowRunStatusModel,
    RefreshToken as AuthRefreshToken,
    User as AuthUser,
    UserAPIKey as AuthUserAPIKey,
)
from apps.orchestrator.repositories import FlowRepository, WorkflowRunRepository
from apps.orchestrator.stores import (
    ActivityFeedStore,
    AdminKeyRegistry,
    AlertEngine,
    AlertRuleStore,
    AuditLogStore,
    AuthorizationCodeStore,
    CollaborationActivityStore,
    ConnectorError,
    ConnectorHealthTracker,
    ConnectorStatus,
    ConsumerUsageTracker,
    CostTrackerStore,
    CreditLedger,
    DebugSession,
    DebugSessionStore,
    DeprecationRegistry,
    ErrorCategory,
    ExecutionDashboardStore,
    ExecutionLogStore,
    ExecutionQuotaStore,
    FailedRequestStore,
    FeaturedStore,
    FlowAccessLogStore,
    FlowAclStore,
    FlowAliasStore,
    FlowAllowedOriginsStore,
    FlowAnnotationStore,
    FlowApprovalStore,
    FlowArchiveStore,
    FlowAuditExportStore,
    FlowBookmarkStore,
    FlowCachingConfigStore,
    FlowChangelogStore,
    FlowCircuitBreakerStore,
    FlowCollaboratorRoleStore,
    FlowCollaboratorStore,
    FlowConcurrencyStore,
    FlowContactStore,
    FlowCostConfigStore,
    FlowCustomDomainStore,
    FlowCustomFieldStore,
    FlowDataClassificationStore,
    FlowDataRetentionStore,
    FlowDependencyStore,
    FlowDescriptionStore,
    FlowEditLockStore,
    FlowEnvironmentStore,
    FlowErrorAlertStore,
    FlowExecutionHookStore,
    FlowExecutionModeStore,
    FlowExpiryStore,
    FlowFavoriteStore,
    FlowFeatureFlagStore,
    FlowGeoRestrictionStore,
    FlowGroupStore,
    FlowInputMaskStore,
    FlowInputSchemaStore,
    FlowInputValidationStore,
    FlowIpAllowlistStore,
    FlowLabelStore,
    FlowMaintenanceWindowStore,
    FlowMetadataStore,
    FlowNotifPrefStore,
    FlowNotificationChannelStore,
    FlowObservabilityConfigStore,
    FlowOutputDestinationStore,
    FlowOutputSchemaStore,
    FlowOutputTransformStore,
    FlowPinStore,
    FlowPriorityStore,
    FlowRateLimitStore,
    FlowReactionStore,
    FlowResourceLimitStore,
    FlowRetryPolicyStore,
    FlowRunPresetStore,
    FlowRunRetentionStore,
    FlowScheduleStore,
    FlowShareStore,
    FlowSnapshotStore,
    FlowTagStore,
    FlowTimeoutStore,
    FlowTriggerConfigStore,
    FlowVersionLockStore,
    FlowVisibilityStore,
    FlowWatchStore,
    FlowWebhookSigningStore,
    FlowWebhookStore,
    IssueStore,
    MarketplaceRegistry,
    NodeCommentStore,
    NodeLockStore,
    NotificationStore,
    OAuthClientRegistry,
    ExecutionCostRecord,
    PluginManifest,
    PluginRegistry,
    PresenceStore,
    RatingStore,
    ReplayStore,
    ReplyStore,
    RetryPolicy,
    ReviewStore,
    RollbackAuditStore,
    SLAStore,
    SSEEventBus,
    SchedulerService,
    SubflowRegistry,
    TaskQueue,
    TemplateRegistry,
    TestSuiteStore,
    WebhookDebugStore,
    WebhookTriggerRegistry,
    WorkflowPermissionStore,
    WorkflowSecretStore,
    WorkflowTestStore,
    WorkflowVariableStore,
    WorkflowVersionStore,
    _FAILED_REQUEST_CAP,
    _SENSITIVE_HEADERS,
    _month_start_ts,
    _next_month_start_ts,
    activity_feed_store,
    admin_key_registry,
    alert_engine,
    alert_rule_store,
    audit_log_store,
    auth_code_store,
    collaboration_activity_store,
    connector_health,
    usage_tracker,
    cost_tracker_store,
    credit_ledger,
    debug_session_store,
    deprecation_registry,
    execution_dashboard_store,
    execution_log_store,
    execution_quota_store,
    failed_request_store,
    featured_store,
    flow_access_log_store,
    flow_acl_store,
    flow_alias_store,
    flow_allowed_origins_store,
    flow_annotation_store,
    flow_approval_store,
    flow_archive_store,
    flow_audit_export_store,
    flow_bookmark_store,
    flow_caching_config_store,
    flow_changelog_store,
    flow_circuit_breaker_store,
    flow_collaborator_role_store,
    flow_collaborator_store,
    flow_concurrency_store,
    flow_contact_store,
    flow_cost_config_store,
    flow_custom_domain_store,
    flow_custom_field_store,
    flow_data_classification_store,
    flow_data_retention_store,
    flow_dependency_store,
    flow_description_store,
    flow_edit_lock_store,
    flow_environment_store,
    flow_error_alert_store,
    flow_execution_hook_store,
    flow_execution_mode_store,
    flow_expiry_store,
    flow_favorite_store,
    flow_feature_flag_store,
    flow_geo_restriction_store,
    flow_group_store,
    flow_input_mask_store,
    flow_input_schema_store,
    flow_input_validation_store,
    flow_ip_allowlist_store,
    flow_label_store,
    flow_maintenance_window_store,
    flow_metadata_store,
    flow_notif_pref_store,
    flow_notification_channel_store,
    flow_observability_config_store,
    flow_output_destination_store,
    flow_output_schema_store,
    flow_output_transform_store,
    flow_pin_store,
    flow_priority_store,
    flow_rate_limit_store,
    flow_reaction_store,
    flow_resource_limit_store,
    flow_retry_policy_store,
    flow_run_preset_store,
    flow_run_retention_store,
    flow_schedule_store,
    flow_share_store,
    flow_snapshot_store,
    flow_tag_store,
    flow_timeout_store,
    flow_trigger_config_store,
    flow_version_lock_store,
    flow_visibility_store,
    flow_watch_store,
    flow_webhook_signing_store,
    flow_webhook_store,
    issue_store,
    marketplace_registry,
    node_comment_store,
    node_lock_store,
    notification_store,
    oauth_client_registry,
    plugin_registry,
    presence_store,
    rating_store,
    replay_store,
    reply_store,
    review_store,
    rollback_audit_store,
    sla_store,
    sse_event_bus,
    subflow_registry,
    task_queue,
    template_registry,
    test_suite_store,
    webhook_debug_store,
    webhook_trigger_registry,
    workflow_permission_store,
    workflow_secret_store,
    workflow_test_store,
    workflow_variable_store,
    workflow_version_store,
)
from apps.orchestrator.dependencies import (
    JWT_SECRET_KEY,
    JWT_ALGORITHM,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    REFRESH_TOKEN_EXPIRE_DAYS,
    PASSWORD_HASH_ITERATIONS,
    API_KEY_LOOKUP_PREFIX_LEN,
    ALLOW_ANONYMOUS_WHEN_NO_USERS,
    FERNET_CIPHER,
    get_authenticated_user,
    _utc_now,
    _hash_sha256,
    _encrypt_api_key,
    _decrypt_api_key,
    _hash_password,
    _verify_password,
    _create_access_token,
    _create_refresh_token,
    _issue_api_tokens,
    _decode_token,
    _normalize_key_header_value,
    _api_key_lookup_prefix,
    _user_to_principal,
    _store_refresh_token,
    _authenticate_user_by_jwt,
    _authenticate_user_by_api_key,
    _can_use_anonymous_bootstrap,
)
from apps.orchestrator.helpers import (
    TRACE_RESULTS_KEY,
    TRACE_SCHEMA_VERSION,
    MAX_DIFF_CHANGES,
    _PERMISSION_RANK,
    _OAUTH2_TOKEN_EXPIRE_SECONDS,
    paginate,
    _trace_value,
    _new_execution_trace,
    _finalize_execution_trace,
    _extract_trace_from_run,
    _flatten_for_diff,
    _build_json_diff,
    _node_result_index,
    _build_run_diff,
    _check_flow_permission,
    _diff_flow_snapshots,
    validate_template,
    _parse_semver,
    _bump_patch,
    _scrub_node_credentials,
    _load_yaml_template,
    _run_task_background,
    _seed_marketplace_listings,
    _share_record_response,
    _lock_response,
    _bulk_result,
    _expiry_response,
    _alias_response,
    _rate_limit_response,
    _fmt_entry,
    _fmt_preset,
    _fmt_ann,
    _fmt_dep,
    _fmt_bm,
    _run_flow_impl,
    _build_history_entry,
    _discover_yaml_templates,
    _get_last_run_for_flow_name,
    _create_oauth2_token,
    _estimate_node_cost,
    _diff_workflows,
    _score_node_suggestions,
    _match_description_to_node,
    _run_flow_debug,
    _run_flow_debug_inner,
    _is_admin,
    _match_output,
    _extract_final_output,
    _user_color,
)
from apps.orchestrator.request_models import (
    StrictRequestModel,
    FlowNodeRequest,
    FlowEdgeRequest,
    CreateFlowRequest,
    RunFlowRequest,
    FlowCloneRequest,
    FlowTagRequest,
    RerunFlowRequest,
    AISuggestRequest,
    WorkflowTestRequest,
    AuthRegisterRequestStrict,
    AuthLoginRequestStrict,
    AuthRefreshRequestStrict,
    APIKeyCreateRequestStrict,
    RollbackRequest,
    SYNAPPS_MASTER_KEY,
    require_master_key,
    _TIMEOUT_MIN,
    _TIMEOUT_MAX,
    _RETRY_MAX_RETRIES_MAX,
    _RETRY_DELAY_MAX,
    _RETRY_BACKOFF_MAX,
    _CONCURRENCY_MIN,
    _CONCURRENCY_MAX,
    _SEMVER_RE,
    _ALIAS_PATTERN,
    _ANN_COLOR_RE,
    _DEFAULT_ANN_COLOR,
    ValidateTemplateRequest,
    RegisterWebhookTriggerRequest,
    CreateScheduleRequest,
    UpdateScheduleRequest,
    ReplayDLQRequest,
    FlowUpdateRequest,
    RegisterWebhookRequest,
    TemplateImportRequest,
    PublishTemplateRequest,
    InstantiateTemplateRequest,
    RunAsyncRequest,
    PublishMarketplaceRequest,
    InstallMarketplaceRequest,
    AdminKeyCreateRequest,
    ManagedKeyCreateRequest,
    RotateKeyRequest,
    ImportFlowRequest,
    FlowLabelRequest,
    FlowShareRequest,
    FlowGroupRequest,
    SaveAsTemplateRequest,
    FlowLockRequest,
    FlowMetadataSetRequest,
    FlowPriorityRequest,
    FlowDescriptionRequest,
    BulkFlowRequest,
    BulkTagRequest,
    BulkMoveRequest,
    BulkPriorityRequest,
    FlowExpiryRequest,
    FlowAliasRequest,
    FlowRateLimitRequest,
    FlowChangelogAddRequest,
    FlowRunPresetRequest,
    FlowAnnotationCreateRequest,
    FlowAnnotationPatchRequest,
    FlowDependencyRequest,
    FlowBookmarkRequest,
    FlowSnapshotRequest,
    FlowReactionRequest,
    FlowScheduleUpsertRequest,
    FlowSchedulePatchRequest,
    FlowWebhookCreateRequest,
    FlowWebhookPatchRequest,
    FlowCustomFieldDefineRequest,
    FlowCustomFieldValueRequest,
    FlowCollaboratorRequest,
    FlowEnvironmentSetRequest,
    FlowNotifPrefRequest,
    FlowTimeoutRequest,
    FlowRetryPolicyRequest,
    FlowConcurrencyRequest,
    FlowInputSchemaRequest,
    FlowOutputSchemaRequest,
    FlowContactRequest,
    FlowCostConfigRequest,
    FlowVisibilityRequest,
    FlowVersionLockRequest,
    FlowApprovalRequestBody,
    FlowApprovalReviewBody,
    FlowTriggerConfigBody,
    FlowRunRetentionBody,
    FlowErrorAlertBody,
    FlowOutputDestinationBody,
    FlowResourceLimitBody,
    FlowAclGrantBody,
    FlowExecutionModeBody,
    FlowInputValidationBody,
    FlowCachingConfigBody,
    FlowCircuitBreakerBody,
    FlowObservabilityConfigBody,
    FlowMaintenanceWindowBody,
    FlowGeoRestrictionBody,
    FlowIpAllowlistBody,
    FlowDataClassificationBody,
    FlowNotificationChannelBody,
    FlowFeatureFlagBody,
    FlowExecutionHookBody,
    FlowCustomDomainBody,
    FlowWebhookSigningBody,
    FlowAuditExportBody,
    FlowCollaboratorRoleBody,
    FlowInputMaskBody,
    FlowOutputTransformBody,
    FlowDataRetentionBody,
    FlowAllowedOriginsBody,
    _FailedRequestSummary,
    _SetQuotaRequest,
    NodeCommentRequest,
    ShareWorkflowRequest,
    ImportWorkflowRequest,
    OAuthClientRegisterRequest,
    _BranchValidateRequest,
    SubflowValidateRequest,
    CostEstimateRequest,
    WorkflowDiffRequest,
    WorkflowVersionSaveRequest,
    SuggestNextNodeRequest,
    AutocompleteRequest,
    StartDebugRequest,
    UpdateBreakpointsRequest,
    RetryWebhookRequest,
    FeatureListingRequest,
    EstimateCostRequest,
    FlowEstimateCostRequest,
    TestCaseRequest,
    RunTestSuiteRequest,
    RateListingRequest,
    ReviewListingRequest,
    ReplyToReviewRequest,
    ReportIssueRequest,
    JoinPresenceRequest,
    HeartbeatRequest,
    AcquireNodeLockRequest,
    RegisterPluginRequest,
    PayoutRequest,
    SetSLAPolicyRequest,
    PublisherAnalyticsService,
    CostCalculator,
    MarketplaceSearchEngine,
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

