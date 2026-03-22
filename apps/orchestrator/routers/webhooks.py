"""
Webhooks router for SynApps Orchestrator.

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
    TASK_STATUSES,
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
    TEMPLATE_EXPORT_VERSION,
    _SSE_EVENT_TYPE_MAP,
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

from apps.orchestrator.webhooks.manager import WebhookManager  # noqa: E402

# webhook_registry is populated by main.py after module load
webhook_registry: WebhookManager = None  # type: ignore[assignment]

# dead_letter_queue, scheduler_registry, CompoundConditionEvaluator populated by main.py
dead_letter_queue = None  # type: ignore[assignment]
scheduler_registry = None  # type: ignore[assignment]
CompoundConditionEvaluator = None  # type: ignore[assignment]
# webhook_trigger_registry is overridden by main.py after Fernet init
# (the stores version lacks encryption; main.py creates a Fernet-enabled one)

router = APIRouter()


# ============================================================
# Webhooks Routes
# ============================================================

@router.get("/webhooks/debug", tags=["Webhook Debugger"])
async def list_webhook_debug_entries(
    flow_id: str | None = None,
    limit: int = 50,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict[str, Any]:
    """List recent webhook debug entries, newest first."""
    items = webhook_debug_store.list(flow_id=flow_id, limit=limit)
    return {"items": items, "total": len(items)}


@router.get("/webhooks/debug/{entry_id}", tags=["Webhook Debugger"])
async def get_webhook_debug_entry(
    entry_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict[str, Any]:
    """Get a single webhook debug entry by ID."""
    entry = webhook_debug_store.get(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Webhook debug entry not found")
    return entry


@router.post("/webhooks/debug/{entry_id}/retry", tags=["Webhook Debugger"])
async def retry_webhook_debug_entry(
    entry_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict[str, Any]:
    """Retry a webhook delivery by re-sending the original payload.

    Increments retry_count and updates last_retry_at on the entry.
    Re-invokes the same flow with the original body.
    """
    entry = webhook_debug_store.get(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Webhook debug entry not found")

    flow_id = entry.get("flow_id")
    if not flow_id:
        raise HTTPException(status_code=400, detail="No flow_id associated with this entry")

    # Re-parse the stored body to build flow input
    body_text = entry.get("body", "")
    try:
        parsed = json.loads(body_text) if body_text else {}
        if not isinstance(parsed, dict):
            parsed = {"payload": parsed}
    except (json.JSONDecodeError, ValueError):
        parsed = {"raw": body_text}

    flow_input = {"payload": parsed, "trigger_id": entry_id}
    run_body = RunFlowRequest(input=flow_input)

    retry_status = 202
    retry_response = ""
    try:
        result = await _run_flow_impl(flow_id, run_body)
        retry_response = json.dumps({"accepted": True, "run_id": result["run_id"]})
    except HTTPException as exc:
        retry_status = exc.status_code
        retry_response = json.dumps({"detail": exc.detail})[:2000]
    except Exception as exc:
        retry_status = 500
        retry_response = json.dumps({"detail": str(exc)})[:2000]
        logger.warning("Webhook retry failed for entry %s: %s", entry_id, exc)

    # Update the entry in place
    entry["retry_count"] = entry.get("retry_count", 0) + 1
    entry["last_retry_at"] = time.time()
    entry["status_code"] = retry_status
    entry["response_body"] = retry_response[:2000]

    return entry


@router.delete("/webhooks/debug", status_code=204, tags=["Webhook Debugger"])
async def clear_webhook_debug_entries(
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> None:
    """Clear all webhook debug entries."""
    webhook_debug_store.clear()
    return None


@router.post("/webhooks", status_code=201, tags=["Dashboard"])
async def register_webhook(
    payload: RegisterWebhookRequest,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Register a new webhook for event delivery."""
    hook = webhook_registry.register(
        url=payload.url,
        events=payload.events,
        secret=payload.secret,
    )
    return hook


