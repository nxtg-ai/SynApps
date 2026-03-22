"""
Flow Config router for SynApps Orchestrator.

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
from datetime import UTC, datetime, timedelta
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
    _ALLOWED_REACTIONS,
    _COLLABORATOR_ROLES,
    _COST_CURRENCIES,
    _CUSTOM_FIELD_TYPES,
    _ENV_NAMES,
    _NOTIF_CHANNELS,
    _NOTIF_EVENTS,
    _VISIBILITY_LEVELS,
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
)

logger = logging.getLogger("orchestrator")


# Orchestrator and applet_registry are populated by main.py after all modules load.
# They start as None/empty and are set via _setup_router_globals() in main.py.
Orchestrator = None  # type: ignore[assignment]
applet_registry: dict = {}

# flow_version_registry is populated by main.py after module load
flow_version_registry = None  # type: ignore[assignment]

# _WEBHOOK_EVENTS is the frozenset of valid webhook event names
from apps.orchestrator.webhooks.manager import WEBHOOK_EVENTS as _WEBHOOK_EVENTS  # noqa: E402

router = APIRouter()


# ============================================================
# Flow Config Routes
# ============================================================

@router.get("/flows/{flow_id}/export", tags=["Flows"])
async def export_flow(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Export a flow as a downloadable JSON file."""
    flow = await FlowRepository.get_by_id(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")

    # Build a clean export payload (strip internal DB-only fields)
    export_data = {
        "synapps_version": "1.0.0",
        "name": flow["name"],
        "nodes": [
            {
                "id": n["id"],
                "type": n["type"],
                "position": n["position"],
                "data": n.get("data", {}),
            }
            for n in flow.get("nodes", [])
        ],
        "edges": [
            {
                "id": e["id"],
                "source": e["source"],
                "target": e["target"],
                "animated": e.get("animated", False),
            }
            for e in flow.get("edges", [])
        ],
    }

    safe_name = re.sub(r"[^a-zA-Z0-9_-]", "_", flow["name"])[:60]
    return JSONResponse(
        content=export_data,
        headers={
            "Content-Disposition": f'attachment; filename="{safe_name}.synapps.json"',
        },
    )


@router.get("/flows/{flow_id}/versions", tags=["Flows"])
async def list_flow_versions(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """List the version history for a flow (newest first).

    Each entry includes ``version_id``, ``version`` (sequential number), and
    ``snapshotted_at`` timestamp. Use ``GET /flows/{flow_id}/versions/{version_id}``
    to retrieve the full snapshot.
    """
    flow = await FlowRepository.get_by_id(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail=f"Flow '{flow_id}' not found")
    return {"items": flow_version_registry.list_versions(flow_id)}


@router.get("/flows/{flow_id}/versions/{version_id}", tags=["Flows"])
async def get_flow_version(
    flow_id: str,
    version_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Retrieve the full snapshot of a specific flow version."""
    entry = flow_version_registry.get_version(flow_id, version_id)
    if not entry:
        raise HTTPException(
            status_code=404,
            detail=f"Version '{version_id}' not found for flow '{flow_id}'",
        )
    return entry


@router.post("/flows/{flow_id}/rollback", status_code=200, tags=["Flows"])
async def rollback_flow(
    flow_id: str,
    version_id: str = Query(..., description="Version ID to roll back to."),
    body: RollbackRequest | None = None,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Roll back a flow to a previous version.

    Snapshots the current state before applying the rollback, so the rollback
    itself is also reversible.  Records an audit entry in ``rollback_audit_store``.
    """
    flow = await FlowRepository.get_by_id(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail=f"Flow '{flow_id}' not found")

    entry = flow_version_registry.get_version(flow_id, version_id)
    if not entry:
        raise HTTPException(
            status_code=404,
            detail=f"Version '{version_id}' not found for flow '{flow_id}'",
        )

    # Snapshot the current state so the rollback is itself reversible
    pre_rollback = flow_version_registry.snapshot(flow_id, flow)
    from_version_id = pre_rollback["version_id"]

    restored = await FlowRepository.save({**entry["snapshot"], "id": flow_id})

    reason = body.reason if body else ""
    user_id = current_user.get("id", current_user.get("email", "unknown"))
    audit_entry = rollback_audit_store.record(
        flow_id=flow_id,
        from_version_id=from_version_id,
        to_version_id=version_id,
        performed_by=user_id,
        reason=reason,
    )

    return {"flow": restored, "rolled_back_to": version_id, "audit_entry": audit_entry}


@router.get("/flows/{flow_id}/rollback/history", status_code=200, tags=["Flows"])
async def get_flow_rollback_history(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """List rollback audit entries for a specific flow, newest first."""
    flow = await FlowRepository.get_by_id(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail=f"Flow '{flow_id}' not found")
    return {"items": rollback_audit_store.list(flow_id=flow_id)}


@router.get("/rollback/history", status_code=200, tags=["Flows"])
async def get_all_rollback_history(
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """List all rollback audit entries (all flows), newest first."""
    return {"items": rollback_audit_store.list()}


@router.get("/flows/{flow_id}/diff", tags=["Flows"])
async def diff_flow_versions(
    flow_id: str,
    version_a: str = Query(..., description="First version ID (base)."),
    version_b: str = Query(..., description="Second version ID (compare)."),
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Compute a structural diff between two versions of a flow.

    Pass the string ``"current"`` as ``version_b`` to diff against the live flow.
    """
    flow = await FlowRepository.get_by_id(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail=f"Flow '{flow_id}' not found")

    if version_b == "current":
        snapshot_b = flow
    else:
        entry_b = flow_version_registry.get_version(flow_id, version_b)
        if not entry_b:
            raise HTTPException(status_code=404, detail=f"Version '{version_b}' not found")
        snapshot_b = entry_b["snapshot"]

    entry_a = flow_version_registry.get_version(flow_id, version_a)
    if not entry_a:
        raise HTTPException(status_code=404, detail=f"Version '{version_a}' not found")

    return _diff_flow_snapshots(entry_a["snapshot"], snapshot_b)


@router.post("/flows/import", status_code=201, tags=["Flows"])
async def import_flow(
    body: ImportFlowRequest,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Import a flow from a JSON export. Assigns a new ID to avoid collisions."""
    new_id = str(uuid.uuid4())

    # Re-map node and edge IDs to avoid collisions with existing flows
    id_map: dict[str, str] = {}
    new_nodes = []
    for node in body.nodes:
        old_id = node.get("id", str(uuid.uuid4()))
        new_node_id = str(uuid.uuid4())
        id_map[old_id] = new_node_id
        new_nodes.append(
            {
                **node,
                "id": new_node_id,
            }
        )

    new_edges = []
    for edge in body.edges:
        new_edges.append(
            {
                "id": str(uuid.uuid4()),
                "source": id_map.get(edge.get("source", ""), edge.get("source", "")),
                "target": id_map.get(edge.get("target", ""), edge.get("target", "")),
                "animated": edge.get("animated", False),
            }
        )

    flow_data = {
        "id": new_id,
        "name": body.name,
        "nodes": new_nodes,
        "edges": new_edges,
    }

    await FlowRepository.save(flow_data)
    return {"message": "Flow imported", "id": new_id}


@router.post("/flows/{flow_id}/clone", status_code=201, tags=["Flows"])
async def clone_flow(
    flow_id: str,
    body: FlowCloneRequest = Body(default_factory=FlowCloneRequest),
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Clone a flow — deep copy with new IDs for flow, nodes, and edges.

    Returns the new flow ID and name. The caller can use GET /flows/{new_id}
    to retrieve the full cloned flow.
    """
    original = await FlowRepository.get_by_id(flow_id)
    if not original:
        raise HTTPException(status_code=404, detail="Flow not found")

    # Build node ID remapping: old_node_id → new_node_id
    node_id_map: dict[str, str] = {
        n["id"]: str(uuid.uuid4()) for n in original.get("nodes", [])
    }

    new_nodes = [
        {**n, "id": node_id_map[n["id"]]}
        for n in original.get("nodes", [])
    ]

    new_edges = [
        {
            **e,
            "id": str(uuid.uuid4()),
            "source": node_id_map.get(e.get("source", ""), e.get("source", "")),
            "target": node_id_map.get(e.get("target", ""), e.get("target", "")),
        }
        for e in original.get("edges", [])
    ]

    new_id = str(uuid.uuid4())
    new_name = (body.name or f"Copy of {original['name']}").strip() or f"Copy of {original['name']}"

    clone_data: dict[str, Any] = {
        "id": new_id,
        "name": new_name,
        "nodes": new_nodes,
        "edges": new_edges,
    }

    await FlowRepository.save(clone_data)

    user_email = current_user.get("email", "")
    if user_email and user_email != "anonymous@local":
        workflow_permission_store.set_owner(new_id, user_email)

    audit_log_store.record(
        user_email or "anonymous",
        "workflow_created",
        "flow",
        new_id,
        detail=f"Flow '{new_name}' cloned from flow '{flow_id}'.",
    )

    return {
        "message": "Flow cloned",
        "id": new_id,
        "name": new_name,
        "node_count": len(new_nodes),
        "edge_count": len(new_edges),
        "cloned_from": flow_id,
    }


@router.post("/flows/{flow_id}/tags", status_code=201, tags=["Flows"])
async def add_flow_tag(
    flow_id: str,
    body: FlowTagRequest,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Add a tag to a flow. Idempotent — adding an existing tag is a no-op."""
    flow = await FlowRepository.get_by_id(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
    flow_tag_store.add(flow_id, body.tag)
    return {"flow_id": flow_id, "tags": flow_tag_store.get(flow_id)}


@router.get("/flows/{flow_id}/tags", tags=["Flows"])
async def get_flow_tags(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Return all tags for a flow."""
    flow = await FlowRepository.get_by_id(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
    return {"flow_id": flow_id, "tags": flow_tag_store.get(flow_id)}


@router.delete("/flows/{flow_id}/tags/{tag}", tags=["Flows"])
async def remove_flow_tag(
    flow_id: str,
    tag: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Remove a tag from a flow. Returns 404 if the flow or tag doesn't exist."""
    flow = await FlowRepository.get_by_id(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
    removed = flow_tag_store.remove(flow_id, tag)
    if not removed:
        raise HTTPException(status_code=404, detail="Tag not found")
    return {"flow_id": flow_id, "tags": flow_tag_store.get(flow_id)}


@router.post("/flows/{flow_id}/favorite", status_code=201, tags=["Flows"])
async def add_flow_favorite(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Mark a flow as a favorite for the current user. Idempotent."""
    flow = await FlowRepository.get_by_id(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
    user_email = current_user.get("email", "anonymous@local")
    flow_favorite_store.add(user_email, flow_id)
    return {"flow_id": flow_id, "favorited": True}


@router.delete("/flows/{flow_id}/favorite", tags=["Flows"])
async def remove_flow_favorite(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Remove a flow from the current user's favorites. Returns 404 if not favorited."""
    flow = await FlowRepository.get_by_id(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
    user_email = current_user.get("email", "anonymous@local")
    removed = flow_favorite_store.remove(user_email, flow_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Flow is not in favorites")
    return {"flow_id": flow_id, "favorited": False}


@router.post("/flows/{flow_id}/pin", status_code=201, tags=["Flows"])
async def pin_flow(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Pin a flow for the current user (top-of-list ordering).

    Returns 409 if the flow is already pinned.
    List pinned flows with GET /flows/pinned.
    """
    flow = await FlowRepository.get_by_id(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
    user_email = current_user.get("email", "anonymous@local")
    pinned = flow_pin_store.pin(user_email, flow_id)
    if not pinned:
        raise HTTPException(status_code=409, detail="Flow is already pinned")
    return {"flow_id": flow_id, "pinned": True}


@router.delete("/flows/{flow_id}/pin", tags=["Flows"])
async def unpin_flow(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Unpin a flow for the current user. Returns 404 if not pinned."""
    flow = await FlowRepository.get_by_id(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
    user_email = current_user.get("email", "anonymous@local")
    removed = flow_pin_store.unpin(user_email, flow_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Flow is not pinned")
    return {"flow_id": flow_id, "pinned": False}


@router.get("/flows/{flow_id}/label", tags=["Flows"])
async def get_flow_label(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Return the label for a flow. Returns null if no label is set."""
    flow = await FlowRepository.get_by_id(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
    label = flow_label_store.get(flow_id)
    return {"flow_id": flow_id, "label": label}


@router.put("/flows/{flow_id}/label", tags=["Flows"])
async def set_flow_label(
    flow_id: str,
    body: FlowLabelRequest,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Set or replace the label (color + optional icon) for a flow."""
    flow = await FlowRepository.get_by_id(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
    flow_label_store.set(flow_id, body.color, body.icon)
    return {"flow_id": flow_id, "label": flow_label_store.get(flow_id)}


@router.delete("/flows/{flow_id}/label", tags=["Flows"])
async def delete_flow_label(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Remove the label from a flow. Returns 404 if no label is set."""
    flow = await FlowRepository.get_by_id(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
    removed = flow_label_store.delete(flow_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Flow has no label")
    return {"flow_id": flow_id, "label": None}


@router.post("/flows/{flow_id}/share", status_code=201, tags=["Flows"])
async def create_share_link(
    flow_id: str,
    body: FlowShareRequest = FlowShareRequest(),
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Generate a short-lived read-only share token for a flow.

    The returned token can be used with GET /flows/shared/{token} to fetch the
    flow without authentication. Default TTL is 24 hours (max 7 days).
    """
    flow = await FlowRepository.get_by_id(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
    actor = current_user.get("email", "anonymous@local")
    record = flow_share_store.create(flow_id, created_by=actor, ttl=body.ttl)
    return _share_record_response(record)


@router.get("/flows/{flow_id}/shares", tags=["Flows"])
async def list_share_links(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """List all active (non-expired) share tokens for a flow."""
    flow = await FlowRepository.get_by_id(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
    tokens = flow_share_store.list_for_flow(flow_id)
    return {"flow_id": flow_id, "tokens": [_share_record_response(r) for r in tokens]}


@router.delete("/flows/{flow_id}/share/{token}", tags=["Flows"])
async def revoke_share_link(
    flow_id: str,
    token: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Revoke a specific share token. Returns 404 if the token does not exist."""
    flow = await FlowRepository.get_by_id(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
    revoked = flow_share_store.revoke(token)
    if not revoked:
        raise HTTPException(status_code=404, detail="Share token not found")
    return {"token": token, "revoked": True}


@router.get("/flows/{flow_id}/group", tags=["Flows"])
async def get_flow_group(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Return the group a flow belongs to. Returns null if ungrouped."""
    flow = await FlowRepository.get_by_id(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
    return {"flow_id": flow_id, "group": flow_group_store.get(flow_id)}


@router.put("/flows/{flow_id}/group", tags=["Flows"])
async def set_flow_group(
    flow_id: str,
    body: FlowGroupRequest,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Assign a flow to a group (creates the group if it doesn't exist).

    A flow can belong to at most one group; calling this replaces any
    existing assignment. Group names are lowercased and stripped.
    """
    flow = await FlowRepository.get_by_id(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
    flow_group_store.set(flow_id, body.group)
    return {"flow_id": flow_id, "group": flow_group_store.get(flow_id)}


@router.delete("/flows/{flow_id}/group", tags=["Flows"])
async def remove_flow_group(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Remove a flow from its group. Returns 404 if the flow is ungrouped."""
    flow = await FlowRepository.get_by_id(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
    removed = flow_group_store.remove(flow_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Flow is not in any group")
    return {"flow_id": flow_id, "group": None}


@router.post("/flows/{flow_id}/save-as-template", status_code=201, tags=["Flows"])
async def save_flow_as_template(
    flow_id: str,
    body: SaveAsTemplateRequest = SaveAsTemplateRequest(),
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Promote a live flow into the template registry.

    Creates a new versioned template entry. If a template with the same
    flow_id already exists in the registry, a new version is appended.
    The returned object is the template entry (id, version, semver, name, …).
    """
    flow = await FlowRepository.get_by_id(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")

    template_name = body.name.strip() or flow.get("name", "Untitled Template")
    actor = current_user.get("email", "anonymous@local")

    template_data: dict[str, Any] = {
        "id": flow_id,
        "name": template_name,
        "description": body.description,
        "tags": [t.lower().strip() for t in body.tags if t.strip()],
        "nodes": flow.get("nodes", []),
        "edges": flow.get("edges", []),
        "metadata": {"created_from_flow": flow_id, "author": actor},
    }
    if body.version:
        template_data["version"] = body.version

    try:
        entry = template_registry.import_template(template_data)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return entry


@router.get("/flows/{flow_id}/access-log", tags=["Flows"])
async def get_flow_access_log(
    flow_id: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Return the access log (read audit trail) for a flow.

    Entries are returned newest-first. Cap is 500 entries per flow.
    """
    flow = await FlowRepository.get_by_id(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
    entries = flow_access_log_store.get(flow_id, limit=limit, offset=offset)
    total = flow_access_log_store.count(flow_id)
    return {"flow_id": flow_id, "entries": entries, "total": total}


@router.get("/flows/{flow_id}/stats", tags=["Flows"])
async def get_flow_stats(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Return per-flow execution aggregate statistics.

    Aggregates all execution dashboard entries for the given flow.
    Returns total_runs, success_count, failure_count, active_count,
    avg_duration_ms, and last_run_at.
    """
    flow = await FlowRepository.get_by_id(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
    return execution_dashboard_store.stats_for_flow(flow_id)


@router.post("/flows/{flow_id}/watch", status_code=201, tags=["Flows"])
async def watch_flow(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Subscribe the authenticated user to this flow.

    Returns 201 on success, 409 if already watching.
    """
    flow = await FlowRepository.get_by_id(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
    user = current_user.get("email", "anonymous@local")
    added = flow_watch_store.watch(flow_id, user)
    if not added:
        raise HTTPException(status_code=409, detail="Already watching this flow")
    return {"flow_id": flow_id, "watching": True, "watcher": user}


@router.delete("/flows/{flow_id}/watch", tags=["Flows"])
async def unwatch_flow(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Unsubscribe the authenticated user from this flow.

    Returns 200 on success, 404 if not watching.
    """
    flow = await FlowRepository.get_by_id(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
    user = current_user.get("email", "anonymous@local")
    removed = flow_watch_store.unwatch(flow_id, user)
    if not removed:
        raise HTTPException(status_code=404, detail="Not watching this flow")
    return {"flow_id": flow_id, "watching": False, "watcher": user}


@router.get("/flows/{flow_id}/watchers", tags=["Flows"])
async def list_flow_watchers(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Return the list of users watching this flow."""
    flow = await FlowRepository.get_by_id(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
    watchers = flow_watch_store.watchers_for_flow(flow_id)
    return {"flow_id": flow_id, "watchers": watchers, "total": len(watchers)}


@router.get("/flows/{flow_id}/lock", tags=["Flows"])
async def get_flow_lock(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Return the current lock status of a flow."""
    flow = await FlowRepository.get_by_id(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
    return _lock_response(flow_id, flow_edit_lock_store.get(flow_id))


@router.post("/flows/{flow_id}/lock", status_code=201, tags=["Flows"])
async def lock_flow(
    flow_id: str,
    body: FlowLockRequest = FlowLockRequest(),
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Lock a flow to prevent edits. Returns 409 if already locked."""
    flow = await FlowRepository.get_by_id(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
    user = current_user.get("email", "anonymous@local")
    try:
        record = flow_edit_lock_store.lock(flow_id, user, body.reason)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _lock_response(flow_id, record)


@router.delete("/flows/{flow_id}/lock", tags=["Flows"])
async def unlock_flow(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Unlock a flow. Returns 404 if the flow is not locked."""
    flow = await FlowRepository.get_by_id(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
    removed = flow_edit_lock_store.unlock(flow_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Flow is not locked")
    return _lock_response(flow_id, None)


@router.get("/flows/{flow_id}/metadata", tags=["Flows"])
async def get_flow_metadata(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Return the metadata dict for a flow (empty dict if none set)."""
    flow = await FlowRepository.get_by_id(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
    return {"flow_id": flow_id, "metadata": flow_metadata_store.get(flow_id)}


@router.put("/flows/{flow_id}/metadata", tags=["Flows"])
async def set_flow_metadata(
    flow_id: str,
    body: FlowMetadataSetRequest,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Replace the entire metadata dict for a flow."""
    flow = await FlowRepository.get_by_id(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
    try:
        saved = flow_metadata_store.set(flow_id, body.metadata)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"flow_id": flow_id, "metadata": saved}


@router.patch("/flows/{flow_id}/metadata", tags=["Flows"])
async def patch_flow_metadata(
    flow_id: str,
    body: FlowMetadataSetRequest,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Merge new key-value pairs into the existing metadata (partial update)."""
    flow = await FlowRepository.get_by_id(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
    try:
        merged = flow_metadata_store.patch(flow_id, body.metadata)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"flow_id": flow_id, "metadata": merged}


@router.delete("/flows/{flow_id}/metadata/{key}", tags=["Flows"])
async def delete_flow_metadata_key(
    flow_id: str,
    key: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Remove a single metadata key from a flow. Returns 404 if key not present."""
    flow = await FlowRepository.get_by_id(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
    removed = flow_metadata_store.delete_key(flow_id, key)
    if not removed:
        raise HTTPException(status_code=404, detail=f"Metadata key '{key}' not found")
    return {"flow_id": flow_id, "deleted_key": key, "metadata": flow_metadata_store.get(flow_id)}


@router.get("/flows/{flow_id}/priority", tags=["Flows"])
async def get_flow_priority(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Return the priority of a flow (null if not set)."""
    flow = await FlowRepository.get_by_id(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
    return {"flow_id": flow_id, "priority": flow_priority_store.get(flow_id)}


@router.put("/flows/{flow_id}/priority", tags=["Flows"])
async def set_flow_priority(
    flow_id: str,
    body: FlowPriorityRequest,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Set the priority of a flow (critical/high/medium/low)."""
    flow = await FlowRepository.get_by_id(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
    priority = flow_priority_store.set(flow_id, body.priority)
    return {"flow_id": flow_id, "priority": priority}


@router.delete("/flows/{flow_id}/priority", tags=["Flows"])
async def clear_flow_priority(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Remove the priority from a flow. Returns 404 if no priority was set."""
    flow = await FlowRepository.get_by_id(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
    removed = flow_priority_store.clear(flow_id)
    if not removed:
        raise HTTPException(status_code=404, detail="No priority set for this flow")
    return {"flow_id": flow_id, "priority": None}


@router.get("/flows/{flow_id}/description", tags=["Flows"])
async def get_flow_description(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Return the description for a flow. Returns empty string if none set."""
    flow = await FlowRepository.get_by_id(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
    return {"flow_id": flow_id, "description": flow_description_store.get(flow_id)}


@router.put("/flows/{flow_id}/description", tags=["Flows"])
async def set_flow_description(
    flow_id: str,
    body: FlowDescriptionRequest,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Set or replace the description for a flow. Send empty string to clear."""
    flow = await FlowRepository.get_by_id(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
    flow_description_store.set(flow_id, body.description)
    return {"flow_id": flow_id, "description": flow_description_store.get(flow_id)}


@router.post("/flows/bulk/archive", tags=["Flows"])
async def bulk_archive_flows(
    body: BulkFlowRequest,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Archive multiple flows in one request.

    Returns per-flow success/failure breakdown. Already-archived flows are
    reported as failures with reason "already_archived".
    """
    succeeded: list[str] = []
    failed: list[dict[str, str]] = []
    for fid in body.flow_ids:
        flow = await FlowRepository.get_by_id(fid)
        if not flow:
            failed.append({"flow_id": fid, "reason": "not_found"})
            continue
        if flow_archive_store.is_archived(fid):
            failed.append({"flow_id": fid, "reason": "already_archived"})
            continue
        flow_archive_store.archive(fid)
        succeeded.append(fid)
    return _bulk_result(succeeded, failed, "archive")


@router.post("/flows/bulk/restore", tags=["Flows"])
async def bulk_restore_flows(
    body: BulkFlowRequest,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Restore multiple archived flows in one request.

    Not-archived flows are reported as failures with reason "not_archived".
    """
    succeeded: list[str] = []
    failed: list[dict[str, str]] = []
    for fid in body.flow_ids:
        flow = await FlowRepository.get_by_id(fid)
        if not flow:
            failed.append({"flow_id": fid, "reason": "not_found"})
            continue
        if not flow_archive_store.is_archived(fid):
            failed.append({"flow_id": fid, "reason": "not_archived"})
            continue
        flow_archive_store.restore(fid)
        succeeded.append(fid)
    return _bulk_result(succeeded, failed, "restore")


@router.post("/flows/bulk/delete", tags=["Flows"])
async def bulk_delete_flows(
    body: BulkFlowRequest,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Permanently delete multiple flows in one request."""
    succeeded: list[str] = []
    failed: list[dict[str, str]] = []
    for fid in body.flow_ids:
        flow = await FlowRepository.get_by_id(fid)
        if not flow:
            failed.append({"flow_id": fid, "reason": "not_found"})
            continue
        await FlowRepository.delete(fid)
        succeeded.append(fid)
    return _bulk_result(succeeded, failed, "delete")


@router.post("/flows/bulk/tag", tags=["Flows"])
async def bulk_tag_flows(
    body: BulkTagRequest,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Add a tag to multiple flows in one request."""
    succeeded: list[str] = []
    failed: list[dict[str, str]] = []
    for fid in body.flow_ids:
        flow = await FlowRepository.get_by_id(fid)
        if not flow:
            failed.append({"flow_id": fid, "reason": "not_found"})
            continue
        flow_tag_store.add(fid, body.tag)
        succeeded.append(fid)
    return _bulk_result(succeeded, failed, "tag")


@router.post("/flows/bulk/move", tags=["Flows"])
async def bulk_move_flows(
    body: BulkMoveRequest,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Move multiple flows to a group in one request.

    Group name is lowercased. Not-found flows are reported as failures.
    """
    succeeded: list[str] = []
    failed: list[dict[str, str]] = []
    group_norm = body.group.lower().strip()
    for fid in body.flow_ids:
        flow = await FlowRepository.get_by_id(fid)
        if not flow:
            failed.append({"flow_id": fid, "reason": "not_found"})
            continue
        flow_group_store.set(fid, group_norm)
        succeeded.append(fid)
    return _bulk_result(succeeded, failed, "move")


@router.post("/flows/bulk/priority", tags=["Flows"])
async def bulk_set_priority(
    body: BulkPriorityRequest,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Set the priority of multiple flows in one request."""
    succeeded: list[str] = []
    failed: list[dict[str, str]] = []
    for fid in body.flow_ids:
        flow = await FlowRepository.get_by_id(fid)
        if not flow:
            failed.append({"flow_id": fid, "reason": "not_found"})
            continue
        flow_priority_store.set(fid, body.priority)
        succeeded.append(fid)
    return _bulk_result(succeeded, failed, "priority")


@router.get("/flows/{flow_id}/expiry", tags=["Flows"])
async def get_flow_expiry(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Return the expiry configuration of a flow."""
    flow = await FlowRepository.get_by_id(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
    return _expiry_response(flow_id, flow_expiry_store.get(flow_id))


@router.put("/flows/{flow_id}/expiry", tags=["Flows"])
async def set_flow_expiry(
    flow_id: str,
    body: FlowExpiryRequest,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Set or replace the expiry for a flow.

    ``expires_at`` must be an ISO-8601 UTC datetime string.
    Returns 422 if the datetime cannot be parsed or is in the past.
    """
    flow = await FlowRepository.get_by_id(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
    try:
        dt = datetime.fromisoformat(body.expires_at.replace("Z", "+00:00"))
        ts = dt.timestamp()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid datetime: {exc}") from exc
    if ts <= time.time():
        raise HTTPException(status_code=422, detail="expires_at must be in the future")
    flow_expiry_store.set(flow_id, ts)
    return _expiry_response(flow_id, ts)


@router.delete("/flows/{flow_id}/expiry", tags=["Flows"])
async def clear_flow_expiry(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Remove the expiry from a flow. Returns 404 if no expiry was set."""
    flow = await FlowRepository.get_by_id(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
    removed = flow_expiry_store.clear(flow_id)
    if not removed:
        raise HTTPException(status_code=404, detail="No expiry set for this flow")
    return _expiry_response(flow_id, None)


@router.get("/flows/by-alias/{alias}", tags=["Flows"])
async def get_flow_by_alias(
    alias: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Look up a flow by its human-readable alias.

    Returns the full flow object (same shape as GET /flows/{id}).
    """
    flow_id = flow_alias_store.resolve(alias)
    if flow_id is None:
        raise HTTPException(status_code=404, detail="Alias not found")
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    return flow


@router.get("/flows/{flow_id}/alias", tags=["Flows"])
async def get_flow_alias(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Return the alias for *flow_id*, or ``null`` if none is set."""
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    return _alias_response(flow_id)


@router.put("/flows/{flow_id}/alias", tags=["Flows"])
async def set_flow_alias(
    flow_id: str,
    body: FlowAliasRequest,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Set or update the alias for *flow_id*.

    - Alias must be a lowercase slug (a-z, 0-9, hyphens), 2–63 chars.
    - Returns 409 if the alias is already owned by a different flow.
    """
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    try:
        flow_alias_store.set(flow_id, body.alias)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _alias_response(flow_id)


@router.delete("/flows/{flow_id}/alias", tags=["Flows"])
async def delete_flow_alias(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Remove the alias for *flow_id*.

    Returns 404 if no alias is currently set.
    """
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    removed = flow_alias_store.clear(flow_id)
    if not removed:
        raise HTTPException(status_code=404, detail="No alias set for this flow")
    return _alias_response(flow_id)


@router.get("/flows/{flow_id}/rate-limit", tags=["Flows"])
async def get_flow_rate_limit(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Return the rate-limit config for *flow_id*, or ``null`` fields if not set."""
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    return _rate_limit_response(flow_id)


@router.put("/flows/{flow_id}/rate-limit", tags=["Flows"])
async def set_flow_rate_limit(
    flow_id: str,
    body: FlowRateLimitRequest,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Set or replace the execution rate limit for *flow_id*.

    Once set, ``POST /flows/{id}/runs`` will return **429** when the limit is
    exceeded within the sliding window.
    """
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    flow_rate_limit_store.set(flow_id, body.max_runs, body.window_seconds)
    return _rate_limit_response(flow_id)


@router.delete("/flows/{flow_id}/rate-limit", tags=["Flows"])
async def delete_flow_rate_limit(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Remove the rate limit for *flow_id*.

    Returns 404 if no limit was configured.
    """
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    removed = flow_rate_limit_store.clear(flow_id)
    if not removed:
        raise HTTPException(status_code=404, detail="No rate limit set for this flow")
    return _rate_limit_response(flow_id)


@router.post("/flows/{flow_id}/changelog", status_code=201, tags=["Flows"])
async def add_changelog_entry(
    flow_id: str,
    body: FlowChangelogAddRequest,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Append a user-authored changelog entry to *flow_id*.

    Valid types: ``note``, ``fix``, ``improvement``, ``breaking``, ``deployment``.
    Returns 422 when the flow's changelog is full (500 entries).
    """
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    author = current_user.get("email", "anonymous@local")
    try:
        entry = flow_changelog_store.add(flow_id, author, body.message, body.type)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _fmt_entry(entry)


@router.get("/flows/{flow_id}/changelog", tags=["Flows"])
async def list_changelog_entries(
    flow_id: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """List changelog entries for *flow_id* (newest-first, paginated)."""
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    entries = flow_changelog_store.list(flow_id, limit=limit, offset=offset)
    return {
        "flow_id": flow_id,
        "total": flow_changelog_store.total(flow_id),
        "items": [_fmt_entry(e) for e in entries],
    }


@router.delete("/flows/{flow_id}/changelog/{entry_id}", tags=["Flows"])
async def delete_changelog_entry(
    flow_id: str,
    entry_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Delete a single changelog entry.

    Returns 404 if the flow or the entry does not exist.
    """
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    removed = flow_changelog_store.delete(flow_id, entry_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Changelog entry not found")
    return {"deleted": True, "entry_id": entry_id}


@router.post("/flows/{flow_id}/presets", status_code=201, tags=["Flows"])
async def create_run_preset(
    flow_id: str,
    body: FlowRunPresetRequest,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Save a named input preset for *flow_id*.

    Returns 422 if the flow's preset capacity (100) is reached.
    """
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    try:
        preset = flow_run_preset_store.add(flow_id, body.name, body.input, body.description)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _fmt_preset(preset)


@router.get("/flows/{flow_id}/presets", tags=["Flows"])
async def list_run_presets(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """List all named run presets for *flow_id*."""
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    presets = flow_run_preset_store.list(flow_id)
    return {"flow_id": flow_id, "items": [_fmt_preset(p) for p in presets]}


@router.get("/flows/{flow_id}/presets/{preset_id}", tags=["Flows"])
async def get_run_preset(
    flow_id: str,
    preset_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Return a single run preset by ID."""
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    preset = flow_run_preset_store.get(flow_id, preset_id)
    if preset is None:
        raise HTTPException(status_code=404, detail="Preset not found")
    return _fmt_preset(preset)


@router.delete("/flows/{flow_id}/presets/{preset_id}", tags=["Flows"])
async def delete_run_preset(
    flow_id: str,
    preset_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Delete a named run preset.

    Returns 404 if the flow or preset does not exist.
    """
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    removed = flow_run_preset_store.delete(flow_id, preset_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Preset not found")
    return {"deleted": True, "preset_id": preset_id}


@router.post("/flows/{flow_id}/annotations", status_code=201, tags=["Flows"])
async def create_annotation(
    flow_id: str,
    body: FlowAnnotationCreateRequest,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Add a sticky-note annotation to the flow canvas."""
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    author = current_user.get("email", "anonymous@local")
    try:
        ann = flow_annotation_store.add(flow_id, body.content, body.x, body.y, body.color, author)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _fmt_ann(ann)


@router.get("/flows/{flow_id}/annotations", tags=["Flows"])
async def list_annotations(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """List all annotations for *flow_id*."""
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    annotations = flow_annotation_store.list(flow_id)
    return {"flow_id": flow_id, "items": [_fmt_ann(a) for a in annotations]}


@router.patch("/flows/{flow_id}/annotations/{ann_id}", tags=["Flows"])
async def patch_annotation(
    flow_id: str,
    ann_id: str,
    body: FlowAnnotationPatchRequest,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Partially update an annotation (content, position, or color)."""
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    updated = flow_annotation_store.patch(flow_id, ann_id, updates)
    if updated is None:
        raise HTTPException(status_code=404, detail="Annotation not found")
    return _fmt_ann(updated)


@router.delete("/flows/{flow_id}/annotations/{ann_id}", tags=["Flows"])
async def delete_annotation(
    flow_id: str,
    ann_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Delete an annotation."""
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    removed = flow_annotation_store.delete(flow_id, ann_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Annotation not found")
    return {"deleted": True, "annotation_id": ann_id}


@router.post("/flows/{flow_id}/dependencies", status_code=201, tags=["Flows"])
async def add_flow_dependency(
    flow_id: str,
    body: FlowDependencyRequest,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Declare that *flow_id* depends on *to_flow_id*.

    - Returns 409 if the dependency already exists or would create a cycle.
    - Returns 422 if capacity (50) is reached or self-loop is attempted.
    """
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    dep_flow = await FlowRepository.get_by_id(body.to_flow_id)
    if dep_flow is None:
        raise HTTPException(status_code=404, detail="Dependency flow not found")
    try:
        edge = flow_dependency_store.add(flow_id, body.to_flow_id, body.label)
    except ValueError as exc:
        msg = str(exc)
        if "cycle" in msg.lower() or "already exists" in msg.lower():
            raise HTTPException(status_code=409, detail=msg) from exc
        raise HTTPException(status_code=422, detail=msg) from exc
    return _fmt_dep(edge)


@router.get("/flows/{flow_id}/dependencies", tags=["Flows"])
async def list_flow_dependencies(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """List flows that *flow_id* depends on (outgoing edges)."""
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    deps = flow_dependency_store.list_dependencies(flow_id)
    return {"flow_id": flow_id, "items": [_fmt_dep(e) for e in deps]}


@router.get("/flows/{flow_id}/dependents", tags=["Flows"])
async def list_flow_dependents(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """List flows that depend on *flow_id* (incoming edges / reverse lookup)."""
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    deps = flow_dependency_store.list_dependents(flow_id)
    return {"flow_id": flow_id, "items": [_fmt_dep(e) for e in deps]}


@router.delete("/flows/{flow_id}/dependencies/{dep_id}", tags=["Flows"])
async def delete_flow_dependency(
    flow_id: str,
    dep_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Remove a declared dependency edge.

    Returns 404 if the flow or the dependency edge does not exist.
    """
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    removed = flow_dependency_store.delete(flow_id, dep_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Dependency not found")
    return {"deleted": True, "dep_id": dep_id}


@router.post("/flows/{flow_id}/bookmarks", status_code=201, tags=["Flows"])
async def create_bookmark(
    flow_id: str,
    body: FlowBookmarkRequest,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Save a named canvas-viewport bookmark for the current user on *flow_id*.

    Returns 422 when the user's bookmark capacity (50) is reached for this flow.
    """
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    user = current_user.get("email", "anonymous@local")
    try:
        bm = flow_bookmark_store.add(flow_id, user, body.name, body.viewport)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _fmt_bm(bm)


@router.get("/flows/{flow_id}/bookmarks", tags=["Flows"])
async def list_bookmarks(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """List the current user's bookmarks for *flow_id*."""
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    user = current_user.get("email", "anonymous@local")
    bms = flow_bookmark_store.list(flow_id, user)
    return {"flow_id": flow_id, "user": user, "items": [_fmt_bm(b) for b in bms]}


@router.delete("/flows/{flow_id}/bookmarks/{bm_id}", tags=["Flows"])
async def delete_bookmark(
    flow_id: str,
    bm_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Delete a bookmark.  Returns 404 if not found for this user."""
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    user = current_user.get("email", "anonymous@local")
    removed = flow_bookmark_store.delete(flow_id, user, bm_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Bookmark not found")
    return {"deleted": True, "bookmark_id": bm_id}


@router.post("/flows/{flow_id}/snapshots", status_code=201, tags=["Flows"])
async def create_flow_snapshot(
    flow_id: str,
    body: FlowSnapshotRequest,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Capture a point-in-time snapshot of a flow's canvas state."""
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    author = current_user.get("email", "anonymous@local")
    snap = flow_snapshot_store.add(flow_id, body.label, body.nodes, body.edges, author)
    return snap


@router.get("/flows/{flow_id}/snapshots", tags=["Flows"])
async def list_flow_snapshots(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """List all snapshots for a flow, newest first."""
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    items = flow_snapshot_store.list(flow_id)
    return {"flow_id": flow_id, "total": len(items), "items": items}


@router.get("/flows/{flow_id}/snapshots/{snapshot_id}", tags=["Flows"])
async def get_flow_snapshot(
    flow_id: str,
    snapshot_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Retrieve a single snapshot including its full nodes/edges payload."""
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    snap = flow_snapshot_store.get(flow_id, snapshot_id)
    if snap is None:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    return snap


@router.delete("/flows/{flow_id}/snapshots/{snapshot_id}", tags=["Flows"])
async def delete_flow_snapshot(
    flow_id: str,
    snapshot_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Delete a snapshot permanently."""
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    removed = flow_snapshot_store.delete(flow_id, snapshot_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    return {"deleted": True, "snapshot_id": snapshot_id}


@router.post("/flows/{flow_id}/snapshots/{snapshot_id}/restore", tags=["Flows"])
async def restore_flow_snapshot(
    flow_id: str,
    snapshot_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Restore a flow to the state captured in a snapshot.

    Writes the snapshot's nodes and edges back to the flow record.
    Returns the snapshot metadata; the caller should refresh the canvas.
    """
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    snap = flow_snapshot_store.get(flow_id, snapshot_id)
    if snap is None:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    existing = await FlowRepository.get_by_id(flow_id)
    flow_data: dict[str, Any] = {
        "id": flow_id,
        "name": existing.get("name", "Unnamed Flow") if existing else "Unnamed Flow",
        "nodes": snap["nodes"],
        "edges": snap["edges"],
    }
    await FlowRepository.save(flow_data)
    return {"restored": True, "snapshot_id": snapshot_id, "label": snap["label"]}


@router.post("/flows/{flow_id}/reactions", status_code=201, tags=["Flows"])
async def add_flow_reaction(
    flow_id: str,
    body: FlowReactionRequest,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Add an emoji reaction to a flow.  Allowed emojis: 👍 👎 ❤️ 🔥 🎉 🚀 ⚠️ ✅ ❌ 🤔"""
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    user = current_user.get("email", "anonymous@local")
    try:
        flow_reaction_store.add(flow_id, body.emoji, user)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"flow_id": flow_id, "emoji": body.emoji, "user": user}


@router.delete("/flows/{flow_id}/reactions/{emoji}", tags=["Flows"])
async def remove_flow_reaction(
    flow_id: str,
    emoji: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Remove the current user's reaction of the given emoji type."""
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    user = current_user.get("email", "anonymous@local")
    try:
        removed = flow_reaction_store.remove(flow_id, emoji, user)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not removed:
        raise HTTPException(status_code=404, detail="Reaction not found")
    return {"deleted": True, "emoji": emoji}


@router.get("/flows/{flow_id}/reactions", tags=["Flows"])
async def get_flow_reactions(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Get aggregate reaction counts plus the current user's reactions."""
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    user = current_user.get("email", "anonymous@local")
    summary = flow_reaction_store.summary(flow_id)
    mine = flow_reaction_store.user_reactions(flow_id, user)
    return {
        "flow_id": flow_id,
        "reactions": summary,
        "user_reactions": mine,
        "allowed": sorted(_ALLOWED_REACTIONS),
    }


@router.put("/flows/{flow_id}/schedule", tags=["Flows"])
async def set_flow_schedule(
    flow_id: str,
    body: FlowScheduleUpsertRequest,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Create or replace the cron schedule for a flow."""
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    try:
        schedule = flow_schedule_store.set(flow_id, body.cron, body.enabled, body.label)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return schedule


@router.get("/flows/{flow_id}/schedule", tags=["Flows"])
async def get_flow_schedule(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Get the current schedule for a flow.  Returns 404 if none set."""
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    schedule = flow_schedule_store.get(flow_id)
    if schedule is None:
        raise HTTPException(status_code=404, detail="No schedule set for this flow")
    return schedule


@router.patch("/flows/{flow_id}/schedule", tags=["Flows"])
async def patch_flow_schedule(
    flow_id: str,
    body: FlowSchedulePatchRequest,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Partially update a flow's schedule (enabled flag, cron, or label)."""
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    updates: dict[str, Any] = {k: v for k, v in body.model_dump().items() if v is not None}
    try:
        updated = flow_schedule_store.patch(flow_id, updates)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if updated is None:
        raise HTTPException(status_code=404, detail="No schedule set for this flow")
    return updated


@router.delete("/flows/{flow_id}/schedule", tags=["Flows"])
async def delete_flow_schedule(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Remove the cron schedule from a flow."""
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    removed = flow_schedule_store.clear(flow_id)
    if not removed:
        raise HTTPException(status_code=404, detail="No schedule set for this flow")
    return {"deleted": True}


@router.post("/flows/{flow_id}/webhooks", status_code=201, tags=["Flows"])
async def create_flow_webhook(
    flow_id: str,
    body: FlowWebhookCreateRequest,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Register an outbound webhook for flow events."""
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    try:
        hook = flow_webhook_store.add(flow_id, body.url, body.events, body.secret, body.label)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return hook


@router.get("/flows/{flow_id}/webhooks", tags=["Flows"])
async def list_flow_webhooks(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """List all outbound webhooks registered for a flow."""
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    items = flow_webhook_store.list(flow_id)
    return {
        "flow_id": flow_id,
        "total": len(items),
        "items": items,
        "allowed_events": sorted(_WEBHOOK_EVENTS),
    }


@router.get("/flows/{flow_id}/webhooks/{hook_id}", tags=["Flows"])
async def get_flow_webhook(
    flow_id: str,
    hook_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Retrieve a single webhook by ID."""
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    hook = flow_webhook_store.get(flow_id, hook_id)
    if hook is None:
        raise HTTPException(status_code=404, detail="Webhook not found")
    return hook


@router.patch("/flows/{flow_id}/webhooks/{hook_id}", tags=["Flows"])
async def patch_flow_webhook(
    flow_id: str,
    hook_id: str,
    body: FlowWebhookPatchRequest,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Partially update a webhook (url, events, enabled, label, secret)."""
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    try:
        updated = flow_webhook_store.patch(flow_id, hook_id, updates)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if updated is None:
        raise HTTPException(status_code=404, detail="Webhook not found")
    return updated


@router.delete("/flows/{flow_id}/webhooks/{hook_id}", tags=["Flows"])
async def delete_flow_webhook(
    flow_id: str,
    hook_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Delete an outbound webhook."""
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    removed = flow_webhook_store.delete(flow_id, hook_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Webhook not found")
    return {"deleted": True, "webhook_id": hook_id}


@router.post("/flows/{flow_id}/custom-fields", status_code=201, tags=["Flows"])
async def define_flow_custom_field(
    flow_id: str,
    body: FlowCustomFieldDefineRequest,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Define a typed custom field schema for a flow."""
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    try:
        field = flow_custom_field_store.define(flow_id, body.name, body.type)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return field


@router.get("/flows/{flow_id}/custom-fields", tags=["Flows"])
async def list_flow_custom_fields(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """List all custom field schemas and their current values for a flow."""
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    fields = flow_custom_field_store.get_all(flow_id)
    return {
        "flow_id": flow_id,
        "total": len(fields),
        "fields": fields,
        "allowed_types": sorted(_CUSTOM_FIELD_TYPES),
    }


@router.put("/flows/{flow_id}/custom-fields/{name}", tags=["Flows"])
async def set_flow_custom_field_value(
    flow_id: str,
    name: str,
    body: FlowCustomFieldValueRequest,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Set the value of a custom field (field must already be defined)."""
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    try:
        result = flow_custom_field_store.set_value(flow_id, name, body.value)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return result


@router.get("/flows/{flow_id}/custom-fields/{name}", tags=["Flows"])
async def get_flow_custom_field(
    flow_id: str,
    name: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Get a single custom field and its current value."""
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    field = flow_custom_field_store.get_field(flow_id, name)
    if field is None:
        raise HTTPException(status_code=404, detail="Custom field not defined")
    return field


@router.delete("/flows/{flow_id}/custom-fields/{name}", tags=["Flows"])
async def delete_flow_custom_field(
    flow_id: str,
    name: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Remove a custom field schema and its stored value."""
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    removed = flow_custom_field_store.delete_field(flow_id, name)
    if not removed:
        raise HTTPException(status_code=404, detail="Custom field not defined")
    return {"deleted": True, "name": name}


@router.put("/flows/{flow_id}/collaborators/{user}", tags=["Flows"])
async def set_flow_collaborator(
    flow_id: str,
    user: str,
    body: FlowCollaboratorRequest,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Add or update a collaborator's role on a flow."""
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    try:
        result = flow_collaborator_store.add(flow_id, user, body.role)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return result


@router.get("/flows/{flow_id}/collaborators", tags=["Flows"])
async def list_flow_collaborators(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """List all collaborators and their roles for a flow."""
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    items = flow_collaborator_store.list(flow_id)
    return {
        "flow_id": flow_id,
        "total": len(items),
        "collaborators": items,
        "allowed_roles": sorted(_COLLABORATOR_ROLES),
    }


@router.get("/flows/{flow_id}/collaborators/{user}", tags=["Flows"])
async def get_flow_collaborator(
    flow_id: str,
    user: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Get a specific collaborator's role."""
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    collab = flow_collaborator_store.get(flow_id, user)
    if collab is None:
        raise HTTPException(status_code=404, detail="Collaborator not found")
    return collab


@router.delete("/flows/{flow_id}/collaborators/{user}", tags=["Flows"])
async def remove_flow_collaborator(
    flow_id: str,
    user: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Remove a collaborator from a flow."""
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    removed = flow_collaborator_store.remove(flow_id, user)
    if not removed:
        raise HTTPException(status_code=404, detail="Collaborator not found")
    return {"deleted": True, "user": user}


@router.put("/flows/{flow_id}/environments/{env_name}", tags=["Flows"])
async def set_flow_environment(
    flow_id: str,
    env_name: str,
    body: FlowEnvironmentSetRequest,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Create or replace a named environment config for a flow."""
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    try:
        result = flow_environment_store.set(flow_id, env_name, body.config)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return result


@router.get("/flows/{flow_id}/environments", tags=["Flows"])
async def list_flow_environments(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """List all environments configured for a flow."""
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    envs = flow_environment_store.list(flow_id)
    return {
        "flow_id": flow_id,
        "total": len(envs),
        "environments": envs,
        "allowed_names": sorted(_ENV_NAMES),
    }


@router.get("/flows/{flow_id}/environments/{env_name}", tags=["Flows"])
async def get_flow_environment(
    flow_id: str,
    env_name: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Get a specific environment config."""
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    env = flow_environment_store.get(flow_id, env_name)
    if env is None:
        raise HTTPException(status_code=404, detail="Environment not configured")
    return env


@router.post("/flows/{flow_id}/environments/{env_name}/activate", tags=["Flows"])
async def activate_flow_environment(
    flow_id: str,
    env_name: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Set an environment as the active one (deactivates all others)."""
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    result = flow_environment_store.activate(flow_id, env_name)
    if result is None:
        raise HTTPException(status_code=404, detail="Environment not configured")
    return result


@router.delete("/flows/{flow_id}/environments/{env_name}", tags=["Flows"])
async def delete_flow_environment(
    flow_id: str,
    env_name: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Remove an environment config."""
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    if env_name not in _ENV_NAMES:
        raise HTTPException(status_code=422, detail=f"Invalid environment name: {env_name!r}")
    removed = flow_environment_store.delete(flow_id, env_name)
    if not removed:
        raise HTTPException(status_code=404, detail="Environment not configured")
    return {"deleted": True, "env_name": env_name}


@router.put("/flows/{flow_id}/notification-prefs", tags=["Flows"])
async def set_flow_notif_prefs(
    flow_id: str,
    body: FlowNotifPrefRequest,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    try:
        prefs = flow_notif_pref_store.set(
            flow_id, current_user["email"], body.events, body.channels
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        **prefs,
        "allowed_events": sorted(_NOTIF_EVENTS),
        "allowed_channels": sorted(_NOTIF_CHANNELS),
    }


@router.get("/flows/{flow_id}/notification-prefs", tags=["Flows"])
async def get_flow_notif_prefs(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    prefs = flow_notif_pref_store.get(flow_id, current_user["email"])
    if prefs is None:
        raise HTTPException(status_code=404, detail="No notification preferences set")
    return {
        **prefs,
        "allowed_events": sorted(_NOTIF_EVENTS),
        "allowed_channels": sorted(_NOTIF_CHANNELS),
    }


@router.delete("/flows/{flow_id}/notification-prefs", tags=["Flows"])
async def delete_flow_notif_prefs(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    removed = flow_notif_pref_store.delete(flow_id, current_user["email"])
    if not removed:
        raise HTTPException(status_code=404, detail="No notification preferences set")
    return {"deleted": True, "flow_id": flow_id}


@router.put("/flows/{flow_id}/timeout", tags=["Flows"])
async def set_flow_timeout(
    flow_id: str,
    body: FlowTimeoutRequest,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    try:
        result = flow_timeout_store.set(flow_id, body.timeout_seconds)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return result


@router.get("/flows/{flow_id}/timeout", tags=["Flows"])
async def get_flow_timeout(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    cfg = flow_timeout_store.get(flow_id)
    if cfg is None:
        raise HTTPException(status_code=404, detail="No timeout configured")
    return cfg


@router.delete("/flows/{flow_id}/timeout", tags=["Flows"])
async def delete_flow_timeout(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    removed = flow_timeout_store.delete(flow_id)
    if not removed:
        raise HTTPException(status_code=404, detail="No timeout configured")
    return {"deleted": True, "flow_id": flow_id}


@router.put("/flows/{flow_id}/retry-policy", tags=["Flows"])
async def set_flow_retry_policy(
    flow_id: str,
    body: FlowRetryPolicyRequest,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    try:
        result = flow_retry_policy_store.set(
            flow_id, body.max_retries, body.retry_delay_s, body.backoff_multiplier
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return result


@router.get("/flows/{flow_id}/retry-policy", tags=["Flows"])
async def get_flow_retry_policy(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    policy = flow_retry_policy_store.get(flow_id)
    if policy is None:
        raise HTTPException(status_code=404, detail="No retry policy configured")
    return policy


@router.delete("/flows/{flow_id}/retry-policy", tags=["Flows"])
async def delete_flow_retry_policy(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    removed = flow_retry_policy_store.delete(flow_id)
    if not removed:
        raise HTTPException(status_code=404, detail="No retry policy configured")
    return {"deleted": True, "flow_id": flow_id}


@router.put("/flows/{flow_id}/concurrency", tags=["Flows"])
async def set_flow_concurrency(
    flow_id: str,
    body: FlowConcurrencyRequest,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    try:
        result = flow_concurrency_store.set(flow_id, body.max_concurrent)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return result


@router.get("/flows/{flow_id}/concurrency", tags=["Flows"])
async def get_flow_concurrency(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    cfg = flow_concurrency_store.get(flow_id)
    if cfg is None:
        raise HTTPException(status_code=404, detail="No concurrency limit configured")
    return cfg


@router.delete("/flows/{flow_id}/concurrency", tags=["Flows"])
async def delete_flow_concurrency(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    removed = flow_concurrency_store.delete(flow_id)
    if not removed:
        raise HTTPException(status_code=404, detail="No concurrency limit configured")
    return {"deleted": True, "flow_id": flow_id}


@router.put("/flows/{flow_id}/input-schema", tags=["Flows"])
async def set_flow_input_schema(
    flow_id: str,
    body: FlowInputSchemaRequest,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    try:
        result = flow_input_schema_store.set(flow_id, body.schema_)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return result


@router.get("/flows/{flow_id}/input-schema", tags=["Flows"])
async def get_flow_input_schema(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    entry = flow_input_schema_store.get(flow_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="No input schema defined")
    return entry


@router.delete("/flows/{flow_id}/input-schema", tags=["Flows"])
async def delete_flow_input_schema(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    removed = flow_input_schema_store.delete(flow_id)
    if not removed:
        raise HTTPException(status_code=404, detail="No input schema defined")
    return {"deleted": True, "flow_id": flow_id}


@router.put("/flows/{flow_id}/output-schema", tags=["Flows"])
async def set_flow_output_schema(
    flow_id: str,
    body: FlowOutputSchemaRequest,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    try:
        result = flow_output_schema_store.set(flow_id, body.schema_)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return result


@router.get("/flows/{flow_id}/output-schema", tags=["Flows"])
async def get_flow_output_schema(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    entry = flow_output_schema_store.get(flow_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="No output schema defined")
    return entry


@router.delete("/flows/{flow_id}/output-schema", tags=["Flows"])
async def delete_flow_output_schema(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    removed = flow_output_schema_store.delete(flow_id)
    if not removed:
        raise HTTPException(status_code=404, detail="No output schema defined")
    return {"deleted": True, "flow_id": flow_id}


@router.put("/flows/{flow_id}/contact", tags=["Flows"])
async def set_flow_contact(
    flow_id: str,
    body: FlowContactRequest,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    return flow_contact_store.set(
        flow_id, body.name, body.email, body.slack_handle, body.team
    )


@router.get("/flows/{flow_id}/contact", tags=["Flows"])
async def get_flow_contact(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    contact = flow_contact_store.get(flow_id)
    if contact is None:
        raise HTTPException(status_code=404, detail="No contact info set")
    return contact


@router.delete("/flows/{flow_id}/contact", tags=["Flows"])
async def delete_flow_contact(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    removed = flow_contact_store.delete(flow_id)
    if not removed:
        raise HTTPException(status_code=404, detail="No contact info set")
    return {"deleted": True, "flow_id": flow_id}


@router.put("/flows/{flow_id}/cost-config", tags=["Flows"])
async def set_flow_cost_config(
    flow_id: str,
    body: FlowCostConfigRequest,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    try:
        result = flow_cost_config_store.set(
            flow_id, body.cost_per_run, body.currency, body.billing_note
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {**result, "allowed_currencies": sorted(_COST_CURRENCIES)}


@router.get("/flows/{flow_id}/cost-config", tags=["Flows"])
async def get_flow_cost_config(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    cfg = flow_cost_config_store.get(flow_id)
    if cfg is None:
        raise HTTPException(status_code=404, detail="No cost config set")
    return {**cfg, "allowed_currencies": sorted(_COST_CURRENCIES)}


@router.delete("/flows/{flow_id}/cost-config", tags=["Flows"])
async def delete_flow_cost_config(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    removed = flow_cost_config_store.delete(flow_id)
    if not removed:
        raise HTTPException(status_code=404, detail="No cost config set")
    return {"deleted": True, "flow_id": flow_id}


@router.put("/flows/{flow_id}/visibility", tags=["Flows"])
async def set_flow_visibility(
    flow_id: str,
    body: FlowVisibilityRequest,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    try:
        result = flow_visibility_store.set(flow_id, body.visibility)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {**result, "allowed_levels": sorted(_VISIBILITY_LEVELS)}


@router.get("/flows/{flow_id}/visibility", tags=["Flows"])
async def get_flow_visibility(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    entry = flow_visibility_store.get(flow_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="No visibility set")
    return {**entry, "allowed_levels": sorted(_VISIBILITY_LEVELS)}


@router.delete("/flows/{flow_id}/visibility", tags=["Flows"])
async def delete_flow_visibility(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    removed = flow_visibility_store.delete(flow_id)
    if not removed:
        raise HTTPException(status_code=404, detail="No visibility set")
    return {"deleted": True, "flow_id": flow_id}


@router.post("/flows/{flow_id}/version-lock", tags=["Flows"])
async def lock_flow_version(
    flow_id: str,
    body: FlowVersionLockRequest,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    try:
        result = flow_version_lock_store.lock(
            flow_id, body.locked_version, body.reason, current_user["email"]
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return result


@router.get("/flows/{flow_id}/version-lock", tags=["Flows"])
async def get_flow_version_lock(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    entry = flow_version_lock_store.get(flow_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Flow is not version-locked")
    return entry


@router.delete("/flows/{flow_id}/version-lock", tags=["Flows"])
async def unlock_flow_version(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    removed = flow_version_lock_store.unlock(flow_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Flow is not version-locked")
    return {"deleted": True, "flow_id": flow_id}


@router.post("/flows/{flow_id}/approval/request", tags=["Flows"])
async def request_flow_approval(
    flow_id: str,
    body: FlowApprovalRequestBody,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    try:
        record = flow_approval_store.request(flow_id, current_user["email"], body.note)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return record


@router.post("/flows/{flow_id}/approval/approve", tags=["Flows"])
async def approve_flow(
    flow_id: str,
    body: FlowApprovalReviewBody,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    record = flow_approval_store.approve(flow_id, current_user["email"], body.comment)
    if record is None:
        raise HTTPException(status_code=404, detail="No pending approval for this flow")
    return record


@router.post("/flows/{flow_id}/approval/reject", tags=["Flows"])
async def reject_flow(
    flow_id: str,
    body: FlowApprovalReviewBody,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    record = flow_approval_store.reject(flow_id, current_user["email"], body.comment)
    if record is None:
        raise HTTPException(status_code=404, detail="No pending approval for this flow")
    return record


@router.get("/flows/{flow_id}/approval", tags=["Flows"])
async def get_flow_approval(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    record = flow_approval_store.get(flow_id)
    if record is None:
        raise HTTPException(status_code=404, detail="No approval record for this flow")
    return record


@router.delete("/flows/{flow_id}/approval", tags=["Flows"])
async def delete_flow_approval(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    deleted = flow_approval_store.clear(flow_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="No approval record for this flow")
    return {"deleted": True, "flow_id": flow_id}


@router.put("/flows/{flow_id}/trigger-config", tags=["Flows"])
async def set_flow_trigger_config(
    flow_id: str,
    body: FlowTriggerConfigBody,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    try:
        record = flow_trigger_config_store.set(flow_id, body.trigger_type, body.config)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return record


@router.get("/flows/{flow_id}/trigger-config", tags=["Flows"])
async def get_flow_trigger_config(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    record = flow_trigger_config_store.get(flow_id)
    if record is None:
        raise HTTPException(status_code=404, detail="No trigger config for this flow")
    return record


@router.delete("/flows/{flow_id}/trigger-config", tags=["Flows"])
async def delete_flow_trigger_config(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    deleted = flow_trigger_config_store.delete(flow_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="No trigger config for this flow")
    return {"deleted": True, "flow_id": flow_id}


@router.put("/flows/{flow_id}/run-retention", tags=["Flows"])
async def set_flow_run_retention(
    flow_id: str,
    body: FlowRunRetentionBody,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    try:
        record = flow_run_retention_store.set(flow_id, body.retain_days, body.max_runs)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return record


@router.get("/flows/{flow_id}/run-retention", tags=["Flows"])
async def get_flow_run_retention(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    record = flow_run_retention_store.get(flow_id)
    if record is None:
        raise HTTPException(status_code=404, detail="No retention policy for this flow")
    return record


@router.delete("/flows/{flow_id}/run-retention", tags=["Flows"])
async def delete_flow_run_retention(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    deleted = flow_run_retention_store.delete(flow_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="No retention policy for this flow")
    return {"deleted": True, "flow_id": flow_id}


@router.put("/flows/{flow_id}/error-alerts", tags=["Flows"])
async def set_flow_error_alerts(
    flow_id: str,
    body: FlowErrorAlertBody,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    try:
        record = flow_error_alert_store.set(flow_id, body.emails, body.slack_channels)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return record


@router.get("/flows/{flow_id}/error-alerts", tags=["Flows"])
async def get_flow_error_alerts(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    record = flow_error_alert_store.get(flow_id)
    if record is None:
        raise HTTPException(status_code=404, detail="No error alert config for this flow")
    return record


@router.delete("/flows/{flow_id}/error-alerts", tags=["Flows"])
async def delete_flow_error_alerts(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    deleted = flow_error_alert_store.delete(flow_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="No error alert config for this flow")
    return {"deleted": True, "flow_id": flow_id}


@router.put("/flows/{flow_id}/output-destination", tags=["Flows"])
async def set_flow_output_destination(
    flow_id: str,
    body: FlowOutputDestinationBody,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    try:
        record = flow_output_destination_store.set(flow_id, body.dest_type, body.config)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return record


@router.get("/flows/{flow_id}/output-destination", tags=["Flows"])
async def get_flow_output_destination(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    record = flow_output_destination_store.get(flow_id)
    if record is None:
        raise HTTPException(status_code=404, detail="No output destination for this flow")
    return record


@router.delete("/flows/{flow_id}/output-destination", tags=["Flows"])
async def delete_flow_output_destination(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    deleted = flow_output_destination_store.delete(flow_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="No output destination for this flow")
    return {"deleted": True, "flow_id": flow_id}


@router.put("/flows/{flow_id}/resource-limits", tags=["Flows"])
async def set_flow_resource_limits(
    flow_id: str,
    body: FlowResourceLimitBody,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    try:
        record = flow_resource_limit_store.set(
            flow_id, body.memory_mb, body.cpu_millicores, body.timeout_s
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return record


@router.get("/flows/{flow_id}/resource-limits", tags=["Flows"])
async def get_flow_resource_limits(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    record = flow_resource_limit_store.get(flow_id)
    if record is None:
        raise HTTPException(status_code=404, detail="No resource limits for this flow")
    return record


@router.delete("/flows/{flow_id}/resource-limits", tags=["Flows"])
async def delete_flow_resource_limits(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    deleted = flow_resource_limit_store.delete(flow_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="No resource limits for this flow")
    return {"deleted": True, "flow_id": flow_id}


@router.post("/flows/{flow_id}/acl/{user}", tags=["Flows"])
async def grant_flow_acl(
    flow_id: str,
    user: str,
    body: FlowAclGrantBody,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    try:
        entry = flow_acl_store.grant(flow_id, user, body.permissions)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return entry


@router.get("/flows/{flow_id}/acl", tags=["Flows"])
async def list_flow_acl(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    entries = flow_acl_store.list_entries(flow_id)
    return {"flow_id": flow_id, "entries": entries}


@router.get("/flows/{flow_id}/acl/{user}", tags=["Flows"])
async def get_flow_acl_user(
    flow_id: str,
    user: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    entry = flow_acl_store.get(flow_id, user)
    if entry is None:
        raise HTTPException(status_code=404, detail="ACL entry not found")
    return entry


@router.delete("/flows/{flow_id}/acl/{user}", tags=["Flows"])
async def revoke_flow_acl(
    flow_id: str,
    user: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    deleted = flow_acl_store.revoke(flow_id, user)
    if not deleted:
        raise HTTPException(status_code=404, detail="ACL entry not found")
    return {"deleted": True, "flow_id": flow_id, "user": user}


@router.put("/flows/{flow_id}/execution-mode", tags=["Flows"])
async def set_flow_execution_mode(
    flow_id: str,
    body: FlowExecutionModeBody,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    try:
        record = flow_execution_mode_store.set(flow_id, body.mode, body.debug)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return record


@router.get("/flows/{flow_id}/execution-mode", tags=["Flows"])
async def get_flow_execution_mode(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    record = flow_execution_mode_store.get(flow_id)
    if record is None:
        raise HTTPException(status_code=404, detail="No execution mode for this flow")
    return record


@router.delete("/flows/{flow_id}/execution-mode", tags=["Flows"])
async def delete_flow_execution_mode(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    deleted = flow_execution_mode_store.delete(flow_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="No execution mode for this flow")
    return {"deleted": True, "flow_id": flow_id}


@router.put("/flows/{flow_id}/input-validation", tags=["Flows"])
async def set_flow_input_validation(
    flow_id: str,
    body: FlowInputValidationBody,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    try:
        record = flow_input_validation_store.set(flow_id, body.rules, body.strict)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return record


@router.get("/flows/{flow_id}/input-validation", tags=["Flows"])
async def get_flow_input_validation(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    record = flow_input_validation_store.get(flow_id)
    if record is None:
        raise HTTPException(status_code=404, detail="No input validation for this flow")
    return record


@router.delete("/flows/{flow_id}/input-validation", tags=["Flows"])
async def delete_flow_input_validation(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    deleted = flow_input_validation_store.delete(flow_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="No input validation for this flow")
    return {"deleted": True, "flow_id": flow_id}


@router.put("/flows/{flow_id}/caching-config", tags=["Flows"])
async def set_flow_caching_config(
    flow_id: str,
    body: FlowCachingConfigBody,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    try:
        record = flow_caching_config_store.set(
            flow_id, body.enabled, body.ttl_seconds, body.key_fields
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return record


@router.get("/flows/{flow_id}/caching-config", tags=["Flows"])
async def get_flow_caching_config(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    record = flow_caching_config_store.get(flow_id)
    if record is None:
        raise HTTPException(status_code=404, detail="No caching config for this flow")
    return record


@router.delete("/flows/{flow_id}/caching-config", tags=["Flows"])
async def delete_flow_caching_config(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    deleted = flow_caching_config_store.delete(flow_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="No caching config for this flow")
    return {"deleted": True, "flow_id": flow_id}


@router.put("/flows/{flow_id}/circuit-breaker", tags=["Flows"])
async def set_flow_circuit_breaker(
    flow_id: str,
    body: FlowCircuitBreakerBody,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    try:
        record = flow_circuit_breaker_store.set(
            flow_id, body.enabled, body.failure_threshold, body.recovery_timeout_s
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return record


@router.get("/flows/{flow_id}/circuit-breaker", tags=["Flows"])
async def get_flow_circuit_breaker(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    record = flow_circuit_breaker_store.get(flow_id)
    if record is None:
        raise HTTPException(status_code=404, detail="No circuit breaker for this flow")
    return record


@router.delete("/flows/{flow_id}/circuit-breaker", tags=["Flows"])
async def delete_flow_circuit_breaker(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    deleted = flow_circuit_breaker_store.delete(flow_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="No circuit breaker for this flow")
    return {"deleted": True, "flow_id": flow_id}


@router.put("/flows/{flow_id}/observability-config", tags=["Flows"])
async def set_flow_observability_config(
    flow_id: str,
    body: FlowObservabilityConfigBody,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    try:
        record = flow_observability_config_store.set(
            flow_id,
            body.traces_enabled,
            body.metrics_enabled,
            body.logs_enabled,
            body.sample_rate,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return record


@router.get("/flows/{flow_id}/observability-config", tags=["Flows"])
async def get_flow_observability_config(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    record = flow_observability_config_store.get(flow_id)
    if record is None:
        raise HTTPException(status_code=404, detail="No observability config for this flow")
    return record


@router.delete("/flows/{flow_id}/observability-config", tags=["Flows"])
async def delete_flow_observability_config(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    deleted = flow_observability_config_store.delete(flow_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="No observability config for this flow")
    return {"deleted": True, "flow_id": flow_id}


@router.put("/flows/{flow_id}/maintenance-window", tags=["Flows"])
async def set_flow_maintenance_window(
    flow_id: str,
    body: FlowMaintenanceWindowBody,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    try:
        record = flow_maintenance_window_store.set(flow_id, body.start, body.end, body.reason)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return record


@router.get("/flows/{flow_id}/maintenance-window", tags=["Flows"])
async def get_flow_maintenance_window(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    record = flow_maintenance_window_store.get(flow_id)
    if record is None:
        raise HTTPException(status_code=404, detail="No maintenance window for this flow")
    return record


@router.delete("/flows/{flow_id}/maintenance-window", tags=["Flows"])
async def delete_flow_maintenance_window(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    deleted = flow_maintenance_window_store.delete(flow_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="No maintenance window for this flow")
    return {"deleted": True, "flow_id": flow_id}


@router.put("/flows/{flow_id}/geo-restrictions", tags=["Flows"])
async def set_flow_geo_restrictions(
    flow_id: str,
    body: FlowGeoRestrictionBody,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    try:
        record = flow_geo_restriction_store.set(flow_id, body.mode, body.regions)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return record


@router.get("/flows/{flow_id}/geo-restrictions", tags=["Flows"])
async def get_flow_geo_restrictions(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    record = flow_geo_restriction_store.get(flow_id)
    if record is None:
        raise HTTPException(status_code=404, detail="No geo restrictions for this flow")
    return record


@router.delete("/flows/{flow_id}/geo-restrictions", tags=["Flows"])
async def delete_flow_geo_restrictions(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    deleted = flow_geo_restriction_store.delete(flow_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="No geo restrictions for this flow")
    return {"deleted": True, "flow_id": flow_id}


@router.put("/flows/{flow_id}/ip-allowlist", tags=["Flows"])
async def set_flow_ip_allowlist(
    flow_id: str,
    body: FlowIpAllowlistBody,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    try:
        record = flow_ip_allowlist_store.set(flow_id, body.enabled, body.cidrs)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return record


@router.get("/flows/{flow_id}/ip-allowlist", tags=["Flows"])
async def get_flow_ip_allowlist(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    record = flow_ip_allowlist_store.get(flow_id)
    if record is None:
        raise HTTPException(status_code=404, detail="No IP allowlist for this flow")
    return record


@router.delete("/flows/{flow_id}/ip-allowlist", tags=["Flows"])
async def delete_flow_ip_allowlist(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    deleted = flow_ip_allowlist_store.delete(flow_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="No IP allowlist for this flow")
    return {"deleted": True, "flow_id": flow_id}


@router.put("/flows/{flow_id}/data-classification", tags=["Flows"])
async def set_flow_data_classification(
    flow_id: str,
    body: FlowDataClassificationBody,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    try:
        record = flow_data_classification_store.set(flow_id, body.level, body.pii_flag)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return record


@router.get("/flows/{flow_id}/data-classification", tags=["Flows"])
async def get_flow_data_classification(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    record = flow_data_classification_store.get(flow_id)
    if record is None:
        raise HTTPException(status_code=404, detail="No data classification for this flow")
    return record


@router.delete("/flows/{flow_id}/data-classification", tags=["Flows"])
async def delete_flow_data_classification(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    deleted = flow_data_classification_store.delete(flow_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="No data classification for this flow")
    return {"deleted": True, "flow_id": flow_id}


@router.post("/flows/{flow_id}/notification-channels", status_code=201, tags=["Flows"])
async def create_flow_notification_channel(
    flow_id: str,
    body: FlowNotificationChannelBody,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    try:
        record = flow_notification_channel_store.create(
            flow_id=flow_id,
            channel_type=body.type,
            target=body.target,
            events=body.events,
            enabled=body.enabled,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return record


@router.get("/flows/{flow_id}/notification-channels", tags=["Flows"])
async def list_flow_notification_channels(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> list:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    return flow_notification_channel_store.list(flow_id)


@router.get("/flows/{flow_id}/notification-channels/{channel_id}", tags=["Flows"])
async def get_flow_notification_channel(
    flow_id: str,
    channel_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    record = flow_notification_channel_store.get(flow_id, channel_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Channel not found")
    return record


@router.delete("/flows/{flow_id}/notification-channels/{channel_id}", tags=["Flows"])
async def delete_flow_notification_channel(
    flow_id: str,
    channel_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    deleted = flow_notification_channel_store.delete(flow_id, channel_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Channel not found")
    return {"deleted": True, "channel_id": channel_id, "flow_id": flow_id}


@router.put("/flows/{flow_id}/feature-flags/{flag_name}", tags=["Flows"])
async def set_flow_feature_flag(
    flow_id: str,
    flag_name: str,
    body: FlowFeatureFlagBody,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    try:
        record = flow_feature_flag_store.set(
            flow_id=flow_id,
            flag_name=flag_name,
            enabled=body.enabled,
            rollout_percentage=body.rollout_percentage,
            description=body.description,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return record


@router.get("/flows/{flow_id}/feature-flags", tags=["Flows"])
async def list_flow_feature_flags(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> list:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    return flow_feature_flag_store.list(flow_id)


@router.get("/flows/{flow_id}/feature-flags/{flag_name}", tags=["Flows"])
async def get_flow_feature_flag(
    flow_id: str,
    flag_name: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    record = flow_feature_flag_store.get(flow_id, flag_name)
    if record is None:
        raise HTTPException(status_code=404, detail="Feature flag not found")
    return record


@router.delete("/flows/{flow_id}/feature-flags/{flag_name}", tags=["Flows"])
async def delete_flow_feature_flag(
    flow_id: str,
    flag_name: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    deleted = flow_feature_flag_store.delete(flow_id, flag_name)
    if not deleted:
        raise HTTPException(status_code=404, detail="Feature flag not found")
    return {"deleted": True, "flag_name": flag_name, "flow_id": flow_id}


@router.post("/flows/{flow_id}/execution-hooks", tags=["Flows"], status_code=201)
async def add_flow_execution_hook(
    flow_id: str,
    body: FlowExecutionHookBody,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    try:
        record = flow_execution_hook_store.add(
            flow_id,
            body.hook_type,
            body.url,
            body.event,
            body.enabled,
            body.headers,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return record


@router.get("/flows/{flow_id}/execution-hooks", tags=["Flows"])
async def list_flow_execution_hooks(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    hooks = flow_execution_hook_store.list(flow_id)
    return {"flow_id": flow_id, "hooks": hooks, "total": len(hooks)}


@router.get("/flows/{flow_id}/execution-hooks/{hook_id}", tags=["Flows"])
async def get_flow_execution_hook(
    flow_id: str,
    hook_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    record = flow_execution_hook_store.get(flow_id, hook_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Execution hook not found")
    return record


@router.delete("/flows/{flow_id}/execution-hooks/{hook_id}", tags=["Flows"])
async def delete_flow_execution_hook(
    flow_id: str,
    hook_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    deleted = flow_execution_hook_store.delete(flow_id, hook_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Execution hook not found")
    return {"deleted": True, "hook_id": hook_id, "flow_id": flow_id}


@router.put("/flows/{flow_id}/custom-domain", tags=["Flows"])
async def set_flow_custom_domain(
    flow_id: str,
    body: FlowCustomDomainBody,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    try:
        record = flow_custom_domain_store.set(flow_id, body.domain, body.enabled)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return record


@router.get("/flows/{flow_id}/custom-domain", tags=["Flows"])
async def get_flow_custom_domain(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    record = flow_custom_domain_store.get(flow_id)
    if record is None:
        raise HTTPException(status_code=404, detail="No custom domain configured")
    return record


@router.delete("/flows/{flow_id}/custom-domain", tags=["Flows"])
async def delete_flow_custom_domain(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    deleted = flow_custom_domain_store.delete(flow_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="No custom domain configured")
    return {"deleted": True, "flow_id": flow_id}


@router.put("/flows/{flow_id}/webhook-signing", tags=["Flows"])
async def set_flow_webhook_signing(
    flow_id: str,
    body: FlowWebhookSigningBody,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    try:
        record = flow_webhook_signing_store.set(
            flow_id, body.secret, body.algorithm, body.enabled
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return record


@router.get("/flows/{flow_id}/webhook-signing", tags=["Flows"])
async def get_flow_webhook_signing(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    record = flow_webhook_signing_store.get(flow_id)
    if record is None:
        raise HTTPException(status_code=404, detail="No webhook signing configured")
    return record


@router.delete("/flows/{flow_id}/webhook-signing", tags=["Flows"])
async def delete_flow_webhook_signing(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    deleted = flow_webhook_signing_store.delete(flow_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="No webhook signing configured")
    return {"deleted": True, "flow_id": flow_id}


@router.post("/flows/{flow_id}/audit-export", tags=["Flows"], status_code=202)
async def create_flow_audit_export(
    flow_id: str,
    body: FlowAuditExportBody,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    try:
        record = flow_audit_export_store.create(
            flow_id, body.format, body.from_ts, body.to_ts
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return record


@router.get("/flows/{flow_id}/audit-export", tags=["Flows"])
async def list_flow_audit_exports(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    exports = flow_audit_export_store.list(flow_id)
    return {"flow_id": flow_id, "exports": exports, "total": len(exports)}


@router.get("/flows/{flow_id}/audit-export/{job_id}", tags=["Flows"])
async def get_flow_audit_export(
    flow_id: str,
    job_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    record = flow_audit_export_store.get(job_id)
    if record is None or record.get("flow_id") != flow_id:
        raise HTTPException(status_code=404, detail="Export job not found")
    return record


@router.put("/flows/{flow_id}/collaborator-roles/{user_id}", tags=["Flows"])
async def set_flow_collaborator_role(
    flow_id: str,
    user_id: str,
    body: FlowCollaboratorRoleBody,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    try:
        record = flow_collaborator_role_store.set(flow_id, user_id, body.role)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return record


@router.get("/flows/{flow_id}/collaborator-roles", tags=["Flows"])
async def list_flow_collaborator_roles(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    roles = flow_collaborator_role_store.list(flow_id)
    return {"flow_id": flow_id, "collaborators": roles, "total": len(roles)}


@router.get("/flows/{flow_id}/collaborator-roles/{user_id}", tags=["Flows"])
async def get_flow_collaborator_role(
    flow_id: str,
    user_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    record = flow_collaborator_role_store.get(flow_id, user_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Collaborator role not found")
    return record


@router.delete("/flows/{flow_id}/collaborator-roles/{user_id}", tags=["Flows"])
async def delete_flow_collaborator_role(
    flow_id: str,
    user_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    deleted = flow_collaborator_role_store.delete(flow_id, user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Collaborator role not found")
    return {"deleted": True, "user_id": user_id, "flow_id": flow_id}


@router.put("/flows/{flow_id}/input-mask", tags=["Flows"])
async def set_flow_input_mask(
    flow_id: str,
    body: FlowInputMaskBody,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    try:
        record = flow_input_mask_store.set(flow_id, body.rules, body.enabled)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return record


@router.get("/flows/{flow_id}/input-mask", tags=["Flows"])
async def get_flow_input_mask(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    record = flow_input_mask_store.get(flow_id)
    if record is None:
        raise HTTPException(status_code=404, detail="No input mask configured")
    return record


@router.delete("/flows/{flow_id}/input-mask", tags=["Flows"])
async def delete_flow_input_mask(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    deleted = flow_input_mask_store.delete(flow_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="No input mask configured")
    return {"deleted": True, "flow_id": flow_id}


@router.put("/flows/{flow_id}/output-transform", tags=["Flows"])
async def set_flow_output_transform(
    flow_id: str,
    body: FlowOutputTransformBody,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict[str, Any]:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    return flow_output_transform_store.set(
        flow_id=flow_id,
        expression=body.expression,
        output_format=body.output_format,
        enabled=body.enabled,
    )


@router.get("/flows/{flow_id}/output-transform", tags=["Flows"])
async def get_flow_output_transform(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict[str, Any]:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    record = flow_output_transform_store.get(flow_id)
    if record is None:
        raise HTTPException(status_code=404, detail="No output transform configured")
    return record


@router.delete("/flows/{flow_id}/output-transform", tags=["Flows"])
async def delete_flow_output_transform(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict[str, Any]:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    deleted = flow_output_transform_store.delete(flow_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="No output transform configured")
    return {"deleted": True, "flow_id": flow_id}


@router.put("/flows/{flow_id}/data-retention", tags=["Flows"])
async def set_flow_data_retention(
    flow_id: str,
    body: FlowDataRetentionBody,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict[str, Any]:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    return flow_data_retention_store.set(
        flow_id=flow_id,
        retention_days=body.retention_days,
        delete_on_expiry=body.delete_on_expiry,
        anonymize_on_expiry=body.anonymize_on_expiry,
        enabled=body.enabled,
    )


@router.get("/flows/{flow_id}/data-retention", tags=["Flows"])
async def get_flow_data_retention(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict[str, Any]:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    record = flow_data_retention_store.get(flow_id)
    if record is None:
        raise HTTPException(status_code=404, detail="No data retention policy configured")
    return record


@router.delete("/flows/{flow_id}/data-retention", tags=["Flows"])
async def delete_flow_data_retention(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict[str, Any]:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    deleted = flow_data_retention_store.delete(flow_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="No data retention policy configured")
    return {"deleted": True, "flow_id": flow_id}


@router.put("/flows/{flow_id}/allowed-origins", tags=["Flows"])
async def set_flow_allowed_origins(
    flow_id: str,
    body: FlowAllowedOriginsBody,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict[str, Any]:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    try:
        return flow_allowed_origins_store.set(
            flow_id=flow_id,
            origins=body.origins,
            enabled=body.enabled,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/flows/{flow_id}/allowed-origins", tags=["Flows"])
async def get_flow_allowed_origins(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict[str, Any]:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    record = flow_allowed_origins_store.get(flow_id)
    if record is None:
        raise HTTPException(status_code=404, detail="No allowed origins configured")
    return record


@router.delete("/flows/{flow_id}/allowed-origins", tags=["Flows"])
async def delete_flow_allowed_origins(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict[str, Any]:
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    deleted = flow_allowed_origins_store.delete(flow_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="No allowed origins configured")
    return {"deleted": True, "flow_id": flow_id}


@router.post("/flows/{flow_id}/archive", tags=["Flows"])
async def archive_flow(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Soft-delete a flow by archiving it.

    Archived flows are excluded from GET /flows by default.
    Use GET /flows?archived=true to list only archived flows.
    Restore with DELETE /flows/{id}/archive.
    """
    flow = await FlowRepository.get_by_id(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
    if flow_archive_store.is_archived(flow_id):
        raise HTTPException(status_code=409, detail="Flow is already archived")
    ts = flow_archive_store.archive(flow_id)
    archived_at = datetime.fromtimestamp(ts, tz=UTC).isoformat()
    return {"flow_id": flow_id, "archived": True, "archived_at": archived_at}


@router.delete("/flows/{flow_id}/archive", tags=["Flows"])
async def restore_flow(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Restore an archived flow, making it visible in normal listings again."""
    flow = await FlowRepository.get_by_id(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
    restored = flow_archive_store.restore(flow_id)
    if not restored:
        raise HTTPException(status_code=409, detail="Flow is not archived")
    return {"flow_id": flow_id, "archived": False}

