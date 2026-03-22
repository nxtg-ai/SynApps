"""
Request body models and shared base classes for SynApps Orchestrator.

Extracted from main.py (M-1 router decomposition Step 2).
"""
import math
import statistics
import time
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import httpx

from pydantic import BaseModel, ConfigDict, Field, field_validator

from apps.orchestrator.models import (
    APIKeyCreateRequestModel,
    AuthLoginRequestModel,
    AuthRefreshRequestModel,
    AuthRegisterRequestModel,
)
from apps.orchestrator.stores import (
    FlowDescriptionStore,
    FlowShareStore,
    execution_log_store,
    marketplace_registry,
    featured_store,
    credit_ledger,
    rating_store,
    review_store,
    reply_store,
)
from apps.orchestrator.helpers import KNOWN_NODE_TYPES, MARKETPLACE_CATEGORIES, HISTORY_VALID_STATUSES, _WORKFLOW_PATTERNS
from apps.orchestrator.repositories import WorkflowRunRepository

def paginate(items: list, page: int, page_size: int) -> dict:
    """Apply offset-based pagination to a list of items."""
    total = len(items)
    total_pages = math.ceil(total / page_size) if page_size > 0 else 0
    start = (page - 1) * page_size
    end = start + page_size
    return {
        "items": items[start:end],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }


class StrictRequestModel(BaseModel):
    """Base model for API request payloads that rejects unknown fields."""

    model_config = ConfigDict(extra="forbid")


class FlowNodeRequest(StrictRequestModel):
    """Strictly validated flow node for API requests."""

    id: str = Field(..., min_length=1, max_length=200)
    type: str = Field(..., min_length=1, max_length=100)
    position: dict[str, float]
    data: dict[str, Any] = Field(default_factory=dict)

    @field_validator("position")
    @classmethod
    def validate_position(cls, v):
        if "x" not in v or "y" not in v:
            raise ValueError("Position must contain 'x' and 'y' keys")
        return v


class FlowEdgeRequest(StrictRequestModel):
    """Strictly validated flow edge for API requests."""

    id: str = Field(..., min_length=1, max_length=200)
    source: str = Field(..., min_length=1)
    target: str = Field(..., min_length=1)
    animated: bool = False


class CreateFlowRequest(StrictRequestModel):
    """Strictly validated flow creation/update request."""

    id: str | None = Field(None, max_length=200)
    name: str = Field(..., min_length=1, max_length=200)
    nodes: list[FlowNodeRequest] = Field(default_factory=list)
    edges: list[FlowEdgeRequest] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v):
        if not v.strip():
            raise ValueError("Flow name cannot be blank")
        return v.strip()

    @field_validator("id")
    @classmethod
    def id_not_blank(cls, v):
        if v is not None and v.strip() == "":
            return None  # Treat blank as None so a UUID is auto-generated
        return v


class RunFlowRequest(StrictRequestModel):
    """Strictly validated request body for running a flow."""

    input: dict[str, Any] = Field(default_factory=dict, description="Input data for the workflow")


class FlowCloneRequest(BaseModel):
    """Optional body for cloning a flow.  All fields are optional."""

    name: str | None = Field(None, max_length=200, description="Name for the cloned flow. Defaults to 'Copy of {original_name}'.")


class FlowTagRequest(BaseModel):
    """Body for adding a tag to a flow."""

    tag: str = Field(..., min_length=1, max_length=64, description="Tag to add (alphanumeric, hyphens, underscores).")


class RerunFlowRequest(StrictRequestModel):
    """Request body for re-running a previous flow execution with input overrides."""

    input: dict[str, Any] = Field(
        default_factory=dict,
        description="Input overrides for the re-run",
    )
    merge_with_original_input: bool = Field(
        default=True,
        description="When true, merge overrides on top of the source run input",
    )


class AISuggestRequest(StrictRequestModel):
    """Strictly validated request body for AI suggestions."""

    prompt: str = Field(
        ..., min_length=1, max_length=5000, description="The prompt for AI suggestion"
    )
    context: str | None = Field(
        None, max_length=10000, description="Optional context for the suggestion"
    )


class WorkflowTestRequest(StrictRequestModel):
    """Request body for POST /workflows/{id}/test."""

    assertions: list[str] = Field(..., description="Assertion strings to evaluate.")
    input: dict[str, Any] = Field(default_factory=dict, description="Mock input for the workflow.")
    save_result: bool = Field(True, description="Whether to persist this test run in history.")
    suite_name: str | None = Field(None, description="Optional label for this test run.")


class AuthRegisterRequestStrict(AuthRegisterRequestModel):
    """Strict request model that rejects unknown registration fields."""

    model_config = ConfigDict(extra="forbid")


class AuthLoginRequestStrict(AuthLoginRequestModel):
    """Strict request model that rejects unknown login fields."""

    model_config = ConfigDict(extra="forbid")


class AuthRefreshRequestStrict(AuthRefreshRequestModel):
    """Strict request model that rejects unknown refresh-token fields."""

    model_config = ConfigDict(extra="forbid")


class APIKeyCreateRequestStrict(APIKeyCreateRequestModel):
    """Strict request model that rejects unknown API-key creation fields."""

    model_config = ConfigDict(extra="forbid")


class RollbackRequest(BaseModel):
    """Request body for the rollback endpoint -- optional reason text."""

    reason: str = Field("", max_length=500)


# ============================================================
# Inline request models extracted from main.py
# ============================================================

import hmac
import os
import re
from fastapi import Header, HTTPException
from apps.orchestrator.webhooks.manager import WEBHOOK_EVENTS


SYNAPPS_MASTER_KEY = os.environ.get("SYNAPPS_MASTER_KEY", "")
ADMIN_KEY_SCOPES = frozenset({"read", "write", "admin"})

# Flow configuration constants
_TIMEOUT_MIN = 1
_TIMEOUT_MAX = 3600
_RETRY_MAX_RETRIES_MAX = 10
_RETRY_DELAY_MAX = 300  # seconds
_RETRY_BACKOFF_MAX = 10.0
_CONCURRENCY_MIN = 1
_CONCURRENCY_MAX = 100
_SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
_ALIAS_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,61}[a-z0-9]$")
_ANN_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
_DEFAULT_ANN_COLOR = "#FFFF99"


def require_master_key(
    x_api_key: str | None = Header(None, alias="X-API-Key"),
    authorization: str | None = Header(None, alias="Authorization"),
) -> str:
    """Dependency that requires the SYNAPPS_MASTER_KEY for admin operations."""
    import sys
    _main = sys.modules.get("apps.orchestrator.main")
    master = getattr(_main, "SYNAPPS_MASTER_KEY", SYNAPPS_MASTER_KEY) if _main else SYNAPPS_MASTER_KEY
    if not master:
        raise HTTPException(
            status_code=503,
            detail="Admin API not configured — SYNAPPS_MASTER_KEY environment variable not set",
        )

    provided = None
    if x_api_key:
        provided = x_api_key.strip()
    elif authorization:
        auth_text = authorization.strip()
        if auth_text.lower().startswith("bearer "):
            provided = auth_text[7:].strip()

    if not provided or not hmac.compare_digest(provided, master):
        raise HTTPException(status_code=403, detail="Invalid or missing master key")

    return provided




class ValidateTemplateRequest(BaseModel):
    """Request body for template validation."""

    model_config = ConfigDict(extra="allow")
    name: str | None = None
    nodes: list[dict[str, Any]] | None = None
    edges: list[dict[str, Any]] | None = None



class RegisterWebhookTriggerRequest(StrictRequestModel):
    """Request body for registering an inbound webhook trigger (N-19)."""

    flow_id: str = Field(..., min_length=1, description="Flow to trigger on receipt")
    secret: str | None = Field(
        None,
        description="Optional HMAC-SHA256 signing secret. "
        "When set, callers must send X-Webhook-Signature: sha256=<hex>",
    )



class CreateScheduleRequest(StrictRequestModel):
    """Request body for creating a new workflow schedule."""

    flow_id: str = Field(..., min_length=1, description="ID of the flow to schedule.")
    cron_expr: str = Field(
        ...,
        min_length=9,
        description="Standard 5-field cron expression (e.g. '0 9 * * 1-5').",
    )
    name: str | None = Field(None, max_length=200, description="Human-readable schedule name.")
    enabled: bool = Field(True, description="Whether the schedule is active immediately.")



class UpdateScheduleRequest(StrictRequestModel):
    """Partial-update request for an existing schedule."""

    cron_expr: str | None = Field(None, min_length=9)
    name: str | None = Field(None, max_length=200)
    enabled: bool | None = None



class ReplayDLQRequest(StrictRequestModel):
    """Optional overrides when replaying a dead-lettered run."""

    input_override: dict[str, Any] | None = Field(
        None,
        description="Override the original input data for the replay.",
    )



class FlowUpdateRequest(StrictRequestModel):
    """Request body for updating (replacing) an existing flow."""

    name: str | None = Field(None, max_length=200)
    nodes: list[dict[str, Any]] = Field(default_factory=list)
    edges: list[dict[str, Any]] = Field(default_factory=list)



