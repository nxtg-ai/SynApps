"""
Collaboration router for SynApps Orchestrator.

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

