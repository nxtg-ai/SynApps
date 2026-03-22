"""
Monitoring router for SynApps Orchestrator.

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

import httpx
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
    API_VERSION,
    API_VERSION_DATE,
    API_SUPPORTED_VERSIONS,
    API_SUNSET_GRACE_DAYS,
    APP_START_TIME,
    _VALID_SHARE_ROLES,
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
    WorkflowAnalyticsDashboard,
    WorkflowAssertionEngine,
    CostCalculator,
    WorkflowProfilerService,
    AnalyticsService,
    WorkflowHealthService,
)

logger = logging.getLogger("orchestrator")


# Orchestrator and applet_registry are populated by main.py after all modules load.
# They start as None/empty and are set via _setup_router_globals() in main.py.
Orchestrator = None  # type: ignore[assignment]
applet_registry: dict = {}

# These are populated by main.py after module load (to avoid circular imports)
metrics = None  # type: ignore[assignment]
app_config = None  # type: ignore[assignment]
env_path = None  # type: ignore[assignment]
flow_version_registry = None  # type: ignore[assignment]
LLMProviderRegistry = None  # type: ignore[assignment]
ImageProviderRegistry = None  # type: ignore[assignment]
probe_connector = None  # type: ignore[assignment]
probe_all_connectors = None  # type: ignore[assignment]
_health_payload = None  # type: ignore[assignment]
emit_event = None  # type: ignore[assignment]
WorkflowImportService = None  # type: ignore[assignment]

analytics_service = AnalyticsService()
workflow_health_service = WorkflowHealthService()

router = APIRouter()

# Provider auto-discovery registry
from synapps.providers.llm import ProviderRegistry as SynappsProviderRegistry  # noqa: E402

SynappsProviderRegistry.auto_discover()
_synapps_registry = SynappsProviderRegistry()
for _pname in SynappsProviderRegistry.list_global():
    _synapps_registry.register(SynappsProviderRegistry.get_global(_pname))


# ============================================================
# Monitoring Routes
# ============================================================

@router.get("/applets", tags=["Applets"])
async def list_applets(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """List all registered applets with their metadata (paginated)."""
    result = []

    for applet_type, applet_class in applet_registry.items():
        result.append({"type": applet_type, **applet_class.get_metadata()})

    applets_dir = os.path.join(os.path.dirname(__file__), "..", "applets")
    if os.path.exists(applets_dir):
        for applet_dir in os.listdir(applets_dir):
            if applet_dir.startswith("__") or applet_dir.startswith("."):
                continue
            if applet_dir not in [a["type"] for a in result]:
                try:
                    applet = await Orchestrator.load_applet(applet_dir)
                    result.append({"type": applet_dir, **applet.get_metadata()})
                except Exception as e:
                    logger.warning(f"Failed to load applet '{applet_dir}': {e}")

    return paginate(result, page, page_size)


@router.get("/llm/providers", tags=["Providers"])
async def list_llm_providers(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """List supported LLM providers and model catalogs."""
    providers = [provider.model_dump() for provider in LLMProviderRegistry.list_providers()]
    return paginate(providers, page, page_size)


@router.get("/image/providers", tags=["Providers"])
async def list_image_providers(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """List supported image generation providers and model catalogs."""
    providers = [provider.model_dump() for provider in ImageProviderRegistry.list_providers()]
    return paginate(providers, page, page_size)


@router.get("/providers", tags=["Providers"])
async def list_discovered_providers(
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """List all auto-discovered LLM providers with capabilities and status."""
    providers = _synapps_registry.all_providers_info()
    return {
        "providers": providers,
        "total": len(providers),
        "discovery": "filesystem",
    }


@router.get("/providers/{name}/health", tags=["Providers"])
async def provider_health_check(
    name: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Run a health check on a specific discovered provider."""
    try:
        health = _synapps_registry.provider_health(name)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"Provider '{name}' not found") from exc
    return health