class RegisterWebhookRequest(StrictRequestModel):
    """Request body for webhook registration."""

    url: str = Field(..., min_length=1, description="Delivery URL")
    events: list[str] = Field(..., min_length=1, description="Event names to subscribe to")
    secret: str | None = Field(None, description="HMAC-SHA256 signing secret")

    @field_validator("events")
    @classmethod
    def events_valid(cls, v):
        invalid = [e for e in v if e not in WEBHOOK_EVENTS]
        if invalid:
            raise ValueError(f"Invalid events: {invalid}. Valid: {sorted(WEBHOOK_EVENTS)}")
        return v



class TemplateImportRequest(BaseModel):
    """Request body for importing a template."""

    model_config = ConfigDict(extra="allow")
    id: str | None = Field(None, description="Template ID. Auto-generated if omitted.")
    name: str = Field(..., min_length=1, max_length=200)
    version: Any | None = Field(
        None,
        description="Semver version string (e.g. '1.2.0'). Auto-incremented patch if omitted. "
        "Integer values from legacy exports are accepted but ignored.",
    )
    description: str | None = Field("", max_length=1000)
    tags: list[str] | None = Field(default_factory=list)
    nodes: list[dict[str, Any]] = Field(default_factory=list)
    edges: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] | None = Field(default_factory=dict)

    @field_validator("version")
    @classmethod
    def validate_version(cls, v):
        if v is None or isinstance(v, int):
            return v  # None or legacy integer — ignored by registry
        if isinstance(v, str):
            if not _SEMVER_RE.match(v):
                raise ValueError("version must be semver format: major.minor.patch (e.g. '1.2.0')")
            return v
        raise ValueError("version must be a semver string or null")



class PublishTemplateRequest(StrictRequestModel):
    """Request body for publishing a flow as a marketplace template."""

    flow_id: str = Field(..., description="ID of the existing flow to publish as a template")
    name: str = Field(..., min_length=1, max_length=200, description="Template display name")
    description: str = Field("", max_length=2000, description="Template description")
    category: str = Field(
        ..., description="One of: notification, data-sync, monitoring, content, devops"
    )
    author: str = Field("anonymous", min_length=1, max_length=100, description="Template author")
    version: str | None = Field(
        None,
        description="Semver version string (e.g. '1.0.0'). Auto-generated if omitted.",
    )

    @field_validator("category")
    @classmethod
    def validate_category(cls, v):
        if v.lower() not in MARKETPLACE_CATEGORIES:
            raise ValueError(
                f"Invalid category '{v}'. Must be one of: {', '.join(sorted(MARKETPLACE_CATEGORIES))}"
            )
        return v.lower()



class InstantiateTemplateRequest(StrictRequestModel):
    """Request body for instantiating a flow from a template."""

    flow_name: str | None = Field(
        None, max_length=200, description="Name for the new flow. Defaults to template name."
    )
    connector_overrides: dict[str, Any] = Field(
        default_factory=dict,
        description="Map of node IDs to connector config overrides.",
    )



class RunAsyncRequest(BaseModel):
    """Request body for async template execution."""

    model_config = ConfigDict(extra="forbid")
    input: dict[str, Any] = Field(default_factory=dict, description="Input data for the workflow")



class PublishMarketplaceRequest(StrictRequestModel):
    """Request body for publishing a flow as a marketplace listing."""

    flow_id: str = Field(..., description="ID of the existing flow to publish")
    name: str = Field(..., min_length=1, max_length=200, description="Listing display name")
    description: str = Field("", max_length=2000, description="Listing description")
    category: str = Field(
        ..., description="One of: notification, data-sync, monitoring, content, devops"
    )
    tags: list[str] = Field(default_factory=list, description="List of searchable tags")
    author: str = Field("anonymous", min_length=1, max_length=100, description="Author name")

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str) -> str:
        if v.lower() not in MARKETPLACE_CATEGORIES:
            raise ValueError(
                f"Invalid category '{v}'. Must be one of: {', '.join(sorted(MARKETPLACE_CATEGORIES))}"
            )
        return v.lower()



class InstallMarketplaceRequest(StrictRequestModel):
    """Request body for installing a marketplace listing."""

    flow_name: str | None = Field(
        None, max_length=200, description="Name for the new flow. Defaults to listing name."
    )
    connector_overrides: dict[str, Any] = Field(
        default_factory=dict,
        description="Map of node IDs to connector config overrides.",
    )



class AdminKeyCreateRequest(BaseModel):
    """Request body for creating an admin API key."""

    model_config = ConfigDict(extra="forbid")
    name: str = Field(..., min_length=1, max_length=128, description="Key name/label")
    scopes: list[str] | None = Field(None, description="Scopes: read, write, admin")
    rate_limit: int | None = Field(
        None,
        ge=1,
        le=10000,
        description="Custom rate limit (requests per minute). Omit to use tier default (60).",
    )

    @field_validator("scopes")
    @classmethod
    def scopes_valid(cls, v):
        if v is not None:
            invalid = [s for s in v if s not in ADMIN_KEY_SCOPES]
            if invalid:
                raise ValueError(f"Invalid scopes: {invalid}. Valid: {sorted(ADMIN_KEY_SCOPES)}")
        return v



class ManagedKeyCreateRequest(StrictRequestModel):
    """Request body for creating a managed API key."""

    name: str = Field(..., min_length=1, max_length=128)
    scopes: list[str] | None = Field(None, description="Scopes: read, write, admin")
    expires_in: int | None = Field(
        None,
        ge=60,
        le=31536000,
        description="Seconds until expiry (min 60s, max 1 year). Omit for no expiry.",
    )
    rate_limit: int | None = Field(
        None,
        ge=1,
        le=10000,
        description="Custom rate limit (requests/min).",
    )

    @field_validator("scopes")
    @classmethod
    def scopes_valid(cls, v):
        if v is not None:
            invalid = [s for s in v if s not in ADMIN_KEY_SCOPES]
            if invalid:
                raise ValueError(f"Invalid scopes: {invalid}. Valid: {sorted(ADMIN_KEY_SCOPES)}")
        return v



class RotateKeyRequest(StrictRequestModel):
    """Request body for rotating a managed API key."""

    grace_period: int = Field(
        86400,
        ge=0,
        le=604800,
        description="Seconds the old key stays valid (default 24h, max 7 days).",
    )



class ImportFlowRequest(BaseModel):
    """Request body for importing a flow."""

    model_config = ConfigDict(strict=False)

    synapps_version: str | None = None
    name: str = Field(..., min_length=1, max_length=200)
    nodes: list[dict[str, Any]] = Field(default_factory=list)
    edges: list[dict[str, Any]] = Field(default_factory=list)



class FlowLabelRequest(BaseModel):
    color: str = Field(..., pattern=r"^#[0-9a-fA-F]{6}$", description="CSS hex color, e.g. #ff5733")
    icon: str = Field("", max_length=2, description="Optional emoji/icon (max 2 chars)")



class FlowShareRequest(BaseModel):
    ttl: int = Field(
        FlowShareStore.DEFAULT_TTL,
        ge=60,
        le=604_800,
        description="Token lifetime in seconds (60s–7d). Default: 86400 (24h).",
    )



class FlowGroupRequest(BaseModel):
    group: str = Field(..., min_length=1, max_length=100)



class SaveAsTemplateRequest(BaseModel):
    name: str = Field("", description="Template name. Defaults to the flow name.")
    description: str = Field("", max_length=1000)
    tags: list[str] = Field(default_factory=list)
    version: str | None = Field(
        None,
        description="Explicit semver (e.g. '1.2.0'). Auto-increments patch if omitted.",
    )



class FlowLockRequest(BaseModel):
    reason: str = Field("", max_length=500)



class FlowMetadataSetRequest(BaseModel):
    metadata: dict[str, Any] = Field(default_factory=dict)



class FlowPriorityRequest(BaseModel):
    priority: str = Field(..., pattern=r"^(critical|high|medium|low)$")



class FlowDescriptionRequest(BaseModel):
    description: str = Field("", max_length=FlowDescriptionStore.MAX_LEN)



class BulkFlowRequest(BaseModel):
    flow_ids: list[str] = Field(..., min_length=1, max_length=100)



class BulkTagRequest(BaseModel):
    flow_ids: list[str] = Field(..., min_length=1, max_length=100)
    tag: str = Field(..., min_length=1, max_length=50)



class BulkMoveRequest(BaseModel):
    flow_ids: list[str] = Field(..., min_length=1, max_length=100)
    group: str = Field(..., min_length=1, max_length=100)



class BulkPriorityRequest(BaseModel):
    flow_ids: list[str] = Field(..., min_length=1, max_length=100)
    priority: str = Field(..., pattern=r"^(critical|high|medium|low)$")



class FlowExpiryRequest(BaseModel):
    expires_at: str = Field(
        ...,
        description="ISO-8601 datetime string (UTC). Flow will return 410 after this time.",
    )



