"""
SynApps Orchestrator - Core Module

This is the lightweight microkernel that routes messages between applets in a
defined sequence. The orchestrator's job is purely to pass messages and data
between applets.
"""

import asyncio
import base64
import hashlib
import hmac
import importlib
import json
import logging
import math
import os
import re
import secrets
import shutil
import sqlite3
import sys
import tempfile
import threading
import time
import uuid
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

# Load environment variables: .env takes priority, falls back to .env.development
from dotenv import load_dotenv

project_root = Path(__file__).parent.parent.parent
env_path = project_root / ".env"
if not env_path.exists():
    env_path = project_root / ".env.development"
load_dotenv(dotenv_path=env_path)

# Import database modules
from contextlib import asynccontextmanager

import httpx
import jwt
from croniter import croniter as CronIter
from cryptography.fernet import Fernet, InvalidToken
from fastapi import (
    APIRouter,
    FastAPI,
    Header,
    HTTPException,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from starlette.exceptions import HTTPException as StarletteHTTPException

from apps.orchestrator.db import close_db_connections, get_db_session, init_db
from apps.orchestrator.models import (
    SUPPORTED_IMAGE_PROVIDERS,
    SUPPORTED_LLM_PROVIDERS,
    SUPPORTED_MEMORY_BACKENDS,
    APIKeyCreateRequestModel,
    AuthLoginRequestModel,
    AuthRefreshRequestModel,
    AuthRegisterRequestModel,
    AuthTokenResponseModel,
    CodeNodeConfigModel,
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
)
from apps.orchestrator.models import (
    RefreshToken as AuthRefreshToken,
)
from apps.orchestrator.models import (
    User as AuthUser,
)
from apps.orchestrator.models import (
    UserAPIKey as AuthUserAPIKey,
)
from apps.orchestrator.repositories import FlowRepository, WorkflowRunRepository
from apps.orchestrator.stores import (
    ConnectorError,
    ConnectorStatus,
    ErrorCategory,
    RetryPolicy,
    SchedulerService,
    WebhookTriggerRegistry,
    activity_feed_store,
    admin_key_registry,
    connector_health,
    cost_tracker_store,
    deprecation_registry,
    execution_dashboard_store,
    execution_log_store,
    failed_request_store,
    notification_store,
    plugin_registry,
    sla_store,
    sse_event_bus,
    subflow_registry,
    usage_tracker,
    webhook_trigger_registry,
    workflow_permission_store,
    workflow_secret_store,
    workflow_variable_store,
)

try:
    import resource
except Exception:  # pragma: no cover - non-Unix fallback
    resource = None  # type: ignore[assignment]

# ============================================================
# Structured JSON Logging with Request-ID tracing
# ============================================================
import contextvars

_current_request_id: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")


class _JSONFormatter(logging.Formatter):
    """Structured JSON log formatter with request_id tracing."""

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": _current_request_id.get("-"),
        }
        if record.exc_info and record.exc_info[0] is not None:
            entry["exception"] = self.formatException(record.exc_info)
        # Include extra structured fields if set by middleware
        for key in ("endpoint", "method", "status", "duration_ms", "client_ip"):
            val = getattr(record, key, None)
            if val is not None:
                entry[key] = val
        return json.dumps(entry, default=str)


def _setup_logging() -> logging.Logger:
    """Configure the root orchestrator logger with JSON structured output."""
    _logger = logging.getLogger("orchestrator")
    _logger.setLevel(logging.INFO)

    # Only add our handler if none exist (avoid duplicate handlers on reload)
    if not _logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(_JSONFormatter())
        _logger.addHandler(handler)
        _logger.propagate = False

    return _logger


logger = _setup_logging()

# ============================================================
# Constants
# ============================================================

API_VERSION = "1.0.0"
API_VERSION_DATE = "2026-02-23"  # date-based API version for X-API-Version header
API_SUPPORTED_VERSIONS = ["v1"]  # active version prefixes
API_SUNSET_GRACE_DAYS = 90  # deprecated endpoints stay live 90 days past sunset
APP_START_TIME = time.time()
WS_AUTH_TOKEN = os.environ.get("WS_AUTH_TOKEN")
JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "synapps-dev-jwt-secret-change-me")
JWT_ALGORITHM = os.environ.get("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("JWT_ACCESS_EXPIRE_MINUTES", "15"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.environ.get("JWT_REFRESH_EXPIRE_DAYS", "14"))
PASSWORD_HASH_ITERATIONS = int(os.environ.get("PASSWORD_HASH_ITERATIONS", "390000"))
API_KEY_VALUE_PREFIX = os.environ.get("API_KEY_PREFIX", "synapps")
API_KEY_LOOKUP_PREFIX_LEN = int(os.environ.get("API_KEY_LOOKUP_PREFIX_LEN", "18"))
ALLOW_ANONYMOUS_WHEN_NO_USERS = os.environ.get(
    "ALLOW_ANONYMOUS_WHEN_NO_USERS",
    "true",
).strip().lower() in {"1", "true", "yes"}
LEGACY_WRITER_NODE_TYPE = "writer"
LEGACY_ARTIST_NODE_TYPE = "artist"
LEGACY_MEMORY_NODE_TYPE = "memory"
LLM_NODE_TYPE = "llm"
IMAGE_NODE_TYPE = "image"
MEMORY_NODE_TYPE = "memory"
HTTP_REQUEST_NODE_TYPE = "http_request"
CODE_NODE_TYPE = "code"
TRANSFORM_NODE_TYPE = "transform"
IF_ELSE_NODE_TYPE = "if_else"
MERGE_NODE_TYPE = "merge"
FOR_EACH_NODE_TYPE = "for_each"
BRANCH_NODE_TYPE = "branch"
COMPOUND_MERGE_NODE_TYPE = "compound_merge"
WEBHOOK_TRIGGER_NODE_TYPE = "webhook_trigger"
SCHEDULER_NODE_TYPE = "scheduler_node"
ERROR_HANDLER_NODE_TYPE = "error_handler"
ENGINE_MAX_CONCURRENCY = int(os.environ.get("ENGINE_MAX_CONCURRENCY", "10"))
TRACE_RESULTS_KEY = "__trace__"
TRACE_SCHEMA_VERSION = 1
MAX_DIFF_CHANGES = 250


# ============================================================
# Centralised App Configuration
# ============================================================

_SECRET_KEYS = frozenset(
    {
        "database_url",
        "jwt_secret_key",
        "synapps_master_key",
        "fernet_key",
        "openai_api_key",
        "stability_api_key",
        "dalle_api_key",
        "ws_auth_token",
        "custom_llm_api_key",
        "secret_key",
    }
)


def _redact(value: str) -> str:
    """Redact a secret value — show first 4 and last 2 chars if long enough."""
    if not value or len(value) < 8:
        return "***"
    return value[:4] + "***" + value[-2:]


class AppConfig:
    """Centralised configuration loaded from environment variables.

    All env vars are read once at import time. The ``to_dict()`` method returns
    the full config with secrets redacted for safe exposure via the /config
    endpoint. ``validate()`` raises ``ValueError`` listing all problems.
    """

    def __init__(self) -> None:
        g = os.environ.get

        # --- Database ---
        self.database_url: str = g("DATABASE_URL", "sqlite+aiosqlite:///synapps.db")

        # --- Server ---
        self.backend_host: str = g("BACKEND_HOST", "0.0.0.0")
        self.backend_port: int = int(g("BACKEND_PORT", "8000"))
        self.production: bool = g("PRODUCTION", "false").strip().lower() in {"1", "true", "yes"}
        self.debug: bool = g("DEBUG", "false").strip().lower() in {"1", "true", "yes"}
        self.log_level: str = g("LOG_LEVEL", "info").strip().lower()

        # --- Auth / JWT ---
        self.jwt_secret_key: str = g("JWT_SECRET_KEY", "synapps-dev-jwt-secret-change-me")
        self.jwt_algorithm: str = g("JWT_ALGORITHM", "HS256")
        self.jwt_access_expire_minutes: int = int(g("JWT_ACCESS_EXPIRE_MINUTES", "15"))
        self.jwt_refresh_expire_days: int = int(g("JWT_REFRESH_EXPIRE_DAYS", "14"))
        self.allow_anonymous: bool = g("ALLOW_ANONYMOUS_WHEN_NO_USERS", "true").strip().lower() in {
            "1",
            "true",
            "yes",
        }
        self.synapps_master_key: str = g("SYNAPPS_MASTER_KEY", "")
        self.fernet_key: str = g("FERNET_KEY", "")
        self.ws_auth_token: str = g("WS_AUTH_TOKEN", "")
        self.smtp_host: str = g("SMTP_HOST", "localhost")
        self.smtp_port: int = int(g("SMTP_PORT", "587"))
        self.smtp_user: str = g("SMTP_USER", "")
        self.smtp_password: str = g("SMTP_PASSWORD", "")
        self.sendgrid_api_key: str = g("SENDGRID_API_KEY", "")

        # --- CORS ---
        self.cors_origins: str = g("BACKEND_CORS_ORIGINS", "")

        # --- Rate Limiting ---
        self.rate_limit_window: int = int(g("RATE_LIMIT_WINDOW_SECONDS", "60"))
        self.rate_limit_free: int = int(g("RATE_LIMIT_FREE", "60"))
        self.rate_limit_pro: int = int(g("RATE_LIMIT_PRO", "200"))
        self.rate_limit_enterprise: int = int(g("RATE_LIMIT_ENTERPRISE", "1000"))
        self.rate_limit_anonymous: int = int(g("RATE_LIMIT_ANONYMOUS", "30"))

        # --- Engine ---
        self.engine_max_concurrency: int = int(g("ENGINE_MAX_CONCURRENCY", "10"))

        # --- API Keys ---
        self.openai_api_key: str = g("OPENAI_API_KEY", "")
        self.stability_api_key: str = g("STABILITY_API_KEY", "")
        self.dalle_api_key: str = g("DALLE_API_KEY", "")
        self.custom_llm_api_key: str = g("CUSTOM_LLM_API_KEY", "")

        # --- Memory ---
        self.memory_backend: str = g("MEMORY_BACKEND", "sqlite_fts").strip().lower()
        self.memory_namespace: str = g("MEMORY_NAMESPACE", "default").strip() or "default"
        self.memory_sqlite_path: str = g("MEMORY_SQLITE_PATH", "")
        self.memory_collection: str = (
            g("MEMORY_COLLECTION", "synapps_memory").strip() or "synapps_memory"
        )

    def validate(self) -> list[str]:
        """Validate configuration. Returns list of error messages (empty = valid)."""
        errors: list[str] = []

        # In production, certain vars are required
        if self.production:
            if self.jwt_secret_key == "synapps-dev-jwt-secret-change-me":
                errors.append("JWT_SECRET_KEY must be changed from the default in production")
            if not self.cors_origins.strip():
                errors.append(
                    "BACKEND_CORS_ORIGINS is required in production "
                    "(comma-separated list of allowed origins)"
                )

        # Always validate ranges
        if self.backend_port < 1 or self.backend_port > 65535:
            errors.append(f"BACKEND_PORT must be 1-65535, got {self.backend_port}")
        if self.rate_limit_window < 1:
            errors.append(f"RATE_LIMIT_WINDOW_SECONDS must be >= 1, got {self.rate_limit_window}")
        if self.engine_max_concurrency < 1:
            errors.append(f"ENGINE_MAX_CONCURRENCY must be >= 1, got {self.engine_max_concurrency}")
        if self.log_level not in {"debug", "info", "warning", "error", "critical"}:
            errors.append(
                f"LOG_LEVEL must be debug/info/warning/error/critical, got '{self.log_level}'"
            )

        return errors

    def to_dict(self, redact_secrets: bool = True) -> dict[str, Any]:
        """Return config as a dictionary, optionally redacting secrets."""
        result: dict[str, Any] = {}
        for key, value in self.__dict__.items():
            if key.startswith("_"):
                continue
            if redact_secrets and key in _SECRET_KEYS and isinstance(value, str) and value:
                result[key] = _redact(value)
            else:
                result[key] = value
        return result


app_config = AppConfig()


# ============================================================
# In-Memory Metrics Collector (Ring-Buffer Backed)
# ============================================================


class _MetricsRingBuffer:
    """Fixed-size ring buffer storing timestamped float samples.

    Each entry is ``(timestamp, value)``.  When the buffer is full the
    oldest entry is silently overwritten — no allocations, no resizing.
    ``query(window_seconds)`` returns only samples within the window.
    """

    def __init__(self, capacity: int = 10_000) -> None:
        self._capacity = capacity
        self._buf: list[tuple | None] = [None] * capacity
        self._head: int = 0  # next write position
        self._count: int = 0

    @property
    def capacity(self) -> int:
        return self._capacity

    def push(self, value: float, ts: float | None = None) -> None:
        ts = ts if ts is not None else time.time()
        self._buf[self._head] = (ts, value)
        self._head = (self._head + 1) % self._capacity
        if self._count < self._capacity:
            self._count += 1

    def query(self, window_seconds: float) -> list[float]:
        """Return values recorded within the last *window_seconds*."""
        cutoff = time.time() - window_seconds
        result: list[float] = []
        for i in range(self._count):
            idx = (self._head - self._count + i) % self._capacity
            entry = self._buf[idx]
            if entry is not None and entry[0] >= cutoff:
                result.append(entry[1])
        return result

    def all_values(self) -> list[float]:
        """Return all stored values (oldest first)."""
        result: list[float] = []
        for i in range(self._count):
            idx = (self._head - self._count + i) % self._capacity
            entry = self._buf[idx]
            if entry is not None:
                result.append(entry[1])
        return result

    def clear(self) -> None:
        self._buf = [None] * self._capacity
        self._head = 0
        self._count = 0

    def __len__(self) -> int:
        return self._count


class _MetricsCollector:
    """Thread-safe in-memory request/response metrics.

    Uses ring buffers for time-windowed queries (1 h / 24 h) and tracks
    per-connector (provider) stats.  No external dependencies — designed
    for ``/metrics`` endpoint consumption.
    """

    def __init__(self, ring_capacity: int = 10_000) -> None:
        self._lock = threading.Lock()
        self.total_requests: int = 0
        self.total_errors: int = 0
        self._response_times = _MetricsRingBuffer(ring_capacity)
        self._error_times = _MetricsRingBuffer(ring_capacity)
        self._provider_usage: dict[str, int] = {}
        self._provider_times: dict[str, _MetricsRingBuffer] = {}
        self._template_runs: dict[str, int] = {}
        self._last_template_run_time: float | None = None
        self._ring_capacity = ring_capacity

    def record_request(self, duration_ms: float, status_code: int, path: str) -> None:
        now = time.time()
        with self._lock:
            self.total_requests += 1
            self._response_times.push(duration_ms, now)
            if status_code >= 400:
                self.total_errors += 1
                self._error_times.push(1.0, now)

    def record_provider_call(self, provider: str, duration_ms: float = 0.0) -> None:
        now = time.time()
        with self._lock:
            self._provider_usage[provider] = self._provider_usage.get(provider, 0) + 1
            if provider not in self._provider_times:
                self._provider_times[provider] = _MetricsRingBuffer(self._ring_capacity)
            self._provider_times[provider].push(duration_ms, now)

    def record_template_run(self, template_name: str) -> None:
        with self._lock:
            self._template_runs[template_name] = self._template_runs.get(template_name, 0) + 1
            self._last_template_run_time = time.time()

    def _window_stats(self, buf: _MetricsRingBuffer, window_seconds: float) -> dict[str, Any]:
        """Compute count, avg, p50, p95, p99 for a time window."""
        values = buf.query(window_seconds)
        if not values:
            return {"count": 0, "avg_ms": 0.0, "p50_ms": 0.0, "p95_ms": 0.0, "p99_ms": 0.0}
        values.sort()
        n = len(values)
        return {
            "count": n,
            "avg_ms": round(sum(values) / n, 2),
            "p50_ms": round(values[n // 2], 2),
            "p95_ms": round(values[int(n * 0.95)], 2),
            "p99_ms": round(values[min(int(n * 0.99), n - 1)], 2),
        }

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            all_times = self._response_times.all_values()
            avg_ms = sum(all_times) / len(all_times) if all_times else 0.0
            error_rate = (
                (self.total_errors / self.total_requests * 100) if self.total_requests > 0 else 0.0
            )

            # Time-windowed request stats
            request_1h = self._window_stats(self._response_times, 3600)
            request_24h = self._window_stats(self._response_times, 86400)

            # Error counts in windows
            errors_1h = len(self._error_times.query(3600))
            errors_24h = len(self._error_times.query(86400))

            # Per-connector (provider) stats
            connector_stats: dict[str, Any] = {}
            for prov, total in self._provider_usage.items():
                prov_buf = self._provider_times.get(prov)
                connector_stats[prov] = {
                    "total_calls": total,
                    "last_1h": self._window_stats(prov_buf, 3600) if prov_buf else {},
                    "last_24h": self._window_stats(prov_buf, 86400) if prov_buf else {},
                }

            return {
                "requests": {
                    "total": self.total_requests,
                    "errors": self.total_errors,
                    "error_rate_pct": round(error_rate, 2),
                    "avg_response_ms": round(avg_ms, 2),
                    "last_1h": request_1h,
                    "last_24h": request_24h,
                    "errors_last_1h": errors_1h,
                    "errors_last_24h": errors_24h,
                },
                "provider_usage": dict(self._provider_usage),
                "connector_stats": connector_stats,
                "template_runs": dict(self._template_runs),
                "last_template_run_at": self._last_template_run_time,
            }

    def reset(self) -> None:
        with self._lock:
            self.total_requests = 0
            self.total_errors = 0
            self._response_times.clear()
            self._error_times.clear()
            self._provider_usage.clear()
            self._provider_times.clear()
            self._template_runs.clear()
            self._last_template_run_time = None


metrics = _MetricsCollector()


# ============================================================
# Failed Request Store (LRU in-memory ring for replay + debug)
# ============================================================








# ============================================================
# Consumer Usage Tracker + Quota System
# ============================================================











# ---------------------------------------------------------------------------
# ExecutionQuotaStore — per-user execution rate limits + monthly quotas (D-13)
# ---------------------------------------------------------------------------






# ============================================================
# API Deprecation Registry
# ============================================================





# Register known deprecated endpoints
deprecation_registry.deprecate(
    "POST",
    "/api/v1/flows/{flow_id}/run",
    sunset="2026-05-24",
    successor="/api/v1/flows/{flow_id}/runs",
)


# ============================================================
# Error Classification + Retry Policies
# ============================================================




# HTTP status → category mapping
_STATUS_CATEGORY: dict[int, ErrorCategory] = {
    429: ErrorCategory.RATE_LIMITED,
    500: ErrorCategory.TRANSIENT,
    502: ErrorCategory.TRANSIENT,
    503: ErrorCategory.TRANSIENT,
    504: ErrorCategory.TRANSIENT,
    408: ErrorCategory.TRANSIENT,
    401: ErrorCategory.PERMANENT,
    403: ErrorCategory.PERMANENT,
    404: ErrorCategory.PERMANENT,
    422: ErrorCategory.PERMANENT,
}

# Exception types that are always transient
_TRANSIENT_EXCEPTIONS: tuple = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.ReadTimeout,
    httpx.WriteTimeout,
    httpx.PoolTimeout,
    ConnectionError,
    TimeoutError,
    OSError,
)


def classify_error(
    exc: Exception | None = None,
    status_code: int | None = None,
) -> ErrorCategory:
    """Classify an error as TRANSIENT, RATE_LIMITED, or PERMANENT.

    Priority: explicit status_code > exception type > fallback to PERMANENT.
    """
    if status_code is not None:
        return _STATUS_CATEGORY.get(status_code, ErrorCategory.PERMANENT)
    if exc is not None:
        if isinstance(exc, _TRANSIENT_EXCEPTIONS):
            return ErrorCategory.TRANSIENT
        if isinstance(exc, httpx.HTTPStatusError):
            return _STATUS_CATEGORY.get(exc.response.status_code, ErrorCategory.PERMANENT)
    return ErrorCategory.PERMANENT




# Default policies per connector
DEFAULT_RETRY_POLICY = RetryPolicy(max_retries=3, base_delay=1.0, backoff_factor=2.0)

CONNECTOR_RETRY_POLICIES: dict[str, RetryPolicy] = {
    "openai": RetryPolicy(max_retries=3, base_delay=1.0, backoff_factor=2.0),
    "anthropic": RetryPolicy(max_retries=3, base_delay=1.5, backoff_factor=2.0),
    "google": RetryPolicy(max_retries=3, base_delay=1.0, backoff_factor=2.0),
    "ollama": RetryPolicy(max_retries=2, base_delay=0.5, backoff_factor=2.0),
    "custom": RetryPolicy(max_retries=2, base_delay=1.0, backoff_factor=2.0),
    "stability": RetryPolicy(max_retries=3, base_delay=2.0, backoff_factor=2.0),
}


def get_retry_policy(connector: str) -> RetryPolicy:
    """Get the retry policy for a connector, falling back to default."""
    return CONNECTOR_RETRY_POLICIES.get(connector, DEFAULT_RETRY_POLICY)




async def execute_with_retry(
    func,
    *,
    connector: str = "",
    policy: RetryPolicy | None = None,
) -> Any:
    """Execute *func* (an async callable) with retry logic.

    On failure, classifies the error and retries according to *policy*.
    Returns the result on success or raises ``ConnectorError`` on exhaustion.
    """
    retry_policy = policy or get_retry_policy(connector)
    last_exc: Exception | None = None

    for attempt in range(retry_policy.max_retries + 1):
        try:
            return await func()
        except Exception as exc:
            last_exc = exc

            # Extract status code if available
            status_code: int | None = None
            if isinstance(exc, httpx.HTTPStatusError):
                status_code = exc.response.status_code
            elif hasattr(exc, "status_code"):
                status_code = exc.status_code

            category = classify_error(exc=exc, status_code=status_code)

            if not retry_policy.should_retry(category, attempt):
                raise ConnectorError(
                    str(exc),
                    category=category,
                    connector=connector,
                    status_code=status_code,
                    attempt=attempt,
                    max_retries=retry_policy.max_retries,
                ) from exc

            delay = retry_policy.delay_for_attempt(attempt)
            logger.warning(
                "Connector '%s' attempt %d/%d failed (%s: %s). Retrying in %.1fs...",
                connector,
                attempt + 1,
                retry_policy.max_retries,
                category.value,
                exc,
                delay,
            )
            await asyncio.sleep(delay)

    # Should not reach here, but just in case
    raise ConnectorError(
        str(last_exc),
        category=ErrorCategory.PERMANENT,
        connector=connector,
        attempt=retry_policy.max_retries,
        max_retries=retry_policy.max_retries,
    ) from last_exc


# ============================================================
# Connector Health Probes
# ============================================================




# Window size for dashboard health metrics (seconds).
HEALTH_WINDOW_SECONDS = 300  # 5 minutes
# Cache TTL for aggregated health results.
HEALTH_CACHE_TTL_SECONDS = 30
# Timeout for individual connector ping.
HEALTH_PROBE_TIMEOUT_SECONDS = 5





# Cache for probe_all_connectors results
_health_cache: dict[str, Any] = {"results": None, "timestamp": 0.0}


async def probe_connector(connector_name: str) -> dict[str, Any]:
    """Run a lightweight health probe for a connector.

    Uses a HEAD/GET ping against the provider's base URL when possible,
    falling back to ``validate_config()`` for providers without an HTTP
    endpoint. Respects ``HEALTH_PROBE_TIMEOUT_SECONDS``.

    Emits ``connector.status_changed`` when the dashboard status transitions.
    """
    # Capture status before probe
    old_ds = connector_health.get_dashboard_status(connector_name).get("dashboard_status")

    start = time.time()
    try:
        provider_cls = LLMProviderRegistry._providers.get(connector_name)
        if provider_cls is None:
            connector_health.record_failure(connector_name, f"Unknown connector: {connector_name}")
            result = {
                "connector": connector_name,
                "reachable": False,
                "latency_ms": 0.0,
                "detail": f"Unknown connector: {connector_name}",
            }
            await _maybe_emit_status_change(connector_name, old_ds)
            return result

        default_cfg = LLMNodeConfigModel(provider=connector_name)
        adapter = provider_cls(default_cfg)

        # First validate config (API key present?)
        is_valid, reason = adapter.validate_config()
        if not is_valid:
            elapsed = (time.time() - start) * 1000
            connector_health.record_failure(connector_name, reason, latency_ms=elapsed)
            result = {
                "connector": connector_name,
                "reachable": False,
                "latency_ms": round(elapsed, 2),
                "detail": reason,
            }
            await _maybe_emit_status_change(connector_name, old_ds)
            return result

        # Attempt lightweight HTTP ping if adapter has a base_url
        base_url = getattr(adapter, "base_url", None)
        if base_url:
            try:
                async with httpx.AsyncClient(timeout=HEALTH_PROBE_TIMEOUT_SECONDS) as client:
                    await client.head(base_url)
                elapsed = (time.time() - start) * 1000
                connector_health.record_success(connector_name, latency_ms=elapsed)
                result = {
                    "connector": connector_name,
                    "reachable": True,
                    "latency_ms": round(elapsed, 2),
                    "detail": "",
                }
                await _maybe_emit_status_change(connector_name, old_ds)
                return result
            except Exception as ping_exc:
                elapsed = (time.time() - start) * 1000
                connector_health.record_failure(
                    connector_name,
                    f"Ping failed: {ping_exc}",
                    latency_ms=elapsed,
                )
                result = {
                    "connector": connector_name,
                    "reachable": False,
                    "latency_ms": round(elapsed, 2),
                    "detail": f"Ping failed: {ping_exc}",
                }
                await _maybe_emit_status_change(connector_name, old_ds)
                return result

        # No base_url — treat validated config as reachable
        elapsed = (time.time() - start) * 1000
        connector_health.record_success(connector_name, latency_ms=elapsed)
        result = {
            "connector": connector_name,
            "reachable": True,
            "latency_ms": round(elapsed, 2),
            "detail": "",
        }
        await _maybe_emit_status_change(connector_name, old_ds)
        return result
    except Exception as exc:
        elapsed = (time.time() - start) * 1000
        connector_health.record_failure(connector_name, str(exc), latency_ms=elapsed)
        result = {
            "connector": connector_name,
            "reachable": False,
            "latency_ms": round(elapsed, 2),
            "detail": str(exc),
        }
        await _maybe_emit_status_change(connector_name, old_ds)
        return result


async def _maybe_emit_status_change(connector_name: str, old_status: str | None) -> None:
    """Emit ``connector.status_changed`` if dashboard status transitioned."""
    new_ds = connector_health.get_dashboard_status(connector_name).get("dashboard_status")
    if new_ds != old_status:
        await emit_event(
            "connector.status_changed",
            {
                "connector": connector_name,
                "old_status": old_status,
                "new_status": new_ds,
            },
        )


async def probe_all_connectors() -> list[dict[str, Any]]:
    """Probe all known connectors and return their statuses.

    Results are cached for ``HEALTH_CACHE_TTL_SECONDS`` seconds to avoid
    hammering upstream providers on every dashboard refresh.
    """
    now = time.time()
    if (
        _health_cache["results"] is not None
        and (now - _health_cache["timestamp"]) < HEALTH_CACHE_TTL_SECONDS
    ):
        return _health_cache["results"]

    results: list[dict[str, Any]] = []
    for name in LLMProviderRegistry._providers:
        probe_result = await probe_connector(name)
        state = connector_health.get_dashboard_status(name)
        results.append(
            {
                **probe_result,
                "status": state["status"],
                "dashboard_status": state["dashboard_status"],
                "consecutive_failures": state["consecutive_failures"],
                "total_probes": state["total_probes"],
                "total_failures": state["total_failures"],
                "last_check": state["last_check"],
                "last_success": state["last_success"],
                "avg_latency_ms": state["avg_latency_ms"],
                "error_count_5m": state["error_count_5m"],
            }
        )
    _health_cache["results"] = results
    _health_cache["timestamp"] = now
    return results


# ============================================================
# Webhook / Event System  (DIRECTIVE-13: Webhook Notification System)
# ============================================================

from apps.orchestrator.webhooks.manager import (
    WebhookManager,
    emit_webhook_event,
)

# Legacy alias kept for backwards-compat in existing tests
WEBHOOK_RETRY_BASE_SECONDS = 1.0


def _get_fernet_encrypt():
    """Return encrypt/decrypt helpers bound to FERNET_CIPHER (lazy)."""

    def _enc(plain: str) -> str:
        return FERNET_CIPHER.encrypt(plain.encode("utf-8")).decode("utf-8")

    def _dec(cipher: str) -> str | None:
        try:
            return FERNET_CIPHER.decrypt(cipher.encode("utf-8")).decode("utf-8")
        except Exception as exc:  # noqa: BLE001
            # SILENT JUSTIFIED: tampered/invalid ciphertext returns None; caller handles sentinel
            logger.debug("Fernet decrypt failed (likely tampered ciphertext): %s", exc)
            return None

    return _enc, _dec


# Instantiated after FERNET_CIPHER is defined (see post-init below).
# For now create with identity encrypt/decrypt — replaced in _init_webhook_manager().
webhook_registry = WebhookManager()


def _init_webhook_manager() -> None:
    """Re-initialise webhook_registry with Fernet encryption. Called after FERNET_CIPHER is ready."""
    global webhook_registry
    enc, dec = _get_fernet_encrypt()
    webhook_registry = WebhookManager(encrypt_fn=enc, decrypt_fn=dec)


async def emit_event(event: str, data: dict[str, Any]) -> None:
    """Fire-and-forget delivery to all webhooks registered for *event*."""
    await emit_webhook_event(event, data, webhook_registry)


# ============================================================
# Webhook Trigger Registry (N-19 — inbound webhook triggers)
# ============================================================




# Global inbound webhook trigger registry (Fernet re-injected at startup)


# ---------------------------------------------------------------------------
# Scheduler Service — Background cron-tick loop
# ---------------------------------------------------------------------------




def _init_webhook_trigger_registry() -> None:
    """Re-initialise webhook_trigger_registry with Fernet encryption."""
    global webhook_trigger_registry
    import apps.orchestrator.stores as _stores
    enc, dec = _get_fernet_encrypt()
    webhook_trigger_registry = WebhookTriggerRegistry(encrypt_fn=enc, decrypt_fn=dec)
    # Keep stores module in sync so conftest.py resets the correct instance
    _stores.webhook_trigger_registry = webhook_trigger_registry


# ============================================================
# Async Task Queue
# ============================================================

TASK_STATUSES = ("pending", "running", "completed", "failed")






# ============================================================
# Admin API Key Registry (master-key-protected)
# ============================================================

SYNAPPS_MASTER_KEY = os.environ.get("SYNAPPS_MASTER_KEY", "")

ADMIN_KEY_SCOPES = frozenset({"read", "write", "admin"})






def require_master_key(
    x_api_key: str | None = Header(None, alias="X-API-Key"),
    authorization: str | None = Header(None, alias="Authorization"),
) -> str:
    """Dependency that requires the SYNAPPS_MASTER_KEY for admin operations."""
    master = SYNAPPS_MASTER_KEY
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


DEFAULT_MEMORY_BACKEND = os.environ.get("MEMORY_BACKEND", "sqlite_fts").strip().lower()
DEFAULT_MEMORY_NAMESPACE = os.environ.get("MEMORY_NAMESPACE", "default").strip() or "default"
DEFAULT_MEMORY_SQLITE_PATH = str(
    Path(os.environ.get("MEMORY_SQLITE_PATH", project_root / "synapps_memory.db")).expanduser()
)
DEFAULT_MEMORY_CHROMA_PATH = str(
    Path(os.environ.get("MEMORY_CHROMA_PATH", project_root / ".chroma")).expanduser()
)
DEFAULT_MEMORY_COLLECTION = (
    os.environ.get("MEMORY_COLLECTION", "synapps_memory").strip() or "synapps_memory"
)
LEGACY_WRITER_LLM_PRESET: dict[str, Any] = {
    "label": "Writer",
    "provider": "openai",
    "model": "gpt-4o",
    "temperature": 0.7,
    "max_tokens": 1000,
}
LEGACY_ARTIST_IMAGE_PRESET: dict[str, Any] = {
    "label": "Image Gen",
    "provider": "stability",
    "model": "stable-diffusion-xl-1024-v1-0",
    "size": "1024x1024",
    "style": "photorealistic",
    "quality": "standard",
    "n": 1,
    "response_format": "b64_json",
}
LEGACY_MEMORY_BACKEND_ALIASES: dict[str, str] = {
    "sqlite": "sqlite_fts",
    "sqlite_fts": "sqlite_fts",
    "sqlite-fts": "sqlite_fts",
    "sqlitefts": "sqlite_fts",
    "fts": "sqlite_fts",
    "chroma": "chroma",
    "chromadb": "chroma",
    "chroma_db": "chroma",
}
_TRUE_BRANCH_HINTS = {
    "true",
    "then",
    "yes",
    "pass",
    "match",
    "matched",
    "on_true",
    "if_true",
}
_FALSE_BRANCH_HINTS = {
    "false",
    "else",
    "no",
    "fail",
    "nomatch",
    "not_match",
    "on_false",
    "if_false",
}

# ============================================================
# Application Setup
# ============================================================

# Interval between key-expiry checks (seconds).
KEY_EXPIRY_CHECK_INTERVAL = 3600
# Warn about keys expiring within this window (seconds) — 24 hours.
KEY_EXPIRY_WARNING_WINDOW = 86400


async def _key_expiry_watcher() -> None:
    """Background loop that emits ``key.expiring_soon`` for nearly-expired keys."""
    while True:
        try:
            await asyncio.sleep(KEY_EXPIRY_CHECK_INTERVAL)
            expiring = api_key_manager.keys_expiring_within(KEY_EXPIRY_WARNING_WINDOW)
            for key_rec in expiring:
                await emit_event(
                    "key.expiring_soon",
                    {
                        "key_id": key_rec["id"],
                        "name": key_rec.get("name"),
                        "expires_at": key_rec.get("expires_at"),
                    },
                )
        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("key_expiry_watcher error")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for database initialization and cleanup."""
    # Validate configuration on startup — fail fast with clear messages
    config_errors = app_config.validate()
    if config_errors:
        for err in config_errors:
            logger.error(f"Configuration error: {err}")
        if app_config.production:
            raise RuntimeError(
                f"Configuration validation failed ({len(config_errors)} error(s)). "
                f"Fix the issues above before starting in production mode."
            )
        else:
            logger.warning(
                f"Configuration has {len(config_errors)} warning(s) — "
                f"continuing in development mode."
            )
    logger.info("Initializing database...")
    await init_db()
    logger.info("Database initialization complete")
    # Start background key-expiry watcher
    expiry_task = asyncio.create_task(_key_expiry_watcher())
    await SchedulerService.start()
    _seed_marketplace_listings()
    yield
    await SchedulerService.stop()
    expiry_task.cancel()
    logger.info("Closing database connections...")
    await close_db_connections()
    logger.info("Database connections closed")


app = FastAPI(
    title="SynApps Orchestrator",
    description=(
        "Visual AI workflow builder API. Connect specialized AI agent nodes, "
        "execute workflows in real-time, and manage LLM provider integrations. "
        "Authenticate via JWT bearer tokens or API keys."
    ),
    version=API_VERSION,
    lifespan=lifespan,
    openapi_url="/api/v1/openapi.json",
    docs_url="/api/v1/docs",
    redoc_url="/api/v1/redoc",
    openapi_tags=[
        {"name": "Auth", "description": "Registration, login, token refresh, API key management."},
        {
            "name": "Flows",
            "description": "Create, list, update, delete, import, and export workflows.",
        },
        {
            "name": "Runs",
            "description": "Execute workflows and inspect run results, traces, and diffs.",
        },
        {"name": "Providers", "description": "LLM and image generation provider registries."},
        {"name": "Applets", "description": "Node type catalog (registered applet metadata)."},
        {
            "name": "Dashboard",
            "description": "Portfolio health, template status, provider overview.",
        },
        {"name": "Health", "description": "Service health checks."},
    ],
)

# ============================================================
# CORS Configuration (environment-aware)
# ============================================================
_is_production = os.environ.get("PRODUCTION", "false").strip().lower() in {"1", "true", "yes"}


def _is_secure_request(request: Request) -> bool:
    """Return True when the incoming request is HTTPS (direct or proxy-terminated)."""
    if request.url.scheme.lower() == "https":
        return True

    # Common reverse-proxy hint (e.g. nginx, ALB, ingress).
    forwarded_proto = request.headers.get("x-forwarded-proto", "")
    if forwarded_proto:
        proto = forwarded_proto.split(",", 1)[0].strip().lower()
        if proto == "https":
            return True

    # RFC 7239 Forwarded header support.
    forwarded = request.headers.get("forwarded", "")
    if forwarded:
        match = re.search(r"(?:^|[;,\s])proto=(https)(?:[;,\s]|$)", forwarded, flags=re.IGNORECASE)
        if match:
            return True

    return False


if _is_production:

    @app.middleware("http")
    async def enforce_https_in_production(request: Request, call_next):
        """Fail closed in production when traffic is not served over HTTPS."""
        if not _is_secure_request(request):
            return _error_response(
                426,
                "HTTPS_REQUIRED",
                "HTTPS is required in production.",
            )

        response = await call_next(request)
        response.headers.setdefault(
            "Strict-Transport-Security",
            "max-age=31536000; includeSubDomains; preload",
        )
        return response


_cors_raw = os.environ.get("BACKEND_CORS_ORIGINS", "")
_cors_origins = [o.strip() for o in _cors_raw.split(",") if o.strip()]

if _is_production and not _cors_origins:
    logger.error(
        "BACKEND_CORS_ORIGINS is required in production. "
        "Set it to a comma-separated list of allowed origins."
    )
    # Fail-closed: no origins allowed if unset in production
    _cors_origins = []
elif not _cors_origins:
    logger.warning("No CORS origins specified, allowing localhost origins in development mode")
    _cors_origins = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ]

# In production, never allow wildcard origins or credentials-with-wildcard
if _is_production and "*" in _cors_origins:
    logger.error("Wildcard CORS origin '*' is not allowed in production, removing it")
    _cors_origins = [o for o in _cors_origins if o != "*"]

_cors_methods = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
_cors_headers = [
    "Authorization",
    "Content-Type",
    "X-API-Key",
    "X-Requested-With",
    "Accept",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=_cors_methods,
    allow_headers=_cors_headers,
    expose_headers=[
        "X-RateLimit-Limit",
        "X-RateLimit-Remaining",
        "X-RateLimit-Reset",
        "Retry-After",
        "X-Request-ID",
        "X-API-Version",
        "Deprecation",
        "Sunset",
        "X-Quota-Warning",
        "X-Quota-Remaining",
    ],
    max_age=600 if _is_production else 0,
)

# ============================================================
# Rate Limiting
# ============================================================
from apps.orchestrator.middleware.rate_limiter import add_rate_limiter  # noqa: E402

add_rate_limiter(app)


# ============================================================
# API Key Manager (Fernet-encrypted, scoped, rotation)
# ============================================================
from apps.orchestrator.api_keys.manager import api_key_manager  # noqa: E402


async def _resolve_rate_limit_user(request: Request) -> dict[str, Any] | None:
    """Best-effort auth parsing for per-user rate-limit keys."""
    x_api_key = request.headers.get("X-API-Key")
    authorization = request.headers.get("Authorization")

    try:
        if x_api_key and x_api_key.strip():
            stripped = x_api_key.strip()
            # Check admin key registry first for sk- prefixed keys
            if stripped.startswith("sk-"):
                admin_key = admin_key_registry.validate_key(stripped)
                if admin_key:
                    principal = {
                        "id": f"admin-key:{admin_key['id']}",
                        "tier": "enterprise",
                    }
                    if admin_key.get("rate_limit") is not None:
                        principal["rate_limit"] = admin_key["rate_limit"]
                    return principal
            principal = await _authenticate_user_by_api_key(stripped)
            principal.setdefault("tier", "free")
            return principal

        if authorization:
            auth_text = authorization.strip()
            if auth_text.lower().startswith("bearer "):
                principal = await _authenticate_user_by_jwt(auth_text[7:].strip())
                principal.setdefault("tier", "free")
                return principal
            if auth_text.lower().startswith("apikey "):
                principal = await _authenticate_user_by_api_key(auth_text[7:].strip())
                principal.setdefault("tier", "free")
                return principal
    except HTTPException:
        # Invalid credentials are handled by endpoint auth dependencies.
        return None
    except Exception as exc:  # noqa: BLE001
        logger.warning("Unexpected error in optional auth resolution: %s", exc)
        return None

    return None


def _anonymous_rate_limit_principal(request: Request) -> dict[str, Any]:
    """Build a stable anonymous principal from the direct socket client."""
    client_host = request.client.host if request.client else "unknown"
    return {
        "id": f"anonymous:{client_host}",
        "tier": "anonymous",
    }


@app.middleware("http")
async def enforce_quota(request: Request, call_next):
    """Block requests when the consumer's monthly quota is exhausted.

    Registered *before* ``attach_rate_limit_identity`` so that in the LIFO
    middleware onion this runs *inside* it — ``request.state.user`` is already
    populated.  Returns 429 with ``Retry-After`` set to the number of seconds
    until the next month boundary.
    Adds ``X-Quota-Warning: true`` header when usage >= 80 %.
    """
    user = getattr(request.state, "user", None)
    key_id = user.get("id", "") if user else ""

    if key_id and not key_id.startswith("anonymous"):
        status = usage_tracker.check_quota(key_id)
        if not status["allowed"]:
            return JSONResponse(
                status_code=429,
                content={
                    "error": {
                        "code": "QUOTA_EXCEEDED",
                        "status": 429,
                        "message": (
                            "Monthly request quota exceeded. "
                            f"Used {status['used']}/{status['quota']}. "
                            "Quota resets on the 1st of next month."
                        ),
                    }
                },
                headers={
                    "Retry-After": str(status["retry_after"]),
                    "X-Quota-Remaining": "0",
                },
            )

    response = await call_next(request)

    # Attach warning header when nearing quota
    if key_id and not key_id.startswith("anonymous"):
        status = usage_tracker.check_quota(key_id)
        if status["warning"]:
            response.headers["X-Quota-Warning"] = "true"
            response.headers["X-Quota-Remaining"] = str(status.get("remaining", 0))

    return response


@app.middleware("http")
async def attach_rate_limit_identity(request: Request, call_next):
    """Attach authenticated principal to request state for per-user rate limiting."""
    principal = await _resolve_rate_limit_user(request)
    if principal is None:
        principal = _anonymous_rate_limit_principal(request)
    request.state.user = principal
    return await call_next(request)


@app.middleware("http")
async def collect_metrics(request: Request, call_next):
    """Record request count, duration, and status for /metrics."""
    start = time.monotonic()
    response = await call_next(request)
    duration_ms = (time.monotonic() - start) * 1000
    metrics.record_request(duration_ms, response.status_code, request.url.path)

    # Track per-consumer usage (user is set by attach_rate_limit_identity)
    user = getattr(request.state, "user", None)
    key_id = user.get("id", "") if user else ""
    if key_id and not key_id.startswith("anonymous"):
        # Estimate response size from content-length header
        content_length = int(response.headers.get("content-length", "0") or "0")
        usage_tracker.record(
            key_id=key_id,
            path=request.url.path,
            status_code=response.status_code,
            response_size=content_length,
        )

    # Emit request.failed webhook for server errors (5xx)
    if response.status_code >= 500:
        await emit_event(
            "request.failed",
            {
                "path": request.url.path,
                "method": request.method,
                "status_code": response.status_code,
                "duration_ms": round(duration_ms, 2),
            },
        )
    return response


@app.middleware("http")
async def request_id_tracing(request: Request, call_next):
    """Assign a unique request ID, propagate it via contextvar, and log the request.

    Failed requests (status >= 400) are captured in :data:`failed_request_store`
    for later replay / debug inspection.
    """
    # Accept client-provided request ID or generate one
    request_id = request.headers.get("X-Request-ID", "").strip() or uuid.uuid4().hex[:16]
    request.state.request_id = request_id

    # Cache the request body so we can store it on failure
    try:
        request_body_bytes = await request.body()
    except Exception:
        request_body_bytes = b""

    # Set contextvar so all log calls during this request include the ID
    token = _current_request_id.set(request_id)
    start = time.monotonic()
    try:
        response = await call_next(request)
        duration_ms = round((time.monotonic() - start) * 1000, 2)

        response.headers["X-Request-ID"] = request_id
        response.headers["X-API-Version"] = API_VERSION_DATE

        # Deprecation headers
        dep_info = deprecation_registry.lookup(request.method, request.url.path)
        if dep_info:
            response.headers["Deprecation"] = "true"
            response.headers["Sunset"] = dep_info["sunset"]
            if dep_info.get("successor"):
                response.headers["Link"] = f'<{dep_info["successor"]}>; rel="successor-version"'

        # Structured request log (while contextvar is still set)
        logger.info(
            "%s %s %s %.1fms",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            extra={
                "endpoint": request.url.path,
                "method": request.method,
                "status": response.status_code,
                "duration_ms": duration_ms,
                "client_ip": request.client.host if request.client else "unknown",
            },
        )

        # Capture failed requests for replay/debug
        if response.status_code >= 400:
            # Read response body from the streaming response
            resp_body_parts: list[bytes] = []
            async for chunk in response.body_iterator:  # type: ignore[union-attr]
                if isinstance(chunk, str):
                    resp_body_parts.append(chunk.encode("utf-8"))
                else:
                    resp_body_parts.append(chunk)
            resp_body_bytes = b"".join(resp_body_parts)

            try:
                resp_body_str = resp_body_bytes.decode("utf-8", errors="replace")
            except Exception:
                resp_body_str = "<binary>"

            try:
                req_body_str = request_body_bytes.decode("utf-8", errors="replace")
            except Exception:
                req_body_str = "<binary>"

            failed_request_store.add(
                {
                    "request_id": request_id,
                    "timestamp": time.time(),
                    "method": request.method,
                    "path": str(request.url),
                    "request_headers": dict(request.headers),
                    "request_body": req_body_str,
                    "response_status": response.status_code,
                    "response_headers": dict(response.headers),
                    "response_body": resp_body_str,
                    "duration_ms": duration_ms,
                    "client_ip": request.client.host if request.client else "unknown",
                }
            )

            # Rebuild the response since we consumed the body iterator
            from starlette.responses import Response as StarletteResponse

            return StarletteResponse(
                content=resp_body_bytes,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type,
            )

        return response
    finally:
        _current_request_id.reset(token)


# ============================================================
# Error Handling - Consistent Error Format
# ============================================================

_HTTP_ERROR_CODES = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    409: "CONFLICT",
    422: "VALIDATION_ERROR",
    429: "RATE_LIMIT_EXCEEDED",
    500: "INTERNAL_SERVER_ERROR",
    501: "NOT_IMPLEMENTED",
    503: "SERVICE_UNAVAILABLE",
}


def _error_response(
    status: int,
    code: str,
    message: str,
    details: list[dict[str, Any]] | None = None,
) -> JSONResponse:
    """Create a standardized error JSONResponse."""
    body: dict[str, Any] = {
        "error": {
            "code": code,
            "status": status,
            "message": message,
        }
    }
    if details is not None:
        body["error"]["details"] = details
    return JSONResponse(status_code=status, content=body)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    code = _HTTP_ERROR_CODES.get(exc.status_code, "ERROR")
    # Preserve headers from the HTTPException (e.g. Retry-After from quota enforcement)
    extra_headers: dict[str, str] = dict(exc.headers) if exc.headers else {}
    response = _error_response(exc.status_code, code, str(exc.detail))
    for header_name, header_value in extra_headers.items():
        response.headers[header_name] = header_value
    return response


@app.exception_handler(StarletteHTTPException)
async def starlette_http_exception_handler(request: Request, exc: StarletteHTTPException):
    code = _HTTP_ERROR_CODES.get(exc.status_code, "ERROR")
    detail = exc.detail if isinstance(exc.detail, str) else "Request error"
    return _error_response(exc.status_code, code, detail)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    details = []
    for err in exc.errors():
        field = ".".join(str(loc) for loc in err.get("loc", []))
        details.append(
            {
                "field": field,
                "message": err.get("msg", ""),
                "type": err.get("type", ""),
            }
        )
    return _error_response(422, "VALIDATION_ERROR", "Request validation failed", details)


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return _error_response(500, "INTERNAL_SERVER_ERROR", "An unexpected error occurred")


# ============================================================
# Pagination
# ============================================================


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


# ============================================================
# Request Validation Models (Pydantic v2 strict)
# ============================================================


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


def _trace_value(value: Any, depth: int = 0) -> Any:
    """Convert arbitrary values into a JSON-serializable structure."""
    if depth >= 8:
        return str(value)

    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, dict):
        return {str(k): _trace_value(v, depth + 1) for k, v in value.items()}

    if isinstance(value, (list, tuple, set)):
        return [_trace_value(v, depth + 1) for v in list(value)]

    if isinstance(value, BaseModel):
        return _trace_value(value.model_dump(), depth + 1)

    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        try:
            return _trace_value(model_dump(), depth + 1)
        except Exception:
            return str(value)

    return str(value)


def _new_execution_trace(
    run_id: str,
    flow_id: str | None,
    input_data: dict[str, Any],
    start_time: float,
) -> dict[str, Any]:
    """Create a baseline execution trace document for a run."""
    return {
        "version": TRACE_SCHEMA_VERSION,
        "run_id": run_id,
        "flow_id": flow_id,
        "status": "running",
        "input": _trace_value(input_data),
        "started_at": float(start_time),
        "ended_at": None,
        "duration_ms": None,
        "nodes": [],
        "errors": [],
    }


def _finalize_execution_trace(trace: dict[str, Any], status: str, end_time: float) -> None:
    """Finalize aggregate timing/status fields in a trace object."""
    trace["status"] = status
    trace["ended_at"] = float(end_time)
    started_at = trace.get("started_at")
    if isinstance(started_at, (int, float)):
        trace["duration_ms"] = max(0.0, (float(end_time) - float(started_at)) * 1000.0)


def _extract_trace_from_run(run: dict[str, Any]) -> dict[str, Any]:
    """Return a normalized execution trace for any run, including legacy runs."""
    run_id = str(run.get("run_id", ""))
    flow_id = run.get("flow_id")
    start_time = run.get("start_time")
    if not isinstance(start_time, (int, float)):
        start_time = time.time()

    input_data = run.get("input_data")
    if not isinstance(input_data, dict):
        input_data = {}

    results = run.get("results")
    if not isinstance(results, dict):
        results = {}

    stored_trace = results.get(TRACE_RESULTS_KEY)
    if isinstance(stored_trace, dict):
        trace = _trace_value(stored_trace)
        if not isinstance(trace, dict):
            trace = _new_execution_trace(run_id, flow_id, input_data, float(start_time))
    else:
        trace = _new_execution_trace(run_id, flow_id, input_data, float(start_time))
        nodes: list[dict[str, Any]] = []
        for node_id, node_result in results.items():
            if node_id == TRACE_RESULTS_KEY:
                continue
            if isinstance(node_result, dict):
                error_payload = node_result.get("error")
                node_errors = []
                if error_payload is not None:
                    node_errors.append(_trace_value(error_payload))
                nodes.append(
                    {
                        "node_id": str(node_id),
                        "node_type": node_result.get("type"),
                        "status": node_result.get("status", "success"),
                        "input": _trace_value(node_result.get("input")),
                        "output": _trace_value(node_result.get("output")),
                        "attempts": node_result.get("attempts", 1),
                        "errors": node_errors,
                        "started_at": node_result.get("started_at"),
                        "ended_at": node_result.get("ended_at"),
                        "duration_ms": node_result.get("duration_ms"),
                    }
                )
            else:
                nodes.append(
                    {
                        "node_id": str(node_id),
                        "node_type": None,
                        "status": "success",
                        "input": None,
                        "output": _trace_value(node_result),
                        "attempts": 1,
                        "errors": [],
                    }
                )
        trace["nodes"] = nodes

    trace["run_id"] = run_id
    trace["flow_id"] = flow_id
    trace["status"] = str(run.get("status", trace.get("status", "unknown")))

    trace_start = trace.get("started_at")
    if not isinstance(trace_start, (int, float)):
        trace_start = float(start_time)
        trace["started_at"] = trace_start

    end_time = run.get("end_time")
    if isinstance(end_time, (int, float)):
        trace["ended_at"] = float(end_time)
        trace["duration_ms"] = max(0.0, (float(end_time) - float(trace_start)) * 1000.0)
    elif trace.get("ended_at") is None and trace.get("status") in {"success", "error"}:
        trace["ended_at"] = float(trace_start)
        trace["duration_ms"] = 0.0

    trace_input = trace.get("input")
    if not isinstance(trace_input, dict):
        trace["input"] = _trace_value(input_data)

    if not isinstance(trace.get("nodes"), list):
        trace["nodes"] = []
    if not isinstance(trace.get("errors"), list):
        trace["errors"] = []

    return trace


def _flatten_for_diff(value: Any, path: str, out: dict[str, Any]) -> None:
    """Flatten nested structures into a path/value map for deterministic diffing."""
    if isinstance(value, dict):
        if not value:
            out[path] = {}
            return
        for key in sorted(value.keys(), key=lambda k: str(k)):
            child_path = f"{path}.{key}"
            _flatten_for_diff(value[key], child_path, out)
        return

    if isinstance(value, list):
        if not value:
            out[path] = []
            return
        for index, item in enumerate(value):
            _flatten_for_diff(item, f"{path}[{index}]", out)
        return

    out[path] = value


def _build_json_diff(left: Any, right: Any, max_changes: int = MAX_DIFF_CHANGES) -> dict[str, Any]:
    """Build a bounded structural diff between two JSON-like values."""
    left_normalized = _trace_value(left)
    right_normalized = _trace_value(right)

    left_flat: dict[str, Any] = {}
    right_flat: dict[str, Any] = {}
    _flatten_for_diff(left_normalized, "$", left_flat)
    _flatten_for_diff(right_normalized, "$", right_flat)

    all_paths = sorted(set(left_flat.keys()) | set(right_flat.keys()))
    changes: list[dict[str, Any]] = []
    total_changes = 0

    for path in all_paths:
        in_left = path in left_flat
        in_right = path in right_flat
        if in_left and in_right and left_flat[path] == right_flat[path]:
            continue

        total_changes += 1
        if len(changes) >= max_changes:
            continue

        if in_left and not in_right:
            change_type = "removed"
        elif in_right and not in_left:
            change_type = "added"
        else:
            change_type = "modified"

        changes.append(
            {
                "path": path,
                "type": change_type,
                "before": left_flat.get(path),
                "after": right_flat.get(path),
            }
        )

    return {
        "changed": total_changes > 0,
        "change_count": total_changes,
        "truncated": total_changes > max_changes,
        "changes": changes,
    }


def _node_result_index(run: dict[str, Any]) -> dict[str, Any]:
    """Return run result payload keyed by node ID, excluding trace metadata."""
    results = run.get("results")
    if not isinstance(results, dict):
        return {}
    return {
        str(node_id): _trace_value(result)
        for node_id, result in results.items()
        if node_id != TRACE_RESULTS_KEY
    }


def _build_run_diff(base_run: dict[str, Any], compare_run: dict[str, Any]) -> dict[str, Any]:
    """Compute an execution diff between two runs."""
    base_trace = _extract_trace_from_run(base_run)
    compare_trace = _extract_trace_from_run(compare_run)

    base_nodes = {
        str(item.get("node_id")): item
        for item in base_trace.get("nodes", [])
        if isinstance(item, dict) and item.get("node_id") is not None
    }
    compare_nodes = {
        str(item.get("node_id")): item
        for item in compare_trace.get("nodes", [])
        if isinstance(item, dict) and item.get("node_id") is not None
    }

    node_diffs: list[dict[str, Any]] = []
    for node_id in sorted(set(base_nodes.keys()) | set(compare_nodes.keys())):
        left = base_nodes.get(node_id)
        right = compare_nodes.get(node_id)
        if left is None:
            node_diffs.append({"node_id": node_id, "type": "added", "after": _trace_value(right)})
            continue
        if right is None:
            node_diffs.append({"node_id": node_id, "type": "removed", "before": _trace_value(left)})
            continue

        left_duration = left.get("duration_ms")
        right_duration = right.get("duration_ms")
        duration_delta = None
        if isinstance(left_duration, (int, float)) and isinstance(right_duration, (int, float)):
            duration_delta = float(right_duration) - float(left_duration)

        status_before = left.get("status")
        status_after = right.get("status")
        attempts_before = left.get("attempts")
        attempts_after = right.get("attempts")

        node_changed = left != right
        if not node_changed:
            continue

        node_diffs.append(
            {
                "node_id": node_id,
                "type": "modified",
                "status": {
                    "before": status_before,
                    "after": status_after,
                    "changed": status_before != status_after,
                },
                "attempts": {
                    "before": attempts_before,
                    "after": attempts_after,
                    "changed": attempts_before != attempts_after,
                },
                "duration_ms": {
                    "before": left_duration,
                    "after": right_duration,
                    "delta_ms": duration_delta,
                },
                "input_changed": left.get("input") != right.get("input"),
                "output_changed": left.get("output") != right.get("output"),
                "errors_changed": left.get("errors") != right.get("errors"),
            }
        )

    base_duration = base_trace.get("duration_ms")
    compare_duration = compare_trace.get("duration_ms")
    duration_delta_ms = None
    if isinstance(base_duration, (int, float)) and isinstance(compare_duration, (int, float)):
        duration_delta_ms = float(compare_duration) - float(base_duration)

    return {
        "base_run_id": base_run.get("run_id"),
        "compare_run_id": compare_run.get("run_id"),
        "flow_id": base_run.get("flow_id") or compare_run.get("flow_id"),
        "summary": {
            "base_status": base_run.get("status"),
            "compare_status": compare_run.get("status"),
            "status_changed": base_run.get("status") != compare_run.get("status"),
            "base_node_count": len(base_nodes),
            "compare_node_count": len(compare_nodes),
            "changed_node_count": len(node_diffs),
        },
        "timing": {
            "base_duration_ms": base_duration,
            "compare_duration_ms": compare_duration,
            "duration_delta_ms": duration_delta_ms,
        },
        "input_diff": _build_json_diff(base_trace.get("input", {}), compare_trace.get("input", {})),
        "output_diff": _build_json_diff(
            _node_result_index(base_run), _node_result_index(compare_run)
        ),
        "trace_diff": _build_json_diff(base_trace, compare_trace),
        "node_diffs": node_diffs,
        "base_trace": base_trace,
        "compare_trace": compare_trace,
    }


# ============================================================
# Authentication Utilities
# ============================================================


def _utc_now() -> float:
    return time.time()


def _hash_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _derive_fernet_key() -> bytes:
    configured = os.environ.get("FERNET_KEY", "").strip()
    if configured:
        try:
            return configured.encode("utf-8")
        except Exception:
            logger.warning("Invalid FERNET_KEY value; falling back to derived key")
    digest = hashlib.sha256(JWT_SECRET_KEY.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


FERNET_CIPHER = Fernet(_derive_fernet_key())

# Now that FERNET_CIPHER is ready, re-init the webhook manager with encryption.
_init_webhook_manager()
_init_webhook_trigger_registry()


def _encrypt_api_key(plain_value: str) -> str:
    return FERNET_CIPHER.encrypt(plain_value.encode("utf-8")).decode("utf-8")


def _decrypt_api_key(encrypted_value: str) -> str | None:
    try:
        return FERNET_CIPHER.decrypt(encrypted_value.encode("utf-8")).decode("utf-8")
    except (InvalidToken, ValueError, TypeError):
        return None


def _hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PASSWORD_HASH_ITERATIONS,
    )
    salt_text = base64.urlsafe_b64encode(salt).decode("utf-8")
    hash_text = base64.urlsafe_b64encode(digest).decode("utf-8")
    return f"pbkdf2_sha256${PASSWORD_HASH_ITERATIONS}${salt_text}${hash_text}"


def _verify_password(password: str, password_hash: str) -> bool:
    try:
        scheme, raw_iterations, salt_text, hash_text = password_hash.split("$", 3)
        if scheme != "pbkdf2_sha256":
            return False
        iterations = int(raw_iterations)
        salt = base64.urlsafe_b64decode(salt_text.encode("utf-8"))
        expected = base64.urlsafe_b64decode(hash_text.encode("utf-8"))
    except Exception:
        return False

    candidate = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        iterations,
    )
    return hmac.compare_digest(candidate, expected)


def _create_access_token(user: AuthUser) -> tuple[str, int]:
    now = int(_utc_now())
    expiry = now + ACCESS_TOKEN_EXPIRE_MINUTES * 60
    payload = {
        "sub": user.id,
        "email": user.email,
        "token_type": "access",
        "iat": now,
        "exp": expiry,
    }
    token = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    return token, expiry - now


def _create_refresh_token(user: AuthUser) -> tuple[str, float, int]:
    now = int(_utc_now())
    expiry = now + REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60
    payload = {
        "sub": user.id,
        "email": user.email,
        "token_type": "refresh",
        "jti": str(uuid.uuid4()),
        "iat": now,
        "exp": expiry,
    }
    token = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    return token, float(expiry), expiry - now


def _decode_token(token: str, expected_type: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(
            token,
            JWT_SECRET_KEY,
            algorithms=[JWT_ALGORITHM],
        )
    except jwt.ExpiredSignatureError as err:
        raise HTTPException(status_code=401, detail="Token expired") from err
    except jwt.InvalidTokenError as err:
        raise HTTPException(status_code=401, detail="Invalid token") from err

    token_type = payload.get("token_type")
    if token_type != expected_type:
        raise HTTPException(status_code=401, detail="Invalid token type")
    return payload


def _issue_api_tokens(user: AuthUser) -> tuple[AuthTokenResponseModel, str, float]:
    access_token, access_expires_in = _create_access_token(user)
    refresh_token, refresh_expires_at, refresh_expires_in = _create_refresh_token(user)
    response_payload = AuthTokenResponseModel(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        access_expires_in=access_expires_in,
        refresh_expires_in=refresh_expires_in,
    )
    return response_payload, refresh_token, refresh_expires_at


def _normalize_key_header_value(raw_value: str) -> str:
    return raw_value.strip()


def _api_key_lookup_prefix(api_key_value: str) -> str:
    return api_key_value[:API_KEY_LOOKUP_PREFIX_LEN]


def _user_to_principal(user: AuthUser) -> dict[str, Any]:
    return {
        "id": user.id,
        "email": user.email,
        "is_active": user.is_active,
        "created_at": user.created_at,
    }


async def _store_refresh_token(
    user_id: str,
    refresh_token: str,
    expires_at: float,
) -> None:
    token_hash = _hash_sha256(refresh_token)
    async with get_db_session() as session:
        session.add(
            AuthRefreshToken(
                id=str(uuid.uuid4()),
                user_id=user_id,
                token_hash=token_hash,
                expires_at=expires_at,
                revoked=False,
                created_at=_utc_now(),
                last_used_at=None,
            )
        )


async def _authenticate_user_by_jwt(access_token: str) -> dict[str, Any]:
    payload = _decode_token(access_token, expected_type="access")
    user_id = payload.get("sub")
    if not isinstance(user_id, str) or not user_id:
        raise HTTPException(status_code=401, detail="Invalid access token subject")

    async with get_db_session() as session:
        result = await session.execute(select(AuthUser).where(AuthUser.id == user_id))
        user = result.scalars().first()
        if not user or not user.is_active:
            raise HTTPException(status_code=401, detail="User is not active")
        return _user_to_principal(user)


async def _authenticate_user_by_api_key(api_key_value: str) -> dict[str, Any]:
    normalized_key = _normalize_key_header_value(api_key_value)
    if not normalized_key:
        raise HTTPException(status_code=401, detail="Invalid API key")

    lookup_prefix = _api_key_lookup_prefix(normalized_key)

    async with get_db_session() as session:
        query = select(AuthUserAPIKey).where(
            AuthUserAPIKey.is_active == True,  # noqa: E712 - SQLAlchemy boolean comparison
            AuthUserAPIKey.key_prefix == lookup_prefix,
        )
        result = await session.execute(query)
        candidates = result.scalars().all()

        for credential in candidates:
            plain_key = _decrypt_api_key(credential.encrypted_key)
            if plain_key is None:
                continue
            if not hmac.compare_digest(plain_key, normalized_key):
                continue

            user_result = await session.execute(
                select(AuthUser).where(AuthUser.id == credential.user_id)
            )
            user = user_result.scalars().first()
            if not user or not user.is_active:
                break

            credential.last_used_at = _utc_now()
            return _user_to_principal(user)

    raise HTTPException(status_code=401, detail="Invalid API key")


async def _can_use_anonymous_bootstrap() -> bool:
    if not ALLOW_ANONYMOUS_WHEN_NO_USERS:
        return False
    try:
        async with get_db_session() as session:
            result = await session.execute(select(AuthUser.id).limit(1))
            first_user_id = result.scalar_one_or_none()
            return first_user_id is None
    except Exception:
        # Allow bootstrap traffic before auth tables are initialized.
        return True


async def get_authenticated_user(
    authorization: str | None = Header(None, alias="Authorization"),
    x_api_key: str | None = Header(None, alias="X-API-Key"),
) -> dict[str, Any]:
    if x_api_key:
        stripped = x_api_key.strip()
        # Recognise admin API keys (sk- prefix) from the in-memory registry
        if stripped.startswith("sk-"):
            admin_key = admin_key_registry.validate_key(stripped)
            if admin_key:
                return {
                    "id": f"admin-key:{admin_key['id']}",
                    "email": f"admin-key@{admin_key['name']}",
                    "is_active": True,
                    "scopes": admin_key.get("scopes", []),
                    "created_at": admin_key.get("created_at"),
                }
            # Try managed key registry (Fernet-encrypted)
            managed_key = api_key_manager.validate(stripped)
            if managed_key:
                return {
                    "id": f"managed-key:{managed_key['id']}",
                    "email": f"managed-key@{managed_key['name']}",
                    "is_active": True,
                    "scopes": managed_key.get("scopes", []),
                    "rate_limit": managed_key.get("rate_limit"),
                    "tier": "enterprise",
                    "created_at": managed_key.get("created_at"),
                }
        return await _authenticate_user_by_api_key(stripped)

    if authorization:
        auth_text = authorization.strip()
        if auth_text.lower().startswith("bearer "):
            return await _authenticate_user_by_jwt(auth_text[7:].strip())
        if auth_text.lower().startswith("apikey "):
            return await _authenticate_user_by_api_key(auth_text[7:].strip())

    if await _can_use_anonymous_bootstrap():
        return {
            "id": "anonymous",
            "email": "anonymous@local",
            "is_active": True,
            "created_at": _utc_now(),
        }

    raise HTTPException(status_code=401, detail="Authentication required")


# ============================================================
# Internal Models
# ============================================================


class AppletStatus(StrEnum):
    IDLE = "idle"
    RUNNING = "running"
    SUCCESS = "success"
    ERROR = "error"


class NodeErrorCode(StrEnum):
    TIMEOUT = "TIMEOUT"
    RETRY_EXHAUSTED = "RETRY_EXHAUSTED"
    EXECUTION_ERROR = "EXECUTION_ERROR"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    UNKNOWN_ERROR = "UNKNOWN_ERROR"


class NodeError(Exception):
    """Structured error for node execution."""

    def __init__(
        self,
        code: NodeErrorCode,
        message: str,
        details: dict[str, Any] | None = None,
        node_id: str | None = None,
    ):
        self.code = code
        self.message = message
        self.details = details or {}
        self.node_id = node_id
        super().__init__(self.message)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "details": self.details,
            "node_id": self.node_id,
        }


class FlowNode(BaseModel):
    id: str
    type: str
    position: dict[str, int]
    data: dict[str, Any] = Field(default_factory=dict)


class FlowEdge(BaseModel):
    id: str
    source: str
    target: str
    animated: bool = False


class Flow(BaseModel):
    id: str
    name: str
    nodes: list[FlowNode]
    edges: list[FlowEdge]


class AppletMessage(BaseModel):
    content: Any
    context: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkflowRunStatus(BaseModel):
    run_id: str
    flow_id: str
    status: str
    current_applet: str | None = None
    progress: int = 0
    total_steps: int = 0
    start_time: float = 0
    end_time: float | None = None
    results: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    error_details: dict[str, Any] = Field(default_factory=dict)
    completed_applets: list[str] = Field(default_factory=list)


# ============================================================
# WebSocket Protocol – structured messages, auth, reconnection
# ============================================================

WS_AUTH_TIMEOUT_SECONDS = int(os.environ.get("WS_AUTH_TIMEOUT_SECONDS", "10"))
WS_HEARTBEAT_INTERVAL = int(os.environ.get("WS_HEARTBEAT_INTERVAL", "30"))
WS_MESSAGE_BUFFER_SIZE = int(os.environ.get("WS_MESSAGE_BUFFER_SIZE", "200"))
WS_SESSION_TTL_SECONDS = int(os.environ.get("WS_SESSION_TTL_SECONDS", "300"))

applet_registry: dict[str, type["BaseApplet"]] = {}


def _ws_message(
    msg_type: str,
    data: dict | None = None,
    *,
    ref_id: str | None = None,
) -> dict:
    """Create a structured WebSocket message.

    Fields:
        id        – unique message identifier (UUIDv4)
        type      – dot-namespaced message type
        data      – payload dict
        timestamp – seconds since epoch (float)
        ref_id    – optional correlation ID linking a response to a request
    """
    msg: dict = {
        "id": str(uuid.uuid4()),
        "type": msg_type,
        "data": data or {},
        "timestamp": time.time(),
    }
    if ref_id:
        msg["ref_id"] = ref_id
    return msg


class _WSSession:
    """State for a single WebSocket session."""

    __slots__ = (
        "session_id",
        "user_id",
        "websocket",
        "subscriptions",
        "connected_at",
        "last_active",
        "state",
        "_message_seq",
    )

    def __init__(
        self,
        session_id: str,
        user_id: str,
        websocket: WebSocket | None = None,
    ) -> None:
        self.session_id = session_id
        self.user_id = user_id
        self.websocket = websocket
        self.subscriptions: set = set()
        self.connected_at = time.time()
        self.last_active = time.time()
        self.state = "connected"
        self._message_seq = 0

    def next_seq(self) -> int:
        self._message_seq += 1
        return self._message_seq


class WebSocketSessionManager:
    """Manages connected WebSocket clients, sessions, and message replay."""

    def __init__(self, buffer_size: int = WS_MESSAGE_BUFFER_SIZE) -> None:
        self._sessions: dict[str, _WSSession] = {}
        self._ws_to_session: dict[int, str] = {}  # id(websocket) -> session_id
        self._message_buffer: list[dict] = []
        self._buffer_size = buffer_size
        self._lock = threading.Lock()
        self._global_seq = 0

    # ------ session management ------

    def create_session(
        self,
        user_id: str,
        websocket: WebSocket,
        session_id: str | None = None,
    ) -> tuple:
        """Create or resume a session.  Returns (session, reconnected)."""
        reconnected = False
        with self._lock:
            if session_id and session_id in self._sessions:
                sess = self._sessions[session_id]
                if sess.user_id == user_id:
                    sess.websocket = websocket
                    sess.state = "connected"
                    sess.last_active = time.time()
                    reconnected = True
                else:
                    session_id = None

            if not reconnected:
                session_id = session_id or str(uuid.uuid4())
                sess = _WSSession(session_id, user_id, websocket)
                self._sessions[session_id] = sess

            self._ws_to_session[id(websocket)] = sess.session_id
        return sess, reconnected

    def remove_session(self, websocket: WebSocket) -> _WSSession | None:
        """Mark session as disconnected and unlink the websocket."""
        with self._lock:
            ws_id = id(websocket)
            sid = self._ws_to_session.pop(ws_id, None)
            if sid and sid in self._sessions:
                sess = self._sessions[sid]
                sess.websocket = None
                sess.state = "disconnected"
                sess.last_active = time.time()
                return sess
        return None

    def get_session_by_ws(self, websocket: WebSocket) -> _WSSession | None:
        with self._lock:
            sid = self._ws_to_session.get(id(websocket))
            return self._sessions.get(sid) if sid else None

    def connected_sessions(self) -> list[_WSSession]:
        """Return sessions that currently have a live websocket."""
        with self._lock:
            return [s for s in self._sessions.values() if s.websocket and s.state == "connected"]

    @property
    def connected_websockets(self) -> list[WebSocket]:
        """List of live websockets (backward-compatible helper)."""
        return [s.websocket for s in self.connected_sessions() if s.websocket]

    def cleanup_expired(self) -> int:
        """Purge sessions disconnected longer than TTL."""
        cutoff = time.time() - WS_SESSION_TTL_SECONDS
        removed = 0
        with self._lock:
            expired = [
                sid
                for sid, s in self._sessions.items()
                if s.state == "disconnected" and s.last_active < cutoff
            ]
            for sid in expired:
                del self._sessions[sid]
                removed += 1
        return removed

    # ------ message buffering for replay ------

    def _buffer_message(self, message: dict) -> None:
        self._global_seq += 1
        message["_seq"] = self._global_seq
        self._message_buffer.append(message)
        if len(self._message_buffer) > self._buffer_size:
            self._message_buffer = self._message_buffer[-self._buffer_size :]

    def get_missed_messages(self, last_seq: int) -> list[dict]:
        """Return messages with _seq > last_seq for reconnection replay."""
        with self._lock:
            return [m for m in self._message_buffer if m.get("_seq", 0) > last_seq]

    @property
    def current_seq(self) -> int:
        with self._lock:
            return self._global_seq

    # ------ broadcast helpers ------

    async def broadcast(self, message: dict) -> None:
        """Send a message to all connected clients and buffer it for replay."""
        with self._lock:
            self._buffer_message(message)
            sessions = [
                s for s in self._sessions.values() if s.websocket and s.state == "connected"
            ]

        disconnected: list[WebSocket] = []
        for sess in sessions:
            try:
                if sess.websocket:
                    await sess.websocket.send_json(message)
            except Exception as e:
                logger.error(f"Failed to send to session {sess.session_id}: {e}")
                if sess.websocket:
                    disconnected.append(sess.websocket)

        for ws in disconnected:
            self.remove_session(ws)


# Module-level manager instance
ws_manager = WebSocketSessionManager()

# Backward-compatible accessor (returns a fresh snapshot each call)
connected_clients: list[WebSocket] = []  # legacy shim – use ws_manager directly


async def broadcast_status(status: dict[str, Any]):
    """Broadcast workflow status to all connected clients using structured messages."""
    broadcast_data = status.copy()
    if "completed_applets" not in broadcast_data:
        broadcast_data["completed_applets"] = []

    message = _ws_message("workflow.status", broadcast_data)

    # Always route through session manager so messages are buffered for replay.
    await ws_manager.broadcast(message)

    # Legacy path: bare websockets appended to connected_clients directly (tests)
    if connected_clients:
        managed_ws_ids = {id(ws) for ws in ws_manager.connected_websockets}
        disconnected = []
        for client in connected_clients:
            # Avoid double-sending to sockets already tracked by ws_manager.
            if id(client) in managed_ws_ids:
                continue
            try:
                await client.send_json(message)
            except Exception as e:
                logger.error(f"Failed to send to legacy client: {e}")
                disconnected.append(client)
        for client in disconnected:
            if client in connected_clients:
                connected_clients.remove(client)


# ============================================================
# Base Applet
# ============================================================


class BaseApplet:
    """Base class that all applets must implement."""

    @classmethod
    def get_metadata(cls) -> dict[str, Any]:
        """Return applet metadata."""
        return {
            "name": cls.__name__,
            "description": cls.__doc__ or "No description provided",
            "version": getattr(cls, "VERSION", "0.1.0"),
            "capabilities": getattr(cls, "CAPABILITIES", []),
        }

    async def on_message(self, message: AppletMessage) -> AppletMessage:
        """Process an incoming message and return a response."""
        raise NotImplementedError("Applets must implement on_message")


# ============================================================
# LLM Providers / Adapters
# ============================================================


def _safe_json_loads(payload: str) -> dict[str, Any] | None:
    """Parse JSON string safely."""
    try:
        data = json.loads(payload)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        return None
    return None


async def _iter_sse_data_lines(response: httpx.Response) -> AsyncIterator[str]:
    """Yield SSE data payload lines from an HTTP response stream."""
    async for line in response.aiter_lines():
        if not line:
            continue
        if line.startswith("data:"):
            yield line[5:].strip()


def _as_text(content: Any) -> str:
    """Normalize arbitrary content payloads into prompt text."""
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        for key in ("prompt", "text", "input", "content", "message"):
            value = content.get(key)
            if isinstance(value, str) and value.strip():
                return value
        return json.dumps(content, ensure_ascii=False)
    return str(content)


def _as_serialized_text(content: Any) -> str:
    """Serialize arbitrary content into a durable text form."""
    if isinstance(content, str):
        return content
    if isinstance(content, (dict, list)):
        return json.dumps(content, ensure_ascii=False)
    return str(content)


def _parse_json_or_default(raw: str | None, default: Any) -> Any:
    """Parse JSON content and return a fallback value if parsing fails."""
    if not raw:
        return default
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return default


def _normalize_memory_tags(raw_tags: Any) -> list[str]:
    """Normalize memory tag payloads into a de-duplicated list of strings."""
    if raw_tags is None:
        return []
    if isinstance(raw_tags, str):
        candidates = [raw_tags]
    elif isinstance(raw_tags, list):
        candidates = [item for item in raw_tags if isinstance(item, (str, int, float))]
    else:
        return []

    tags: list[str] = []
    for item in candidates:
        cleaned = str(item).strip()
        if cleaned and cleaned not in tags:
            tags.append(cleaned)
    return tags


def _fts_terms(text: str) -> list[str]:
    """Build safe FTS terms from arbitrary free text."""
    cleaned = "".join(char if char.isalnum() else " " for char in text.lower())
    return [term for term in cleaned.split() if term]


_TEMPLATE_PATTERN = re.compile(r"\{\{\s*([a-zA-Z0-9_.-]+)\s*\}\}")


def _resolve_template_path(data: Any, path: str) -> tuple[Any, bool]:
    """Resolve a dotted path from nested dict/list payloads."""
    current = data
    for segment in path.split("."):
        if isinstance(current, dict):
            if segment not in current:
                return None, False
            current = current[segment]
            continue
        if isinstance(current, list):
            if not segment.isdigit():
                return None, False
            index = int(segment)
            if index < 0 or index >= len(current):
                return None, False
            current = current[index]
            continue
        return None, False
    return current, True


def _render_template_string(template: str, data: dict[str, Any]) -> Any:
    """Render {{path}} tokens in a string template."""
    matches = list(_TEMPLATE_PATTERN.finditer(template))
    if not matches:
        return template

    if len(matches) == 1 and matches[0].span() == (0, len(template)):
        value, found = _resolve_template_path(data, matches[0].group(1))
        return value if found else template

    def replace_token(match: re.Match[str]) -> str:
        path = match.group(1)
        value, found = _resolve_template_path(data, path)
        if not found or value is None:
            return ""
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False)
        return str(value)

    return _TEMPLATE_PATTERN.sub(replace_token, template)


def _render_template_payload(template: Any, data: dict[str, Any]) -> Any:
    """Render templates recursively for strings/dicts/lists."""
    if isinstance(template, str):
        return _render_template_string(template, data)
    if isinstance(template, list):
        return [_render_template_payload(item, data) for item in template]
    if isinstance(template, dict):
        return {key: _render_template_payload(value, data) for key, value in template.items()}
    return template


_JSON_PATH_SEGMENT_PATTERN = re.compile(
    r"\.([a-zA-Z0-9_\-]+)|\[(\d+)\]|\['([^']+)'\]|\[\"([^\"]+)\"\]"
)


def _parse_json_path(path: str) -> list[Any] | None:
    """Parse a restricted JSON path expression into key/index segments."""
    normalized = path.strip() or "$"
    if not normalized.startswith("$"):
        normalized = f"${normalized if normalized.startswith('.') else f'.{normalized}'}"

    if normalized == "$":
        return []

    segments: list[Any] = []
    index = 1
    while index < len(normalized):
        match = _JSON_PATH_SEGMENT_PATTERN.match(normalized, index)
        if not match:
            return None
        key = match.group(1) or match.group(3) or match.group(4)
        if key is not None:
            segments.append(key)
        else:
            raw_index = match.group(2)
            if raw_index is None:
                return None
            segments.append(int(raw_index))
        index = match.end()
    return segments


def _resolve_json_path(data: Any, path: str) -> tuple[Any, bool]:
    """Resolve a restricted JSON path against nested dictionaries/lists."""
    segments = _parse_json_path(path)
    if segments is None:
        return None, False

    current = data
    for segment in segments:
        if isinstance(segment, int):
            if not isinstance(current, list):
                return None, False
            if segment < 0 or segment >= len(current):
                return None, False
            current = current[segment]
            continue
        if not isinstance(current, dict):
            return None, False
        if segment not in current:
            return None, False
        current = current[segment]
    return current, True


def _safe_tmp_dir(path_value: str) -> str:
    """Normalize and enforce that a working directory stays under /tmp."""
    tmp_root = Path("/tmp").resolve()
    candidate = Path(path_value or "/tmp").expanduser()
    try:
        resolved = candidate.resolve(strict=False)
    except Exception:
        resolved = tmp_root
    if resolved == tmp_root or tmp_root in resolved.parents:
        return str(resolved)
    return str(tmp_root)


def _sandbox_preexec_fn(
    cpu_time_seconds: int,
    memory_limit_mb: int,
    max_output_bytes: int,
):
    """Build a pre-exec hook that applies OS-level resource limits."""
    if resource is None:
        return None

    memory_bytes = int(memory_limit_mb * 1024 * 1024)
    max_file_size = max(1024, int(max_output_bytes * 2))

    def _preexec() -> None:
        # NOTE: This function runs in the child process after fork(), before exec().
        # Logging is NOT safe here (may deadlock on inherited mutexes) — silence is
        # intentional.  Each setrlimit call is best-effort: if the platform or
        # container doesn't support a limit, we continue rather than aborting the
        # child startup.  All failures are implicitly visible via the absence of the
        # resource constraint (overrun → SIGXCPU / SIGKILL from parent timeout).
        try:
            os.setsid()
        except Exception:  # pragma: no cover - platform-dependent
            pass

        try:
            resource.setrlimit(resource.RLIMIT_CPU, (cpu_time_seconds, cpu_time_seconds))
        except Exception:  # pragma: no cover - unsupported on some kernels
            pass
        try:
            resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
        except Exception:  # pragma: no cover - unsupported on some kernels
            pass
        try:
            resource.setrlimit(resource.RLIMIT_FSIZE, (max_file_size, max_file_size))
        except Exception:  # pragma: no cover - unsupported on some kernels
            pass
        try:
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        except Exception:  # pragma: no cover - unsupported on some kernels
            pass
        try:
            resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
        except Exception:  # pragma: no cover - unsupported on some kernels
            pass
        try:
            resource.setrlimit(resource.RLIMIT_NPROC, (1, 1))  # Limit to a single process
        except Exception:  # pragma: no cover - unsupported on some kernels
            pass

    return _preexec


async def _read_stream_limited(
    stream: asyncio.StreamReader | None,
    max_bytes: int,
) -> tuple[bytes, bool]:
    """Read an async stream and cap captured bytes."""
    if stream is None:
        return b"", False

    chunks: list[bytes] = []
    total = 0
    truncated = False

    while True:
        chunk = await stream.read(8192)
        if not chunk:
            break
        if total < max_bytes:
            remaining = max_bytes - total
            chunks.append(chunk[:remaining])
            if len(chunk) > remaining:
                truncated = True
        else:
            truncated = True
        total += len(chunk)

    return b"".join(chunks), truncated


def _extract_sandbox_result(stdout_text: str) -> tuple[str, dict[str, Any] | None]:
    """Extract structured wrapper result markers from stdout."""
    start_marker = "__SYNAPPS_RESULT_START__"
    end_marker = "__SYNAPPS_RESULT_END__"

    start_index = stdout_text.rfind(start_marker)
    if start_index < 0:
        return stdout_text, None

    end_index = stdout_text.find(end_marker, start_index)
    if end_index < 0:
        return stdout_text, None

    payload_start = start_index + len(start_marker)
    payload_text = stdout_text[payload_start:end_index].strip()

    cleaned_stdout = (
        stdout_text[:start_index] + stdout_text[end_index + len(end_marker) :]
    ).strip()
    parsed = _safe_json_loads(payload_text)
    return cleaned_stdout, parsed


PYTHON_CODE_WRAPPER = r"""
import os
import sys
import json
import builtins
import pathlib
import traceback

_clean_env = {
    "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
    "HOME": "/tmp",
    "TMPDIR": "/tmp",
    "TMP": "/tmp",
    "TEMP": "/tmp",
    "PYTHONIOENCODING": "utf-8",
    "PYTHONUNBUFFERED": "1",
}
os.environ.clear()
os.environ.update(_clean_env)


ALLOWED_ROOT = pathlib.Path("/tmp").resolve()

def _resolve_path(raw_path):
    path_obj = pathlib.Path(raw_path)
    if not path_obj.is_absolute():
        path_obj = pathlib.Path(os.getcwd()) / path_obj
    return path_obj.resolve(strict=False)

def _assert_tmp_path(raw_path):
    resolved = _resolve_path(raw_path)
    if resolved == ALLOWED_ROOT or ALLOWED_ROOT in resolved.parents:
        return str(resolved)
    raise PermissionError(f"Filesystem access is restricted to /tmp: {raw_path}")

def _wrap_path_func(module_obj, func_name, indices):
    original = getattr(module_obj, func_name, None)
    if not callable(original):
        return

    def wrapped(*args, **kwargs):
        mutable = list(args)
        for index in indices:
            if index < len(mutable):
                mutable[index] = _assert_tmp_path(mutable[index])
        return original(*mutable, **kwargs)

    setattr(module_obj, func_name, wrapped)

_original_open = builtins.open
def _safe_open(path, *args, **kwargs):
    return _original_open(_assert_tmp_path(path), *args, **kwargs)
builtins.open = _safe_open

_wrap_path_func(os, "open", [0])
_wrap_path_func(os, "listdir", [0])
_wrap_path_func(os, "scandir", [0])
_wrap_path_func(os, "mkdir", [0])
_wrap_path_func(os, "makedirs", [0])
_wrap_path_func(os, "remove", [0])
_wrap_path_func(os, "unlink", [0])
_wrap_path_func(os, "rmdir", [0])
_wrap_path_func(os, "rename", [0, 1])
_wrap_path_func(os, "replace", [0, 1])

for blocked_name in ("system", "popen", "fork", "forkpty"):
    if hasattr(os, blocked_name):
        setattr(os, blocked_name, lambda *args, **kwargs: (_ for _ in ()).throw(PermissionError("Process spawning is blocked")))

blocked_modules = {"subprocess", "socket", "ctypes", "multiprocessing", "pathlib"}
_original_import = builtins.__import__
def _safe_import(name, globals=None, locals=None, fromlist=(), level=0):
    module_root = name.split(".", 1)[0]
    if module_root in blocked_modules:
        raise ImportError(f"Import '{module_root}' is blocked in code sandbox")
    return _original_import(name, globals, locals, fromlist, level)
builtins.__import__ = _safe_import

payload_raw = sys.stdin.read()
try:
    payload = json.loads(payload_raw) if payload_raw.strip() else {}
except Exception:
    payload = {}

user_code = str(payload.get("code", ""))
globals_scope = {
    "__name__": "__main__",
    "data": payload.get("data"),
    "context": payload.get("context", {}),
    "metadata": payload.get("metadata", {}),
    "result": None,
}

wrapper_result = {"ok": True, "result": None}
try:
    exec(compile(user_code, "<user_code.py>", "exec"), globals_scope, globals_scope)
    wrapper_result["result"] = globals_scope.get("result")
except Exception as exc:
    wrapper_result = {
        "ok": False,
        "error": {
            "type": exc.__class__.__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(limit=20),
        },
    }

print("__SYNAPPS_RESULT_START__")
print(json.dumps(wrapper_result, ensure_ascii=False))
print("__SYNAPPS_RESULT_END__")
"""


JAVASCRIPT_CODE_WRAPPER = r"""
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const Module = require('module');

// --- ENVIRONMENT VARIABLE SANITIZATION START ---
const cleanEnv = {
  PATH: process.env.PATH || '/usr/local/bin:/usr/bin:/bin',
  HOME: '/tmp',
  TMPDIR: '/tmp',
  TMP: '/tmp',
  TEMP: '/tmp',
};
// Clear existing process.env and set only allowed variables
for (const key in process.env) {
  delete process.env[key];
}
Object.assign(process.env, cleanEnv);
// --- ENVIRONMENT VARIABLE SANITIZATION END ---


const ALLOWED_ROOT = path.resolve('/tmp');

function resolvePath(rawPath) {
  const inputPath = String(rawPath);
  if (path.isAbsolute(inputPath)) {
    return path.resolve(inputPath);
  }
  return path.resolve(process.cwd(), inputPath);
}

function assertTmpPath(rawPath) {
  const resolved = resolvePath(rawPath);
  if (resolved === ALLOWED_ROOT || resolved.startsWith(ALLOWED_ROOT + path.sep)) {
    return resolved;
  }
  throw new Error(`Filesystem access is restricted to /tmp: ${rawPath}`);
}

function wrapFs(target) {
  const singlePathFns = [
    'readFileSync', 'writeFileSync', 'appendFileSync', 'openSync', 'readdirSync',
    'statSync', 'lstatSync', 'unlinkSync', 'rmSync', 'mkdirSync', 'mkdtempSync',
    'accessSync', 'chmodSync', 'realpathSync', 'readlinkSync'
  ];
  for (const fn of singlePathFns) {
    if (typeof target[fn] !== 'function') continue;
    const original = target[fn].bind(target);
    target[fn] = function(p, ...args) {
      if (typeof p === 'number') {
        return original(p, ...args);
      }
      return original(assertTmpPath(p), ...args);
    };
  }

  for (const fn of ['renameSync', 'copyFileSync', 'linkSync', 'symlinkSync']) {
    if (typeof target[fn] !== 'function') continue;
    const original = target[fn].bind(target);
    target[fn] = function(src, dst, ...args) {
      return original(assertTmpPath(src), assertTmpPath(dst), ...args);
    };
  }
}

function wrapFsPromises(promisesApi) {
  if (!promisesApi) return;
  const singlePathFns = ['readFile', 'writeFile', 'appendFile', 'open', 'readdir', 'stat', 'lstat', 'unlink', 'rm', 'mkdir', 'realpath', 'readlink'];
  for (const fn of singlePathFns) {
    if (typeof promisesApi[fn] !== 'function') continue;
    const original = promisesApi[fn].bind(promisesApi);
    promisesApi[fn] = async function(p, ...args) {
      if (typeof p === 'number') {
        return original(p, ...args);
      }
      return original(assertTmpPath(p), ...args);
    };
  }
  for (const fn of ['rename', 'copyFile', 'link', 'symlink']) {
    if (typeof promisesApi[fn] !== 'function') continue;
    const original = promisesApi[fn].bind(promisesApi);
    promisesApi[fn] = async function(src, dst, ...args) {
      return original(assertTmpPath(src), assertTmpPath(dst), ...args);
    };
  }
}

wrapFs(fs);
wrapFsPromises(fs.promises);

const blockedModules = new Set(['child_process', 'worker_threads', 'cluster', 'net', 'dgram']);
const originalLoad = Module._load;
Module._load = function(request, parent, isMain) {
  const normalized = request.startsWith('node:') ? request.slice(5) : request;
  if (blockedModules.has(normalized)) {
    throw new Error(`Import '${normalized}' is blocked in code sandbox`);
  }
  if (normalized === 'fs') return fs;
  if (normalized === 'fs/promises') return fs.promises;
  return originalLoad.apply(this, arguments);
};

let payload = {};
try {
  const raw = fs.readFileSync(0, 'utf8');
  payload = raw.trim() ? JSON.parse(raw) : {};
} catch (err) {
  payload = {};
}

const sandbox = {
  data: payload.data,
  context: payload.context || {},
  metadata: payload.metadata || {},
  result: null,
  console,
  require,
  Buffer,
  setTimeout,
  clearTimeout,
};

const execTimeoutMs = Math.max(1, Number(payload.exec_timeout_ms || 1000));
let wrapperResult = { ok: true, result: null };
try {
  const context = vm.createContext(sandbox, {
    codeGeneration: { strings: false, wasm: false },
  });
  const script = new vm.Script(String(payload.code || ''), { filename: '<user_code.js>' });
  script.runInContext(context, { timeout: execTimeoutMs });
  wrapperResult.result = sandbox.result;
} catch (err) {
  wrapperResult = {
    ok: false,
    error: {
      type: err && err.name ? err.name : 'Error',
      message: err && err.message ? err.message : String(err),
      stack: err && err.stack ? String(err.stack) : '',
    },
  };
}

console.log('__SYNAPPS_RESULT_START__');
console.log(JSON.stringify(wrapperResult));
console.log('__SYNAPPS_RESULT_END__');
"""


class MemoryStoreBackend(ABC):
    """Abstract persistence backend for memory node operations."""

    backend_name: str

    @abstractmethod
    def upsert(
        self,
        key: str,
        namespace: str,
        content: str,
        payload: Any,
        metadata: dict[str, Any],
    ) -> None:
        """Persist or replace one memory record."""

    @abstractmethod
    def get(self, key: str, namespace: str | None = None) -> dict[str, Any] | None:
        """Fetch one memory record by key."""

    @abstractmethod
    def search(
        self,
        namespace: str,
        query: str,
        tags: list[str],
        top_k: int,
    ) -> list[dict[str, Any]]:
        """Search memory records in a namespace."""

    @abstractmethod
    def delete(self, key: str, namespace: str | None = None) -> bool:
        """Delete one memory record."""

    @abstractmethod
    def clear(self, namespace: str) -> int:
        """Delete all records in a namespace."""


class SQLiteFTSMemoryStoreBackend(MemoryStoreBackend):
    """SQLite-backed persistent store with FTS5 search and LIKE fallback."""

    backend_name = "sqlite_fts"

    def __init__(self, db_path: str):
        self.db_path = str(Path(db_path).expanduser())
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._schema_lock = threading.Lock()
        self._initialized = False
        self._fts_enabled = True
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _ensure_schema(self) -> None:
        with self._schema_lock:
            if self._initialized:
                return
            with self._connect() as conn:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS memories (
                        id TEXT PRIMARY KEY,
                        namespace TEXT NOT NULL,
                        content TEXT NOT NULL,
                        payload_json TEXT NOT NULL,
                        metadata_json TEXT,
                        created_at REAL NOT NULL,
                        flow_id TEXT,
                        node_id TEXT
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_memories_namespace_created_at
                    ON memories(namespace, created_at DESC)
                    """
                )
                try:
                    conn.execute(
                        """
                        CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts
                        USING fts5(
                            memory_id UNINDEXED,
                            namespace UNINDEXED,
                            content,
                            payload,
                            tags
                        )
                        """
                    )
                    self._fts_enabled = True
                except sqlite3.OperationalError:
                    logger.warning(
                        "SQLite FTS5 is unavailable for '%s'; using LIKE fallback.",
                        self.db_path,
                    )
                    self._fts_enabled = False
                    conn.execute(
                        """
                        CREATE TABLE IF NOT EXISTS memories_fts (
                            memory_id TEXT PRIMARY KEY,
                            namespace TEXT NOT NULL,
                            content TEXT NOT NULL,
                            payload TEXT NOT NULL,
                            tags TEXT NOT NULL
                        )
                        """
                    )
                    conn.execute(
                        """
                        CREATE INDEX IF NOT EXISTS idx_memories_fts_namespace
                        ON memories_fts(namespace)
                        """
                    )
                conn.commit()
            self._initialized = True

    def _row_to_result(self, row: sqlite3.Row, score: float) -> dict[str, Any]:
        payload = _parse_json_or_default(row["payload_json"], row["content"])
        metadata = _parse_json_or_default(row["metadata_json"], {})
        if not isinstance(metadata, dict):
            metadata = {}
        metadata.setdefault("created_at", row["created_at"])
        return MemorySearchResultModel(
            key=row["id"],
            data=payload,
            score=score,
            metadata=metadata,
        ).model_dump()

    def upsert(
        self,
        key: str,
        namespace: str,
        content: str,
        payload: Any,
        metadata: dict[str, Any],
    ) -> None:
        self._ensure_schema()
        now = float(metadata.get("timestamp", time.time()))
        payload_json = json.dumps(payload, ensure_ascii=False)
        metadata_json = json.dumps(metadata, ensure_ascii=False)
        tags_text = " ".join(_normalize_memory_tags(metadata.get("tags", [])))
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO memories (
                    id, namespace, content, payload_json, metadata_json, created_at, flow_id, node_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    namespace = excluded.namespace,
                    content = excluded.content,
                    payload_json = excluded.payload_json,
                    metadata_json = excluded.metadata_json,
                    created_at = excluded.created_at,
                    flow_id = excluded.flow_id,
                    node_id = excluded.node_id
                """,
                (
                    key,
                    namespace,
                    content,
                    payload_json,
                    metadata_json,
                    now,
                    metadata.get("flow_id"),
                    metadata.get("node_id"),
                ),
            )
            if self._fts_enabled:
                conn.execute("DELETE FROM memories_fts WHERE memory_id = ?", (key,))
                conn.execute(
                    """
                    INSERT INTO memories_fts(memory_id, namespace, content, payload, tags)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (key, namespace, content, _as_serialized_text(payload), tags_text),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO memories_fts(memory_id, namespace, content, payload, tags)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(memory_id) DO UPDATE SET
                        namespace = excluded.namespace,
                        content = excluded.content,
                        payload = excluded.payload,
                        tags = excluded.tags
                    """,
                    (key, namespace, content, _as_serialized_text(payload), tags_text),
                )
            conn.commit()

    def get(self, key: str, namespace: str | None = None) -> dict[str, Any] | None:
        self._ensure_schema()
        with self._connect() as conn:
            if namespace:
                row = conn.execute(
                    """
                    SELECT id, content, payload_json, metadata_json, created_at
                    FROM memories
                    WHERE id = ? AND namespace = ?
                    LIMIT 1
                    """,
                    (key, namespace),
                ).fetchone()
            else:
                row = conn.execute(
                    """
                    SELECT id, content, payload_json, metadata_json, created_at
                    FROM memories
                    WHERE id = ?
                    LIMIT 1
                    """,
                    (key,),
                ).fetchone()
        if not row:
            return None
        return self._row_to_result(row, score=1.0)

    def search(
        self,
        namespace: str,
        query: str,
        tags: list[str],
        top_k: int,
    ) -> list[dict[str, Any]]:
        self._ensure_schema()
        normalized_tags = _normalize_memory_tags(tags)
        query_text = (query or "").strip()

        rows: list[sqlite3.Row] = []
        if self._fts_enabled:
            terms = _fts_terms(query_text or " ".join(normalized_tags))
            if terms:
                match_query = " OR ".join(f'"{term}"' for term in terms)
                with self._connect() as conn:
                    try:
                        rows = conn.execute(
                            """
                            SELECT
                                m.id,
                                m.content,
                                m.payload_json,
                                m.metadata_json,
                                m.created_at,
                                bm25(memories_fts) AS rank
                            FROM memories_fts
                            JOIN memories m ON memories_fts.memory_id = m.id
                            WHERE m.namespace = ? AND memories_fts MATCH ?
                            ORDER BY rank
                            LIMIT ?
                            """,
                            (namespace, match_query, top_k),
                        ).fetchall()
                    except sqlite3.OperationalError as exc:
                        logger.debug("SQLite FTS query failed, using LIKE fallback: %s", exc)
                        rows = []

        if not rows:
            sql = (
                "SELECT id, content, payload_json, metadata_json, created_at "
                "FROM memories WHERE namespace = ?"
            )
            params: list[Any] = [namespace]
            search_text = query_text or " ".join(normalized_tags)
            if search_text:
                sql += " AND (content LIKE ? OR payload_json LIKE ? OR metadata_json LIKE ?)"
                like_value = f"%{search_text}%"
                params.extend([like_value, like_value, like_value])
            for tag in normalized_tags:
                sql += " AND metadata_json LIKE ?"
                params.append(f"%{tag}%")
            sql += " ORDER BY created_at DESC LIMIT ?"
            params.append(top_k)
            with self._connect() as conn:
                rows = conn.execute(sql, tuple(params)).fetchall()

        results: list[dict[str, Any]] = []
        for row in rows:
            rank = row["rank"] if "rank" in row.keys() else None
            score = 0.8
            if rank is not None:
                try:
                    score = 1.0 / (1.0 + abs(float(rank)))
                except (TypeError, ValueError):
                    score = 0.8
            results.append(self._row_to_result(row, score=score))

        if normalized_tags:
            filtered_results: list[dict[str, Any]] = []
            for result in results:
                metadata = result.get("metadata", {})
                memory_tags = _normalize_memory_tags(metadata.get("tags", []))
                if any(tag in memory_tags for tag in normalized_tags):
                    filtered_results.append(result)
            results = filtered_results

        return results[:top_k]

    def delete(self, key: str, namespace: str | None = None) -> bool:
        self._ensure_schema()
        with self._connect() as conn:
            if namespace:
                existing = conn.execute(
                    "SELECT 1 FROM memories WHERE id = ? AND namespace = ?",
                    (key, namespace),
                ).fetchone()
                if not existing:
                    return False
                conn.execute(
                    "DELETE FROM memories WHERE id = ? AND namespace = ?", (key, namespace)
                )
            else:
                existing = conn.execute("SELECT 1 FROM memories WHERE id = ?", (key,)).fetchone()
                if not existing:
                    return False
                conn.execute("DELETE FROM memories WHERE id = ?", (key,))
            conn.execute("DELETE FROM memories_fts WHERE memory_id = ?", (key,))
            conn.commit()
        return True

    def clear(self, namespace: str) -> int:
        self._ensure_schema()
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id FROM memories WHERE namespace = ?",
                (namespace,),
            ).fetchall()
            memory_ids = [row["id"] for row in rows]
            conn.execute("DELETE FROM memories WHERE namespace = ?", (namespace,))
            if self._fts_enabled:
                for memory_id in memory_ids:
                    conn.execute("DELETE FROM memories_fts WHERE memory_id = ?", (memory_id,))
            else:
                conn.execute("DELETE FROM memories_fts WHERE namespace = ?", (namespace,))
            conn.commit()
        return len(memory_ids)


class ChromaMemoryStoreBackend(MemoryStoreBackend):
    """ChromaDB-backed persistent vector store."""

    backend_name = "chroma"

    def __init__(self, persist_path: str, collection_name: str):
        self.persist_path = str(Path(persist_path).expanduser())
        Path(self.persist_path).mkdir(parents=True, exist_ok=True)
        try:
            import chromadb  # type: ignore
        except Exception as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("chromadb package is not installed") from exc

        self._client = chromadb.PersistentClient(path=self.persist_path)
        self._collection = self._client.get_or_create_collection(name=collection_name)

    def _entry_to_result(
        self,
        memory_id: str,
        document: str,
        metadata: dict[str, Any] | None,
        score: float,
    ) -> dict[str, Any]:
        raw_metadata = metadata or {}
        payload = _parse_json_or_default(raw_metadata.get("payload_json"), document)
        stored_metadata = _parse_json_or_default(raw_metadata.get("metadata_json"), {})
        if not isinstance(stored_metadata, dict):
            stored_metadata = {}
        if "created_at" in raw_metadata:
            stored_metadata.setdefault("created_at", raw_metadata["created_at"])
        return MemorySearchResultModel(
            key=memory_id,
            data=payload,
            score=score,
            metadata=stored_metadata,
        ).model_dump()

    def upsert(
        self,
        key: str,
        namespace: str,
        content: str,
        payload: Any,
        metadata: dict[str, Any],
    ) -> None:
        now = float(metadata.get("timestamp", time.time()))
        safe_metadata: dict[str, Any] = {
            "namespace": namespace,
            "created_at": now,
            "payload_json": json.dumps(payload, ensure_ascii=False),
            "metadata_json": json.dumps(metadata, ensure_ascii=False),
            "tags_text": " ".join(_normalize_memory_tags(metadata.get("tags", []))),
        }
        if metadata.get("flow_id") is not None:
            safe_metadata["flow_id"] = str(metadata["flow_id"])
        if metadata.get("node_id") is not None:
            safe_metadata["node_id"] = str(metadata["node_id"])
        self._collection.upsert(ids=[key], documents=[content], metadatas=[safe_metadata])

    def get(self, key: str, namespace: str | None = None) -> dict[str, Any] | None:
        payload = self._collection.get(ids=[key], include=["documents", "metadatas"])
        ids = payload.get("ids") or []
        if not ids:
            return None
        documents = payload.get("documents") or []
        metadatas = payload.get("metadatas") or []
        for index, memory_id in enumerate(ids):
            metadata = metadatas[index] if index < len(metadatas) else {}
            if namespace and str((metadata or {}).get("namespace", "")) != namespace:
                continue
            document = documents[index] if index < len(documents) else ""
            return self._entry_to_result(memory_id, document, metadata, score=1.0)
        return None

    def search(
        self,
        namespace: str,
        query: str,
        tags: list[str],
        top_k: int,
    ) -> list[dict[str, Any]]:
        normalized_tags = _normalize_memory_tags(tags)
        query_text = (query or "").strip() or " ".join(normalized_tags)
        results: list[dict[str, Any]] = []

        if query_text:
            payload = self._collection.query(
                query_texts=[query_text],
                n_results=top_k,
                where={"namespace": namespace},
                include=["documents", "metadatas", "distances"],
            )
            ids = (payload.get("ids") or [[]])[0]
            documents = (payload.get("documents") or [[]])[0]
            metadatas = (payload.get("metadatas") or [[]])[0]
            distances = (payload.get("distances") or [[]])[0]
            for index, memory_id in enumerate(ids):
                document = documents[index] if index < len(documents) else ""
                metadata = metadatas[index] if index < len(metadatas) else {}
                distance = distances[index] if index < len(distances) else 0.0
                try:
                    score = 1.0 / (1.0 + max(float(distance), 0.0))
                except (TypeError, ValueError):
                    score = 0.8
                results.append(self._entry_to_result(memory_id, document, metadata, score=score))
        else:
            payload = self._collection.get(
                where={"namespace": namespace},
                limit=top_k,
                include=["documents", "metadatas"],
            )
            ids = payload.get("ids") or []
            documents = payload.get("documents") or []
            metadatas = payload.get("metadatas") or []
            for index, memory_id in enumerate(ids):
                document = documents[index] if index < len(documents) else ""
                metadata = metadatas[index] if index < len(metadatas) else {}
                results.append(self._entry_to_result(memory_id, document, metadata, score=0.7))

        if normalized_tags:
            filtered: list[dict[str, Any]] = []
            for result in results:
                memory_tags = _normalize_memory_tags(result.get("metadata", {}).get("tags", []))
                if any(tag in memory_tags for tag in normalized_tags):
                    filtered.append(result)
            results = filtered

        return results[:top_k]

    def delete(self, key: str, namespace: str | None = None) -> bool:
        record = self.get(key, namespace=namespace)
        if not record:
            return False
        self._collection.delete(ids=[key])
        return True

    def clear(self, namespace: str) -> int:
        payload = self._collection.get(where={"namespace": namespace}, include=["metadatas"])
        ids = payload.get("ids") or []
        if ids:
            self._collection.delete(ids=ids)
        return len(ids)


class MemoryStoreFactory:
    """Factory and cache for memory backends."""

    _stores: dict[str, MemoryStoreBackend] = {}
    _lock = threading.Lock()

    @classmethod
    def get_store(cls, config: MemoryNodeConfigModel) -> MemoryStoreBackend:
        backend = (
            config.backend
            if config.backend in SUPPORTED_MEMORY_BACKENDS
            else DEFAULT_MEMORY_BACKEND
        )

        if backend == "chroma":
            chroma_path = config.persist_path or DEFAULT_MEMORY_CHROMA_PATH
            key = f"chroma::{chroma_path}::{config.collection}"
            with cls._lock:
                cached = cls._stores.get(key)
                if cached:
                    return cached
                try:
                    store = ChromaMemoryStoreBackend(chroma_path, config.collection)
                    cls._stores[key] = store
                    return store
                except Exception as exc:
                    logger.warning(
                        "Chroma backend unavailable, falling back to sqlite_fts: %s",
                        exc,
                    )

        if config.persist_path:
            expanded_path = Path(config.persist_path).expanduser()
            if str(expanded_path).lower().endswith((".db", ".sqlite", ".sqlite3")):
                sqlite_path = str(expanded_path)
            else:
                sqlite_path = str(expanded_path / "memory.sqlite3")
        else:
            sqlite_path = DEFAULT_MEMORY_SQLITE_PATH
        key = f"sqlite_fts::{sqlite_path}"
        with cls._lock:
            cached = cls._stores.get(key)
            if cached:
                return cached
            store = SQLiteFTSMemoryStoreBackend(str(sqlite_path))
            cls._stores[key] = store
            return store


class MemoryNodeApplet(BaseApplet):
    """Persistent memory node with SQLite FTS and ChromaDB backends."""

    VERSION = "1.0.0"
    CAPABILITIES = [
        "persistent-memory",
        "vector-search",
        "tag-retrieval",
        "memory-management",
    ]

    async def on_message(self, message: AppletMessage) -> AppletMessage:
        try:
            config = self._resolve_config(message)
            operation = self._resolve_operation(message, config)
            namespace = self._resolve_namespace(message, config)
            store = MemoryStoreFactory.get_store(config)
        except Exception as exc:
            return AppletMessage(
                content={"error": f"Invalid memory configuration: {exc}"},
                context=message.context,
                metadata={"applet": MEMORY_NODE_TYPE, "status": "error"},
            )

        try:
            if operation == "store":
                return await self._handle_store(message, config, namespace, store)
            if operation == "retrieve":
                return await self._handle_retrieve(message, config, namespace, store)
            if operation == "delete":
                return await self._handle_delete(message, config, namespace, store)
            if operation == "clear":
                return await self._handle_clear(message, namespace, store)
        except Exception as exc:
            logger.error("Memory node operation failed: %s", exc, exc_info=True)
            return AppletMessage(
                content={"error": f"Memory operation failed: {exc}"},
                context=message.context,
                metadata={
                    "applet": MEMORY_NODE_TYPE,
                    "status": "error",
                    "operation": operation,
                    "backend": store.backend_name,
                    "namespace": namespace,
                },
            )

        return AppletMessage(
            content={"error": f"Unsupported memory operation: {operation}"},
            context=message.context,
            metadata={"applet": MEMORY_NODE_TYPE, "status": "error"},
        )

    def _resolve_config(self, message: AppletMessage) -> MemoryNodeConfigModel:
        node_data = message.metadata.get("node_data", {})
        if not isinstance(node_data, dict):
            node_data = {}

        context_config = message.context.get("memory_config", {})
        if not isinstance(context_config, dict):
            context_config = {}

        metadata_config = message.metadata.get("memory_config", {})
        if not isinstance(metadata_config, dict):
            metadata_config = {}

        merged = {**context_config, **metadata_config, **node_data}
        backend = str(merged.get("backend", DEFAULT_MEMORY_BACKEND)).strip().lower()
        if backend not in SUPPORTED_MEMORY_BACKENDS:
            backend = "sqlite_fts"

        payload = {
            "label": merged.get("label", "Memory"),
            "operation": merged.get("operation", "store"),
            "backend": backend,
            "namespace": merged.get("namespace", DEFAULT_MEMORY_NAMESPACE),
            "key": merged.get("key"),
            "query": merged.get("query"),
            "tags": merged.get("tags", []),
            "top_k": merged.get("top_k", merged.get("topK", 5)),
            "persist_path": merged.get("persist_path", merged.get("persistPath")),
            "collection": merged.get("collection", DEFAULT_MEMORY_COLLECTION),
            "include_metadata": merged.get(
                "include_metadata", merged.get("includeMetadata", False)
            ),
            "extra": merged.get("extra", {}),
        }
        return MemoryNodeConfigModel.model_validate(payload)

    def _resolve_operation(self, message: AppletMessage, config: MemoryNodeConfigModel) -> str:
        operation = config.operation
        if isinstance(message.content, dict) and "operation" in message.content:
            raw_operation = message.content.get("operation")
            if raw_operation is not None:
                operation = str(raw_operation).strip().lower()
        if operation not in {"store", "retrieve", "delete", "clear"}:
            raise ValueError("operation must be one of: store, retrieve, delete, clear")
        return operation

    def _resolve_namespace(self, message: AppletMessage, config: MemoryNodeConfigModel) -> str:
        namespace = config.namespace
        if isinstance(message.context.get("memory_namespace"), str):
            raw = message.context["memory_namespace"].strip()
            if raw:
                namespace = raw
        if isinstance(message.content, dict) and isinstance(message.content.get("namespace"), str):
            raw = message.content["namespace"].strip()
            if raw:
                namespace = raw
        return namespace

    def _resolve_key(
        self,
        message: AppletMessage,
        config: MemoryNodeConfigModel,
        default_generate: bool = False,
    ) -> str | None:
        key: str | None = config.key
        if isinstance(message.context.get("memory_key"), str):
            raw_context_key = message.context["memory_key"].strip()
            if raw_context_key:
                key = raw_context_key
        if isinstance(message.content, dict) and isinstance(message.content.get("key"), str):
            raw_content_key = message.content["key"].strip()
            if raw_content_key:
                key = raw_content_key
        if not key and default_generate:
            key = str(uuid.uuid4())
        return key

    def _resolve_query(self, message: AppletMessage, config: MemoryNodeConfigModel) -> str:
        query = config.query or ""
        if isinstance(message.content, str):
            query = message.content
        elif isinstance(message.content, dict):
            for key in ("query", "text", "content"):
                candidate = message.content.get(key)
                if isinstance(candidate, str) and candidate.strip():
                    query = candidate
                    break
        return query.strip()

    def _resolve_tags(self, message: AppletMessage, config: MemoryNodeConfigModel) -> list[str]:
        tags = _normalize_memory_tags(config.tags)
        tags.extend(_normalize_memory_tags(message.context.get("memory_tags")))
        if isinstance(message.content, dict):
            tags.extend(_normalize_memory_tags(message.content.get("tags")))
        deduped: list[str] = []
        for tag in tags:
            if tag not in deduped:
                deduped.append(tag)
        return deduped

    def _extract_store_payload(self, message: AppletMessage) -> Any:
        content = message.content
        if isinstance(content, dict):
            if "data" in content:
                return content["data"]
            ignored_keys = {
                "operation",
                "key",
                "tags",
                "query",
                "namespace",
                "backend",
                "top_k",
                "topK",
                "persist_path",
                "persistPath",
                "collection",
                "include_metadata",
                "includeMetadata",
            }
            payload = {k: v for k, v in content.items() if k not in ignored_keys}
            return payload if payload else content
        return {"value": content}

    async def _handle_store(
        self,
        message: AppletMessage,
        config: MemoryNodeConfigModel,
        namespace: str,
        store: MemoryStoreBackend,
    ) -> AppletMessage:
        payload = self._extract_store_payload(message)
        key = self._resolve_key(message, config, default_generate=True)
        if not key:
            raise ValueError("key could not be resolved for store operation")

        tags = self._resolve_tags(message, config)
        metadata: dict[str, Any] = {
            "timestamp": message.context.get("timestamp", time.time()),
            "run_id": message.context.get("run_id", message.metadata.get("run_id")),
            "flow_id": message.context.get("flow_id", message.metadata.get("flow_id")),
            "node_id": message.metadata.get("node_id"),
            "tags": tags,
        }
        await asyncio.to_thread(
            store.upsert,
            key,
            namespace,
            _as_serialized_text(payload),
            payload,
            metadata,
        )

        output_context = {
            **message.context,
            "memory_key": key,
            "memory_retrieved": False,
            "memory_backend": store.backend_name,
            "memory_namespace": namespace,
        }
        return AppletMessage(
            content={
                "key": key,
                "status": "stored",
                "backend": store.backend_name,
                "namespace": namespace,
            },
            context=output_context,
            metadata={
                "applet": MEMORY_NODE_TYPE,
                "operation": "store",
                "backend": store.backend_name,
                "namespace": namespace,
            },
        )

    async def _handle_retrieve(
        self,
        message: AppletMessage,
        config: MemoryNodeConfigModel,
        namespace: str,
        store: MemoryStoreBackend,
    ) -> AppletMessage:
        key = self._resolve_key(message, config, default_generate=False)
        if key:
            record = await asyncio.to_thread(store.get, key, namespace)
            if record:
                content: Any = record["data"]
                if config.include_metadata:
                    content = {
                        "key": key,
                        "data": record["data"],
                        "metadata": record["metadata"],
                        "score": record["score"],
                    }
                return AppletMessage(
                    content=content,
                    context={
                        **message.context,
                        "memory_key": key,
                        "memory_retrieved": True,
                        "memory_backend": store.backend_name,
                        "memory_namespace": namespace,
                    },
                    metadata={
                        "applet": MEMORY_NODE_TYPE,
                        "operation": "retrieve",
                        "key": key,
                        "backend": store.backend_name,
                        "namespace": namespace,
                    },
                )

        tags = self._resolve_tags(message, config)
        query = self._resolve_query(message, config)
        results = await asyncio.to_thread(store.search, namespace, query, tags, config.top_k)
        if results:
            response_content: dict[str, Any] = {
                "memories": {item["key"]: item["data"] for item in results},
                "status": "retrieved",
            }
            if config.include_metadata:
                response_content["results"] = results
                response_content["count"] = len(results)
                if query:
                    response_content["query"] = query
                if tags:
                    response_content["tags"] = tags
            return AppletMessage(
                content=response_content,
                context={
                    **message.context,
                    "memory_retrieved": True,
                    "memory_backend": store.backend_name,
                    "memory_namespace": namespace,
                },
                metadata={
                    "applet": MEMORY_NODE_TYPE,
                    "operation": "retrieve",
                    "backend": store.backend_name,
                    "namespace": namespace,
                },
            )

        return AppletMessage(
            content={"status": "not_found"},
            context={
                **message.context,
                "memory_retrieved": False,
                "memory_backend": store.backend_name,
                "memory_namespace": namespace,
            },
            metadata={
                "applet": MEMORY_NODE_TYPE,
                "operation": "retrieve",
                "backend": store.backend_name,
                "namespace": namespace,
                "status": "not_found",
            },
        )

    async def _handle_delete(
        self,
        message: AppletMessage,
        config: MemoryNodeConfigModel,
        namespace: str,
        store: MemoryStoreBackend,
    ) -> AppletMessage:
        key = self._resolve_key(message, config, default_generate=False)
        if not key:
            return AppletMessage(
                content={"status": "not_found", "key": None},
                context=message.context,
                metadata={
                    "applet": MEMORY_NODE_TYPE,
                    "operation": "delete",
                    "backend": store.backend_name,
                    "namespace": namespace,
                    "status": "not_found",
                },
            )
        deleted = await asyncio.to_thread(store.delete, key, namespace)
        return AppletMessage(
            content={"status": "deleted" if deleted else "not_found", "key": key},
            context=message.context,
            metadata={
                "applet": MEMORY_NODE_TYPE,
                "operation": "delete",
                "backend": store.backend_name,
                "namespace": namespace,
                "status": "success" if deleted else "not_found",
            },
        )

    async def _handle_clear(
        self,
        message: AppletMessage,
        namespace: str,
        store: MemoryStoreBackend,
    ) -> AppletMessage:
        deleted_count = await asyncio.to_thread(store.clear, namespace)
        return AppletMessage(
            content={"status": "cleared", "count": deleted_count, "namespace": namespace},
            context=message.context,
            metadata={
                "applet": MEMORY_NODE_TYPE,
                "operation": "clear",
                "backend": store.backend_name,
                "namespace": namespace,
                "status": "success",
            },
        )


class LLMProviderAdapter(ABC):
    """Common interface for all LLM provider adapters."""

    name: str

    def __init__(self, config: LLMNodeConfigModel):
        self.config = config

    @abstractmethod
    async def complete(self, request: LLMRequestModel) -> LLMResponseModel:
        """Run a non-streaming completion call."""

    @abstractmethod
    async def stream(self, request: LLMRequestModel) -> AsyncIterator[LLMStreamChunkModel]:
        """Run a streaming completion call."""

    @abstractmethod
    def get_models(self) -> list[LLMModelInfoModel]:
        """List known models for this provider."""

    @abstractmethod
    def validate_config(self) -> tuple[bool, str]:
        """Validate provider configuration."""

    def default_model(self) -> str:
        models = self.get_models()
        return models[0].id if models else ""


class OpenAIProviderAdapter(LLMProviderAdapter):
    """OpenAI chat completion adapter."""

    name = "openai"

    def __init__(self, config: LLMNodeConfigModel):
        super().__init__(config)
        self.api_key = config.api_key or os.environ.get("OPENAI_API_KEY")
        self.base_url = (
            config.base_url or os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1"
        ).rstrip("/")

    def validate_config(self) -> tuple[bool, str]:
        if not self.api_key:
            return False, "OPENAI_API_KEY not set"
        return True, ""

    def get_models(self) -> list[LLMModelInfoModel]:
        return [
            LLMModelInfoModel(
                id="gpt-4o",
                name="GPT-4o",
                provider=self.name,
                context_window=128000,
                supports_vision=True,
                max_output_tokens=16384,
            ),
            LLMModelInfoModel(
                id="gpt-4o-mini",
                name="GPT-4o Mini",
                provider=self.name,
                context_window=128000,
                supports_vision=True,
                max_output_tokens=16384,
            ),
            LLMModelInfoModel(
                id="gpt-4.1",
                name="GPT-4.1",
                provider=self.name,
                context_window=1047576,
                supports_vision=True,
                max_output_tokens=32768,
            ),
            LLMModelInfoModel(
                id="o3-mini",
                name="o3-mini",
                provider=self.name,
                context_window=200000,
                max_output_tokens=100000,
            ),
        ]

    def _build_payload(self, request: LLMRequestModel, stream: bool) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": request.model,
            "messages": [m.model_dump() for m in request.messages],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "top_p": request.top_p,
            "stream": stream,
        }
        if request.stop_sequences:
            payload["stop"] = request.stop_sequences
        if stream:
            payload["stream_options"] = {"include_usage": True}
        if request.structured_output and "response_format" not in request.extra:
            if request.json_schema:
                payload["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "structured_response",
                        "schema": request.json_schema,
                    },
                }
            else:
                payload["response_format"] = {"type": "json_object"}
        payload.update(request.extra)
        return payload

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            **self.config.headers,
        }

    async def complete(self, request: LLMRequestModel) -> LLMResponseModel:
        payload = self._build_payload(request, stream=False)
        async with httpx.AsyncClient(timeout=self.config.timeout_seconds) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=payload,
            )
            if response.status_code >= 400:
                detail = response.text or f"HTTP {response.status_code}"
                raise RuntimeError(f"OpenAI request failed: {detail}")
            response.raise_for_status()
            data = response.json()

        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        usage = data.get("usage") or {}
        return LLMResponseModel(
            content=message.get("content", ""),
            model=data.get("model", request.model),
            provider=self.name,
            usage=LLMUsageModel(
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
                total_tokens=usage.get("total_tokens", 0),
            ),
            finish_reason=choice.get("finish_reason", "stop"),
            raw=data,
        )

    async def stream(self, request: LLMRequestModel) -> AsyncIterator[LLMStreamChunkModel]:
        payload = self._build_payload(request, stream=True)
        usage = LLMUsageModel()
        async with httpx.AsyncClient(timeout=self.config.timeout_seconds) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=payload,
            ) as response:
                response.raise_for_status()
                async for data_line in _iter_sse_data_lines(response):
                    if data_line == "[DONE]":
                        break
                    chunk = _safe_json_loads(data_line)
                    if not chunk:
                        continue
                    raw_usage = chunk.get("usage") or {}
                    if raw_usage:
                        usage = LLMUsageModel(
                            prompt_tokens=raw_usage.get("prompt_tokens", 0),
                            completion_tokens=raw_usage.get("completion_tokens", 0),
                            total_tokens=raw_usage.get("total_tokens", 0),
                        )
                    choices = chunk.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta") or {}
                    text_delta = delta.get("content", "")
                    if text_delta:
                        yield LLMStreamChunkModel(content=text_delta)
        yield LLMStreamChunkModel(done=True, usage=usage)


class CustomProviderAdapter(OpenAIProviderAdapter):
    """Adapter for OpenAI-compatible custom endpoints."""

    name = "custom"

    def __init__(self, config: LLMNodeConfigModel):
        super().__init__(config)
        self.api_key = config.api_key or os.environ.get("CUSTOM_LLM_API_KEY")
        self.base_url = (config.base_url or os.environ.get("CUSTOM_LLM_BASE_URL", "")).rstrip("/")

    def validate_config(self) -> tuple[bool, str]:
        if not self.base_url:
            return False, "base_url is required for custom provider"
        return True, ""

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", **self.config.headers}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def get_models(self) -> list[LLMModelInfoModel]:
        model_id = self.config.model or "custom-model"
        return [LLMModelInfoModel(id=model_id, name=model_id, provider=self.name)]


class AnthropicProviderAdapter(LLMProviderAdapter):
    """Anthropic Messages API adapter."""

    name = "anthropic"

    def __init__(self, config: LLMNodeConfigModel):
        super().__init__(config)
        self.api_key = config.api_key or os.environ.get("ANTHROPIC_API_KEY")
        self.base_url = (
            config.base_url or os.environ.get("ANTHROPIC_BASE_URL") or "https://api.anthropic.com"
        ).rstrip("/")

    def validate_config(self) -> tuple[bool, str]:
        if not self.api_key:
            return False, "ANTHROPIC_API_KEY not set"
        return True, ""

    def get_models(self) -> list[LLMModelInfoModel]:
        return [
            LLMModelInfoModel(
                id="claude-sonnet-4-6",
                name="Claude Sonnet 4.6",
                provider=self.name,
                context_window=200000,
                supports_vision=True,
                max_output_tokens=16000,
            ),
            LLMModelInfoModel(
                id="claude-haiku-4-5-20251001",
                name="Claude Haiku 4.5",
                provider=self.name,
                context_window=200000,
                supports_vision=True,
                max_output_tokens=8192,
            ),
            LLMModelInfoModel(
                id="claude-opus-4-6",
                name="Claude Opus 4.6",
                provider=self.name,
                context_window=200000,
                supports_vision=True,
                max_output_tokens=32000,
            ),
        ]

    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": self.api_key or "",
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
            **self.config.headers,
        }

    def _build_payload(self, request: LLMRequestModel, stream: bool) -> dict[str, Any]:
        system_messages = [m.content for m in request.messages if m.role == "system"]
        normal_messages = [
            {"role": m.role, "content": m.content} for m in request.messages if m.role != "system"
        ]
        payload: dict[str, Any] = {
            "model": request.model,
            "messages": normal_messages,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "top_p": request.top_p,
            "stream": stream,
        }
        if request.stop_sequences:
            payload["stop_sequences"] = request.stop_sequences
        if system_messages:
            payload["system"] = "\n".join(system_messages).strip()
        payload.update(request.extra)
        return payload

    async def complete(self, request: LLMRequestModel) -> LLMResponseModel:
        payload = self._build_payload(request, stream=False)
        async with httpx.AsyncClient(timeout=self.config.timeout_seconds) as client:
            response = await client.post(
                f"{self.base_url}/v1/messages",
                headers=self._headers(),
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        text_content = ""
        for block in data.get("content", []):
            if isinstance(block, dict) and block.get("type") == "text":
                text_content += block.get("text", "")

        usage = data.get("usage") or {}
        prompt_tokens = usage.get("input_tokens", 0)
        completion_tokens = usage.get("output_tokens", 0)
        return LLMResponseModel(
            content=text_content,
            model=data.get("model", request.model),
            provider=self.name,
            usage=LLMUsageModel(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
            ),
            finish_reason=data.get("stop_reason", "end_turn"),
            raw=data,
        )

    async def stream(self, request: LLMRequestModel) -> AsyncIterator[LLMStreamChunkModel]:
        payload = self._build_payload(request, stream=True)
        usage = LLMUsageModel()
        async with httpx.AsyncClient(timeout=self.config.timeout_seconds) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/v1/messages",
                headers=self._headers(),
                json=payload,
            ) as response:
                response.raise_for_status()
                async for data_line in _iter_sse_data_lines(response):
                    if data_line == "[DONE]":
                        break
                    chunk = _safe_json_loads(data_line)
                    if not chunk:
                        continue

                    chunk_type = chunk.get("type", "")
                    if chunk_type == "content_block_delta":
                        delta = chunk.get("delta") or {}
                        text_delta = delta.get("text", "")
                        if text_delta:
                            yield LLMStreamChunkModel(content=text_delta)
                    elif chunk_type == "message_delta":
                        raw_usage = chunk.get("usage") or {}
                        if raw_usage:
                            prompt_tokens = raw_usage.get("input_tokens", usage.prompt_tokens)
                            completion_tokens = raw_usage.get(
                                "output_tokens", usage.completion_tokens
                            )
                            usage = LLMUsageModel(
                                prompt_tokens=prompt_tokens,
                                completion_tokens=completion_tokens,
                                total_tokens=prompt_tokens + completion_tokens,
                            )
        yield LLMStreamChunkModel(done=True, usage=usage)


class GoogleProviderAdapter(LLMProviderAdapter):
    """Google Gemini REST adapter."""

    name = "google"

    def __init__(self, config: LLMNodeConfigModel):
        super().__init__(config)
        self.api_key = config.api_key or os.environ.get("GOOGLE_API_KEY")
        self.base_url = (
            config.base_url
            or os.environ.get("GOOGLE_BASE_URL")
            or "https://generativelanguage.googleapis.com/v1beta"
        ).rstrip("/")

    def validate_config(self) -> tuple[bool, str]:
        if not self.api_key:
            return False, "GOOGLE_API_KEY not set"
        return True, ""

    def get_models(self) -> list[LLMModelInfoModel]:
        return [
            LLMModelInfoModel(
                id="gemini-2.5-flash",
                name="Gemini 2.5 Flash",
                provider=self.name,
                context_window=1048576,
                supports_vision=True,
                max_output_tokens=65536,
            ),
            LLMModelInfoModel(
                id="gemini-2.5-pro",
                name="Gemini 2.5 Pro",
                provider=self.name,
                context_window=1048576,
                supports_vision=True,
                max_output_tokens=65536,
            ),
        ]

    def _build_payload(self, request: LLMRequestModel) -> dict[str, Any]:
        contents: list[dict[str, Any]] = []
        system_messages = []
        for message in request.messages:
            if message.role == "system":
                system_messages.append(message.content)
                continue
            role = "model" if message.role == "assistant" else "user"
            contents.append({"role": role, "parts": [{"text": message.content}]})

        generation_config: dict[str, Any] = {
            "temperature": request.temperature,
            "topP": request.top_p,
            "maxOutputTokens": request.max_tokens,
        }
        if request.stop_sequences:
            generation_config["stopSequences"] = request.stop_sequences
        if request.structured_output:
            generation_config["responseMimeType"] = "application/json"
            if request.json_schema:
                generation_config["responseSchema"] = request.json_schema

        payload: dict[str, Any] = {
            "contents": contents or [{"role": "user", "parts": [{"text": ""}]}],
            "generationConfig": generation_config,
            **request.extra,
        }
        if system_messages:
            payload["systemInstruction"] = {"parts": [{"text": "\n".join(system_messages).strip()}]}
        return payload

    async def complete(self, request: LLMRequestModel) -> LLMResponseModel:
        payload = self._build_payload(request)
        async with httpx.AsyncClient(timeout=self.config.timeout_seconds) as client:
            response = await client.post(
                f"{self.base_url}/models/{request.model}:generateContent",
                params={"key": self.api_key},
                headers={"Content-Type": "application/json", **self.config.headers},
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        candidates = data.get("candidates") or [{}]
        candidate = candidates[0]
        content_parts = (candidate.get("content") or {}).get("parts") or []
        text_content = "".join(
            part.get("text", "") for part in content_parts if isinstance(part, dict)
        )

        metadata = data.get("usageMetadata") or {}
        usage = LLMUsageModel(
            prompt_tokens=metadata.get("promptTokenCount", 0),
            completion_tokens=metadata.get("candidatesTokenCount", 0),
            total_tokens=metadata.get("totalTokenCount", 0),
        )
        finish_reason = candidate.get("finishReason", "STOP")
        return LLMResponseModel(
            content=text_content,
            model=request.model,
            provider=self.name,
            usage=usage,
            finish_reason=finish_reason,
            raw=data,
        )

    async def stream(self, request: LLMRequestModel) -> AsyncIterator[LLMStreamChunkModel]:
        payload = self._build_payload(request)
        usage = LLMUsageModel()
        async with httpx.AsyncClient(timeout=self.config.timeout_seconds) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/models/{request.model}:streamGenerateContent",
                params={"alt": "sse", "key": self.api_key},
                headers={"Content-Type": "application/json", **self.config.headers},
                json=payload,
            ) as response:
                response.raise_for_status()
                async for data_line in _iter_sse_data_lines(response):
                    chunk = _safe_json_loads(data_line)
                    if not chunk:
                        continue
                    candidates = chunk.get("candidates") or []
                    if candidates:
                        content = (candidates[0].get("content") or {}).get("parts") or []
                        text_delta = "".join(
                            part.get("text", "") for part in content if isinstance(part, dict)
                        )
                        if text_delta:
                            yield LLMStreamChunkModel(content=text_delta)
                    metadata = chunk.get("usageMetadata") or {}
                    if metadata:
                        usage = LLMUsageModel(
                            prompt_tokens=metadata.get("promptTokenCount", usage.prompt_tokens),
                            completion_tokens=metadata.get(
                                "candidatesTokenCount", usage.completion_tokens
                            ),
                            total_tokens=metadata.get("totalTokenCount", usage.total_tokens),
                        )
        yield LLMStreamChunkModel(done=True, usage=usage)


class OllamaProviderAdapter(LLMProviderAdapter):
    """Ollama local model adapter."""

    name = "ollama"

    def __init__(self, config: LLMNodeConfigModel):
        super().__init__(config)
        self.base_url = (
            config.base_url or os.environ.get("OLLAMA_BASE_URL") or "http://localhost:11434"
        ).rstrip("/")

    def validate_config(self) -> tuple[bool, str]:
        if not self.base_url:
            return False, "base_url is required for ollama"
        return True, ""

    def get_models(self) -> list[LLMModelInfoModel]:
        return [
            LLMModelInfoModel(
                id="llama3.1",
                name="Llama 3.1",
                provider=self.name,
                context_window=131072,
                max_output_tokens=4096,
            ),
            LLMModelInfoModel(
                id="mistral",
                name="Mistral",
                provider=self.name,
                context_window=32768,
                max_output_tokens=4096,
            ),
            LLMModelInfoModel(
                id="codellama",
                name="Code Llama",
                provider=self.name,
                context_window=16384,
                max_output_tokens=4096,
            ),
        ]

    def _build_payload(self, request: LLMRequestModel, stream: bool) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": request.model,
            "messages": [m.model_dump() for m in request.messages],
            "stream": stream,
            "options": {
                "temperature": request.temperature,
                "top_p": request.top_p,
                "num_predict": request.max_tokens,
            },
        }
        if request.stop_sequences:
            payload["options"]["stop"] = request.stop_sequences
        if request.structured_output:
            payload["format"] = request.json_schema or "json"
        payload.update(request.extra)
        return payload

    async def complete(self, request: LLMRequestModel) -> LLMResponseModel:
        payload = self._build_payload(request, stream=False)
        async with httpx.AsyncClient(timeout=self.config.timeout_seconds) as client:
            response = await client.post(
                f"{self.base_url}/api/chat",
                headers={"Content-Type": "application/json", **self.config.headers},
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        usage = LLMUsageModel(
            prompt_tokens=data.get("prompt_eval_count", 0),
            completion_tokens=data.get("eval_count", 0),
            total_tokens=data.get("prompt_eval_count", 0) + data.get("eval_count", 0),
        )
        return LLMResponseModel(
            content=((data.get("message") or {}).get("content", "")),
            model=data.get("model", request.model),
            provider=self.name,
            usage=usage,
            finish_reason="stop" if data.get("done", True) else "incomplete",
            raw=data,
        )

    async def stream(self, request: LLMRequestModel) -> AsyncIterator[LLMStreamChunkModel]:
        payload = self._build_payload(request, stream=True)
        usage = LLMUsageModel()
        async with httpx.AsyncClient(timeout=self.config.timeout_seconds) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/api/chat",
                headers={"Content-Type": "application/json", **self.config.headers},
                json=payload,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    chunk = _safe_json_loads(line)
                    if not chunk:
                        continue
                    text_delta = (chunk.get("message") or {}).get("content", "")
                    if text_delta:
                        yield LLMStreamChunkModel(content=text_delta)
                    if chunk.get("done", False):
                        usage = LLMUsageModel(
                            prompt_tokens=chunk.get("prompt_eval_count", 0),
                            completion_tokens=chunk.get("eval_count", 0),
                            total_tokens=chunk.get("prompt_eval_count", 0)
                            + chunk.get("eval_count", 0),
                        )
        yield LLMStreamChunkModel(done=True, usage=usage)


class LLMProviderRegistry:
    """Runtime registry for provider adapters."""

    _providers: dict[str, type[LLMProviderAdapter]] = {
        "openai": OpenAIProviderAdapter,
        "anthropic": AnthropicProviderAdapter,
        "google": GoogleProviderAdapter,
        "ollama": OllamaProviderAdapter,
        "custom": CustomProviderAdapter,
    }

    @classmethod
    def get(cls, name: str, config: LLMNodeConfigModel) -> LLMProviderAdapter:
        provider_name = name.lower().strip()
        provider_cls = cls._providers.get(provider_name)
        if not provider_cls:
            raise ValueError(f"Unknown provider '{name}'. Available: {list(cls._providers.keys())}")
        return provider_cls(config)

    @classmethod
    def list_providers(cls) -> list[LLMProviderInfoModel]:
        providers: list[LLMProviderInfoModel] = []
        for name in SUPPORTED_LLM_PROVIDERS:
            provider_cls = cls._providers.get(name)
            if provider_cls is None:
                continue
            default_cfg = LLMNodeConfigModel(provider=name)
            provider = provider_cls(default_cfg)
            is_valid, reason = provider.validate_config()
            providers.append(
                LLMProviderInfoModel(
                    name=name,
                    configured=is_valid,
                    reason="" if is_valid else reason,
                    models=provider.get_models(),
                )
            )
        return providers


class LLMNodeApplet(BaseApplet):
    """Universal LLM node with provider adapter routing."""

    VERSION = "1.0.0"
    CAPABILITIES = [
        "text-generation",
        "multi-provider",
        "streaming",
        "structured-output",
    ]

    async def on_message(self, message: AppletMessage) -> AppletMessage:
        config = self._resolve_config(message)
        provider = LLMProviderRegistry.get(config.provider, config)
        metrics.record_provider_call(config.provider)
        is_valid, reason = provider.validate_config()
        if not is_valid:
            return AppletMessage(
                content=f"Provider '{config.provider}' is not configured: {reason}",
                context=message.context,
                metadata={"applet": "llm", "status": "error"},
            )

        request = self._build_request(message, config, provider)

        if config.stream:
            response = await self._run_streaming(provider, request, message, config)
        else:
            response = await provider.complete(request)

        parsed_content: Any = response.content
        parse_error = None
        if config.structured_output:
            try:
                parsed_content = json.loads(response.content)
            except json.JSONDecodeError:
                parse_error = "Provider response was not valid JSON"

        output_context = {**message.context}
        output_context["last_llm_response"] = response.model_dump()
        output_context["llm_provider"] = response.provider
        output_context["llm_model"] = response.model

        metadata: dict[str, Any] = {
            "applet": "llm",
            "provider": response.provider,
            "model": response.model,
            "usage": response.usage.model_dump(),
            "finish_reason": response.finish_reason,
            "status": "success",
        }
        if config.structured_output:
            metadata["structured_output"] = parse_error is None
            if parse_error:
                metadata["structured_output_error"] = parse_error

        return AppletMessage(content=parsed_content, context=output_context, metadata=metadata)

    async def _run_streaming(
        self,
        provider: LLMProviderAdapter,
        request: LLMRequestModel,
        message: AppletMessage,
        config: LLMNodeConfigModel,
    ) -> LLMResponseModel:
        full_text = ""
        usage = LLMUsageModel()
        node_id = message.metadata.get("node_id")
        run_id = message.metadata.get("run_id")

        async for chunk in provider.stream(request):
            if chunk.content:
                full_text += chunk.content
                await self._broadcast_stream(
                    node_id=node_id,
                    run_id=run_id,
                    provider_name=provider.name,
                    model=request.model,
                    chunk=chunk.content,
                    done=False,
                )
            if chunk.usage:
                usage = chunk.usage

        await self._broadcast_stream(
            node_id=node_id,
            run_id=run_id,
            provider_name=provider.name,
            model=request.model,
            chunk="",
            done=True,
        )
        return LLMResponseModel(
            content=full_text,
            model=request.model,
            provider=provider.name,
            usage=usage,
            finish_reason="stop",
            raw={},
        )

    async def _broadcast_stream(
        self,
        node_id: str | None,
        run_id: str | None,
        provider_name: str,
        model: str,
        chunk: str,
        done: bool,
    ) -> None:
        if not ws_manager.connected_websockets:
            return
        message = _ws_message(
            "llm.stream",
            {
                "node_id": node_id,
                "run_id": run_id,
                "provider": provider_name,
                "model": model,
                "chunk": chunk,
                "done": done,
            },
        )
        await ws_manager.broadcast(message)

    def _resolve_config(self, message: AppletMessage) -> LLMNodeConfigModel:
        node_data = message.metadata.get("node_data", {})
        if not isinstance(node_data, dict):
            node_data = {}

        context_config = message.context.get("llm_config", {})
        if not isinstance(context_config, dict):
            context_config = {}

        metadata_config = message.metadata.get("llm_config", {})
        if not isinstance(metadata_config, dict):
            metadata_config = {}

        merged = {**context_config, **metadata_config, **node_data}

        config_payload = {
            "label": merged.get("label", "LLM"),
            "provider": merged.get("provider", "openai"),
            "model": merged.get("model"),
            "system_prompt": merged.get(
                "system_prompt",
                merged.get("systemPrompt", message.metadata.get("system_prompt", "")),
            ),
            "temperature": merged.get("temperature", 0.7),
            "max_tokens": merged.get("max_tokens", merged.get("maxTokens", 1024)),
            "top_p": merged.get("top_p", merged.get("topP", 1.0)),
            "stop_sequences": merged.get("stop_sequences", merged.get("stopSequences", [])),
            "stream": merged.get("stream", False),
            "structured_output": merged.get(
                "structured_output", merged.get("structuredOutput", False)
            ),
            "json_schema": merged.get("json_schema", merged.get("jsonSchema")),
            "api_key": merged.get("api_key", merged.get("apiKey")),
            "base_url": merged.get("base_url", merged.get("baseUrl")),
            "timeout_seconds": merged.get("timeout_seconds", merged.get("timeoutSeconds", 120.0)),
            "headers": merged.get("headers", {}),
            "extra": merged.get("extra", {}),
        }
        if isinstance(config_payload["stop_sequences"], str):
            config_payload["stop_sequences"] = [config_payload["stop_sequences"]]
        return LLMNodeConfigModel.model_validate(config_payload)

    def _build_request(
        self,
        message: AppletMessage,
        config: LLMNodeConfigModel,
        provider: LLMProviderAdapter,
    ) -> LLMRequestModel:
        messages: list[LLMMessageModel] = []

        raw_history = message.context.get("messages", [])
        if isinstance(raw_history, list):
            for item in raw_history:
                if not isinstance(item, dict):
                    continue
                role = item.get("role")
                content = item.get("content")
                if isinstance(role, str) and isinstance(content, str):
                    try:
                        messages.append(LLMMessageModel(role=role, content=content))
                    except Exception:
                        continue  # OMIT JUSTIFIED: skip malformed chat history item; valid messages still processed

        if config.system_prompt:
            messages.insert(0, LLMMessageModel(role="system", content=config.system_prompt))

        messages.append(LLMMessageModel(role="user", content=_as_text(message.content)))

        model_id = config.model or provider.default_model()

        return LLMRequestModel(
            messages=messages,
            model=model_id,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
            top_p=config.top_p,
            stop_sequences=config.stop_sequences,
            stream=config.stream,
            structured_output=config.structured_output,
            json_schema=config.json_schema,
            extra=dict(config.extra),
        )


def _parse_image_size(size: str) -> tuple[int, int]:
    """Parse an image size string like '1024x1024' into integer width/height."""
    if not isinstance(size, str):
        return 1024, 1024
    raw = size.strip().lower()
    if "x" not in raw:
        return 1024, 1024
    width_raw, height_raw = raw.split("x", 1)
    try:
        width = int(width_raw)
        height = int(height_raw)
    except ValueError:
        return 1024, 1024
    if width <= 0 or height <= 0:
        return 1024, 1024
    return width, height


def _extract_openai_style_images(payload: dict[str, Any]) -> list[str]:
    """Extract image payload values from OpenAI-compatible image responses."""
    images: list[str] = []
    for item in payload.get("data") or []:
        if not isinstance(item, dict):
            continue
        b64_value = item.get("b64_json")
        if isinstance(b64_value, str) and b64_value:
            images.append(b64_value)
            continue
        url_value = item.get("url")
        if isinstance(url_value, str) and url_value:
            images.append(url_value)
    return images


class ImageProviderAdapter(ABC):
    """Common interface for all image provider adapters."""

    name: str

    def __init__(self, config: ImageGenNodeConfigModel):
        self.config = config

    @abstractmethod
    async def generate(self, request: ImageGenRequestModel) -> ImageGenResponseModel:
        """Generate one or more images from the request prompt."""

    @abstractmethod
    def get_models(self) -> list[ImageModelInfoModel]:
        """List known models for this provider."""

    @abstractmethod
    def validate_config(self) -> tuple[bool, str]:
        """Validate provider configuration."""

    def default_model(self) -> str:
        models = self.get_models()
        return models[0].id if models else ""


class OpenAIImageProviderAdapter(ImageProviderAdapter):
    """OpenAI image generation adapter (DALL-E 3)."""

    name = "openai"

    def __init__(self, config: ImageGenNodeConfigModel):
        super().__init__(config)
        self.api_key = config.api_key or os.environ.get("OPENAI_API_KEY")
        self.base_url = (
            config.base_url or os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1"
        ).rstrip("/")

    def validate_config(self) -> tuple[bool, str]:
        if not self.api_key:
            return False, "OPENAI_API_KEY not set"
        return True, ""

    def get_models(self) -> list[ImageModelInfoModel]:
        return [
            ImageModelInfoModel(
                id="dall-e-3",
                name="DALL-E 3",
                provider=self.name,
                supports_base64=True,
                supports_url=True,
                max_images=1,
            ),
        ]

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            **self.config.headers,
        }

    def _build_payload(self, request: ImageGenRequestModel) -> dict[str, Any]:
        prompt_text = request.prompt
        if request.style:
            prompt_text = f"{prompt_text}, {request.style} style"

        payload: dict[str, Any] = {
            "model": request.model,
            "prompt": prompt_text,
            "n": 1 if request.model == "dall-e-3" else request.n,
            "size": request.size,
            "quality": request.quality,
            "response_format": request.response_format,
        }
        payload.update(request.extra)
        return payload

    async def generate(self, request: ImageGenRequestModel) -> ImageGenResponseModel:
        payload = self._build_payload(request)
        async with httpx.AsyncClient(timeout=self.config.timeout_seconds) as client:
            response = await client.post(
                f"{self.base_url}/images/generations",
                headers=self._headers(),
                json=payload,
            )
            if response.status_code >= 400:
                detail = response.text or f"HTTP {response.status_code}"
                raise RuntimeError(f"OpenAI image request failed: {detail}")
            response.raise_for_status()
            data = response.json()

        images = _extract_openai_style_images(data)
        revised_prompt = None
        entries = data.get("data") or []
        if entries and isinstance(entries[0], dict):
            raw_revised = entries[0].get("revised_prompt")
            if isinstance(raw_revised, str):
                revised_prompt = raw_revised

        return ImageGenResponseModel(
            images=images,
            model=data.get("model", request.model),
            provider=self.name,
            revised_prompt=revised_prompt,
            raw=data if isinstance(data, dict) else {},
        )


class StabilityImageProviderAdapter(ImageProviderAdapter):
    """Stability AI image generation adapter."""

    name = "stability"

    def __init__(self, config: ImageGenNodeConfigModel):
        super().__init__(config)
        self.api_key = config.api_key or os.environ.get("STABILITY_API_KEY")
        self.base_url = (
            config.base_url or os.environ.get("STABILITY_BASE_URL") or "https://api.stability.ai"
        ).rstrip("/")

    def validate_config(self) -> tuple[bool, str]:
        if not self.api_key:
            return False, "STABILITY_API_KEY not set"
        return True, ""

    def get_models(self) -> list[ImageModelInfoModel]:
        return [
            ImageModelInfoModel(
                id="stable-diffusion-xl-1024-v1-0",
                name="Stable Diffusion XL",
                provider=self.name,
                supports_base64=True,
                supports_url=False,
                max_images=4,
            ),
            ImageModelInfoModel(
                id="stable-diffusion-3",
                name="Stable Diffusion 3",
                provider=self.name,
                supports_base64=True,
                supports_url=False,
                max_images=4,
            ),
        ]

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            **self.config.headers,
        }

    def _build_payload(self, request: ImageGenRequestModel) -> dict[str, Any]:
        width, height = _parse_image_size(request.size)
        prompt_text = request.prompt
        if request.style:
            prompt_text = f"{prompt_text}, {request.style} style"

        text_prompts: list[dict[str, Any]] = [{"text": prompt_text, "weight": 1.0}]
        if request.negative_prompt:
            text_prompts.append({"text": request.negative_prompt, "weight": -1.0})

        payload: dict[str, Any] = {
            "text_prompts": text_prompts,
            "cfg_scale": float(request.extra.get("cfg_scale", 7)),
            "height": height,
            "width": width,
            "samples": request.n,
            "steps": int(request.extra.get("steps", 30)),
        }
        payload.update({k: v for k, v in request.extra.items() if k not in {"cfg_scale", "steps"}})
        return payload

    async def generate(self, request: ImageGenRequestModel) -> ImageGenResponseModel:
        payload = self._build_payload(request)
        model_id = request.model
        async with httpx.AsyncClient(timeout=self.config.timeout_seconds) as client:
            response = await client.post(
                f"{self.base_url}/v1/generation/{model_id}/text-to-image",
                headers=self._headers(),
                json=payload,
            )
            if response.status_code >= 400:
                detail = response.text or f"HTTP {response.status_code}"
                raise RuntimeError(f"Stability image request failed: {detail}")
            response.raise_for_status()
            data = response.json()

        images = []
        for artifact in data.get("artifacts") or []:
            if isinstance(artifact, dict):
                raw_b64 = artifact.get("base64")
                if isinstance(raw_b64, str) and raw_b64:
                    images.append(raw_b64)

        return ImageGenResponseModel(
            images=images,
            model=model_id,
            provider=self.name,
            raw=data if isinstance(data, dict) else {},
        )


class FluxImageProviderAdapter(ImageProviderAdapter):
    """Flux image generation adapter using an OpenAI-compatible response shape."""

    name = "flux"

    def __init__(self, config: ImageGenNodeConfigModel):
        super().__init__(config)
        self.api_key = config.api_key or os.environ.get("FLUX_API_KEY")
        self.base_url = (
            config.base_url or os.environ.get("FLUX_BASE_URL") or "https://api.bfl.ai/v1"
        ).rstrip("/")

    def validate_config(self) -> tuple[bool, str]:
        if not self.api_key:
            return False, "FLUX_API_KEY not set"
        return True, ""

    def get_models(self) -> list[ImageModelInfoModel]:
        return [
            ImageModelInfoModel(
                id="flux-1.1-pro",
                name="FLUX 1.1 Pro",
                provider=self.name,
                supports_base64=True,
                supports_url=True,
                max_images=4,
            ),
            ImageModelInfoModel(
                id="flux-1-dev",
                name="FLUX 1 Dev",
                provider=self.name,
                supports_base64=True,
                supports_url=True,
                max_images=4,
            ),
        ]

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", **self.config.headers}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _endpoint(self) -> str:
        endpoint = self.config.extra.get("endpoint", "/images/generations")
        if not isinstance(endpoint, str) or not endpoint.strip():
            endpoint = "/images/generations"
        if not endpoint.startswith("/"):
            endpoint = f"/{endpoint}"
        return endpoint

    def _build_payload(self, request: ImageGenRequestModel) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": request.model,
            "prompt": request.prompt,
            "size": request.size,
            "style": request.style,
            "quality": request.quality,
            "n": request.n,
            "response_format": request.response_format,
        }
        if request.negative_prompt:
            payload["negative_prompt"] = request.negative_prompt
        payload.update(request.extra)
        return payload

    async def generate(self, request: ImageGenRequestModel) -> ImageGenResponseModel:
        payload = self._build_payload(request)
        async with httpx.AsyncClient(timeout=self.config.timeout_seconds) as client:
            response = await client.post(
                f"{self.base_url}{self._endpoint()}",
                headers=self._headers(),
                json=payload,
            )
            if response.status_code >= 400:
                detail = response.text or f"HTTP {response.status_code}"
                raise RuntimeError(f"Flux image request failed: {detail}")
            response.raise_for_status()
            data = response.json()

        images = _extract_openai_style_images(data if isinstance(data, dict) else {})
        if not images and isinstance(data, dict):
            for item in data.get("images") or []:
                if isinstance(item, str) and item:
                    images.append(item)
        revised_prompt = None
        if isinstance(data, dict):
            raw_revised = data.get("revised_prompt")
            if isinstance(raw_revised, str):
                revised_prompt = raw_revised
        return ImageGenResponseModel(
            images=images,
            model=request.model,
            provider=self.name,
            revised_prompt=revised_prompt,
            raw=data if isinstance(data, dict) else {},
        )


class ImageProviderRegistry:
    """Runtime registry for image provider adapters."""

    _providers: dict[str, type[ImageProviderAdapter]] = {
        "openai": OpenAIImageProviderAdapter,
        "stability": StabilityImageProviderAdapter,
        "flux": FluxImageProviderAdapter,
    }

    @classmethod
    def get(cls, name: str, config: ImageGenNodeConfigModel) -> ImageProviderAdapter:
        provider_name = name.lower().strip()
        provider_cls = cls._providers.get(provider_name)
        if not provider_cls:
            raise ValueError(f"Unknown provider '{name}'. Available: {list(cls._providers.keys())}")
        return provider_cls(config)

    @classmethod
    def list_providers(cls) -> list[ImageProviderInfoModel]:
        providers: list[ImageProviderInfoModel] = []
        for name in SUPPORTED_IMAGE_PROVIDERS:
            provider_cls = cls._providers.get(name)
            if provider_cls is None:
                continue
            default_cfg = ImageGenNodeConfigModel(provider=name)
            provider = provider_cls(default_cfg)
            is_valid, reason = provider.validate_config()
            providers.append(
                ImageProviderInfoModel(
                    name=name,
                    configured=is_valid,
                    reason="" if is_valid else reason,
                    models=provider.get_models(),
                )
            )
        return providers


class ImageGenNodeApplet(BaseApplet):
    """Universal image generation node with provider adapter routing."""

    VERSION = "1.0.0"
    CAPABILITIES = [
        "image-generation",
        "multi-provider",
        "text-to-image",
    ]

    async def on_message(self, message: AppletMessage) -> AppletMessage:
        config = self._resolve_config(message)
        provider = ImageProviderRegistry.get(config.provider, config)
        is_valid, reason = provider.validate_config()
        if not is_valid:
            return AppletMessage(
                content={"error": f"Provider '{config.provider}' is not configured: {reason}"},
                context=message.context,
                metadata={"applet": IMAGE_NODE_TYPE, "status": "error"},
            )

        request = self._build_request(message, config, provider)
        response = await provider.generate(request)
        first_image = response.images[0] if response.images else ""

        output_context = {**message.context}
        output_context["last_image_response"] = response.model_dump()
        output_context["image_provider"] = response.provider
        output_context["image_model"] = response.model

        content: dict[str, Any] = {
            "image": first_image,
            "images": response.images,
            "prompt": request.prompt,
            "provider": response.provider,
            "model": response.model,
        }
        if response.revised_prompt:
            content["revised_prompt"] = response.revised_prompt

        metadata = {
            "applet": IMAGE_NODE_TYPE,
            "provider": response.provider,
            "model": response.model,
            "image_count": len(response.images),
            "status": "success",
        }
        return AppletMessage(content=content, context=output_context, metadata=metadata)

    def _resolve_config(self, message: AppletMessage) -> ImageGenNodeConfigModel:
        node_data = message.metadata.get("node_data", {})
        if not isinstance(node_data, dict):
            node_data = {}

        context_config = message.context.get("image_config", {})
        if not isinstance(context_config, dict):
            context_config = {}

        metadata_config = message.metadata.get("image_config", {})
        if not isinstance(metadata_config, dict):
            metadata_config = {}

        merged = {**context_config, **metadata_config, **node_data}
        config_payload = {
            "label": merged.get("label", "Image Gen"),
            "provider": merged.get("provider", "openai"),
            "model": merged.get("model"),
            "size": merged.get("size", "1024x1024"),
            "style": merged.get("style", "photorealistic"),
            "quality": merged.get("quality", "standard"),
            "n": merged.get("n", 1),
            "response_format": merged.get(
                "response_format", merged.get("responseFormat", "b64_json")
            ),
            "api_key": merged.get("api_key", merged.get("apiKey")),
            "base_url": merged.get("base_url", merged.get("baseUrl")),
            "timeout_seconds": merged.get("timeout_seconds", merged.get("timeoutSeconds", 120.0)),
            "headers": merged.get("headers", {}),
            "extra": merged.get("extra", {}),
        }
        return ImageGenNodeConfigModel.model_validate(config_payload)

    def _build_request(
        self,
        message: AppletMessage,
        config: ImageGenNodeConfigModel,
        provider: ImageProviderAdapter,
    ) -> ImageGenRequestModel:
        prompt_text = _as_text(message.content).strip()
        if not prompt_text:
            prompt_text = "A beautiful landscape with mountains and a lake."

        negative_prompt = ""
        if isinstance(message.context, dict):
            raw_negative = message.context.get(
                "negative_prompt", message.context.get("negativePrompt", "")
            )
            if isinstance(raw_negative, str):
                negative_prompt = raw_negative

        model_id = config.model or provider.default_model()
        return ImageGenRequestModel(
            prompt=prompt_text,
            negative_prompt=negative_prompt,
            model=model_id,
            size=config.size,
            style=config.style,
            quality=config.quality,
            n=config.n,
            response_format=config.response_format,
            extra=dict(config.extra),
        )


class HTTPRequestNodeApplet(BaseApplet):
    """Universal HTTP request node for calling external APIs."""

    VERSION = "1.0.0"
    CAPABILITIES = [
        "http-requests",
        "api-integration",
        "templated-headers",
        "templated-body",
    ]

    @staticmethod
    def _is_ssrf_blocked(url: str) -> bool:
        """Reject private/internal IP ranges to prevent SSRF."""
        import ipaddress as _ip
        import urllib.parse

        try:
            host = urllib.parse.urlparse(url).hostname or ""
            if not host:
                return False
            if host.lower() in {"localhost", "ip6-localhost", "ip6-loopback"}:
                return True
            if host.endswith(".local") or host.endswith(".internal"):
                return True
            try:
                addr = _ip.ip_address(host)
                return addr.is_private or addr.is_loopback or addr.is_link_local
            except ValueError:
                pass  # hostname is a DNS name, not an IP literal — allow
            return False
        except Exception:
            return False  # malformed URL will fail at the httpx layer

    async def on_message(self, message: AppletMessage) -> AppletMessage:
        try:
            config = self._resolve_config(message)
        except Exception as exc:
            return AppletMessage(
                content={"error": f"Invalid HTTP request configuration: {exc}"},
                context=message.context,
                metadata={"applet": HTTP_REQUEST_NODE_TYPE, "status": "error"},
            )

        template_data = self._template_data(message)
        rendered_url_value = _render_template_payload(config.url, template_data)
        rendered_url = str(rendered_url_value).strip()
        if not rendered_url:
            return AppletMessage(
                content={"error": "HTTP request URL resolved to an empty value"},
                context=message.context,
                metadata={"applet": HTTP_REQUEST_NODE_TYPE, "status": "error"},
            )

        if self._is_ssrf_blocked(rendered_url):
            return AppletMessage(
                content={"error": "URL blocked: private/internal addresses are not allowed"},
                context=message.context,
                metadata={"applet": HTTP_REQUEST_NODE_TYPE, "status": "error"},
            )

        rendered_headers = self._normalize_headers(
            _render_template_payload(config.headers, template_data)
        )
        rendered_query_params = self._normalize_query_params(
            _render_template_payload(config.query_params, template_data)
        )

        body_template = config.body_template
        if body_template is None:
            body_template = self._default_body_template(message, config.method)
        rendered_body = (
            _render_template_payload(body_template, template_data)
            if body_template is not None
            else None
        )

        request_kwargs: dict[str, Any] = {"headers": rendered_headers}
        if rendered_query_params:
            request_kwargs["params"] = rendered_query_params
        if config.body_type != "none" and rendered_body is not None:
            self._apply_body_payload(config.body_type, rendered_body, request_kwargs)
        request_kwargs.update(dict(config.extra))

        last_error: Exception | None = None
        last_response: httpx.Response | None = None
        for attempt in range(config.max_retries + 1):
            if attempt > 0:
                await asyncio.sleep(config.retry_backoff_factor * (2 ** (attempt - 1)))
            try:
                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(config.timeout_seconds),
                    follow_redirects=config.allow_redirects,
                    verify=config.verify_ssl,
                ) as client:
                    response = await client.request(config.method, rendered_url, **request_kwargs)
                if response.status_code >= 500 and attempt < config.max_retries:
                    last_response = response
                    continue
                last_response = response
                break
            except httpx.HTTPError as exc:
                last_error = exc
                logger.warning(
                    "HTTP request node attempt %d/%d failed: %s",
                    attempt + 1,
                    config.max_retries + 1,
                    exc,
                )
                if attempt < config.max_retries:
                    continue
                return AppletMessage(
                    content={
                        "error": f"HTTP request failed: {exc!s}",
                        "url": rendered_url,
                        "method": config.method,
                    },
                    context=message.context,
                    metadata={
                        "applet": HTTP_REQUEST_NODE_TYPE,
                        "status": "error",
                        "method": config.method,
                        "url": rendered_url,
                    },
                )

        response = last_response
        if response is None:
            # Safety fallback — should not be reachable
            error_detail = str(last_error) if last_error else "unknown error"
            return AppletMessage(
                content={"error": f"HTTP request failed after retries: {error_detail}"},
                context=message.context,
                metadata={"applet": HTTP_REQUEST_NODE_TYPE, "status": "error"},
            )

        parsed_data = self._parse_response_data(response)
        response_headers: dict[str, str] = (
            {key: value for key, value in response.headers.items()}
            if config.include_response_headers
            else {}
        )

        output_content: dict[str, Any] = {
            "status_code": response.status_code,
            "ok": response.is_success,
            "url": str(response.url),
            "method": config.method,
            "data": parsed_data,
            "request": {
                "url": rendered_url,
                "method": config.method,
                "headers": rendered_headers,
                "query_params": rendered_query_params,
                "body": rendered_body,
            },
        }
        if response_headers:
            output_content["headers"] = response_headers

        output_context = {**message.context}
        output_context["last_http_response"] = output_content

        metadata = {
            "applet": HTTP_REQUEST_NODE_TYPE,
            "status": "success" if response.is_success else "error",
            "method": config.method,
            "status_code": response.status_code,
            "url": str(response.url),
        }
        return AppletMessage(content=output_content, context=output_context, metadata=metadata)

    def _resolve_config(self, message: AppletMessage) -> HTTPRequestNodeConfigModel:
        node_data = message.metadata.get("node_data", {})
        if not isinstance(node_data, dict):
            node_data = {}

        context_config = message.context.get("http_request_config", {})
        if not isinstance(context_config, dict):
            context_config = {}
        legacy_context_config = message.context.get("http_config", {})
        if isinstance(legacy_context_config, dict):
            context_config = {**legacy_context_config, **context_config}

        metadata_config = message.metadata.get("http_request_config", {})
        if not isinstance(metadata_config, dict):
            metadata_config = {}
        legacy_metadata_config = message.metadata.get("http_config", {})
        if isinstance(legacy_metadata_config, dict):
            metadata_config = {**legacy_metadata_config, **metadata_config}

        merged = {**context_config, **metadata_config, **node_data}
        config_payload = {
            "label": merged.get("label", "HTTP Request"),
            "url": merged.get("url"),
            "method": merged.get("method", "GET"),
            "headers": merged.get("headers", {}),
            "query_params": merged.get(
                "query_params", merged.get("queryParams", merged.get("params", {}))
            ),
            "body_template": merged.get(
                "body_template", merged.get("bodyTemplate", merged.get("body"))
            ),
            "body_type": merged.get("body_type", merged.get("bodyType", "auto")),
            "timeout_seconds": merged.get("timeout_seconds", merged.get("timeoutSeconds", 30.0)),
            "allow_redirects": merged.get("allow_redirects", merged.get("allowRedirects", True)),
            "verify_ssl": merged.get("verify_ssl", merged.get("verifySSL", True)),
            "include_response_headers": merged.get(
                "include_response_headers",
                merged.get("includeResponseHeaders", True),
            ),
            "extra": merged.get("extra", {}),
            "auth_type": str(merged.get("auth_type", "none")),
            "auth_value": merged.get("auth_value"),
            "auth_header_name": str(merged.get("auth_header_name", "X-API-Key")),
            "max_retries": int(merged.get("max_retries", 0)),
            "retry_backoff_factor": float(merged.get("retry_backoff_factor", 0.5)),
        }
        config = HTTPRequestNodeConfigModel.model_validate(config_payload)

        if config.auth_type == "bearer" and config.auth_value:
            config.headers.setdefault("Authorization", f"Bearer {config.auth_value}")
        elif config.auth_type == "basic" and config.auth_value:
            import base64

            encoded = base64.b64encode(config.auth_value.encode()).decode()
            config.headers.setdefault("Authorization", f"Basic {encoded}")
        elif config.auth_type == "api_key" and config.auth_value:
            config.headers.setdefault(config.auth_header_name, config.auth_value)

        return config

    def _template_data(self, message: AppletMessage) -> dict[str, Any]:
        context = message.context if isinstance(message.context, dict) else {}
        results = context.get("results", {})
        if not isinstance(results, dict):
            results = {}
        return {
            "input": message.content,
            "content": message.content,
            "context": context,
            "results": results,
            "run_id": context.get("run_id", message.metadata.get("run_id")),
            "node_id": message.metadata.get("node_id"),
        }

    def _normalize_headers(self, raw_headers: Any) -> dict[str, str]:
        if not isinstance(raw_headers, dict):
            return {}
        headers: dict[str, str] = {}
        for key, value in raw_headers.items():
            if value is None:
                continue
            key_str = str(key).strip()
            if not key_str:
                continue
            if isinstance(value, (dict, list)):
                headers[key_str] = json.dumps(value, ensure_ascii=False)
            else:
                headers[key_str] = str(value)
        return headers

    def _normalize_query_params(self, raw_query_params: Any) -> dict[str, Any]:
        if not isinstance(raw_query_params, dict):
            return {}
        query_params: dict[str, Any] = {}
        for key, value in raw_query_params.items():
            key_str = str(key).strip()
            if not key_str or value is None:
                continue
            query_params[key_str] = value
        return query_params

    def _default_body_template(self, message: AppletMessage, method: str) -> Any | None:
        if method not in {"POST", "PUT", "PATCH", "DELETE"}:
            return None
        if message.content is None:
            return None
        return message.content

    def _apply_body_payload(
        self,
        body_type: str,
        body: Any,
        request_kwargs: dict[str, Any],
    ) -> None:
        if body_type == "json" or (body_type == "auto" and isinstance(body, (dict, list))):
            request_kwargs["json"] = body
            return

        if body_type == "form":
            if isinstance(body, dict):
                request_kwargs["data"] = {
                    str(key): (
                        json.dumps(value, ensure_ascii=False)
                        if isinstance(value, (dict, list))
                        else str(value)
                    )
                    for key, value in body.items()
                }
            else:
                request_kwargs["data"] = {"value": str(body)}
            return

        if body_type == "none":
            return

        if isinstance(body, (dict, list)):
            request_kwargs["content"] = json.dumps(body, ensure_ascii=False)
        else:
            request_kwargs["content"] = str(body)

    def _parse_response_data(self, response: httpx.Response) -> Any:
        content_type = response.headers.get("content-type", "").lower()
        if "application/json" in content_type:
            try:
                return response.json()
            except Exception:
                pass  # OMIT JUSTIFIED: decode fallback — falls through to json.loads(text_body)

        text_body = response.text
        if not text_body:
            return ""
        try:
            return json.loads(text_body)
        except Exception:
            return text_body


class TransformNodeApplet(BaseApplet):
    """Config-driven data transformation node."""

    VERSION = "1.0.0"
    CAPABILITIES = [
        "json-path-extract",
        "template-string",
        "regex-replace",
        "split-join",
        "config-driven-transform",
    ]

    async def on_message(self, message: AppletMessage) -> AppletMessage:
        try:
            config = self._resolve_config(message)
        except Exception as exc:
            return AppletMessage(
                content={"error": f"Invalid transform configuration: {exc}"},
                context=message.context,
                metadata={"applet": TRANSFORM_NODE_TYPE, "status": "error"},
            )

        template_data = self._template_data(message)
        source_value = _render_template_payload(config.source, template_data)

        try:
            output_value = self._apply_transform(
                config=config,
                source_value=source_value,
                template_data=template_data,
            )
        except Exception as exc:
            return AppletMessage(
                content={
                    "ok": False,
                    "operation": config.operation,
                    "input": source_value,
                    "error": str(exc),
                },
                context=message.context,
                metadata={
                    "applet": TRANSFORM_NODE_TYPE,
                    "status": "error",
                    "operation": config.operation,
                },
            )

        output_content = {
            "ok": True,
            "operation": config.operation,
            "input": source_value,
            "output": output_value,
        }
        output_context = {**message.context, "last_transform_response": output_content}
        output_metadata = {
            "applet": TRANSFORM_NODE_TYPE,
            "status": "success",
            "operation": config.operation,
        }
        return AppletMessage(
            content=output_content, context=output_context, metadata=output_metadata
        )

    def _resolve_config(self, message: AppletMessage) -> TransformNodeConfigModel:
        node_data = message.metadata.get("node_data", {})
        if not isinstance(node_data, dict):
            node_data = {}

        context_config = message.context.get("transform_config", {})
        if not isinstance(context_config, dict):
            context_config = {}
        legacy_context_config = message.context.get("transform", {})
        if isinstance(legacy_context_config, dict):
            context_config = {**legacy_context_config, **context_config}

        metadata_config = message.metadata.get("transform_config", {})
        if not isinstance(metadata_config, dict):
            metadata_config = {}
        legacy_metadata_config = message.metadata.get("transform", {})
        if isinstance(legacy_metadata_config, dict):
            metadata_config = {**legacy_metadata_config, **metadata_config}

        merged = {**context_config, **metadata_config, **node_data}
        config_payload = {
            "label": merged.get("label", "Transform"),
            "operation": merged.get("operation", "template"),
            "source": merged.get("source", merged.get("input", "{{content}}")),
            "json_path": merged.get("json_path", merged.get("jsonPath", merged.get("path", "$"))),
            "template": merged.get(
                "template",
                merged.get("template_string", merged.get("templateString", "{{source}}")),
            ),
            "regex_pattern": merged.get(
                "regex_pattern", merged.get("regexPattern", merged.get("pattern", ""))
            ),
            "regex_replacement": merged.get(
                "regex_replacement",
                merged.get("regexReplacement", merged.get("replacement", "")),
            ),
            "regex_flags": merged.get("regex_flags", merged.get("regexFlags", "")),
            "regex_count": merged.get("regex_count", merged.get("regexCount", 0)),
            "split_delimiter": merged.get(
                "split_delimiter",
                merged.get("splitDelimiter", merged.get("delimiter", ",")),
            ),
            "split_maxsplit": merged.get(
                "split_maxsplit",
                merged.get("splitMaxsplit", merged.get("maxsplit", -1)),
            ),
            "split_index": merged.get("split_index", merged.get("splitIndex")),
            "join_delimiter": merged.get(
                "join_delimiter",
                merged.get("joinDelimiter", merged.get("joiner", ",")),
            ),
            "return_list": merged.get("return_list", merged.get("returnList", False)),
            "strip_items": merged.get("strip_items", merged.get("stripItems", False)),
            "drop_empty": merged.get("drop_empty", merged.get("dropEmpty", False)),
            "extra": merged.get("extra", {}),
        }
        return TransformNodeConfigModel.model_validate(config_payload)

    def _template_data(self, message: AppletMessage) -> dict[str, Any]:
        context = message.context if isinstance(message.context, dict) else {}
        results = context.get("results", {})
        if not isinstance(results, dict):
            results = {}
        return {
            "input": message.content,
            "content": message.content,
            "context": context,
            "results": results,
            "metadata": message.metadata,
            "run_id": context.get("run_id", message.metadata.get("run_id")),
            "node_id": message.metadata.get("node_id"),
        }

    def _apply_transform(
        self,
        config: TransformNodeConfigModel,
        source_value: Any,
        template_data: dict[str, Any],
    ) -> Any:
        if config.operation == "json_path":
            return self._transform_json_path(source_value, config.json_path)
        if config.operation == "template":
            return self._transform_template(config.template, source_value, template_data)
        if config.operation == "regex_replace":
            return self._transform_regex_replace(
                source_value=source_value,
                pattern=config.regex_pattern,
                replacement=config.regex_replacement,
                flags_text=config.regex_flags,
                count=config.regex_count,
            )
        if config.operation == "split_join":
            return self._transform_split_join(source_value, config)
        raise ValueError(f"Unsupported transform operation: {config.operation}")

    def _transform_json_path(self, source_value: Any, json_path: str) -> Any:
        result, found = _resolve_json_path(source_value, json_path)
        if not found:
            raise ValueError(f"json_path not found: {json_path}")
        return result

    def _transform_template(
        self,
        template: str,
        source_value: Any,
        template_data: dict[str, Any],
    ) -> Any:
        scope = {
            **template_data,
            "source": source_value,
            "value": source_value,
        }
        return _render_template_payload(template, scope)

    def _transform_regex_replace(
        self,
        source_value: Any,
        pattern: str,
        replacement: str,
        flags_text: str,
        count: int,
    ) -> str:
        if not pattern:
            raise ValueError("regex_pattern is required for regex_replace operation")

        flags = 0
        if "i" in flags_text:
            flags |= re.IGNORECASE
        if "m" in flags_text:
            flags |= re.MULTILINE
        if "s" in flags_text:
            flags |= re.DOTALL
        if "x" in flags_text:
            flags |= re.VERBOSE

        compiled = re.compile(pattern, flags=flags)
        source_text = _as_text(source_value)
        return compiled.sub(replacement, source_text, count=count)

    def _transform_split_join(
        self,
        source_value: Any,
        config: TransformNodeConfigModel,
    ) -> Any:
        if isinstance(source_value, list):
            parts = [_as_text(item) for item in source_value]
        else:
            source_text = _as_text(source_value)
            if config.split_delimiter == "":
                parts = list(source_text)
            else:
                maxsplit = config.split_maxsplit
                parts = source_text.split(config.split_delimiter, maxsplit)

        normalized: list[str] = []
        for item in parts:
            value = item.strip() if config.strip_items else item
            if config.drop_empty and value == "":
                continue
            normalized.append(value)

        if config.split_index is not None:
            if config.split_index >= len(normalized):
                raise ValueError("split_index is out of range")
            return normalized[config.split_index]

        if config.return_list:
            return normalized

        return config.join_delimiter.join(normalized)


class IfElseNodeApplet(BaseApplet):
    """Conditional routing node that evaluates data and selects a true/false branch."""

    VERSION = "1.0.0"
    CAPABILITIES = [
        "conditional-routing",
        "contains-condition",
        "equals-condition",
        "regex-condition",
        "json-path-condition",
    ]

    async def on_message(self, message: AppletMessage) -> AppletMessage:
        base_context = message.context if isinstance(message.context, dict) else {}

        try:
            config = self._resolve_config(message)
        except Exception as exc:
            error_content = {
                "ok": False,
                "operation": "unknown",
                "result": False,
                "branch": "false",
                "error": f"Invalid if/else configuration: {exc}",
            }
            return AppletMessage(
                content=error_content,
                context={**base_context, "last_if_else_response": error_content},
                metadata={
                    "applet": IF_ELSE_NODE_TYPE,
                    "status": "error",
                    "operation": "unknown",
                    "branch": "false",
                    "condition_result": False,
                },
            )

        template_data = self._template_data(message)
        source_value = _render_template_payload(config.source, template_data)
        expected_value = (
            _render_template_payload(config.value, template_data)
            if config.value is not None
            else None
        )

        try:
            result, details = self._evaluate_condition(config, source_value, expected_value)
            if config.negate:
                result = not result
                details["negated"] = True
        except Exception as exc:
            error_content = {
                "ok": False,
                "operation": config.operation,
                "source": source_value,
                "value": expected_value,
                "result": False,
                "branch": "false",
                "error": str(exc),
            }
            return AppletMessage(
                content=error_content,
                context={**base_context, "last_if_else_response": error_content},
                metadata={
                    "applet": IF_ELSE_NODE_TYPE,
                    "status": "error",
                    "operation": config.operation,
                    "branch": "false",
                    "condition_result": False,
                },
            )

        branch = "true" if result else "false"
        output_content = {
            "ok": True,
            "operation": config.operation,
            "source": source_value,
            "value": expected_value,
            "result": result,
            "branch": branch,
            "details": details,
        }
        output_context = {**base_context, "last_if_else_response": output_content}
        output_metadata = {
            "applet": IF_ELSE_NODE_TYPE,
            "status": "success",
            "operation": config.operation,
            "branch": branch,
            "condition_result": result,
        }
        return AppletMessage(
            content=output_content, context=output_context, metadata=output_metadata
        )

    def _resolve_config(self, message: AppletMessage) -> IfElseNodeConfigModel:
        context = message.context if isinstance(message.context, dict) else {}
        node_data = message.metadata.get("node_data", {})
        if not isinstance(node_data, dict):
            node_data = {}

        context_config: dict[str, Any] = {}
        for key in ("if_else_config", "ifelse_config", "condition_config", "if_config"):
            candidate = context.get(key)
            if isinstance(candidate, dict):
                context_config = {**context_config, **candidate}

        metadata_config: dict[str, Any] = {}
        for key in ("if_else_config", "ifelse_config", "condition_config", "if_config"):
            candidate = message.metadata.get(key)
            if isinstance(candidate, dict):
                metadata_config = {**metadata_config, **candidate}

        merged = {**context_config, **metadata_config, **node_data}
        config_payload = {
            "label": merged.get("label", "If / Else"),
            "operation": merged.get(
                "operation",
                merged.get("condition", merged.get("match_type", "equals")),
            ),
            "source": merged.get(
                "source",
                merged.get("left", merged.get("input", "{{content}}")),
            ),
            "value": merged.get(
                "value",
                merged.get("expected", merged.get("right")),
            ),
            "case_sensitive": merged.get(
                "case_sensitive",
                merged.get("caseSensitive", False),
            ),
            "negate": merged.get("negate", merged.get("not", False)),
            "regex_pattern": merged.get(
                "regex_pattern",
                merged.get("regexPattern", merged.get("pattern", "")),
            ),
            "regex_flags": merged.get("regex_flags", merged.get("regexFlags", "")),
            "json_path": merged.get("json_path", merged.get("jsonPath", merged.get("path", "$"))),
            "true_target": merged.get(
                "true_target",
                merged.get("trueTarget", merged.get("on_true")),
            ),
            "false_target": merged.get(
                "false_target",
                merged.get("falseTarget", merged.get("on_false")),
            ),
            "extra": merged.get("extra", {}),
        }
        return IfElseNodeConfigModel.model_validate(config_payload)

    def _template_data(self, message: AppletMessage) -> dict[str, Any]:
        context = message.context if isinstance(message.context, dict) else {}
        results = context.get("results", {})
        if not isinstance(results, dict):
            results = {}
        return {
            "input": message.content,
            "content": message.content,
            "context": context,
            "results": results,
            "metadata": message.metadata,
            "run_id": context.get("run_id", message.metadata.get("run_id")),
            "node_id": message.metadata.get("node_id"),
        }

    def _evaluate_condition(
        self,
        config: IfElseNodeConfigModel,
        source_value: Any,
        expected_value: Any,
    ) -> tuple[bool, dict[str, Any]]:
        if config.operation == "contains":
            matched = self._evaluate_contains(
                source_value=source_value,
                expected_value=expected_value,
                case_sensitive=config.case_sensitive,
            )
            return matched, {"mode": "contains"}

        if config.operation == "equals":
            matched = self._evaluate_equals(
                left=source_value,
                right=expected_value,
                case_sensitive=config.case_sensitive,
            )
            return matched, {"mode": "equals"}

        if config.operation == "regex":
            pattern = config.regex_pattern
            if not pattern and expected_value is not None:
                pattern = _as_text(expected_value)
            if not pattern:
                raise ValueError("regex_pattern is required for regex operation")

            flags = self._compile_regex_flags(config.regex_flags)
            source_text = _as_text(source_value)
            matched = re.search(pattern, source_text, flags=flags) is not None
            return matched, {"mode": "regex", "pattern": pattern}

        if config.operation == "json_path":
            matched_value, found = _resolve_json_path(source_value, config.json_path)
            if not found:
                return False, {"mode": "json_path", "found": False}
            if expected_value is None:
                return True, {"mode": "json_path", "found": True, "value": matched_value}
            matched = self._evaluate_equals(
                left=matched_value,
                right=expected_value,
                case_sensitive=config.case_sensitive,
            )
            return matched, {
                "mode": "json_path",
                "found": True,
                "value": matched_value,
            }

        raise ValueError(f"Unsupported if/else operation: {config.operation}")

    def _evaluate_contains(
        self,
        source_value: Any,
        expected_value: Any,
        case_sensitive: bool,
    ) -> bool:
        if expected_value is None:
            return False

        if isinstance(source_value, dict):
            if expected_value in source_value:
                return True
            return expected_value in source_value.values()

        if isinstance(source_value, (list, tuple, set)):
            return expected_value in source_value

        source_text = _as_text(source_value)
        expected_text = _as_text(expected_value)
        if not case_sensitive:
            source_text = source_text.lower()
            expected_text = expected_text.lower()
        return expected_text in source_text

    def _evaluate_equals(
        self,
        left: Any,
        right: Any,
        case_sensitive: bool,
    ) -> bool:
        if isinstance(left, str) and isinstance(right, str) and not case_sensitive:
            return left.lower() == right.lower()
        return left == right

    def _compile_regex_flags(self, flags_text: str) -> int:
        flags = 0
        if "i" in flags_text:
            flags |= re.IGNORECASE
        if "m" in flags_text:
            flags |= re.MULTILINE
        if "s" in flags_text:
            flags |= re.DOTALL
        if "x" in flags_text:
            flags |= re.VERBOSE
        return flags


# ============================================================
# Compound Condition Evaluator + Branch/Merge Applets (N-37)
# ============================================================


class CompoundConditionEvaluator:
    """Evaluates compound boolean condition trees.

    Condition node types:
      - "leaf": {"type": "leaf", "source": str, "operation": str, "value": str}
        Operations: equals, not_equals, contains, not_contains, starts_with,
                    ends_with, regex, gt, gte, lt, lte, is_empty, is_not_empty,
                    is_null, is_not_null, type_is (value = "str"/"int"/"list"/"dict"/"bool")
      - "and":  {"type": "and",  "conditions": [<condition_node>, ...]}
      - "or":   {"type": "or",   "conditions": [<condition_node>, ...]}
      - "not":  {"type": "not",  "condition":  <condition_node>}

    The `source` in a leaf can be:
      - a literal value
      - a template like "{{output.field}}" or "{{data.key}}" (resolve from context)
    """

    SUPPORTED_OPERATIONS: dict[str, str] = {
        "equals": "Strict equality comparison",
        "not_equals": "Strict inequality comparison",
        "contains": "Substring or collection membership check",
        "not_contains": "Negated contains check",
        "starts_with": "String prefix check",
        "ends_with": "String suffix check",
        "regex": "Regular expression match",
        "gt": "Numeric greater-than comparison",
        "gte": "Numeric greater-than-or-equal comparison",
        "lt": "Numeric less-than comparison",
        "lte": "Numeric less-than-or-equal comparison",
        "is_empty": "True when value is empty string, list, dict, or None",
        "is_not_empty": "True when value is non-empty",
        "is_null": "True when value is None or the string 'null'",
        "is_not_null": "True when value is not None and not the string 'null'",
        "type_is": "Check runtime type (str, int, float, list, dict, bool)",
    }

    def evaluate(self, condition: dict, context: dict) -> bool:
        """Evaluate a condition node against context.

        Args:
            condition: A condition node dict with a "type" key.
            context: Execution context used to resolve template sources.

        Returns:
            Boolean result of the condition.

        Raises:
            ValueError: If the condition node type or operation is unsupported.
        """
        node_type = condition.get("type")

        if node_type == "leaf":
            source_raw = condition.get("source", "")
            operation = condition.get("operation", "equals")
            expected_str = condition.get("value", "")
            actual = self._resolve_source(source_raw, context)
            return self._eval_leaf(operation, actual, expected_str)

        if node_type == "and":
            sub_conditions = condition.get("conditions", [])
            if not sub_conditions:
                return True
            return all(self.evaluate(c, context) for c in sub_conditions)

        if node_type == "or":
            sub_conditions = condition.get("conditions", [])
            if not sub_conditions:
                return False
            return any(self.evaluate(c, context) for c in sub_conditions)

        if node_type == "not":
            inner = condition.get("condition")
            if inner is None:
                raise ValueError("'not' condition node requires a 'condition' key")
            return not self.evaluate(inner, context)

        raise ValueError(f"Unsupported condition node type: {node_type!r}")

    def _resolve_source(self, source: str, context: dict) -> Any:
        """Resolve {{output.x}}, {{data.x}}, {{input.x}} from context.

        Args:
            source: A literal string or a {{path}} template token.
            context: Execution context dict.

        Returns:
            The resolved value, or the original source string if no template token found.
        """
        if not isinstance(source, str):
            return source
        template_data = {
            "output": context.get("output", context.get("results", {})),
            "data": context.get("data", context),
            "input": context.get("input", context.get("content")),
            "context": context,
            "results": context.get("results", {}),
        }
        return _render_template_payload(source, template_data)

    def _eval_leaf(self, op: str, actual: Any, expected_str: str) -> bool:
        """Evaluate a single leaf comparison.

        Args:
            op: Operation name (one of SUPPORTED_OPERATIONS keys).
            actual: The resolved actual value.
            expected_str: The expected value as a string (coerced as needed).

        Returns:
            Boolean result.

        Raises:
            ValueError: If the operation is unsupported or regex pattern is invalid.
        """
        # Unary operations (do not use expected_str)
        if op == "is_null":
            return actual is None or actual == "null"
        if op == "is_not_null":
            return actual is not None and actual != "null"
        if op == "is_empty":
            if actual is None:
                return True
            if isinstance(actual, (str, list, dict)):
                return len(actual) == 0
            return False
        if op == "is_not_empty":
            if actual is None:
                return False
            if isinstance(actual, (str, list, dict)):
                return len(actual) > 0
            return True

        # Type check
        if op == "type_is":
            type_map: dict[str, type] = {
                "str": str,
                "int": int,
                "float": float,
                "list": list,
                "dict": dict,
                "bool": bool,
            }
            expected_type = type_map.get(expected_str.strip().lower())
            if expected_type is None:
                raise ValueError(
                    f"type_is: unsupported type name {expected_str!r}. "
                    f"Must be one of: {', '.join(type_map)}"
                )
            return isinstance(actual, expected_type)

        # String operations
        actual_str = _as_text(actual)
        if op == "starts_with":
            return actual_str.startswith(expected_str)
        if op == "ends_with":
            return actual_str.endswith(expected_str)

        if op == "contains":
            if isinstance(actual, (list, dict)):
                return expected_str in actual
            return expected_str in actual_str
        if op == "not_contains":
            if isinstance(actual, (list, dict)):
                return expected_str not in actual
            return expected_str not in actual_str

        if op == "regex":
            try:
                return re.search(expected_str, actual_str) is not None
            except re.error as exc:
                raise ValueError(f"regex: invalid pattern {expected_str!r}: {exc}") from exc

        # Equality
        if op == "equals":
            # Try coercing to numeric for comparison when both sides look numeric
            try:
                actual_num = float(actual) if not isinstance(actual, bool) else actual
                expected_num = float(expected_str)
                return actual_num == expected_num
            except (ValueError, TypeError):
                pass
            return str(actual) == expected_str

        if op == "not_equals":
            try:
                actual_num = float(actual) if not isinstance(actual, bool) else actual
                expected_num = float(expected_str)
                return actual_num != expected_num
            except (ValueError, TypeError):
                pass
            return str(actual) != expected_str

        # Numeric comparisons
        if op in ("gt", "gte", "lt", "lte"):
            try:
                actual_num = float(actual)
                expected_num = float(expected_str)
            except (ValueError, TypeError) as exc:
                raise ValueError(
                    f"{op}: both operands must be numeric. "
                    f"Got actual={actual!r}, expected={expected_str!r}"
                ) from exc
            if op == "gt":
                return actual_num > expected_num
            if op == "gte":
                return actual_num >= expected_num
            if op == "lt":
                return actual_num < expected_num
            return actual_num <= expected_num  # lte

        raise ValueError(f"Unsupported leaf operation: {op!r}")


class BranchApplet(BaseApplet):
    """Multi-output conditional routing based on compound condition trees.

    Node data schema::

        {
          "branches": [
            {
              "id": "branch_1",
              "label": "High Value",
              "condition": {
                "type": "and",
                "conditions": [
                  {"type": "leaf", "source": "{{output.score}}", "operation": "gte", "value": "80"},
                  {"type": "leaf", "source": "{{output.status}}", "operation": "equals", "value": "active"}
                ]
              }
            }
          ],
          "default_branch": "default"
        }

    Returns ``{"_branch": "<matched_branch_id>", "data": <input_data>}``.
    The execution engine uses ``_branch`` + ``sourceHandle`` to route to the
    correct downstream node.
    """

    VERSION = "1.0.0"
    CAPABILITIES = [
        "compound-condition",
        "multi-branch-routing",
        "and-or-not-logic",
        "template-source-resolution",
    ]

    _evaluator = CompoundConditionEvaluator()

    async def on_message(self, message: AppletMessage) -> AppletMessage:
        """Evaluate branch conditions and return the first matching branch ID."""
        base_context = message.context if isinstance(message.context, dict) else {}
        node_data = message.metadata.get("node_data", {})
        if not isinstance(node_data, dict):
            node_data = {}

        branches: list[dict] = node_data.get("branches", [])
        default_branch: str = node_data.get("default_branch", "default")

        # Build evaluation context from input
        eval_context: dict[str, Any] = {
            **base_context,
            "output": message.content if isinstance(message.content, dict) else {},
            "input": message.content,
            "content": message.content,
        }

        matched_branch = default_branch
        for branch_def in branches:
            branch_id = branch_def.get("id", "")
            condition = branch_def.get("condition")
            if not condition or not isinstance(condition, dict):
                logger.warning(
                    "BranchApplet: branch %r has no valid condition — skipping",
                    branch_id,
                )
                continue
            try:
                result = self._evaluator.evaluate(condition, eval_context)
            except Exception as exc:
                logger.warning(
                    "BranchApplet: error evaluating branch %r condition: %s",
                    branch_id,
                    exc,
                )
                continue
            if result:
                matched_branch = branch_id
                break

        output_content = {"_branch": matched_branch, "data": message.content}
        output_metadata: dict[str, Any] = {
            **message.metadata,
            "applet": BRANCH_NODE_TYPE,
            "status": "success",
            "matched_branch": matched_branch,
        }
        output_context = {**base_context, "last_branch_response": output_content}
        return AppletMessage(
            content=output_content,
            context=output_context,
            metadata=output_metadata,
        )


class CompoundMergeApplet(BaseApplet):
    """Collects output from multiple upstream branches and merges them.

    Node data schema::

        {"merge_strategy": "first"}  // "first", "all", "array"

    Strategies:
      - ``"first"``  — pass input_data through as-is (first-wins semantics)
      - ``"all"``    — wrap input_data in a dict keyed ``"merged"``
      - ``"array"``  — wrap input_data in a list
    """

    VERSION = "1.0.0"
    CAPABILITIES = [
        "fan-in",
        "branch-merge",
        "merge-first",
        "merge-all",
        "merge-array",
    ]

    async def on_message(self, message: AppletMessage) -> AppletMessage:
        """Merge incoming branch data according to the configured strategy."""
        base_context = message.context if isinstance(message.context, dict) else {}
        node_data = message.metadata.get("node_data", {})
        if not isinstance(node_data, dict):
            node_data = {}

        strategy = node_data.get("merge_strategy", "first")
        input_data = message.content

        try:
            merged = self._apply_strategy(strategy, input_data)
        except Exception as exc:
            logger.warning("CompoundMergeApplet: error applying strategy %r: %s", strategy, exc)
            merged = input_data

        output_content = {
            "ok": True,
            "strategy": strategy,
            "output": merged,
        }
        output_context = {**base_context, "last_compound_merge_response": output_content}
        output_metadata: dict[str, Any] = {
            **message.metadata,
            "applet": COMPOUND_MERGE_NODE_TYPE,
            "status": "success",
            "strategy": strategy,
        }
        return AppletMessage(
            content=output_content,
            context=output_context,
            metadata=output_metadata,
        )

    def _apply_strategy(self, strategy: str, input_data: Any) -> Any:
        """Apply the selected merge strategy to input_data.

        Args:
            strategy: One of "first", "all", "array".
            input_data: Incoming branch data.

        Returns:
            Merged output.

        Raises:
            ValueError: If strategy is unrecognised.
        """
        if strategy == "first":
            return input_data
        if strategy == "all":
            return {"merged": input_data}
        if strategy == "array":
            return [input_data]
        raise ValueError(f"Unsupported merge_strategy: {strategy!r}")


class MergeNodeApplet(BaseApplet):
    """Fan-in node that merges multiple upstream branch outputs."""

    VERSION = "1.0.0"
    CAPABILITIES = [
        "fan-in",
        "merge-array",
        "merge-concatenate",
        "merge-first-wins",
    ]

    async def on_message(self, message: AppletMessage) -> AppletMessage:
        base_context = message.context if isinstance(message.context, dict) else {}

        try:
            config = self._resolve_config(message)
        except Exception as exc:
            error_content = {
                "ok": False,
                "strategy": "unknown",
                "output": None,
                "count": 0,
                "error": f"Invalid merge configuration: {exc}",
            }
            return AppletMessage(
                content=error_content,
                context={**base_context, "last_merge_response": error_content},
                metadata={"applet": MERGE_NODE_TYPE, "status": "error"},
            )

        inputs = self._normalize_inputs(message.content)
        merged_output = self._merge_inputs(
            strategy=config.strategy,
            inputs=inputs,
            delimiter=config.delimiter,
        )

        output_content = {
            "ok": True,
            "strategy": config.strategy,
            "count": len(inputs),
            "inputs": inputs,
            "output": merged_output,
        }
        output_context = {**base_context, "last_merge_response": output_content}
        output_metadata = {
            "applet": MERGE_NODE_TYPE,
            "status": "success",
            "strategy": config.strategy,
            "input_count": len(inputs),
        }
        return AppletMessage(
            content=output_content, context=output_context, metadata=output_metadata
        )

    def _resolve_config(self, message: AppletMessage) -> MergeNodeConfigModel:
        context = message.context if isinstance(message.context, dict) else {}
        node_data = message.metadata.get("node_data", {})
        if not isinstance(node_data, dict):
            node_data = {}

        context_config = context.get("merge_config", {})
        if not isinstance(context_config, dict):
            context_config = {}

        metadata_config = message.metadata.get("merge_config", {})
        if not isinstance(metadata_config, dict):
            metadata_config = {}

        merged = {**context_config, **metadata_config, **node_data}
        config_payload = {
            "label": merged.get("label", "Merge"),
            "strategy": merged.get(
                "strategy", merged.get("merge_strategy", merged.get("mergeStrategy", "array"))
            ),
            "delimiter": merged.get(
                "delimiter", merged.get("join_delimiter", merged.get("joinDelimiter", "\n"))
            ),
            "extra": merged.get("extra", {}),
        }
        return MergeNodeConfigModel.model_validate(config_payload)

    def _normalize_inputs(self, content: Any) -> list[Any]:
        if isinstance(content, dict):
            raw_inputs = content.get("inputs")
            if isinstance(raw_inputs, list):
                return list(raw_inputs)
            if raw_inputs is not None:
                return [raw_inputs]
            if "input" in content:
                return [content.get("input")]
            return [content]

        if isinstance(content, list):
            return list(content)
        if content is None:
            return []
        return [content]

    def _merge_inputs(
        self,
        strategy: str,
        inputs: list[Any],
        delimiter: str,
    ) -> Any:
        if strategy == "first_wins":
            return inputs[0] if inputs else None
        if strategy == "concatenate":
            return delimiter.join(_as_text(item) for item in inputs)
        return inputs


class CodeNodeApplet(BaseApplet):
    """Sandboxed code execution node for Python and JavaScript."""

    VERSION = "1.0.0"
    CAPABILITIES = [
        "code-execution",
        "python",
        "javascript",
        "sandboxed-subprocess",
        "resource-limits",
    ]

    async def on_message(self, message: AppletMessage) -> AppletMessage:
        try:
            config = self._resolve_config(message)
        except Exception as exc:
            return AppletMessage(
                content={"error": f"Invalid code node configuration: {exc}"},
                context=message.context,
                metadata={"applet": CODE_NODE_TYPE, "status": "error"},
            )

        code_text = config.code
        if not code_text.strip() and isinstance(message.content, dict):
            raw_code = message.content.get("code")
            if isinstance(raw_code, str):
                code_text = raw_code

        if not code_text.strip():
            return AppletMessage(
                content={"error": "No code provided"},
                context=message.context,
                metadata={"applet": CODE_NODE_TYPE, "status": "error"},
            )

        started_at = time.perf_counter()
        execution_result = await self._execute_sandboxed_code(message, config, code_text)
        duration_ms = round((time.perf_counter() - started_at) * 1000.0, 3)

        output_content = {
            **execution_result,
            "language": config.language,
            "duration_ms": duration_ms,
        }
        output_context = {**message.context, "last_code_response": output_content}
        output_metadata = {
            "applet": CODE_NODE_TYPE,
            "status": "success" if execution_result.get("ok") else "error",
            "language": config.language,
            "timed_out": execution_result.get("timed_out", False),
            "exit_code": execution_result.get("exit_code"),
            "duration_ms": duration_ms,
        }
        return AppletMessage(
            content=output_content, context=output_context, metadata=output_metadata
        )

    def _resolve_config(self, message: AppletMessage) -> CodeNodeConfigModel:
        node_data = message.metadata.get("node_data", {})
        if not isinstance(node_data, dict):
            node_data = {}

        context_config = message.context.get("code_config", {})
        if not isinstance(context_config, dict):
            context_config = {}

        metadata_config = message.metadata.get("code_config", {})
        if not isinstance(metadata_config, dict):
            metadata_config = {}

        merged = {**context_config, **metadata_config, **node_data}
        config_payload = {
            "label": merged.get("label", "Code"),
            "language": merged.get("language", merged.get("runtime", "python")),
            "code": merged.get("code", ""),
            "timeout_seconds": merged.get("timeout_seconds", merged.get("timeoutSeconds", 5.0)),
            "cpu_time_seconds": merged.get("cpu_time_seconds", merged.get("cpuTimeSeconds", 3)),
            "memory_limit_mb": merged.get("memory_limit_mb", merged.get("memoryLimitMb", 256)),
            "max_output_bytes": merged.get(
                "max_output_bytes", merged.get("maxOutputBytes", 262144)
            ),
            "working_dir": merged.get("working_dir", merged.get("workingDir", "/tmp")),
            "env": merged.get("env", {}),
            "extra": merged.get("extra", {}),
        }
        return CodeNodeConfigModel.model_validate(config_payload)

    async def _execute_sandboxed_code(
        self,
        message: AppletMessage,
        config: CodeNodeConfigModel,
        code_text: str,
    ) -> dict[str, Any]:
        sandbox_dir = tempfile.mkdtemp(prefix="synapps-code-", dir="/tmp")
        requested_workdir = _safe_tmp_dir(config.working_dir)
        if requested_workdir == "/tmp":
            workdir = sandbox_dir
        else:
            workdir = requested_workdir
            Path(workdir).mkdir(parents=True, exist_ok=True)

        if config.language == "python":
            runner_path = Path(sandbox_dir) / "sandbox_runner.py"
            runner_path.write_text(PYTHON_CODE_WRAPPER, encoding="utf-8")
            executable = os.environ.get("CODE_NODE_PYTHON_BIN") or sys.executable or "python3"
            command = [executable, "-I", "-B", str(runner_path)]
        else:
            runner_path = Path(sandbox_dir) / "sandbox_runner.js"
            runner_path.write_text(JAVASCRIPT_CODE_WRAPPER, encoding="utf-8")
            executable = os.environ.get("CODE_NODE_NODE_BIN") or "node"
            command = [executable, str(runner_path)]

        payload = {
            "code": code_text,
            "data": message.content,
            "context": message.context,
            "metadata": message.metadata,
            "exec_timeout_ms": max(1, int(config.timeout_seconds * 1000)),
        }
        payload_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")

        env = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": "/tmp",
            "TMPDIR": "/tmp",
            "TMP": "/tmp",
            "TEMP": "/tmp",
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUNBUFFERED": "1",
        }
        if isinstance(config.env, dict):
            for key, value in config.env.items():
                env[str(key)] = str(value)

        effective_memory_limit_mb = config.memory_limit_mb
        if config.language == "javascript":
            effective_memory_limit_mb = max(effective_memory_limit_mb, 768)

        preexec_fn = _sandbox_preexec_fn(
            cpu_time_seconds=config.cpu_time_seconds,
            memory_limit_mb=effective_memory_limit_mb,
            max_output_bytes=config.max_output_bytes,
        )

        timed_out = False
        stdout_text = ""
        stderr_text = ""
        stdout_truncated = False
        stderr_truncated = False
        return_code: int | None = None

        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=workdir,
                env=env,
                preexec_fn=preexec_fn,
            )
        except FileNotFoundError:
            return {
                "ok": False,
                "timed_out": False,
                "exit_code": None,
                "stdout": "",
                "stderr": f"Runtime not found: {command[0]}",
                "result": None,
                "error": {"message": f"Runtime not found: {command[0]}"},
                "stdout_truncated": False,
                "stderr_truncated": False,
            }

        stdout_task = asyncio.create_task(
            _read_stream_limited(process.stdout, config.max_output_bytes)
        )
        stderr_task = asyncio.create_task(
            _read_stream_limited(process.stderr, config.max_output_bytes)
        )

        try:
            if process.stdin is not None:
                process.stdin.write(payload_bytes)
                await process.stdin.drain()
                process.stdin.close()

            await asyncio.wait_for(process.wait(), timeout=config.timeout_seconds)
            return_code = process.returncode
        except TimeoutError:
            timed_out = True
            process.kill()
            await process.wait()
            return_code = process.returncode
        finally:
            stdout_bytes, stdout_truncated = await stdout_task
            stderr_bytes, stderr_truncated = await stderr_task
            stdout_text = stdout_bytes.decode("utf-8", errors="replace")
            stderr_text = stderr_bytes.decode("utf-8", errors="replace")

        if return_code in (-9, -24):
            timed_out = True

        cleaned_stdout, wrapper_payload = _extract_sandbox_result(stdout_text)
        wrapper_ok = bool(wrapper_payload and wrapper_payload.get("ok"))
        wrapper_error = wrapper_payload.get("error") if isinstance(wrapper_payload, dict) else None

        result_payload = {
            "ok": (not timed_out) and return_code == 0 and wrapper_ok,
            "timed_out": timed_out,
            "exit_code": return_code,
            "stdout": cleaned_stdout,
            "stderr": stderr_text,
            "result": wrapper_payload.get("result") if isinstance(wrapper_payload, dict) else None,
            "error": wrapper_error,
            "stdout_truncated": stdout_truncated,
            "stderr_truncated": stderr_truncated,
        }

        if timed_out and not result_payload.get("error"):
            result_payload["error"] = {"message": "Execution timed out"}
        elif return_code not in (0, None) and not result_payload.get("error"):
            result_payload["error"] = {"message": f"Process exited with code {return_code}"}
        elif wrapper_payload is None and not result_payload.get("error"):
            result_payload["error"] = {
                "message": "Sandbox wrapper did not return a structured result"
            }

        shutil.rmtree(sandbox_dir, ignore_errors=True)

        return result_payload


class ForEachNodeApplet(BaseApplet):
    """For-Each loop node that iterates over an array, executing downstream nodes per item."""

    VERSION = "1.0.0"
    CAPABILITIES = [
        "loop",
        "for-each",
        "array-iteration",
        "parallel-iteration",
        "max-iteration-limit",
    ]

    async def on_message(self, message: AppletMessage) -> AppletMessage:
        try:
            config = self._resolve_config(message)
        except Exception as exc:
            return AppletMessage(
                content={"error": f"Invalid for-each configuration: {exc}"},
                context=message.context,
                metadata={"applet": FOR_EACH_NODE_TYPE, "status": "error"},
            )

        template_data = self._template_data(message)
        resolved_source = _render_template_payload(config.array_source, template_data)

        items = self._coerce_to_list(resolved_source)
        if items is None:
            return AppletMessage(
                content={
                    "ok": False,
                    "error": "array_source did not resolve to an iterable array",
                    "resolved_value": resolved_source,
                },
                context=message.context,
                metadata={"applet": FOR_EACH_NODE_TYPE, "status": "error"},
            )

        total_items = len(items)
        effective_limit = min(total_items, config.max_iterations)
        truncated = total_items > config.max_iterations
        items = items[:effective_limit]

        node_id = message.metadata.get("node_id", "for_each")
        run_id = message.context.get("run_id", message.metadata.get("run_id"))

        if config.parallel:
            iteration_results = await self._run_parallel(items, message, config, node_id, run_id)
        else:
            iteration_results = await self._run_sequential(items, message, node_id, run_id)

        output_content = {
            "ok": True,
            "total_items": total_items,
            "iterated": len(items),
            "truncated": truncated,
            "max_iterations": config.max_iterations,
            "parallel": config.parallel,
            "results": iteration_results,
        }
        output_context = {
            **message.context,
            "last_for_each_response": output_content,
            "for_each_results": iteration_results,
        }
        output_metadata = {
            "applet": FOR_EACH_NODE_TYPE,
            "status": "success",
            "iterated": len(items),
            "truncated": truncated,
            "parallel": config.parallel,
        }
        return AppletMessage(
            content=output_content,
            context=output_context,
            metadata=output_metadata,
        )

    def _resolve_config(self, message: AppletMessage) -> ForEachNodeConfigModel:
        node_data = message.metadata.get("node_data", {})
        if not isinstance(node_data, dict):
            node_data = {}

        context_config = message.context.get("for_each_config", {})
        if not isinstance(context_config, dict):
            context_config = {}

        metadata_config = message.metadata.get("for_each_config", {})
        if not isinstance(metadata_config, dict):
            metadata_config = {}

        merged = {**context_config, **metadata_config, **node_data}
        config_payload = {
            "label": merged.get("label", "For-Each"),
            "array_source": merged.get(
                "array_source",
                merged.get("arraySource", merged.get("source", "{{input}}")),
            ),
            "max_iterations": merged.get(
                "max_iterations",
                merged.get("maxIterations", merged.get("limit", 1000)),
            ),
            "parallel": merged.get("parallel", False),
            "concurrency_limit": merged.get(
                "concurrency_limit",
                merged.get("concurrencyLimit", 10),
            ),
            "extra": merged.get("extra", {}),
        }
        return ForEachNodeConfigModel.model_validate(config_payload)

    def _template_data(self, message: AppletMessage) -> dict[str, Any]:
        context = message.context if isinstance(message.context, dict) else {}
        results = context.get("results", {})
        if not isinstance(results, dict):
            results = {}
        return {
            "input": message.content,
            "content": message.content,
            "context": context,
            "results": results,
            "metadata": message.metadata,
            "run_id": context.get("run_id", message.metadata.get("run_id")),
            "node_id": message.metadata.get("node_id"),
        }

    @staticmethod
    def _coerce_to_list(value: Any) -> list[Any] | None:
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            value = value.strip()
            if value.startswith("["):
                try:
                    parsed = json.loads(value)
                    if isinstance(parsed, list):
                        return parsed
                except (json.JSONDecodeError, ValueError):
                    pass
            return None
        if isinstance(value, dict):
            return None
        try:
            return list(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _build_iteration_message(
        item: Any,
        index: int,
        message: AppletMessage,
        node_id: str,
        run_id: str | None,
    ) -> AppletMessage:
        iteration_context = {
            **message.context,
            "for_each_item": item,
            "for_each_index": index,
            "for_each_node_id": node_id,
        }
        iteration_metadata = {
            **message.metadata,
            "for_each_item": item,
            "for_each_index": index,
            "parent_node_id": node_id,
        }
        return AppletMessage(
            content=item,
            context=iteration_context,
            metadata=iteration_metadata,
        )

    async def _execute_single_iteration(
        self,
        item: Any,
        index: int,
        message: AppletMessage,
        node_id: str,
        run_id: str | None,
    ) -> dict[str, Any]:
        iteration_msg = self._build_iteration_message(item, index, message, node_id, run_id)

        downstream_nodes = self._get_downstream_nodes(message)

        if not downstream_nodes:
            return {"index": index, "item": item, "output": item}

        current_output: Any = item
        current_msg = iteration_msg

        for downstream in downstream_nodes:
            try:
                applet = await Orchestrator.load_applet(downstream["type"].lower())
                sub_metadata = {**current_msg.metadata}
                if "data" in downstream and isinstance(downstream["data"], dict):
                    sub_metadata["node_data"] = downstream["data"]
                sub_msg = AppletMessage(
                    content=current_msg.content,
                    context=current_msg.context,
                    metadata=sub_metadata,
                )
                response = await applet.on_message(sub_msg)
                current_output = response.content
                current_msg = response
            except Exception as exc:
                return {
                    "index": index,
                    "item": item,
                    "error": str(exc),
                    "failed_at_node": downstream.get("id", downstream.get("type")),
                }

        return {"index": index, "item": item, "output": current_output}

    def _get_downstream_nodes(self, message: AppletMessage) -> list[dict[str, Any]]:
        node_data = message.metadata.get("node_data", {})
        if not isinstance(node_data, dict):
            return []
        sub_nodes = node_data.get("sub_nodes", node_data.get("subNodes", []))
        if isinstance(sub_nodes, list):
            return [n for n in sub_nodes if isinstance(n, dict) and "type" in n]
        return []

    async def _run_sequential(
        self,
        items: list[Any],
        message: AppletMessage,
        node_id: str,
        run_id: str | None,
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for index, item in enumerate(items):
            result = await self._execute_single_iteration(item, index, message, node_id, run_id)
            results.append(result)
        return results

    async def _run_parallel(
        self,
        items: list[Any],
        message: AppletMessage,
        config: ForEachNodeConfigModel,
        node_id: str,
        run_id: str | None,
    ) -> list[dict[str, Any]]:
        semaphore = asyncio.Semaphore(config.concurrency_limit)

        async def _guarded(item: Any, index: int) -> dict[str, Any]:
            async with semaphore:
                return await self._execute_single_iteration(item, index, message, node_id, run_id)

        tasks = [_guarded(item, idx) for idx, item in enumerate(items)]
        return list(await asyncio.gather(*tasks))


# ============================================================
# Webhook Trigger Node Applet (N-19)
# ============================================================


class WebhookTriggerNodeApplet(BaseApplet):
    """Inbound webhook trigger — starts a workflow when a unique URL is POSTed.

    The applet itself is a passthrough: during normal flow execution it
    simply forwards its input context so the downstream nodes receive the
    webhook payload that was submitted via
    ``POST /api/v1/webhook-triggers/{id}/receive``.
    """

    VERSION = "1.0.0"
    CAPABILITIES = [
        "webhook-trigger",
        "hmac-sha256-verification",
        "flow-start",
    ]

    async def on_message(self, message: AppletMessage) -> AppletMessage:
        """Pass through — the trigger fires the flow from the HTTP endpoint."""
        return AppletMessage(
            content=message.content,
            context=message.context,
            metadata={
                **message.metadata,
                "applet": WEBHOOK_TRIGGER_NODE_TYPE,
                "status": "triggered",
            },
        )


applet_registry["llm"] = LLMNodeApplet
applet_registry[IMAGE_NODE_TYPE] = ImageGenNodeApplet
applet_registry[MEMORY_NODE_TYPE] = MemoryNodeApplet
applet_registry[HTTP_REQUEST_NODE_TYPE] = HTTPRequestNodeApplet
applet_registry[CODE_NODE_TYPE] = CodeNodeApplet
applet_registry[TRANSFORM_NODE_TYPE] = TransformNodeApplet
applet_registry[IF_ELSE_NODE_TYPE] = IfElseNodeApplet
applet_registry[BRANCH_NODE_TYPE] = BranchApplet
applet_registry[COMPOUND_MERGE_NODE_TYPE] = CompoundMergeApplet
applet_registry[MERGE_NODE_TYPE] = MergeNodeApplet
applet_registry[FOR_EACH_NODE_TYPE] = ForEachNodeApplet
applet_registry[WEBHOOK_TRIGGER_NODE_TYPE] = WebhookTriggerNodeApplet


# ---------------------------------------------------------------------------
# Scheduler Node — Cron-Triggered Workflow Scheduler
# ---------------------------------------------------------------------------

SCHEDULER_CREDENTIAL_FIELDS = frozenset(
    {
        "api_key",
        "bearer_token",
        "password",
        "secret",
        "token",
        "auth",
        "authorization",
        "private_key",
        "client_secret",
    }
)


def _compute_next_run(cron_expr: str, base: "datetime | None" = None) -> str:
    """Return ISO-8601 string of the next scheduled run time for a cron expression."""
    from datetime import datetime as _dt

    now = base or _dt.now(UTC)
    # Strip timezone for croniter (it works with naive datetimes internally)
    now_naive = now.replace(tzinfo=None)
    try:
        c = CronIter(cron_expr, now_naive)
        next_naive = c.get_next(_dt)
        return next_naive.isoformat()
    except (ValueError, KeyError) as exc:
        raise ValueError(f"Invalid cron expression '{cron_expr}': {exc}") from exc


class SchedulerRegistry:
    """In-memory store for workflow cron schedules (thread-safe)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._schedules: dict[str, dict[str, Any]] = {}

    def create(
        self,
        flow_id: str,
        cron_expr: str,
        name: str | None = None,
        enabled: bool = True,
    ) -> dict[str, Any]:
        """Validate cron expression and register a new schedule."""
        from datetime import datetime as _dt

        next_run = _compute_next_run(cron_expr)  # raises ValueError if invalid
        schedule_id = str(uuid.uuid4())
        entry: dict[str, Any] = {
            "id": schedule_id,
            "flow_id": flow_id,
            "cron_expr": cron_expr,
            "name": name or f"Schedule for {flow_id}",
            "enabled": enabled,
            "next_run": next_run,
            "last_run": None,
            "created_at": _dt.now(UTC).isoformat(),
            "run_count": 0,
        }
        with self._lock:
            self._schedules[schedule_id] = entry
        return dict(entry)

    def get(self, schedule_id: str) -> dict[str, Any] | None:
        with self._lock:
            entry = self._schedules.get(schedule_id)
            return dict(entry) if entry else None

    def list(self, flow_id: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            results = [dict(v) for v in self._schedules.values()]
        if flow_id:
            results = [r for r in results if r["flow_id"] == flow_id]
        return sorted(results, key=lambda s: s.get("created_at", ""), reverse=True)

    def update(self, schedule_id: str, **kwargs: Any) -> dict[str, Any] | None:
        """Partial update. Recomputes next_run if cron_expr changes."""
        with self._lock:
            entry = self._schedules.get(schedule_id)
            if entry is None:
                return None
            if "cron_expr" in kwargs:
                kwargs["next_run"] = _compute_next_run(kwargs["cron_expr"])
            entry.update(kwargs)
            return dict(entry)

    def delete(self, schedule_id: str) -> bool:
        with self._lock:
            return self._schedules.pop(schedule_id, None) is not None

    def get_due(self) -> "list[dict[str, Any]]":
        """Return enabled schedules whose next_run is in the past."""
        from datetime import datetime as _dt

        now_iso = _dt.now(UTC).replace(tzinfo=None).isoformat()
        with self._lock:
            due = [
                dict(v)
                for v in self._schedules.values()
                if v.get("enabled", True) and (v.get("next_run") or "") <= now_iso
            ]
        return due


scheduler_registry = SchedulerRegistry()


class SchedulerNodeApplet(BaseApplet):
    """Passthrough node — represents the scheduler trigger in a cron-driven flow.

    The flow is started externally by ``SchedulerService``; this applet simply
    forwards the message downstream so the rest of the pipeline can execute.
    """

    VERSION = "1.0.0"
    CAPABILITIES = ["scheduler-trigger", "cron-schedule", "flow-start"]

    async def on_message(self, message: AppletMessage) -> AppletMessage:
        return AppletMessage(
            content=message.content,
            context=message.context,
            metadata={
                **message.metadata,
                "applet": SCHEDULER_NODE_TYPE,
                "status": "triggered",
            },
        )


applet_registry[SCHEDULER_NODE_TYPE] = SchedulerNodeApplet


# ---------------------------------------------------------------------------
# Dead Letter Queue — Failed Run Store
# ---------------------------------------------------------------------------


class DeadLetterQueue:
    """In-memory store for failed workflow runs.

    Entries are added automatically when a run reaches "error" status.
    Consumers can list, inspect, and replay failed runs via the DLQ API.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: dict[str, dict[str, Any]] = {}

    def push(
        self,
        run_id: str,
        flow_id: str | None,
        flow_snapshot: dict[str, Any] | None,
        input_data: dict[str, Any],
        error: str,
        error_details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Add a failed run to the DLQ."""
        from datetime import datetime as _dt

        entry_id = str(uuid.uuid4())
        entry: dict[str, Any] = {
            "id": entry_id,
            "run_id": run_id,
            "flow_id": flow_id,
            "flow_snapshot": flow_snapshot,
            "input_data": input_data,
            "error": error,
            "error_details": error_details,
            "failed_at": _dt.now(UTC).isoformat(),
            "replay_count": 0,
        }
        with self._lock:
            self._entries[entry_id] = entry
        return dict(entry)

    def get(self, entry_id: str) -> dict[str, Any] | None:
        with self._lock:
            e = self._entries.get(entry_id)
            return dict(e) if e else None

    def list(self, flow_id: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            entries = [dict(v) for v in self._entries.values()]
        if flow_id:
            entries = [e for e in entries if e.get("flow_id") == flow_id]
        return sorted(entries, key=lambda e: e.get("failed_at", ""), reverse=True)

    def delete(self, entry_id: str) -> bool:
        with self._lock:
            return self._entries.pop(entry_id, None) is not None

    def increment_replay(self, entry_id: str) -> None:
        with self._lock:
            e = self._entries.get(entry_id)
            if e:
                e["replay_count"] = e.get("replay_count", 0) + 1

    def size(self) -> int:
        with self._lock:
            return len(self._entries)


dead_letter_queue = DeadLetterQueue()


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# SSEEventBus — real-time per-run event bus for SSE streaming (N-32)
# ---------------------------------------------------------------------------






# ---------------------------------------------------------------------------
# Execution Log Store — Structured per-node execution logs (D-108 / N-25)
# ---------------------------------------------------------------------------






# ---------------------------------------------------------------------------
# Workflow Variables + Environment Secrets — N-26
# ---------------------------------------------------------------------------








# ---------------------------------------------------------------------------
# Workflow Notifications — N-27
# ---------------------------------------------------------------------------






class NotificationService:
    """Dispatch workflow completion/failure notifications.

    Supports three adapter types:
      - ``email``   — SMTP (stdlib smtplib) or SendGrid HTTP
      - ``slack``   — POST to a Slack Incoming Webhook URL
      - ``webhook`` — POST to any custom HTTP endpoint

    All adapter errors are caught and logged — notifications must NEVER
    crash or block the workflow execution path.
    """

    async def dispatch(
        self,
        event: str,  # "on_complete" or "on_failure"
        flow_id: str,
        flow_name: str,
        run_id: str,
        status: str,
        duration_ms: float | None,
        output_preview: str,
    ) -> None:
        config = notification_store.get(flow_id)
        handlers = config.get(event, [])
        if not handlers:
            return
        summary = self._build_summary(flow_name, run_id, status, duration_ms, output_preview)
        for handler in handlers:
            if not isinstance(handler, dict):
                continue
            handler_type = str(handler.get("type", "")).lower()
            try:
                if handler_type == "email":
                    await self._send_email(handler, summary)
                elif handler_type == "slack":
                    await self._send_slack(handler, summary, status)
                elif handler_type == "webhook":
                    await self._send_webhook(handler, summary, status, run_id)
                else:
                    logger.warning("Unknown notification handler type: %s", handler_type)
            except Exception as exc:
                logger.error(
                    "Notification dispatch failed for handler type=%s flow=%s: %s",
                    handler_type,
                    flow_id,
                    exc,
                )

    def _build_summary(
        self,
        flow_name: str,
        run_id: str,
        status: str,
        duration_ms: float | None,
        output_preview: str,
    ) -> str:
        dur = f"{duration_ms:.0f}ms" if duration_ms is not None else "N/A"
        preview = str(output_preview)[:200] if output_preview else "(no output)"
        return (
            f"Workflow: {flow_name}\n"
            f"Run ID:   {run_id}\n"
            f"Status:   {status.upper()}\n"
            f"Duration: {dur}\n"
            f"Output:   {preview}"
        )

    async def _send_email(self, handler: dict[str, Any], summary: str) -> None:
        """Send notification via SMTP or SendGrid.

        Handler fields:
          - to (str | list[str]): recipient(s)
          - subject (str, optional): email subject
          - smtp_host (str, optional): SMTP server (default: app_config.smtp_host or localhost)
          - smtp_port (int, optional): SMTP port (default: 587)
          - smtp_user (str, optional): SMTP username
          - smtp_password (str, optional): SMTP password
          - sendgrid_api_key (str, optional): if set, use SendGrid HTTP API instead of SMTP
        """
        import smtplib
        from email.mime.text import MIMEText

        to = handler.get("to", "")
        if isinstance(to, str):
            recipients = [to] if to else []
        else:
            recipients = [r for r in to if r]
        if not recipients:
            logger.warning("Email notification: no recipients configured")
            return

        subject = handler.get("subject", "SynApps Workflow Notification")
        sendgrid_key = handler.get("sendgrid_api_key") or app_config.sendgrid_api_key

        if sendgrid_key:
            # Use SendGrid HTTP API
            payload = {
                "personalizations": [{"to": [{"email": r} for r in recipients]}],
                "from": {"email": handler.get("from_email", "notifications@synapps.local")},
                "subject": subject,
                "content": [{"type": "text/plain", "value": summary}],
            }
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    "https://api.sendgrid.com/v3/mail/send",
                    json=payload,
                    headers={"Authorization": f"Bearer {sendgrid_key}"},
                )
                if resp.status_code not in (200, 202):
                    logger.warning("SendGrid returned %s for flow notification", resp.status_code)
        else:
            # Use SMTP
            smtp_host = handler.get("smtp_host") or getattr(app_config, "smtp_host", "localhost")
            smtp_port = int(handler.get("smtp_port", getattr(app_config, "smtp_port", 587)))
            smtp_user = handler.get("smtp_user") or getattr(app_config, "smtp_user", "")
            smtp_password = handler.get("smtp_password") or getattr(app_config, "smtp_password", "")
            from_addr = handler.get("from_email", "notifications@synapps.local")

            msg = MIMEText(summary)
            msg["Subject"] = subject
            msg["From"] = from_addr
            msg["To"] = ", ".join(recipients)

            def _smtp_send() -> None:
                with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as s:
                    if smtp_user:
                        s.starttls()
                        s.login(smtp_user, smtp_password)
                    s.sendmail(from_addr, recipients, msg.as_string())

            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, _smtp_send)

    async def _send_slack(self, handler: dict[str, Any], summary: str, status: str) -> None:
        """POST formatted notification to a Slack Incoming Webhook.

        Handler fields:
          - webhook_url (str, required): Slack incoming webhook URL
          - channel (str, optional): channel override (e.g. #alerts)
        """
        webhook_url = handler.get("webhook_url", "")
        if not webhook_url:
            logger.warning("Slack notification: no webhook_url configured")
            return

        color = "#36a64f" if status == "success" else "#e01e5a"
        blocks = {
            "attachments": [
                {
                    "color": color,
                    "blocks": [
                        {
                            "type": "section",
                            "text": {"type": "mrkdwn", "text": f"```{summary}```"},
                        }
                    ],
                }
            ]
        }
        if handler.get("channel"):
            blocks["channel"] = handler["channel"]

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(webhook_url, json=blocks)
            if resp.status_code != 200:
                logger.warning("Slack webhook returned %s for flow notification", resp.status_code)

    async def _send_webhook(
        self, handler: dict[str, Any], summary: str, status: str, run_id: str
    ) -> None:
        """POST JSON payload to a custom webhook URL.

        Handler fields:
          - url (str, required): target URL
          - headers (dict, optional): additional request headers
        """
        url = handler.get("url", "")
        if not url:
            logger.warning("Webhook notification: no url configured")
            return
        headers = handler.get("headers", {}) or {}
        payload = {
            "event": "workflow_notification",
            "run_id": run_id,
            "status": status,
            "summary": summary,
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code >= 400:
                logger.warning(
                    "Webhook notification returned %s for run %s", resp.status_code, run_id
                )


notification_service = NotificationService()


# ---------------------------------------------------------------------------
# Node Comment Store (N-28)
# ---------------------------------------------------------------------------






# ---------------------------------------------------------------------------
# Activity Feed Store (N-28)
# ---------------------------------------------------------------------------






# ---------------------------------------------------------------------------
# Workflow Permission Store (N-29)
# ---------------------------------------------------------------------------

_PERMISSION_RANK: dict[str, int] = {"viewer": 1, "editor": 2, "owner": 3}
_VALID_SHARE_ROLES: frozenset[str] = frozenset({"viewer", "editor"})






# ---------------------------------------------------------------------------
# Audit Log Store (N-30)
# ---------------------------------------------------------------------------






# ---------------------------------------------------------------------------
# FlowTagStore — N-131 Flow Tags / Labels
# ---------------------------------------------------------------------------






# ---------------------------------------------------------------------------
# FlowFavoriteStore — N-133 Flow Favorites
# ---------------------------------------------------------------------------






# ---------------------------------------------------------------------------
# FlowPinStore — N-137 Flow Pinning
# ---------------------------------------------------------------------------






# ---------------------------------------------------------------------------
# FlowDescriptionStore — N-134 Flow Descriptions
# ---------------------------------------------------------------------------






# ---------------------------------------------------------------------------
# FlowArchiveStore — N-135 Flow Archiving
# ---------------------------------------------------------------------------






# ---------------------------------------------------------------------------
# FlowLabelStore — N-138 Flow Labels
# ---------------------------------------------------------------------------






# ---------------------------------------------------------------------------
# FlowShareStore — N-139 Flow Sharing Links
# ---------------------------------------------------------------------------






# ---------------------------------------------------------------------------
# FlowGroupStore — N-140 Flow Groups
# ---------------------------------------------------------------------------






# ---------------------------------------------------------------------------
# FlowAccessLogStore — N-142 Flow Access Log
# ---------------------------------------------------------------------------






# ---------------------------------------------------------------------------
# FlowWatchStore — N-144 Flow Watch
# ---------------------------------------------------------------------------






# ---------------------------------------------------------------------------
# FlowEditLockStore — N-145 Flow Edit Lock
# ---------------------------------------------------------------------------






# ---------------------------------------------------------------------------
# FlowMetadataStore — N-146 Flow Metadata
# ---------------------------------------------------------------------------






# ---------------------------------------------------------------------------
# FlowPriorityStore — N-147 Flow Priority
# ---------------------------------------------------------------------------

FLOW_PRIORITY_VALUES = ("critical", "high", "medium", "low")






# ---------------------------------------------------------------------------
# FlowExpiryStore — N-149 Flow Expiry
# ---------------------------------------------------------------------------






# ---------------------------------------------------------------------------
# FlowAliasStore — N-150 Flow Aliases
# ---------------------------------------------------------------------------






# ---------------------------------------------------------------------------
# FlowRateLimitStore — N-151 Flow Rate Limiting
# ---------------------------------------------------------------------------






# ---------------------------------------------------------------------------
# FlowChangelogStore — N-152 Flow Changelog
# ---------------------------------------------------------------------------

_CHANGELOG_ENTRY_TYPES = frozenset({"note", "fix", "improvement", "breaking", "deployment"})






# ---------------------------------------------------------------------------
# FlowRunPresetStore — N-153 Flow Run Presets
# ---------------------------------------------------------------------------






# ---------------------------------------------------------------------------
# FlowAnnotationStore — N-154 Flow Annotations
# ---------------------------------------------------------------------------






# ---------------------------------------------------------------------------
# FlowDependencyStore — N-155 Flow Dependencies
# ---------------------------------------------------------------------------






# ---------------------------------------------------------------------------
# FlowBookmarkStore — N-156 Flow Bookmarks
# ---------------------------------------------------------------------------






# ---------------------------------------------------------------------------
# FlowSnapshotStore — N-157 Flow Snapshots
# ---------------------------------------------------------------------------






# ---------------------------------------------------------------------------
# FlowReactionStore — N-158 Flow Reactions
# ---------------------------------------------------------------------------

_ALLOWED_REACTIONS: frozenset[str] = frozenset(
    ["👍", "👎", "❤️", "🔥", "🎉", "🚀", "⚠️", "✅", "❌", "🤔"]
)






# ---------------------------------------------------------------------------
# FlowScheduleStore — N-159 Flow Scheduled Runs
# ---------------------------------------------------------------------------

_CRON_FIELD = r"(\*(?:/[0-9]+)?|[0-9,\-/]+)"
_CRON_PATTERN = re.compile(
    rf"^{_CRON_FIELD}\s+{_CRON_FIELD}\s+{_CRON_FIELD}\s+{_CRON_FIELD}\s+{_CRON_FIELD}$"
)






# ---------------------------------------------------------------------------
# FlowWebhookStore — N-160 Flow Outbound Webhooks
# ---------------------------------------------------------------------------

_WEBHOOK_EVENTS: frozenset[str] = frozenset(
    ["run.started", "run.completed", "run.failed", "flow.updated", "flow.deleted"]
)
_URL_PATTERN = re.compile(r"^https?://\S+$")






# ---------------------------------------------------------------------------
# FlowCustomFieldStore — N-161 Flow Custom Fields
# ---------------------------------------------------------------------------

_CUSTOM_FIELD_TYPES: frozenset[str] = frozenset(["string", "number", "boolean", "date"])






# ---------------------------------------------------------------------------
# FlowCollaboratorStore — N-162 Flow Collaborators
# ---------------------------------------------------------------------------

_COLLABORATOR_ROLES: frozenset[str] = frozenset(["owner", "editor", "viewer", "commenter"])






# ---------------------------------------------------------------------------
# FlowEnvironmentStore — N-163 Flow Environments
# ---------------------------------------------------------------------------

_ENV_NAMES: frozenset[str] = frozenset(["development", "staging", "production"])






# ---------------------------------------------------------------------------
# FlowNotifPrefStore — N-164 Flow Notification Preferences
# ---------------------------------------------------------------------------

_NOTIF_EVENTS: frozenset[str] = frozenset(
    ["run.completed", "run.failed", "flow.updated", "flow.deleted", "collaborator.added"]
)
_NOTIF_CHANNELS: frozenset[str] = frozenset(["email", "slack", "in_app"])






# ---------------------------------------------------------------------------
# FlowTimeoutStore — N-165 Flow Timeout Config
# ---------------------------------------------------------------------------

_TIMEOUT_MIN = 1
_TIMEOUT_MAX = 3600






# ---------------------------------------------------------------------------
# FlowRetryPolicyStore — N-166 Flow Retry Policy
# ---------------------------------------------------------------------------

_RETRY_MAX_RETRIES_MAX = 10
_RETRY_DELAY_MAX = 300  # seconds
_RETRY_BACKOFF_MAX = 10.0






# ---------------------------------------------------------------------------
# FlowConcurrencyStore — N-167 Flow Concurrency Limit
# ---------------------------------------------------------------------------

_CONCURRENCY_MIN = 1
_CONCURRENCY_MAX = 100






# ---------------------------------------------------------------------------
# FlowInputSchemaStore — N-168 Flow Input Schema
# ---------------------------------------------------------------------------

_INPUT_SCHEMA_MAX_BYTES = 16_384  # 16 KB






# ---------------------------------------------------------------------------
# FlowOutputSchemaStore — N-169 Flow Output Schema
# ---------------------------------------------------------------------------

_OUTPUT_SCHEMA_MAX_BYTES = 16_384






# ---------------------------------------------------------------------------
# FlowContactStore — N-170 Flow Contact Info
# ---------------------------------------------------------------------------






# ---------------------------------------------------------------------------
# FlowCostConfigStore — N-171 Flow Cost Estimate Config
# ---------------------------------------------------------------------------

_COST_CURRENCIES: frozenset[str] = frozenset(["USD", "EUR", "GBP", "JPY", "AUD", "CAD"])






# ---------------------------------------------------------------------------
# FlowVisibilityStore — N-172 Flow Visibility
# ---------------------------------------------------------------------------

_VISIBILITY_LEVELS: frozenset[str] = frozenset(["private", "internal", "public"])






# ---------------------------------------------------------------------------
# FlowVersionLockStore — N-173 Flow Version Lock
# ---------------------------------------------------------------------------






# ---------------------------------------------------------------------------
# FlowApprovalStore — N-174 Flow Approval Workflow
# ---------------------------------------------------------------------------

_APPROVAL_STATUSES: frozenset[str] = frozenset(["pending", "approved", "rejected"])







# ---------------------------------------------------------------------------
# FlowTriggerConfigStore — N-175 Flow Trigger Configuration
# ---------------------------------------------------------------------------

_TRIGGER_TYPES: frozenset[str] = frozenset(["manual", "webhook", "schedule", "event", "api"])






# ---------------------------------------------------------------------------
# FlowRunRetentionStore — N-176 Flow Run History Retention
# ---------------------------------------------------------------------------






# ---------------------------------------------------------------------------
# FlowErrorAlertStore — N-177 Flow Error Alert Recipients
# ---------------------------------------------------------------------------






# ---------------------------------------------------------------------------
# FlowOutputDestinationStore — N-178 Flow Output Destination
# ---------------------------------------------------------------------------

_OUTPUT_DEST_TYPES: frozenset[str] = frozenset(["webhook", "s3", "database", "file", "none"])






# ---------------------------------------------------------------------------
# FlowResourceLimitStore — N-179 Flow Resource Limits
# ---------------------------------------------------------------------------






# ---------------------------------------------------------------------------
# FlowAclStore — N-180 Flow Access Control List
# ---------------------------------------------------------------------------

_ACL_PERMISSIONS: frozenset[str] = frozenset(["read", "write", "execute", "admin"])






# ---------------------------------------------------------------------------
# FlowExecutionModeStore — N-181 Flow Execution Mode
# ---------------------------------------------------------------------------

_EXECUTION_MODES: frozenset[str] = frozenset(["async", "sync", "dry_run"])






# ---------------------------------------------------------------------------
# FlowInputValidationStore — N-182 Flow Input Validation Rules
# ---------------------------------------------------------------------------






# ---------------------------------------------------------------------------
# FlowCachingConfigStore — N-183 Flow Caching Configuration
# ---------------------------------------------------------------------------






# ---------------------------------------------------------------------------
# FlowCircuitBreakerStore — N-184 Flow Circuit Breaker Config
# ---------------------------------------------------------------------------

_CB_STATES: frozenset[str] = frozenset(["closed", "open", "half_open"])






# ---------------------------------------------------------------------------
# FlowObservabilityConfigStore — N-185 Flow Observability Configuration
# ---------------------------------------------------------------------------






# ---------------------------------------------------------------------------
# FlowMaintenanceWindowStore — N-186 Flow Maintenance Window
# ---------------------------------------------------------------------------






# ---------------------------------------------------------------------------
# FlowGeoRestrictionStore — N-187 Flow Geographic Restrictions
# ---------------------------------------------------------------------------

_GEO_MODES: frozenset[str] = frozenset(["allowlist", "blocklist", "none"])






# ---------------------------------------------------------------------------
# FlowIpAllowlistStore — N-188 Flow IP Allowlist
# ---------------------------------------------------------------------------





# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# FlowDataClassificationStore — N-189 Flow Data Classification
# ---------------------------------------------------------------------------

_DATA_CLASSIFICATION_LEVELS: frozenset[str] = frozenset(
    ["public", "internal", "confidential", "restricted"]
)







# ---------------------------------------------------------------------------
# FlowNotificationChannelStore — N-190 Flow Notification Channels
# ---------------------------------------------------------------------------

_NOTIF_CHANNEL_TYPES: frozenset[str] = frozenset(["email", "slack", "webhook", "pagerduty"])
_NOTIF_CHANNEL_EVENTS: frozenset[str] = frozenset(
    ["run.started", "run.completed", "run.failed", "run.cancelled"]
)







# ---------------------------------------------------------------------------
# FlowFeatureFlagStore — N-191 Flow Feature Flags
# ---------------------------------------------------------------------------






# ---------------------------------------------------------------------------
# FlowExecutionHookStore — N-192 Flow Execution Hooks
# ---------------------------------------------------------------------------






# ---------------------------------------------------------------------------
# FlowCustomDomainStore — N-193 Flow Custom Domain
# ---------------------------------------------------------------------------






# ---------------------------------------------------------------------------
# FlowWebhookSigningStore — N-194 Flow Webhook Signing
# ---------------------------------------------------------------------------






# ---------------------------------------------------------------------------
# FlowAuditExportStore — N-195 Flow Audit Export
# ---------------------------------------------------------------------------






# ---------------------------------------------------------------------------
# FlowCollaboratorRoleStore — N-196 Flow Collaborator Roles
# ---------------------------------------------------------------------------






# ---------------------------------------------------------------------------
# FlowInputMaskStore — N-197 Flow Input Mask
# ---------------------------------------------------------------------------






# ---------------------------------------------------------------------------
# FlowOutputTransformStore — N-198 Flow Output Transform
# ---------------------------------------------------------------------------






# FlowDataRetentionStore — N-199 Flow Data Retention Policy
# ---------------------------------------------------------------------------






# FlowAllowedOriginsStore — N-200 Flow Allowed Origins
# ---------------------------------------------------------------------------






# WorkflowImportService — N-31 Import from External Tools
# ---------------------------------------------------------------------------


class WorkflowImportService:
    """Convert n8n or Zapier workflow JSON to SynApps format.

    Auto-detects the source format from payload structure, then maps
    node types and connectivity to SynApps equivalents.  Unknown node
    types fall back to ``transform``.
    """

    # ---- n8n → SynApps node-type mapping ----
    _N8N_TYPE_MAP: dict[str, str] = {
        "n8n-nodes-base.start": "start",
        "n8n-nodes-base.manualTrigger": "start",
        "n8n-nodes-base.webhook": "start",
        "n8n-nodes-base.scheduleTrigger": "start",
        "n8n-nodes-base.httpRequest": "http",
        "n8n-nodes-base.code": "code",
        "n8n-nodes-base.function": "code",
        "n8n-nodes-base.functionItem": "code",
        "n8n-nodes-base.if": "if_else",
        "n8n-nodes-base.switch": "if_else",
        "n8n-nodes-base.merge": "merge",
        "n8n-nodes-base.splitInBatches": "for_each",
        "n8n-nodes-base.itemLists": "for_each",
        "n8n-nodes-base.set": "transform",
        "n8n-nodes-base.noOp": "transform",
        # LLM / AI nodes
        "n8n-nodes-base.openAi": "llm",
        "@n8n/n8n-nodes-langchain.openAi": "llm",
        "@n8n/n8n-nodes-langchain.lmOpenAi": "llm",
        "@n8n/n8n-nodes-langchain.agent": "llm",
        "@n8n/n8n-nodes-langchain.chainLlm": "llm",
    }

    # ---- Zapier action-type → SynApps node-type mapping ----
    _ZAPIER_TYPE_MAP: dict[str, str] = {
        "trigger": "start",
        "webhook_trigger": "start",
        "schedule_trigger": "start",
        "action": "transform",
        "http_action": "http",
        "webhook_action": "http",
        "code_action": "code",
        "filter": "if_else",
        "conditional": "if_else",
        "delay": "transform",
        "formatter": "transform",
        "ai_action": "llm",
        "openai_action": "llm",
        "loop": "for_each",
        "sub_zap": "for_each",
    }

    # ---- Format detection ----

    @staticmethod
    def detect_format(data: dict[str, Any]) -> str:
        """Return 'n8n', 'zapier', or 'unknown'."""
        if "nodes" in data and "connections" in data:
            nodes = data.get("nodes", [])
            if nodes and isinstance(nodes[0], dict) and "type" in nodes[0]:
                n8n_type: str = nodes[0]["type"]
                if "n8n" in n8n_type or "." in n8n_type:
                    return "n8n"
        if "steps" in data or "zap" in data or "trigger" in data:
            return "zapier"
        # Fallback heuristics
        if "connections" in data:
            return "n8n"
        return "unknown"

    # ---- n8n conversion ----

    @classmethod
    def from_n8n(cls, data: dict[str, Any]) -> dict[str, Any]:
        """Convert an n8n workflow export to SynApps format."""
        flow_id = str(uuid.uuid4())
        name: str = data.get("name", "Imported n8n Workflow")
        raw_nodes: list[dict[str, Any]] = data.get("nodes", [])
        connections: dict[str, Any] = data.get("connections", {})

        # Build name→id mapping (n8n uses node names as connection keys)
        name_to_id: dict[str, str] = {}
        synapps_nodes: list[dict[str, Any]] = []

        for i, raw in enumerate(raw_nodes):
            node_id = f"n8n-{i}"
            name_to_id[raw.get("name", node_id)] = node_id
            n8n_type: str = raw.get("type", "")
            snap_type = cls._N8N_TYPE_MAP.get(n8n_type, "transform")
            pos = raw.get("position", [i * 200, 0])
            params: dict[str, Any] = raw.get("parameters", {})
            node_data: dict[str, Any] = {"label": raw.get("name", snap_type)}
            # Map common parameters
            if snap_type == "http":
                node_data["url"] = params.get("url", "")
                node_data["method"] = params.get("method", "GET")
            elif snap_type == "code":
                node_data["code"] = params.get("jsCode", params.get("functionCode", ""))
            elif snap_type == "llm":
                node_data["prompt"] = params.get("prompt", params.get("text", ""))
                node_data["model"] = params.get("model", "gpt-4o-mini")
            elif snap_type == "if_else":
                node_data["condition"] = params.get("conditions", {})
            synapps_nodes.append(
                {
                    "id": node_id,
                    "type": snap_type,
                    "position": {
                        "x": pos[0] if isinstance(pos, list) else 0,
                        "y": pos[1] if isinstance(pos, list) else 0,
                    },
                    "data": node_data,
                }
            )

        # Ensure start and end nodes exist
        has_start = any(n["type"] == "start" for n in synapps_nodes)
        has_end = any(n["type"] == "end" for n in synapps_nodes)
        if not has_start:
            synapps_nodes.insert(
                0,
                {"id": "imported-start", "type": "start", "position": {"x": 0, "y": 0}, "data": {}},
            )
            name_to_id["__start__"] = "imported-start"
        if not has_end:
            last_x = max((n["position"]["x"] for n in synapps_nodes), default=0) + 200
            synapps_nodes.append(
                {"id": "imported-end", "type": "end", "position": {"x": last_x, "y": 0}, "data": {}}
            )

        # Build edges from n8n connections dict
        edges: list[dict[str, Any]] = []
        edge_counter = 0
        for src_name, output_groups in connections.items():
            src_id = name_to_id.get(src_name)
            if not src_id:
                continue
            main_outputs = output_groups.get("main", [])
            for output_list in main_outputs:
                if not isinstance(output_list, list):
                    continue
                for conn in output_list:
                    tgt_name = conn.get("node", "")
                    tgt_id = name_to_id.get(tgt_name)
                    if tgt_id:
                        edges.append(
                            {
                                "id": f"e{edge_counter}",
                                "source": src_id,
                                "target": tgt_id,
                            }
                        )
                        edge_counter += 1

        return {"id": flow_id, "name": name, "nodes": synapps_nodes, "edges": edges}

    # ---- Zapier conversion ----

    @classmethod
    def from_zapier(cls, data: dict[str, Any]) -> dict[str, Any]:
        """Convert a Zapier zap export to SynApps format.

        Expected Zapier structure::

            {
              "title": "My Zap",
              "steps": [
                {"id": "1", "type": "trigger", "app": "Gmail", "action": "New Email", "params": {}},
                {"id": "2", "type": "action", "app": "Slack", "action": "Send Message", "params": {}}
              ]
            }
        """
        flow_id = str(uuid.uuid4())
        name: str = data.get(
            "title", data.get("name", data.get("zap", {}).get("title", "Imported Zapier Workflow"))
        )
        # Support both flat steps and nested zap.steps
        steps: list[dict[str, Any]] = data.get("steps", data.get("zap", {}).get("steps", []))

        synapps_nodes: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []

        for i, step in enumerate(steps):
            raw_type: str = step.get("type", "action").lower()
            snap_type = cls._ZAPIER_TYPE_MAP.get(raw_type, "transform")
            step_id = str(step.get("id", f"zapier-{i}"))
            params: dict[str, Any] = step.get("params", step.get("config", {}))
            node_data: dict[str, Any] = {
                "label": f"{step.get('app', '')} — {step.get('action', step.get('event', ''))}".strip(
                    " —"
                ),
            }
            if snap_type == "http":
                node_data["url"] = params.get("url", "")
                node_data["method"] = params.get("method", "POST")
            elif snap_type == "code":
                node_data["code"] = params.get("code", "")
            elif snap_type == "llm":
                node_data["prompt"] = params.get("prompt", params.get("input", ""))
                node_data["model"] = params.get("model", "gpt-4o-mini")
            synapps_nodes.append(
                {
                    "id": step_id,
                    "type": snap_type,
                    "position": {"x": i * 200, "y": 0},
                    "data": node_data,
                }
            )
            if i > 0:
                prev_id = str(steps[i - 1].get("id", f"zapier-{i - 1}"))
                edges.append({"id": f"e{i - 1}", "source": prev_id, "target": step_id})

        # Ensure start and end
        if not synapps_nodes or synapps_nodes[0]["type"] != "start":
            synapps_nodes.insert(
                0,
                {
                    "id": "imported-start",
                    "type": "start",
                    "position": {"x": -200, "y": 0},
                    "data": {},
                },
            )
            if steps:
                edges.insert(
                    0,
                    {
                        "id": "e-start",
                        "source": "imported-start",
                        "target": str(steps[0].get("id", "zapier-0")),
                    },
                )
        if not synapps_nodes or synapps_nodes[-1]["type"] != "end":
            last_x = len(steps) * 200
            synapps_nodes.append(
                {"id": "imported-end", "type": "end", "position": {"x": last_x, "y": 0}, "data": {}}
            )
            if steps:
                last_step_id = str(steps[-1].get("id", f"zapier-{len(steps) - 1}"))
                edges.append({"id": "e-end", "source": last_step_id, "target": "imported-end"})

        return {"id": flow_id, "name": name, "nodes": synapps_nodes, "edges": edges}

    # ---- Auto-dispatch ----

    @classmethod
    def convert(cls, data: dict[str, Any], fmt: str | None = None) -> tuple[dict[str, Any], str]:
        """Convert *data* to SynApps format; return (workflow, detected_format)."""
        if fmt is None:
            fmt = cls.detect_format(data)
        if fmt == "n8n":
            return cls.from_n8n(data), "n8n"
        if fmt == "zapier":
            return cls.from_zapier(data), "zapier"
        raise HTTPException(
            status_code=422,
            detail=f"Unrecognised import format: {fmt!r}. Supported: 'n8n', 'zapier'.",
        )


def _check_flow_permission(flow_id: str, user_id: str, required: str) -> None:
    """Raise HTTP 403 if user lacks the required role.

    If no permissions are set for the flow (open-access / legacy), always passes.
    Roles in ascending order: viewer < editor < owner.
    """
    if not workflow_permission_store.has_flow(flow_id):
        return  # open access — backwards compatible
    role = workflow_permission_store.get_role(flow_id, user_id)
    if role is None:
        raise HTTPException(
            status_code=403,
            detail="Access denied: you are not a member of this workflow.",
        )
    if _PERMISSION_RANK.get(role, 0) < _PERMISSION_RANK.get(required, 0):
        raise HTTPException(
            status_code=403,
            detail=f"Access denied: '{required}' role required, you have '{role}'.",
        )


def _resolve_template(value: Any, variables: dict[str, Any], secrets: dict[str, str]) -> Any:
    """Resolve ``{{var.name}}`` and ``{{secret.name}}`` placeholders in a value.

    Recursively processes strings, lists, and dicts. Non-string scalars are
    returned unchanged.
    """
    if isinstance(value, str):
        import re

        def _replacer(match: re.Match) -> str:
            namespace, name = match.group(1).strip(), match.group(2).strip()
            if namespace == "var":
                return str(variables.get(name, match.group(0)))
            if namespace == "secret":
                return str(secrets.get(name, match.group(0)))
            return match.group(0)

        return re.sub(r"\{\{(var|secret)\.([^}]+)\}\}", _replacer, value)
    if isinstance(value, dict):
        return {k: _resolve_template(v, variables, secrets) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve_template(item, variables, secrets) for item in value]
    return value


def _resolve_node_data(
    node_data: dict[str, Any], variables: dict[str, Any], secrets: dict[str, str]
) -> dict[str, Any]:
    """Apply template resolution to all node data fields."""
    return {k: _resolve_template(v, variables, secrets) for k, v in node_data.items()}


def _mask_secrets(value: Any, secret_values: set[str]) -> Any:
    """Replace raw secret values with ``***`` in log entry fields."""
    if not secret_values:
        return value
    if isinstance(value, str):
        result = value
        for sv in secret_values:
            if sv and sv in result:
                result = result.replace(sv, "***")
        return result
    if isinstance(value, dict):
        return {k: _mask_secrets(v, secret_values) for k, v in value.items()}
    if isinstance(value, list):
        return [_mask_secrets(item, secret_values) for item in value]
    return value


# ---------------------------------------------------------------------------
# Flow Version Registry — Snapshot history for workflow rollback
# ---------------------------------------------------------------------------


def _diff_flow_snapshots(snapshot_a: dict[str, Any], snapshot_b: dict[str, Any]) -> dict[str, Any]:
    """Return a structural diff between two flow snapshots.

    Compares nodes and edges:
    - ``nodes_added``: node IDs present in B but not A
    - ``nodes_removed``: node IDs present in A but not B
    - ``nodes_changed``: node IDs where type or data differ
    - ``edges_added``: edge source→target pairs in B but not A
    - ``edges_removed``: edge source→target pairs in A but not B
    """

    def _node_map(snapshot: dict) -> dict[str, dict]:
        return {n["id"]: n for n in snapshot.get("nodes", []) if isinstance(n, dict) and "id" in n}

    def _edge_key(edge: dict) -> str:
        return f"{edge.get('source', '')}→{edge.get('target', '')}"

    def _edge_set(snapshot: dict) -> set[str]:
        return {_edge_key(e) for e in snapshot.get("edges", []) if isinstance(e, dict)}

    nodes_a = _node_map(snapshot_a)
    nodes_b = _node_map(snapshot_b)
    ids_a = set(nodes_a)
    ids_b = set(nodes_b)

    nodes_added = sorted(ids_b - ids_a)
    nodes_removed = sorted(ids_a - ids_b)
    nodes_changed = []
    for nid in ids_a & ids_b:
        na, nb = nodes_a[nid], nodes_b[nid]
        if na.get("type") != nb.get("type") or na.get("data") != nb.get("data"):
            nodes_changed.append(nid)

    edges_a = _edge_set(snapshot_a)
    edges_b = _edge_set(snapshot_b)

    return {
        "nodes_added": nodes_added,
        "nodes_removed": nodes_removed,
        "nodes_changed": sorted(nodes_changed),
        "edges_added": sorted(edges_b - edges_a),
        "edges_removed": sorted(edges_a - edges_b),
        "summary": {
            "nodes_added": len(nodes_added),
            "nodes_removed": len(nodes_removed),
            "nodes_changed": len(nodes_changed),
            "edges_added": len(edges_b - edges_a),
            "edges_removed": len(edges_a - edges_b),
        },
    }


class FlowVersionRegistry:
    """In-memory version history for flows.

    Each time a flow is updated via PUT, the pre-update snapshot is stored here.
    Consumers can list, retrieve, diff, and roll back to any prior version.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # flow_id -> list[version_dict] (chronological, index 0 = oldest)
        self._versions: dict[str, list[dict[str, Any]]] = {}

    def snapshot(self, flow_id: str, flow_data: dict[str, Any]) -> dict[str, Any]:
        """Snapshot the current state of a flow before it is overwritten."""
        from datetime import datetime as _dt  # noqa: PLC0415

        version_id = str(uuid.uuid4())
        with self._lock:
            versions = self._versions.setdefault(flow_id, [])
            seq = len(versions) + 1
            entry: dict[str, Any] = {
                "version_id": version_id,
                "flow_id": flow_id,
                "version": seq,
                "snapshot": dict(flow_data),
                "snapshotted_at": _dt.now(UTC).isoformat(),
            }
            versions.append(entry)
        return dict(entry)

    def list_versions(self, flow_id: str) -> list[dict[str, Any]]:
        """Return version history newest-first (snapshots only, no full data)."""
        with self._lock:
            versions = self._versions.get(flow_id, [])
            # Return summary without full snapshot data for list endpoint
            return [
                {
                    "version_id": v["version_id"],
                    "flow_id": v["flow_id"],
                    "version": v["version"],
                    "snapshotted_at": v["snapshotted_at"],
                }
                for v in reversed(versions)
            ]

    def get_version(self, flow_id: str, version_id: str) -> dict[str, Any] | None:
        """Retrieve a full snapshot by version_id."""
        with self._lock:
            for v in self._versions.get(flow_id, []):
                if v["version_id"] == version_id:
                    return dict(v)
        return None

    def get_latest(self, flow_id: str) -> dict[str, Any] | None:
        """Return the most recent snapshot for a flow."""
        with self._lock:
            versions = self._versions.get(flow_id, [])
            return dict(versions[-1]) if versions else None

    def diff(self, flow_id: str, version_id_a: str, version_id_b: str) -> dict[str, Any] | None:
        """Compute node/edge diff between two versions.

        Returns ``None`` if either version is not found.
        """
        va = self.get_version(flow_id, version_id_a)
        vb = self.get_version(flow_id, version_id_b)
        if va is None or vb is None:
            return None
        return _diff_flow_snapshots(va["snapshot"], vb["snapshot"])


flow_version_registry = FlowVersionRegistry()


# ---------------------------------------------------------------------------
# Rollback Audit Store — tracks all workflow version rollbacks
# ---------------------------------------------------------------------------






class RollbackRequest(BaseModel):
    """Request body for the rollback endpoint -- optional reason text."""

    reason: str = Field("", max_length=500)


# ---------------------------------------------------------------------------
# Error Handler Node — Graph-level error catcher
# ---------------------------------------------------------------------------


class ErrorHandlerNodeApplet(BaseApplet):
    """Error handler node — catches failures from upstream nodes and emits
    a clean, structured error response so the pipeline can continue.

    Configuration keys in ``node.data``:
    - ``fallback_content`` (any): output to emit when an error is received.
      Defaults to the error message string.
    - ``suppress_error`` (bool): if ``True``, emits ``fallback_content`` and
      continues; if ``False`` (default), emits an error-status response which
      will still cause downstream nodes to see the error context.
    """

    VERSION = "1.0.0"
    CAPABILITIES = ["error-handling", "fallback-routing", "pipeline-recovery"]

    async def on_message(self, message: AppletMessage) -> AppletMessage:
        node_data = (
            message.metadata.get("node_data", {}) if isinstance(message.metadata, dict) else {}
        )
        fallback_content = node_data.get("fallback_content", message.content)
        suppress = bool(node_data.get("suppress_error", False))

        error_info = (
            message.metadata.get("error_info") if isinstance(message.metadata, dict) else None
        )
        return AppletMessage(
            content=fallback_content if suppress else message.content,
            context=message.context,
            metadata={
                **message.metadata,
                "applet": ERROR_HANDLER_NODE_TYPE,
                "status": "handled" if suppress else "error_forwarded",
                "original_error": error_info,
            },
        )


applet_registry[ERROR_HANDLER_NODE_TYPE] = ErrorHandlerNodeApplet

# ============================================================
# Subflow — Reusable Workflow Components (N-38)
# ============================================================

SUBFLOW_NODE_TYPE = "subflow"






class SubflowApplet(BaseApplet):
    """Execute one workflow inline as a node within another workflow.

    Node data schema:
        workflow_id      : str  — ID of the target workflow to execute
        input_mapping    : dict — maps param names to template expressions
        output_key       : str  — key under which subflow output is returned
        timeout_seconds  : int  — execution timeout (default 30)
        max_depth        : int  — max recursion depth (default 3)
    """

    VERSION = "1.0.0"
    CAPABILITIES = ["subflow", "reusable-component", "nested-execution"]

    async def on_message(self, message: AppletMessage) -> AppletMessage:
        """Execute the target workflow inline and return its output."""
        node_data = message.metadata.get("node_data", {})
        if not isinstance(node_data, dict):
            node_data = {}

        workflow_id: str | None = node_data.get("workflow_id")
        if not workflow_id:
            raise ValueError("SubflowApplet requires 'workflow_id' in node data")

        input_mapping: dict[str, Any] = node_data.get("input_mapping") or {}
        if not isinstance(input_mapping, dict):
            input_mapping = {}

        output_key: str = node_data.get("output_key") or "subflow_result"
        timeout_seconds: float = float(node_data.get("timeout_seconds", 30))
        max_depth: int = int(node_data.get("max_depth", 3))

        context = message.context if isinstance(message.context, dict) else {}
        current_depth: int = int(context.get("_subflow_depth", 0))
        if current_depth >= max_depth:
            raise ValueError(
                f"Maximum subflow depth {max_depth} exceeded (current depth: {current_depth})"
            )

        parent_run_id: str = context.get("run_id", "unknown")

        # Resolve input_mapping values using template substitution
        template_data: dict[str, Any] = {
            "input": message.content,
            "context": context,
            "results": context.get("results", {}),
        }
        # Also expose top-level input fields for {{field}} convenience
        if isinstance(message.content, dict):
            template_data.update(message.content)

        resolved_inputs: dict[str, Any] = {}
        for param, template_expr in input_mapping.items():
            resolved_inputs[param] = _render_template_payload(template_expr, template_data)

        # Fetch the target workflow
        flow = await FlowRepository.get_by_id(workflow_id)
        if flow is None:
            raise ValueError(f"Subflow workflow '{workflow_id}' not found")

        # Register execution to catch circular references
        subflow_registry.enter(parent_run_id, workflow_id)
        try:
            sub_context: dict[str, Any] = {
                "_subflow_depth": current_depth + 1,
                "_parent_run_id": parent_run_id,
            }
            sub_output = await asyncio.wait_for(
                SubflowApplet._execute_inline(flow, resolved_inputs, sub_context),
                timeout=timeout_seconds,
            )
        finally:
            subflow_registry.exit(parent_run_id, workflow_id)

        result_content: dict[str, Any] = {
            output_key: sub_output,
            "_subflow_id": workflow_id,
        }
        output_context = {
            **context,
            "last_subflow_result": sub_output,
            "_subflow_id": workflow_id,
        }
        return AppletMessage(
            content=result_content,
            context=output_context,
            metadata={
                "applet": SUBFLOW_NODE_TYPE,
                "status": "success",
                "subflow_id": workflow_id,
                "output_key": output_key,
            },
        )

    @staticmethod
    async def _execute_inline(
        flow: dict[str, Any],
        input_data: dict[str, Any],
        sub_context: dict[str, Any],
    ) -> Any:
        """Execute a flow's nodes in dependency order and return the final output.

        This is a simplified BFS execution that runs the nodes inline (no
        background task, no status broadcasting) so the parent workflow can
        await the result directly.
        """
        flow_nodes: list[dict[str, Any]] = flow.get("nodes", [])
        flow_edges: list[dict[str, Any]] = flow.get("edges", [])

        nodes_by_id: dict[str, dict[str, Any]] = {
            node["id"]: node
            for node in flow_nodes
            if isinstance(node, dict) and isinstance(node.get("id"), str)
        }
        edges_by_source: dict[str, list[dict[str, Any]]] = {}
        for edge in flow_edges:
            if not isinstance(edge, dict):
                continue
            source = edge.get("source")
            if isinstance(source, str) and source:
                edges_by_source.setdefault(source, []).append(edge)

        target_nodes = {
            edge.get("target")
            for edge in flow_edges
            if isinstance(edge, dict) and isinstance(edge.get("target"), str)
        }
        start_nodes = [
            node["id"]
            for node in flow_nodes
            if isinstance(node, dict)
            and isinstance(node.get("id"), str)
            and node["id"] not in target_nodes
        ]
        if not start_nodes:
            raise ValueError("Subflow has no start node")

        # BFS traversal; carry context and last_output between nodes
        context: dict[str, Any] = {
            "input": input_data,
            "results": {},
            **sub_context,
        }
        current_nodes = list(start_nodes)
        visited: set[str] = set()
        last_output: Any = input_data

        while current_nodes:
            next_nodes: list[str] = []
            for node_id in current_nodes:
                if node_id in visited:
                    continue
                visited.add(node_id)

                node = nodes_by_id.get(node_id)
                if not isinstance(node, dict):
                    continue

                node_type = str(node.get("type", "")).strip().lower()
                outgoing_edges = edges_by_source.get(node_id, [])

                if node_type in ("start", "end"):
                    last_output = context.get("input", input_data)
                    context["results"][node_id] = {
                        "type": node_type,
                        "output": last_output,
                        "status": "success",
                    }
                    for edge in outgoing_edges:
                        target = edge.get("target")
                        if isinstance(target, str) and target and target not in next_nodes:
                            next_nodes.append(target)
                    continue

                node_data = node.get("data", {})
                if not isinstance(node_data, dict):
                    node_data = {}

                applet = await Orchestrator.load_applet(node_type)
                msg = AppletMessage(
                    content=last_output,
                    context=context,
                    metadata={"node_id": node_id, "node_data": node_data},
                )
                response = await applet.on_message(msg)
                last_output = response.content
                context.update(response.context)
                if not isinstance(context.get("results"), dict):
                    context["results"] = {}
                context["results"][node_id] = {
                    "type": node_type,
                    "output": last_output,
                    "status": "success",
                }

                targets = Orchestrator._collect_outgoing_targets(outgoing_edges)
                for target in targets:
                    if target not in next_nodes:
                        next_nodes.append(target)

            current_nodes = next_nodes

        return last_output


applet_registry[SUBFLOW_NODE_TYPE] = SubflowApplet


# ============================================================
# Orchestrator Core
# ============================================================


class Orchestrator:
    """Core orchestration engine that executes applet flows."""

    @staticmethod
    async def load_applet(applet_type: str) -> BaseApplet:
        """Dynamically load an applet by type."""
        normalized_type = applet_type.strip().lower()
        if normalized_type in applet_registry:
            return applet_registry[normalized_type]()

        if normalized_type == LLM_NODE_TYPE:
            applet_registry[LLM_NODE_TYPE] = LLMNodeApplet
            return LLMNodeApplet()

        if normalized_type in {IMAGE_NODE_TYPE, "image_gen", "image-gen"}:
            applet_registry[IMAGE_NODE_TYPE] = ImageGenNodeApplet
            return ImageGenNodeApplet()

        if normalized_type in {MEMORY_NODE_TYPE, "memory_node", "memory-node"}:
            applet_registry[MEMORY_NODE_TYPE] = MemoryNodeApplet
            return MemoryNodeApplet()

        if normalized_type in {
            HTTP_REQUEST_NODE_TYPE,
            "http-request",
            "httprequest",
            "http_request_node",
            "http",
        }:
            applet_registry[HTTP_REQUEST_NODE_TYPE] = HTTPRequestNodeApplet
            return HTTPRequestNodeApplet()

        if normalized_type in {
            CODE_NODE_TYPE,
            "code-node",
            "code_node",
            "code_execution",
            "code-execution",
        }:
            applet_registry[CODE_NODE_TYPE] = CodeNodeApplet
            return CodeNodeApplet()

        if normalized_type in {
            TRANSFORM_NODE_TYPE,
            "transform-node",
            "transform_node",
            "transformer",
            "data_transform",
            "data-transform",
        }:
            applet_registry[TRANSFORM_NODE_TYPE] = TransformNodeApplet
            return TransformNodeApplet()

        if normalized_type in {
            IF_ELSE_NODE_TYPE,
            "ifelse",
            "if-else",
            "conditional",
            "condition",
            "condition_node",
            "condition-node",
        }:
            applet_registry[IF_ELSE_NODE_TYPE] = IfElseNodeApplet
            return IfElseNodeApplet()

        if normalized_type in {
            BRANCH_NODE_TYPE,
            "branch_node",
            "branch-node",
            "multi_branch",
            "multi-branch",
        }:
            applet_registry[BRANCH_NODE_TYPE] = BranchApplet
            return BranchApplet()

        if normalized_type in {
            COMPOUND_MERGE_NODE_TYPE,
            "compound_merge",
            "compound-merge",
            "branch_merge",
            "branch-merge",
        }:
            applet_registry[COMPOUND_MERGE_NODE_TYPE] = CompoundMergeApplet
            return CompoundMergeApplet()

        if normalized_type in {
            MERGE_NODE_TYPE,
            "fan_in",
            "fan-in",
            "merge_node",
            "merge-node",
            "fanin",
        }:
            applet_registry[MERGE_NODE_TYPE] = MergeNodeApplet
            return MergeNodeApplet()

        if normalized_type in {
            FOR_EACH_NODE_TYPE,
            "foreach",
            "for-each",
            "for_each_node",
            "for-each-node",
            "loop",
        }:
            applet_registry[FOR_EACH_NODE_TYPE] = ForEachNodeApplet
            return ForEachNodeApplet()

        if normalized_type in {
            WEBHOOK_TRIGGER_NODE_TYPE,
            "webhook-trigger",
            "webhook_trigger_node",
            "webhook-trigger-node",
        }:
            applet_registry[WEBHOOK_TRIGGER_NODE_TYPE] = WebhookTriggerNodeApplet
            return WebhookTriggerNodeApplet()

        if normalized_type in {
            SCHEDULER_NODE_TYPE,
            "scheduler",
            "scheduler-node",
            "cron",
            "cron_node",
            "cron-node",
        }:
            applet_registry[SCHEDULER_NODE_TYPE] = SchedulerNodeApplet
            return SchedulerNodeApplet()

        if normalized_type in {
            ERROR_HANDLER_NODE_TYPE,
            "error-handler",
            "error_handler_node",
            "error-handler-node",
            "catch",
        }:
            applet_registry[ERROR_HANDLER_NODE_TYPE] = ErrorHandlerNodeApplet
            return ErrorHandlerNodeApplet()

        # Fallback: check the plugin registry for third-party node types (N-60)
        plugin_entry = plugin_registry.get_by_node_type(normalized_type)
        if plugin_entry:
            return DynamicPluginApplet(plugin_entry)

        try:
            module_path = f"apps.applets.{normalized_type}.applet"
            module = importlib.import_module(module_path)
            applet_class = getattr(module, f"{normalized_type.capitalize()}Applet")
            applet_registry[normalized_type] = applet_class
            return applet_class()
        except (ImportError, AttributeError) as e:
            logger.error(f"Failed to load applet '{normalized_type}': {e}")
            raise ValueError(f"Applet type '{normalized_type}' not found") from e

    @staticmethod
    def create_run_id() -> str:
        """Generate a unique run ID."""
        return str(uuid.uuid4())

    @staticmethod
    def _collect_outgoing_targets(outgoing_edges: list[dict[str, Any]]) -> list[str]:
        """Collect unique target ids from outgoing edges while preserving order."""
        targets: list[str] = []
        for edge in outgoing_edges:
            target = edge.get("target")
            if isinstance(target, str) and target and target not in targets:
                targets.append(target)
        return targets

    @staticmethod
    def _branch_from_hint(hint: Any) -> str | None:
        """Infer a branch from an arbitrary string hint."""
        if hint is None:
            return None
        text = str(hint).strip().lower()
        if not text:
            return None

        normalized = text.replace("-", "_")
        if normalized in _TRUE_BRANCH_HINTS:
            return "true"
        if normalized in _FALSE_BRANCH_HINTS:
            return "false"

        tokens = [token for token in re.split(r"[^a-z0-9]+", normalized) if token]
        has_true = any(token in _TRUE_BRANCH_HINTS for token in tokens)
        has_false = any(token in _FALSE_BRANCH_HINTS for token in tokens)
        if has_true and not has_false:
            return "true"
        if has_false and not has_true:
            return "false"
        return None

    @staticmethod
    def _extract_if_else_branch(response: AppletMessage | None) -> str:
        """Resolve true/false routing branch from an if/else applet response."""
        if response is None:
            return "false"

        if isinstance(response.metadata, dict):
            branch = Orchestrator._branch_from_hint(response.metadata.get("branch"))
            if branch:
                return branch
            raw_result = response.metadata.get("condition_result")
            branch = Orchestrator._branch_from_hint(raw_result)
            if branch:
                return branch
            if isinstance(raw_result, bool):
                return "true" if raw_result else "false"
            if isinstance(raw_result, (int, float)):
                return "true" if raw_result != 0 else "false"

        if isinstance(response.content, dict):
            branch = Orchestrator._branch_from_hint(response.content.get("branch"))
            if branch:
                return branch
            raw_result = response.content.get("result")
            branch = Orchestrator._branch_from_hint(raw_result)
            if branch:
                return branch
            if isinstance(raw_result, bool):
                return "true" if raw_result else "false"
            if isinstance(raw_result, (int, float)):
                return "true" if raw_result != 0 else "false"

        return "false"

    @staticmethod
    def _branch_target_from_node_data(node: dict[str, Any], branch: str) -> str | None:
        """Read explicit branch target ids from if/else node data."""
        node_data = node.get("data", {})
        if not isinstance(node_data, dict):
            return None

        keys = (
            ("true_target", "trueTarget", "on_true", "onTrue", "then_target", "thenTarget")
            if branch == "true"
            else ("false_target", "falseTarget", "on_false", "onFalse", "else_target", "elseTarget")
        )
        for key in keys:
            value = node_data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    @staticmethod
    def _infer_edge_branch(edge: dict[str, Any]) -> str | None:
        """Infer true/false branch from edge metadata."""
        candidates: list[Any] = [
            edge.get("branch"),
            edge.get("label"),
            edge.get("sourceHandle"),
            edge.get("source_handle"),
            edge.get("targetHandle"),
            edge.get("target_handle"),
            edge.get("id"),
        ]

        edge_data = edge.get("data")
        if isinstance(edge_data, dict):
            candidates.extend(
                [
                    edge_data.get("branch"),
                    edge_data.get("label"),
                    edge_data.get("sourceHandle"),
                    edge_data.get("source_handle"),
                    edge_data.get("targetHandle"),
                    edge_data.get("target_handle"),
                ]
            )

        for candidate in candidates:
            branch = Orchestrator._branch_from_hint(candidate)
            if branch:
                return branch
        return None

    @staticmethod
    def _resolve_next_targets(
        node: dict[str, Any],
        outgoing_edges: list[dict[str, Any]],
        response: AppletMessage | None = None,
    ) -> list[str]:
        """Resolve outgoing targets, applying conditional routing for if/else nodes."""
        default_targets = Orchestrator._collect_outgoing_targets(outgoing_edges)
        node_type = str(node.get("type", "")).strip().lower()
        if node_type != IF_ELSE_NODE_TYPE:
            return default_targets

        if not outgoing_edges:
            return []

        selected_branch = Orchestrator._extract_if_else_branch(response)
        explicit_target = Orchestrator._branch_target_from_node_data(node, selected_branch)
        if explicit_target and explicit_target in default_targets:
            return [explicit_target]

        branch_targets: list[str] = []
        for index, edge in enumerate(outgoing_edges):
            inferred_branch = Orchestrator._infer_edge_branch(edge)
            if inferred_branch is None:
                if len(outgoing_edges) >= 2:
                    inferred_branch = "true" if index == 0 else "false" if index == 1 else None
                else:
                    inferred_branch = "true" if index == 0 else None

            if inferred_branch != selected_branch:
                continue

            target = edge.get("target")
            if isinstance(target, str) and target and target not in branch_targets:
                branch_targets.append(target)

        if branch_targets:
            return [branch_targets[0]]

        if selected_branch == "true":
            return default_targets[:1]
        if len(default_targets) > 1:
            return [default_targets[1]]
        return []

    @staticmethod
    def _mark_animated_edges(
        flow_edges: list[dict[str, Any]],
        source_node_id: str,
        selected_targets: list[str],
    ) -> None:
        """Mark selected edges as animated for runtime visualization."""
        if not selected_targets:
            return
        selected_target_set = set(selected_targets)
        for edge in flow_edges:
            if edge.get("source") != source_node_id:
                continue
            if edge.get("target") in selected_target_set:
                edge["animated"] = True

    @staticmethod
    def migrate_legacy_writer_nodes(flow: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        """Convert legacy writer nodes into LLM nodes with OpenAI GPT-4o defaults."""
        if not isinstance(flow, dict):
            return flow, False

        nodes = flow.get("nodes")
        if not isinstance(nodes, list):
            return flow, False

        migrated = False
        migrated_nodes: list[Any] = []

        for node in nodes:
            if not isinstance(node, dict):
                migrated_nodes.append(node)
                continue

            node_type = str(node.get("type", "")).strip().lower()
            if node_type != LEGACY_WRITER_NODE_TYPE:
                migrated_nodes.append(node)
                continue

            node_data = node.get("data", {})
            migrated_data = dict(node_data) if isinstance(node_data, dict) else {}

            if "systemPrompt" in migrated_data and "system_prompt" not in migrated_data:
                migrated_data["system_prompt"] = migrated_data["systemPrompt"]
            if "maxTokens" in migrated_data and "max_tokens" not in migrated_data:
                migrated_data["max_tokens"] = migrated_data["maxTokens"]

            for key, value in LEGACY_WRITER_LLM_PRESET.items():
                migrated_data.setdefault(key, value)

            migrated_data.setdefault("legacy_applet", LEGACY_WRITER_NODE_TYPE)
            migrated_data.setdefault("migration_source", "T-052")

            migrated_node = dict(node)
            migrated_node["type"] = LLM_NODE_TYPE
            migrated_node["data"] = migrated_data
            migrated_nodes.append(migrated_node)
            migrated = True

        if not migrated:
            return flow, False

        migrated_flow = dict(flow)
        migrated_flow["nodes"] = migrated_nodes
        return migrated_flow, True

    @staticmethod
    def _resolve_legacy_artist_defaults(generator: Any) -> dict[str, str]:
        """Map legacy artist generator values to image-provider defaults."""
        if isinstance(generator, str):
            value = generator.strip().lower()
            if value in {"openai", "dall-e-3", "dall-e3", "dalle3"}:
                return {"provider": "openai", "model": "dall-e-3"}
            if value in {"flux", "flux-1.1-pro", "flux-1-dev"}:
                return {"provider": "flux", "model": "flux-1.1-pro"}
        return {"provider": "stability", "model": "stable-diffusion-xl-1024-v1-0"}

    @staticmethod
    def migrate_legacy_artist_nodes(flow: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        """Convert legacy artist nodes into image nodes with provider presets."""
        if not isinstance(flow, dict):
            return flow, False

        nodes = flow.get("nodes")
        if not isinstance(nodes, list):
            return flow, False

        migrated = False
        migrated_nodes: list[Any] = []

        for node in nodes:
            if not isinstance(node, dict):
                migrated_nodes.append(node)
                continue

            node_type = str(node.get("type", "")).strip().lower()
            if node_type != LEGACY_ARTIST_NODE_TYPE:
                migrated_nodes.append(node)
                continue

            node_data = node.get("data", {})
            migrated_data = dict(node_data) if isinstance(node_data, dict) else {}

            generator = migrated_data.get("provider")
            if not isinstance(generator, str):
                generator = migrated_data.get("generator", migrated_data.get("image_generator"))

            provider_defaults = Orchestrator._resolve_legacy_artist_defaults(generator)

            if "responseFormat" in migrated_data and "response_format" not in migrated_data:
                migrated_data["response_format"] = migrated_data["responseFormat"]

            for key, value in LEGACY_ARTIST_IMAGE_PRESET.items():
                migrated_data.setdefault(key, value)

            migrated_data.setdefault("provider", provider_defaults["provider"])
            migrated_data.setdefault("model", provider_defaults["model"])
            migrated_data.setdefault("legacy_applet", LEGACY_ARTIST_NODE_TYPE)
            migrated_data.setdefault("migration_source", "T-054")

            migrated_node = dict(node)
            migrated_node["type"] = IMAGE_NODE_TYPE
            migrated_node["data"] = migrated_data
            migrated_nodes.append(migrated_node)
            migrated = True

        if not migrated:
            return flow, False

        migrated_flow = dict(flow)
        migrated_flow["nodes"] = migrated_nodes
        return migrated_flow, True

    @staticmethod
    def _normalize_legacy_memory_backend(raw_backend: Any) -> str:
        """Map legacy memory backend names to supported memory-node backend ids."""
        if not isinstance(raw_backend, str):
            return "sqlite_fts"
        normalized = raw_backend.strip().lower()
        return LEGACY_MEMORY_BACKEND_ALIASES.get(normalized, "sqlite_fts")

    @staticmethod
    def migrate_legacy_memory_nodes(flow: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        """Convert legacy memory applet nodes into memory nodes with persistent defaults."""
        if not isinstance(flow, dict):
            return flow, False

        nodes = flow.get("nodes")
        if not isinstance(nodes, list):
            return flow, False

        migrated = False
        migrated_nodes: list[Any] = []

        for node in nodes:
            if not isinstance(node, dict):
                migrated_nodes.append(node)
                continue

            raw_node_type = str(node.get("type", "")).strip()
            node_type = raw_node_type.lower()
            is_memory_node = node_type == MEMORY_NODE_TYPE
            is_memory_alias = node_type in {"memoryapplet", "memory_applet", "memory-applet"}
            if not (is_memory_node or is_memory_alias):
                migrated_nodes.append(node)
                continue

            node_data = node.get("data", {})
            migrated_data = dict(node_data) if isinstance(node_data, dict) else {}

            legacy_key_mappings = {
                "memoryKey": "key",
                "memory_key": "key",
                "memoryNamespace": "namespace",
                "memory_namespace": "namespace",
                "persistPath": "persist_path",
                "collectionName": "collection",
                "includeMetadata": "include_metadata",
                "topK": "top_k",
            }
            for legacy_key, modern_key in legacy_key_mappings.items():
                if legacy_key in migrated_data and modern_key not in migrated_data:
                    migrated_data[modern_key] = migrated_data[legacy_key]

            if "backend" in migrated_data:
                migrated_data["backend"] = Orchestrator._normalize_legacy_memory_backend(
                    migrated_data.get("backend")
                )
            else:
                migrated_data["backend"] = "sqlite_fts"

            operation = migrated_data.get("operation", "store")
            if isinstance(operation, str):
                normalized_operation = operation.strip().lower()
            else:
                normalized_operation = "store"
            if normalized_operation not in {"store", "retrieve", "delete", "clear"}:
                normalized_operation = "store"
            migrated_data["operation"] = normalized_operation

            namespace = migrated_data.get("namespace", DEFAULT_MEMORY_NAMESPACE)
            if not isinstance(namespace, str) or not namespace.strip():
                namespace = DEFAULT_MEMORY_NAMESPACE
            migrated_data["namespace"] = namespace.strip()

            if "tags" in migrated_data and isinstance(migrated_data["tags"], str):
                migrated_data["tags"] = [migrated_data["tags"]]

            if "top_k" in migrated_data:
                try:
                    migrated_data["top_k"] = max(1, min(50, int(migrated_data["top_k"])))
                except (TypeError, ValueError):
                    migrated_data["top_k"] = 5

            migrated_data.setdefault("label", "Memory")
            migrated_data.setdefault("include_metadata", False)
            migrated_data.setdefault("legacy_applet", LEGACY_MEMORY_NODE_TYPE)
            migrated_data.setdefault("migration_source", "T-056")

            migrated_node = dict(node)
            migrated_node["type"] = MEMORY_NODE_TYPE
            migrated_node["data"] = migrated_data
            migrated_nodes.append(migrated_node)

            if migrated_node != node:
                migrated = True

        if not migrated:
            return flow, False

        migrated_flow = dict(flow)
        migrated_flow["nodes"] = migrated_nodes
        return migrated_flow, True

    @staticmethod
    def migrate_legacy_nodes(flow: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        """Apply all known legacy node migrations."""
        writer_migrated_flow, writer_migrated = Orchestrator.migrate_legacy_writer_nodes(flow)
        artist_migrated_flow, artist_migrated = Orchestrator.migrate_legacy_artist_nodes(
            writer_migrated_flow
        )
        fully_migrated_flow, memory_migrated = Orchestrator.migrate_legacy_memory_nodes(
            artist_migrated_flow
        )
        return fully_migrated_flow, (writer_migrated or artist_migrated or memory_migrated)

    @staticmethod
    async def auto_migrate_legacy_nodes(
        flow: dict[str, Any] | None,
        persist: bool = False,
    ) -> dict[str, Any] | None:
        """Apply known legacy node migrations and optionally persist migrated flow."""
        if not flow:
            return flow

        migrated_flow, migrated = Orchestrator.migrate_legacy_nodes(flow)
        if migrated:
            logger.info(
                "Auto-migrated legacy nodes for flow '%s'",
                migrated_flow.get("id"),
            )
            if persist:
                await FlowRepository.save(migrated_flow)
        return migrated_flow

    @staticmethod
    async def auto_migrate_legacy_writer_nodes(
        flow: dict[str, Any] | None,
        persist: bool = False,
    ) -> dict[str, Any] | None:
        """Backward-compatible alias for legacy migration helper."""
        return await Orchestrator.auto_migrate_legacy_nodes(flow, persist=persist)

    @staticmethod
    def _topological_layers(
        nodes_by_id: dict[str, dict[str, Any]],
        edges_by_source: dict[str, list[dict[str, Any]]],
        incoming_sources_by_target: dict[str, list[str]],
    ) -> list[list[str]]:
        """Compute topological layers (Kahn's algorithm).

        Returns a list of layers, where each layer contains node IDs that
        have no unresolved dependencies and can execute in parallel.
        """
        in_degree: dict[str, int] = {nid: 0 for nid in nodes_by_id}
        for target_id, sources in incoming_sources_by_target.items():
            if target_id in in_degree:
                in_degree[target_id] = len(sources)

        queue = [nid for nid, deg in in_degree.items() if deg == 0]
        layers: list[list[str]] = []

        while queue:
            layers.append(list(queue))
            next_queue: list[str] = []
            for nid in queue:
                for edge in edges_by_source.get(nid, []):
                    target = edge.get("target")
                    if not isinstance(target, str) or target not in in_degree:
                        continue
                    in_degree[target] -= 1
                    if in_degree[target] == 0 and target not in next_queue:
                        next_queue.append(target)
            queue = next_queue

        # Any remaining nodes (cycles) get appended as a final layer
        remaining = [nid for nid, deg in in_degree.items() if deg > 0]
        if remaining:
            layers.append(remaining)

        return layers

    @staticmethod
    def _detect_parallel_groups(
        layer: list[str],
        nodes_by_id: dict[str, dict[str, Any]],
    ) -> list[list[str]]:
        """Split a topological layer into parallel-safe groups.

        Merge nodes and nodes with order dependencies are isolated;
        all other independent nodes are grouped together for parallel execution.
        """
        parallel_group: list[str] = []
        sequential: list[list[str]] = []

        for nid in layer:
            node = nodes_by_id.get(nid)
            if not isinstance(node, dict):
                continue
            node_type = str(node.get("type", "")).strip().lower()
            # Merge nodes must wait for inputs; run them individually
            if node_type == MERGE_NODE_TYPE:
                sequential.append([nid])
            else:
                parallel_group.append(nid)

        groups: list[list[str]] = []
        if parallel_group:
            groups.append(parallel_group)
        groups.extend(sequential)
        return groups

    @staticmethod
    async def execute_flow(flow: dict, input_data: dict[str, Any]) -> str:
        """Execute a flow and return the run ID."""
        run_id = Orchestrator.create_run_id()
        start_time = time.time()
        flow_id = flow.get("id")
        initial_trace = _new_execution_trace(run_id, flow_id, input_data, start_time)

        status = {
            "run_id": run_id,
            "flow_id": flow_id,
            "status": "running",
            "current_applet": None,
            "progress": 0,
            "total_steps": len(flow.get("nodes", [])),
            "start_time": start_time,
            "results": {TRACE_RESULTS_KEY: initial_trace},
            "input_data": input_data,
        }

        status_dict = status.copy()

        flow_name = flow.get("name", "")
        if flow_name:
            metrics.record_template_run(flow_name)

        await emit_event(
            "template_started",
            {
                "run_id": run_id,
                "flow_id": flow_id,
                "flow_name": flow_name,
            },
        )

        # Register with execution dashboard (best-effort, never blocks execution)
        try:
            _input_bytes = len(str(input_data).encode("utf-8", errors="replace"))
            execution_dashboard_store.register(
                run_id=run_id,
                flow_id=flow_id or "",
                flow_name=flow_name,
                user_id="",  # user context not available in static method
                node_count=len(flow.get("nodes", [])),
                input_size_bytes=_input_bytes,
            )
        except Exception as _dash_exc:
            logger.warning("Execution dashboard register failed: %s", _dash_exc)

        workflow_run_repo = WorkflowRunRepository()
        logger.info(f"Starting workflow execution with run ID: {run_id}")
        await workflow_run_repo.save(status_dict)

        broadcast_status_dict = status_dict.copy()
        broadcast_status_dict["completed_applets"] = []
        await broadcast_status(broadcast_status_dict)

        asyncio.create_task(
            Orchestrator._execute_flow_async(
                run_id, flow, input_data, workflow_run_repo, broadcast_status
            )
        )

        return run_id

    @staticmethod
    async def _execute_flow_async(
        run_id: str,
        flow: dict,
        input_data: dict[str, Any],
        workflow_run_repo: WorkflowRunRepository,
        broadcast_status_fn,
    ):
        """Execute a flow with parallel independent-node support.

        The engine performs a BFS traversal where each wave of ``current_nodes``
        is partitioned into *parallel groups* (independent nodes that share no
        mutual edges) and *sequential groups* (merge/fan-in nodes that need all
        inputs).  Parallel groups are dispatched concurrently via
        ``asyncio.gather`` with a configurable semaphore.
        """
        status = None
        memory_completed_applets: list[str] = []
        context: dict[str, Any] = {}
        execution_trace = _new_execution_trace(run_id, flow.get("id"), input_data, time.time())

        def _ensure_trace_in_context_results() -> None:
            results = context.get("results")
            if not isinstance(results, dict):
                results = {}
                context["results"] = results
            results[TRACE_RESULTS_KEY] = execution_trace

        def _append_trace_error(payload: Any) -> None:
            errors = execution_trace.setdefault("errors", [])
            if isinstance(errors, list):
                errors.append(_trace_value(payload))

        async def _fail(error_msg: str, error_details: dict[str, Any] | None = None) -> None:
            nonlocal status
            end_time = time.time()
            if error_details:
                _append_trace_error(error_details)
            else:
                _append_trace_error({"message": error_msg})
            _finalize_execution_trace(execution_trace, "error", end_time)
            _ensure_trace_in_context_results()

            if status and isinstance(status, dict):
                status["status"] = "error"
                status["error"] = error_msg
                if error_details:
                    status["error_details"] = error_details
                status["end_time"] = end_time
                status["results"] = context.get("results", {})
                status["completed_applets"] = list(memory_completed_applets)
                await workflow_run_repo.save(status)
                await broadcast_status_fn(status)
            else:
                await broadcast_status_fn(
                    {
                        "run_id": run_id,
                        "status": "error",
                        "error": error_msg,
                        "completed_applets": list(memory_completed_applets),
                    }
                )
            # Push to Dead Letter Queue for failed runs
            try:
                dead_letter_queue.push(
                    run_id=run_id,
                    flow_id=flow.get("id") if isinstance(flow, dict) else None,
                    flow_snapshot=dict(flow) if isinstance(flow, dict) else None,
                    input_data=input_data if isinstance(input_data, dict) else {},
                    error=error_msg,
                    error_details=error_details,
                )
            except Exception as dlq_exc:  # noqa: BLE001
                logger.warning("Failed to push run %s to DLQ: %s", run_id, dlq_exc)
            # N-33: SLA violation detection on error path (best-effort)
            try:
                _sla_fid = flow.get("id", "") if isinstance(flow, dict) else ""
                _sla_pol = sla_store.get_policy(_sla_fid)
                _sla_dur = end_time - (
                    status.get("start_time", end_time)
                    if status and isinstance(status, dict)
                    else end_time
                )
                if _sla_pol:
                    sla_store.increment_run_count(_sla_pol["owner_id"])
                    if _sla_dur > _sla_pol["max_duration_seconds"]:
                        sla_store.record_violation(
                            policy_id=_sla_pol["policy_id"],
                            flow_id=_sla_fid,
                            run_id=run_id,
                            actual_duration=_sla_dur,
                            max_duration=_sla_pol["max_duration_seconds"],
                        )
            except Exception as _sla_err_exc:
                logger.warning("SLA tracking (error path) failed: %s", _sla_err_exc)

        try:
            status = await workflow_run_repo.get_by_run_id(run_id)

            if status and isinstance(status, dict):
                status_start_time = status.get("start_time")
                if isinstance(status_start_time, (int, float)):
                    execution_trace["started_at"] = float(status_start_time)

                status_input_data = status.get("input_data")
                if isinstance(status_input_data, dict):
                    execution_trace["input"] = _trace_value(status_input_data)

                status_results = status.get("results")
                if isinstance(status_results, dict):
                    existing_trace = status_results.get(TRACE_RESULTS_KEY)
                    if isinstance(existing_trace, dict):
                        normalized_trace = _trace_value(existing_trace)
                        if isinstance(normalized_trace, dict):
                            execution_trace = normalized_trace

            flow_nodes = flow.get("nodes", [])
            flow_edges = flow.get("edges", [])

            nodes_by_id: dict[str, dict[str, Any]] = {
                node["id"]: node
                for node in flow_nodes
                if isinstance(node, dict) and isinstance(node.get("id"), str)
            }

            edges_by_source: dict[str, list[dict[str, Any]]] = {}
            incoming_sources_by_target: dict[str, list[str]] = {}
            for edge in flow_edges:
                if not isinstance(edge, dict):
                    continue
                source = edge.get("source")
                target = edge.get("target")
                if not isinstance(source, str) or not source:
                    continue
                if not isinstance(target, str) or not target:
                    continue
                edges_by_source.setdefault(source, []).append(edge)
                incoming_sources = incoming_sources_by_target.setdefault(target, [])
                if source not in incoming_sources:
                    incoming_sources.append(source)

            target_nodes = {
                edge.get("target")
                for edge in flow_edges
                if isinstance(edge, dict) and isinstance(edge.get("target"), str)
            }
            start_nodes = [
                node["id"]
                for node in flow_nodes
                if isinstance(node, dict)
                and isinstance(node.get("id"), str)
                and node["id"] not in target_nodes
            ]
            scheduled_nodes = set(start_nodes)

            if not start_nodes:
                await _fail("No start node found in flow")
                return

            context = {
                "input": input_data,
                "results": {TRACE_RESULTS_KEY: execution_trace},
                "run_id": run_id,
            }
            merge_inputs_by_node: dict[str, list[Any]] = {}
            merge_input_sources_by_node: dict[str, list[str]] = {}
            _ensure_trace_in_context_results()

            if status and isinstance(status, dict):
                status["input_data"] = input_data

            # Read configurable concurrency limit
            flow_concurrency = ENGINE_MAX_CONCURRENCY
            flow_meta = flow.get("data", flow.get("metadata", {}))
            if isinstance(flow_meta, dict):
                raw_conc = flow_meta.get(
                    "engine_max_concurrency",
                    flow_meta.get("engineMaxConcurrency"),
                )
                if raw_conc is not None:
                    try:
                        flow_concurrency = max(1, int(raw_conc))
                    except (ValueError, TypeError):
                        pass
            engine_semaphore = asyncio.Semaphore(flow_concurrency)

            visited: set = set()
            failed_node_id: str | None = None

            # ----------------------------------------------------------------
            # _execute_single_node — extracted for reuse in parallel dispatch
            # ----------------------------------------------------------------
            async def _execute_single_node(node_id: str) -> list[str] | None:
                """Execute one node and return its downstream target IDs.

                Returns ``None`` on fatal (non-fallback) error to signal abort.
                """
                nonlocal failed_node_id

                node = nodes_by_id.get(node_id)
                if not isinstance(node, dict):
                    return []
                node_type = str(node.get("type", "")).strip().lower()
                outgoing_edges = edges_by_source.get(node_id, [])
                node_started_at = time.time()
                node_trace: dict[str, Any] = {
                    "node_id": node_id,
                    "node_type": node.get("type"),
                    "status": "running",
                    "input": None,
                    "output": None,
                    "attempts": 0,
                    "errors": [],
                    "started_at": node_started_at,
                    "ended_at": None,
                    "duration_ms": None,
                }
                execution_log_store.append(
                    run_id,
                    {
                        "timestamp": node_started_at,
                        "run_id": run_id,
                        "node_id": node_id,
                        "node_type": node.get("type"),
                        "event": "node_start",
                        "attempt": 1,
                        "input": None,
                        "output": None,
                        "error": None,
                        "duration_ms": None,
                    },
                )
                # Capture secret values once per node for log masking
                _node_secret_values: set[str] = workflow_secret_store.get_secret_values(
                    flow.get("id", "")
                )

                # -- merge gate: defer if not all inputs arrived --
                if node_type == MERGE_NODE_TYPE:
                    required = incoming_sources_by_target.get(node_id, [])
                    received = merge_input_sources_by_node.get(node_id, [])
                    missing = [s for s in required if s not in received]
                    if missing and any(s in scheduled_nodes and s not in visited for s in missing):
                        return [node_id]  # re-enqueue

                visited.add(node_id)

                if status and isinstance(status, dict):
                    status["current_applet"] = node.get("type")
                    status["progress"] = status.get("progress", 0) + 1
                    status["results"] = context.get("results", {})

                if node_id not in memory_completed_applets:
                    memory_completed_applets.append(node_id)

                if status and isinstance(status, dict):
                    bcast = status.copy()
                    bcast["completed_applets"] = list(memory_completed_applets)
                    await workflow_run_repo.save(status)
                    await broadcast_status_fn(bcast)

                # -- start / end passthrough --
                if node_type in ("start", "end"):
                    if (
                        node_type == "start"
                        and isinstance(node.get("data"), dict)
                        and "parsedInputData" in node["data"]
                    ):
                        parsed_input = node["data"]["parsedInputData"]
                        if parsed_input and isinstance(parsed_input, dict):
                            context["input"] = parsed_input
                            if status and isinstance(status, dict):
                                status["input_data"] = parsed_input

                    next_targets = Orchestrator._collect_outgoing_targets(outgoing_edges)
                    passthrough_output = context.get("input", input_data)
                    node_ended_at = time.time()
                    node_trace["status"] = "success"
                    node_trace["input"] = _trace_value(context.get("input", input_data))
                    node_trace["output"] = _trace_value(passthrough_output)
                    node_trace["attempts"] = 1
                    node_trace["ended_at"] = node_ended_at
                    node_trace["duration_ms"] = max(
                        0.0,
                        (node_ended_at - node_started_at) * 1000.0,
                    )
                    context["results"][node_id] = {
                        "type": node["type"],
                        "input": _trace_value(context.get("input", input_data)),
                        "output": passthrough_output,
                        "status": "success",
                        "attempts": 1,
                        "errors": [],
                        "started_at": node_started_at,
                        "ended_at": node_ended_at,
                        "duration_ms": node_trace["duration_ms"],
                    }
                    trace_nodes = execution_trace.setdefault("nodes", [])
                    if isinstance(trace_nodes, list):
                        trace_nodes.append(node_trace)
                    _ensure_trace_in_context_results()
                    execution_log_store.append(
                        run_id,
                        {
                            "timestamp": node_trace["ended_at"],
                            "run_id": run_id,
                            "node_id": node_id,
                            "node_type": node_trace["node_type"],
                            "event": "node_success",
                            "attempt": 1,
                            "input": _mask_secrets(node_trace["input"], _node_secret_values),
                            "output": _mask_secrets(node_trace["output"], _node_secret_values),
                            "error": None,
                            "duration_ms": node_trace["duration_ms"],
                        },
                    )

                    for tid in next_targets:
                        scheduled_nodes.add(tid)
                        tn = nodes_by_id.get(tid)
                        if (
                            isinstance(tn, dict)
                            and str(tn.get("type", "")).strip().lower() == MERGE_NODE_TYPE
                        ):
                            merge_inputs_by_node.setdefault(tid, []).append(passthrough_output)
                            ms = merge_input_sources_by_node.setdefault(tid, [])
                            if node_id not in ms:
                                ms.append(node_id)
                    return next_targets

                # -- normal applet execution with retry / timeout / fallback --
                node_data = node.get("data", {})
                if not isinstance(node_data, dict):
                    node_data = {}

                # -- resolve {{var.*}} and {{secret.*}} templates in node data --
                _flow_id = flow.get("id", "")
                _vars = workflow_variable_store.get(_flow_id)
                _secrets = workflow_secret_store.get_raw(_flow_id)
                if _vars or _secrets:
                    node_data = _resolve_node_data(node_data, _vars, _secrets)

                timeout_seconds = float(node_data.get("timeout_seconds", 60.0))
                retry_config = node_data.get("retry_config", {})
                if not isinstance(retry_config, dict):
                    retry_config = {}
                max_retries = int(retry_config.get("max_retries", 0))
                retry_delay = float(retry_config.get("delay", 1.0))
                retry_backoff = float(retry_config.get("backoff", 2.0))
                # retry_on: list of conditions — "timeout", "error", or "all" (default)
                retry_on_raw = retry_config.get("retry_on", "all")
                if isinstance(retry_on_raw, str):
                    retry_on_conditions: set[str] = (
                        {"timeout", "error"} if retry_on_raw == "all" else {retry_on_raw}
                    )
                else:
                    retry_on_conditions = (
                        set(retry_on_raw) if retry_on_raw else {"timeout", "error"}
                    )
                fallback_node_id_cfg = node_data.get("fallback_node_id")

                attempts = 0
                last_error: NodeError | None = None
                success = False
                response: AppletMessage | None = None
                message_content_for_trace: Any = None

                while attempts <= max_retries:
                    try:
                        if attempts > 0:
                            wait_time = retry_delay * (retry_backoff ** (attempts - 1))
                            logger.info(
                                f"Retrying node {node_id} (attempt {attempts}/{max_retries}) after {wait_time}s"
                            )
                            execution_log_store.append(
                                run_id,
                                {
                                    "timestamp": time.time(),
                                    "run_id": run_id,
                                    "node_id": node_id,
                                    "node_type": node_trace["node_type"],
                                    "event": "node_retry",
                                    "attempt": attempts + 1,
                                    "input": None,
                                    "output": None,
                                    "error": node_trace["errors"][-1]
                                    if node_trace.get("errors")
                                    else None,
                                    "duration_ms": None,
                                },
                            )
                            await asyncio.sleep(wait_time)
                        attempt_number = attempts + 1

                        applet = await Orchestrator.load_applet(node_type)

                        message_content: Any = input_data
                        if node_type == MERGE_NODE_TYPE:
                            node_inputs = list(merge_inputs_by_node.get(node_id, []))
                            node_sources = list(merge_input_sources_by_node.get(node_id, []))
                            message_content = {
                                "inputs": node_inputs,
                                "sources": node_sources,
                                "count": len(node_inputs),
                                "input": input_data,
                            }
                        if message_content_for_trace is None:
                            message_content_for_trace = _trace_value(message_content)

                        message_metadata: dict[str, Any] = {
                            "node_id": node_id,
                            "run_id": run_id,
                        }
                        message_metadata["node_data"] = node_data

                        if node_type == "writer" and "systemPrompt" in node_data:
                            message_metadata["system_prompt"] = node_data["systemPrompt"]
                        if node_type == "artist":
                            if "system_prompt" in node_data:
                                message_metadata["system_prompt"] = node_data["system_prompt"]
                            elif "systemPrompt" in node_data:
                                message_metadata["system_prompt"] = node_data["systemPrompt"]
                            if "generator" in node_data:
                                message_metadata["generator"] = node_data["generator"]

                        message = AppletMessage(
                            content=message_content,
                            context=context,
                            metadata=message_metadata,
                        )
                        node_trace["attempts"] = attempt_number

                        async with engine_semaphore:
                            response = await asyncio.wait_for(
                                applet.on_message(message),
                                timeout=timeout_seconds,
                            )

                        node_ended_at = time.time()
                        context["results"][node_id] = {
                            "type": node["type"],
                            "input": _trace_value(message_content),
                            "output": response.content,
                            "status": "success",
                            "attempts": attempt_number,
                            "errors": _trace_value(node_trace["errors"]),
                            "started_at": node_started_at,
                            "ended_at": node_ended_at,
                            "duration_ms": max(0.0, (node_ended_at - node_started_at) * 1000.0),
                        }
                        context.update(response.context)
                        if not isinstance(context.get("results"), dict):
                            context["results"] = {}
                        context["results"][node_id] = context["results"].get(node_id) or {
                            "type": node["type"],
                            "input": _trace_value(message_content),
                            "output": response.content,
                            "status": "success",
                            "attempts": attempt_number,
                            "errors": _trace_value(node_trace["errors"]),
                            "started_at": node_started_at,
                            "ended_at": node_ended_at,
                            "duration_ms": max(0.0, (node_ended_at - node_started_at) * 1000.0),
                        }
                        node_trace["status"] = "success"
                        node_trace["input"] = _trace_value(message_content)
                        node_trace["output"] = _trace_value(response.content)
                        node_trace["ended_at"] = node_ended_at
                        node_trace["duration_ms"] = max(
                            0.0, (node_ended_at - node_started_at) * 1000.0
                        )
                        trace_nodes = execution_trace.setdefault("nodes", [])
                        if isinstance(trace_nodes, list):
                            trace_nodes.append(node_trace)
                        execution_log_store.append(
                            run_id,
                            {
                                "timestamp": node_ended_at,
                                "run_id": run_id,
                                "node_id": node_id,
                                "node_type": node_trace["node_type"],
                                "event": "node_success",
                                "attempt": attempt_number,
                                "input": _mask_secrets(
                                    node_trace.get("input"), _node_secret_values
                                ),
                                "output": _mask_secrets(
                                    node_trace.get("output"), _node_secret_values
                                ),
                                "error": None,
                                "duration_ms": node_trace.get("duration_ms"),
                            },
                        )
                        _ensure_trace_in_context_results()
                        await emit_event(
                            "step_completed",
                            {
                                "run_id": run_id,
                                "node_id": node_id,
                                "node_type": node.get("type"),
                                "duration_ms": node_trace.get("duration_ms"),
                            },
                        )
                        success = True
                        break

                    except TimeoutError:
                        last_error = NodeError(
                            NodeErrorCode.TIMEOUT,
                            f"Node execution timed out after {timeout_seconds}s",
                            node_id=node_id,
                        )
                        logger.warning(
                            f"Timeout in node {node_id} (attempt {attempt_number}/{max_retries + 1})"
                        )
                        errors_list = node_trace.setdefault("errors", [])
                        if isinstance(errors_list, list):
                            errors_list.append(
                                {
                                    "attempt": attempt_number,
                                    "time": time.time(),
                                    "error": last_error.to_dict(),
                                }
                            )
                        if "timeout" not in retry_on_conditions:
                            break  # do not retry on timeout if not configured
                    except Exception as e:
                        last_error = NodeError(
                            NodeErrorCode.EXECUTION_ERROR,
                            str(e),
                            node_id=node_id,
                        )
                        logger.error(
                            f"Error in node {node_id} (attempt {attempt_number}/{max_retries + 1}): {e}"
                        )
                        errors_list = node_trace.setdefault("errors", [])
                        if isinstance(errors_list, list):
                            errors_list.append(
                                {
                                    "attempt": attempt_number,
                                    "time": time.time(),
                                    "error": last_error.to_dict(),
                                }
                            )
                        if "error" not in retry_on_conditions:
                            break  # do not retry on generic error if not configured
                    attempts += 1

                if not success:
                    node_ended_at = time.time()
                    error_payload = (
                        last_error.to_dict() if last_error else {"message": "Unknown error"}
                    )
                    node_trace["input"] = _trace_value(message_content_for_trace)
                    node_trace["attempts"] = attempts
                    node_trace["ended_at"] = node_ended_at
                    node_trace["duration_ms"] = max(0.0, (node_ended_at - node_started_at) * 1000.0)

                    if fallback_node_id_cfg:
                        logger.info(
                            f"Using fallback path for node {node_id} -> {fallback_node_id_cfg}"
                        )
                        node_trace["status"] = "fallback"
                        node_trace["output"] = {
                            "fallback_node_id": fallback_node_id_cfg,
                        }
                        context["results"][node_id] = {
                            "type": node["type"],
                            "input": _trace_value(message_content_for_trace),
                            "output": None,
                            "error": error_payload,
                            "status": "fallback",
                            "attempts": attempts,
                            "errors": _trace_value(node_trace["errors"]),
                            "started_at": node_started_at,
                            "ended_at": node_ended_at,
                            "duration_ms": node_trace["duration_ms"],
                        }
                        trace_nodes = execution_trace.setdefault("nodes", [])
                        if isinstance(trace_nodes, list):
                            trace_nodes.append(node_trace)
                        execution_log_store.append(
                            run_id,
                            {
                                "timestamp": node_ended_at,
                                "run_id": run_id,
                                "node_id": node_id,
                                "node_type": node_trace["node_type"],
                                "event": "node_fallback",
                                "attempt": attempts,
                                "input": _mask_secrets(
                                    node_trace.get("input"), _node_secret_values
                                ),
                                "output": _mask_secrets(
                                    node_trace.get("output"), _node_secret_values
                                ),
                                "error": _mask_secrets(error_payload, _node_secret_values),
                                "duration_ms": node_trace.get("duration_ms"),
                            },
                        )
                        _append_trace_error({"node_id": node_id, "error": error_payload})
                        _ensure_trace_in_context_results()
                        if node_id not in memory_completed_applets:
                            memory_completed_applets.append(node_id)
                        if status and isinstance(status, dict):
                            status["results"] = context["results"]
                            status["completed_applets"] = list(memory_completed_applets)
                            await workflow_run_repo.save(status)
                            await broadcast_status_fn(status)
                        if fallback_node_id_cfg in nodes_by_id:
                            scheduled_nodes.add(fallback_node_id_cfg)
                            return [fallback_node_id_cfg]
                        return []

                    # Fatal failure — no fallback
                    failed_node_id = node_id
                    node_trace["status"] = "error"
                    node_trace["output"] = None
                    context["results"][node_id] = {
                        "type": node["type"],
                        "input": _trace_value(message_content_for_trace),
                        "output": None,
                        "error": error_payload,
                        "status": "error",
                        "attempts": attempts,
                        "errors": _trace_value(node_trace["errors"]),
                        "started_at": node_started_at,
                        "ended_at": node_ended_at,
                        "duration_ms": node_trace["duration_ms"],
                    }
                    trace_nodes = execution_trace.setdefault("nodes", [])
                    if isinstance(trace_nodes, list):
                        trace_nodes.append(node_trace)
                    execution_log_store.append(
                        run_id,
                        {
                            "timestamp": node_ended_at,
                            "run_id": run_id,
                            "node_id": node_id,
                            "node_type": node_trace["node_type"],
                            "event": "node_error",
                            "attempt": attempts,
                            "input": _mask_secrets(node_trace.get("input"), _node_secret_values),
                            "output": None,
                            "error": _mask_secrets(error_payload, _node_secret_values),
                            "duration_ms": node_trace.get("duration_ms"),
                        },
                    )
                    _ensure_trace_in_context_results()
                    err_msg = (
                        f"Error in applet '{node['type']}': "
                        f"{last_error.message if last_error else 'Unknown error'}"
                    )
                    await emit_event(
                        "step_failed",
                        {
                            "run_id": run_id,
                            "node_id": node_id,
                            "node_type": node.get("type"),
                            "error": err_msg,
                        },
                    )
                    await _fail(err_msg, error_payload if isinstance(error_payload, dict) else None)
                    return None

                if node_id not in memory_completed_applets:
                    memory_completed_applets.append(node_id)

                if status and isinstance(status, dict):
                    status["results"] = context["results"]
                    status["completed_applets"] = list(memory_completed_applets)
                    await workflow_run_repo.save(status)
                    await broadcast_status_fn(status)

                selected_targets = Orchestrator._resolve_next_targets(
                    node=node,
                    outgoing_edges=outgoing_edges,
                    response=response,
                )
                for tid in selected_targets:
                    scheduled_nodes.add(tid)
                    tn = nodes_by_id.get(tid)
                    if (
                        isinstance(tn, dict)
                        and str(tn.get("type", "")).strip().lower() == MERGE_NODE_TYPE
                    ):
                        merge_inputs_by_node.setdefault(tid, []).append(
                            response.content if response else None
                        )
                        ms = merge_input_sources_by_node.setdefault(tid, [])
                        if node_id not in ms:
                            ms.append(node_id)

                Orchestrator._mark_animated_edges(
                    flow_edges=flow_edges,
                    source_node_id=node_id,
                    selected_targets=selected_targets,
                )
                return selected_targets

            # ================================================================
            # Main execution loop — BFS with parallel independent nodes
            # ================================================================
            current_nodes = list(start_nodes)

            while current_nodes:
                next_nodes: list[str] = []

                # Partition into ready and deferred (merge nodes still waiting)
                ready: list[str] = []
                deferred: list[str] = []
                for nid in current_nodes:
                    if nid in visited:
                        continue
                    node = nodes_by_id.get(nid)
                    if not isinstance(node, dict):
                        continue
                    nt = str(node.get("type", "")).strip().lower()
                    if nt == MERGE_NODE_TYPE:
                        req = incoming_sources_by_target.get(nid, [])
                        recv = merge_input_sources_by_node.get(nid, [])
                        missing = [s for s in req if s not in recv]
                        if missing and any(
                            s in scheduled_nodes and s not in visited for s in missing
                        ):
                            deferred.append(nid)
                            continue
                    ready.append(nid)

                # Group ready nodes into parallel-safe groups
                groups = Orchestrator._detect_parallel_groups(ready, nodes_by_id)

                for group in groups:
                    if failed_node_id:
                        break

                    if len(group) == 1:
                        # Single node — execute directly
                        result_targets = await _execute_single_node(group[0])
                        if result_targets is None:
                            break
                        for tid in result_targets:
                            if tid not in next_nodes:
                                next_nodes.append(tid)
                    else:
                        # Parallel group — execute concurrently
                        async def _run_node(nid: str) -> tuple:
                            targets = await _execute_single_node(nid)
                            return (nid, targets)

                        parallel_results = await asyncio.gather(
                            *[_run_node(nid) for nid in group],
                            return_exceptions=True,
                        )

                        for pr in parallel_results:
                            if failed_node_id:
                                break
                            if isinstance(pr, BaseException):
                                logger.error(f"Unexpected parallel node error: {pr}")
                                await _fail(f"Unexpected parallel execution error: {pr}")
                                failed_node_id = "parallel_group"
                                break
                            _nid, result_targets = pr
                            if result_targets is None:
                                break
                            for tid in result_targets:
                                if tid not in next_nodes:
                                    next_nodes.append(tid)

                if failed_node_id:
                    return

                # Re-enqueue deferred merge nodes
                for nid in deferred:
                    if nid not in next_nodes:
                        next_nodes.append(nid)

                current_nodes = next_nodes

            if status and isinstance(status, dict):
                end_time = time.time()
                _finalize_execution_trace(execution_trace, "success", end_time)
                _ensure_trace_in_context_results()
                status["status"] = "success"
                status["end_time"] = end_time
                status["results"] = context["results"]
                if "input_data" not in status or not status["input_data"]:
                    status["input_data"] = input_data
                await workflow_run_repo.save(status)
                # Update execution dashboard (best-effort)
                try:
                    _out_bytes = len(
                        str(context.get("results", {})).encode("utf-8", errors="replace")
                    )
                    execution_dashboard_store.update_status(
                        run_id,
                        "completed",
                        completed_nodes=len(memory_completed_applets),
                        output_size_bytes=_out_bytes,
                    )
                except Exception as _dash_exc:
                    logger.warning("Execution dashboard update (success) failed: %s", _dash_exc)
                # N-41: record execution costs (best-effort — never block completion)
                try:
                    _flow_id_for_cost = flow.get("id", "")
                    _node_costs: list[dict[str, Any]] = []
                    for _log_entry in execution_log_store.get(run_id):
                        if _log_entry.get("event") == "node_success":
                            _nid = _log_entry.get("node_id", "")
                            _ntype = _log_entry.get("node_type", "")
                            _node_data = nodes_by_id.get(_nid, {}).get("data", {})
                            _output = _log_entry.get("output") or {}
                            _node_costs.append(
                                _estimate_node_cost(_ntype, _node_data, _output)
                                | {"node_id": _nid, "node_type": _ntype}
                            )
                    cost_tracker_store.record(run_id, _flow_id_for_cost, _node_costs)
                except Exception as _cost_exc:
                    logger.warning("Cost tracking failed: %s", _cost_exc)
                # N-33: SLA violation detection (best-effort)
                try:
                    _sla_flow_id = flow.get("id", "")
                    _sla_policy = sla_store.get_policy(_sla_flow_id)
                    _sla_duration = end_time - status.get("start_time", end_time)
                    if _sla_policy:
                        sla_store.increment_run_count(_sla_policy["owner_id"])
                        if _sla_duration > _sla_policy["max_duration_seconds"]:
                            sla_store.record_violation(
                                policy_id=_sla_policy["policy_id"],
                                flow_id=_sla_flow_id,
                                run_id=run_id,
                                actual_duration=_sla_duration,
                                max_duration=_sla_policy["max_duration_seconds"],
                            )
                except Exception as _sla_exc:
                    logger.warning("SLA tracking failed: %s", _sla_exc)
                broadcast_data = status.copy()
                broadcast_data["completed_applets"] = memory_completed_applets
                await broadcast_status_fn(broadcast_data)
                await emit_event(
                    "template_completed",
                    {
                        "run_id": run_id,
                        "flow_id": flow.get("id"),
                        "flow_name": flow.get("name", ""),
                        "duration_ms": execution_trace.get("duration_ms"),
                    },
                )
                # Dispatch on_complete notifications (fire-and-forget)
                _notif_duration = status.get("end_time", time.time()) - status.get(
                    "start_time", time.time()
                )
                _output_preview = (
                    str(list(context.get("results", {}).values())[-1].get("output", ""))
                    if context.get("results")
                    else ""
                )
                asyncio.ensure_future(
                    notification_service.dispatch(
                        event="on_complete",
                        flow_id=flow.get("id", ""),
                        flow_name=flow.get("name", ""),
                        run_id=run_id,
                        status="success",
                        duration_ms=_notif_duration * 1000,
                        output_preview=_output_preview,
                    )
                )
                activity_feed_store.record(
                    flow.get("id", ""),
                    actor="system",
                    action="run_completed",
                    detail=f"Run {run_id} completed successfully.",
                )
                sse_event_bus.publish_sync(
                    run_id,
                    {
                        "event": "execution_complete",
                        "run_id": run_id,
                        "status": "success",
                        "duration_ms": execution_trace.get("duration_ms"),
                    },
                )

        except asyncio.CancelledError:
            # Task cancelled during post-completion broadcast (e.g. TestClient teardown).
            # Status is already saved to DB — safe to absorb.
            logger.debug(
                "_execute_flow_async %s: cancelled during post-completion broadcast",
                run_id,
            )
        except Exception as e:
            logger.error(f"Error executing workflow: {e}")
            end_time = time.time()
            # Update execution dashboard (best-effort)
            try:
                execution_dashboard_store.update_status(
                    run_id,
                    "error",
                    completed_nodes=len(memory_completed_applets),
                )
            except Exception as _dash_exc:
                logger.warning("Execution dashboard update (error) failed: %s", _dash_exc)
            _append_trace_error(
                {
                    "code": NodeErrorCode.UNKNOWN_ERROR,
                    "message": str(e),
                    "type": type(e).__name__,
                }
            )
            _finalize_execution_trace(execution_trace, "error", end_time)
            _ensure_trace_in_context_results()
            if status and isinstance(status, dict):
                status["status"] = "error"
                status["error"] = f"Workflow execution error: {str(e)}"
                status["end_time"] = end_time
                status["results"] = context.get("results", {})
                await workflow_run_repo.save(status)
                broadcast_data = status.copy()
                broadcast_data["completed_applets"] = memory_completed_applets
                await broadcast_status_fn(broadcast_data)
            else:
                await broadcast_status_fn(
                    {
                        "run_id": run_id,
                        "status": "error",
                        "error": f"Workflow execution error: {str(e)}",
                        "completed_applets": memory_completed_applets,
                    }
                )
            await emit_event(
                "template_failed",
                {
                    "run_id": run_id,
                    "flow_id": flow.get("id"),
                    "flow_name": flow.get("name", ""),
                    "error": str(e),
                },
            )
            # Dispatch on_failure notifications (fire-and-forget)
            asyncio.ensure_future(
                notification_service.dispatch(
                    event="on_failure",
                    flow_id=flow.get("id", ""),
                    flow_name=flow.get("name", ""),
                    run_id=run_id,
                    status="error",
                    duration_ms=None,
                    output_preview=str(e)[:200],
                )
            )
            activity_feed_store.record(
                flow.get("id", ""),
                actor="system",
                action="run_failed",
                detail=f"Run {run_id} failed: {str(e)[:200]}",
            )
            sse_event_bus.publish_sync(
                run_id,
                {
                    "event": "execution_complete",
                    "run_id": run_id,
                    "status": "error",
                    "error": str(e)[:500],
                },
            )


# ============================================================
# API Routes (v1)
# ============================================================

v1 = APIRouter(prefix="/api/v1", tags=["v1"])

# Re-export symbols that tests import directly from main.py
# These were moved to helpers.py / request_models.py during M-1 decomposition.
from apps.orchestrator.helpers import (  # noqa: E402
    _diff_flow_snapshots,
    _estimate_node_cost,
    _extract_trace_from_run,
    _finalize_execution_trace,
    _new_execution_trace,
    _seed_marketplace_listings,
    _trace_value,
)
from apps.orchestrator.request_models import (  # noqa: E402
    DynamicPluginApplet,
)
from apps.orchestrator.routers import (
    admin as admin_router,
)

# ============================================================
# Import sub-routers (M-1 decomposition)
# ============================================================
from apps.orchestrator.routers import (
    auth as auth_router,
)
from apps.orchestrator.routers import (
    collaboration as collaboration_router,
)
from apps.orchestrator.routers import (
    execution as execution_router,
)
from apps.orchestrator.routers import (
    flow_config as flow_config_router,
)
from apps.orchestrator.routers import (
    flows as flows_router,
)
from apps.orchestrator.routers import (
    marketplace as marketplace_router,
)
from apps.orchestrator.routers import (
    monitoring as monitoring_router,
)
from apps.orchestrator.routers import (
    webhooks as webhooks_router,
)

v1.include_router(auth_router.router)
v1.include_router(monitoring_router.router)
v1.include_router(marketplace_router.router)
v1.include_router(webhooks_router.router)
v1.include_router(admin_router.router)
v1.include_router(collaboration_router.router)
v1.include_router(execution_router.router)
v1.include_router(flows_router.router)
v1.include_router(flow_config_router.router)

# Populate Orchestrator and applet_registry in each router module.
# These are set here (not at router import time) to avoid circular imports.
_ROUTER_MODULES = [
    auth_router,
    monitoring_router,
    marketplace_router,
    webhooks_router,
    admin_router,
    collaboration_router,
    execution_router,
    flows_router,
    flow_config_router,
]
for _router_mod in _ROUTER_MODULES:
    _router_mod.Orchestrator = Orchestrator
    _router_mod.applet_registry = applet_registry

# Propagate shared instances to the routers that need them
webhooks_router.webhook_registry = webhook_registry
webhooks_router.dead_letter_queue = dead_letter_queue
webhooks_router.scheduler_registry = scheduler_registry
webhooks_router.CompoundConditionEvaluator = CompoundConditionEvaluator
webhooks_router.webhook_trigger_registry = webhook_trigger_registry

admin_router.emit_event = emit_event

flows_router.flow_version_registry = flow_version_registry
flow_config_router.flow_version_registry = flow_version_registry

# Also populate Orchestrator in helpers module (used by helper functions)
import apps.orchestrator.helpers as _helpers_mod  # noqa: E402

_helpers_mod.Orchestrator = Orchestrator

# Include versioned router
app.include_router(v1)


# ============================================================
# v2 Router (placeholder — returns 501 for all routes)
# ============================================================

v2 = APIRouter(prefix="/api/v2", tags=["v2"])


@v2.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
    include_in_schema=False,
)
async def v2_not_implemented(path: str, request: Request):
    """Placeholder for API v2 — not yet implemented."""
    return JSONResponse(
        status_code=501,
        content={
            "error": {
                "code": "NOT_IMPLEMENTED",
                "status": 501,
                "message": (
                    "API v2 is not yet available. "
                    f"Use /api/v1/ (current version: {API_VERSION_DATE})."
                ),
            }
        },
        headers={"X-API-Version": API_VERSION_DATE},
    )


app.include_router(v2)


# ============================================================
# Health Check (unversioned)
# ============================================================


def _health_payload() -> dict[str, Any]:
    uptime_seconds = max(0, int(time.time() - APP_START_TIME))
    active_connectors = sum(1 for p in LLMProviderRegistry.list_providers() if p.configured)

    # Derive aggregate status from connector dashboard statuses.
    # - healthy: all connectors healthy (or none tracked yet)
    # - degraded: any connector degraded
    # - down: any connector down or disabled
    dashboard = connector_health.all_dashboard_statuses()
    if dashboard:
        statuses = {v["dashboard_status"] for v in dashboard.values()}
        if ConnectorStatus.DOWN in statuses:
            aggregate = "down"
        elif ConnectorStatus.DEGRADED in statuses:
            aggregate = "degraded"
        else:
            aggregate = "healthy"
    else:
        aggregate = "healthy"

    return {
        "status": aggregate,
        "service": "SynApps Orchestrator API",
        "version": API_VERSION,
        "uptime": uptime_seconds,
        "active_connectors": active_connectors,
    }


@app.get("/health")
async def health():
    """Unversioned health check endpoint."""
    return _health_payload()


@app.get("/")
async def health_root():
    """Root health check endpoint."""
    return _health_payload()


# Populate monitoring_router with objects defined later in this file
monitoring_router.metrics = metrics
monitoring_router.app_config = app_config
monitoring_router.env_path = env_path
monitoring_router.flow_version_registry = flow_version_registry
monitoring_router.LLMProviderRegistry = LLMProviderRegistry
monitoring_router.ImageProviderRegistry = ImageProviderRegistry
monitoring_router.probe_connector = probe_connector
monitoring_router.probe_all_connectors = probe_all_connectors
monitoring_router._health_payload = _health_payload
monitoring_router.emit_event = emit_event
monitoring_router.WorkflowImportService = WorkflowImportService


# ============================================================
# WebSocket (versioned, structured protocol with auth & recovery)
# ============================================================


async def _ws_authenticate(websocket: WebSocket) -> dict[str, Any] | None:
    """Authenticate a WebSocket connection via JWT, API key, or legacy WS token.

    The client must send an ``auth`` message within ``WS_AUTH_TIMEOUT_SECONDS``.
    Supported ``auth`` message shapes::

        {"type": "auth", "token": "<jwt_access_token>"}
        {"type": "auth", "api_key": "<api_key>"}
        {"type": "auth", "token": "<legacy_ws_auth_token>"}

    Returns the authenticated user dict or *None* on failure (connection closed).
    """
    if await _can_use_anonymous_bootstrap():
        try:
            raw = await asyncio.wait_for(websocket.receive_text(), timeout=1.0)
            msg = json.loads(raw)
            if msg.get("type") == "auth":
                user = await _ws_try_credentials(msg)
                if user:
                    return user
        except (TimeoutError, json.JSONDecodeError, Exception):
            # Intentional: anonymous bootstrap allows connections without auth.
            # Timeout (no message sent), malformed JSON, or any transport error
            # all fall through to the anonymous user below — silence is correct.
            pass
        return {
            "id": "anonymous",
            "email": "anonymous@local",
            "is_active": True,
            "created_at": _utc_now(),
        }

    try:
        raw = await asyncio.wait_for(
            websocket.receive_text(), timeout=float(WS_AUTH_TIMEOUT_SECONDS)
        )
    except TimeoutError:
        await websocket.send_json(
            _ws_message(
                "error",
                {
                    "code": "AUTH_TIMEOUT",
                    "message": f"Send auth message within {WS_AUTH_TIMEOUT_SECONDS}s",
                },
            )
        )
        await websocket.close(code=4002, reason="Authentication timeout")
        return None
    except Exception:
        await websocket.send_json(
            _ws_message(
                "error",
                {
                    "code": "AUTH_ERROR",
                    "message": "Failed to read authentication message",
                },
            )
        )
        await websocket.close(code=4003, reason="Auth read error")
        return None

    try:
        msg = json.loads(raw)
    except json.JSONDecodeError:
        await websocket.send_json(
            _ws_message(
                "error",
                {
                    "code": "AUTH_ERROR",
                    "message": "Invalid authentication message format - expected JSON",
                },
            )
        )
        await websocket.close(code=4003, reason="Invalid auth message")
        return None

    if msg.get("type") != "auth":
        await websocket.send_json(
            _ws_message(
                "error",
                {
                    "code": "AUTH_FAILED",
                    "message": "First message must be of type 'auth'",
                },
            )
        )
        await websocket.close(code=4001, reason="Authentication failed")
        return None

    user = await _ws_try_credentials(msg)
    if not user:
        await websocket.send_json(
            _ws_message(
                "error",
                {
                    "code": "AUTH_FAILED",
                    "message": "Invalid credentials",
                },
            )
        )
        await websocket.close(code=4001, reason="Authentication failed")
        return None

    return user


async def _ws_try_credentials(msg: dict) -> dict[str, Any] | None:
    """Try to authenticate from an auth message payload."""
    token = msg.get("token", "")
    if token:
        if WS_AUTH_TOKEN and token == WS_AUTH_TOKEN:
            return {
                "id": "ws_token_user",
                "email": "ws@local",
                "is_active": True,
                "created_at": _utc_now(),
            }
        try:
            return await _authenticate_user_by_jwt(token)
        except HTTPException:
            # JWT auth failed — fall through to try API key auth below.
            # HTTPException from _authenticate_user_by_jwt carries the rejection
            # detail; we suppress it here because we have a second auth method.
            pass

    api_key = msg.get("api_key", "")
    if api_key:
        try:
            return await _authenticate_user_by_api_key(api_key)
        except HTTPException:
            # API key auth also failed — fall through to return None (rejected).
            pass

    return None


@app.websocket("/api/v1/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    # --- Authentication phase ---
    user = await _ws_authenticate(websocket)
    if user is None:
        return

    user_id: str = user.get("id", "anonymous")

    # Accept session_id and optional last_seq from query params for reconnection.
    # If last_seq is explicitly provided (including "0"), replay logic will use it.
    requested_session_id = websocket.query_params.get("session_id")
    last_seq_raw = websocket.query_params.get("last_seq")
    last_seq: int | None = None
    if last_seq_raw is not None:
        try:
            last_seq = int(last_seq_raw)
        except (ValueError, TypeError):
            last_seq = 0

    # --- Session creation / resumption ---
    session, reconnected = ws_manager.create_session(
        user_id=user_id,
        websocket=websocket,
        session_id=requested_session_id,
    )
    session_id = session.session_id
    if websocket not in connected_clients:
        connected_clients.append(websocket)

    logger.info(
        f"WebSocket client connected (session={session_id}, "
        f"user={user_id}, reconnected={reconnected}). "
        f"Total clients: {len(ws_manager.connected_websockets)}"
    )

    await websocket.send_json(
        _ws_message(
            "auth.result",
            {
                "authenticated": True,
                "session_id": session_id,
                "user_id": user_id,
                "reconnected": reconnected,
                "server_seq": ws_manager.current_seq,
            },
        )
    )

    # --- Replay missed messages on reconnect ---
    if reconnected and last_seq is not None:
        missed = ws_manager.get_missed_messages(last_seq)
        if missed:
            await websocket.send_json(
                _ws_message(
                    "replay.start",
                    {
                        "count": len(missed),
                        "from_seq": last_seq + 1,
                        "to_seq": missed[-1].get("_seq", 0),
                    },
                )
            )
            for m in missed:
                try:
                    await websocket.send_json(m)
                except Exception:
                    break
            await websocket.send_json(
                _ws_message(
                    "replay.end",
                    {
                        "count": len(missed),
                    },
                )
            )

    # --- Server heartbeat task ---
    async def _heartbeat():
        try:
            while True:
                await asyncio.sleep(WS_HEARTBEAT_INTERVAL)
                try:
                    await websocket.send_json(
                        _ws_message(
                            "heartbeat",
                            {
                                "server_seq": ws_manager.current_seq,
                            },
                        )
                    )
                    session.last_active = time.time()
                except Exception:
                    break
        except asyncio.CancelledError:
            pass

    heartbeat_task = asyncio.create_task(_heartbeat())

    # --- Message loop ---
    try:
        while True:
            raw = await websocket.receive_text()
            session.last_active = time.time()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json(
                    _ws_message(
                        "error",
                        {
                            "code": "INVALID_MESSAGE",
                            "message": "Message must be valid JSON",
                        },
                    )
                )
                continue

            msg_type = msg.get("type", "")
            msg_id = msg.get("id")

            if msg_type == "ping":
                await websocket.send_json(_ws_message("pong", ref_id=msg_id))

            elif msg_type == "subscribe":
                channel = msg.get("data", {}).get("channel", "")
                if channel:
                    session.subscriptions.add(channel)
                await websocket.send_json(
                    _ws_message(
                        "subscribe.ack",
                        {"channel": channel},
                        ref_id=msg_id,
                    )
                )

            elif msg_type == "unsubscribe":
                channel = msg.get("data", {}).get("channel", "")
                session.subscriptions.discard(channel)
                await websocket.send_json(
                    _ws_message(
                        "unsubscribe.ack",
                        {"channel": channel},
                        ref_id=msg_id,
                    )
                )

            elif msg_type == "get_state":
                await websocket.send_json(
                    _ws_message(
                        "state",
                        {
                            "session_id": session_id,
                            "user_id": user_id,
                            "subscriptions": sorted(session.subscriptions),
                            "server_seq": ws_manager.current_seq,
                            "connected_at": session.connected_at,
                        },
                        ref_id=msg_id,
                    )
                )

            else:
                await websocket.send_json(
                    _ws_message(
                        "error",
                        {
                            "code": "UNKNOWN_MESSAGE_TYPE",
                            "message": f"Unknown message type: {msg_type}",
                        },
                        ref_id=msg_id,
                    )
                )

    except WebSocketDisconnect:
        logger.info(f"Client disconnected (session={session_id})")
    except Exception as e:
        logger.error(f"WebSocket error (session={session_id}): {e}")
    finally:
        heartbeat_task.cancel()
        ws_manager.remove_session(websocket)
        if websocket in connected_clients:
            connected_clients.remove(websocket)
        logger.info(
            f"WebSocket session {session_id} cleaned up. "
            f"Remaining clients: {len(ws_manager.connected_websockets)}"
        )


# For direct execution
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