@router.get("/connectors/health", tags=["Health"])
async def connectors_health(
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Run health probes on all connectors and return per-connector status.

    Each connector is probed with a lightweight HTTP HEAD ping (5 s timeout).
    Results are cached for 30 s to avoid hammering upstream on every request.

    Dashboard statuses follow these thresholds:
    - *healthy*:  avg latency < 500 ms AND 0 errors in last 5 min
    - *degraded*: avg latency < 2000 ms OR < 5 errors in last 5 min
    - *down*:     timeout OR ≥ 5 errors in last 5 min
    """
    results = await probe_all_connectors()
    summary = {
        "healthy": sum(1 for r in results if r["dashboard_status"] == ConnectorStatus.HEALTHY),
        "degraded": sum(1 for r in results if r["dashboard_status"] == ConnectorStatus.DEGRADED),
        "down": sum(1 for r in results if r["dashboard_status"] == ConnectorStatus.DOWN),
        "disabled": sum(1 for r in results if r["status"] == ConnectorStatus.DISABLED),
    }
    return {
        "connectors": results,
        "summary": summary,
        "total": len(results),
        "disable_threshold": connector_health.disable_threshold,
    }


@router.post("/connectors/{connector_name}/probe", tags=["Health"])
async def probe_single_connector(
    connector_name: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Probe a single connector and return its health state."""
    probe_result = await probe_connector(connector_name)
    state = connector_health.get_dashboard_status(connector_name)
    return {
        **probe_result,
        "status": state["status"],
        "dashboard_status": state["dashboard_status"],
        "consecutive_failures": state["consecutive_failures"],
        "total_probes": state["total_probes"],
        "last_check": state["last_check"],
        "last_success": state["last_success"],
        "avg_latency_ms": state["avg_latency_ms"],
        "error_count_5m": state["error_count_5m"],
    }


@router.get("/health", tags=["Health"])
async def health_v1():
    """Service health check — returns status, version, and uptime."""
    return _health_payload()


@router.get("/dashboard/portfolio", tags=["Dashboard"])
async def portfolio_dashboard(
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Portfolio dogfood dashboard — template statuses, provider registry, health."""

    # 1. Templates
    templates = _discover_yaml_templates()
    template_statuses = []
    for tmpl in templates:
        last_run = await _get_last_run_for_flow_name(tmpl["name"])
        template_statuses.append(
            {
                **tmpl,
                "last_run": last_run,
            }
        )

    # 2. Provider registry
    provider_status = []
    for info in LLMProviderRegistry.list_providers():
        d = info.model_dump()
        provider_status.append(
            {
                "name": d["name"],
                "configured": d["configured"],
                "reason": d.get("reason", ""),
                "model_count": len(d.get("models", [])),
            }
        )

    # 3. Health
    uptime_seconds = max(0, int(time.time() - APP_START_TIME))
    db_ok = True
    try:
        async with get_db_session() as session:
            await session.execute(select(1))
    except Exception:
        db_ok = False

    return {
        "templates": template_statuses,
        "template_count": len(template_statuses),
        "providers": provider_status,
        "provider_count": len(provider_status),
        "health": {
            "status": "healthy" if db_ok else "degraded",
            "database": "reachable" if db_ok else "unreachable",
            "uptime_seconds": uptime_seconds,
            "version": API_VERSION,
        },
    }


@router.get("/health/detailed", tags=["Health"])
async def health_detailed(
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Detailed health check with database, providers, and last template run."""
    uptime_seconds = max(0, int(time.time() - APP_START_TIME))

    # Database
    db_ok = True
    try:
        async with get_db_session() as session:
            await session.execute(select(1))
    except Exception:
        db_ok = False

    # Providers
    provider_checks = []
    for info in LLMProviderRegistry.list_providers():
        d = info.model_dump()
        provider_checks.append(
            {
                "name": d["name"],
                "connected": d["configured"],
                "reason": d.get("reason", ""),
            }
        )

    # Last template execution
    snap = metrics.snapshot()
    last_run_at = snap["last_template_run_at"]

    overall = "ok"
    if not db_ok:
        overall = "down"
    elif not any(p["connected"] for p in provider_checks):
        overall = "degraded"

    return {
        "status": overall,
        "uptime_seconds": uptime_seconds,
        "version": API_VERSION,
        "database": {"reachable": db_ok},
        "providers": provider_checks,
        "last_template_run_at": last_run_at,
    }


@router.get("/metrics", tags=["Health"])
async def get_metrics(
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """In-memory request metrics: counts, error rate, response time, provider usage."""
    return metrics.snapshot()


@router.get("/config", tags=["Health"])
async def get_config(
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Return current server configuration with secrets redacted."""
    config = app_config.to_dict(redact_secrets=True)
    config["_validation_errors"] = app_config.validate()
    config["_env_file_loaded"] = str(env_path) if env_path.exists() else None
    return config


@router.get("/requests/failed", tags=["Debug"], response_model=list[_FailedRequestSummary])
async def list_failed_requests(
    limit: int = Query(50, ge=1, le=500),
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """List recent failed requests with timestamp, upstream, status code, and error."""
    entries = failed_request_store.list_recent(limit=limit)
    return [
        {
            "request_id": e["request_id"],
            "timestamp": e["timestamp"],
            "method": e["method"],
            "path": e["path"],
            "response_status": e["response_status"],
            "duration_ms": e["duration_ms"],
            "client_ip": e.get("client_ip", "unknown"),
        }
        for e in entries
    ]


@router.post("/requests/{request_id}/replay", tags=["Debug"])
async def replay_request(
    request_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Re-send the original failed request internally.

    The replayed request does **not** count toward the consumer's rate limit
    (it is an admin/debug action).  Returns the new upstream response.
    """
    entry = failed_request_store.get(request_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Failed request not found")

    method = entry["method"]
    path = entry["path"]
    req_headers = dict(entry.get("request_headers", {}))
    req_body = entry.get("request_body", "")

    # Tag replayed requests so middleware can identify them
    req_headers["X-Replay"] = "true"
    req_headers["X-Original-Request-ID"] = request_id
    # Remove hop-by-hop / host headers to avoid confusion
    for hdr in ("host", "content-length", "transfer-encoding"):
        req_headers.pop(hdr, None)

    # Replay by making an internal HTTP call to ourselves
    base_url = f"http://127.0.0.1:{app_config.backend_port}"
    try:
        async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as client:
            resp = await client.request(
                method=method,
                url=path if path.startswith("/") else f"/{path}",
                headers=req_headers,
                content=req_body.encode("utf-8") if req_body else None,
            )
    except (httpx.HTTPError, OSError, Exception) as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Replay failed: {exc}",
        ) from exc

    try:
        resp_json = resp.json()
    except Exception:
        resp_json = resp.text

    return {
        "original_request_id": request_id,
        "replay_status": resp.status_code,
        "replay_headers": dict(resp.headers),
        "replay_body": resp_json,
    }


@router.get("/requests/{request_id}/debug", tags=["Debug"])
async def debug_request(
    request_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Return the full request chain for a failed request.

    Includes request headers, body, response headers, response body, and
    timing.  Sensitive headers (Authorization, API keys, cookies) are
    **redacted** in the output.
    """
    entry = failed_request_store.get(request_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Failed request not found")

    return {
        "request_id": entry["request_id"],
        "timestamp": entry["timestamp"],
        "method": entry["method"],
        "path": entry["path"],
        "duration_ms": entry["duration_ms"],
        "client_ip": entry.get("client_ip", "unknown"),
        "request": {
            "headers": FailedRequestStore.redact_headers(entry.get("request_headers", {})),
            "body": entry.get("request_body", ""),
        },
        "response": {
            "status": entry["response_status"],
            "headers": FailedRequestStore.redact_headers(entry.get("response_headers", {})),
            "body": entry.get("response_body", ""),
        },
    }


@router.get("/usage/me", tags=["Usage"])
async def get_my_execution_usage(
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict[str, Any]:
    """Return current authenticated user's execution quota status (D-13).

    Shows executions consumed this hour and this month, limits, and remaining quota.
    """
    return execution_quota_store.get_usage(current_user.get("email", ""))


@router.get("/usage", tags=["Usage"])
async def list_usage(
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Per-API-key usage breakdown (requests today/week/month, bandwidth, error rate)."""
    return usage_tracker.all_usage()


@router.get("/usage/{key_id:path}", tags=["Usage"])
async def get_key_usage(
    key_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Detailed usage for a specific consumer (by endpoint, by hour)."""
    rec = usage_tracker.get_usage(key_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="No usage data for this key")
    return {
        "key_id": key_id,
        "requests_today": rec["requests_today"],
        "requests_week": rec["requests_week"],
        "requests_month": rec["requests_month"],
        "errors_month": rec["errors_month"],
        "bandwidth_bytes": rec["bandwidth_bytes"],
        "error_rate_pct": round(rec["errors_month"] / rec["requests_month"] * 100, 2)
        if rec["requests_month"] > 0
        else 0.0,
        "quota": rec.get("quota"),
        "by_endpoint": rec.get("by_endpoint", {}),
        "by_hour": rec.get("by_hour", {}),
        "last_request_at": rec.get("last_request_at"),
    }


@router.get("/quotas", tags=["Usage"])
async def list_quotas(
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Show all keys with current usage vs quota, percentage consumed."""
    return usage_tracker.all_quotas()


@router.put("/quotas/{key_id:path}", tags=["Usage"])
async def set_quota(
    key_id: str,
    body: _SetQuotaRequest,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Set or clear the monthly request quota for a consumer key."""
    usage_tracker.set_quota(key_id, body.monthly_limit)
    return {
        "key_id": key_id,
        "monthly_limit": body.monthly_limit,
        "status": "quota_set" if body.monthly_limit else "quota_cleared",
    }


@router.get("/version", tags=["Health"])
async def get_api_version():
    """Return current API version, supported versions, and deprecated endpoints."""
    return {
        "api_version": API_VERSION_DATE,
        "app_version": API_VERSION,
        "supported_versions": API_SUPPORTED_VERSIONS,
        "deprecated_endpoints": deprecation_registry.all_deprecated(),
        "sunset_grace_days": API_SUNSET_GRACE_DAYS,
    }


@router.get("/analytics/workflows", tags=["Analytics"])
async def get_workflow_analytics(
    flow_id: str | None = Query(None, description="Filter analytics to a specific flow ID."),
):
    """Per-flow execution analytics: run counts, success/error rates, avg duration."""
    workflows = await analytics_service.get_workflow_analytics(flow_id=flow_id)
    return {"workflows": workflows, "total_flows": len(workflows)}


@router.get("/analytics/nodes", tags=["Analytics"])
async def get_node_analytics(
    flow_id: str | None = Query(None, description="Filter analytics to a specific flow ID."),
):
    """Per-node execution analytics: execution counts, success/error rates, avg duration."""
    nodes = await analytics_service.get_node_analytics(flow_id=flow_id)
    return {"nodes": nodes, "total_nodes": len(nodes)}


@router.get("/analytics/dashboard", tags=["Analytics"])
async def get_analytics_dashboard(
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Aggregated execution insights dashboard (N-33).

    Returns:
    - top_workflows: top 10 by execution count
    - avg_duration_by_node_type: average duration per node type (ms)
    - error_rate_trends: hourly error rates for the last 24 h
    - peak_usage_hours: executions per hour-of-day (0–23)
    """
    top_workflows, avg_durations, trends, peak_hours = await asyncio.gather(
        WorkflowAnalyticsDashboard.top_workflows(),
        WorkflowAnalyticsDashboard.avg_duration_by_node_type(),
        WorkflowAnalyticsDashboard.error_rate_trends(),
        WorkflowAnalyticsDashboard.peak_usage_hours(),
    )

    # N-41 cost summary: aggregate across all tracked executions.
    all_records = cost_tracker_store.all_records()
    cost_total_usd = sum(r.total_usd for r in all_records)
    run_count = len(all_records)
    avg_usd_per_run = (cost_total_usd / run_count) if run_count > 0 else 0.0

    # Top costly flows: aggregate by flow_id, return sorted descending.
    flow_totals: dict[str, float] = {}
    for rec in all_records:
        flow_totals[rec.flow_id] = flow_totals.get(rec.flow_id, 0.0) + rec.total_usd
    top_costly_flows = sorted(
        [{"flow_id": fid, "total_usd": total} for fid, total in flow_totals.items()],
        key=lambda x: x["total_usd"],
        reverse=True,
    )[:10]

    return {
        "top_workflows": top_workflows,
        "avg_duration_by_node_type": avg_durations,
        "error_rate_trends": trends,
        "peak_usage_hours": peak_hours,
        "cost_summary": {
            "total_usd": cost_total_usd,
            "avg_usd_per_run": avg_usd_per_run,
            "top_costly_flows": top_costly_flows,
        },
    }


@router.get("/analytics/dashboard/export.csv", tags=["Analytics"])
async def export_analytics_dashboard_csv(
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Download analytics dashboard data as CSV (N-33).

    Returns a multi-section CSV with top workflows and node duration data.
    """
    import csv
    import io

    top_workflows = await WorkflowAnalyticsDashboard.top_workflows(limit=50)
    avg_durations = await WorkflowAnalyticsDashboard.avg_duration_by_node_type()

    buf = io.StringIO()
    writer = csv.writer(buf)

    # Section 1: top workflows
    writer.writerow(["# Top Workflows"])
    writer.writerow(
        [
            "flow_id",
            "run_count",
            "success_count",
            "error_count",
            "success_rate",
            "error_rate",
            "avg_duration_seconds",
        ]
    )
    for wf in top_workflows:
        writer.writerow(
            [
                wf["flow_id"],
                wf["run_count"],
                wf["success_count"],
                wf["error_count"],
                wf["success_rate"],
                wf["error_rate"],
                wf.get("avg_duration_seconds", ""),
            ]
        )

    writer.writerow([])  # blank separator

    # Section 2: avg duration by node type
    writer.writerow(["# Avg Duration by Node Type (ms)"])
    writer.writerow(["node_type", "avg_duration_ms", "sample_count"])
    for nd in avg_durations:
        writer.writerow([nd["node_type"], nd["avg_duration_ms"], nd["sample_count"]])

    from fastapi.responses import StreamingResponse

    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=analytics_dashboard.csv"},
    )


@router.get("/monitoring/workflows", tags=["Monitoring"])
async def get_monitoring_workflows(
    flow_id: str | None = Query(None, description="Filter to a specific flow ID."),
    window_hours: int = Query(24, ge=1, le=168, description="Look-back window in hours."),
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict[str, Any]:
    """Health summary for all workflows (or a specific flow) in the given window.

    Also evaluates all enabled alert rules against the current health data.
    """
    health = await workflow_health_service.get_health(flow_id=flow_id, window_hours=window_hours)
    alert_engine.evaluate(health)
    return {"workflows": health, "total": len(health), "window_hours": window_hours}


@router.get("/monitoring/workflows/{flow_id}", tags=["Monitoring"])
async def get_monitoring_workflow_detail(
    flow_id: str,
    window_hours: int = Query(24, ge=1, le=168, description="Look-back window in hours."),
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict[str, Any]:
    """Health detail for a single workflow.

    Returns 404 if the flow has no runs in the requested window.
    """
    health = await workflow_health_service.get_health(flow_id=flow_id, window_hours=window_hours)
    if not health:
        raise HTTPException(
            status_code=404,
            detail=f"No runs found for flow {flow_id!r} in the last {window_hours}h.",
        )
    alert_engine.evaluate(health)
    return {"workflow": health[0], "window_hours": window_hours}


@router.post("/monitoring/alerts", tags=["Monitoring"], status_code=201)
async def create_alert_rule(
    body: dict[str, Any],
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict[str, Any]:
    """Create a new alert rule.

    Required body fields: metric, operator, threshold, action_type.
    Optional: workflow_id (default "*"), window_minutes (default 60), action_config (default {}).
    """
    metric = body.get("metric")
    operator = body.get("operator")
    threshold = body.get("threshold")
    action_type = body.get("action_type")

    if metric not in AlertRuleStore.VALID_METRICS:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid metric {metric!r}. Must be one of {sorted(AlertRuleStore.VALID_METRICS)}.",
        )
    if operator not in AlertRuleStore.VALID_OPERATORS:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid operator {operator!r}. Must be one of {sorted(AlertRuleStore.VALID_OPERATORS)}.",
        )
    if threshold is None:
        raise HTTPException(status_code=422, detail="'threshold' is required.")
    try:
        float(threshold)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="'threshold' must be numeric.") from exc
    if action_type not in AlertRuleStore.VALID_ACTION_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid action_type {action_type!r}. Must be one of {sorted(AlertRuleStore.VALID_ACTION_TYPES)}.",
        )

    rule = alert_rule_store.create(body)
    return {"rule": rule}


@router.get("/monitoring/alerts", tags=["Monitoring"])
async def list_alert_rules(
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict[str, Any]:
    """List all alert rules."""
    rules = alert_rule_store.list_all()
    return {"rules": rules, "total": len(rules)}


@router.put("/monitoring/alerts/{rule_id}", tags=["Monitoring"])
async def update_alert_rule(
    rule_id: str,
    body: dict[str, Any],
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict[str, Any]:
    """Partially update an alert rule (threshold, operator, enabled, action_config)."""
    if "operator" in body and body["operator"] not in AlertRuleStore.VALID_OPERATORS:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid operator {body['operator']!r}.",
        )
    updated = alert_rule_store.update(rule_id, body)
    if updated is None:
        raise HTTPException(status_code=404, detail=f"Alert rule {rule_id!r} not found.")
    return {"rule": updated}


@router.delete("/monitoring/alerts/{rule_id}", tags=["Monitoring"], status_code=204)
async def delete_alert_rule(
    rule_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> None:
    """Delete an alert rule by id."""
    deleted = alert_rule_store.delete(rule_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Alert rule {rule_id!r} not found.")


@router.post("/workflows/{flow_id}/test", tags=["Testing"])
async def run_workflow_test(
    flow_id: str,
    body: WorkflowTestRequest,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict[str, Any]:
    """Run a workflow with mock inputs and evaluate assertions against the results (N-34).

    Each assertion is a string in the form ``path op value``, e.g.:
    - ``status == success``
    - ``output.text == Hello``
    - ``output.count > 3``
    - ``results.llm1.output.score >= 0.8``
    - ``type(output.items) == list``
    """
    flow = await FlowRepository.get_by_id(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")

    flow = await Orchestrator.auto_migrate_legacy_nodes(flow, persist=True)

    # Execute the flow with mock inputs and wait for completion (max 60 s)
    run_id = await Orchestrator.execute_flow(flow, body.input)
    deadline = time.time() + 60.0
    run: dict[str, Any] | None = None
    while time.time() < deadline:
        await asyncio.sleep(0.1)
        run = await WorkflowRunRepository.get_by_run_id(run_id)
        if run and run.get("status") in ("success", "error"):
            break

    if run is None:
        run = {"status": "unknown", "results": {}}

    # Evaluate assertions
    assertion_results = [WorkflowAssertionEngine.evaluate(a, run) for a in body.assertions]
    passed = all(r["passed"] for r in assertion_results)

    # Determine current flow version (if versioning store has one)
    versions = flow_version_registry.list_versions(flow_id)
    version_id = versions[-1]["version_id"] if versions else None

    result_record = {
        "id": str(uuid.uuid4()),
        "workflow_id": flow_id,
        "run_id": run_id,
        "suite_name": body.suite_name,
        "version_id": version_id,
        "passed": passed,
        "assertion_count": len(body.assertions),
        "pass_count": sum(1 for r in assertion_results if r["passed"]),
        "fail_count": sum(1 for r in assertion_results if not r["passed"]),
        "assertion_results": assertion_results,
        "run_status": run.get("status"),
        "timestamp": time.time(),
    }

    if body.save_result:
        workflow_test_store.record_result(flow_id, result_record)

    return result_record


@router.get("/workflows/{flow_id}/test-history", tags=["Testing"])
async def get_workflow_test_history(
    flow_id: str,
    limit: int = Query(50, ge=1, le=500),
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict[str, Any]:
    """Return test run history for a workflow (N-34)."""
    flow = await FlowRepository.get_by_id(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
    history = workflow_test_store.get_history(flow_id, limit=limit)
    return {
        "workflow_id": flow_id,
        "total": len(history),
        "history": history,
    }


@router.post("/workflows/{flow_id}/test-suites", tags=["Testing"])
async def save_test_suite(
    flow_id: str,
    body: dict[str, Any],
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict[str, Any]:
    """Save a named test suite definition for a workflow (N-34)."""
    flow = await FlowRepository.get_by_id(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
    body.setdefault("name", "Unnamed Suite")
    return workflow_test_store.save_suite(flow_id, body)


@router.get("/workflows/{flow_id}/test-suites", tags=["Testing"])
async def list_test_suites(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict[str, Any]:
    """List saved test suite definitions for a workflow (N-34)."""
    flow = await FlowRepository.get_by_id(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
    suites = workflow_test_store.list_suites(flow_id)
    return {"workflow_id": flow_id, "total": len(suites), "suites": suites}


@router.get("/workflows/{flow_id}/variables", tags=["Variables"])
async def get_workflow_variables(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Return all variables defined for a workflow."""
    flow = await FlowRepository.get_by_id(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
    variables = workflow_variable_store.get(flow_id)
    return {"flow_id": flow_id, "variables": variables, "count": len(variables)}


@router.put("/workflows/{flow_id}/variables", tags=["Variables"])
async def put_workflow_variables(
    flow_id: str,
    body: dict[str, Any],
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Set (replace) all variables for a workflow.

    Body must be a flat JSON object of ``{key: value}`` pairs.
    """
    flow = await FlowRepository.get_by_id(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
    if not isinstance(body, dict):
        raise HTTPException(status_code=422, detail="Body must be a JSON object")
    workflow_variable_store.set(flow_id, body)
    return {
        "flow_id": flow_id,
        "variables": workflow_variable_store.get(flow_id),
        "count": len(body),
    }


@router.get("/workflows/{flow_id}/secrets", tags=["Secrets"])
async def get_workflow_secrets(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Return masked secret names for a workflow (values are always ``***``)."""
    flow = await FlowRepository.get_by_id(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
    masked = workflow_secret_store.get_masked(flow_id)
    return {"flow_id": flow_id, "secrets": masked, "count": len(masked)}


@router.put("/workflows/{flow_id}/secrets", tags=["Secrets"])
async def put_workflow_secrets(
    flow_id: str,
    body: dict[str, str],
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Set (replace) all secrets for a workflow.

    Body must be ``{name: plaintext_value}`` pairs. Values are encrypted at
    rest and never returned in plaintext via the API.
    """
    flow = await FlowRepository.get_by_id(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
    if not isinstance(body, dict):
        raise HTTPException(status_code=422, detail="Body must be a JSON object")
    workflow_secret_store.set(flow_id, body)
    masked = workflow_secret_store.get_masked(flow_id)
    return {"flow_id": flow_id, "secrets": masked, "count": len(body)}


@router.get("/workflows/{flow_id}/notifications", tags=["Notifications"])
async def get_workflow_notifications(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Return the notification configuration for a workflow."""
    flow = await FlowRepository.get_by_id(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
    config = notification_store.get(flow_id)
    return {"flow_id": flow_id, "config": config}


@router.put("/workflows/{flow_id}/notifications", tags=["Notifications"])
async def put_workflow_notifications(
    flow_id: str,
    body: dict[str, Any],
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Set the notification configuration for a workflow.

    Body shape:
        {
            "on_complete": [{"type": "email"|"slack"|"webhook", ...}],
            "on_failure":  [{"type": "email"|"slack"|"webhook", ...}]
        }
    """
    flow = await FlowRepository.get_by_id(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
    if not isinstance(body, dict):
        raise HTTPException(status_code=422, detail="Body must be a JSON object")
    # Validate handler types
    valid_types = {"email", "slack", "webhook"}
    for event_key in ("on_complete", "on_failure"):
        handlers = body.get(event_key, [])
        if not isinstance(handlers, list):
            raise HTTPException(status_code=422, detail=f"{event_key} must be a list")
        for h in handlers:
            if not isinstance(h, dict) or "type" not in h:
                raise HTTPException(status_code=422, detail="Each handler must have a 'type' field")
            if h["type"] not in valid_types:
                raise HTTPException(
                    status_code=422,
                    detail=f"Unknown handler type '{h['type']}'. Valid: {sorted(valid_types)}",
                )
    notification_store.set(flow_id, body)
    return {"flow_id": flow_id, "config": notification_store.get(flow_id)}


@router.post(
    "/workflows/{flow_id}/nodes/{node_id}/comments",
    status_code=201,
    tags=["Comments"],
)
async def create_node_comment(
    flow_id: str,
    node_id: str,
    body: NodeCommentRequest,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict[str, Any]:
    """Add a threaded comment to a specific node in a workflow."""
    flow = await FlowRepository.get_by_id(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
    author = current_user.get("email", "unknown")
    comment = node_comment_store.add(
        flow_id, node_id, author=author, content=body.content, parent_id=body.parent_id
    )
    activity_feed_store.record(
        flow_id,
        actor=author,
        action="node_commented",
        detail=f"Comment on node '{node_id}': {body.content[:80]}",
    )
    return comment


@router.get("/workflows/{flow_id}/nodes/{node_id}/comments", tags=["Comments"])
async def list_node_comments(
    flow_id: str,
    node_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict[str, Any]:
    """Return all comments on a specific node."""
    flow = await FlowRepository.get_by_id(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
    comments = node_comment_store.get(flow_id, node_id)
    return {"flow_id": flow_id, "node_id": node_id, "count": len(comments), "comments": comments}


@router.get("/workflows/{flow_id}/comments", tags=["Comments"])
async def list_flow_comments(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict[str, Any]:
    """Return all comments across all nodes in a flow."""
    flow = await FlowRepository.get_by_id(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
    comments = node_comment_store.get_all_for_flow(flow_id)
    return {"flow_id": flow_id, "count": len(comments), "comments": comments}


@router.get("/workflows/{flow_id}/activity", tags=["Activity"])
async def get_workflow_activity(
    flow_id: str,
    limit: int = Query(50, ge=1, le=200),
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict[str, Any]:
    """Return the activity feed for a workflow — edits, runs, and comments."""
    flow = await FlowRepository.get_by_id(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
    events = activity_feed_store.get(flow_id, limit=limit)
    return {"flow_id": flow_id, "count": len(events), "events": events}


@router.post("/workflows/{flow_id}/share", status_code=200, tags=["Permissions"])
async def share_workflow(
    flow_id: str,
    body: ShareWorkflowRequest,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict[str, Any]:
    """Grant a user viewer or editor access to a workflow. Only the owner can share."""
    if body.role not in _VALID_SHARE_ROLES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid role '{body.role}'. Valid: {sorted(_VALID_SHARE_ROLES)}",
        )
    flow = await FlowRepository.get_by_id(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
    _check_flow_permission(flow_id, current_user.get("email", ""), "owner")
    workflow_permission_store.grant(flow_id, body.user_id, body.role)
    audit_log_store.record(
        current_user.get("email", "unknown"),
        "permission_granted",
        "flow",
        flow_id,
        detail=f"Granted '{body.role}' to {body.user_id}.",
    )
    return {
        "flow_id": flow_id,
        "shared_with": body.user_id,
        "role": body.role,
        "permissions": workflow_permission_store.get_permissions(flow_id),
    }


@router.delete(
    "/workflows/{flow_id}/share/{target_user_id}",
    status_code=200,
    tags=["Permissions"],
)
async def revoke_workflow_share(
    flow_id: str,
    target_user_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict[str, Any]:
    """Revoke a user's access to a workflow. Only the owner can revoke."""
    flow = await FlowRepository.get_by_id(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
    _check_flow_permission(flow_id, current_user.get("email", ""), "owner")
    workflow_permission_store.revoke(flow_id, target_user_id)
    audit_log_store.record(
        current_user.get("email", "unknown"),
        "permission_revoked",
        "flow",
        flow_id,
        detail=f"Revoked access for {target_user_id}.",
    )
    return {
        "flow_id": flow_id,
        "revoked": target_user_id,
        "permissions": workflow_permission_store.get_permissions(flow_id),
    }


@router.get("/workflows/{flow_id}/permissions", tags=["Permissions"])
async def get_workflow_permissions(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict[str, Any]:
    """Return the ownership and access grants for a workflow."""
    flow = await FlowRepository.get_by_id(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
    _check_flow_permission(flow_id, current_user.get("email", ""), "viewer")
    perms = workflow_permission_store.get_permissions(flow_id)
    return {"flow_id": flow_id, "permissions": perms}


@router.get("/audit", tags=["Audit"])
async def get_audit_trail(
    actor: str | None = Query(None, description="Filter by actor email"),
    action: str | None = Query(None, description="Filter by action name"),
    resource_type: str | None = Query(None, description="Filter by resource type"),
    resource_id: str | None = Query(None, description="Filter by resource ID"),
    since: str | None = Query(None, description="ISO timestamp lower bound"),
    until: str | None = Query(None, description="ISO timestamp upper bound"),
    limit: int = Query(100, ge=1, le=1000, description="Max entries to return"),
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict[str, Any]:
    """Return audit log entries with optional filters.

    Performs lazy retention purge on each call (entries older than the
    configured retention window are removed before querying).
    """
    audit_log_store.purge_old()
    entries = audit_log_store.query(
        actor=actor,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        since=since,
        until=until,
        limit=limit,
    )
    return {"count": len(entries), "entries": entries}


@router.post("/workflows/import", status_code=200, tags=["Workflows"])
async def import_workflow(
    body: ImportWorkflowRequest,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict[str, Any]:
    """Import a workflow from an external tool (n8n or Zapier) and convert to SynApps format.

    Returns the converted SynApps workflow JSON.  Pass ``save=true`` to also
    persist the result as a new flow (caller becomes the owner).
    """
    workflow, detected_format = WorkflowImportService.convert(body.data, fmt=body.format)
    result: dict[str, Any] = {
        "format": detected_format,
        "workflow": workflow,
        "node_count": len(workflow.get("nodes", [])),
        "edge_count": len(workflow.get("edges", [])),
    }
    if body.save:
        await FlowRepository.save(workflow)
        user_email = current_user.get("email", "")
        if user_email and user_email != "anonymous@local":
            workflow_permission_store.set_owner(workflow["id"], user_email)
        audit_log_store.record(
            user_email or "anonymous",
            "workflow_created",
            "flow",
            workflow["id"],
            detail=f"Imported from {detected_format}: '{workflow.get('name', workflow['id'])}'.",
        )
        result["saved"] = True
        result["flow_id"] = workflow["id"]
    return result


@router.post("/flows/{flow_id}/estimate-cost", tags=["Flows"])
async def estimate_cost_flow(
    flow_id: str,
    body: FlowEstimateCostRequest | None = None,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Estimate execution cost for a saved flow."""
    flow = await FlowRepository.get_by_id(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
    nodes = flow.get("nodes", [])
    iterations = body.foreach_iterations if body else 10
    return CostCalculator.estimate(nodes, iterations)


@router.post("/plugins", status_code=201, tags=["Plugins"])
async def register_plugin(
    body: RegisterPluginRequest,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict[str, Any]:
    """Register a new marketplace plugin (authenticated)."""
    manifest = PluginManifest(**body.model_dump())
    try:
        plugin_id = plugin_registry.register(manifest)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"plugin_id": plugin_id, "message": f"Plugin '{body.name}' registered"}


@router.get("/plugins", tags=["Plugins"])
async def list_plugins() -> dict[str, Any]:
    """List all registered plugins (public)."""
    plugins = plugin_registry.list_all()
    return {"plugins": plugins, "total": len(plugins)}


@router.get("/plugins/{plugin_id}", tags=["Plugins"])
async def get_plugin(plugin_id: str) -> dict[str, Any]:
    """Get details of a specific plugin (public)."""
    entry = plugin_registry.get(plugin_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Plugin not found")
    return entry


@router.delete("/plugins/{plugin_id}", status_code=204, tags=["Plugins"])
async def delete_plugin(
    plugin_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> None:
    """Unregister a plugin (authenticated)."""
    if not plugin_registry.unregister(plugin_id):
        raise HTTPException(status_code=404, detail="Plugin not found")


@router.get("/plugins/{plugin_id}/schema", tags=["Plugins"])
async def get_plugin_schema(plugin_id: str) -> dict[str, Any]:
    """Return the config_schema for a plugin (public)."""
    entry = plugin_registry.get(plugin_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Plugin not found")
    return {"plugin_id": plugin_id, "config_schema": entry["manifest"]["config_schema"]}


@router.post("/plugins/{plugin_id}/install", tags=["Plugins"])
async def install_plugin(
    plugin_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict[str, Any]:
    """Increment the install count for a plugin (authenticated)."""
    entry = plugin_registry.get(plugin_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Plugin not found")
    plugin_registry.increment_install_count(plugin_id)
    updated = plugin_registry.get(plugin_id)
    return {
        "plugin_id": plugin_id,
        "node_type": entry["manifest"]["node_type"],
        "message": "Plugin installed",
        "install_count": updated["install_count"] if updated else 0,
    }