class FlowAliasRequest(BaseModel):
    alias: str = Field(..., min_length=2, max_length=63, description="Lowercase slug (a-z, 0-9, hyphens).")

    @field_validator("alias")
    @classmethod
    def _validate_alias(cls, v: str) -> str:
        if not _ALIAS_PATTERN.match(v):
            raise ValueError(
                "alias must be 2–63 chars, lowercase alphanumeric and hyphens, "
                "starting and ending with alphanumeric"
            )
        return v



class FlowRateLimitRequest(BaseModel):
    max_runs: int = Field(..., ge=1, le=10000, description="Maximum runs allowed in the window.")
    window_seconds: int = Field(..., ge=1, le=86400, description="Sliding window duration in seconds (1s–24h).")



class FlowChangelogAddRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000, description="Changelog entry text.")
    type: str = Field(
        "note",
        pattern=r"^(note|fix|improvement|breaking|deployment)$",
        description="Entry type.",
    )



class FlowRunPresetRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200, description="Human-readable preset name.")
    description: str = Field("", max_length=1000, description="Optional description.")
    input: dict[str, Any] = Field(default_factory=dict, description="Input payload for the run.")



class FlowAnnotationCreateRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=2000)
    x: float = Field(..., description="Canvas x coordinate.")
    y: float = Field(..., description="Canvas y coordinate.")
    color: str = Field(_DEFAULT_ANN_COLOR, description="Hex color code, e.g. #FFFF99.")

    @field_validator("color")
    @classmethod
    def _validate_color(cls, v: str) -> str:
        if not _ANN_COLOR_RE.match(v):
            raise ValueError("color must be a 6-digit hex color, e.g. #FFFF99")
        return v.upper()



class FlowAnnotationPatchRequest(BaseModel):
    content: str | None = Field(None, min_length=1, max_length=2000)
    x: float | None = None
    y: float | None = None
    color: str | None = None

    @field_validator("color")
    @classmethod
    def _validate_color(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not _ANN_COLOR_RE.match(v):
            raise ValueError("color must be a 6-digit hex color, e.g. #FFFF99")
        return v.upper()



class FlowDependencyRequest(BaseModel):
    to_flow_id: str = Field(..., min_length=1, description="ID of the flow being depended upon.")
    label: str = Field("", max_length=200, description="Optional human-readable label.")



class FlowBookmarkRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200, description="Bookmark name.")
    viewport: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional canvas viewport state (e.g. {x, y, zoom}).",
    )



class FlowSnapshotRequest(BaseModel):
    label: str = Field(..., min_length=1, max_length=200, description="Human-readable snapshot label")
    nodes: list[Any] = Field(default_factory=list)
    edges: list[Any] = Field(default_factory=list)



class FlowReactionRequest(BaseModel):
    emoji: str = Field(..., min_length=1, max_length=10, description="Emoji character to react with")



class FlowScheduleUpsertRequest(BaseModel):
    cron: str = Field(..., min_length=1, max_length=100, description="5-field cron expression")
    enabled: bool = Field(default=True)
    label: str = Field(default="", max_length=200)



class FlowSchedulePatchRequest(BaseModel):
    cron: str | None = Field(default=None, max_length=100)
    enabled: bool | None = Field(default=None)
    label: str | None = Field(default=None, max_length=200)



class FlowWebhookCreateRequest(BaseModel):
    url: str = Field(..., min_length=1, max_length=500)
    events: list[str] = Field(..., min_length=1)
    secret: str = Field(default="", max_length=200)
    label: str = Field(default="", max_length=200)



class FlowWebhookPatchRequest(BaseModel):
    url: str | None = Field(default=None, max_length=500)
    events: list[str] | None = Field(default=None)
    enabled: bool | None = Field(default=None)
    label: str | None = Field(default=None, max_length=200)
    secret: str | None = Field(default=None, max_length=200)



class FlowCustomFieldDefineRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    type: str = Field(..., description="One of: string, number, boolean, date")



class FlowCustomFieldValueRequest(BaseModel):
    value: Any = Field(..., description="Value matching the field's declared type")



class FlowCollaboratorRequest(BaseModel):
    role: str = Field(..., description="One of: owner, editor, viewer, commenter")



class FlowEnvironmentSetRequest(BaseModel):
    config: dict[str, str] = Field(default_factory=dict, description="Key-value config overrides")



class FlowNotifPrefRequest(BaseModel):
    events: dict[str, bool] = Field(default_factory=dict)
    channels: list[str] = Field(default_factory=list)



class FlowTimeoutRequest(BaseModel):
    timeout_seconds: int = Field(..., ge=_TIMEOUT_MIN, le=_TIMEOUT_MAX)



class FlowRetryPolicyRequest(BaseModel):
    max_retries: int = Field(..., ge=0, le=_RETRY_MAX_RETRIES_MAX)
    retry_delay_s: int = Field(default=0, ge=0, le=_RETRY_DELAY_MAX)
    backoff_multiplier: float = Field(default=1.0, ge=1.0, le=_RETRY_BACKOFF_MAX)



class FlowConcurrencyRequest(BaseModel):
    max_concurrent: int = Field(..., ge=_CONCURRENCY_MIN, le=_CONCURRENCY_MAX)



class FlowInputSchemaRequest(BaseModel):
    schema_: dict[str, Any] = Field(..., alias="schema")

    model_config = {"populate_by_name": True}



class FlowOutputSchemaRequest(BaseModel):
    schema_: dict[str, Any] = Field(..., alias="schema")

    model_config = {"populate_by_name": True}



class FlowContactRequest(BaseModel):
    name: str = Field(default="", max_length=200)
    email: str = Field(default="", max_length=200)
    slack_handle: str = Field(default="", max_length=100)
    team: str = Field(default="", max_length=200)



class FlowCostConfigRequest(BaseModel):
    cost_per_run: float = Field(..., ge=0)
    currency: str = Field(default="USD")
    billing_note: str = Field(default="", max_length=500)



class FlowVisibilityRequest(BaseModel):
    visibility: str



class FlowVersionLockRequest(BaseModel):
    locked_version: str = Field(..., min_length=1, max_length=50)
    reason: str = Field(default="", max_length=500)



class FlowApprovalRequestBody(BaseModel):
    note: str = Field(default="", max_length=500)



class FlowApprovalReviewBody(BaseModel):
    comment: str = Field(default="", max_length=500)



class FlowTriggerConfigBody(BaseModel):
    trigger_type: str
    config: dict[str, Any] = Field(default_factory=dict)



class FlowRunRetentionBody(BaseModel):
    retain_days: int = Field(default=30, ge=1, le=365)
    max_runs: int | None = Field(default=None)



class FlowErrorAlertBody(BaseModel):
    emails: list[str] = Field(default_factory=list)
    slack_channels: list[str] = Field(default_factory=list)



class FlowOutputDestinationBody(BaseModel):
    dest_type: str
    config: dict[str, Any] = Field(default_factory=dict)



class FlowResourceLimitBody(BaseModel):
    memory_mb: int | None = Field(default=None, ge=1, le=16384)
    cpu_millicores: int | None = Field(default=None, ge=1, le=64000)
    timeout_s: int | None = Field(default=None, ge=1, le=86400)



class FlowAclGrantBody(BaseModel):
    permissions: list[str] = Field(default_factory=list)



class FlowExecutionModeBody(BaseModel):
    mode: str = Field(default="async")
    debug: bool = Field(default=False)



class FlowInputValidationBody(BaseModel):
    rules: list[dict[str, Any]] = Field(default_factory=list)
    strict: bool = Field(default=False)



class FlowCachingConfigBody(BaseModel):
    enabled: bool = Field(default=False)
    ttl_seconds: int = Field(default=300, ge=0, le=86400)
    key_fields: list[str] = Field(default_factory=list)



class FlowCircuitBreakerBody(BaseModel):
    enabled: bool = Field(default=True)
    failure_threshold: int = Field(default=5, ge=1, le=100)
    recovery_timeout_s: int = Field(default=60, ge=1, le=3600)



class FlowObservabilityConfigBody(BaseModel):
    traces_enabled: bool = Field(default=True)
    metrics_enabled: bool = Field(default=True)
    logs_enabled: bool = Field(default=True)
    sample_rate: float = Field(default=1.0, ge=0.0, le=1.0)



class FlowMaintenanceWindowBody(BaseModel):
    start: str = Field(..., description="ISO 8601 start datetime")
    end: str = Field(..., description="ISO 8601 end datetime")
    reason: str = Field(default="", max_length=500)



class FlowGeoRestrictionBody(BaseModel):
    mode: str = Field(default="none")
    regions: list[str] = Field(default_factory=list)



class FlowIpAllowlistBody(BaseModel):
    enabled: bool = Field(default=True)
    cidrs: list[str] = Field(default_factory=list)



class FlowDataClassificationBody(BaseModel):
    level: str = Field(..., description="public | internal | confidential | restricted")
    pii_flag: bool = False



class FlowNotificationChannelBody(BaseModel):
    type: str = Field(..., description="email | slack | webhook | pagerduty")
    target: str = Field(..., min_length=1, max_length=512)
    events: list[str] = Field(default_factory=list)
    enabled: bool = True