@router.get("/webhooks", tags=["Dashboard"])
async def list_webhooks(
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """List all registered webhooks (secrets are not returned)."""
    hooks = webhook_registry.list_hooks()
    return {"webhooks": hooks, "total": len(hooks)}


@router.delete("/webhooks/{hook_id}", tags=["Dashboard"])
async def delete_webhook(
    hook_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Delete a webhook by ID."""
    if not webhook_registry.delete(hook_id):
        raise HTTPException(status_code=404, detail=f"Webhook '{hook_id}' not found")
    return {"message": "Webhook deleted", "id": hook_id}


@router.post("/webhook-triggers", status_code=201, tags=["Webhook Triggers"])
async def register_webhook_trigger(
    payload: RegisterWebhookTriggerRequest,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Register a new inbound webhook trigger tied to a flow.

    Returns a trigger record with an ``id`` that forms the unique receive URL:
    ``POST /api/v1/webhook-triggers/{id}/receive``.
    Secrets are stored encrypted and never returned in subsequent calls.
    """
    # Verify the target flow exists
    flow = await FlowRepository.get_by_id(payload.flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail=f"Flow '{payload.flow_id}' not found")
    trigger = webhook_trigger_registry.register(
        flow_id=payload.flow_id,
        secret=payload.secret,
    )
    return trigger


@router.get("/webhook-triggers", tags=["Webhook Triggers"])
async def list_webhook_triggers(
    flow_id: str | None = Query(None, description="Filter by flow ID"),
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """List all registered inbound webhook triggers (secrets not returned)."""
    triggers = webhook_trigger_registry.list_triggers(flow_id=flow_id)
    return {"triggers": triggers, "total": len(triggers)}


@router.get("/webhook-triggers/{trigger_id}", tags=["Webhook Triggers"])
async def get_webhook_trigger(
    trigger_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Get a single webhook trigger by ID (secret not returned)."""
    trigger = webhook_trigger_registry.get(trigger_id)
    if not trigger:
        raise HTTPException(status_code=404, detail=f"Trigger '{trigger_id}' not found")
    return trigger


@router.delete("/webhook-triggers/{trigger_id}", tags=["Webhook Triggers"])
async def delete_webhook_trigger(
    trigger_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Delete a webhook trigger by ID."""
    if not webhook_trigger_registry.delete(trigger_id):
        raise HTTPException(status_code=404, detail=f"Trigger '{trigger_id}' not found")
    return {"message": "Webhook trigger deleted", "id": trigger_id}


@router.post(
    "/webhook-triggers/{trigger_id}/receive",
    status_code=202,
    tags=["Webhook Triggers"],
)
async def receive_webhook_trigger(
    trigger_id: str,
    request: Request,
    x_webhook_signature: str | None = Header(None, alias="X-Webhook-Signature"),
):
    """Receive an inbound webhook and trigger the associated flow.

    No session auth is required — the caller is authenticated via HMAC-SHA256
    signature when a secret is configured on the trigger.  Unsigned requests
    are accepted only when the trigger has no secret.

    The raw request body is passed as the flow's ``input`` dict under the key
    ``payload``.  If the body is valid JSON it is inlined directly; otherwise
    it is wrapped as ``{"raw": "<body_text>"}``.
    """
    _wh_start = time.time()
    body_bytes = await request.body()
    body_text = body_bytes.decode("utf-8", errors="replace")

    # Build sanitized headers (drop Authorization value for security)
    raw_headers: dict[str, str] = {}
    for k, v in request.headers.items():
        if k.lower() == "authorization":
            raw_headers[k] = "[REDACTED]"
        else:
            raw_headers[k] = v

    # Determine flow_id from the trigger registry (may be None if trigger unknown)
    trigger_meta = webhook_trigger_registry.get(trigger_id)
    debug_flow_id: str | None = trigger_meta["flow_id"] if trigger_meta else None

    if not webhook_trigger_registry.verify_signature(trigger_id, body_bytes, x_webhook_signature):
        # Record failed delivery before raising
        _wh_dur = (time.time() - _wh_start) * 1000
        webhook_debug_store.record(
            {
                "entry_id": str(uuid.uuid4()),
                "flow_id": debug_flow_id,
                "received_at": _wh_start,
                "method": request.method,
                "path": str(request.url.path),
                "headers": raw_headers,
                "body": body_text[:10_000],
                "body_size": len(body_bytes),
                "status_code": 401,
                "response_body": '{"detail":"Invalid or missing webhook signature"}',
                "duration_ms": _wh_dur,
                "retry_count": 0,
                "last_retry_at": None,
            }
        )
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing webhook signature",
        )

    trigger = webhook_trigger_registry.get(trigger_id)
    if not trigger:
        _wh_dur = (time.time() - _wh_start) * 1000
        webhook_debug_store.record(
            {
                "entry_id": str(uuid.uuid4()),
                "flow_id": None,
                "received_at": _wh_start,
                "method": request.method,
                "path": str(request.url.path),
                "headers": raw_headers,
                "body": body_text[:10_000],
                "body_size": len(body_bytes),
                "status_code": 404,
                "response_body": f'{{"detail":"Trigger \'{trigger_id}\' not found"}}',
                "duration_ms": _wh_dur,
                "retry_count": 0,
                "last_retry_at": None,
            }
        )
        raise HTTPException(status_code=404, detail=f"Trigger '{trigger_id}' not found")

    # Parse body → flow input
    try:
        parsed = json.loads(body_bytes) if body_bytes else {}
        if not isinstance(parsed, dict):
            parsed = {"payload": parsed}
    except (json.JSONDecodeError, ValueError):
        parsed = {"raw": body_text}

    flow_input = {"payload": parsed, "trigger_id": trigger_id}
    run_body = RunFlowRequest(input=flow_input)

    status_code = 202
    response_body = ""
    try:
        result = await _run_flow_impl(trigger["flow_id"], run_body)
        response_body = json.dumps(
            {"accepted": True, "run_id": result["run_id"], "trigger_id": trigger_id}
        )
    except HTTPException as exc:
        status_code = exc.status_code
        response_body = json.dumps({"detail": exc.detail})[:2000]
        raise
    except Exception as exc:
        status_code = 500
        response_body = json.dumps({"detail": str(exc)})[:2000]
        raise
    finally:
        _wh_dur = (time.time() - _wh_start) * 1000
        webhook_debug_store.record(
            {
                "entry_id": str(uuid.uuid4()),
                "flow_id": trigger["flow_id"],
                "received_at": _wh_start,
                "method": request.method,
                "path": str(request.url.path),
                "headers": raw_headers,
                "body": body_text[:10_000],
                "body_size": len(body_bytes),
                "status_code": status_code,
                "response_body": response_body[:2000],
                "duration_ms": _wh_dur,
                "retry_count": 0,
                "last_retry_at": None,
            }
        )

    return {"accepted": True, "run_id": result["run_id"], "trigger_id": trigger_id}


@router.post("/schedules", status_code=201, tags=["Schedules"])
async def create_schedule(
    body: CreateScheduleRequest,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Register a new cron schedule for a flow.

    The ``cron_expr`` field accepts standard 5-field cron syntax::

        ┌─────── minute (0–59)
        │ ┌───── hour (0–23)
        │ │ ┌─── day of month (1–31)
        │ │ │ ┌─ month (1–12)
        │ │ │ │ ┌ day of week (0–7, Sunday=0/7)
        │ │ │ │ │
        * * * * *

    Examples: ``0 9 * * 1-5`` (9 AM Mon–Fri), ``*/15 * * * *`` (every 15 min).
    """
    # Verify the flow exists
    flow = await FlowRepository.get_by_id(body.flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail=f"Flow '{body.flow_id}' not found")

    try:
        entry = scheduler_registry.create(
            flow_id=body.flow_id,
            cron_expr=body.cron_expr,
            name=body.name,
            enabled=body.enabled,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return entry


@router.get("/schedules", tags=["Schedules"])
async def list_schedules(
    flow_id: str | None = Query(None, description="Filter by flow ID."),
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """List all registered schedules, optionally filtered by flow."""
    return scheduler_registry.list(flow_id=flow_id)


@router.get("/schedules/{schedule_id}", tags=["Schedules"])
async def get_schedule(
    schedule_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Retrieve a single schedule by ID."""
    entry = scheduler_registry.get(schedule_id)
    if not entry:
        raise HTTPException(status_code=404, detail=f"Schedule '{schedule_id}' not found")
    return entry


@router.patch("/schedules/{schedule_id}", tags=["Schedules"])
async def update_schedule(
    schedule_id: str,
    body: UpdateScheduleRequest,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Pause, resume, rename, or change the cron expression of a schedule."""
    if not scheduler_registry.get(schedule_id):
        raise HTTPException(status_code=404, detail=f"Schedule '{schedule_id}' not found")

    updates: dict[str, Any] = {}
    if body.cron_expr is not None:
        updates["cron_expr"] = body.cron_expr
    if body.name is not None:
        updates["name"] = body.name
    if body.enabled is not None:
        updates["enabled"] = body.enabled

    if not updates:
        raise HTTPException(status_code=422, detail="No update fields provided")

    try:
        entry = scheduler_registry.update(schedule_id, **updates)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return entry


@router.delete("/schedules/{schedule_id}", status_code=204, tags=["Schedules"])
async def delete_schedule(
    schedule_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Delete a schedule. The associated flow is not affected."""
    if not scheduler_registry.delete(schedule_id):
        raise HTTPException(status_code=404, detail=f"Schedule '{schedule_id}' not found")


@router.get("/dlq", tags=["DLQ"])
async def list_dlq(
    flow_id: str | None = Query(None, description="Filter by flow ID."),
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """List dead-lettered (failed) runs, newest first."""
    return {
        "items": dead_letter_queue.list(flow_id=flow_id),
        "total": dead_letter_queue.size()
        if flow_id is None
        else len(dead_letter_queue.list(flow_id=flow_id)),
    }


@router.get("/dlq/{entry_id}", tags=["DLQ"])
async def get_dlq_entry(
    entry_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Get a single dead-lettered run by DLQ entry ID."""
    entry = dead_letter_queue.get(entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail=f"DLQ entry '{entry_id}' not found")
    return entry


@router.delete("/dlq/{entry_id}", status_code=204, tags=["DLQ"])
async def delete_dlq_entry(
    entry_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Remove a dead-lettered run from the queue."""
    if not dead_letter_queue.delete(entry_id):
        raise HTTPException(status_code=404, detail=f"DLQ entry '{entry_id}' not found")


@router.post("/dlq/{entry_id}/replay", status_code=202, tags=["DLQ"])
async def replay_dlq_entry(
    entry_id: str,
    body: ReplayDLQRequest = ReplayDLQRequest(),
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Replay a dead-lettered run using the original (or overridden) input.

    Looks up the flow by ID and re-executes with the stored input data (or
    ``input_override`` if provided). Increments ``replay_count`` on the entry.
    """
    entry = dead_letter_queue.get(entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail=f"DLQ entry '{entry_id}' not found")

    flow_id = entry.get("flow_id")
    if not flow_id:
        raise HTTPException(status_code=422, detail="DLQ entry has no flow_id — cannot replay")

    replay_input = (
        body.input_override if body.input_override is not None else entry.get("input_data", {})
    )
    run_body = RunFlowRequest(input=replay_input)

    result = await _run_flow_impl(flow_id, run_body)
    dead_letter_queue.increment_replay(entry_id)
    return {"accepted": True, "run_id": result["run_id"], "dlq_entry_id": entry_id}


@router.post("/templates/import", status_code=201, tags=["Templates"])
async def import_template(
    body: TemplateImportRequest,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Import a template from JSON. Creates a new version if the ID already exists."""
    data = body.model_dump()
    try:
        entry = template_registry.import_template(data)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return entry


@router.get("/templates/{template_id}/export", tags=["Templates"])
async def export_template(
    template_id: str,
    version: int | None = Query(None, ge=1, description="Version number. Latest if omitted."),
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Export a template as portable JSON with metadata.

    Checks the versioned template registry first, then falls back to YAML
    templates on disk.
    """
    template = template_registry.get(template_id, version=version)
    if not template:
        # Fall back to YAML templates on disk (no versioning)
        yaml_data = _load_yaml_template(template_id)
        if not yaml_data:
            raise HTTPException(status_code=404, detail=f"Template '{template_id}' not found")
        template = {
            "id": yaml_data.get("id", template_id),
            "version": 1,
            "semver": "1.0.0",
            "name": yaml_data.get("name", ""),
            "description": yaml_data.get("description", ""),
            "tags": yaml_data.get("tags", []),
            "nodes": yaml_data.get("nodes", []),
            "edges": yaml_data.get("edges", []),
            "metadata": yaml_data.get("metadata", {}),
        }

    export_data = {
        "synapps_export_version": TEMPLATE_EXPORT_VERSION,
        "exported_at": time.time(),
        **template,
    }

    safe_name = re.sub(r"[^a-zA-Z0-9_-]", "_", template.get("name", "template"))[:60]
    return JSONResponse(
        content=export_data,
        headers={
            "Content-Disposition": f'attachment; filename="{safe_name}.synapps-template.json"',
        },
    )


@router.get("/templates/{template_id}/versions", tags=["Templates"])
async def list_template_versions(
    template_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """List all versions of a template."""
    versions = template_registry.list_versions(template_id)
    if not versions:
        raise HTTPException(status_code=404, detail=f"Template '{template_id}' not found")
    return {"template_id": template_id, "versions": versions, "total": len(versions)}


@router.get("/templates", tags=["Templates"])
async def list_templates(
    category: str | None = Query(
        None,
        description="Filter by category: notification, data-sync, monitoring, content, devops",
    ),
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """List all imported templates (latest version of each), optionally filtered by category."""
    templates = template_registry.list_templates()
    if category:
        category_lower = category.lower()
        templates = [
            t
            for t in templates
            if t.get("metadata", {}).get("category", "").lower() == category_lower
            or category_lower in [c.lower() for c in t.get("metadata", {}).get("categories", [])]
        ]
    return {"templates": templates, "total": len(templates)}


@router.get("/templates/search", tags=["Templates"])
async def search_templates(
    q: str | None = Query(None, description="Full-text search against name and description."),
    tags: list[str] = Query(default=[], description="Filter by tags (any match)."),
    category: str | None = Query(None, description="Filter by category metadata."),
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Search templates by name/description text and/or tags.

    Results are ranked by recency (most recently imported first). All filters
    are AND-combined: a template must match every supplied filter to appear.
    """
    results = template_registry.list_templates()

    if q:
        q_lower = q.lower()
        results = [
            t
            for t in results
            if q_lower in t.get("name", "").lower() or q_lower in t.get("description", "").lower()
        ]

    if tags:
        tag_set = {t.lower() for t in tags}
        results = [
            t for t in results if tag_set.intersection({tg.lower() for tg in t.get("tags", [])})
        ]

    if category:
        cat_lower = category.lower()
        results = [
            t for t in results if t.get("metadata", {}).get("category", "").lower() == cat_lower
        ]

    return {"items": results, "total": len(results)}


@router.get("/templates/{template_id}/by-semver", tags=["Templates"])
async def get_template_by_semver(
    template_id: str,
    version: str | None = Query(
        None,
        description="Semver version (e.g. '1.0.0'). Returns latest if omitted.",
        pattern=r"^\d+\.\d+\.\d+$",
    ),
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Fetch a specific template version by semver string.

    Returns the latest version if the ``version`` query param is omitted.
    """
    template = template_registry.get_by_semver(template_id, semver=version)
    if not template:
        # Fall back to YAML templates on disk when no semver requested
        if version is None:
            yaml_data = _load_yaml_template(template_id)
            if yaml_data:
                return {
                    "id": yaml_data.get("id", template_id),
                    "version": 1,
                    "semver": "1.0.0",
                    "name": yaml_data.get("name", ""),
                    "description": yaml_data.get("description", ""),
                    "tags": yaml_data.get("tags", []),
                    "nodes": yaml_data.get("nodes", []),
                    "edges": yaml_data.get("edges", []),
                    "metadata": yaml_data.get("metadata", {}),
                }
        detail = (
            f"Template '{template_id}' version '{version}' not found"
            if version
            else f"Template '{template_id}' not found"
        )
        raise HTTPException(status_code=404, detail=detail)
    return template


@router.put("/templates/{template_id}/rollback", tags=["Templates"])
async def rollback_template(
    template_id: str,
    version: str = Query(
        ...,
        description="Semver version to rollback to (e.g. '1.0.0').",
        pattern=r"^\d+\.\d+\.\d+$",
    ),
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Rollback a template to a previous semver version.

    Creates a new version whose content is copied from the target version.
    The new version gets the next auto-incremented semver.
    """
    entry = template_registry.rollback(template_id, target_semver=version)
    if entry is None:
        # Distinguish between template not found and version not found
        versions = template_registry.list_versions(template_id)
        if not versions:
            raise HTTPException(status_code=404, detail=f"Template '{template_id}' not found")
        raise HTTPException(
            status_code=404,
            detail=f"Version '{version}' not found for template '{template_id}'",
        )
    return entry


@router.post("/templates", status_code=201, tags=["Templates"])
async def publish_template(
    body: PublishTemplateRequest,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Publish an existing flow as a marketplace template.

    Snapshots the flow's nodes and edges into the template registry with
    marketplace metadata (category, author).
    """
    flow = await FlowRepository.get_by_id(body.flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail=f"Flow '{body.flow_id}' not found")

    template_data = {
        "name": body.name,
        "description": body.description,
        "tags": [body.category],
        "nodes": _scrub_node_credentials(flow.get("nodes", [])),
        "edges": flow.get("edges", []),
        "metadata": {
            "category": body.category,
            "author": body.author,
            "source_flow_id": body.flow_id,
        },
    }
    if body.version:
        template_data["version"] = body.version

    try:
        entry = template_registry.import_template(template_data)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return entry


@router.post("/templates/{template_id}/instantiate", status_code=201, tags=["Templates"])
async def instantiate_template(
    template_id: str,
    body: InstantiateTemplateRequest,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Create a new flow from a marketplace template.

    Clones the template's nodes and edges into a fresh flow, re-mapping all
    IDs to avoid collisions. If ``connector_overrides`` are provided, the
    matching node configs are merged with the user's actual connector settings.
    """
    template = template_registry.get(template_id)
    if not template:
        raise HTTPException(status_code=404, detail=f"Template '{template_id}' not found")

    # Re-map node IDs
    id_map: dict[str, str] = {}
    new_nodes = []
    for node in template.get("nodes", []):
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

    # Re-map edge references
    new_edges = []
    for edge in template.get("edges", []):
        new_edges.append(
            {
                "id": str(uuid.uuid4()),
                "source": id_map.get(edge.get("source", ""), edge.get("source", "")),
                "target": id_map.get(edge.get("target", ""), edge.get("target", "")),
                "animated": edge.get("animated", False),
            }
        )

    flow_name = body.flow_name or template.get("name", "Unnamed Flow")
    new_flow_id = str(uuid.uuid4())
    flow_data = {
        "id": new_flow_id,
        "name": flow_name,
        "nodes": new_nodes,
        "edges": new_edges,
    }

    await FlowRepository.save(flow_data)
    return {
        "message": "Flow created from template",
        "flow_id": new_flow_id,
        "template_id": template_id,
        "template_version": template.get("version"),
    }


@router.post("/templates/{template_id}/run-async", status_code=202, tags=["Runs"])
async def run_template_async(
    template_id: str,
    body: RunAsyncRequest,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Run a YAML template asynchronously. Returns a task ID for polling."""
    template_data = _load_yaml_template(template_id)
    if not template_data:
        raise HTTPException(status_code=404, detail=f"Template '{template_id}' not found")

    task_id = task_queue.create(template_id, template_data.get("name", ""))
    asyncio.create_task(_run_task_background(task_id, template_data, body.input))
    return {"task_id": task_id, "status": "pending"}


@router.get("/tasks/{task_id}", tags=["Runs"])
async def get_task(
    task_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Get the status and result of an async task."""
    task = task_queue.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
    return task


@router.get("/tasks", tags=["Runs"])
async def list_tasks(
    status: str | None = Query(
        None, description="Filter by status: pending, running, completed, failed"
    ),
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """List all async tasks, optionally filtered by status."""
    if status and status not in TASK_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status. Valid: {TASK_STATUSES}")
    tasks = task_queue.list_tasks(status=status)
    return {"tasks": tasks, "total": len(tasks)}


@router.get("/executions/{run_id}/stream", tags=["Executions"])
async def stream_execution_events(
    run_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> EventSourceResponse:
    """Stream node-by-node execution progress as Server-Sent Events.

    Replays all existing log entries for *run_id* first, then streams new
    events in real-time.  Closes automatically when an ``execution_complete``
    event is received.

    SSE event types emitted:
    - ``node_started`` — a node has begun execution
    - ``node_completed`` — a node succeeded (or used fallback)
    - ``node_failed`` — a node errored
    - ``execution_complete`` — the workflow reached a terminal state (``data``
      includes ``status`` and optional ``error``)
    """
    import json as _json

    # Validate run exists or has logs
    existing_logs = execution_log_store.get(run_id)
    run_record = await WorkflowRunRepository.get_by_run_id(run_id)
    if not existing_logs and run_record is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")

    async def _event_generator():
        q = sse_event_bus.subscribe(run_id)
        try:
            # --- Replay existing log entries ---
            for entry in existing_logs:
                raw_event = entry.get("event", "")
                sse_type = _SSE_EVENT_TYPE_MAP.get(raw_event, raw_event)
                payload = {
                    "run_id": run_id,
                    "node_id": entry.get("node_id"),
                    "node_type": entry.get("node_type"),
                    "timestamp": entry.get("timestamp"),
                    "attempt": entry.get("attempt"),
                    "error": entry.get("error"),
                    "duration_ms": entry.get("duration_ms"),
                }
                yield {"event": sse_type, "data": _json.dumps(payload)}

            # --- If run already terminal, send execution_complete and exit ---
            if run_record and run_record.get("status") in ("success", "error"):
                yield {
                    "event": "execution_complete",
                    "data": _json.dumps(
                        {
                            "run_id": run_id,
                            "status": run_record["status"],
                            "error": run_record.get("error"),
                        }
                    ),
                }
                return

            # --- Stream live events ---
            while True:
                try:
                    entry = await asyncio.wait_for(q.get(), timeout=1.0)
                except TimeoutError:
                    # Poll for terminal status (covers race between publish and subscribe)
                    check = await WorkflowRunRepository.get_by_run_id(run_id)
                    if check and check.get("status") in ("success", "error"):
                        yield {
                            "event": "execution_complete",
                            "data": _json.dumps(
                                {
                                    "run_id": run_id,
                                    "status": check["status"],
                                    "error": check.get("error"),
                                }
                            ),
                        }
                        return
                    continue

                raw_event = entry.get("event", "")
                sse_type = _SSE_EVENT_TYPE_MAP.get(raw_event, raw_event)
                if raw_event == "execution_complete":
                    yield {
                        "event": "execution_complete",
                        "data": _json.dumps(
                            {
                                "run_id": run_id,
                                "status": entry.get("status"),
                                "error": entry.get("error"),
                                "duration_ms": entry.get("duration_ms"),
                            }
                        ),
                    }
                    return

                payload = {
                    "run_id": run_id,
                    "node_id": entry.get("node_id"),
                    "node_type": entry.get("node_type"),
                    "timestamp": entry.get("timestamp"),
                    "attempt": entry.get("attempt"),
                    "error": entry.get("error"),
                    "duration_ms": entry.get("duration_ms"),
                }
                yield {"event": sse_type, "data": _json.dumps(payload)}

        finally:
            sse_event_bus.unsubscribe(run_id, q)

    return EventSourceResponse(_event_generator())


@router.post("/oauth/clients", status_code=201)
async def oauth_register_client(
    body: OAuthClientRegisterRequest,
    _user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict[str, Any]:
    """Register a new OAuth2 client application.

    The ``client_secret`` is included in the response exactly once and is not
    retrievable afterwards.
    """
    record = oauth_client_registry.register(
        name=body.name,
        redirect_uris=body.redirect_uris,
        allowed_scopes=body.allowed_scopes,
        grant_types=body.grant_types,
    )
    logger.info("OAuth2 client registered: client_id=%s name=%s", record["client_id"], body.name)
    return record


@router.get("/oauth/clients")
async def oauth_list_clients(
    _user: dict[str, Any] = Depends(get_authenticated_user),
) -> list[dict[str, Any]]:
    """List all registered OAuth2 clients (secrets not included)."""
    return oauth_client_registry.list_all()


@router.delete("/oauth/clients/{client_id}", status_code=204)
async def oauth_revoke_client(
    client_id: str,
    _user: dict[str, Any] = Depends(get_authenticated_user),
) -> None:
    """Revoke (deactivate) a registered OAuth2 client."""
    revoked = oauth_client_registry.revoke(client_id)
    if not revoked:
        raise HTTPException(status_code=404, detail="OAuth2 client not found")
    logger.info("OAuth2 client revoked: client_id=%s", client_id)


@router.get("/oauth/authorize")
async def oauth_authorize(
    client_id: str = Query(...),
    redirect_uri: str = Query(...),
    response_type: str = Query(...),
    scope: str = Query(default="read"),
    state: str | None = Query(default=None),
    authorization: str | None = Header(None, alias="Authorization"),
) -> dict[str, Any]:
    """OAuth2 authorization endpoint (authorization_code flow).

    Requires a valid user JWT in the ``Authorization: Bearer`` header to
    identify the authorizing user.  Auto-approves the grant (no consent UI).
    """
    if response_type != "code":
        raise HTTPException(
            status_code=400,
            detail="Only response_type=code is supported",
        )

    # Validate the client exists and is active.
    client = oauth_client_registry.get(client_id)
    if client is None or not client.get("is_active", False):
        raise HTTPException(status_code=400, detail="Unknown or inactive OAuth2 client")

    # Validate the redirect_uri against the registered list.
    if redirect_uri not in client["redirect_uris"]:
        raise HTTPException(status_code=400, detail="redirect_uri not registered for this client")

    # Identify the authorizing user from the Bearer token.
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401, detail="Authorization header with Bearer token required"
        )
    token_str = authorization.removeprefix("Bearer ").strip()
    try:
        payload = jwt.decode(token_str, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        user_id: str = payload.get("sub", "")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token subject")
    except jwt.ExpiredSignatureError as err:
        raise HTTPException(status_code=401, detail="Token expired") from err
    except jwt.InvalidTokenError as err:
        raise HTTPException(status_code=401, detail="Invalid token") from err

    # Parse and validate requested scopes.
    requested_scopes = [s.strip() for s in scope.split() if s.strip()]
    allowed = client["allowed_scopes"]
    invalid_scopes = [s for s in requested_scopes if s not in allowed]
    if invalid_scopes:
        raise HTTPException(
            status_code=400,
            detail=f"Requested scopes not allowed: {invalid_scopes}",
        )

    code = auth_code_store.create(
        client_id=client_id,
        user_id=user_id,
        scopes=requested_scopes,
        redirect_uri=redirect_uri,
    )
    logger.info(
        "OAuth2 authorization code issued: client_id=%s user_id=%s",
        client_id,
        user_id,
    )
    response: dict[str, Any] = {"code": code}
    if state is not None:
        response["state"] = state
    return response


@router.post("/oauth/token")
async def oauth_token(
    grant_type: str = Form(...),
    client_id: str = Form(...),
    client_secret: str = Form(...),
    code: str | None = Form(default=None),
    redirect_uri: str | None = Form(default=None),
    scope: str | None = Form(default=None),
) -> dict[str, Any]:
    """OAuth2 token endpoint supporting authorization_code and client_credentials grants.

    Accepts ``application/x-www-form-urlencoded`` body (standard OAuth2).
    Returns a JWT access token with ``token_type='oauth2'`` in the payload.
    """
    # Validate the client credentials regardless of grant type.
    if not oauth_client_registry.validate_secret(client_id, client_secret):
        logger.warning(
            "OAuth2 token request failed: invalid client credentials client_id=%s", client_id
        )
        raise HTTPException(status_code=401, detail="Invalid client credentials")

    client = oauth_client_registry.get(client_id)
    if client is None:
        raise HTTPException(status_code=401, detail="Invalid client credentials")

    if grant_type not in client["grant_types"]:
        raise HTTPException(
            status_code=400,
            detail=f"grant_type '{grant_type}' not allowed for this client",
        )

    if grant_type == "authorization_code":
        if not code or not redirect_uri:
            raise HTTPException(
                status_code=400,
                detail="code and redirect_uri are required for authorization_code grant",
            )
        record = auth_code_store.consume(code)
        if record is None:
            logger.warning(
                "OAuth2 token request: invalid/expired/used code client_id=%s", client_id
            )
            raise HTTPException(
                status_code=400, detail="Invalid, expired, or already-used authorization code"
            )
        if record["client_id"] != client_id:
            raise HTTPException(
                status_code=400, detail="Authorization code was issued to a different client"
            )
        if record["redirect_uri"] != redirect_uri:
            raise HTTPException(
                status_code=400, detail="redirect_uri does not match authorization request"
            )

        token_scope = " ".join(record["scopes"])
        access_token = _create_oauth2_token(
            sub=record["user_id"],
            client_id=client_id,
            scope=token_scope,
        )
        logger.info(
            "OAuth2 authorization_code token issued: client_id=%s user_id=%s",
            client_id,
            record["user_id"],
        )
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "expires_in": _OAUTH2_TOKEN_EXPIRE_SECONDS,
            "scope": token_scope,
        }

    if grant_type == "client_credentials":
        requested_scope = scope or " ".join(client["allowed_scopes"])
        requested_scopes = [s.strip() for s in requested_scope.split() if s.strip()]
        invalid_scopes = [s for s in requested_scopes if s not in client["allowed_scopes"]]
        if invalid_scopes:
            raise HTTPException(
                status_code=400,
                detail=f"Requested scopes not allowed: {invalid_scopes}",
            )
        token_scope = " ".join(requested_scopes)
        access_token = _create_oauth2_token(
            sub=client_id,
            client_id=client_id,
            scope=token_scope,
        )
        logger.info(
            "OAuth2 client_credentials token issued: client_id=%s scope=%s",
            client_id,
            token_scope,
        )
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "expires_in": _OAUTH2_TOKEN_EXPIRE_SECONDS,
            "scope": token_scope,
        }

    raise HTTPException(status_code=400, detail=f"Unsupported grant_type: {grant_type}")


@router.post("/oauth/introspect")
async def oauth_introspect(
    token: str = Form(...),
) -> dict[str, Any]:
    """OAuth2 token introspection endpoint (RFC 7662).

    Decodes the JWT and returns active=True with claims if valid, or
    active=False if the token is invalid, expired, or not an OAuth2 token.
    """
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        logger.debug("OAuth2 introspect: token expired")
        return {"active": False}
    except jwt.InvalidTokenError as err:
        logger.debug("OAuth2 introspect: invalid token: %s", err)
        return {"active": False}

    if payload.get("token_type") != "oauth2":
        return {"active": False}

    result: dict[str, Any] = {
        "active": True,
        "sub": payload.get("sub"),
        "client_id": payload.get("oauth2_client_id"),
        "scope": payload.get("scope"),
        "exp": payload.get("exp"),
    }
    return result


@router.post(
    "/workflows/{flow_id}/branch-validate",
    status_code=200,
    tags=["Branching"],
)
async def branch_validate(flow_id: str, body: _BranchValidateRequest):
    """Validate a branch condition tree without executing it.

    Performs a structural walk of the condition dict to detect:
    - Unsupported node types
    - Missing required keys (``type`` on every node; ``source`` / ``operation``
      on leaf nodes; ``conditions`` on and/or nodes; ``condition`` on not nodes)
    - Unsupported leaf operation names

    Returns ``{"valid": true}`` on success or ``{"valid": false, "error": "<message>"}``
    on failure.
    """

    def _validate_node(node: Any, path: str) -> str | None:
        """Return an error message string, or None if the node is valid."""
        if not isinstance(node, dict):
            return f"{path}: expected a dict, got {type(node).__name__}"

        node_type = node.get("type")
        if node_type is None:
            return f"{path}: missing required key 'type'"

        if node_type == "leaf":
            if "source" not in node:
                return f"{path}: leaf node missing 'source'"
            if "operation" not in node:
                return f"{path}: leaf node missing 'operation'"
            op = node["operation"]
            if op not in CompoundConditionEvaluator.SUPPORTED_OPERATIONS:
                return (
                    f"{path}: unsupported operation {op!r}. "
                    f"Supported: {', '.join(sorted(CompoundConditionEvaluator.SUPPORTED_OPERATIONS))}"
                )
            return None

        if node_type in ("and", "or"):
            sub = node.get("conditions")
            if sub is None:
                return f"{path}: '{node_type}' node missing 'conditions'"
            if not isinstance(sub, list):
                return f"{path}: 'conditions' must be a list"
            for idx, child in enumerate(sub):
                err = _validate_node(child, f"{path}.conditions[{idx}]")
                if err:
                    return err
            return None

        if node_type == "not":
            inner = node.get("condition")
            if inner is None:
                return f"{path}: 'not' node missing 'condition'"
            return _validate_node(inner, f"{path}.condition")

        return f"{path}: unsupported condition node type {node_type!r}"

    error_msg = _validate_node(body.condition, "condition")
    if error_msg:
        return {"valid": False, "error": error_msg}
    return {"valid": True, "error": None}


@router.get(
    "/branch/operations",
    status_code=200,
    tags=["Branching"],
)
async def branch_operations():
    """List all supported leaf operations for compound condition builders.

    Returns a list of operation objects, each with:
    - ``name``: The operation identifier used in condition trees
    - ``description``: Human-readable explanation of what the operation checks
    """
    operations = [
        {"name": name, "description": desc}
        for name, desc in sorted(CompoundConditionEvaluator.SUPPORTED_OPERATIONS.items())
    ]
    return {"operations": operations, "total": len(operations)}