class FlowFeatureFlagBody(BaseModel):
    enabled: bool = True
    rollout_percentage: int = Field(default=100, ge=0, le=100)
    description: str = Field(default="", max_length=500)



class FlowExecutionHookBody(BaseModel):
    hook_type: str = Field(..., description="pre_execution | post_execution | on_error")
    url: str = Field(..., min_length=1, max_length=2048)
    event: str = Field(default="", max_length=100)
    enabled: bool = True
    headers: dict[str, str] = Field(default_factory=dict)

    @field_validator("hook_type")
    @classmethod
    def validate_hook_type(cls, v: str) -> str:
        allowed = {"pre_execution", "post_execution", "on_error"}
        if v not in allowed:
            raise ValueError(f"hook_type must be one of {sorted(allowed)}")
        return v



class FlowCustomDomainBody(BaseModel):
    domain: str = Field(..., min_length=3, max_length=253)
    enabled: bool = True



class FlowWebhookSigningBody(BaseModel):
    secret: str = Field(..., min_length=8, max_length=512)
    algorithm: str = Field(default="sha256")
    enabled: bool = True

    @field_validator("algorithm")
    @classmethod
    def validate_algorithm(cls, v: str) -> str:
        allowed = {"sha256", "sha512"}
        if v not in allowed:
            raise ValueError(f"algorithm must be one of {sorted(allowed)}")
        return v



class FlowAuditExportBody(BaseModel):
    format: str = Field(default="json", description="json | csv")
    from_ts: str | None = Field(default=None, max_length=50)
    to_ts: str | None = Field(default=None, max_length=50)

    @field_validator("format")
    @classmethod
    def validate_format(cls, v: str) -> str:
        allowed = {"json", "csv"}
        if v not in allowed:
            raise ValueError(f"format must be one of {sorted(allowed)}")
        return v



class FlowCollaboratorRoleBody(BaseModel):
    role: str = Field(..., description="viewer | editor | admin")

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        allowed = {"viewer", "editor", "admin"}
        if v not in allowed:
            raise ValueError(f"role must be one of {sorted(allowed)}")
        return v



class FlowInputMaskBody(BaseModel):
    rules: dict[str, str] = Field(default_factory=dict)
    enabled: bool = True



class FlowOutputTransformBody(BaseModel):
    expression: str = Field(..., min_length=1, max_length=2048)
    output_format: str = Field(default="json")
    enabled: bool = True

    @field_validator("output_format")
    @classmethod
    def validate_output_format(cls, v: str) -> str:
        allowed = {"json", "xml", "csv", "text"}
        if v not in allowed:
            raise ValueError(f"output_format must be one of {sorted(allowed)}")
        return v



class FlowDataRetentionBody(BaseModel):
    retention_days: int = Field(..., ge=1, le=3650)
    delete_on_expiry: bool = False
    anonymize_on_expiry: bool = False
    enabled: bool = True



class FlowAllowedOriginsBody(BaseModel):
    origins: list[str] = Field(default_factory=list, max_length=50)
    enabled: bool = True



class _FailedRequestSummary(BaseModel):
    request_id: str
    timestamp: float
    method: str
    path: str
    response_status: int
    duration_ms: float
    client_ip: str = "unknown"



class _SetQuotaRequest(BaseModel):
    monthly_limit: int | None = Field(
        None,
        ge=1,
        le=10_000_000,
        description="Monthly request limit. null = unlimited.",
    )



class AnalyticsService:
    """Stateless service for computing execution analytics over workflow runs."""

    @staticmethod
    async def get_workflow_analytics(flow_id: str | None = None) -> list[dict]:
        """Aggregate per-flow analytics from all workflow runs.

        Args:
            flow_id: Optional filter — if provided, only that flow is included.

        Returns:
            List of per-flow dicts sorted by last_run_at descending (nulls last).
        """
        all_runs = await WorkflowRunRepository.get_all()

        if flow_id is not None:
            all_runs = [r for r in all_runs if r.get("flow_id") == flow_id]

        # Group by flow_id
        groups: dict[str, list[dict]] = {}
        for run in all_runs:
            fid = run.get("flow_id") or ""
            groups.setdefault(fid, []).append(run)

        result = []
        for fid, runs in groups.items():
            run_count = len(runs)
            success_count = sum(1 for r in runs if r.get("status") == "success")
            error_count = sum(1 for r in runs if r.get("status") == "error")
            terminal_count = success_count + error_count
            success_rate = success_count / terminal_count if terminal_count > 0 else 0.0
            error_rate = error_count / terminal_count if terminal_count > 0 else 0.0

            durations = [
                r["end_time"] - r["start_time"]
                for r in runs
                if r.get("end_time") is not None and r.get("start_time") is not None
            ]
            avg_duration_seconds: float | None = (
                sum(durations) / len(durations) if durations else None
            )

            start_times = [r["start_time"] for r in runs if r.get("start_time") is not None]
            last_run_at: float | None = max(start_times) if start_times else None

            result.append(
                {
                    "flow_id": fid,
                    "run_count": run_count,
                    "success_count": success_count,
                    "error_count": error_count,
                    "success_rate": success_rate,
                    "error_rate": error_rate,
                    "avg_duration_seconds": avg_duration_seconds,
                    "last_run_at": last_run_at,
                }
            )

        result.sort(
            key=lambda x: x["last_run_at"] if x["last_run_at"] is not None else float("-inf"),
            reverse=True,
        )
        return result

    @staticmethod
    async def get_node_analytics(flow_id: str | None = None) -> list[dict]:
        """Aggregate per-node analytics from all workflow run results.

        Args:
            flow_id: Optional filter — if provided, only runs for that flow are included.

        Returns:
            List of per-node dicts sorted by execution_count descending.
        """
        all_runs = await WorkflowRunRepository.get_all()

        if flow_id is not None:
            all_runs = [r for r in all_runs if r.get("flow_id") == flow_id]

        # Aggregate per (node_id, flow_id)
        node_stats: dict[tuple[str, str], dict] = {}

        for run in all_runs:
            fid = run.get("flow_id") or ""
            results = run.get("results") or {}
            if not isinstance(results, dict):
                continue
            for nid, node_result in results.items():
                if not isinstance(node_result, dict):
                    continue
                key = (nid, fid)
                if key not in node_stats:
                    node_stats[key] = {
                        "node_id": nid,
                        "flow_id": fid,
                        "execution_count": 0,
                        "success_count": 0,
                        "error_count": 0,
                        "_durations": [],
                    }
                node_stats[key]["execution_count"] += 1
                status = node_result.get("status", "")
                if status == "success":
                    node_stats[key]["success_count"] += 1
                elif status == "error":
                    node_stats[key]["error_count"] += 1
                dur = node_result.get("duration_seconds")
                if dur is not None:
                    try:
                        node_stats[key]["_durations"].append(float(dur))
                    except (TypeError, ValueError):
                        pass  # Non-numeric duration — skip gracefully

        output = []
        for stats in node_stats.values():
            durations = stats.pop("_durations", [])
            success_count = stats["success_count"]
            error_count = stats["error_count"]
            terminal = success_count + error_count
            stats["success_rate"] = success_count / terminal if terminal > 0 else 0.0
            stats["avg_duration_seconds"] = sum(durations) / len(durations) if durations else None
            output.append(stats)

        output.sort(key=lambda x: x["execution_count"], reverse=True)
        return output



class WorkflowAnalyticsDashboard:
    """Aggregates execution data into dashboard metrics for N-33."""

    @staticmethod
    async def top_workflows(limit: int = 10) -> list[dict]:
        """Top workflows by execution count (descending)."""
        workflows = await AnalyticsService.get_workflow_analytics()
        workflows_sorted = sorted(workflows, key=lambda x: x["run_count"], reverse=True)
        return workflows_sorted[:limit]

    @staticmethod
    async def avg_duration_by_node_type() -> list[dict]:
        """Average execution duration (ms) grouped by node type from execution logs."""
        # Gather all log entries across all runs
        with execution_log_store._lock:
            all_logs = {
                run_id: list(entries) for run_id, entries in execution_log_store._logs.items()
            }
        type_durations: dict[str, list[float]] = {}
        for entries in all_logs.values():
            for entry in entries:
                node_type = entry.get("node_type")
                duration_ms = entry.get("duration_ms")
                if node_type and duration_ms is not None:
                    try:
                        type_durations.setdefault(node_type, []).append(float(duration_ms))
                    except (TypeError, ValueError):
                        pass  # non-numeric — skip gracefully
        result = []
        for node_type, durations in type_durations.items():
            result.append(
                {
                    "node_type": node_type,
                    "avg_duration_ms": sum(durations) / len(durations),
                    "sample_count": len(durations),
                }
            )
        result.sort(key=lambda x: x["avg_duration_ms"], reverse=True)
        return result

    @staticmethod
    async def error_rate_trends() -> list[dict]:
        """Error rate per hour for the last 24 hours (UTC).

        Returns a list of 24 dicts: {hour_label, total, errors, error_rate}.
        hour_label is ISO-8601 truncated to the hour, e.g. "2026-03-19T14".
        """

        now = datetime.now(UTC)
        # Build 24-hour bucket keys newest-first then reverse
        hour_keys: list[str] = []
        for i in range(23, -1, -1):
            ts = now - timedelta(hours=i)
            hour_keys.append(ts.strftime("%Y-%m-%dT%H"))

        buckets: dict[str, dict[str, int]] = {k: {"total": 0, "errors": 0} for k in hour_keys}

        all_runs = await WorkflowRunRepository.get_all()
        for run in all_runs:
            start_time = run.get("start_time")
            if start_time is None:
                continue
            try:
                ts = datetime.fromtimestamp(float(start_time), tz=UTC)
                key = ts.strftime("%Y-%m-%dT%H")
            except (TypeError, ValueError, OSError):
                continue
            if key not in buckets:
                continue
            buckets[key]["total"] += 1
            if run.get("status") == "error":
                buckets[key]["errors"] += 1

        result = []
        for key in hour_keys:
            b = buckets[key]
            total = b["total"]
            errors = b["errors"]
            result.append(
                {
                    "hour_label": key,
                    "total": total,
                    "errors": errors,
                    "error_rate": errors / total if total > 0 else 0.0,
                }
            )
        return result

    @staticmethod
    async def peak_usage_hours() -> list[dict]:
        """Total executions per hour-of-day (0–23) across all time."""

        hour_counts: dict[int, int] = {h: 0 for h in range(24)}
        all_runs = await WorkflowRunRepository.get_all()
        for run in all_runs:
            start_time = run.get("start_time")
            if start_time is None:
                continue
            try:
                ts = datetime.fromtimestamp(float(start_time), tz=UTC)
                hour_counts[ts.hour] += 1
            except (TypeError, ValueError, OSError):
                continue
        return [{"hour": h, "execution_count": c} for h, c in sorted(hour_counts.items())]



class WorkflowHealthService:
    """Compute per-workflow health metrics over a sliding time window."""

    @staticmethod
    async def get_health(
        flow_id: str | None = None,
        window_hours: int = 24,
    ) -> list[dict[str, Any]]:
        """Return health dicts for all workflows (or a single flow) within window.

        Args:
            flow_id: Optional — restrict results to a single flow.
            window_hours: How many hours back to consider (default 24).

        Returns:
            List of WorkflowHealth dicts sorted by last_run_at descending.
            Keys: flow_id, run_count, success_count, error_count,
                  success_rate, error_rate, avg_duration_seconds,
                  p95_duration_seconds, last_run_at, health_status.
        """
        all_runs = await WorkflowRunRepository.get_all()
        cutoff = time.time() - window_hours * 3600.0

        # Apply time-window filter
        windowed = [r for r in all_runs if (r.get("start_time") or 0.0) >= cutoff]

        # Optional single-flow filter
        if flow_id is not None:
            windowed = [r for r in windowed if r.get("flow_id") == flow_id]

        # Group by flow_id
        groups: dict[str, list[dict[str, Any]]] = {}
        for run in windowed:
            fid = run.get("flow_id") or ""
            groups.setdefault(fid, []).append(run)

        result: list[dict[str, Any]] = []
        for fid, runs in groups.items():
            run_count = len(runs)
            success_count = sum(1 for r in runs if r.get("status") == "success")
            error_count = sum(1 for r in runs if r.get("status") == "error")
            terminal_count = success_count + error_count
            success_rate = success_count / terminal_count if terminal_count > 0 else 0.0
            error_rate = error_count / terminal_count if terminal_count > 0 else 0.0

            durations = [
                float(r["end_time"]) - float(r["start_time"])
                for r in runs
                if r.get("end_time") is not None and r.get("start_time") is not None
            ]
            avg_duration_seconds: float | None = (
                sum(durations) / len(durations) if durations else None
            )
            p95_duration_seconds: float | None = None
            if durations:
                sorted_durations = sorted(durations)
                idx = max(0, int(math.ceil(0.95 * len(sorted_durations))) - 1)
                p95_duration_seconds = sorted_durations[idx]

            start_times = [float(r["start_time"]) for r in runs if r.get("start_time") is not None]
            last_run_at: float | None = max(start_times) if start_times else None

            if error_rate > 0.3:
                health_status = "critical"
            elif error_rate >= 0.1:
                health_status = "degraded"
            else:
                health_status = "healthy"

            result.append(
                {
                    "flow_id": fid,
                    "run_count": run_count,
                    "success_count": success_count,
                    "error_count": error_count,
                    "success_rate": success_rate,
                    "error_rate": error_rate,
                    "avg_duration_seconds": avg_duration_seconds,
                    "p95_duration_seconds": p95_duration_seconds,
                    "last_run_at": last_run_at,
                    "health_status": health_status,
                }
            )

        result.sort(
            key=lambda x: x["last_run_at"] if x["last_run_at"] is not None else float("-inf"),
            reverse=True,
        )
        return result



class WorkflowAssertionEngine:
    """Evaluates assertions against a workflow run result.

    Assertion string format:  ``path op value``

    Examples:
      ``status == success``
      ``output.text == Hello world``
      ``output.count > 5``
      ``results.node1.output.score >= 0.8``
      ``type(output.result) == list``

    Path resolution:
    - ``status``                  → run["status"]
    - ``output.X``                → looks for X in the output of the last
                                   non-terminal node (or any node with output X)
    - ``results.NODE.output.X``   → run["results"][NODE]["output"][X]
    - ``results.NODE.status``     → run["results"][NODE]["status"]
    """

    _OPS = {"==", "!=", ">", ">=", "<", "<="}
    _TYPE_MAP = {
        "str": str,
        "string": str,
        "int": int,
        "float": float,
        "number": (int, float),
        "bool": bool,
        "boolean": bool,
        "list": list,
        "array": list,
        "dict": dict,
        "object": dict,
        "null": type(None),
        "none": type(None),
    }

    @classmethod
    def evaluate(cls, assertion: str, run: dict[str, Any]) -> dict[str, Any]:
        """Evaluate a single assertion string against *run*.

        Returns a dict:
        {assertion, passed, actual, expected, op, error}
        """
        out: dict[str, Any] = {
            "assertion": assertion,
            "passed": False,
            "actual": None,
            "expected": None,
            "op": None,
            "error": None,
        }
        try:
            path, op, raw_expected = cls._parse(assertion)
            out["op"] = op
            actual = cls._resolve(path, run)
            out["actual"] = actual

            if op == "type==":
                type_name = raw_expected.strip().lower()
                expected_type = cls._TYPE_MAP.get(type_name)
                out["expected"] = type_name
                if expected_type is None:
                    out["error"] = f"Unknown type '{raw_expected}'"
                else:
                    out["passed"] = isinstance(actual, expected_type)
            else:
                expected = cls._coerce(raw_expected, actual)
                out["expected"] = expected
                out["passed"] = cls._compare(actual, op, expected)
        except Exception as exc:
            out["error"] = str(exc)
        return out

    @classmethod
    def _parse(cls, assertion: str) -> tuple[str, str, str]:
        """Split assertion into (path, op, raw_expected)."""
        # Handle type() assertions
        if assertion.startswith("type("):
            close = assertion.index(")")
            path = assertion[5:close]
            rest = assertion[close + 1 :].strip()
            if not rest.startswith("=="):
                raise ValueError("type() assertion must use == operator")
            return path.strip(), "type==", rest[2:].strip()

        # Try longest operators first to avoid partial matches
        for op in (">=", "<=", "!=", "==", ">", "<"):
            idx = assertion.find(op)
            if idx != -1:
                path = assertion[:idx].strip()
                value = assertion[idx + len(op) :].strip()
                # Strip surrounding quotes
                if (value.startswith('"') and value.endswith('"')) or (
                    value.startswith("'") and value.endswith("'")
                ):
                    value = value[1:-1]
                return path, op, value
        raise ValueError(f"Cannot parse assertion: {assertion!r}")

    @classmethod
    def _resolve(cls, path: str, run: dict[str, Any]) -> Any:
        """Resolve a dot-notation path against a run dict."""
        parts = path.split(".")

        # Top-level shortcuts
        if parts[0] == "status":
            return run.get("status")

        if parts[0] == "results" and len(parts) >= 2:
            results = run.get("results") or {}
            node_id = parts[1]
            node = results.get(node_id)
            if node is None:
                raise KeyError(f"Node '{node_id}' not found in results")
            return cls._dig(node, parts[2:])

        if parts[0] == "output":
            # Search all node results for the output key
            results = run.get("results") or {}
            output_key = parts[1] if len(parts) > 1 else None
            # Prefer last node result that has this output key
            candidate = None
            for node_result in results.values():
                if not isinstance(node_result, dict):
                    continue
                output = node_result.get("output")
                if not isinstance(output, dict):
                    continue
                if output_key is None or output_key in output:
                    candidate = output
            if candidate is None:
                raise KeyError(f"No node output found with key '{output_key}'")
            if output_key is None:
                return candidate
            return cls._dig(candidate, parts[1:])

        # Fallback: treat as top-level run key
        return cls._dig(run, parts)

    @classmethod
    def _dig(cls, obj: Any, parts: list[str]) -> Any:
        for part in parts:
            if isinstance(obj, dict):
                obj = obj[part]
            elif isinstance(obj, (list, tuple)):
                obj = obj[int(part)]
            else:
                raise KeyError(f"Cannot traverse '{part}' on {type(obj).__name__}")
        return obj

    @classmethod
    def _coerce(cls, raw: str, reference: Any) -> Any:
        """Coerce raw string to the same type as reference if possible."""
        if isinstance(reference, bool):
            return raw.lower() in ("true", "1", "yes")
        if isinstance(reference, int):
            try:
                return int(raw)
            except ValueError:
                pass
        if isinstance(reference, float):
            try:
                return float(raw)
            except ValueError:
                pass
        if raw.lower() in ("null", "none"):
            return None
        if raw.lower() == "true":
            return True
        if raw.lower() == "false":
            return False
        # Try numeric
        try:
            return int(raw)
        except ValueError:
            pass
        try:
            return float(raw)
        except ValueError:
            pass
        return raw

    @classmethod
    def _compare(cls, actual: Any, op: str, expected: Any) -> bool:
        try:
            if op == "==":
                return actual == expected
            if op == "!=":
                return actual != expected
            if op == ">":
                return actual > expected
            if op == ">=":
                return actual >= expected
            if op == "<":
                return actual < expected
            if op == "<=":
                return actual <= expected
        except TypeError:
            return False  # incomparable types — return safe error value
        return False



class NodeCommentRequest(BaseModel):
    content: str
    parent_id: str | None = None



class ShareWorkflowRequest(BaseModel):
    user_id: str
    role: str  # "viewer" or "editor"



class ImportWorkflowRequest(BaseModel):
    """Body for POST /workflows/import."""

    format: str | None = Field(
        None,
        description="Source format: 'n8n' or 'zapier'. Auto-detected if omitted.",
    )
    data: dict[str, Any] = Field(..., description="Raw workflow JSON from the source tool.")
    save: bool = Field(
        False, description="If true, persist the converted workflow to the flow store."
    )



class OAuthClientRegisterRequest(BaseModel):
    """Request body for registering a new OAuth2 client."""

    name: str = Field(..., min_length=1, max_length=200)
    redirect_uris: list[str] = Field(..., min_length=1)
    allowed_scopes: list[str] = Field(default=["read"])
    grant_types: list[str] = Field(default=["authorization_code"])



class _BranchValidateRequest(BaseModel):
    """Request body for branch condition validation."""

    condition: dict[str, Any]



class SubflowValidateRequest(BaseModel):
    """Request body for POST /subflows/validate."""

    parent_flow_id: str
    subflow_id: str



class CostEstimateRequest(BaseModel):
    """Request body for the estimate-cost endpoint."""

    input_data: dict = {}
    input_text: str = ""



class WorkflowDiffRequest(BaseModel):
    v1: dict  # full workflow JSON (nodes, edges)
    v2: dict  # full workflow JSON (nodes, edges)



class WorkflowVersionSaveRequest(BaseModel):
    snapshot: dict
    label: str = ""



class WorkflowProfilerService:
    """Aggregate node-level performance statistics from execution logs.

    Reads from the global execution_log_store to compute per-node latency
    percentiles across all runs, and per-execution bottleneck analysis.
    """

    def profile_workflow(self, flow_id: str) -> dict:  # noqa: ARG002
        """Profile all nodes seen across all execution runs.

        flow_id is accepted for API consistency; the current in-memory store
        has no flow_id index so statistics are aggregated across all runs.
        Only node_success/node_completed events with a non-None duration_ms
        are included.
        """
        node_durations: dict[str, list[float]] = {}
        with execution_log_store._lock:
            all_items = list(execution_log_store._logs.items())

        for _run_id, entries in all_items:
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                if entry.get("event") not in ("node_success", "node_completed"):
                    continue
                nid = entry.get("node_id")
                dur = entry.get("duration_ms")
                if nid and dur is not None:
                    try:
                        node_durations.setdefault(nid, []).append(float(dur))
                    except (TypeError, ValueError) as exc:
                        logger.warning("Profiler: invalid duration_ms for node %s: %s", nid, exc)

        nodes = []
        for nid, durations in node_durations.items():
            sorted_d = sorted(durations)
            n = len(sorted_d)

            def _pct(pct: float, _s: list = sorted_d, _n: int = n) -> float:
                idx = min(int(pct / 100.0 * _n), _n - 1)
                return _s[idx]

            nodes.append(
                {
                    "node_id": nid,
                    "run_count": n,
                    "avg_ms": sum(sorted_d) / n,
                    "p50_ms": _pct(50),
                    "p95_ms": _pct(95),
                    "p99_ms": _pct(99),
                    "min_ms": sorted_d[0],
                    "max_ms": sorted_d[-1],
                }
            )

        return {
            "flow_id": flow_id,
            "profiled_at": time.time(),
            "nodes": nodes,
            "total_node_types_profiled": len(nodes),
        }

    def profile_execution(self, execution_id: str) -> dict | None:
        """Profile a single execution run, identifying the bottleneck node.

        Returns None when no logs exist for execution_id (triggers 404 in API).
        """
        entries = execution_log_store.get(execution_id)
        if not entries:
            return None

        node_entries: list[dict] = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            if entry.get("event") not in ("node_success", "node_completed"):
                continue
            nid = entry.get("node_id")
            dur = entry.get("duration_ms")
            if nid and dur is not None:
                try:
                    node_entries.append(
                        {"node_id": nid, "duration_ms": float(dur), "is_bottleneck": False}
                    )
                except (TypeError, ValueError) as exc:
                    logger.warning(
                        "Profiler: invalid duration_ms for execution %s node %s: %s",
                        execution_id,
                        nid,
                        exc,
                    )

        if not node_entries:
            return {
                "execution_id": execution_id,
                "nodes": [],
                "total_duration_ms": 0.0,
                "bottleneck_node_id": None,
            }

        total_duration_ms = sum(e["duration_ms"] for e in node_entries)
        max_dur = max(e["duration_ms"] for e in node_entries)
        bottleneck_node_id: str | None = None
        for entry in node_entries:
            if entry["duration_ms"] == max_dur:
                entry["is_bottleneck"] = True
                bottleneck_node_id = entry["node_id"]
                break

        return {
            "execution_id": execution_id,
            "nodes": node_entries,
            "total_duration_ms": total_duration_ms,
            "bottleneck_node_id": bottleneck_node_id,
        }



class SuggestNextNodeRequest(BaseModel):
    """Request body for POST /ai-assist/suggest-next."""

    current_node_type: str
    existing_node_types: list[str] = []
    limit: int = 5



class AutocompleteRequest(BaseModel):
    """Request body for POST /ai-assist/autocomplete."""

    description: str
    limit: int = 5



class StartDebugRequest(BaseModel):
    """Body for POST /workflows/{flow_id}/debug."""

    input_data: dict[str, Any] = Field(default_factory=dict)
    breakpoints: list[str] = Field(default_factory=list)



class UpdateBreakpointsRequest(BaseModel):
    """Body for POST /debug/{session_id}/breakpoints."""

    breakpoints: list[str] = Field(
        ..., description="New breakpoint node IDs (replaces current set)."
    )



class RetryWebhookRequest(StrictRequestModel):
    """Request body for retrying a webhook delivery."""

    entry_id: str



class FeatureListingRequest(BaseModel):
    """Request body for featuring a marketplace listing."""

    model_config = ConfigDict(extra="forbid")
    blurb: str = Field("", max_length=200)



class MarketplaceSearchEngine:
    """Full-text search over marketplace listings.

    Indexes: name, description, tags (joined), author.
    Supports: keyword search (case-insensitive, partial match),
              autocomplete (prefix match on name + tags),
              filter by category, min_rating, min_installs.
    Scoring: name match = 3pts, tag match = 2pts, description match = 1pt, author match = 1pt.
    Results sorted by score desc, then install_count desc.
    """

    def search(
        self,
        listings: list[dict[str, Any]],
        q: str = "",
        category: str = "",
        min_rating: float = 0.0,
        min_installs: int = 0,
        sort_by: str = "relevance",
        limit: int = 12,
        offset: int = 0,
        tags: list[str] | None = None,
        rating_lookup: Any | None = None,
    ) -> dict[str, Any]:
        """Return {items, total, query, filters_applied}.

        Args:
            listings: Raw listing dicts from the registry.
            q: Keyword query string (case-insensitive, partial match).
            category: Filter by category (case-insensitive).
            min_rating: Minimum avg_rating to include.
            min_installs: Minimum install_count to include.
            sort_by: One of "relevance", "installs", "rating", "newest".
            limit: Max items to return.
            offset: Pagination offset.
            tags: Optional list of tags to filter by (any-match).
            rating_lookup: Optional RatingStore for rating-based filtering.
        """
        q_lower = q.strip().lower()
        results: list[dict[str, Any]] = []

        for listing in listings:
            # Category filter
            if category and listing.get("category", "").lower() != category.lower():
                continue

            # Tag filter (legacy support)
            if tags:
                tag_set = {t.lower() for t in tags}
                listing_tags = [t.lower() for t in listing.get("tags", [])]
                if not any(t in tag_set for t in listing_tags):
                    continue

            # Install count filter
            if listing.get("install_count", 0) < min_installs:
                continue

            # Rating filter
            if min_rating > 0.0 and rating_lookup is not None:
                lid = listing.get("listing_id", listing.get("id", ""))
                stats = rating_lookup.get_stats(lid)
                if stats["avg_rating"] < min_rating:
                    continue

            # Score against query
            score = self._score(listing, q_lower) if q_lower else 0.0

            # If query provided, only include matches
            if q_lower and score <= 0.0:
                continue

            results.append({**listing, "_score": score})

        # Sort
        if sort_by == "installs":
            results.sort(key=lambda x: (-x.get("install_count", 0), -x["_score"]))
        elif sort_by == "rating":
            # Sort by avg_rating from rating_lookup if available
            def _rating_key(item: dict[str, Any]) -> float:
                if rating_lookup is not None:
                    lid = item.get("listing_id", item.get("id", ""))
                    return rating_lookup.get_stats(lid)["avg_rating"]
                return 0.0

            results.sort(key=lambda x: (-_rating_key(x), -x["_score"]))
        elif sort_by == "newest":
            results.sort(key=lambda x: (-x.get("published_at", 0), -x["_score"]))
        else:
            # relevance (default)
            results.sort(key=lambda x: (-x["_score"], -x.get("install_count", 0)))

        total = len(results)
        page_items = results[offset : offset + limit]

        filters_applied: dict[str, Any] = {}
        if category:
            filters_applied["category"] = category
        if min_rating > 0.0:
            filters_applied["min_rating"] = min_rating
        if min_installs > 0:
            filters_applied["min_installs"] = min_installs
        if sort_by != "relevance":
            filters_applied["sort_by"] = sort_by
        if tags:
            filters_applied["tags"] = tags

        return {
            "items": page_items,
            "total": total,
            "query": q,
            "filters_applied": filters_applied,
        }

    def autocomplete(
        self,
        listings: list[dict[str, Any]],
        q: str,
        limit: int = 8,
    ) -> list[str]:
        """Return unique suggestion strings matching prefix of name or individual tags."""
        prefix = q.strip().lower()
        if not prefix:
            return []

        seen: set[str] = set()
        suggestions: list[str] = []

        for listing in listings:
            name = listing.get("name", "")
            if name.lower().startswith(prefix) and name.lower() not in seen:
                seen.add(name.lower())
                suggestions.append(name)

            for tag in listing.get("tags", []):
                if tag.lower().startswith(prefix) and tag.lower() not in seen:
                    seen.add(tag.lower())
                    suggestions.append(tag)

            if len(suggestions) >= limit:
                break

        return suggestions[:limit]

    def _score(self, listing: dict[str, Any], q_lower: str) -> float:
        """Score a single listing against the query.

        Scoring weights:
        - name match = 3 points per query word
        - tag match = 2 points per query word
        - description match = 1 point per query word
        - author match = 1 point per query word

        Multi-word queries: each word scored independently and summed.
        Exact full-query matches get a 2x bonus on the matching field.
        """
        if not q_lower:
            return 0.0

        words = q_lower.split()
        score = 0.0

        name_lower = listing.get("name", "").lower()
        desc_lower = listing.get("description", "").lower()
        tags_lower = " ".join(listing.get("tags", [])).lower()
        individual_tags = [t.lower() for t in listing.get("tags", [])]
        author_lower = listing.get("author", "").lower()

        for word in words:
            if word in name_lower:
                score += 3.0
            if any(word in t for t in individual_tags):
                score += 2.0
            if word in desc_lower:
                score += 1.0
            if word in author_lower:
                score += 1.0

        # Exact full-query bonus
        if q_lower in name_lower:
            score += 3.0
        if q_lower in tags_lower:
            score += 2.0

        return score



class PublisherAnalyticsService:
    """Aggregates all analytics data for a publisher across their listings."""

    @staticmethod
    def _publisher_listings(publisher_id: str) -> list[dict[str, Any]]:
        """Return all listings owned by a publisher."""
        return [
            lst
            for lst in marketplace_registry.list_all()
            if lst.get("publisher_id") == publisher_id
        ]

    @staticmethod
    def summary(publisher_id: str) -> dict[str, Any]:
        """Return top-level KPIs for a publisher.

        Keys: total_installs, total_listings, avg_rating, total_credits_earned,
        credit_balance, total_reviews, featured_count.
        """
        listings = PublisherAnalyticsService._publisher_listings(publisher_id)
        total_installs = sum(lst.get("install_count", 0) for lst in listings)
        total_listings = len(listings)

        # Aggregate ratings across all listings
        all_ratings: list[float] = []
        total_reviews = 0
        featured_count = 0
        for lst in listings:
            lid = lst.get("id", "")
            stats = rating_store.get_stats(lid)
            if stats["rating_count"] > 0:
                all_ratings.extend([stats["avg_rating"]] * stats["rating_count"])
            total_reviews += len(review_store.list(lid, limit=1000))
            if featured_store.is_featured(lid):
                featured_count += 1

        avg_rating = round(sum(all_ratings) / len(all_ratings), 2) if all_ratings else 0.0

        payout = credit_ledger.payout_report(publisher_id)
        return {
            "total_installs": total_installs,
            "total_listings": total_listings,
            "avg_rating": avg_rating,
            "total_credits_earned": payout["total_earned"],
            "credit_balance": payout["balance"],
            "total_reviews": total_reviews,
            "featured_count": featured_count,
        }

    @staticmethod
    def per_listing(publisher_id: str) -> list[dict[str, Any]]:
        """Return per-listing breakdown sorted by install_count desc.

        Each entry: listing_id, name, install_count, avg_rating, rating_count,
        review_count, credits_earned, trending_score, is_featured, published_at.
        """
        listings = PublisherAnalyticsService._publisher_listings(publisher_id)
        payout = credit_ledger.payout_report(publisher_id)
        credits_by_listing: dict[str, int] = {}
        for pl in payout.get("per_listing", []):
            credits_by_listing[pl["listing_id"]] = pl["credits_earned"]

        result: list[dict[str, Any]] = []
        for lst in listings:
            lid = lst.get("id", "")
            stats = rating_store.get_stats(lid)
            reviews = review_store.list(lid, limit=1000)
            result.append(
                {
                    "listing_id": lid,
                    "name": lst.get("name", ""),
                    "install_count": lst.get("install_count", 0),
                    "avg_rating": stats["avg_rating"],
                    "rating_count": stats["rating_count"],
                    "review_count": len(reviews),
                    "credits_earned": credits_by_listing.get(lid, 0),
                    "trending_score": TrendingService.score(lst),
                    "is_featured": featured_store.is_featured(lid),
                    "published_at": lst.get("published_at", 0),
                }
            )
        result.sort(key=lambda x: x["install_count"], reverse=True)
        return result

    @staticmethod
    def growth_trend(publisher_id: str, days: int = 30) -> list[dict[str, Any]]:
        """Return daily install counts for the past N days.

        Each entry: {date: "YYYY-MM-DD", installs: int}.
        Uses install_timestamps from listings.
        """
        from datetime import datetime, timedelta

        now = datetime.now(tz=UTC)
        start_date = (now - timedelta(days=days - 1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        # Build date buckets
        date_counts: dict[str, int] = {}
        for i in range(days):
            d = start_date + timedelta(days=i)
            date_counts[d.strftime("%Y-%m-%d")] = 0

        # Count installs per day across all publisher listings
        listings = PublisherAnalyticsService._publisher_listings(publisher_id)
        for lst in listings:
            for ts in lst.get("install_timestamps", []):
                install_date = datetime.fromtimestamp(ts, tz=UTC).strftime("%Y-%m-%d")
                if install_date in date_counts:
                    date_counts[install_date] += 1

        return [{"date": date, "installs": count} for date, count in sorted(date_counts.items())]

    @staticmethod
    def top_templates(publisher_id: str, limit: int = 5) -> list[dict[str, Any]]:
        """Return top N templates by install_count."""
        per = PublisherAnalyticsService.per_listing(publisher_id)
        return per[:limit]

    @staticmethod
    def listing_detail(publisher_id: str, listing_id: str) -> dict[str, Any] | None:
        """Return detailed analytics for a single listing owned by the publisher.

        Returns None if the listing is not found. Raises ValueError if the
        listing is not owned by the publisher.
        """
        listing = marketplace_registry.get(listing_id)
        if listing is None:
            return None
        if listing.get("publisher_id") != publisher_id:
            raise ValueError("Listing not owned by publisher")

        lid = listing.get("id", listing_id)
        stats = rating_store.get_stats(lid)
        reviews = review_store.list(lid, limit=10)

        # Enrich reviews with replies
        enriched_reviews = []
        for review in reviews:
            reply = reply_store.get_reply(review["review_id"])
            enriched_reviews.append({**review, "reply": reply})

        payout = credit_ledger.payout_report(publisher_id)
        credits_earned = 0
        for pl in payout.get("per_listing", []):
            if pl["listing_id"] == lid:
                credits_earned = pl["credits_earned"]
                break

        # Build 30-day install trend for this specific listing
        from datetime import datetime, timedelta

        now = datetime.now(tz=UTC)
        start_date = (now - timedelta(days=29)).replace(hour=0, minute=0, second=0, microsecond=0)
        date_counts: dict[str, int] = {}
        for i in range(30):
            d = start_date + timedelta(days=i)
            date_counts[d.strftime("%Y-%m-%d")] = 0
        for ts in listing.get("install_timestamps", []):
            install_date = datetime.fromtimestamp(ts, tz=UTC).strftime("%Y-%m-%d")
            if install_date in date_counts:
                date_counts[install_date] += 1

        install_trend = [
            {"date": date, "installs": count} for date, count in sorted(date_counts.items())
        ]

        return {
            "listing": listing,
            "stats": {
                "avg_rating": stats["avg_rating"],
                "rating_count": stats["rating_count"],
                "review_count": len(reviews),
                "credits_earned": credits_earned,
                "trending_score": TrendingService.score(listing),
                "is_featured": featured_store.is_featured(lid),
            },
            "recent_reviews": enriched_reviews,
            "install_trend": install_trend,
        }



class CostCalculator:
    """Estimate execution cost of a workflow before running it.

    Pricing table (per call):
      llm:       $0.002  (e.g. GPT-3.5 equivalent, ~500 tokens)
      imagegen:  $0.020  (e.g. DALL-E standard)
      http:      $0.000  (free, external API cost not tracked)
      code:      $0.001  (compute cost)
      transform: $0.000  (free)
      ifelse:    $0.000  (free)
      merge:     $0.000  (free)
      foreach:   $0.001  (per-iteration overhead)

    For foreach nodes, multiply by expected_iterations (default 10).
    Total = sum of per-node cost. Return itemized breakdown + total.
    """

    PRICING: dict[str, float] = {
        "llm": 0.002,
        "imagegen": 0.020,
        "http": 0.000,
        "code": 0.001,
        "transform": 0.000,
        "ifelse": 0.000,
        "merge": 0.000,
        "foreach": 0.001,
    }
    DEFAULT_FOREACH_ITERATIONS = 10

    @classmethod
    def estimate(cls, nodes: list[dict], foreach_iterations: int = 10) -> dict:
        """Estimate execution cost for a list of workflow nodes.

        Args:
            nodes: list of node dicts with at least {"id": str, "type": str}
            foreach_iterations: assumed iterations for foreach nodes

        Returns:
            Dictionary with total_usd, currency, breakdown, node_count,
            and billable_node_count.
        """
        breakdown: list[dict[str, Any]] = []
        total: float = 0.0
        billable_count = 0

        for node in nodes:
            node_id = node.get("id", "unknown")
            node_type = node.get("type", "unknown")
            per_call = cls.PRICING.get(node_type, 0.0)

            if node_type == "foreach":
                cost = per_call * foreach_iterations
                note = f"foreach x{foreach_iterations} iterations"
            elif per_call > 0:
                cost = per_call
                note = f"{node_type} base cost"
            else:
                cost = 0.0
                note = "free"

            if cost > 0:
                billable_count += 1

            breakdown.append({
                "node_id": node_id,
                "node_type": node_type,
                "cost_usd": round(cost, 6),
                "note": note,
            })
            total += cost

        return {
            "total_usd": round(total, 6),
            "currency": "USD",
            "breakdown": breakdown,
            "node_count": len(nodes),
            "billable_node_count": billable_count,
        }



class EstimateCostRequest(BaseModel):
    """Request body for estimating cost of arbitrary nodes."""

    nodes: list[dict]
    foreach_iterations: int = Field(10, ge=1, le=1000)



class FlowEstimateCostRequest(BaseModel):
    """Request body for estimating cost of a saved flow."""

    foreach_iterations: int = Field(10, ge=1, le=1000)



class TestCaseRequest(BaseModel):
    """Request body for adding a workflow test case."""

    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field("", max_length=1000)
    input: dict[str, Any] = Field(default_factory=dict)
    expected_output: dict[str, Any] = Field(default_factory=dict)
    match_mode: Literal["exact", "contains", "keys_present"] = "contains"



class RunTestSuiteRequest(BaseModel):
    """Request body for running a test suite against a flow."""

    test_ids: list[str] = Field(default_factory=list)
    foreach_parallel: bool = False



class TrendingService:
    """Compute trending score: installs in last 7 days (weighted) + all-time install_count."""

    RECENCY_WINDOW_SECONDS: float = 7 * 24 * 3600  # 7 days

    @staticmethod
    def score(listing: dict[str, Any]) -> float:
        """Trending score = recent installs × 10 + all-time install_count."""
        now = time.time()
        recent_installs = sum(
            1
            for ts in listing.get("install_timestamps", [])
            if now - ts < TrendingService.RECENCY_WINDOW_SECONDS
        )
        # Recent installs worth 10x, historical worth 1x
        return recent_installs * 10 + listing.get("install_count", 0)

    @staticmethod
    def top(listings: list[dict[str, Any]], limit: int = 10) -> list[dict[str, Any]]:
        """Return the top-N listings sorted by trending score descending."""
        return sorted(listings, key=TrendingService.score, reverse=True)[:limit]



class RateListingRequest(BaseModel):
    """Request body for rating a marketplace listing."""

    model_config = ConfigDict(extra="forbid")
    stars: int = Field(..., ge=1, le=5, description="Star rating 1-5")



class ReviewListingRequest(BaseModel):
    """Request body for reviewing a marketplace listing."""

    model_config = ConfigDict(extra="forbid")
    text: str = Field(..., min_length=1, max_length=2000)
    stars: int | None = Field(None, ge=1, le=5)



class ReplyToReviewRequest(BaseModel):
    """Request body for a publisher reply to a review."""

    model_config = ConfigDict(extra="forbid")
    text: str = Field(..., min_length=1, max_length=2000)



class ReportIssueRequest(BaseModel):
    """Request body for reporting an issue with a marketplace listing."""

    model_config = ConfigDict(extra="forbid")
    type: Literal["broken", "malware", "spam", "outdated", "other"]
    description: str = Field(..., min_length=1, max_length=1000)



class JoinPresenceRequest(BaseModel):
    """Request body for joining a flow's collaboration session."""

    model_config = ConfigDict(extra="forbid")
    flow_id: str = ""  # optional; path param is authoritative



class HeartbeatRequest(BaseModel):
    """Request body for a collaboration heartbeat (empty — just needs auth)."""

    model_config = ConfigDict(extra="forbid")



class AcquireNodeLockRequest(BaseModel):
    """Request body for acquiring a node lock."""

    model_config = ConfigDict(extra="forbid")
    node_id: str



class DynamicPluginApplet:
    """Applet adapter that executes a third-party plugin via HTTP POST."""

    def __init__(self, plugin_entry: dict[str, Any]) -> None:
        self.plugin_entry = plugin_entry

    async def execute(self, message: Any) -> dict[str, Any]:
        """POST input data to the plugin's endpoint_url and return the JSON response."""
        manifest = self.plugin_entry["manifest"]
        endpoint = manifest["endpoint_url"]
        payload = {
            "input": message.input if hasattr(message, "input") else {},
            "config": message.config if hasattr(message, "config") else {},
            "node_id": message.node_id if hasattr(message, "node_id") else "",
        }
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(endpoint, json=payload)
                resp.raise_for_status()
                return resp.json()
        except httpx.TimeoutException as exc:
            raise ValueError(f"Plugin '{manifest['name']}' timed out after 30s") from exc
        except httpx.HTTPStatusError as exc:
            raise ValueError(
                f"Plugin '{manifest['name']}' returned HTTP {exc.response.status_code}"
            ) from exc
        except Exception as exc:
            logger.warning("Plugin '%s' execution error: %s", manifest["name"], exc)
            raise ValueError(f"Plugin '{manifest['name']}' failed: {exc}") from exc



class RegisterPluginRequest(BaseModel):
    """Request body for POST /plugins."""

    name: str
    version: str
    display_name: str
    description: str
    node_type: str
    endpoint_url: str
    config_schema: dict[str, Any] = {}
    tags: list[str] = []
    author: str = ""
    icon_url: str = ""



class PayoutRequest(BaseModel):
    """Request body for requesting a credit payout."""

    model_config = ConfigDict(extra="forbid")
    amount: int = Field(..., ge=1)



class SetSLAPolicyRequest(BaseModel):
    """Request body for creating/updating an SLA policy."""

    model_config = ConfigDict(extra="forbid")
    max_duration_seconds: float = Field(..., gt=0)
    alert_threshold_pct: float = Field(0.8, ge=0.1, le=1.0)

