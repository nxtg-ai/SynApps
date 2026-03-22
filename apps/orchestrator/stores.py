"""
stores.py — In-memory Store, Registry, Tracker, and helper classes for SynApps.

Extracted from main.py (M-1 Step 1).  This module is intentionally self-contained:
it imports only from the Python standard library and direct third-party dependencies
(fastapi, cryptography, httpx).  It never imports from apps.orchestrator.*.
main.py imports everything back via `from apps.orchestrator.stores import ...`.
"""
import asyncio
import hashlib
import hmac
import json
import logging
import math
import os
import re
import secrets
import threading
import time
import uuid
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

import httpx
from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger("orchestrator")


# ---------------------------------------------------------------------------
# Module-level constants and helpers used by store classes
# ---------------------------------------------------------------------------

HEALTH_WINDOW_SECONDS = 300  # 5 minutes

_SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def _parse_semver(v: str) -> tuple | None:
    """Parse a semver string into (major, minor, patch) or None."""
    m = _SEMVER_RE.match(v)
    return (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


def _bump_patch(semver: str) -> str:
    """Increment the patch component of a semver string."""
    parts = _parse_semver(semver)
    if not parts:
        return "1.0.0"
    return f"{parts[0]}.{parts[1]}.{parts[2] + 1}"

FLOW_PRIORITY_VALUES = ("critical", "high", "medium", "low")

_CRON_FIELD = r"(\*(?:/[0-9]+)?|[0-9,\-/]+)"
_CRON_PATTERN = re.compile(
    rf"^{_CRON_FIELD}\s+{_CRON_FIELD}\s+{_CRON_FIELD}\s+{_CRON_FIELD}\s+{_CRON_FIELD}$"
)

_URL_PATTERN = re.compile(r"^https?://\S+$")

_TIMEOUT_MIN = 1

_TIMEOUT_MAX = 3600

_RETRY_MAX_RETRIES_MAX = 10

_RETRY_DELAY_MAX = 300  # seconds

_RETRY_BACKOFF_MAX = 10.0

_CONCURRENCY_MIN = 1

_CONCURRENCY_MAX = 100

_INPUT_SCHEMA_MAX_BYTES = 16_384  # 16 KB

_OUTPUT_SCHEMA_MAX_BYTES = 16_384


_SENSITIVE_HEADERS = frozenset(
    {
        "authorization",
        "x-api-key",
        "cookie",
        "set-cookie",
        "x-csrf-token",
        "proxy-authorization",
    }
)

_FAILED_REQUEST_CAP = int(os.environ.get("FAILED_REQUEST_CAP", "100"))

def _month_start_ts() -> float:
    """Return Unix timestamp for midnight UTC on the 1st of the current month."""
    now = datetime.now(UTC)
    return datetime(now.year, now.month, 1, tzinfo=UTC).timestamp()

def _next_month_start_ts() -> float:
    """Return Unix timestamp for midnight UTC on the 1st of the **next** month."""
    now = datetime.now(UTC)
    if now.month == 12:
        return datetime(now.year + 1, 1, 1, tzinfo=UTC).timestamp()
    return datetime(now.year, now.month + 1, 1, tzinfo=UTC).timestamp()


class FailedRequestStore:
    """Thread-safe LRU store for failed HTTP requests.

    Stores the last *capacity* failed requests (status >= 400) with full
    request/response data.  When the store is full the oldest entry is evicted.
    """

    def __init__(self, capacity: int = 100) -> None:
        self._capacity = max(1, capacity)
        self._lock = threading.Lock()
        self._entries: dict[str, dict[str, Any]] = {}
        self._order: list[str] = []  # oldest first

    @property
    def capacity(self) -> int:
        return self._capacity

    def add(self, entry: dict[str, Any]) -> None:
        """Add a failed request entry.  Evicts oldest if at capacity."""
        rid = entry.get("request_id", "")
        if not rid:
            return
        with self._lock:
            if rid in self._entries:
                return  # no dupes
            if len(self._order) >= self._capacity:
                evict = self._order.pop(0)
                self._entries.pop(evict, None)
            self._entries[rid] = entry
            self._order.append(rid)

    def get(self, request_id: str) -> dict[str, Any] | None:
        with self._lock:
            return self._entries.get(request_id)

    def list_recent(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return most-recent failed requests (newest first)."""
        with self._lock:
            if limit <= 0:
                return []
            ids = self._order[-limit:]
            return [self._entries[rid] for rid in reversed(ids) if rid in self._entries]

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
            self._order.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._order)

    @staticmethod
    def redact_headers(headers: dict[str, str]) -> dict[str, str]:
        """Return a copy of *headers* with sensitive values replaced by '[REDACTED]'."""
        return {
            k: ("[REDACTED]" if k.lower() in _SENSITIVE_HEADERS else v) for k, v in headers.items()
        }
failed_request_store = FailedRequestStore(capacity=_FAILED_REQUEST_CAP)


class ConsumerUsageTracker:
    """Thread-safe in-memory per-key usage tracker with monthly quota support.

    Tracks per-key:
    - Requests today / this week / this month
    - Error count for current month
    - Per-endpoint request counts
    - Per-hour histogram (0-23) for current day
    - Monthly quota + enforcement

    Usage data resets on the 1st of each month at midnight UTC.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # key_id -> usage record
        self._usage: dict[str, dict[str, Any]] = {}
        # key_id -> monthly request quota (None = unlimited)
        self._quotas: dict[str, int | None] = {}
        self._month_start = _month_start_ts()

    def _ensure_key(self, key_id: str) -> dict[str, Any]:
        """Return (or create) the usage record for *key_id*.  Caller holds lock."""
        self._maybe_reset_month()
        if key_id not in self._usage:
            self._usage[key_id] = self._blank_record()
        return self._usage[key_id]

    @staticmethod
    def _blank_record() -> dict[str, Any]:
        now = datetime.now(UTC)
        return {
            "month": now.month,
            "year": now.year,
            "requests_month": 0,
            "requests_week": 0,
            "requests_today": 0,
            "errors_month": 0,
            "bandwidth_bytes": 0,
            "by_endpoint": {},  # path -> count
            "by_hour": {},  # "HH" -> count (today only)
            "last_request_at": None,
            "_day": now.day,
            "_iso_week": now.isocalendar()[1],
        }

    @staticmethod
    def _get_month_start_ts() -> float:
        """Return _month_start_ts(), resolved through main's namespace so that
        tests patching ``apps.orchestrator.main._month_start_ts`` still work."""
        try:
            import apps.orchestrator.main as _main  # noqa: PLC0415 — lazy import

            return _main._month_start_ts()
        except Exception:  # pragma: no cover — fallback before main is loaded
            return _month_start_ts()

    @staticmethod
    def _get_next_month_start_ts() -> float:
        """Return _next_month_start_ts() resolved through main's namespace."""
        try:
            import apps.orchestrator.main as _main  # noqa: PLC0415 — lazy import

            return _main._next_month_start_ts()
        except Exception:  # pragma: no cover — fallback before main is loaded
            return _next_month_start_ts()

    def _maybe_reset_month(self) -> None:
        """Check if the month boundary has been crossed and reset if so."""
        current_start = self._get_month_start_ts()
        if current_start > self._month_start:
            self._month_start = current_start
            self._usage.clear()  # full reset

    def _maybe_roll_day(self, rec: dict[str, Any]) -> None:
        """Reset daily / weekly counters if the day or week changed."""
        now = datetime.now(UTC)
        if rec["_day"] != now.day:
            rec["requests_today"] = 0
            rec["by_hour"] = {}
            rec["_day"] = now.day
        iso_week = now.isocalendar()[1]
        if rec["_iso_week"] != iso_week:
            rec["requests_week"] = 0
            rec["_iso_week"] = iso_week

    def record(
        self,
        key_id: str,
        path: str,
        status_code: int,
        response_size: int = 0,
    ) -> None:
        """Record a request for *key_id*."""
        now = datetime.now(UTC)
        with self._lock:
            rec = self._ensure_key(key_id)
            self._maybe_roll_day(rec)
            rec["requests_month"] += 1
            rec["requests_week"] += 1
            rec["requests_today"] += 1
            rec["bandwidth_bytes"] += response_size
            if status_code >= 400:
                rec["errors_month"] += 1
            # Per-endpoint
            rec["by_endpoint"][path] = rec["by_endpoint"].get(path, 0) + 1
            # Per-hour histogram
            hour_key = f"{now.hour:02d}"
            rec["by_hour"][hour_key] = rec["by_hour"].get(hour_key, 0) + 1
            rec["last_request_at"] = now.timestamp()

    def set_quota(self, key_id: str, monthly_limit: int | None) -> None:
        """Set or clear the monthly request quota for *key_id*."""
        with self._lock:
            self._quotas[key_id] = monthly_limit

    def get_quota(self, key_id: str) -> int | None:
        """Return the monthly quota for *key_id* (None = unlimited)."""
        with self._lock:
            return self._quotas.get(key_id)

    def check_quota(self, key_id: str) -> dict[str, Any]:
        """Return quota status for *key_id*.

        Returns dict with:
        - allowed: bool — True if the request should proceed
        - quota: int | None — monthly limit
        - used: int — requests this month
        - remaining: int | None — requests left (None if unlimited)
        - pct: float — percentage consumed (0.0 if unlimited)
        - warning: bool — True if >= 80% consumed
        - retry_after: int — seconds until next month reset (only meaningful if blocked)
        """
        with self._lock:
            self._maybe_reset_month()
            quota = self._quotas.get(key_id)
            rec = self._usage.get(key_id)
            used = rec["requests_month"] if rec else 0

        if quota is None:
            return {
                "allowed": True,
                "quota": None,
                "used": used,
                "remaining": None,
                "pct": 0.0,
                "warning": False,
                "retry_after": 0,
            }

        pct = (used / quota * 100) if quota > 0 else 0.0
        remaining = max(0, quota - used)
        allowed = used < quota
        retry_after = max(0, int(self._get_next_month_start_ts() - time.time())) if not allowed else 0

        return {
            "allowed": allowed,
            "quota": quota,
            "used": used,
            "remaining": remaining,
            "pct": round(pct, 2),
            "warning": pct >= 80.0 and allowed,
            "retry_after": retry_after,
        }

    def get_usage(self, key_id: str) -> dict[str, Any] | None:
        """Return the usage record for a single key."""
        with self._lock:
            self._maybe_reset_month()
            rec = self._usage.get(key_id)
            if rec is None:
                return None
            self._maybe_roll_day(rec)
            quota = self._quotas.get(key_id)
            return {**rec, "quota": quota, "key_id": key_id}

    def all_usage(self) -> list[dict[str, Any]]:
        """Return usage summaries for all tracked keys."""
        with self._lock:
            self._maybe_reset_month()
            result = []
            for key_id, rec in self._usage.items():
                self._maybe_roll_day(rec)
                quota = self._quotas.get(key_id)
                pct = (rec["requests_month"] / quota * 100) if quota else 0.0
                result.append(
                    {
                        "key_id": key_id,
                        "requests_today": rec["requests_today"],
                        "requests_week": rec["requests_week"],
                        "requests_month": rec["requests_month"],
                        "errors_month": rec["errors_month"],
                        "bandwidth_bytes": rec["bandwidth_bytes"],
                        "error_rate_pct": round(
                            rec["errors_month"] / rec["requests_month"] * 100, 2
                        )
                        if rec["requests_month"] > 0
                        else 0.0,
                        "last_request_at": rec["last_request_at"],
                        "quota": quota,
                        "quota_pct": round(pct, 2),
                    }
                )
            return result

    def all_quotas(self) -> list[dict[str, Any]]:
        """Return quota status for all keys that have a quota set."""
        with self._lock:
            self._maybe_reset_month()
            result = []
            for key_id, quota in self._quotas.items():
                rec = self._usage.get(key_id)
                used = rec["requests_month"] if rec else 0
                pct = (used / quota * 100) if quota and quota > 0 else 0.0
                result.append(
                    {
                        "key_id": key_id,
                        "quota": quota,
                        "used": used,
                        "remaining": max(0, (quota or 0) - used),
                        "pct": round(pct, 2),
                        "status": "blocked"
                        if quota and used >= quota
                        else "warning"
                        if pct >= 80.0
                        else "ok",
                    }
                )
            return result

    def clear(self) -> None:
        with self._lock:
            self._usage.clear()
            self._quotas.clear()
            self._month_start = self._get_month_start_ts()
usage_tracker = ConsumerUsageTracker()


class ExecutionQuotaStore:
    """Thread-safe per-user execution rate limiter and monthly quota tracker.

    Tracks:
    - Executions this rolling hour (reset every 60 min)
    - Executions this calendar month (reset on month rollover)

    Default limits:
    - 60 executions/hour
    - 1 000 executions/month
    """

    DEFAULT_HOURLY_LIMIT = 60
    DEFAULT_MONTHLY_LIMIT = 1000

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # user_email -> {"hourly": int, "monthly": int, "hour_start": float, "month_key": str}
        self._records: dict[str, dict[str, Any]] = {}
        # user_email -> {"hourly_limit": int | None, "monthly_limit": int | None}
        self._limits: dict[str, dict[str, int | None]] = {}

    def _month_key(self) -> str:
        now = datetime.now(UTC)
        return f"{now.year}-{now.month:02d}"

    def _ensure(self, user_email: str) -> dict[str, Any]:
        """Return (creating if needed) the record for user_email. Caller holds lock."""
        now_ts = time.time()
        mk = self._month_key()
        if user_email not in self._records:
            self._records[user_email] = {
                "hourly": 0,
                "monthly": 0,
                "hour_start": now_ts,
                "month_key": mk,
            }
        rec = self._records[user_email]
        # Roll hourly counter if > 3600s elapsed
        if now_ts - rec["hour_start"] >= 3600:
            rec["hourly"] = 0
            rec["hour_start"] = now_ts
        # Roll monthly counter if month changed
        if rec["month_key"] != mk:
            rec["monthly"] = 0
            rec["month_key"] = mk
        return rec

    def check_and_record(self, user_email: str) -> None:
        """Check quota then increment counters.

        Raises HTTPException(429) with Retry-After header if any limit is exceeded.
        """
        with self._lock:
            rec = self._ensure(user_email)
            limits = self._limits.get(user_email, {})
            hourly_limit = limits.get("hourly_limit") or self.DEFAULT_HOURLY_LIMIT
            monthly_limit = limits.get("monthly_limit") or self.DEFAULT_MONTHLY_LIMIT

            if rec["hourly"] >= hourly_limit:
                seconds_remaining = max(1, int(3600 - (time.time() - rec["hour_start"])))
                raise HTTPException(
                    status_code=429,
                    detail={
                        "error": "execution_rate_limit_exceeded",
                        "message": f"Hourly execution limit of {hourly_limit} reached.",
                        "retry_after_seconds": seconds_remaining,
                    },
                    headers={"Retry-After": str(seconds_remaining)},
                )

            if rec["monthly"] >= monthly_limit:
                raise HTTPException(
                    status_code=429,
                    detail={
                        "error": "execution_monthly_quota_exceeded",
                        "message": f"Monthly execution quota of {monthly_limit} reached.",
                        "retry_after_seconds": 86400,
                    },
                    headers={"Retry-After": "86400"},
                )

            rec["hourly"] += 1
            rec["monthly"] += 1

    def get_usage(self, user_email: str) -> dict[str, Any]:
        """Return current quota status for user_email."""
        with self._lock:
            rec = self._ensure(user_email)
            limits = self._limits.get(user_email, {})
            hourly_limit = limits.get("hourly_limit") or self.DEFAULT_HOURLY_LIMIT
            monthly_limit = limits.get("monthly_limit") or self.DEFAULT_MONTHLY_LIMIT
            now_ts = time.time()
            hourly_reset_in = max(0, int(3600 - (now_ts - rec["hour_start"])))
            return {
                "user": user_email,
                "executions_this_hour": rec["hourly"],
                "hourly_limit": hourly_limit,
                "hourly_remaining": max(0, hourly_limit - rec["hourly"]),
                "hourly_reset_in_seconds": hourly_reset_in,
                "executions_this_month": rec["monthly"],
                "monthly_limit": monthly_limit,
                "monthly_remaining": max(0, monthly_limit - rec["monthly"]),
                "month": rec["month_key"],
            }

    def set_limits(
        self,
        user_email: str,
        hourly_limit: int | None = None,
        monthly_limit: int | None = None,
    ) -> None:
        """Override default limits for user_email (admin use)."""
        with self._lock:
            self._limits.setdefault(user_email, {})
            if hourly_limit is not None:
                self._limits[user_email]["hourly_limit"] = hourly_limit
            if monthly_limit is not None:
                self._limits[user_email]["monthly_limit"] = monthly_limit

    def reset(self) -> None:
        with self._lock:
            self._records.clear()
            self._limits.clear()
execution_quota_store = ExecutionQuotaStore()


class DeprecationRegistry:
    """Registry of deprecated API endpoints with sunset dates.

    Each entry maps a (method, path) to a sunset date string (ISO-8601).
    The ``Deprecation`` and ``Sunset`` HTTP headers are attached by middleware.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # (method_upper, path) -> {"sunset": "YYYY-MM-DD", "successor": optional_path}
        self._entries: dict[tuple, dict[str, str]] = {}

    def deprecate(
        self,
        method: str,
        path: str,
        sunset: str,
        successor: str | None = None,
    ) -> None:
        """Mark an endpoint as deprecated with a sunset date."""
        with self._lock:
            entry: dict[str, str] = {"sunset": sunset}
            if successor:
                entry["successor"] = successor
            self._entries[(method.upper(), path)] = entry

    def lookup(self, method: str, path: str) -> dict[str, str] | None:
        """Return deprecation info if (method, path) is deprecated, else None."""
        with self._lock:
            return self._entries.get((method.upper(), path))

    def all_deprecated(self) -> list[dict[str, str]]:
        """Return all deprecated endpoints."""
        with self._lock:
            result = []
            for (method, path), info in self._entries.items():
                result.append({"method": method, "path": path, **info})
            return result

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
deprecation_registry = DeprecationRegistry()


class ErrorCategory(StrEnum):
    """Classification of errors to drive retry decisions."""

    TRANSIENT = "transient"  # Network blip, 500/502/503 — retry immediately
    RATE_LIMITED = "rate_limited"  # 429 — retry with backoff
    PERMANENT = "permanent"  # 401/403/404, validation — fail fast


class RetryPolicy:
    """Per-connector retry configuration.

    Attributes:
        max_retries: Maximum number of retry attempts (0 = no retries).
        base_delay: Initial delay in seconds before first retry.
        backoff_factor: Multiplier applied to delay after each retry.
        retryable_categories: Set of ErrorCategory values that are retryable.
    """

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        backoff_factor: float = 2.0,
        retryable_categories: set | None = None,
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.backoff_factor = backoff_factor
        self.retryable_categories: set = retryable_categories or {
            ErrorCategory.TRANSIENT,
            ErrorCategory.RATE_LIMITED,
        }

    def should_retry(self, category: ErrorCategory, attempt: int) -> bool:
        """Return True if we should retry given the error category and attempt number."""
        if attempt >= self.max_retries:
            return False
        return category in self.retryable_categories

    def delay_for_attempt(self, attempt: int) -> float:
        """Exponential backoff delay for the given attempt (0-indexed)."""
        return self.base_delay * (self.backoff_factor**attempt)

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_retries": self.max_retries,
            "base_delay": self.base_delay,
            "backoff_factor": self.backoff_factor,
            "retryable_categories": sorted(c.value for c in self.retryable_categories),
        }


class ConnectorError(Exception):
    """Error raised by a connector with classification metadata."""

    def __init__(
        self,
        message: str,
        category: ErrorCategory,
        connector: str = "",
        status_code: int | None = None,
        attempt: int = 0,
        max_retries: int = 0,
    ):
        super().__init__(message)
        self.category = category
        self.connector = connector
        self.status_code = status_code
        self.attempt = attempt
        self.max_retries = max_retries


class ConnectorStatus(StrEnum):
    """Health status for a connector."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"  # < 2000ms avg or < 5 errors in 5min
    DOWN = "down"  # timeout or > 5 errors in 5min
    DISABLED = "disabled"  # ≥ disable_threshold consecutive failures


class ConnectorHealthTracker:
    """Per-connector health state with auto-disable / auto-re-enable.

    After ``disable_threshold`` consecutive probe failures, a connector is
    marked DISABLED.  A single successful probe re-enables it immediately.

    Dashboard-oriented metrics (latency samples + errors) are kept in a
    rolling 5-minute window so callers can derive
    ``healthy / degraded / down`` status per the directive thresholds.
    """

    def __init__(self, disable_threshold: int = 3) -> None:
        self._lock = threading.Lock()
        self._disable_threshold = disable_threshold
        # connector name → state dict
        self._state: dict[str, dict[str, Any]] = {}

    def _ensure(self, connector: str) -> dict[str, Any]:
        if connector not in self._state:
            self._state[connector] = {
                "status": ConnectorStatus.HEALTHY,
                "consecutive_failures": 0,
                "total_probes": 0,
                "total_failures": 0,
                "last_check": None,
                "last_failure_reason": None,
                "last_success": None,
                # Rolling window data
                "latency_samples": [],  # list of (timestamp, ms)
                "error_samples": [],  # list of timestamps
            }
        return self._state[connector]

    def _prune_window(self, s: dict[str, Any], now: float) -> None:
        """Drop samples older than HEALTH_WINDOW_SECONDS."""
        cutoff = now - HEALTH_WINDOW_SECONDS
        s["latency_samples"] = [(ts, ms) for ts, ms in s["latency_samples"] if ts >= cutoff]
        s["error_samples"] = [ts for ts in s["error_samples"] if ts >= cutoff]

    def record_success(self, connector: str, latency_ms: float = 0.0) -> None:
        """Record a successful probe — resets failure count and re-enables."""
        with self._lock:
            s = self._ensure(connector)
            now = time.time()
            s["consecutive_failures"] = 0
            s["status"] = ConnectorStatus.HEALTHY
            s["total_probes"] += 1
            s["last_check"] = now
            s["last_failure_reason"] = None
            s["last_success"] = now
            if latency_ms > 0:
                s["latency_samples"].append((now, latency_ms))
            self._prune_window(s, now)

    def record_failure(self, connector: str, reason: str = "", latency_ms: float = 0.0) -> None:
        """Record a failed probe — increments failure count, may disable."""
        with self._lock:
            s = self._ensure(connector)
            now = time.time()
            s["consecutive_failures"] += 1
            s["total_probes"] += 1
            s["total_failures"] += 1
            s["last_check"] = now
            s["last_failure_reason"] = reason
            s["error_samples"].append(now)
            if latency_ms > 0:
                s["latency_samples"].append((now, latency_ms))
            self._prune_window(s, now)
            if s["consecutive_failures"] >= self._disable_threshold:
                s["status"] = ConnectorStatus.DISABLED
            elif s["consecutive_failures"] >= 1:
                s["status"] = ConnectorStatus.DEGRADED

    def get_status(self, connector: str) -> dict[str, Any]:
        """Get the current health state for a connector."""
        with self._lock:
            s = self._ensure(connector)
            return dict(s)

    def get_dashboard_status(self, connector: str) -> dict[str, Any]:
        """Return dashboard-oriented status with windowed metrics.

        Derives a ``dashboard_status`` according to the directive thresholds:
        - *healthy*:  avg latency < 500ms AND 0 errors in last 5min
        - *degraded*: avg latency < 2000ms OR < 5 errors in last 5min
        - *down*:     timeout OR ≥ 5 errors in last 5min
        """
        with self._lock:
            s = self._ensure(connector)
            now = time.time()
            self._prune_window(s, now)

            latencies = [ms for _, ms in s["latency_samples"]]
            avg_latency = (sum(latencies) / len(latencies)) if latencies else 0.0
            error_count = len(s["error_samples"])

            # Determine dashboard status
            if s["status"] == ConnectorStatus.DISABLED:
                dashboard_status = ConnectorStatus.DOWN
            elif error_count >= 5 or avg_latency >= 2000:
                dashboard_status = ConnectorStatus.DOWN
            elif error_count >= 1 or avg_latency >= 500:
                dashboard_status = ConnectorStatus.DEGRADED
            else:
                dashboard_status = ConnectorStatus.HEALTHY

            return {
                "status": s["status"],
                "dashboard_status": dashboard_status,
                "consecutive_failures": s["consecutive_failures"],
                "total_probes": s["total_probes"],
                "total_failures": s["total_failures"],
                "last_check": s["last_check"],
                "last_success": s["last_success"],
                "last_failure_reason": s["last_failure_reason"],
                "avg_latency_ms": round(avg_latency, 2),
                "error_count_5m": error_count,
                "sample_count_5m": len(latencies),
            }

    def is_disabled(self, connector: str) -> bool:
        with self._lock:
            s = self._ensure(connector)
            return s["status"] == ConnectorStatus.DISABLED

    def all_statuses(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            return {name: dict(s) for name, s in self._state.items()}

    def all_dashboard_statuses(self) -> dict[str, dict[str, Any]]:
        """Return dashboard-oriented statuses for every tracked connector."""
        result: dict[str, dict[str, Any]] = {}
        for name in list(self._state.keys()):
            result[name] = self.get_dashboard_status(name)
        return result

    def reset(self) -> None:
        with self._lock:
            self._state.clear()

    @property
    def disable_threshold(self) -> int:
        return self._disable_threshold
connector_health = ConnectorHealthTracker(disable_threshold=3)


class WebhookTriggerRegistry:
    """In-memory registry for inbound webhook trigger endpoints (N-19).

    Each trigger is tied to a specific flow.  When the unique ``/receive``
    URL is called with a POST, the flow is started with the request body as
    its input.  An optional HMAC-SHA256 secret can be configured to verify
    that the request originates from a trusted sender.
    """

    def __init__(self, encrypt_fn=None, decrypt_fn=None) -> None:
        self._lock = threading.Lock()
        # trigger_id -> stored record (raw secret never stored; only encrypted)
        self._triggers: dict[str, dict[str, Any]] = {}
        # Optional Fernet helpers (injected after app startup)
        self._encrypt: Any = encrypt_fn or (lambda s: s)
        self._decrypt: Any = decrypt_fn or (lambda s: s)

    # ------------------------------------------------------------------
    # CRUD helpers
    # ------------------------------------------------------------------

    def register(self, flow_id: str, secret: str | None = None) -> dict[str, Any]:
        """Register a new inbound webhook trigger for *flow_id*."""
        trigger_id = str(uuid.uuid4())
        enc_secret: str | None = None
        if secret:
            enc_secret = self._encrypt(secret)
        record: dict[str, Any] = {
            "id": trigger_id,
            "flow_id": flow_id,
            "_enc_secret": enc_secret,
            "created_at": datetime.now(UTC).isoformat(),
        }
        with self._lock:
            self._triggers[trigger_id] = record
        return self._public_view(record)

    def list_triggers(self, flow_id: str | None = None) -> list[dict[str, Any]]:
        """Return all triggers, optionally filtered by *flow_id*."""
        with self._lock:
            records = list(self._triggers.values())
        if flow_id:
            records = [r for r in records if r["flow_id"] == flow_id]
        return [self._public_view(r) for r in records]

    def get(self, trigger_id: str) -> dict[str, Any] | None:
        """Return a single trigger by ID, or None if not found."""
        with self._lock:
            record = self._triggers.get(trigger_id)
        return self._public_view(record) if record else None

    def delete(self, trigger_id: str) -> bool:
        """Remove a trigger.  Returns True if it existed."""
        with self._lock:
            return self._triggers.pop(trigger_id, None) is not None

    def reset(self) -> None:
        """Clear all registered triggers (test teardown helper)."""
        with self._lock:
            self._triggers.clear()

    # ------------------------------------------------------------------
    # Signature verification
    # ------------------------------------------------------------------

    def verify_signature(self, trigger_id: str, body_bytes: bytes, sig_header: str | None) -> bool:
        """Verify the HMAC-SHA256 ``X-Webhook-Signature`` header.

        Returns True if:
        - the trigger has no secret configured (no verification required), OR
        - the header matches ``sha256=<hex_digest>`` computed with the stored secret.

        Returns False on any mismatch or if a secret is required but no header
        was supplied.
        """
        with self._lock:
            record = self._triggers.get(trigger_id)
        if not record:
            return False
        enc_secret = record.get("_enc_secret")
        if enc_secret is None:
            # No secret configured — accept all
            return True
        if not sig_header:
            return False
        plain_secret = self._decrypt(enc_secret)
        if not plain_secret:
            return False
        expected = (
            "sha256="
            + hmac.new(plain_secret.encode("utf-8"), body_bytes, hashlib.sha256).hexdigest()
        )
        return hmac.compare_digest(expected, sig_header)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _public_view(record: dict[str, Any]) -> dict[str, Any]:
        """Return a copy of *record* with the encrypted secret stripped."""
        return {k: v for k, v in record.items() if k != "_enc_secret"}
webhook_trigger_registry = WebhookTriggerRegistry()


class SchedulerService:
    """Async background service that fires scheduled workflows on their cron cadence.

    Tick interval: 30 seconds (configurable via ``SCHEDULER_TICK_SECONDS`` env var).
    Lightweight: does not use a third-party scheduler framework — just asyncio.sleep.
    """

    _task: asyncio.Task | None = None
    _running: bool = False
    TICK_SECONDS: float = float(os.environ.get("SCHEDULER_TICK_SECONDS", "30"))

    @classmethod
    async def start(cls) -> None:
        """Start the background tick loop."""
        cls._running = True
        cls._task = asyncio.create_task(cls._run_loop(), name="scheduler-service")
        logger.info("SchedulerService started (tick=%.0fs)", cls.TICK_SECONDS)

    @classmethod
    async def stop(cls) -> None:
        """Stop the background tick loop gracefully."""
        cls._running = False
        if cls._task and not cls._task.done():
            cls._task.cancel()
            await asyncio.gather(cls._task, return_exceptions=True)
            cls._task = None
        logger.info("SchedulerService stopped")

    @classmethod
    async def _run_loop(cls) -> None:
        while cls._running:
            await asyncio.sleep(cls.TICK_SECONDS)
            if cls._running:
                await cls._tick()

    @classmethod
    async def _tick(cls) -> None:
        """Fire any schedules whose next_run time has arrived."""
        from datetime import UTC  # noqa: PLC0415
        from datetime import datetime as _dt

        # Lazy imports to avoid circular dependency between stores.py and main.py
        from apps.orchestrator.main import (  # noqa: PLC0415
            RunFlowRequest,
            _compute_next_run,
            _run_flow_impl,
            scheduler_registry,
        )

        due = scheduler_registry.get_due()
        for schedule in due:
            schedule_id = schedule["id"]
            flow_id = schedule["flow_id"]
            try:
                run_body = RunFlowRequest(
                    input={
                        "trigger": "scheduler",
                        "schedule_id": schedule_id,
                        "schedule_name": schedule.get("name"),
                    }
                )
                await _run_flow_impl(flow_id, run_body)
                scheduler_registry.update(
                    schedule_id,
                    last_run=_dt.now(UTC).isoformat(),
                    next_run=_compute_next_run(schedule["cron_expr"]),
                    run_count=schedule.get("run_count", 0) + 1,
                )
                logger.info(
                    "SchedulerService: fired schedule %s for flow %s",
                    schedule_id,
                    flow_id,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "SchedulerService: failed to fire schedule %s: %s",
                    schedule_id,
                    exc,
                )
                # Advance next_run so we don't hammer a broken flow
                try:
                    scheduler_registry.update(
                        schedule_id,
                        next_run=_compute_next_run(schedule["cron_expr"]),
                    )
                except ValueError:
                    pass  # OMIT JUSTIFIED: cron_expr already validated at creation; failure here is unreachable


class TaskQueue:
    """In-memory async task tracker for background workflow execution."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tasks: dict[str, dict[str, Any]] = {}

    def create(self, template_id: str, flow_name: str) -> str:
        task_id = str(uuid.uuid4())
        with self._lock:
            self._tasks[task_id] = {
                "task_id": task_id,
                "template_id": template_id,
                "flow_name": flow_name,
                "status": "pending",
                "progress_pct": 0,
                "run_id": None,
                "result": None,
                "error": None,
                "created_at": time.time(),
                "started_at": None,
                "completed_at": None,
            }
        return task_id

    def get(self, task_id: str) -> dict[str, Any] | None:
        with self._lock:
            t = self._tasks.get(task_id)
            return dict(t) if t else None

    def list_tasks(self, status: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            tasks = list(self._tasks.values())
        if status:
            tasks = [t for t in tasks if t["status"] == status]
        tasks.sort(key=lambda t: t["created_at"], reverse=True)
        return [dict(t) for t in tasks]

    def update(self, task_id: str, **fields: Any) -> None:
        with self._lock:
            t = self._tasks.get(task_id)
            if t:
                t.update(fields)

    def reset(self) -> None:
        with self._lock:
            self._tasks.clear()
task_queue = TaskQueue()


class AdminKeyRegistry:
    """In-memory admin API key store, protected by master key."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._keys: dict[str, dict[str, Any]] = {}  # id -> key data

    def create(
        self,
        name: str,
        scopes: list[str] | None = None,
        rate_limit: int | None = None,
    ) -> dict[str, Any]:
        key_id = str(uuid.uuid4())
        plain_key = f"sk-{uuid.uuid4().hex}"
        key_prefix = plain_key[:12]
        entry = {
            "id": key_id,
            "name": name,
            "key_prefix": key_prefix,
            "scopes": sorted(set(scopes or ["read", "write"])),
            "rate_limit": rate_limit,  # None = use default tier limit
            "is_active": True,
            "created_at": time.time(),
            "last_used_at": None,
        }
        with self._lock:
            self._keys[key_id] = {**entry, "_plain_key": plain_key}
        return {**entry, "api_key": plain_key}

    def get(self, key_id: str) -> dict[str, Any] | None:
        with self._lock:
            k = self._keys.get(key_id)
            if not k:
                return None
            return {kk: vv for kk, vv in k.items() if kk != "_plain_key"}

    def list_keys(self) -> list[dict[str, Any]]:
        with self._lock:
            return [
                {kk: vv for kk, vv in k.items() if kk != "_plain_key"} for k in self._keys.values()
            ]

    def revoke(self, key_id: str) -> bool:
        with self._lock:
            k = self._keys.get(key_id)
            if not k:
                return False
            k["is_active"] = False
            return True

    def delete(self, key_id: str) -> bool:
        with self._lock:
            return self._keys.pop(key_id, None) is not None

    def validate_key(self, plain_key: str) -> dict[str, Any] | None:
        """Validate a plain API key and return its data if active."""
        with self._lock:
            for k in self._keys.values():
                if k.get("_plain_key") == plain_key and k.get("is_active"):
                    k["last_used_at"] = time.time()
                    return {kk: vv for kk, vv in k.items() if kk != "_plain_key"}
        return None

    def reset(self) -> None:
        with self._lock:
            self._keys.clear()
admin_key_registry = AdminKeyRegistry()


class SSEEventBus:
    """Thread-safe per-run event bus for Server-Sent Events streaming.

    Subscribers call :meth:`subscribe` to obtain an :class:`asyncio.Queue`
    that receives events as they are published.  ``publish_sync`` is safe to
    call from synchronous code running inside an active asyncio event loop
    (e.g. from within an async coroutine via a sync helper).
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subscribers: dict[str, list[asyncio.Queue]] = {}

    def subscribe(self, run_id: str) -> asyncio.Queue:
        """Return a new queue that will receive all future events for *run_id*."""
        q: asyncio.Queue = asyncio.Queue(maxsize=1000)
        with self._lock:
            self._subscribers.setdefault(run_id, []).append(q)
        return q

    def unsubscribe(self, run_id: str, queue: asyncio.Queue) -> None:
        with self._lock:
            subs = self._subscribers.get(run_id, [])
            try:
                subs.remove(queue)
            except ValueError:
                pass
            if not subs:
                self._subscribers.pop(run_id, None)

    def publish_sync(self, run_id: str, event: dict[str, Any]) -> None:
        """Synchronously put *event* into every subscriber queue for *run_id*.

        Uses ``put_nowait``; events are silently dropped when a queue is full
        (subscriber is too slow).  Safe to call from synchronous code running
        inside an asyncio event loop.
        """
        with self._lock:
            queues = list(self._subscribers.get(run_id, []))
        for q in queues:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass  # slow consumer — drop rather than block the engine

    def has_subscribers(self, run_id: str) -> bool:
        with self._lock:
            return bool(self._subscribers.get(run_id))

    def reset(self) -> None:
        with self._lock:
            self._subscribers.clear()
sse_event_bus = SSEEventBus()


class ExecutionLogStore:
    """Append-only per-run execution log store.

    Captures structured log entries during flow execution — one entry per node
    event (start, retry, success, error, fallback).  Keyed by run_id.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._logs: dict[str, list[dict[str, Any]]] = {}
        self._execution_inputs: dict[str, tuple[str, dict[str, Any]]] = {}

    def record_input(self, execution_id: str, flow_id: str, input_data: dict[str, Any]) -> None:
        """Record the flow_id and input_data for an execution (used by replay)."""
        with self._lock:
            self._execution_inputs[execution_id] = (flow_id, dict(input_data))

    def get_input(self, execution_id: str) -> tuple[str, dict[str, Any]] | None:
        """Return (flow_id, input_data) for an execution, or None if not found."""
        with self._lock:
            return self._execution_inputs.get(execution_id)

    def append(self, run_id: str, entry: dict[str, Any]) -> None:
        """Append a log entry for *run_id* and notify SSE subscribers."""
        with self._lock:
            self._logs.setdefault(run_id, []).append(entry)
        sse_event_bus.publish_sync(run_id, entry)

    def get(self, run_id: str) -> list[dict[str, Any]]:
        """Return all log entries for *run_id* (empty list if none)."""
        with self._lock:
            return list(self._logs.get(run_id, []))

    def delete(self, run_id: str) -> bool:
        """Remove the log for *run_id*. Returns True if it existed."""
        with self._lock:
            return self._logs.pop(run_id, None) is not None

    def has(self, run_id: str) -> bool:
        with self._lock:
            return run_id in self._logs

    def size(self) -> int:
        with self._lock:
            return len(self._logs)

    def reset(self) -> None:
        """Clear all logs (test teardown)."""
        with self._lock:
            self._logs.clear()
            self._execution_inputs.clear()
execution_log_store = ExecutionLogStore()


class WorkflowVariableStore:
    """Thread-safe per-workflow key-value variable store.

    Variables are plain values (strings, numbers, booleans) accessible in
    node fields via the ``{{var.name}}`` template syntax.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._store: dict[str, dict[str, Any]] = {}

    def set(self, flow_id: str, variables: dict[str, Any]) -> None:
        with self._lock:
            self._store[flow_id] = dict(variables)

    def get(self, flow_id: str) -> dict[str, Any]:
        with self._lock:
            return dict(self._store.get(flow_id, {}))

    def delete(self, flow_id: str) -> None:
        with self._lock:
            self._store.pop(flow_id, None)

    def reset(self) -> None:
        with self._lock:
            self._store.clear()


class WorkflowSecretStore:
    """Thread-safe per-workflow encrypted secret store.

    Secrets are encrypted at rest using Fernet symmetric encryption.
    GET returns values masked as ``***`` to prevent accidental leakage.
    Only the raw values are available internally for template substitution.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._store: dict[str, dict[str, bytes]] = {}  # flow_id → {key: encrypted_bytes}
        self._fernet: Fernet | None = None

    def _get_fernet(self) -> Fernet:
        if self._fernet is None:
            from apps.orchestrator.main import app_config  # noqa: PLC0415 — lazy to avoid circular import

            key = app_config.fernet_key.encode() if app_config.fernet_key else None
            if key and len(key) == 44:
                self._fernet = Fernet(key)
            else:
                self._fernet = Fernet(Fernet.generate_key())
        return self._fernet

    def set(self, flow_id: str, secrets: dict[str, str]) -> None:
        f = self._get_fernet()
        with self._lock:
            encrypted = {k: f.encrypt(str(v).encode()) for k, v in secrets.items()}
            self._store[flow_id] = encrypted

    def get_masked(self, flow_id: str) -> dict[str, str]:
        """Return secret keys with masked values (``***``) — safe to return in API responses."""
        with self._lock:
            return {k: "***" for k in self._store.get(flow_id, {})}

    def get_raw(self, flow_id: str) -> dict[str, str]:
        """Return decrypted secret values — for internal template substitution only."""
        f = self._get_fernet()
        with self._lock:
            result = {}
            for k, v in self._store.get(flow_id, {}).items():
                try:
                    result[k] = f.decrypt(v).decode()
                except Exception:
                    result[k] = ""  # corrupt/tampered — emit empty rather than crash
            return result

    def get_secret_values(self, flow_id: str) -> "set[str]":
        """Return the set of raw secret values — used for log masking."""
        return set(self.get_raw(flow_id).values())

    def delete(self, flow_id: str) -> None:
        with self._lock:
            self._store.pop(flow_id, None)

    def reset(self) -> None:
        with self._lock:
            self._store.clear()


class NotificationStore:
    """Thread-safe per-workflow notification configuration store.

    Config shape per flow:
        {
            "on_complete": [{"type": "email"|"slack"|"webhook", ...}],
            "on_failure":  [{"type": "email"|"slack"|"webhook", ...}]
        }
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._store: dict[str, dict[str, Any]] = {}

    def set(self, flow_id: str, config: dict[str, Any]) -> None:
        with self._lock:
            self._store[flow_id] = dict(config)

    def get(self, flow_id: str) -> dict[str, Any]:
        with self._lock:
            return dict(self._store.get(flow_id, {}))

    def delete(self, flow_id: str) -> None:
        with self._lock:
            self._store.pop(flow_id, None)

    def reset(self) -> None:
        with self._lock:
            self._store.clear()
notification_store = NotificationStore()


class NodeCommentStore:
    """Thread-safe in-memory store for per-workflow, per-node comments."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._comments: dict[str, list[dict[str, Any]]] = {}  # key: "flow_id:node_id"

    def add(
        self,
        flow_id: str,
        node_id: str,
        author: str,
        content: str,
        parent_id: str | None = None,
    ) -> dict[str, Any]:
        key = f"{flow_id}:{node_id}"
        comment: dict[str, Any] = {
            "id": str(uuid.uuid4()),
            "flow_id": flow_id,
            "node_id": node_id,
            "author": author,
            "content": content,
            "parent_id": parent_id,
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
        }
        with self._lock:
            self._comments.setdefault(key, []).append(comment)
        return comment

    def get(self, flow_id: str, node_id: str) -> list[dict[str, Any]]:
        key = f"{flow_id}:{node_id}"
        with self._lock:
            return list(self._comments.get(key, []))

    def get_all_for_flow(self, flow_id: str) -> list[dict[str, Any]]:
        with self._lock:
            result: list[dict[str, Any]] = []
            for key, comments in self._comments.items():
                if key.startswith(f"{flow_id}:"):
                    result.extend(comments)
        result.sort(key=lambda c: c["created_at"])
        return result

    def delete(self, flow_id: str, node_id: str, comment_id: str) -> bool:
        key = f"{flow_id}:{node_id}"
        with self._lock:
            comments = self._comments.get(key, [])
            before = len(comments)
            self._comments[key] = [c for c in comments if c["id"] != comment_id]
            return len(self._comments[key]) < before

    def reset(self) -> None:
        with self._lock:
            self._comments.clear()
node_comment_store = NodeCommentStore()


class ActivityFeedStore:
    """Thread-safe in-memory store for per-workflow activity events."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._events: dict[str, list[dict[str, Any]]] = {}  # key: flow_id

    def record(
        self,
        flow_id: str,
        actor: str,
        action: str,
        detail: str = "",
    ) -> dict[str, Any]:
        event: dict[str, Any] = {
            "id": str(uuid.uuid4()),
            "flow_id": flow_id,
            "actor": actor,
            "action": action,
            "detail": detail,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        with self._lock:
            self._events.setdefault(flow_id, []).append(event)
        return event

    def get(self, flow_id: str, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            events = list(self._events.get(flow_id, []))
        events.sort(key=lambda e: e["timestamp"], reverse=True)
        return events[:limit]

    def reset(self) -> None:
        with self._lock:
            self._events.clear()
activity_feed_store = ActivityFeedStore()


class WorkflowPermissionStore:
    """Thread-safe in-memory store for per-workflow ownership and access grants.

    Backwards compatible: if no permissions are set for a flow, all access is
    allowed (open). Permissions are set when a flow is created with an
    authenticated user.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # flow_id → {"owner": str, "grants": {user_id: role}}
        self._perms: dict[str, dict[str, Any]] = {}

    def set_owner(self, flow_id: str, user_id: str) -> None:
        with self._lock:
            if flow_id not in self._perms:
                self._perms[flow_id] = {"owner": user_id, "grants": {}}
            else:
                self._perms[flow_id]["owner"] = user_id

    def grant(self, flow_id: str, user_id: str, role: str) -> None:
        with self._lock:
            if flow_id in self._perms:
                self._perms[flow_id]["grants"][user_id] = role

    def revoke(self, flow_id: str, user_id: str) -> None:
        with self._lock:
            if flow_id in self._perms:
                self._perms[flow_id]["grants"].pop(user_id, None)

    def get_role(self, flow_id: str, user_id: str) -> str | None:
        """Return role for user: 'owner', 'editor', 'viewer', or None."""
        with self._lock:
            perm = self._perms.get(flow_id)
            if perm is None:
                return None
            if perm["owner"] == user_id:
                return "owner"
            return perm["grants"].get(user_id)

    def has_flow(self, flow_id: str) -> bool:
        with self._lock:
            return flow_id in self._perms

    def get_permissions(self, flow_id: str) -> dict[str, Any]:
        with self._lock:
            perm = self._perms.get(flow_id)
            if perm is None:
                return {}
            return {"owner": perm["owner"], "grants": dict(perm["grants"])}

    def delete(self, flow_id: str) -> None:
        with self._lock:
            self._perms.pop(flow_id, None)

    def reset(self) -> None:
        with self._lock:
            self._perms.clear()
workflow_permission_store = WorkflowPermissionStore()


class AuditLogStore:
    """Global compliance audit log with configurable retention.

    Records every workflow edit, execution, and permission change with
    timestamp, actor, action, resource type, and resource ID.
    """

    def __init__(self, retention_days: int = 90) -> None:
        self._lock = threading.Lock()
        self._entries: list[dict[str, Any]] = []
        self._retention_days = retention_days

    def record(
        self,
        actor: str,
        action: str,
        resource_type: str,
        resource_id: str,
        detail: str = "",
    ) -> dict[str, Any]:
        entry: dict[str, Any] = {
            "id": str(uuid.uuid4()),
            "timestamp": datetime.now(UTC).isoformat(),
            "actor": actor,
            "action": action,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "detail": detail,
        }
        with self._lock:
            self._entries.append(entry)
        return entry

    def query(
        self,
        actor: str | None = None,
        action: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        since: str | None = None,
        until: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Return matching entries in reverse-chronological order."""
        with self._lock:
            entries = list(self._entries)
        results: list[dict[str, Any]] = []
        for e in reversed(entries):
            if actor and e["actor"] != actor:
                continue
            if action and e["action"] != action:
                continue
            if resource_type and e["resource_type"] != resource_type:
                continue
            if resource_id and e["resource_id"] != resource_id:
                continue
            if since and e["timestamp"] < since:
                continue
            if until and e["timestamp"] > until:
                continue
            results.append(e)
            if len(results) >= limit:
                break
        return results

    def purge_old(self, retention_days: int | None = None) -> int:
        """Delete entries older than retention_days. Returns count deleted."""
        days = retention_days if retention_days is not None else self._retention_days
        cutoff = (datetime.now(UTC) - timedelta(days=days)).isoformat()
        with self._lock:
            before = len(self._entries)
            self._entries = [e for e in self._entries if e["timestamp"] >= cutoff]
            return before - len(self._entries)

    def count(self) -> int:
        with self._lock:
            return len(self._entries)

    def reset(self) -> None:
        with self._lock:
            self._entries.clear()
audit_log_store = AuditLogStore(retention_days=int(os.getenv("AUDIT_LOG_RETENTION_DAYS", "90")))


class FlowTagStore:
    """In-memory store for flow tags. Each flow has a set of string tags."""

    def __init__(self) -> None:
        self._tags: dict[str, set[str]] = {}
        self._lock = threading.Lock()

    def add(self, flow_id: str, tag: str) -> None:
        with self._lock:
            self._tags.setdefault(flow_id, set()).add(tag.lower().strip())

    def remove(self, flow_id: str, tag: str) -> bool:
        """Returns True if the tag existed and was removed."""
        with self._lock:
            tags = self._tags.get(flow_id, set())
            if tag.lower().strip() in tags:
                tags.discard(tag.lower().strip())
                return True
            return False

    def get(self, flow_id: str) -> list[str]:
        with self._lock:
            return sorted(self._tags.get(flow_id, set()))

    def delete_flow(self, flow_id: str) -> None:
        with self._lock:
            self._tags.pop(flow_id, None)

    def reset(self) -> None:
        with self._lock:
            self._tags.clear()
flow_tag_store = FlowTagStore()


class FlowFavoriteStore:
    """Tracks which flows each user has favorited.

    Keyed by user email → set of flow_ids.  Per-user so favorites are
    personal; one user favoriting a flow does not affect other users.
    """

    def __init__(self) -> None:
        self._favorites: dict[str, set[str]] = {}
        self._lock = threading.Lock()

    def add(self, user_email: str, flow_id: str) -> None:
        with self._lock:
            self._favorites.setdefault(user_email, set()).add(flow_id)

    def remove(self, user_email: str, flow_id: str) -> bool:
        """Returns True if the entry existed and was removed."""
        with self._lock:
            favs = self._favorites.get(user_email, set())
            if flow_id in favs:
                favs.discard(flow_id)
                return True
            return False

    def get(self, user_email: str) -> set[str]:
        with self._lock:
            return set(self._favorites.get(user_email, set()))

    def is_favorite(self, user_email: str, flow_id: str) -> bool:
        with self._lock:
            return flow_id in self._favorites.get(user_email, set())

    def reset(self) -> None:
        with self._lock:
            self._favorites.clear()
flow_favorite_store = FlowFavoriteStore()


class FlowPinStore:
    """Tracks which flows each user has pinned (top-of-list ordering).

    Keyed by user_email → ordered list of flow_ids (insertion order).
    Pins are personal — one user pinning a flow does not affect others.
    """

    def __init__(self) -> None:
        self._pins: dict[str, list[str]] = {}  # email → ordered list
        self._lock = threading.Lock()

    def pin(self, user_email: str, flow_id: str) -> bool:
        """Pin a flow. Returns False if already pinned, True if newly pinned."""
        with self._lock:
            pins = self._pins.setdefault(user_email, [])
            if flow_id in pins:
                return False
            pins.append(flow_id)
            return True

    def unpin(self, user_email: str, flow_id: str) -> bool:
        """Unpin a flow. Returns True if it was pinned, False otherwise."""
        with self._lock:
            pins = self._pins.get(user_email, [])
            if flow_id in pins:
                pins.remove(flow_id)
                return True
            return False

    def get(self, user_email: str) -> list[str]:
        """Return pinned flow_ids in pin order (oldest first)."""
        with self._lock:
            return list(self._pins.get(user_email, []))

    def is_pinned(self, user_email: str, flow_id: str) -> bool:
        with self._lock:
            return flow_id in self._pins.get(user_email, [])

    def reset(self) -> None:
        with self._lock:
            self._pins.clear()
flow_pin_store = FlowPinStore()


class FlowDescriptionStore:
    """Stores a free-text description per flow_id (max 4 000 chars)."""

    MAX_LEN = 4000

    def __init__(self) -> None:
        self._descriptions: dict[str, str] = {}
        self._lock = threading.Lock()

    def set(self, flow_id: str, text: str) -> None:
        with self._lock:
            self._descriptions[flow_id] = text[: self.MAX_LEN]

    def get(self, flow_id: str) -> str:
        with self._lock:
            return self._descriptions.get(flow_id, "")

    def delete(self, flow_id: str) -> None:
        with self._lock:
            self._descriptions.pop(flow_id, None)

    def reset(self) -> None:
        with self._lock:
            self._descriptions.clear()
flow_description_store = FlowDescriptionStore()


class FlowArchiveStore:
    """Tracks archived (soft-deleted) flows.

    Archived flows are hidden from normal listings but remain in the DB.
    Users can restore them at any time via DELETE /flows/{id}/archive.
    """

    def __init__(self) -> None:
        self._archived: dict[str, float] = {}  # flow_id → archived_at (epoch)
        self._lock = threading.Lock()

    def archive(self, flow_id: str) -> float:
        """Mark flow as archived. Returns the archived_at timestamp."""
        ts = time.time()
        with self._lock:
            self._archived[flow_id] = ts
        return ts

    def restore(self, flow_id: str) -> bool:
        """Remove archive mark. Returns True if it was archived, False otherwise."""
        with self._lock:
            return self._archived.pop(flow_id, None) is not None

    def is_archived(self, flow_id: str) -> bool:
        with self._lock:
            return flow_id in self._archived

    def archived_at(self, flow_id: str) -> float | None:
        with self._lock:
            return self._archived.get(flow_id)

    def all_archived_ids(self) -> set[str]:
        with self._lock:
            return set(self._archived)

    def reset(self) -> None:
        with self._lock:
            self._archived.clear()
flow_archive_store = FlowArchiveStore()


class FlowLabelStore:
    """Stores a visual label (color + optional icon) per flow_id.

    - color: CSS hex color string, e.g. "#ff5733" (7 chars: # + 6 hex digits)
    - icon: optional emoji or short text, max 2 characters
    """

    _HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")

    def __init__(self) -> None:
        self._labels: dict[str, dict[str, str]] = {}  # flow_id → {color, icon}
        self._lock = threading.Lock()

    def set(self, flow_id: str, color: str, icon: str = "") -> None:
        with self._lock:
            self._labels[flow_id] = {"color": color, "icon": icon}

    def get(self, flow_id: str) -> dict[str, str] | None:
        with self._lock:
            return dict(self._labels[flow_id]) if flow_id in self._labels else None

    def delete(self, flow_id: str) -> bool:
        with self._lock:
            return self._labels.pop(flow_id, None) is not None

    def reset(self) -> None:
        with self._lock:
            self._labels.clear()
flow_label_store = FlowLabelStore()


class FlowShareStore:
    """Issues and validates short-lived read-only share tokens for flows.

    Tokens are UUID4 hex strings. Expired tokens are not automatically
    purged — they are rejected on access and can accumulate, but the store
    is only in-memory so they vanish on restart or reset().
    """

    DEFAULT_TTL = 86_400  # 24 hours in seconds

    def __init__(self) -> None:
        self._tokens: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def create(self, flow_id: str, created_by: str, ttl: int = DEFAULT_TTL) -> dict[str, Any]:
        """Generate a new share token. Returns the token record."""
        token = uuid.uuid4().hex
        expires_at = time.time() + ttl
        record: dict[str, Any] = {
            "token": token,
            "flow_id": flow_id,
            "created_by": created_by,
            "expires_at": expires_at,
            "ttl": ttl,
        }
        with self._lock:
            self._tokens[token] = record
        return record

    def get(self, token: str) -> dict[str, Any] | None:
        """Return the token record if it exists and has not expired."""
        with self._lock:
            record = self._tokens.get(token)
        if record is None:
            return None
        if time.time() > record["expires_at"]:
            return None  # expired
        return record

    def revoke(self, token: str) -> bool:
        """Delete a token regardless of expiry. Returns True if it existed."""
        with self._lock:
            return self._tokens.pop(token, None) is not None

    def list_for_flow(self, flow_id: str) -> list[dict[str, Any]]:
        """Return all active (non-expired) tokens for a given flow."""
        now = time.time()
        with self._lock:
            return [
                dict(r)
                for r in self._tokens.values()
                if r["flow_id"] == flow_id and now <= r["expires_at"]
            ]

    def reset(self) -> None:
        with self._lock:
            self._tokens.clear()
flow_share_store = FlowShareStore()


class FlowGroupStore:
    """Assigns each flow to at most one named group (folder).

    Groups are implicit — they exist as long as at least one flow is assigned.
    Group names are lowercased and stripped on write.
    """

    def __init__(self) -> None:
        self._flow_to_group: dict[str, str] = {}  # flow_id → group_name
        self._lock = threading.Lock()

    def set(self, flow_id: str, group: str) -> None:
        """Assign (or move) a flow to a group."""
        with self._lock:
            self._flow_to_group[flow_id] = group.lower().strip()

    def get(self, flow_id: str) -> str | None:
        """Return the group for a flow, or None if ungrouped."""
        with self._lock:
            return self._flow_to_group.get(flow_id)

    def remove(self, flow_id: str) -> bool:
        """Remove a flow from its group. Returns True if it was in a group."""
        with self._lock:
            return self._flow_to_group.pop(flow_id, None) is not None

    def flows_in_group(self, group: str) -> list[str]:
        """Return all flow_ids in the given group (normalised)."""
        norm = group.lower().strip()
        with self._lock:
            return [fid for fid, g in self._flow_to_group.items() if g == norm]

    def all_groups(self) -> dict[str, int]:
        """Return {group_name: flow_count} for all non-empty groups."""
        with self._lock:
            counts: dict[str, int] = {}
            for g in self._flow_to_group.values():
                counts[g] = counts.get(g, 0) + 1
            return counts

    def reset(self) -> None:
        with self._lock:
            self._flow_to_group.clear()
flow_group_store = FlowGroupStore()


class FlowAccessLogStore:
    """Records who accessed (read) each flow and when.

    Capped at MAX_ENTRIES per flow to prevent unbounded memory growth.
    Entries are stored in chronological order (oldest first).
    """

    MAX_ENTRIES = 500

    def __init__(self) -> None:
        self._log: dict[str, list[dict[str, Any]]] = {}  # flow_id → entries
        self._lock = threading.Lock()

    def record(self, flow_id: str, accessor: str) -> None:
        entry: dict[str, Any] = {"accessor": accessor, "accessed_at": time.time()}
        with self._lock:
            entries = self._log.setdefault(flow_id, [])
            entries.append(entry)
            if len(entries) > self.MAX_ENTRIES:
                del entries[0]  # drop oldest when cap exceeded

    def get(self, flow_id: str, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        with self._lock:
            entries = self._log.get(flow_id, [])
            # Return newest-first slice
            sliced = list(reversed(entries))[offset : offset + limit]
        return [
            {
                "accessor": e["accessor"],
                "accessed_at": datetime.fromtimestamp(e["accessed_at"], tz=UTC).isoformat(),
            }
            for e in sliced
        ]

    def count(self, flow_id: str) -> int:
        with self._lock:
            return len(self._log.get(flow_id, []))

    def reset(self) -> None:
        with self._lock:
            self._log.clear()
flow_access_log_store = FlowAccessLogStore()


class FlowWatchStore:
    """Track per-user watch subscriptions for flows.

    Users can watch flows to receive notifications when they run or fail.
    Stored as {user_email: set[flow_id]} and the inverse {flow_id: set[user_email]}.
    """

    def __init__(self) -> None:
        self._by_user: dict[str, set[str]] = {}
        self._by_flow: dict[str, set[str]] = {}
        self._lock = threading.Lock()

    def watch(self, flow_id: str, user: str) -> bool:
        """Subscribe user to flow. Returns True if newly added, False if already watching."""
        with self._lock:
            if user in self._by_flow.get(flow_id, set()):
                return False
            self._by_user.setdefault(user, set()).add(flow_id)
            self._by_flow.setdefault(flow_id, set()).add(user)
            return True

    def unwatch(self, flow_id: str, user: str) -> bool:
        """Unsubscribe user from flow. Returns True if removed, False if not watching."""
        with self._lock:
            if user not in self._by_flow.get(flow_id, set()):
                return False
            self._by_flow[flow_id].discard(user)
            self._by_user.get(user, set()).discard(flow_id)
            return True

    def is_watching(self, flow_id: str, user: str) -> bool:
        with self._lock:
            return user in self._by_flow.get(flow_id, set())

    def watched_by_user(self, user: str) -> list[str]:
        """Return list of flow_ids watched by a user (insertion-stable via set iteration)."""
        with self._lock:
            return sorted(self._by_user.get(user, set()))

    def watchers_for_flow(self, flow_id: str) -> list[str]:
        """Return list of user emails watching a flow."""
        with self._lock:
            return sorted(self._by_flow.get(flow_id, set()))

    def reset(self) -> None:
        with self._lock:
            self._by_user.clear()
            self._by_flow.clear()
flow_watch_store = FlowWatchStore()


class FlowEditLockStore:
    """Prevent edits to a flow by locking it.

    A locked flow cannot be updated via PUT /flows/{id} until unlocked.
    Lock includes the locking user and an optional reason.
    """

    def __init__(self) -> None:
        self._locks: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def lock(self, flow_id: str, user: str, reason: str = "") -> dict[str, Any]:
        """Lock a flow. Returns the lock record. Raises ValueError if already locked."""
        with self._lock:
            if flow_id in self._locks:
                raise ValueError("Flow is already locked")
            record: dict[str, Any] = {
                "flow_id": flow_id,
                "locked_by": user,
                "reason": reason,
                "locked_at": time.time(),
            }
            self._locks[flow_id] = record
            return dict(record)

    def unlock(self, flow_id: str) -> bool:
        """Unlock a flow. Returns True if removed, False if not locked."""
        with self._lock:
            if flow_id not in self._locks:
                return False
            del self._locks[flow_id]
            return True

    def get(self, flow_id: str) -> dict[str, Any] | None:
        """Return the lock record for a flow, or None if unlocked."""
        with self._lock:
            record = self._locks.get(flow_id)
            return dict(record) if record else None

    def is_locked(self, flow_id: str) -> bool:
        with self._lock:
            return flow_id in self._locks

    def reset(self) -> None:
        with self._lock:
            self._locks.clear()
flow_edit_lock_store = FlowEditLockStore()


class FlowMetadataStore:
    """Store arbitrary JSON-serialisable key-value metadata per flow.

    Keys are strings; values can be any JSON-compatible type.
    Maximum 50 keys per flow. Key names max 100 chars.
    """

    MAX_KEYS = 50
    MAX_KEY_LEN = 100

    def __init__(self) -> None:
        self._data: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def get(self, flow_id: str) -> dict[str, Any]:
        with self._lock:
            return dict(self._data.get(flow_id, {}))

    def set(self, flow_id: str, metadata: dict[str, Any]) -> dict[str, Any]:
        """Replace the entire metadata dict for a flow. Returns the saved dict."""
        if len(metadata) > self.MAX_KEYS:
            raise ValueError(f"Metadata exceeds {self.MAX_KEYS} key limit")
        for key in metadata:
            if len(key) > self.MAX_KEY_LEN:
                raise ValueError(f"Key '{key[:20]}...' exceeds {self.MAX_KEY_LEN} char limit")
        with self._lock:
            self._data[flow_id] = dict(metadata)
            return dict(self._data[flow_id])

    def patch(self, flow_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        """Merge updates into existing metadata. Returns the merged dict."""
        with self._lock:
            current = self._data.get(flow_id, {})
            merged = {**current, **updates}
        if len(merged) > self.MAX_KEYS:
            raise ValueError(f"Metadata would exceed {self.MAX_KEYS} key limit")
        for key in merged:
            if len(key) > self.MAX_KEY_LEN:
                raise ValueError(f"Key '{key[:20]}...' exceeds {self.MAX_KEY_LEN} char limit")
        with self._lock:
            self._data[flow_id] = merged
            return dict(merged)

    def delete_key(self, flow_id: str, key: str) -> bool:
        """Remove a single key. Returns True if removed, False if not present."""
        with self._lock:
            if flow_id not in self._data or key not in self._data[flow_id]:
                return False
            del self._data[flow_id][key]
            return True

    def reset(self) -> None:
        with self._lock:
            self._data.clear()
flow_metadata_store = FlowMetadataStore()


class FlowPriorityStore:
    """Store priority level per flow. Default is None (unset)."""

    def __init__(self) -> None:
        self._priorities: dict[str, str] = {}
        self._lock = threading.Lock()

    def set(self, flow_id: str, priority: str) -> str:
        if priority not in FLOW_PRIORITY_VALUES:
            raise ValueError(f"Invalid priority '{priority}'; must be one of {FLOW_PRIORITY_VALUES}")
        with self._lock:
            self._priorities[flow_id] = priority
            return priority

    def get(self, flow_id: str) -> str | None:
        with self._lock:
            return self._priorities.get(flow_id)

    def clear(self, flow_id: str) -> bool:
        with self._lock:
            if flow_id not in self._priorities:
                return False
            del self._priorities[flow_id]
            return True

    def flows_with_priority(self, priority: str) -> list[str]:
        with self._lock:
            return [fid for fid, p in self._priorities.items() if p == priority]

    def reset(self) -> None:
        with self._lock:
            self._priorities.clear()
flow_priority_store = FlowPriorityStore()


class FlowExpiryStore:
    """Store optional expiry timestamps per flow.

    Expiry is checked lazily at read time — no background worker needed.
    A flow past its expiry is considered expired; callers decide what to
    return (410 Gone, 404, auto-archive, etc.).
    """

    def __init__(self) -> None:
        self._expiries: dict[str, float] = {}
        self._lock = threading.Lock()

    def set(self, flow_id: str, expires_at: float) -> float:
        """Set expiry timestamp (Unix epoch). Returns the stored value."""
        with self._lock:
            self._expiries[flow_id] = expires_at
            return expires_at

    def get(self, flow_id: str) -> float | None:
        """Return the expiry timestamp, or None if not set."""
        with self._lock:
            return self._expiries.get(flow_id)

    def clear(self, flow_id: str) -> bool:
        """Remove expiry. Returns True if removed, False if not set."""
        with self._lock:
            if flow_id not in self._expiries:
                return False
            del self._expiries[flow_id]
            return True

    def is_expired(self, flow_id: str) -> bool:
        """Return True if a non-None expiry exists and is in the past."""
        with self._lock:
            ts = self._expiries.get(flow_id)
        return ts is not None and time.time() > ts

    def reset(self) -> None:
        with self._lock:
            self._expiries.clear()
flow_expiry_store = FlowExpiryStore()


class FlowAliasStore:
    """Bidirectional alias ↔ flow_id mapping.

    Aliases are unique slugs (lowercase alphanumeric + hyphens) that
    provide a human-readable shorthand for looking up a flow.
    Each flow may have at most one alias; each alias maps to exactly one flow.
    """

    def __init__(self) -> None:
        self._alias_to_flow: dict[str, str] = {}
        self._flow_to_alias: dict[str, str] = {}
        self._lock = threading.Lock()

    def set(self, flow_id: str, alias: str) -> None:
        """Set or update the alias for *flow_id*.

        Raises ``ValueError`` if *alias* is already owned by a different flow.
        """
        with self._lock:
            owner = self._alias_to_flow.get(alias)
            if owner and owner != flow_id:
                raise ValueError(f"Alias '{alias}' is already in use by another flow")
            # Remove previous alias for this flow (if any)
            old = self._flow_to_alias.pop(flow_id, None)
            if old:
                self._alias_to_flow.pop(old, None)
            self._alias_to_flow[alias] = flow_id
            self._flow_to_alias[flow_id] = alias

    def get(self, flow_id: str) -> str | None:
        """Return the alias for *flow_id*, or ``None`` if not set."""
        with self._lock:
            return self._flow_to_alias.get(flow_id)

    def resolve(self, alias: str) -> str | None:
        """Return the flow_id for *alias*, or ``None`` if not found."""
        with self._lock:
            return self._alias_to_flow.get(alias)

    def clear(self, flow_id: str) -> bool:
        """Remove the alias for *flow_id*.  Returns ``True`` if one existed."""
        with self._lock:
            alias = self._flow_to_alias.pop(flow_id, None)
            if alias:
                self._alias_to_flow.pop(alias, None)
                return True
            return False

    def reset(self) -> None:
        with self._lock:
            self._alias_to_flow.clear()
            self._flow_to_alias.clear()
flow_alias_store = FlowAliasStore()


class FlowRateLimitStore:
    """Per-flow execution rate limiting via a sliding-window counter.

    Stores a config (max_runs, window_seconds) per flow and tracks
    recent run timestamps to enforce the limit at run time.
    """

    def __init__(self) -> None:
        self._limits: dict[str, dict[str, int]] = {}  # flow_id → config
        self._timestamps: dict[str, deque] = {}  # flow_id → deque[float]
        self._lock = threading.Lock()

    def set(self, flow_id: str, max_runs: int, window_seconds: int) -> dict[str, Any]:
        with self._lock:
            self._limits[flow_id] = {"max_runs": max_runs, "window_seconds": window_seconds}
            return self._limits[flow_id].copy()

    def get(self, flow_id: str) -> dict[str, Any] | None:
        with self._lock:
            cfg = self._limits.get(flow_id)
            return cfg.copy() if cfg else None

    def clear(self, flow_id: str) -> bool:
        with self._lock:
            existed = flow_id in self._limits
            self._limits.pop(flow_id, None)
            self._timestamps.pop(flow_id, None)
            return existed

    def check_and_record(self, flow_id: str) -> None:
        """Record a run attempt; raises ``ValueError`` if the limit is exceeded."""
        with self._lock:
            cfg = self._limits.get(flow_id)
            if cfg is None:
                return  # No limit configured — allow freely.
            max_runs = cfg["max_runs"]
            window = cfg["window_seconds"]
            now = time.time()
            q = self._timestamps.setdefault(flow_id, deque())
            cutoff = now - window
            while q and q[0] <= cutoff:
                q.popleft()
            if len(q) >= max_runs:
                raise ValueError(
                    f"Rate limit exceeded: max {max_runs} runs per {window}s"
                )
            q.append(now)

    def current_count(self, flow_id: str) -> int:
        """Number of runs recorded in the current window."""
        with self._lock:
            cfg = self._limits.get(flow_id)
            if cfg is None:
                return 0
            window = cfg["window_seconds"]
            now = time.time()
            q = self._timestamps.get(flow_id, deque())
            cutoff = now - window
            return sum(1 for t in q if t > cutoff)

    def reset(self) -> None:
        with self._lock:
            self._limits.clear()
            self._timestamps.clear()
flow_rate_limit_store = FlowRateLimitStore()


class FlowChangelogStore:
    """Append-only log of user-authored changelog entries per flow.

    Each entry has: id, flow_id, author, type, message, created_at (epoch float).
    Entries are returned newest-first. Capacity is capped at 500 per flow.
    """

    MAX_ENTRIES = 500

    def __init__(self) -> None:
        self._entries: dict[str, list[dict[str, Any]]] = {}  # flow_id → [entry, ...]
        self._lock = threading.Lock()

    def add(
        self,
        flow_id: str,
        author: str,
        message: str,
        entry_type: str = "note",
    ) -> dict[str, Any]:
        with self._lock:
            entries = self._entries.setdefault(flow_id, [])
            if len(entries) >= self.MAX_ENTRIES:
                raise ValueError(
                    f"Changelog capacity ({self.MAX_ENTRIES}) reached for this flow"
                )
            entry: dict[str, Any] = {
                "id": uuid.uuid4().hex,
                "flow_id": flow_id,
                "author": author,
                "type": entry_type,
                "message": message,
                "created_at": time.time(),
            }
            entries.append(entry)
            return entry.copy()

    def list(
        self,
        flow_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        with self._lock:
            entries = list(reversed(self._entries.get(flow_id, [])))
            return [e.copy() for e in entries[offset : offset + limit]]

    def delete(self, flow_id: str, entry_id: str) -> bool:
        with self._lock:
            entries = self._entries.get(flow_id, [])
            before = len(entries)
            self._entries[flow_id] = [e for e in entries if e["id"] != entry_id]
            return len(self._entries[flow_id]) < before

    def total(self, flow_id: str) -> int:
        with self._lock:
            return len(self._entries.get(flow_id, []))

    def reset(self) -> None:
        with self._lock:
            self._entries.clear()
flow_changelog_store = FlowChangelogStore()


class FlowRunPresetStore:
    """Named input presets for a flow.

    Each preset stores a name, optional description, and an input payload dict.
    Presets are scoped to (flow_id) and allow users to save commonly-used inputs
    for quick reuse when triggering runs.
    Capacity: 100 presets per flow.
    """

    MAX_PRESETS = 100

    def __init__(self) -> None:
        self._store: dict[str, list[dict[str, Any]]] = {}  # flow_id → [preset, ...]
        self._lock = threading.Lock()

    def add(
        self,
        flow_id: str,
        name: str,
        input_payload: dict[str, Any],
        description: str = "",
    ) -> dict[str, Any]:
        with self._lock:
            presets = self._store.setdefault(flow_id, [])
            if len(presets) >= self.MAX_PRESETS:
                raise ValueError(
                    f"Preset capacity ({self.MAX_PRESETS}) reached for this flow"
                )
            preset: dict[str, Any] = {
                "id": uuid.uuid4().hex,
                "flow_id": flow_id,
                "name": name,
                "description": description,
                "input": input_payload,
                "created_at": time.time(),
            }
            presets.append(preset)
            return preset.copy()

    def list(self, flow_id: str) -> list[dict[str, Any]]:
        with self._lock:
            return [p.copy() for p in self._store.get(flow_id, [])]

    def get(self, flow_id: str, preset_id: str) -> dict[str, Any] | None:
        with self._lock:
            for p in self._store.get(flow_id, []):
                if p["id"] == preset_id:
                    return p.copy()
            return None

    def delete(self, flow_id: str, preset_id: str) -> bool:
        with self._lock:
            presets = self._store.get(flow_id, [])
            before = len(presets)
            self._store[flow_id] = [p for p in presets if p["id"] != preset_id]
            return len(self._store[flow_id]) < before

    def reset(self) -> None:
        with self._lock:
            self._store.clear()
flow_run_preset_store = FlowRunPresetStore()


class FlowAnnotationStore:
    """Per-flow sticky-note annotations with canvas position and optional color.

    Each annotation has: id, flow_id, content, x, y, color, author, created_at, updated_at.
    Capacity: 200 annotations per flow.
    """

    MAX_ANNOTATIONS = 200

    def __init__(self) -> None:
        self._store: dict[str, list[dict[str, Any]]] = {}  # flow_id → [annotation, ...]
        self._lock = threading.Lock()

    def add(
        self,
        flow_id: str,
        content: str,
        x: float,
        y: float,
        color: str,
        author: str,
    ) -> dict[str, Any]:
        with self._lock:
            annotations = self._store.setdefault(flow_id, [])
            if len(annotations) >= self.MAX_ANNOTATIONS:
                raise ValueError(
                    f"Annotation capacity ({self.MAX_ANNOTATIONS}) reached for this flow"
                )
            now = time.time()
            ann: dict[str, Any] = {
                "id": uuid.uuid4().hex,
                "flow_id": flow_id,
                "content": content,
                "x": x,
                "y": y,
                "color": color,
                "author": author,
                "created_at": now,
                "updated_at": now,
            }
            annotations.append(ann)
            return ann.copy()

    def list(self, flow_id: str) -> list[dict[str, Any]]:
        with self._lock:
            return [a.copy() for a in self._store.get(flow_id, [])]

    def get(self, flow_id: str, ann_id: str) -> dict[str, Any] | None:
        with self._lock:
            for a in self._store.get(flow_id, []):
                if a["id"] == ann_id:
                    return a.copy()
            return None

    def patch(
        self,
        flow_id: str,
        ann_id: str,
        updates: dict[str, Any],
    ) -> dict[str, Any] | None:
        with self._lock:
            for a in self._store.get(flow_id, []):
                if a["id"] == ann_id:
                    for k, v in updates.items():
                        a[k] = v
                    a["updated_at"] = time.time()
                    return a.copy()
            return None

    def delete(self, flow_id: str, ann_id: str) -> bool:
        with self._lock:
            annotations = self._store.get(flow_id, [])
            before = len(annotations)
            self._store[flow_id] = [a for a in annotations if a["id"] != ann_id]
            return len(self._store[flow_id]) < before

    def reset(self) -> None:
        with self._lock:
            self._store.clear()
flow_annotation_store = FlowAnnotationStore()


class FlowDependencyStore:
    """Directed dependency graph between flows.

    Records that flow A *depends on* flow B (A → B).
    Each directed edge is stored as a record with an id, from_flow_id, to_flow_id,
    optional label, and created_at.

    Cycle detection: adding A→B is rejected (ValueError) if B already
    transitively depends on A (would create a cycle).
    Max out-degree: 50 dependencies per flow.
    """

    MAX_DEPS = 50

    def __init__(self) -> None:
        # from_flow_id → [edge_dict, ...]
        self._outgoing: dict[str, list[dict[str, Any]]] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Internal helpers (must be called with lock held)
    # ------------------------------------------------------------------

    def _reaches(self, start: str, target: str) -> bool:
        """BFS: can *start* reach *target* following outgoing edges?"""
        visited: set[str] = set()
        queue = [start]
        while queue:
            node = queue.pop()
            if node == target:
                return True
            if node in visited:
                continue
            visited.add(node)
            for e in self._outgoing.get(node, []):
                queue.append(e["to_flow_id"])
        return False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add(
        self,
        from_flow_id: str,
        to_flow_id: str,
        label: str = "",
    ) -> dict[str, Any]:
        with self._lock:
            edges = self._outgoing.setdefault(from_flow_id, [])
            # Check duplicate
            if any(e["to_flow_id"] == to_flow_id for e in edges):
                raise ValueError("Dependency already exists")
            if len(edges) >= self.MAX_DEPS:
                raise ValueError(
                    f"Dependency limit ({self.MAX_DEPS}) reached for this flow"
                )
            # Self-loop
            if from_flow_id == to_flow_id:
                raise ValueError("A flow cannot depend on itself")
            # Cycle detection: if to_flow_id already reaches from_flow_id, adding
            # this edge would create a cycle.
            if self._reaches(to_flow_id, from_flow_id):
                raise ValueError(
                    "Adding this dependency would create a cycle"
                )
            edge: dict[str, Any] = {
                "id": uuid.uuid4().hex,
                "from_flow_id": from_flow_id,
                "to_flow_id": to_flow_id,
                "label": label,
                "created_at": time.time(),
            }
            edges.append(edge)
            return edge.copy()

    def list_dependencies(self, flow_id: str) -> list[dict[str, Any]]:
        """Flows that *flow_id* depends on (outgoing edges)."""
        with self._lock:
            return [e.copy() for e in self._outgoing.get(flow_id, [])]

    def list_dependents(self, flow_id: str) -> list[dict[str, Any]]:
        """Flows that depend on *flow_id* (incoming edges)."""
        with self._lock:
            result = []
            for edges in self._outgoing.values():
                for e in edges:
                    if e["to_flow_id"] == flow_id:
                        result.append(e.copy())
            return result

    def delete(self, from_flow_id: str, dep_id: str) -> bool:
        with self._lock:
            edges = self._outgoing.get(from_flow_id, [])
            before = len(edges)
            self._outgoing[from_flow_id] = [e for e in edges if e["id"] != dep_id]
            return len(self._outgoing[from_flow_id]) < before

    def reset(self) -> None:
        with self._lock:
            self._outgoing.clear()
flow_dependency_store = FlowDependencyStore()


class FlowBookmarkStore:
    """Per-user canvas viewport bookmarks for a flow.

    Each bookmark captures a name, the user who created it, and an optional
    viewport dict (x, y, zoom) so the UI can restore the exact canvas position.
    Scoped to (flow_id, user) — a user can have up to 50 bookmarks per flow.
    """

    MAX_PER_USER_FLOW = 50

    def __init__(self) -> None:
        # (flow_id, user) → [bookmark_dict, ...]
        self._store: dict[tuple[str, str], list[dict[str, Any]]] = {}
        self._lock = threading.Lock()

    def add(
        self,
        flow_id: str,
        user: str,
        name: str,
        viewport: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            key = (flow_id, user)
            bms = self._store.setdefault(key, [])
            if len(bms) >= self.MAX_PER_USER_FLOW:
                raise ValueError(
                    f"Bookmark capacity ({self.MAX_PER_USER_FLOW}) reached for this flow/user"
                )
            bm: dict[str, Any] = {
                "id": uuid.uuid4().hex,
                "flow_id": flow_id,
                "user": user,
                "name": name,
                "viewport": viewport or {},
                "created_at": time.time(),
            }
            bms.append(bm)
            return bm.copy()

    def list(self, flow_id: str, user: str) -> list[dict[str, Any]]:
        with self._lock:
            return [b.copy() for b in self._store.get((flow_id, user), [])]

    def delete(self, flow_id: str, user: str, bm_id: str) -> bool:
        with self._lock:
            key = (flow_id, user)
            bms = self._store.get(key, [])
            before = len(bms)
            self._store[key] = [b for b in bms if b["id"] != bm_id]
            return len(self._store[key]) < before

    def reset(self) -> None:
        with self._lock:
            self._store.clear()
flow_bookmark_store = FlowBookmarkStore()


class FlowSnapshotStore:
    """Stores point-in-time snapshots of a flow's nodes/edges.

    Snapshots let users capture and optionally restore the canvas state
    without creating a full semver version (cf. FlowChangelogStore for
    text notes, workflow_version_store for semver releases).

    Limits: 50 snapshots per flow, oldest entry auto-evicted when full.
    """

    MAX_SNAPSHOTS = 50

    def __init__(self) -> None:
        self._store: dict[str, list[dict[str, Any]]] = {}  # flow_id → snapshots
        self._lock = threading.Lock()

    def add(
        self,
        flow_id: str,
        label: str,
        nodes: list[Any],
        edges: list[Any],
        author: str,
    ) -> dict[str, Any]:
        with self._lock:
            snaps = self._store.setdefault(flow_id, [])
            if len(snaps) >= self.MAX_SNAPSHOTS:
                snaps.pop(0)
            snap: dict[str, Any] = {
                "id": uuid.uuid4().hex,
                "flow_id": flow_id,
                "label": label,
                "nodes": nodes,
                "edges": edges,
                "author": author,
                "created_at": datetime.now(UTC).isoformat(),
            }
            snaps.append(snap)
            return snap.copy()

    def list(self, flow_id: str) -> list[dict[str, Any]]:
        with self._lock:
            return [s.copy() for s in reversed(self._store.get(flow_id, []))]

    def get(self, flow_id: str, snapshot_id: str) -> dict[str, Any] | None:
        with self._lock:
            for s in self._store.get(flow_id, []):
                if s["id"] == snapshot_id:
                    return s.copy()
            return None

    def delete(self, flow_id: str, snapshot_id: str) -> bool:
        with self._lock:
            snaps = self._store.get(flow_id, [])
            before = len(snaps)
            self._store[flow_id] = [s for s in snaps if s["id"] != snapshot_id]
            return len(self._store[flow_id]) < before

    def reset(self) -> None:
        with self._lock:
            self._store.clear()
flow_snapshot_store = FlowSnapshotStore()


class FlowReactionStore:
    """Tracks emoji reactions per flow, scoped to the reacting user.

    Each user can add at most one reaction of each emoji type per flow.
    The store exposes aggregate counts (all users) and per-user reactions.
    """

    def __init__(self) -> None:
        # (flow_id, emoji) → set of usernames
        self._reactions: dict[tuple[str, str], set[str]] = {}
        self._lock = threading.Lock()

    def add(self, flow_id: str, emoji: str, user: str) -> None:
        """Add user's reaction.  No-op if already reacted with this emoji."""
        if emoji not in _ALLOWED_REACTIONS:
            raise ValueError(f"Unsupported reaction: {emoji}")
        with self._lock:
            self._reactions.setdefault((flow_id, emoji), set()).add(user)

    def remove(self, flow_id: str, emoji: str, user: str) -> bool:
        """Remove user's reaction.  Returns True if it existed."""
        if emoji not in _ALLOWED_REACTIONS:
            raise ValueError(f"Unsupported reaction: {emoji}")
        with self._lock:
            users = self._reactions.get((flow_id, emoji), set())
            if user not in users:
                return False
            users.discard(user)
            return True

    def summary(self, flow_id: str) -> list[dict[str, Any]]:
        """Return aggregate counts for all reactions on a flow."""
        with self._lock:
            result = []
            for emoji in _ALLOWED_REACTIONS:
                users = self._reactions.get((flow_id, emoji), set())
                if users:
                    result.append({"emoji": emoji, "count": len(users)})
            result.sort(key=lambda r: -r["count"])
            return result

    def user_reactions(self, flow_id: str, user: str) -> list[str]:
        """Return the list of emojis the given user has reacted with."""
        with self._lock:
            return [
                emoji
                for emoji in _ALLOWED_REACTIONS
                if user in self._reactions.get((flow_id, emoji), set())
            ]

    def reset(self) -> None:
        with self._lock:
            self._reactions.clear()
flow_reaction_store = FlowReactionStore()


class FlowScheduleStore:
    """Stores a cron schedule per flow.

    One schedule per flow.  A schedule can be enabled or disabled without
    removing it.  The cron expression is validated against a basic 5-field
    pattern (minute hour dom month dow) but is not executed by the store —
    the actual scheduling is the responsibility of an external worker.
    """

    def __init__(self) -> None:
        self._schedules: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def _validate_cron(self, expr: str) -> None:
        if not _CRON_PATTERN.match(expr.strip()):
            raise ValueError(f"Invalid cron expression: {expr!r}")

    def set(self, flow_id: str, cron: str, enabled: bool = True, label: str = "") -> dict[str, Any]:
        self._validate_cron(cron)
        with self._lock:
            existing = self._schedules.get(flow_id)
            schedule: dict[str, Any] = {
                "flow_id": flow_id,
                "cron": cron.strip(),
                "enabled": enabled,
                "label": label,
                "created_at": existing["created_at"] if existing else datetime.now(UTC).isoformat(),
                "updated_at": datetime.now(UTC).isoformat(),
            }
            self._schedules[flow_id] = schedule
            return schedule.copy()

    def get(self, flow_id: str) -> dict[str, Any] | None:
        with self._lock:
            s = self._schedules.get(flow_id)
            return s.copy() if s else None

    def patch(self, flow_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
        """Partial update: only 'enabled', 'cron', 'label' are patchable."""
        with self._lock:
            s = self._schedules.get(flow_id)
            if s is None:
                return None
            if "cron" in updates:
                self._validate_cron(updates["cron"])
                s["cron"] = updates["cron"].strip()
            if "enabled" in updates:
                s["enabled"] = bool(updates["enabled"])
            if "label" in updates:
                s["label"] = updates["label"]
            s["updated_at"] = datetime.now(UTC).isoformat()
            return s.copy()

    def clear(self, flow_id: str) -> bool:
        with self._lock:
            if flow_id not in self._schedules:
                return False
            del self._schedules[flow_id]
            return True

    def reset(self) -> None:
        with self._lock:
            self._schedules.clear()
flow_schedule_store = FlowScheduleStore()


class FlowWebhookStore:
    """Stores outbound webhook subscriptions per flow.

    Each webhook has a URL, a set of events to listen for, and an optional
    secret (for HMAC signing).  Multiple webhooks per flow are allowed (max 20).
    """

    MAX_WEBHOOKS = 20

    def __init__(self) -> None:
        self._store: dict[str, list[dict[str, Any]]] = {}
        self._lock = threading.Lock()

    def _validate(self, url: str, events: list[str]) -> None:
        if not _URL_PATTERN.match(url):
            raise ValueError(f"Invalid URL: {url!r}")
        unknown = set(events) - _WEBHOOK_EVENTS
        if unknown:
            raise ValueError(f"Unknown events: {sorted(unknown)}")
        if not events:
            raise ValueError("At least one event is required")

    def add(
        self,
        flow_id: str,
        url: str,
        events: list[str],
        secret: str = "",
        label: str = "",
    ) -> dict[str, Any]:
        self._validate(url, events)
        with self._lock:
            hooks = self._store.setdefault(flow_id, [])
            if len(hooks) >= self.MAX_WEBHOOKS:
                raise ValueError(f"Maximum of {self.MAX_WEBHOOKS} webhooks per flow exceeded")
            hook: dict[str, Any] = {
                "id": uuid.uuid4().hex,
                "flow_id": flow_id,
                "url": url,
                "events": sorted(set(events)),
                "secret": secret,
                "label": label,
                "enabled": True,
                "created_at": datetime.now(UTC).isoformat(),
            }
            hooks.append(hook)
            return hook.copy()

    def list(self, flow_id: str) -> list[dict[str, Any]]:
        with self._lock:
            return [h.copy() for h in self._store.get(flow_id, [])]

    def get(self, flow_id: str, hook_id: str) -> dict[str, Any] | None:
        with self._lock:
            for h in self._store.get(flow_id, []):
                if h["id"] == hook_id:
                    return h.copy()
            return None

    def patch(self, flow_id: str, hook_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
        with self._lock:
            for h in self._store.get(flow_id, []):
                if h["id"] == hook_id:
                    if "url" in updates:
                        if not _URL_PATTERN.match(updates["url"]):
                            raise ValueError(f"Invalid URL: {updates['url']!r}")
                        h["url"] = updates["url"]
                    if "events" in updates:
                        unknown = set(updates["events"]) - _WEBHOOK_EVENTS
                        if unknown:
                            raise ValueError(f"Unknown events: {sorted(unknown)}")
                        h["events"] = sorted(set(updates["events"]))
                    if "enabled" in updates:
                        h["enabled"] = bool(updates["enabled"])
                    if "label" in updates:
                        h["label"] = updates["label"]
                    if "secret" in updates:
                        h["secret"] = updates["secret"]
                    return h.copy()
            return None

    def delete(self, flow_id: str, hook_id: str) -> bool:
        with self._lock:
            hooks = self._store.get(flow_id, [])
            before = len(hooks)
            self._store[flow_id] = [h for h in hooks if h["id"] != hook_id]
            return len(self._store[flow_id]) < before

    def reset(self) -> None:
        with self._lock:
            self._store.clear()
flow_webhook_store = FlowWebhookStore()


class FlowCustomFieldStore:
    """Schema-enforced custom fields per flow.

    Each flow can have a set of named custom fields with a declared type.
    The store validates that values match the declared type on write.
    Field names must be slug-safe (alphanumeric + underscore, 1-64 chars).
    """

    MAX_FIELDS = 30
    _NAME_RE = re.compile(r"^[a-z_][a-z0-9_]{0,63}$")

    def __init__(self) -> None:
        self._schemas: dict[str, dict[str, str]] = {}    # flow_id → {name: type}
        self._values: dict[str, dict[str, Any]] = {}     # flow_id → {name: value}
        self._lock = threading.Lock()

    def _validate_value(self, field_type: str, value: Any) -> Any:
        if field_type == "string":
            if not isinstance(value, str):
                raise ValueError(f"Expected string, got {type(value).__name__}")
            return value
        elif field_type == "number":
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise ValueError(f"Expected number, got {type(value).__name__}")
            return value
        elif field_type == "boolean":
            if not isinstance(value, bool):
                raise ValueError(f"Expected boolean, got {type(value).__name__}")
            return value
        elif field_type == "date":
            if not isinstance(value, str):
                raise ValueError("date must be a string in ISO format")
            # Basic ISO date check
            try:
                datetime.fromisoformat(value)
            except ValueError as exc:
                raise ValueError(f"Invalid date: {value!r}") from exc
            return value
        raise ValueError(f"Unknown type: {field_type}")

    def define(self, flow_id: str, name: str, field_type: str) -> dict[str, Any]:
        """Create or update a field schema (does not affect existing value)."""
        if not self._NAME_RE.match(name):
            raise ValueError(f"Invalid field name: {name!r}")
        if field_type not in _CUSTOM_FIELD_TYPES:
            raise ValueError(f"Unknown field type: {field_type!r}")
        with self._lock:
            schemas = self._schemas.setdefault(flow_id, {})
            if name not in schemas and len(schemas) >= self.MAX_FIELDS:
                raise ValueError(f"Maximum of {self.MAX_FIELDS} custom fields exceeded")
            schemas[name] = field_type
            return {"flow_id": flow_id, "name": name, "type": field_type}

    def set_value(self, flow_id: str, name: str, value: Any) -> dict[str, Any]:
        with self._lock:
            field_type = self._schemas.get(flow_id, {}).get(name)
            if field_type is None:
                raise KeyError(f"Field {name!r} is not defined")
        coerced = self._validate_value(field_type, value)
        with self._lock:
            self._values.setdefault(flow_id, {})[name] = coerced
            return {"flow_id": flow_id, "name": name, "type": field_type, "value": coerced}

    def get_all(self, flow_id: str) -> list[dict[str, Any]]:
        with self._lock:
            schemas = self._schemas.get(flow_id, {})
            values = self._values.get(flow_id, {})
            return [
                {"name": n, "type": t, "value": values.get(n)}
                for n, t in sorted(schemas.items())
            ]

    def get_field(self, flow_id: str, name: str) -> dict[str, Any] | None:
        with self._lock:
            field_type = self._schemas.get(flow_id, {}).get(name)
            if field_type is None:
                return None
            value = self._values.get(flow_id, {}).get(name)
            return {"flow_id": flow_id, "name": name, "type": field_type, "value": value}

    def delete_field(self, flow_id: str, name: str) -> bool:
        with self._lock:
            schemas = self._schemas.get(flow_id, {})
            if name not in schemas:
                return False
            del schemas[name]
            self._values.get(flow_id, {}).pop(name, None)
            return True

    def reset(self) -> None:
        with self._lock:
            self._schemas.clear()
            self._values.clear()
flow_custom_field_store = FlowCustomFieldStore()


class FlowCollaboratorStore:
    """Manages named collaborator roles per flow.

    Each flow has a collaborator list: user (email) → role.
    The owner role is informational — there is no access enforcement here
    (that is the responsibility of workflow_permission_store).
    Multiple users per flow, max 100. A user can only have one role per flow.
    """

    MAX_COLLABORATORS = 100

    def __init__(self) -> None:
        self._store: dict[str, dict[str, str]] = {}  # flow_id → {user: role}
        self._lock = threading.Lock()

    def add(self, flow_id: str, user: str, role: str) -> dict[str, Any]:
        if role not in _COLLABORATOR_ROLES:
            raise ValueError(f"Invalid role: {role!r}")
        with self._lock:
            collab = self._store.setdefault(flow_id, {})
            if user not in collab and len(collab) >= self.MAX_COLLABORATORS:
                raise ValueError(f"Maximum of {self.MAX_COLLABORATORS} collaborators per flow exceeded")
            collab[user] = role
            return {"flow_id": flow_id, "user": user, "role": role}

    def list(self, flow_id: str) -> list[dict[str, Any]]:
        with self._lock:
            return [
                {"user": u, "role": r}
                for u, r in sorted(self._store.get(flow_id, {}).items())
            ]

    def get(self, flow_id: str, user: str) -> dict[str, Any] | None:
        with self._lock:
            role = self._store.get(flow_id, {}).get(user)
            if role is None:
                return None
            return {"flow_id": flow_id, "user": user, "role": role}

    def remove(self, flow_id: str, user: str) -> bool:
        with self._lock:
            collab = self._store.get(flow_id, {})
            if user not in collab:
                return False
            del collab[user]
            return True

    def reset(self) -> None:
        with self._lock:
            self._store.clear()
flow_collaborator_store = FlowCollaboratorStore()


class FlowEnvironmentStore:
    """Stores per-environment configuration overrides for a flow.

    Each flow can have up to 3 named environments (development, staging,
    production). Each environment stores a flat key-value config dict and
    tracks which is "active". Only one environment can be active at a time.
    """

    MAX_KEYS = 50

    def __init__(self) -> None:
        self._envs: dict[str, dict[str, Any]] = {}   # flow_id → {env_name: {config, active, updated_at}}
        self._lock = threading.Lock()

    def set(self, flow_id: str, env_name: str, config: dict[str, str]) -> dict[str, Any]:
        if env_name not in _ENV_NAMES:
            raise ValueError(f"Invalid environment name: {env_name!r}")
        if len(config) > self.MAX_KEYS:
            raise ValueError(f"Environment config exceeds maximum of {self.MAX_KEYS} keys")
        with self._lock:
            envs = self._envs.setdefault(flow_id, {})
            existing = envs.get(env_name, {})
            envs[env_name] = {
                "name": env_name,
                "config": dict(config),
                "active": existing.get("active", False),
                "created_at": existing.get("created_at", datetime.now(UTC).isoformat()),
                "updated_at": datetime.now(UTC).isoformat(),
            }
            return {"flow_id": flow_id, **envs[env_name]}

    def get(self, flow_id: str, env_name: str) -> dict[str, Any] | None:
        with self._lock:
            env = self._envs.get(flow_id, {}).get(env_name)
            if env is None:
                return None
            return {"flow_id": flow_id, **env}

    def list(self, flow_id: str) -> list[dict[str, Any]]:
        with self._lock:
            return [
                {"flow_id": flow_id, **v}
                for v in sorted(self._envs.get(flow_id, {}).values(), key=lambda e: e["name"])
            ]

    def activate(self, flow_id: str, env_name: str) -> dict[str, Any] | None:
        with self._lock:
            envs = self._envs.get(flow_id, {})
            if env_name not in envs:
                return None
            for name, env in envs.items():
                env["active"] = name == env_name
            return {"flow_id": flow_id, **envs[env_name]}

    def delete(self, flow_id: str, env_name: str) -> bool:
        with self._lock:
            envs = self._envs.get(flow_id, {})
            if env_name not in envs:
                return False
            del envs[env_name]
            return True

    def reset(self) -> None:
        with self._lock:
            self._envs.clear()
flow_environment_store = FlowEnvironmentStore()


class FlowNotifPrefStore:
    """Per-user, per-flow notification preference store.

    Each (flow_id, user) pair can specify which events they want notifications
    for and via which channels. Preferences are stored as-is; enforcement of
    actual delivery is downstream of this API.
    """

    def __init__(self) -> None:
        self._prefs: dict[tuple[str, str], dict[str, Any]] = {}  # (flow_id, user) → prefs
        self._lock = threading.Lock()

    def set(
        self,
        flow_id: str,
        user: str,
        events: dict[str, bool],
        channels: list[str],
    ) -> dict[str, Any]:
        unknown_events = set(events) - _NOTIF_EVENTS
        if unknown_events:
            raise ValueError(f"Unknown events: {sorted(unknown_events)}")
        unknown_channels = set(channels) - _NOTIF_CHANNELS
        if unknown_channels:
            raise ValueError(f"Unknown channels: {sorted(unknown_channels)}")
        with self._lock:
            self._prefs[(flow_id, user)] = {
                "events": dict(events),
                "channels": list(channels),
                "updated_at": datetime.now(UTC).isoformat(),
            }
            return {"flow_id": flow_id, "user": user, **self._prefs[(flow_id, user)]}

    def get(self, flow_id: str, user: str) -> dict[str, Any] | None:
        with self._lock:
            prefs = self._prefs.get((flow_id, user))
            if prefs is None:
                return None
            return {"flow_id": flow_id, "user": user, **prefs}

    def delete(self, flow_id: str, user: str) -> bool:
        with self._lock:
            if (flow_id, user) not in self._prefs:
                return False
            del self._prefs[(flow_id, user)]
            return True

    def reset(self) -> None:
        with self._lock:
            self._prefs.clear()
flow_notif_pref_store = FlowNotifPrefStore()


class FlowTimeoutStore:
    """Stores per-flow execution timeout configuration.

    When set, any run for the flow that exceeds the configured number of
    seconds should be terminated. The store is advisory — enforcement is
    downstream of this API.
    """

    def __init__(self) -> None:
        self._timeouts: dict[str, dict[str, Any]] = {}  # flow_id → {timeout_seconds, updated_at}
        self._lock = threading.Lock()

    def set(self, flow_id: str, timeout_seconds: int) -> dict[str, Any]:
        if not (_TIMEOUT_MIN <= timeout_seconds <= _TIMEOUT_MAX):
            raise ValueError(
                f"timeout_seconds must be between {_TIMEOUT_MIN} and {_TIMEOUT_MAX}"
            )
        with self._lock:
            self._timeouts[flow_id] = {
                "timeout_seconds": timeout_seconds,
                "updated_at": datetime.now(UTC).isoformat(),
            }
            return {"flow_id": flow_id, **self._timeouts[flow_id]}

    def get(self, flow_id: str) -> dict[str, Any] | None:
        with self._lock:
            cfg = self._timeouts.get(flow_id)
            if cfg is None:
                return None
            return {"flow_id": flow_id, **cfg}

    def delete(self, flow_id: str) -> bool:
        with self._lock:
            if flow_id not in self._timeouts:
                return False
            del self._timeouts[flow_id]
            return True

    def reset(self) -> None:
        with self._lock:
            self._timeouts.clear()
flow_timeout_store = FlowTimeoutStore()


class FlowRetryPolicyStore:
    """Stores per-flow default retry policy for node execution failures.

    Fields:
      max_retries       — 0 (no retry) to 10
      retry_delay_s     — initial delay between retries, 0–300 seconds
      backoff_multiplier — exponential backoff factor, 1.0–10.0 (1.0 = constant delay)

    This policy applies as a default when individual nodes do not have
    their own retry config. Enforcement is downstream of this API.
    """

    def __init__(self) -> None:
        self._policies: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def set(
        self,
        flow_id: str,
        max_retries: int,
        retry_delay_s: int,
        backoff_multiplier: float,
    ) -> dict[str, Any]:
        if not (0 <= max_retries <= _RETRY_MAX_RETRIES_MAX):
            raise ValueError(f"max_retries must be 0–{_RETRY_MAX_RETRIES_MAX}")
        if not (0 <= retry_delay_s <= _RETRY_DELAY_MAX):
            raise ValueError(f"retry_delay_s must be 0–{_RETRY_DELAY_MAX}")
        if not (1.0 <= backoff_multiplier <= _RETRY_BACKOFF_MAX):
            raise ValueError(f"backoff_multiplier must be 1.0–{_RETRY_BACKOFF_MAX}")
        with self._lock:
            self._policies[flow_id] = {
                "max_retries": max_retries,
                "retry_delay_s": retry_delay_s,
                "backoff_multiplier": backoff_multiplier,
                "updated_at": datetime.now(UTC).isoformat(),
            }
            return {"flow_id": flow_id, **self._policies[flow_id]}

    def get(self, flow_id: str) -> dict[str, Any] | None:
        with self._lock:
            policy = self._policies.get(flow_id)
            if policy is None:
                return None
            return {"flow_id": flow_id, **policy}

    def delete(self, flow_id: str) -> bool:
        with self._lock:
            if flow_id not in self._policies:
                return False
            del self._policies[flow_id]
            return True

    def reset(self) -> None:
        with self._lock:
            self._policies.clear()
flow_retry_policy_store = FlowRetryPolicyStore()


class FlowConcurrencyStore:
    """Stores per-flow maximum concurrent execution limit.

    When set, no more than max_concurrent runs of the flow should be
    active at once. Enforcement is downstream of this API.
    """

    def __init__(self) -> None:
        self._limits: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def set(self, flow_id: str, max_concurrent: int) -> dict[str, Any]:
        if not (_CONCURRENCY_MIN <= max_concurrent <= _CONCURRENCY_MAX):
            raise ValueError(
                f"max_concurrent must be between {_CONCURRENCY_MIN} and {_CONCURRENCY_MAX}"
            )
        with self._lock:
            self._limits[flow_id] = {
                "max_concurrent": max_concurrent,
                "updated_at": datetime.now(UTC).isoformat(),
            }
            return {"flow_id": flow_id, **self._limits[flow_id]}

    def get(self, flow_id: str) -> dict[str, Any] | None:
        with self._lock:
            cfg = self._limits.get(flow_id)
            if cfg is None:
                return None
            return {"flow_id": flow_id, **cfg}

    def delete(self, flow_id: str) -> bool:
        with self._lock:
            if flow_id not in self._limits:
                return False
            del self._limits[flow_id]
            return True

    def reset(self) -> None:
        with self._lock:
            self._limits.clear()
flow_concurrency_store = FlowConcurrencyStore()


class FlowInputSchemaStore:
    """Stores a JSON Schema definition for validating flow run input payloads.

    Only stores the schema as-is; input validation against the schema is
    performed downstream during run execution. The schema must be a JSON
    object (dict).
    """

    def __init__(self) -> None:
        self._schemas: dict[str, dict[str, Any]] = {}  # flow_id → {schema, updated_at}
        self._lock = threading.Lock()

    def set(self, flow_id: str, schema: dict[str, Any]) -> dict[str, Any]:
        import json as _json

        serialized = _json.dumps(schema)
        if len(serialized) > _INPUT_SCHEMA_MAX_BYTES:
            raise ValueError(
                f"Schema exceeds maximum size of {_INPUT_SCHEMA_MAX_BYTES} bytes"
            )
        if not isinstance(schema, dict):
            raise ValueError("Schema must be a JSON object")
        with self._lock:
            self._schemas[flow_id] = {
                "schema": schema,
                "updated_at": datetime.now(UTC).isoformat(),
            }
            return {"flow_id": flow_id, **self._schemas[flow_id]}

    def get(self, flow_id: str) -> dict[str, Any] | None:
        with self._lock:
            entry = self._schemas.get(flow_id)
            if entry is None:
                return None
            return {"flow_id": flow_id, **entry}

    def delete(self, flow_id: str) -> bool:
        with self._lock:
            if flow_id not in self._schemas:
                return False
            del self._schemas[flow_id]
            return True

    def reset(self) -> None:
        with self._lock:
            self._schemas.clear()
flow_input_schema_store = FlowInputSchemaStore()


class FlowOutputSchemaStore:
    """Stores a JSON Schema definition describing a flow's output payload.

    Intended for documentation and downstream consumer validation. The schema
    must be a JSON object. Enforcement is upstream of this API.
    """

    def __init__(self) -> None:
        self._schemas: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def set(self, flow_id: str, schema: dict[str, Any]) -> dict[str, Any]:
        import json as _json

        if not isinstance(schema, dict):
            raise ValueError("Schema must be a JSON object")
        serialized = _json.dumps(schema)
        if len(serialized) > _OUTPUT_SCHEMA_MAX_BYTES:
            raise ValueError(
                f"Schema exceeds maximum size of {_OUTPUT_SCHEMA_MAX_BYTES} bytes"
            )
        with self._lock:
            self._schemas[flow_id] = {
                "schema": schema,
                "updated_at": datetime.now(UTC).isoformat(),
            }
            return {"flow_id": flow_id, **self._schemas[flow_id]}

    def get(self, flow_id: str) -> dict[str, Any] | None:
        with self._lock:
            entry = self._schemas.get(flow_id)
            if entry is None:
                return None
            return {"flow_id": flow_id, **entry}

    def delete(self, flow_id: str) -> bool:
        with self._lock:
            if flow_id not in self._schemas:
                return False
            del self._schemas[flow_id]
            return True

    def reset(self) -> None:
        with self._lock:
            self._schemas.clear()
flow_output_schema_store = FlowOutputSchemaStore()


class FlowContactStore:
    """Stores per-flow owner/point-of-contact information.

    Fields are all optional strings — name, email, slack_handle, team.
    Intended for discoverability and incident response escalation.
    """

    def __init__(self) -> None:
        self._contacts: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def set(
        self,
        flow_id: str,
        name: str,
        email: str,
        slack_handle: str,
        team: str,
    ) -> dict[str, Any]:
        with self._lock:
            self._contacts[flow_id] = {
                "name": name,
                "email": email,
                "slack_handle": slack_handle,
                "team": team,
                "updated_at": datetime.now(UTC).isoformat(),
            }
            return {"flow_id": flow_id, **self._contacts[flow_id]}

    def get(self, flow_id: str) -> dict[str, Any] | None:
        with self._lock:
            contact = self._contacts.get(flow_id)
            if contact is None:
                return None
            return {"flow_id": flow_id, **contact}

    def delete(self, flow_id: str) -> bool:
        with self._lock:
            if flow_id not in self._contacts:
                return False
            del self._contacts[flow_id]
            return True

    def reset(self) -> None:
        with self._lock:
            self._contacts.clear()
flow_contact_store = FlowContactStore()


class FlowCostConfigStore:
    """Stores per-flow cost estimation configuration.

    Fields:
      cost_per_run   — estimated monetary cost per execution (non-negative float)
      currency       — ISO 4217 currency code (USD, EUR, GBP, JPY, AUD, CAD)
      billing_note   — freeform annotation (max 500 chars)

    Intended for cost dashboards and pre-run cost estimation UI.
    """

    def __init__(self) -> None:
        self._configs: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def set(
        self,
        flow_id: str,
        cost_per_run: float,
        currency: str,
        billing_note: str,
    ) -> dict[str, Any]:
        if cost_per_run < 0:
            raise ValueError("cost_per_run must be non-negative")
        if currency not in _COST_CURRENCIES:
            raise ValueError(f"Unsupported currency: {currency!r}")
        if len(billing_note) > 500:
            raise ValueError("billing_note exceeds 500 characters")
        with self._lock:
            self._configs[flow_id] = {
                "cost_per_run": cost_per_run,
                "currency": currency,
                "billing_note": billing_note,
                "updated_at": datetime.now(UTC).isoformat(),
            }
            return {"flow_id": flow_id, **self._configs[flow_id]}

    def get(self, flow_id: str) -> dict[str, Any] | None:
        with self._lock:
            cfg = self._configs.get(flow_id)
            if cfg is None:
                return None
            return {"flow_id": flow_id, **cfg}

    def delete(self, flow_id: str) -> bool:
        with self._lock:
            if flow_id not in self._configs:
                return False
            del self._configs[flow_id]
            return True

    def reset(self) -> None:
        with self._lock:
            self._configs.clear()
flow_cost_config_store = FlowCostConfigStore()


class FlowVisibilityStore:
    """Stores per-flow visibility setting.

    Levels:
      private  — visible only to the flow owner
      internal — visible to all authenticated users in the organization
      public   — visible to anyone (including unauthenticated users)

    Enforcement is downstream. New flows default to "private" (not stored
    until explicitly set).
    """

    def __init__(self) -> None:
        self._visibility: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def set(self, flow_id: str, level: str) -> dict[str, Any]:
        if level not in _VISIBILITY_LEVELS:
            raise ValueError(f"Invalid visibility level: {level!r}")
        with self._lock:
            self._visibility[flow_id] = {
                "visibility": level,
                "updated_at": datetime.now(UTC).isoformat(),
            }
            return {"flow_id": flow_id, **self._visibility[flow_id]}

    def get(self, flow_id: str) -> dict[str, Any] | None:
        with self._lock:
            entry = self._visibility.get(flow_id)
            if entry is None:
                return None
            return {"flow_id": flow_id, **entry}

    def delete(self, flow_id: str) -> bool:
        with self._lock:
            if flow_id not in self._visibility:
                return False
            del self._visibility[flow_id]
            return True

    def reset(self) -> None:
        with self._lock:
            self._visibility.clear()
flow_visibility_store = FlowVisibilityStore()


class FlowVersionLockStore:
    """Pins a flow to a specific version string, preventing auto-updates.

    Fields:
      locked_version — semver or arbitrary version string (max 50 chars)
      reason         — freeform annotation (max 500 chars)
      locked_by      — user who set the lock
      locked_at      — ISO timestamp
    """

    def __init__(self) -> None:
        self._locks: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def lock(
        self, flow_id: str, locked_version: str, reason: str, locked_by: str
    ) -> dict[str, Any]:
        if not locked_version or len(locked_version) > 50:
            raise ValueError("locked_version must be 1–50 characters")
        if len(reason) > 500:
            raise ValueError("reason exceeds 500 characters")
        with self._lock:
            self._locks[flow_id] = {
                "locked_version": locked_version,
                "reason": reason,
                "locked_by": locked_by,
                "locked_at": datetime.now(UTC).isoformat(),
            }
            return {"flow_id": flow_id, **self._locks[flow_id]}

    def get(self, flow_id: str) -> dict[str, Any] | None:
        with self._lock:
            entry = self._locks.get(flow_id)
            if entry is None:
                return None
            return {"flow_id": flow_id, **entry}

    def unlock(self, flow_id: str) -> bool:
        with self._lock:
            if flow_id not in self._locks:
                return False
            del self._locks[flow_id]
            return True

    def reset(self) -> None:
        with self._lock:
            self._locks.clear()
flow_version_lock_store = FlowVersionLockStore()


class FlowApprovalStore:
    """Tracks per-flow deployment approval gate.

    Lifecycle:
      POST /request  — submitter opens an approval request (→ pending)
      POST /approve  — reviewer approves                   (→ approved)
      POST /reject   — reviewer rejects with reason        (→ rejected)
      GET  /         — current approval record
      DELETE /       — clear the approval record
    """

    def __init__(self) -> None:
        self._approvals: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def request(self, flow_id: str, submitted_by: str, note: str) -> dict[str, Any]:
        if len(note) > 500:
            raise ValueError("note exceeds 500 characters")
        with self._lock:
            self._approvals[flow_id] = {
                "status": "pending",
                "submitted_by": submitted_by,
                "note": note,
                "reviewer": None,
                "review_comment": None,
                "requested_at": datetime.now(UTC).isoformat(),
                "reviewed_at": None,
            }
            return {"flow_id": flow_id, **self._approvals[flow_id]}

    def _review(
        self,
        flow_id: str,
        status: str,
        reviewer: str,
        comment: str,
    ) -> dict[str, Any] | None:
        with self._lock:
            approval = self._approvals.get(flow_id)
            if approval is None:
                return None
            approval.update(
                {
                    "status": status,
                    "reviewer": reviewer,
                    "review_comment": comment,
                    "reviewed_at": datetime.now(UTC).isoformat(),
                }
            )
            return {"flow_id": flow_id, **approval}

    def approve(self, flow_id: str, reviewer: str, comment: str) -> dict[str, Any] | None:
        return self._review(flow_id, "approved", reviewer, comment)

    def reject(self, flow_id: str, reviewer: str, comment: str) -> dict[str, Any] | None:
        return self._review(flow_id, "rejected", reviewer, comment)

    def get(self, flow_id: str) -> dict[str, Any] | None:
        with self._lock:
            approval = self._approvals.get(flow_id)
            if approval is None:
                return None
            return {"flow_id": flow_id, **approval}

    def clear(self, flow_id: str) -> bool:
        with self._lock:
            if flow_id not in self._approvals:
                return False
            del self._approvals[flow_id]
            return True

    def reset(self) -> None:
        with self._lock:
            self._approvals.clear()
flow_approval_store = FlowApprovalStore()


class FlowTriggerConfigStore:
    """Store trigger configuration for a flow (what initiates execution)."""

    def __init__(self) -> None:
        self._configs: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def set(self, flow_id: str, trigger_type: str, config: dict[str, Any]) -> dict[str, Any]:
        if trigger_type not in _TRIGGER_TYPES:
            raise ValueError(f"trigger_type must be one of {sorted(_TRIGGER_TYPES)}")
        with self._lock:
            self._configs[flow_id] = {
                "trigger_type": trigger_type,
                "config": config,
                "updated_at": datetime.now(UTC).isoformat(),
            }
            return {"flow_id": flow_id, **self._configs[flow_id]}

    def get(self, flow_id: str) -> dict[str, Any] | None:
        with self._lock:
            rec = self._configs.get(flow_id)
            if rec is None:
                return None
            return {"flow_id": flow_id, **rec}

    def delete(self, flow_id: str) -> bool:
        with self._lock:
            return self._configs.pop(flow_id, None) is not None

    def reset(self) -> None:
        with self._lock:
            self._configs.clear()
flow_trigger_config_store = FlowTriggerConfigStore()


class FlowRunRetentionStore:
    """Store per-flow retention policy for run history records."""

    _MIN_DAYS: int = 1
    _MAX_DAYS: int = 365

    def __init__(self) -> None:
        self._policies: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def set(self, flow_id: str, retain_days: int, max_runs: int | None) -> dict[str, Any]:
        if not (self._MIN_DAYS <= retain_days <= self._MAX_DAYS):
            raise ValueError(f"retain_days must be between {self._MIN_DAYS} and {self._MAX_DAYS}")
        if max_runs is not None and max_runs < 1:
            raise ValueError("max_runs must be at least 1 if provided")
        with self._lock:
            self._policies[flow_id] = {
                "retain_days": retain_days,
                "max_runs": max_runs,
                "updated_at": datetime.now(UTC).isoformat(),
            }
            return {"flow_id": flow_id, **self._policies[flow_id]}

    def get(self, flow_id: str) -> dict[str, Any] | None:
        with self._lock:
            rec = self._policies.get(flow_id)
            if rec is None:
                return None
            return {"flow_id": flow_id, **rec}

    def delete(self, flow_id: str) -> bool:
        with self._lock:
            return self._policies.pop(flow_id, None) is not None

    def reset(self) -> None:
        with self._lock:
            self._policies.clear()
flow_run_retention_store = FlowRunRetentionStore()


class FlowErrorAlertStore:
    """Store error alert recipients for a flow."""

    _MAX_RECIPIENTS: int = 20

    def __init__(self) -> None:
        self._alerts: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def set(self, flow_id: str, emails: list[str], slack_channels: list[str]) -> dict[str, Any]:
        if len(emails) > self._MAX_RECIPIENTS:
            raise ValueError(f"emails exceeds maximum of {self._MAX_RECIPIENTS}")
        if len(slack_channels) > self._MAX_RECIPIENTS:
            raise ValueError(f"slack_channels exceeds maximum of {self._MAX_RECIPIENTS}")
        with self._lock:
            self._alerts[flow_id] = {
                "emails": list(emails),
                "slack_channels": list(slack_channels),
                "updated_at": datetime.now(UTC).isoformat(),
            }
            return {"flow_id": flow_id, **self._alerts[flow_id]}

    def get(self, flow_id: str) -> dict[str, Any] | None:
        with self._lock:
            rec = self._alerts.get(flow_id)
            if rec is None:
                return None
            return {"flow_id": flow_id, **rec}

    def delete(self, flow_id: str) -> bool:
        with self._lock:
            return self._alerts.pop(flow_id, None) is not None

    def reset(self) -> None:
        with self._lock:
            self._alerts.clear()
flow_error_alert_store = FlowErrorAlertStore()


class FlowOutputDestinationStore:
    """Store output destination configuration for a flow."""

    def __init__(self) -> None:
        self._destinations: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def set(self, flow_id: str, dest_type: str, config: dict[str, Any]) -> dict[str, Any]:
        if dest_type not in _OUTPUT_DEST_TYPES:
            raise ValueError(f"dest_type must be one of {sorted(_OUTPUT_DEST_TYPES)}")
        with self._lock:
            self._destinations[flow_id] = {
                "dest_type": dest_type,
                "config": config,
                "updated_at": datetime.now(UTC).isoformat(),
            }
            return {"flow_id": flow_id, **self._destinations[flow_id]}

    def get(self, flow_id: str) -> dict[str, Any] | None:
        with self._lock:
            rec = self._destinations.get(flow_id)
            if rec is None:
                return None
            return {"flow_id": flow_id, **rec}

    def delete(self, flow_id: str) -> bool:
        with self._lock:
            return self._destinations.pop(flow_id, None) is not None

    def reset(self) -> None:
        with self._lock:
            self._destinations.clear()
flow_output_destination_store = FlowOutputDestinationStore()


class FlowResourceLimitStore:
    """Store resource limit configuration for a flow."""

    _MAX_MEMORY_MB: int = 16384  # 16 GB
    _MAX_CPU_MILLICORES: int = 64000  # 64 vCPUs
    _MAX_TIMEOUT_S: int = 86400  # 24 hours

    def __init__(self) -> None:
        self._limits: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def set(
        self,
        flow_id: str,
        memory_mb: int | None,
        cpu_millicores: int | None,
        timeout_s: int | None,
    ) -> dict[str, Any]:
        if memory_mb is not None and not (1 <= memory_mb <= self._MAX_MEMORY_MB):
            raise ValueError(f"memory_mb must be between 1 and {self._MAX_MEMORY_MB}")
        if cpu_millicores is not None and not (1 <= cpu_millicores <= self._MAX_CPU_MILLICORES):
            raise ValueError(f"cpu_millicores must be between 1 and {self._MAX_CPU_MILLICORES}")
        if timeout_s is not None and not (1 <= timeout_s <= self._MAX_TIMEOUT_S):
            raise ValueError(f"timeout_s must be between 1 and {self._MAX_TIMEOUT_S}")
        with self._lock:
            self._limits[flow_id] = {
                "memory_mb": memory_mb,
                "cpu_millicores": cpu_millicores,
                "timeout_s": timeout_s,
                "updated_at": datetime.now(UTC).isoformat(),
            }
            return {"flow_id": flow_id, **self._limits[flow_id]}

    def get(self, flow_id: str) -> dict[str, Any] | None:
        with self._lock:
            rec = self._limits.get(flow_id)
            if rec is None:
                return None
            return {"flow_id": flow_id, **rec}

    def delete(self, flow_id: str) -> bool:
        with self._lock:
            return self._limits.pop(flow_id, None) is not None

    def reset(self) -> None:
        with self._lock:
            self._limits.clear()
flow_resource_limit_store = FlowResourceLimitStore()


class FlowAclStore:
    """Store per-user ACL entries for a flow."""

    def __init__(self) -> None:
        self._acls: dict[str, dict[str, dict[str, Any]]] = {}
        self._lock = threading.Lock()

    def grant(self, flow_id: str, user: str, permissions: list[str]) -> dict[str, Any]:
        invalid = set(permissions) - _ACL_PERMISSIONS
        if invalid:
            raise ValueError(f"invalid permissions: {sorted(invalid)}")
        with self._lock:
            if flow_id not in self._acls:
                self._acls[flow_id] = {}
            self._acls[flow_id][user] = {
                "permissions": sorted(set(permissions)),
                "granted_at": datetime.now(UTC).isoformat(),
            }
            return {"flow_id": flow_id, "user": user, **self._acls[flow_id][user]}

    def revoke(self, flow_id: str, user: str) -> bool:
        with self._lock:
            flow_acl = self._acls.get(flow_id)
            if flow_acl is None:
                return False
            return flow_acl.pop(user, None) is not None

    def get(self, flow_id: str, user: str) -> dict[str, Any] | None:
        with self._lock:
            flow_acl = self._acls.get(flow_id, {})
            entry = flow_acl.get(user)
            if entry is None:
                return None
            return {"flow_id": flow_id, "user": user, **entry}

    def list_entries(self, flow_id: str) -> list[dict[str, Any]]:
        with self._lock:
            return [
                {"flow_id": flow_id, "user": u, **e}
                for u, e in self._acls.get(flow_id, {}).items()
            ]

    def reset(self) -> None:
        with self._lock:
            self._acls.clear()
flow_acl_store = FlowAclStore()


class FlowExecutionModeStore:
    """Store execution mode configuration for a flow."""

    def __init__(self) -> None:
        self._modes: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def set(self, flow_id: str, mode: str, debug: bool) -> dict[str, Any]:
        if mode not in _EXECUTION_MODES:
            raise ValueError(f"mode must be one of {sorted(_EXECUTION_MODES)}")
        with self._lock:
            self._modes[flow_id] = {
                "mode": mode,
                "debug": debug,
                "updated_at": datetime.now(UTC).isoformat(),
            }
            return {"flow_id": flow_id, **self._modes[flow_id]}

    def get(self, flow_id: str) -> dict[str, Any] | None:
        with self._lock:
            rec = self._modes.get(flow_id)
            if rec is None:
                return None
            return {"flow_id": flow_id, **rec}

    def delete(self, flow_id: str) -> bool:
        with self._lock:
            return self._modes.pop(flow_id, None) is not None

    def reset(self) -> None:
        with self._lock:
            self._modes.clear()
flow_execution_mode_store = FlowExecutionModeStore()


class FlowInputValidationStore:
    """Store input validation rules for a flow."""

    _MAX_RULES: int = 50

    def __init__(self) -> None:
        self._rules: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def set(self, flow_id: str, rules: list[dict[str, Any]], strict: bool) -> dict[str, Any]:
        if len(rules) > self._MAX_RULES:
            raise ValueError(f"rules exceeds maximum of {self._MAX_RULES}")
        with self._lock:
            self._rules[flow_id] = {
                "rules": rules,
                "strict": strict,
                "rule_count": len(rules),
                "updated_at": datetime.now(UTC).isoformat(),
            }
            return {"flow_id": flow_id, **self._rules[flow_id]}

    def get(self, flow_id: str) -> dict[str, Any] | None:
        with self._lock:
            rec = self._rules.get(flow_id)
            if rec is None:
                return None
            return {"flow_id": flow_id, **rec}

    def delete(self, flow_id: str) -> bool:
        with self._lock:
            return self._rules.pop(flow_id, None) is not None

    def reset(self) -> None:
        with self._lock:
            self._rules.clear()
flow_input_validation_store = FlowInputValidationStore()


class FlowCachingConfigStore:
    """Store caching configuration for a flow."""

    _MAX_TTL: int = 86400  # 24 hours
    _MAX_KEY_FIELDS: int = 10

    def __init__(self) -> None:
        self._configs: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def set(self, flow_id: str, enabled: bool, ttl_seconds: int, key_fields: list[str]) -> dict[str, Any]:
        if not (0 <= ttl_seconds <= self._MAX_TTL):
            raise ValueError(f"ttl_seconds must be between 0 and {self._MAX_TTL}")
        if len(key_fields) > self._MAX_KEY_FIELDS:
            raise ValueError(f"key_fields exceeds maximum of {self._MAX_KEY_FIELDS}")
        with self._lock:
            self._configs[flow_id] = {
                "enabled": enabled,
                "ttl_seconds": ttl_seconds,
                "key_fields": list(key_fields),
                "updated_at": datetime.now(UTC).isoformat(),
            }
            return {"flow_id": flow_id, **self._configs[flow_id]}

    def get(self, flow_id: str) -> dict[str, Any] | None:
        with self._lock:
            rec = self._configs.get(flow_id)
            if rec is None:
                return None
            return {"flow_id": flow_id, **rec}

    def delete(self, flow_id: str) -> bool:
        with self._lock:
            return self._configs.pop(flow_id, None) is not None

    def reset(self) -> None:
        with self._lock:
            self._configs.clear()
flow_caching_config_store = FlowCachingConfigStore()


class FlowCircuitBreakerStore:
    """Store circuit breaker configuration for a flow."""

    _MAX_THRESHOLD: int = 100
    _MAX_RECOVERY_S: int = 3600

    def __init__(self) -> None:
        self._configs: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def set(
        self,
        flow_id: str,
        enabled: bool,
        failure_threshold: int,
        recovery_timeout_s: int,
    ) -> dict[str, Any]:
        if not (1 <= failure_threshold <= self._MAX_THRESHOLD):
            raise ValueError(f"failure_threshold must be between 1 and {self._MAX_THRESHOLD}")
        if not (1 <= recovery_timeout_s <= self._MAX_RECOVERY_S):
            raise ValueError(f"recovery_timeout_s must be between 1 and {self._MAX_RECOVERY_S}")
        with self._lock:
            self._configs[flow_id] = {
                "enabled": enabled,
                "failure_threshold": failure_threshold,
                "recovery_timeout_s": recovery_timeout_s,
                "state": "closed",
                "updated_at": datetime.now(UTC).isoformat(),
            }
            return {"flow_id": flow_id, **self._configs[flow_id]}

    def get(self, flow_id: str) -> dict[str, Any] | None:
        with self._lock:
            rec = self._configs.get(flow_id)
            if rec is None:
                return None
            return {"flow_id": flow_id, **rec}

    def delete(self, flow_id: str) -> bool:
        with self._lock:
            return self._configs.pop(flow_id, None) is not None

    def reset(self) -> None:
        with self._lock:
            self._configs.clear()
flow_circuit_breaker_store = FlowCircuitBreakerStore()


class FlowObservabilityConfigStore:
    """Store observability configuration for a flow (traces, metrics, logs)."""

    def __init__(self) -> None:
        self._configs: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def set(
        self,
        flow_id: str,
        traces_enabled: bool,
        metrics_enabled: bool,
        logs_enabled: bool,
        sample_rate: float,
    ) -> dict[str, Any]:
        if not (0.0 <= sample_rate <= 1.0):
            raise ValueError("sample_rate must be between 0.0 and 1.0")
        with self._lock:
            self._configs[flow_id] = {
                "traces_enabled": traces_enabled,
                "metrics_enabled": metrics_enabled,
                "logs_enabled": logs_enabled,
                "sample_rate": sample_rate,
                "updated_at": datetime.now(UTC).isoformat(),
            }
            return {"flow_id": flow_id, **self._configs[flow_id]}

    def get(self, flow_id: str) -> dict[str, Any] | None:
        with self._lock:
            rec = self._configs.get(flow_id)
            if rec is None:
                return None
            return {"flow_id": flow_id, **rec}

    def delete(self, flow_id: str) -> bool:
        with self._lock:
            return self._configs.pop(flow_id, None) is not None

    def reset(self) -> None:
        with self._lock:
            self._configs.clear()
flow_observability_config_store = FlowObservabilityConfigStore()


class FlowMaintenanceWindowStore:
    """Store maintenance window configuration for a flow."""

    _MAX_REASON_LEN: int = 500

    def __init__(self) -> None:
        self._windows: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def set(
        self,
        flow_id: str,
        start_iso: str,
        end_iso: str,
        reason: str,
    ) -> dict[str, Any]:
        if len(reason) > self._MAX_REASON_LEN:
            raise ValueError(f"reason exceeds {self._MAX_REASON_LEN} characters")
        with self._lock:
            self._windows[flow_id] = {
                "start": start_iso,
                "end": end_iso,
                "reason": reason,
                "active": True,
                "updated_at": datetime.now(UTC).isoformat(),
            }
            return {"flow_id": flow_id, **self._windows[flow_id]}

    def get(self, flow_id: str) -> dict[str, Any] | None:
        with self._lock:
            rec = self._windows.get(flow_id)
            if rec is None:
                return None
            return {"flow_id": flow_id, **rec}

    def delete(self, flow_id: str) -> bool:
        with self._lock:
            return self._windows.pop(flow_id, None) is not None

    def reset(self) -> None:
        with self._lock:
            self._windows.clear()
flow_maintenance_window_store = FlowMaintenanceWindowStore()


class FlowGeoRestrictionStore:
    """Store geographic restriction configuration for a flow."""

    _MAX_REGIONS: int = 50

    def __init__(self) -> None:
        self._restrictions: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def set(self, flow_id: str, mode: str, regions: list[str]) -> dict[str, Any]:
        if mode not in _GEO_MODES:
            raise ValueError(f"mode must be one of {sorted(_GEO_MODES)}")
        if len(regions) > self._MAX_REGIONS:
            raise ValueError(f"regions exceeds maximum of {self._MAX_REGIONS}")
        with self._lock:
            self._restrictions[flow_id] = {
                "mode": mode,
                "regions": sorted(set(regions)),
                "updated_at": datetime.now(UTC).isoformat(),
            }
            return {"flow_id": flow_id, **self._restrictions[flow_id]}

    def get(self, flow_id: str) -> dict[str, Any] | None:
        with self._lock:
            rec = self._restrictions.get(flow_id)
            if rec is None:
                return None
            return {"flow_id": flow_id, **rec}

    def delete(self, flow_id: str) -> bool:
        with self._lock:
            return self._restrictions.pop(flow_id, None) is not None

    def reset(self) -> None:
        with self._lock:
            self._restrictions.clear()
flow_geo_restriction_store = FlowGeoRestrictionStore()


class FlowIpAllowlistStore:
    """Store IP allowlist for a flow (CIDR notation supported)."""

    _MAX_ENTRIES: int = 100

    def __init__(self) -> None:
        self._lists: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def set(self, flow_id: str, enabled: bool, cidrs: list[str]) -> dict[str, Any]:
        if len(cidrs) > self._MAX_ENTRIES:
            raise ValueError(f"cidrs exceeds maximum of {self._MAX_ENTRIES}")
        with self._lock:
            self._lists[flow_id] = {
                "enabled": enabled,
                "cidrs": list(dict.fromkeys(cidrs)),  # deduplicate preserving order
                "updated_at": datetime.now(UTC).isoformat(),
            }
            return {"flow_id": flow_id, **self._lists[flow_id]}

    def get(self, flow_id: str) -> dict[str, Any] | None:
        with self._lock:
            rec = self._lists.get(flow_id)
            if rec is None:
                return None
            return {"flow_id": flow_id, **rec}

    def delete(self, flow_id: str) -> bool:
        with self._lock:
            return self._lists.pop(flow_id, None) is not None

    def reset(self) -> None:
        with self._lock:
            self._lists.clear()
flow_ip_allowlist_store = FlowIpAllowlistStore()


class FlowDataClassificationStore:
    def __init__(self) -> None:
        self._records: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def set(self, flow_id: str, level: str, pii_flag: bool) -> dict[str, Any]:
        if level not in _DATA_CLASSIFICATION_LEVELS:
            raise ValueError(f"level must be one of {sorted(_DATA_CLASSIFICATION_LEVELS)}")
        with self._lock:
            self._records[flow_id] = {
                "level": level,
                "pii_flag": pii_flag,
                "updated_at": datetime.now(UTC).isoformat(),
            }
            return {"flow_id": flow_id, **self._records[flow_id]}

    def get(self, flow_id: str) -> dict[str, Any] | None:
        with self._lock:
            rec = self._records.get(flow_id)
            return {"flow_id": flow_id, **rec} if rec else None

    def delete(self, flow_id: str) -> bool:
        with self._lock:
            if flow_id not in self._records:
                return False
            del self._records[flow_id]
            return True

    def reset(self) -> None:
        with self._lock:
            self._records.clear()
flow_data_classification_store = FlowDataClassificationStore()


class FlowNotificationChannelStore:
    _MAX_CHANNELS: int = 20

    def __init__(self) -> None:
        self._channels: dict[str, dict[str, dict[str, Any]]] = {}
        self._lock = threading.Lock()

    def create(
        self,
        flow_id: str,
        channel_type: str,
        target: str,
        events: list[str],
        enabled: bool,
    ) -> dict[str, Any]:
        if channel_type not in _NOTIF_CHANNEL_TYPES:
            raise ValueError(f"type must be one of {sorted(_NOTIF_CHANNEL_TYPES)}")
        invalid = set(events) - _NOTIF_CHANNEL_EVENTS
        if invalid:
            raise ValueError(f"invalid events: {sorted(invalid)}")
        with self._lock:
            flow_channels = self._channels.setdefault(flow_id, {})
            if len(flow_channels) >= self._MAX_CHANNELS:
                raise ValueError(f"max {self._MAX_CHANNELS} channels per flow exceeded")
            channel_id = uuid.uuid4().hex
            record: dict[str, Any] = {
                "channel_id": channel_id,
                "flow_id": flow_id,
                "type": channel_type,
                "target": target,
                "events": sorted(set(events)),
                "enabled": enabled,
                "created_at": datetime.now(UTC).isoformat(),
            }
            flow_channels[channel_id] = record
            return dict(record)

    def list(self, flow_id: str) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(v) for v in self._channels.get(flow_id, {}).values()]

    def get(self, flow_id: str, channel_id: str) -> dict[str, Any] | None:
        with self._lock:
            ch = self._channels.get(flow_id, {}).get(channel_id)
            return dict(ch) if ch else None

    def delete(self, flow_id: str, channel_id: str) -> bool:
        with self._lock:
            flow_channels = self._channels.get(flow_id, {})
            if channel_id not in flow_channels:
                return False
            del flow_channels[channel_id]
            return True

    def reset(self) -> None:
        with self._lock:
            self._channels.clear()
flow_notification_channel_store = FlowNotificationChannelStore()


class FlowFeatureFlagStore:
    _MAX_FLAGS: int = 50

    def __init__(self) -> None:
        self._flags: dict[str, dict[str, dict[str, Any]]] = {}
        self._lock = threading.Lock()

    def set(
        self,
        flow_id: str,
        flag_name: str,
        enabled: bool,
        rollout_percentage: int,
        description: str,
    ) -> dict[str, Any]:
        if not (0 <= rollout_percentage <= 100):
            raise ValueError("rollout_percentage must be 0-100")
        with self._lock:
            flow_flags = self._flags.setdefault(flow_id, {})
            if flag_name not in flow_flags and len(flow_flags) >= self._MAX_FLAGS:
                raise ValueError(f"max {self._MAX_FLAGS} feature flags per flow exceeded")
            record: dict[str, Any] = {
                "flag_name": flag_name,
                "flow_id": flow_id,
                "enabled": enabled,
                "rollout_percentage": rollout_percentage,
                "description": description,
                "updated_at": datetime.now(UTC).isoformat(),
            }
            flow_flags[flag_name] = record
            return dict(record)

    def get(self, flow_id: str, flag_name: str) -> dict[str, Any] | None:
        with self._lock:
            rec = self._flags.get(flow_id, {}).get(flag_name)
            return dict(rec) if rec else None

    def list(self, flow_id: str) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(v) for v in self._flags.get(flow_id, {}).values()]

    def delete(self, flow_id: str, flag_name: str) -> bool:
        with self._lock:
            flow_flags = self._flags.get(flow_id, {})
            if flag_name not in flow_flags:
                return False
            del flow_flags[flag_name]
            return True

    def reset(self) -> None:
        with self._lock:
            self._flags.clear()
flow_feature_flag_store = FlowFeatureFlagStore()


class FlowExecutionHookStore:
    """Per-flow pre/post execution hooks (webhook URLs or inline scripts)."""

    _MAX_HOOKS: int = 20

    def __init__(self) -> None:
        self._hooks: dict[str, dict[str, dict[str, Any]]] = {}  # flow_id → hook_id → record
        self._lock = threading.Lock()

    def add(
        self,
        flow_id: str,
        hook_type: str,
        url: str,
        event: str,
        enabled: bool,
        headers: dict[str, str],
    ) -> dict[str, Any]:
        with self._lock:
            flow_hooks = self._hooks.setdefault(flow_id, {})
            if len(flow_hooks) >= self._MAX_HOOKS:
                raise ValueError(f"Maximum {self._MAX_HOOKS} hooks per flow")
            hook_id = str(uuid.uuid4())
            record: dict[str, Any] = {
                "hook_id": hook_id,
                "flow_id": flow_id,
                "hook_type": hook_type,
                "url": url,
                "event": event,
                "enabled": enabled,
                "headers": headers,
                "created_at": datetime.now(UTC).isoformat(),
            }
            flow_hooks[hook_id] = record
            return record.copy()

    def list(self, flow_id: str) -> list[dict[str, Any]]:
        with self._lock:
            return [r.copy() for r in self._hooks.get(flow_id, {}).values()]

    def get(self, flow_id: str, hook_id: str) -> dict[str, Any] | None:
        with self._lock:
            return (self._hooks.get(flow_id, {}).get(hook_id) or {}).copy() or None

    def delete(self, flow_id: str, hook_id: str) -> bool:
        with self._lock:
            return self._hooks.get(flow_id, {}).pop(hook_id, None) is not None

    def reset(self) -> None:
        with self._lock:
            self._hooks.clear()
flow_execution_hook_store = FlowExecutionHookStore()


class FlowCustomDomainStore:
    """Per-flow custom domain configuration."""

    def __init__(self) -> None:
        self._domains: dict[str, dict[str, Any]] = {}  # flow_id → record
        self._domain_index: dict[str, str] = {}  # domain → flow_id (uniqueness)
        self._lock = threading.Lock()

    def set(self, flow_id: str, domain: str, enabled: bool) -> dict[str, Any]:
        with self._lock:
            # Release old domain mapping if replacing
            old = self._domains.get(flow_id)
            if old and old["domain"] != domain:
                self._domain_index.pop(old["domain"], None)
            # Check uniqueness across flows
            existing_flow = self._domain_index.get(domain)
            if existing_flow and existing_flow != flow_id:
                raise ValueError(f"Domain '{domain}' is already in use by another flow")
            record: dict[str, Any] = {
                "flow_id": flow_id,
                "domain": domain,
                "enabled": enabled,
                "updated_at": datetime.now(UTC).isoformat(),
            }
            self._domains[flow_id] = record
            self._domain_index[domain] = flow_id
            return record.copy()

    def get(self, flow_id: str) -> dict[str, Any] | None:
        with self._lock:
            rec = self._domains.get(flow_id)
            return rec.copy() if rec else None

    def delete(self, flow_id: str) -> bool:
        with self._lock:
            rec = self._domains.pop(flow_id, None)
            if rec:
                self._domain_index.pop(rec["domain"], None)
                return True
            return False

    def reset(self) -> None:
        with self._lock:
            self._domains.clear()
            self._domain_index.clear()
flow_custom_domain_store = FlowCustomDomainStore()


class FlowWebhookSigningStore:
    """Per-flow HMAC signing configuration for outbound webhooks."""

    _ALLOWED_ALGOS: frozenset[str] = frozenset({"sha256", "sha512"})

    def __init__(self) -> None:
        self._configs: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def set(self, flow_id: str, secret: str, algorithm: str, enabled: bool) -> dict[str, Any]:
        if algorithm not in self._ALLOWED_ALGOS:
            raise ValueError(f"algorithm must be one of {sorted(self._ALLOWED_ALGOS)}")
        with self._lock:
            record: dict[str, Any] = {
                "flow_id": flow_id,
                "secret": secret,
                "algorithm": algorithm,
                "enabled": enabled,
                "updated_at": datetime.now(UTC).isoformat(),
            }
            self._configs[flow_id] = record
            return record.copy()

    def get(self, flow_id: str) -> dict[str, Any] | None:
        with self._lock:
            rec = self._configs.get(flow_id)
            return rec.copy() if rec else None

    def delete(self, flow_id: str) -> bool:
        with self._lock:
            return self._configs.pop(flow_id, None) is not None

    def reset(self) -> None:
        with self._lock:
            self._configs.clear()
flow_webhook_signing_store = FlowWebhookSigningStore()


class FlowAuditExportStore:
    """Per-flow audit export job tracker.

    Each export job captures a snapshot of audit log entries for a flow,
    keyed by job_id.  The store does not hold the real audit_log_store
    data — it creates its own lightweight export records for testing.
    """

    _MAX_EXPORTS: int = 20

    def __init__(self) -> None:
        self._exports: dict[str, dict[str, Any]] = {}  # job_id → record
        self._flow_jobs: dict[str, list[str]] = {}  # flow_id → [job_id]
        self._lock = threading.Lock()

    def create(
        self,
        flow_id: str,
        format: str,
        from_ts: str | None,
        to_ts: str | None,
    ) -> dict[str, Any]:
        with self._lock:
            flow_jobs = self._flow_jobs.setdefault(flow_id, [])
            if len(flow_jobs) >= self._MAX_EXPORTS:
                raise ValueError(f"Maximum {self._MAX_EXPORTS} exports per flow")
            job_id = str(uuid.uuid4())
            record: dict[str, Any] = {
                "job_id": job_id,
                "flow_id": flow_id,
                "format": format,
                "from_ts": from_ts,
                "to_ts": to_ts,
                "status": "pending",
                "created_at": datetime.now(UTC).isoformat(),
            }
            self._exports[job_id] = record
            flow_jobs.append(job_id)
            return record.copy()

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            rec = self._exports.get(job_id)
            return rec.copy() if rec else None

    def list(self, flow_id: str) -> list[dict[str, Any]]:
        with self._lock:
            job_ids = self._flow_jobs.get(flow_id, [])
            return [self._exports[j].copy() for j in job_ids if j in self._exports]

    def reset(self) -> None:
        with self._lock:
            self._exports.clear()
            self._flow_jobs.clear()
flow_audit_export_store = FlowAuditExportStore()


class FlowCollaboratorRoleStore:
    """Per-flow role assignments (viewer | editor | admin) per user_id."""

    _ALLOWED_ROLES: frozenset[str] = frozenset({"viewer", "editor", "admin"})
    _MAX_COLLABORATORS: int = 50

    def __init__(self) -> None:
        self._roles: dict[str, dict[str, dict[str, Any]]] = {}  # flow_id → user_id → record
        self._lock = threading.Lock()

    def set(self, flow_id: str, user_id: str, role: str) -> dict[str, Any]:
        if role not in self._ALLOWED_ROLES:
            raise ValueError(f"role must be one of {sorted(self._ALLOWED_ROLES)}")
        with self._lock:
            flow_roles = self._roles.setdefault(flow_id, {})
            if user_id not in flow_roles and len(flow_roles) >= self._MAX_COLLABORATORS:
                raise ValueError(f"Maximum {self._MAX_COLLABORATORS} collaborators per flow")
            record: dict[str, Any] = {
                "flow_id": flow_id,
                "user_id": user_id,
                "role": role,
                "updated_at": datetime.now(UTC).isoformat(),
            }
            flow_roles[user_id] = record
            return record.copy()

    def get(self, flow_id: str, user_id: str) -> dict[str, Any] | None:
        with self._lock:
            rec = self._roles.get(flow_id, {}).get(user_id)
            return rec.copy() if rec else None

    def list(self, flow_id: str) -> list[dict[str, Any]]:
        with self._lock:
            return [r.copy() for r in self._roles.get(flow_id, {}).values()]

    def delete(self, flow_id: str, user_id: str) -> bool:
        with self._lock:
            return self._roles.get(flow_id, {}).pop(user_id, None) is not None

    def reset(self) -> None:
        with self._lock:
            self._roles.clear()
flow_collaborator_role_store = FlowCollaboratorRoleStore()


class FlowInputMaskStore:
    """Per-flow input field masking rules (field_name → mask_type)."""

    _ALLOWED_MASKS: frozenset[str] = frozenset(
        {"full", "partial", "hash", "redact"}
    )
    _MAX_RULES: int = 50

    def __init__(self) -> None:
        self._masks: dict[str, dict[str, Any]] = {}  # flow_id → {rules, updated_at}
        self._lock = threading.Lock()

    def set(
        self,
        flow_id: str,
        rules: dict[str, str],
        enabled: bool,
    ) -> dict[str, Any]:
        for field, mask in rules.items():
            if mask not in self._ALLOWED_MASKS:
                raise ValueError(
                    f"mask type '{mask}' for field '{field}' must be one of "
                    f"{sorted(self._ALLOWED_MASKS)}"
                )
        if len(rules) > self._MAX_RULES:
            raise ValueError(f"Maximum {self._MAX_RULES} masking rules per flow")
        with self._lock:
            record: dict[str, Any] = {
                "flow_id": flow_id,
                "rules": rules,
                "enabled": enabled,
                "updated_at": datetime.now(UTC).isoformat(),
            }
            self._masks[flow_id] = record
            return record.copy()

    def get(self, flow_id: str) -> dict[str, Any] | None:
        with self._lock:
            rec = self._masks.get(flow_id)
            return rec.copy() if rec else None

    def delete(self, flow_id: str) -> bool:
        with self._lock:
            return self._masks.pop(flow_id, None) is not None

    def reset(self) -> None:
        with self._lock:
            self._masks.clear()
flow_input_mask_store = FlowInputMaskStore()


class FlowOutputTransformStore:
    """Per-flow output transformation configuration."""

    _ALLOWED_FORMATS: frozenset[str] = frozenset({"json", "xml", "csv", "text"})

    def __init__(self) -> None:
        self._transforms: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def set(
        self,
        flow_id: str,
        expression: str,
        output_format: str,
        enabled: bool,
    ) -> dict[str, Any]:
        if output_format not in self._ALLOWED_FORMATS:
            raise ValueError(
                f"output_format must be one of {sorted(self._ALLOWED_FORMATS)}"
            )
        with self._lock:
            record: dict[str, Any] = {
                "flow_id": flow_id,
                "expression": expression,
                "output_format": output_format,
                "enabled": enabled,
                "updated_at": datetime.now(UTC).isoformat(),
            }
            self._transforms[flow_id] = record
            return record.copy()

    def get(self, flow_id: str) -> dict[str, Any] | None:
        with self._lock:
            rec = self._transforms.get(flow_id)
            return rec.copy() if rec else None

    def delete(self, flow_id: str) -> bool:
        with self._lock:
            return self._transforms.pop(flow_id, None) is not None

    def reset(self) -> None:
        with self._lock:
            self._transforms.clear()
flow_output_transform_store = FlowOutputTransformStore()


class FlowDataRetentionStore:
    """Per-flow data retention policy configuration."""

    def __init__(self) -> None:
        self._policies: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def set(
        self,
        flow_id: str,
        retention_days: int,
        delete_on_expiry: bool,
        anonymize_on_expiry: bool,
        enabled: bool,
    ) -> dict[str, Any]:
        with self._lock:
            record: dict[str, Any] = {
                "flow_id": flow_id,
                "retention_days": retention_days,
                "delete_on_expiry": delete_on_expiry,
                "anonymize_on_expiry": anonymize_on_expiry,
                "enabled": enabled,
                "updated_at": datetime.now(UTC).isoformat(),
            }
            self._policies[flow_id] = record
            return record.copy()

    def get(self, flow_id: str) -> dict[str, Any] | None:
        with self._lock:
            rec = self._policies.get(flow_id)
            return rec.copy() if rec else None

    def delete(self, flow_id: str) -> bool:
        with self._lock:
            return self._policies.pop(flow_id, None) is not None

    def reset(self) -> None:
        with self._lock:
            self._policies.clear()
flow_data_retention_store = FlowDataRetentionStore()


class FlowAllowedOriginsStore:
    """Per-flow allowed origins (CORS-style) configuration."""

    _MAX_ORIGINS: int = 50

    def __init__(self) -> None:
        self._configs: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def set(
        self,
        flow_id: str,
        origins: list[str],
        enabled: bool,
    ) -> dict[str, Any]:
        if len(origins) > self._MAX_ORIGINS:
            raise ValueError(f"Too many origins; maximum is {self._MAX_ORIGINS}")
        with self._lock:
            record: dict[str, Any] = {
                "flow_id": flow_id,
                "origins": list(origins),
                "enabled": enabled,
                "updated_at": datetime.now(UTC).isoformat(),
            }
            self._configs[flow_id] = record
            return record.copy()

    def get(self, flow_id: str) -> dict[str, Any] | None:
        with self._lock:
            rec = self._configs.get(flow_id)
            return rec.copy() if rec else None

    def delete(self, flow_id: str) -> bool:
        with self._lock:
            return self._configs.pop(flow_id, None) is not None

    def reset(self) -> None:
        with self._lock:
            self._configs.clear()
flow_allowed_origins_store = FlowAllowedOriginsStore()


class RollbackAuditStore:
    """Thread-safe audit log for workflow version rollbacks.

    Records every rollback operation with from/to version IDs, the user who
    performed it, an optional reason, and a timestamp.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: list[dict[str, Any]] = []

    def record(
        self,
        flow_id: str,
        from_version_id: str,
        to_version_id: str,
        performed_by: str,
        reason: str = "",
    ) -> dict[str, Any]:
        """Record a rollback event and return the audit entry."""
        entry: dict[str, Any] = {
            "audit_id": str(uuid.uuid4()),
            "flow_id": flow_id,
            "from_version_id": from_version_id,
            "to_version_id": to_version_id,
            "performed_by": performed_by,
            "reason": reason,
            "rolled_back_at": time.time(),
        }
        with self._lock:
            self._entries.append(entry)
        return dict(entry)

    def list(
        self,
        flow_id: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Return audit entries newest-first, optionally filtered by flow_id."""
        with self._lock:
            items = list(self._entries)
        if flow_id is not None:
            items = [e for e in items if e["flow_id"] == flow_id]
        items.reverse()
        return items[:limit]

    def reset(self) -> None:
        """Clear all audit entries. Used between tests."""
        with self._lock:
            self._entries.clear()
rollback_audit_store = RollbackAuditStore()


class SubflowRegistry:
    """Tracks active subflow executions to detect circular references.

    A parent run executing a child flow is recorded here. If the same
    (parent_run_id, child_flow_id) pair appears again while still active,
    that signals a circular invocation and an error is raised.
    """

    def __init__(self) -> None:
        # Maps parent_run_id -> set of child_flow_ids currently executing
        self._active: dict[str, set[str]] = {}

    def enter(self, parent_run_id: str, child_flow_id: str) -> None:
        """Record that parent_run_id is executing child_flow_id.

        Raises RuntimeError if child_flow_id is already being executed
        by parent_run_id (circular reference).
        """
        running = self._active.setdefault(parent_run_id, set())
        if child_flow_id in running:
            raise RuntimeError(
                f"Circular subflow reference detected: run '{parent_run_id}' "
                f"is already executing workflow '{child_flow_id}'"
            )
        running.add(child_flow_id)

    def exit(self, parent_run_id: str, child_flow_id: str) -> None:
        """Remove the tracking entry when subflow completes."""
        running = self._active.get(parent_run_id)
        if running is not None:
            running.discard(child_flow_id)
            if not running:
                del self._active[parent_run_id]

    def reset(self) -> None:
        """Clear all tracking state — for test isolation."""
        self._active.clear()
subflow_registry = SubflowRegistry()


class TemplateRegistry:
    """In-memory versioned template store.

    Each template has a unique ID. Every import of the same ID creates a new
    version. Versions are numbered sequentially starting at 1. Each version
    also carries a semver string (``major.minor.patch``).
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # template_id -> list of version dicts (index 0 = v1, index 1 = v2, …)
        self._templates: dict[str, list[dict[str, Any]]] = {}

    def _next_semver(self, versions: list[dict[str, Any]], explicit: str | None) -> str:
        """Determine the semver for the next version."""
        if explicit:
            parsed = _parse_semver(explicit)
            if not parsed:
                raise ValueError(
                    f"Invalid semver: '{explicit}'. Expected format: major.minor.patch"
                )
            # Check for duplicates
            for v in versions:
                if v.get("semver") == explicit:
                    raise ValueError(f"Version '{explicit}' already exists for this template")
            return explicit
        if not versions:
            return "1.0.0"
        return _bump_patch(versions[-1].get("semver", "1.0.0"))

    def import_template(self, data: dict[str, Any]) -> dict[str, Any]:
        """Import a template, creating a new version if the ID already exists."""
        template_id = data.get("id") or str(uuid.uuid4())
        name = data.get("name", "Unnamed Template")
        explicit_semver = data.get("version") if isinstance(data.get("version"), str) else None
        with self._lock:
            versions = self._templates.setdefault(template_id, [])
            semver = self._next_semver(versions, explicit_semver)
            seq = len(versions) + 1
            entry = {
                "id": template_id,
                "version": seq,
                "semver": semver,
                "name": name,
                "description": data.get("description", ""),
                "tags": data.get("tags", []),
                "nodes": data.get("nodes", []),
                "edges": data.get("edges", []),
                "metadata": data.get("metadata", {}),
                "imported_at": time.time(),
            }
            versions.append(entry)
        return entry

    def get(self, template_id: str, version: int | None = None) -> dict[str, Any] | None:
        """Get a template. Returns latest version unless a specific version is given."""
        with self._lock:
            versions = self._templates.get(template_id)
            if not versions:
                return None
            if version is not None:
                if 1 <= version <= len(versions):
                    return dict(versions[version - 1])
                return None
            return dict(versions[-1])

    def get_by_semver(self, template_id: str, semver: str | None = None) -> dict[str, Any] | None:
        """Get a template by semver string. Returns latest if semver is None."""
        with self._lock:
            versions = self._templates.get(template_id)
            if not versions:
                return None
            if semver is None:
                return dict(versions[-1])
            for v in versions:
                if v.get("semver") == semver:
                    return dict(v)
            return None

    def rollback(self, template_id: str, target_semver: str) -> dict[str, Any] | None:
        """Rollback to a previous semver by creating a new version from that snapshot."""
        with self._lock:
            versions = self._templates.get(template_id)
            if not versions:
                return None
            # Find the target version
            target = None
            for v in versions:
                if v.get("semver") == target_semver:
                    target = v
                    break
            if target is None:
                return None
            # Create a new version from the target snapshot
            seq = len(versions) + 1
            new_semver = _bump_patch(versions[-1].get("semver", "1.0.0"))
            entry = {
                "id": template_id,
                "version": seq,
                "semver": new_semver,
                "name": target["name"],
                "description": target.get("description", ""),
                "tags": list(target.get("tags", [])),
                "nodes": list(target.get("nodes", [])),
                "edges": list(target.get("edges", [])),
                "metadata": dict(target.get("metadata", {})),
                "imported_at": time.time(),
                "rolled_back_from": target_semver,
            }
            versions.append(entry)
        return entry

    def list_templates(self) -> list[dict[str, Any]]:
        """List all templates (latest version of each)."""
        with self._lock:
            result = []
            for versions in self._templates.values():
                if versions:
                    latest = dict(versions[-1])
                    latest["total_versions"] = len(versions)
                    result.append(latest)
            return sorted(result, key=lambda t: t.get("imported_at", 0), reverse=True)

    def list_versions(self, template_id: str) -> list[dict[str, Any]]:
        """List all versions of a template."""
        with self._lock:
            versions = self._templates.get(template_id)
            if not versions:
                return []
            return [dict(v) for v in versions]

    def delete(self, template_id: str) -> bool:
        with self._lock:
            return self._templates.pop(template_id, None) is not None

    def reset(self) -> None:
        with self._lock:
            self._templates.clear()
template_registry = TemplateRegistry()


class MarketplaceRegistry:
    """Thread-safe in-memory store for marketplace listings."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._listings: dict[str, dict[str, Any]] = {}

    def publish(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a new marketplace listing. Raises ValueError on ID collision."""
        listing_id = str(uuid.uuid4())
        entry: dict[str, Any] = {
            "id": listing_id,
            "name": data["name"],
            "description": data.get("description", ""),
            "category": data["category"],
            "tags": list(data.get("tags", [])),
            "author": data.get("author", "anonymous"),
            "publisher_id": data.get("publisher_id"),
            "nodes": data.get("nodes", []),
            "edges": data.get("edges", []),
            "install_count": 0,
            "install_timestamps": [],
            "featured": False,
            "published_at": time.time(),
        }
        with self._lock:
            if listing_id in self._listings:
                raise ValueError(f"Listing ID '{listing_id}' already exists")
            self._listings[listing_id] = entry
        return entry

    def search(
        self,
        q: str | None,
        category: str | None,
        tags: list[str] | None,
        page: int,
        per_page: int,
    ) -> tuple[list[dict[str, Any]], int]:
        """Search marketplace listings. Returns (items, total)."""
        with self._lock:
            results = list(self._listings.values())

        if q:
            q_lower = q.lower()
            filtered = []
            for item in results:
                if (
                    q_lower in item["name"].lower()
                    or q_lower in item["description"].lower()
                    or any(q_lower in tag.lower() for tag in item["tags"])
                ):
                    filtered.append(item)
            results = filtered

        if category:
            cat_lower = category.lower()
            results = [item for item in results if item["category"] == cat_lower]

        if tags:
            tag_set = {t.lower() for t in tags}
            results = [
                item for item in results if any(tag.lower() in tag_set for tag in item["tags"])
            ]

        total = len(results)
        start = (page - 1) * per_page
        end = start + per_page
        return results[start:end], total

    def featured(self) -> list[dict[str, Any]]:
        """Return top 10 listings sorted by install_count desc, published_at desc."""
        with self._lock:
            all_items = list(self._listings.values())
        sorted_items = sorted(
            all_items,
            key=lambda x: (-x["install_count"], -x["published_at"]),
        )
        return sorted_items[:10]

    def get(self, listing_id: str) -> dict[str, Any] | None:
        """Get a listing by ID. Returns None if not found."""
        with self._lock:
            return self._listings.get(listing_id)

    def increment_install(self, listing_id: str) -> bool:
        """Increment install_count for a listing. Returns False if not found."""
        with self._lock:
            listing = self._listings.get(listing_id)
            if listing is None:
                return False
            listing["install_count"] += 1
            listing.setdefault("install_timestamps", []).append(time.time())
            return True

    def get_install_timestamps(self, listing_id: str) -> list[float]:
        """Return the list of install timestamps for a listing."""
        with self._lock:
            listing = self._listings.get(listing_id)
            if listing is None:
                return []
            return list(listing.get("install_timestamps", []))

    def list_all(self) -> list[dict[str, Any]]:
        """Return all listings as a list."""
        with self._lock:
            return list(self._listings.values())

    def reset(self) -> None:
        """Clear all listings (for testing)."""
        with self._lock:
            self._listings.clear()
marketplace_registry = MarketplaceRegistry()


class AlertRuleStore:
    """Thread-safe in-memory store for workflow alert rules.

    Rule schema:
        id (str), workflow_id (str or "*"), metric (str), operator (str),
        threshold (float), window_minutes (int), action_type (str),
        action_config (dict), enabled (bool), created_at (float),
        last_triggered_at (float | None)

    Supported metrics: error_rate, avg_duration_seconds, run_count
    Supported operators: ">", "<", ">=", "<="
    Action types: "webhook", "log"
    """

    VALID_METRICS = {"error_rate", "avg_duration_seconds", "run_count"}
    VALID_OPERATORS = {">", "<", ">=", "<="}
    VALID_ACTION_TYPES = {"webhook", "log"}

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._rules: dict[str, dict[str, Any]] = {}

    def create(self, rule: dict[str, Any]) -> dict[str, Any]:
        """Persist a new alert rule and return it with an assigned id."""
        with self._lock:
            rule_id = str(uuid.uuid4())
            now = time.time()
            stored: dict[str, Any] = {
                "id": rule_id,
                "workflow_id": rule.get("workflow_id", "*"),
                "metric": rule["metric"],
                "operator": rule["operator"],
                "threshold": float(rule["threshold"]),
                "window_minutes": int(rule.get("window_minutes", 60)),
                "action_type": rule["action_type"],
                "action_config": dict(rule.get("action_config") or {}),
                "enabled": bool(rule.get("enabled", True)),
                "created_at": now,
                "last_triggered_at": None,
            }
            self._rules[rule_id] = stored
            return dict(stored)

    def list_all(self) -> list[dict[str, Any]]:
        """Return all alert rules ordered by created_at ascending."""
        with self._lock:
            return sorted(self._rules.values(), key=lambda r: r["created_at"])

    def get(self, rule_id: str) -> dict[str, Any] | None:
        """Return a single rule by id, or None if not found."""
        with self._lock:
            rule = self._rules.get(rule_id)
            return dict(rule) if rule else None

    def update(self, rule_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        """Partially update a rule (threshold, operator, enabled, action_config).

        Returns the updated rule or None if rule_id does not exist.
        """
        allowed_fields = {"threshold", "operator", "enabled", "action_config"}
        with self._lock:
            rule = self._rules.get(rule_id)
            if rule is None:
                return None
            for field in allowed_fields:
                if field in patch:
                    if field == "threshold":
                        rule[field] = float(patch[field])
                    elif field == "enabled":
                        rule[field] = bool(patch[field])
                    elif field == "action_config":
                        rule[field] = dict(patch[field])
                    else:
                        rule[field] = patch[field]
            return dict(rule)

    def delete(self, rule_id: str) -> bool:
        """Remove a rule by id. Returns True if deleted, False if not found."""
        with self._lock:
            if rule_id in self._rules:
                del self._rules[rule_id]
                return True
            return False

    def mark_triggered(self, rule_id: str) -> None:
        """Update last_triggered_at timestamp for a rule."""
        with self._lock:
            if rule_id in self._rules:
                self._rules[rule_id]["last_triggered_at"] = time.time()

    def reset(self) -> None:
        """Clear all rules (used in tests)."""
        with self._lock:
            self._rules.clear()


class AlertEngine:
    """Evaluate enabled alert rules against health results and fire actions."""

    def __init__(self, store: AlertRuleStore) -> None:
        self._store = store

    @staticmethod
    def _logger() -> Any:
        """Return the orchestrator logger, resolving through main's namespace so
        tests that patch ``apps.orchestrator.main.logger`` still work."""
        try:
            import apps.orchestrator.main as _main  # noqa: PLC0415 — lazy import

            return _main.logger
        except Exception:  # pragma: no cover — fallback during early import
            return logger

    def evaluate(self, health_results: list[dict[str, Any]]) -> None:
        """Check all enabled rules against health data and trigger matched actions.

        Args:
            health_results: List of WorkflowHealth dicts from WorkflowHealthService.
        """
        rules = self._store.list_all()
        health_by_flow: dict[str, dict[str, Any]] = {h["flow_id"]: h for h in health_results}

        for rule in rules:
            if not rule.get("enabled", True):
                continue

            workflow_id = rule.get("workflow_id", "*")
            metric = rule["metric"]
            operator = rule["operator"]
            threshold = float(rule["threshold"])
            action_type = rule["action_type"]
            action_config = rule.get("action_config") or {}
            rule_id = rule["id"]

            # Determine which flows to check
            if workflow_id == "*":
                candidates = list(health_results)
            else:
                candidate = health_by_flow.get(workflow_id)
                candidates = [candidate] if candidate is not None else []

            for health in candidates:
                metric_value = health.get(metric)
                if metric_value is None:
                    continue

                try:
                    metric_float = float(metric_value)
                except (TypeError, ValueError):
                    self._logger().warning(
                        "AlertEngine: non-numeric metric value for rule %s metric %s: %r",
                        rule_id,
                        metric,
                        metric_value,
                    )
                    continue

                triggered = self._compare(metric_float, operator, threshold)
                if not triggered:
                    continue

                self._store.mark_triggered(rule_id)
                self._fire_action(rule, health, metric_float, action_type, action_config)

    @staticmethod
    def _compare(value: float, operator: str, threshold: float) -> bool:
        """Evaluate value operator threshold."""
        if operator == ">":
            return value > threshold
        if operator == "<":
            return value < threshold
        if operator == ">=":
            return value >= threshold
        if operator == "<=":
            return value <= threshold
        return False

    def _fire_action(
        self,
        rule: dict[str, Any],
        health: dict[str, Any],
        metric_value: float,
        action_type: str,
        action_config: dict[str, Any],
    ) -> None:
        """Dispatch the configured action for a triggered rule."""
        _log = self._logger()
        if action_type == "log":
            _log.warning(
                "AlertEngine: rule %s triggered — flow=%s metric=%s value=%.4f "
                "operator=%s threshold=%.4f",
                rule["id"],
                health.get("flow_id"),
                rule["metric"],
                metric_value,
                rule["operator"],
                rule["threshold"],
            )
        elif action_type == "webhook":
            url = action_config.get("url")
            if not url:
                _log.warning(
                    "AlertEngine: webhook rule %s has no url in action_config", rule["id"]
                )
                return
            payload = {
                "rule_id": rule["id"],
                "flow_id": health.get("flow_id"),
                "metric": rule["metric"],
                "metric_value": metric_value,
                "operator": rule["operator"],
                "threshold": rule["threshold"],
                "health_status": health.get("health_status"),
                "triggered_at": time.time(),
            }
            # Non-blocking fire-and-forget via a background thread
            import threading as _threading

            def _post() -> None:
                try:
                    httpx.post(url, json=payload, timeout=10.0)
                except Exception as exc:
                    _log.warning(
                        "AlertEngine: webhook delivery failed for rule %s url=%s: %s",
                        rule["id"],
                        url,
                        exc,
                    )

            _threading.Thread(target=_post, daemon=True).start()
        else:
            _log.warning(
                "AlertEngine: unknown action_type %r for rule %s — no action taken",
                action_type,
                rule["id"],
            )


class WorkflowTestStore:
    """Thread-safe in-memory store for workflow test suites and test run history.

    Test suite: {id, workflow_id, name, assertions: [{path, op, expected}]}
    Test result: {id, workflow_id, suite_id, run_id, passed, results, timestamp, version_id}
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._suites: dict[str, list[dict[str, Any]]] = {}  # workflow_id -> [suite]
        self._history: dict[str, list[dict[str, Any]]] = {}  # workflow_id -> [result]

    def save_suite(self, workflow_id: str, suite: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            suites = self._suites.setdefault(workflow_id, [])
            suite["workflow_id"] = workflow_id
            if "id" not in suite:
                suite["id"] = str(uuid.uuid4())
            # Replace existing suite with same id or append
            for i, s in enumerate(suites):
                if s["id"] == suite["id"]:
                    suites[i] = suite
                    return suite
            suites.append(suite)
            return suite

    def list_suites(self, workflow_id: str) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._suites.get(workflow_id, []))

    def record_result(self, workflow_id: str, result: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            history = self._history.setdefault(workflow_id, [])
            result.setdefault("id", str(uuid.uuid4()))
            history.append(result)
            return result

    def get_history(self, workflow_id: str, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            history = self._history.get(workflow_id, [])
            # Most recent first
            return list(reversed(history[-limit:]))

    def reset(self) -> None:
        with self._lock:
            self._suites.clear()
            self._history.clear()
workflow_test_store = WorkflowTestStore()


class OAuthClientRegistry:
    """In-memory registry for OAuth2 client registrations.

    Client secrets are stored as SHA-256 hashes; the plain secret is returned
    only at registration time and never again.
    """

    def __init__(self) -> None:
        self._clients: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def register(
        self,
        name: str,
        redirect_uris: list[str],
        allowed_scopes: list[str],
        grant_types: list[str],
    ) -> dict[str, Any]:
        """Register a new OAuth2 client and return the full record including plain secret."""
        client_id = str(uuid.uuid4())
        plain_secret = secrets.token_hex(32)
        secret_hash = hashlib.sha256(plain_secret.encode("utf-8")).hexdigest()
        record: dict[str, Any] = {
            "client_id": client_id,
            "_secret_hash": secret_hash,
            "name": name,
            "redirect_uris": list(redirect_uris),
            "allowed_scopes": list(allowed_scopes),
            "grant_types": list(grant_types),
            "is_active": True,
            "created_at": time.time(),
        }
        with self._lock:
            self._clients[client_id] = record
        return {
            **{k: v for k, v in record.items() if k != "_secret_hash"},
            "client_secret": plain_secret,
        }

    def get(self, client_id: str) -> dict[str, Any] | None:
        """Return client record (without secret hash) or None if not found."""
        with self._lock:
            record = self._clients.get(client_id)
        if record is None:
            return None
        return {k: v for k, v in record.items() if k != "_secret_hash"}

    def validate_secret(self, client_id: str, client_secret: str) -> bool:
        """Return True if the client exists, is active, and the secret matches."""
        with self._lock:
            record = self._clients.get(client_id)
        if record is None or not record.get("is_active", False):
            return False
        candidate_hash = hashlib.sha256(client_secret.encode("utf-8")).hexdigest()
        return hmac.compare_digest(candidate_hash, record["_secret_hash"])

    def list_all(self) -> list[dict[str, Any]]:
        """Return all client records without secret hashes."""
        with self._lock:
            records = list(self._clients.values())
        return [{k: v for k, v in r.items() if k != "_secret_hash"} for r in records]

    def revoke(self, client_id: str) -> bool:
        """Mark a client as inactive. Returns True if the client existed."""
        with self._lock:
            if client_id not in self._clients:
                return False
            self._clients[client_id]["is_active"] = False
            return True

    def reset(self) -> None:
        """Clear all registrations (for tests)."""
        with self._lock:
            self._clients.clear()


class AuthorizationCodeStore:
    """In-memory store for OAuth2 authorization codes with 10-minute TTL."""

    _CODE_TTL_SECONDS: int = 600

    def __init__(self) -> None:
        self._codes: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _now() -> float:
        """Return current time, resolved through main's namespace so tests that
        patch ``apps.orchestrator.main.time`` still work."""
        try:
            import apps.orchestrator.main as _main  # noqa: PLC0415 — lazy import

            return _main.time.time()
        except Exception:  # pragma: no cover — fallback before main is loaded
            return time.time()

    def create(
        self,
        client_id: str,
        user_id: str,
        scopes: list[str],
        redirect_uri: str,
    ) -> str:
        """Create and store a new authorization code; return the code string."""
        code = secrets.token_urlsafe(32)
        record: dict[str, Any] = {
            "code": code,
            "client_id": client_id,
            "user_id": user_id,
            "scopes": list(scopes),
            "redirect_uri": redirect_uri,
            "expires_at": self._now() + self._CODE_TTL_SECONDS,
            "used": False,
        }
        with self._lock:
            self._codes[code] = record
        return code

    def consume(self, code: str) -> dict[str, Any] | None:
        """Return and mark-used the code record if valid, None if expired/used/missing."""
        with self._lock:
            record = self._codes.get(code)
            if record is None:
                return None
            if record["used"]:
                return None
            if self._now() > record["expires_at"]:
                return None
            record["used"] = True
            return dict(record)

    def cleanup_expired(self) -> None:
        """Remove expired code records from memory."""
        now = self._now()
        with self._lock:
            expired = [c for c, r in self._codes.items() if now > r["expires_at"]]
            for c in expired:
                del self._codes[c]

    def reset(self) -> None:
        """Clear all codes (for tests)."""
        with self._lock:
            self._codes.clear()


@dataclass
class ExecutionCostRecord:
    """Cost record for a single workflow execution."""

    execution_id: str
    flow_id: str
    node_costs: list[dict]
    total_usd: float
    total_tokens: int
    created_at: float


class CostTrackerStore:
    """Thread-safe store for per-execution cost records."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._records: dict[str, ExecutionCostRecord] = {}

    def record(
        self, execution_id: str, flow_id: str, node_costs: list[dict]
    ) -> ExecutionCostRecord:
        """Compute totals and persist cost record for an execution.

        Args:
            execution_id: The run/execution ID.
            flow_id: The flow/workflow ID.
            node_costs: List of per-node cost dicts (from _estimate_node_cost + node_id/node_type).

        Returns:
            The created ExecutionCostRecord.
        """
        total_usd = sum(float(nc.get("estimated_usd", 0.0)) for nc in node_costs)
        total_tokens = sum(
            int(nc.get("token_input", 0)) + int(nc.get("token_output", 0)) for nc in node_costs
        )
        rec = ExecutionCostRecord(
            execution_id=execution_id,
            flow_id=flow_id,
            node_costs=list(node_costs),
            total_usd=total_usd,
            total_tokens=total_tokens,
            created_at=time.time(),
        )
        with self._lock:
            self._records[execution_id] = rec
        return rec

    def get(self, execution_id: str) -> ExecutionCostRecord | None:
        """Return the cost record for an execution, or None."""
        with self._lock:
            return self._records.get(execution_id)

    def list_for_flow(self, flow_id: str) -> list[ExecutionCostRecord]:
        """Return all cost records for a given flow_id."""
        with self._lock:
            return [r for r in self._records.values() if r.flow_id == flow_id]

    def all_records(self) -> list[ExecutionCostRecord]:
        """Return all cost records across all flows and executions."""
        with self._lock:
            return list(self._records.values())

    def reset(self) -> None:
        """Clear all records (test teardown)."""
        with self._lock:
            self._records.clear()
cost_tracker_store = CostTrackerStore()


class ReplayStore:
    """Thread-safe store tracking execution replay chains."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._chains: dict[str, list[str]] = {}
        self._reverse: dict[str, str] = {}

    def register_replay(self, original_run_id: str, replay_run_id: str) -> None:
        """Record that *replay_run_id* is a replay of *original_run_id*.

        Args:
            original_run_id: The root (original) execution ID.
            replay_run_id: The new replay execution ID.
        """
        with self._lock:
            self._chains.setdefault(original_run_id, []).append(replay_run_id)
            self._reverse[replay_run_id] = original_run_id

    def get_chain(self, run_id: str) -> list[str]:
        """Return the full replay chain starting from the root original run.

        Returns [original_run_id, replay1, replay2, ...].
        If run_id is itself a replay, follows back to the root first.
        """
        with self._lock:
            # resolve root
            root = run_id
            while root in self._reverse:
                root = self._reverse[root]
            replays = list(self._chains.get(root, []))
            return [root] + replays

    def get_original(self, run_id: str) -> str:
        """Return the root original run_id by following the reverse chain."""
        with self._lock:
            current = run_id
            while current in self._reverse:
                current = self._reverse[current]
            return current

    def reset(self) -> None:
        """Clear all replay data (test teardown)."""
        with self._lock:
            self._chains.clear()
            self._reverse.clear()
replay_store = ReplayStore()


class WorkflowVersionStore:
    """In-memory version history for workflow snapshots.

    Each version record contains a snapshot of the full workflow dict at the
    time of saving.  list_versions omits the snapshot for efficiency.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._versions: dict[str, list[dict]] = {}  # flow_id -> list of version records

    def save_version(self, flow_id: str, snapshot: dict, label: str = "") -> dict:
        """Append a snapshot and return the version summary (without full snapshot)."""
        version_id = str(uuid.uuid4())
        created_at = time.time()
        node_count = len(snapshot.get("nodes", []))
        edge_count = len(snapshot.get("edges", []))
        record = {
            "version_id": version_id,
            "snapshot": snapshot,
            "created_at": created_at,
            "label": label,
            "node_count": node_count,
            "edge_count": edge_count,
        }
        with self._lock:
            self._versions.setdefault(flow_id, []).append(record)
        return {
            "version_id": version_id,
            "created_at": created_at,
            "label": label,
            "node_count": node_count,
            "edge_count": edge_count,
        }

    def list_versions(self, flow_id: str) -> list[dict]:
        """Return version summaries for flow_id, omitting the full snapshot."""
        with self._lock:
            records = self._versions.get(flow_id, [])
            return [
                {
                    "version_id": r["version_id"],
                    "created_at": r["created_at"],
                    "label": r["label"],
                    "node_count": r["node_count"],
                    "edge_count": r["edge_count"],
                }
                for r in records
            ]

    def get_version(self, flow_id: str, version_id: str) -> dict | None:
        """Return the full version record (including snapshot) or None if not found."""
        with self._lock:
            for record in self._versions.get(flow_id, []):
                if record["version_id"] == version_id:
                    return dict(record)
        return None

    def reset(self) -> None:
        """Clear all stored versions (test teardown)."""
        with self._lock:
            self._versions.clear()
workflow_version_store = WorkflowVersionStore()


@dataclass
class DebugSession:
    """Represents a single step-through debug session for a workflow run.

    The session tracks which nodes have been visited, stores captured
    input/output at each breakpoint, and exposes an asyncio.Event so the
    background execution task can be paused and resumed from the API.
    """

    session_id: str
    run_id: str
    flow_id: str
    status: str  # "paused" | "running" | "completed" | "aborted"
    breakpoints: set[str]
    current_node_id: str | None
    current_node_input: dict
    current_node_output: dict
    execution_history: list  # list[dict]: {node_id, input, output, skipped, timestamp}
    created_at: float
    paused_at: float | None
    _resume_event: asyncio.Event
    _skip_flag: bool

    def to_dict(self) -> dict[str, Any]:
        """Serialize the session to a dict safe for API responses."""
        return {
            "session_id": self.session_id,
            "run_id": self.run_id,
            "flow_id": self.flow_id,
            "status": self.status,
            "breakpoints": sorted(self.breakpoints),
            "current_node_id": self.current_node_id,
            "current_node_input": self.current_node_input,
            "current_node_output": self.current_node_output,
            "execution_history": list(self.execution_history),
            "created_at": self.created_at,
            "paused_at": self.paused_at,
        }


class DebugSessionStore:
    """Thread-safe in-memory registry of active DebugSession objects.

    Provides create/get/delete/list operations. A ``reset()`` method is
    available for test teardown.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sessions: dict[str, DebugSession] = {}  # session_id → DebugSession
        self._by_run: dict[str, str] = {}  # run_id → session_id

    def create(self, run_id: str, flow_id: str, breakpoints: list[str]) -> DebugSession:
        """Create and register a new DebugSession.

        Args:
            run_id: The workflow run ID this session is attached to.
            flow_id: The flow being debugged.
            breakpoints: Node IDs where execution should pause.

        Returns:
            The newly created DebugSession.
        """
        session = DebugSession(
            session_id=str(uuid.uuid4()),
            run_id=run_id,
            flow_id=flow_id,
            status="running",
            breakpoints=set(breakpoints),
            current_node_id=None,
            current_node_input={},
            current_node_output={},
            execution_history=[],
            created_at=time.time(),
            paused_at=None,
            _resume_event=asyncio.Event(),
            _skip_flag=False,
        )
        with self._lock:
            self._sessions[session.session_id] = session
            self._by_run[run_id] = session.session_id
        return session

    def get(self, session_id: str) -> "DebugSession | None":
        """Return the DebugSession for *session_id*, or None."""
        with self._lock:
            return self._sessions.get(session_id)

    def get_by_run_id(self, run_id: str) -> "DebugSession | None":
        """Return the DebugSession attached to *run_id*, or None."""
        with self._lock:
            sid = self._by_run.get(run_id)
            if sid is None:
                return None
            return self._sessions.get(sid)

    def list_active(self) -> "list[DebugSession]":
        """Return all sessions that are not yet completed or aborted."""
        with self._lock:
            return [s for s in self._sessions.values() if s.status not in ("completed", "aborted")]

    def delete(self, session_id: str) -> None:
        """Remove the session from the registry.

        Args:
            session_id: The session to remove.
        """
        with self._lock:
            session = self._sessions.pop(session_id, None)
            if session is not None:
                self._by_run.pop(session.run_id, None)

    def reset(self) -> None:
        """Clear all sessions — for test teardown only."""
        with self._lock:
            self._sessions.clear()
            self._by_run.clear()
debug_session_store = DebugSessionStore()


class CreditLedger:
    """Track credits earned by template authors from installs.

    Each install awards the publisher CREDITS_PER_INSTALL credits.
    Ledger entries are immutable (append-only). Payouts reduce balance.
    """

    CREDITS_PER_INSTALL: int = 10

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: dict[str, list[dict[str, Any]]] = {}

    def credit(
        self,
        publisher_id: str,
        listing_id: str,
        listing_name: str,
        amount: int,
    ) -> dict[str, Any]:
        """Add a credit entry (earned from install). Returns the entry."""
        entry: dict[str, Any] = {
            "entry_id": str(uuid.uuid4()),
            "publisher_id": publisher_id,
            "type": "credit",
            "amount": amount,
            "listing_id": listing_id,
            "listing_name": listing_name,
            "note": "",
            "created_at": time.time(),
        }
        with self._lock:
            self._entries.setdefault(publisher_id, []).append(entry)
        return entry

    def debit(self, publisher_id: str, amount: int, note: str = "") -> dict[str, Any]:
        """Record a payout/debit. Returns the entry.

        Raises:
            ValueError: If current balance is less than the requested amount.
        """
        with self._lock:
            bal = self._balance_unlocked(publisher_id)
            if bal < amount:
                raise ValueError(f"Insufficient balance: {bal} < {amount}")
            entry: dict[str, Any] = {
                "entry_id": str(uuid.uuid4()),
                "publisher_id": publisher_id,
                "type": "debit",
                "amount": amount,
                "listing_id": None,
                "listing_name": None,
                "note": note,
                "created_at": time.time(),
            }
            self._entries.setdefault(publisher_id, []).append(entry)
        return entry

    def balance(self, publisher_id: str) -> int:
        """Return current credit balance for publisher."""
        with self._lock:
            return self._balance_unlocked(publisher_id)

    def _balance_unlocked(self, publisher_id: str) -> int:
        """Compute balance without acquiring the lock (caller must hold it)."""
        entries = self._entries.get(publisher_id, [])
        total = 0
        for e in entries:
            if e["type"] == "credit":
                total += e["amount"]
            else:
                total -= e["amount"]
        return total

    def ledger(self, publisher_id: str, limit: int = 100) -> list[dict[str, Any]]:
        """Return all ledger entries for publisher, newest first."""
        with self._lock:
            entries = list(self._entries.get(publisher_id, []))
        entries.reverse()
        return entries[:limit]

    def total_earned(self, publisher_id: str) -> int:
        """Return total credits ever earned (credits only, not debits)."""
        with self._lock:
            entries = self._entries.get(publisher_id, [])
            return sum(e["amount"] for e in entries if e["type"] == "credit")

    def payout_report(self, publisher_id: str) -> dict[str, Any]:
        """Return summary: balance, total_earned, total_paid_out, entry_count, per_listing breakdown."""
        with self._lock:
            entries = self._entries.get(publisher_id, [])
            total_earned = sum(e["amount"] for e in entries if e["type"] == "credit")
            total_paid_out = sum(e["amount"] for e in entries if e["type"] == "debit")
            per_listing: dict[str, dict[str, Any]] = {}
            for e in entries:
                if e["type"] != "credit":
                    continue
                lid = e["listing_id"]
                if lid not in per_listing:
                    per_listing[lid] = {
                        "listing_id": lid,
                        "listing_name": e["listing_name"],
                        "installs": 0,
                        "credits_earned": 0,
                    }
                per_listing[lid]["installs"] += 1
                per_listing[lid]["credits_earned"] += e["amount"]
            return {
                "balance": total_earned - total_paid_out,
                "total_earned": total_earned,
                "total_paid_out": total_paid_out,
                "entry_count": len(entries),
                "per_listing": list(per_listing.values()),
            }

    def reset(self) -> None:
        """Clear all data (for testing)."""
        with self._lock:
            self._entries.clear()
credit_ledger = CreditLedger()


class SLAStore:
    """Thread-safe in-memory store for SLA policies and violation tracking."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._policies: dict[str, dict[str, Any]] = {}  # flow_id -> policy
        self._violations: list[dict[str, Any]] = []
        self._run_count_by_owner: dict[str, int] = {}

    def set_policy(
        self,
        flow_id: str,
        owner_id: str,
        max_duration_seconds: float,
        alert_threshold_pct: float = 0.8,
    ) -> dict[str, Any]:
        """Create or update an SLA policy for a flow."""
        with self._lock:
            policy = {
                "policy_id": self._policies.get(flow_id, {}).get("policy_id", str(uuid.uuid4())),
                "flow_id": flow_id,
                "owner_id": owner_id,
                "max_duration_seconds": max_duration_seconds,
                "alert_threshold_pct": alert_threshold_pct,
                "created_at": time.time(),
            }
            self._policies[flow_id] = policy
            return dict(policy)

    def get_policy(self, flow_id: str) -> dict[str, Any] | None:
        """Return the SLA policy for a flow, or None if not set."""
        with self._lock:
            p = self._policies.get(flow_id)
            return dict(p) if p else None

    def delete_policy(self, flow_id: str) -> bool:
        """Delete an SLA policy. Returns True if it existed."""
        with self._lock:
            return self._policies.pop(flow_id, None) is not None

    def list_policies(self, owner_id: str) -> list[dict[str, Any]]:
        """Return all SLA policies owned by *owner_id*."""
        with self._lock:
            return [dict(p) for p in self._policies.values() if p["owner_id"] == owner_id]

    def record_violation(
        self,
        policy_id: str,
        flow_id: str,
        run_id: str,
        actual_duration: float,
        max_duration: float,
    ) -> dict[str, Any]:
        """Record an SLA violation and return the violation dict."""
        pct_over = ((actual_duration - max_duration) / max_duration) * 100.0
        violation: dict[str, Any] = {
            "violation_id": str(uuid.uuid4()),
            "policy_id": policy_id,
            "flow_id": flow_id,
            "run_id": run_id,
            "actual_duration_seconds": actual_duration,
            "max_duration_seconds": max_duration,
            "pct_over": round(pct_over, 2),
            "created_at": time.time(),
        }
        with self._lock:
            self._violations.append(violation)
        return violation

    def increment_run_count(self, owner_id: str) -> None:
        """Track total run count per owner for compliance calculations."""
        with self._lock:
            self._run_count_by_owner[owner_id] = self._run_count_by_owner.get(owner_id, 0) + 1

    def list_violations(
        self,
        flow_id: str | None = None,
        owner_id: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Return violations newest-first, optionally filtered."""
        with self._lock:
            items = list(self._violations)
        # Filter by flow_id
        if flow_id is not None:
            items = [v for v in items if v["flow_id"] == flow_id]
        # Filter by owner_id (look up policies)
        if owner_id is not None:
            with self._lock:
                owned_flows = {
                    fid for fid, p in self._policies.items() if p["owner_id"] == owner_id
                }
            items = [v for v in items if v["flow_id"] in owned_flows]
        # Sort newest first and apply limit
        items.sort(key=lambda v: v["created_at"], reverse=True)
        return items[:limit]

    def compliance_stats(self, owner_id: str) -> dict[str, Any]:
        """Return compliance statistics for an owner.

        Returns dict with total_runs, violations, compliance_rate_pct, and
        by_flow breakdown.
        """
        with self._lock:
            total_runs = self._run_count_by_owner.get(owner_id, 0)
            owned_flows = {fid for fid, p in self._policies.items() if p["owner_id"] == owner_id}
            owner_violations = [v for v in self._violations if v["flow_id"] in owned_flows]
        violation_count = len(owner_violations)
        if total_runs == 0:
            compliance_rate = 100.0
        else:
            compliance_rate = round(((total_runs - violation_count) / total_runs) * 100.0, 2)
        # Per-flow breakdown
        by_flow: dict[str, dict[str, Any]] = {}
        for v in owner_violations:
            fid = v["flow_id"]
            entry = by_flow.setdefault(fid, {"flow_id": fid, "violations": 0})
            entry["violations"] += 1
        return {
            "total_runs": total_runs,
            "violations": violation_count,
            "compliance_rate_pct": compliance_rate,
            "by_flow": list(by_flow.values()),
        }

    def reset(self) -> None:
        """Clear all data (for testing)."""
        with self._lock:
            self._policies.clear()
            self._violations.clear()
            self._run_count_by_owner.clear()
sla_store = SLAStore()


class WebhookDebugStore:
    """Thread-safe in-memory store for webhook debug entries.

    Maintains a bounded FIFO buffer of webhook deliveries for real-time
    inspection and retry.  Oldest entries are evicted when the store
    exceeds MAX_ENTRIES.
    """

    MAX_ENTRIES = 200

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: list[dict[str, Any]] = []

    def record(self, entry: dict[str, Any]) -> dict[str, Any]:
        """Append a debug entry, evicting the oldest if over capacity."""
        with self._lock:
            self._entries.append(entry)
            while len(self._entries) > self.MAX_ENTRIES:
                self._entries.pop(0)
        return entry

    def list(
        self,
        flow_id: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Return entries newest-first, optionally filtered by *flow_id*."""
        with self._lock:
            items = list(self._entries)
        if flow_id is not None:
            items = [e for e in items if e.get("flow_id") == flow_id]
        items.reverse()
        return items[:limit]

    def get(self, entry_id: str) -> dict[str, Any] | None:
        """Return a single entry by ID, or None."""
        with self._lock:
            for entry in self._entries:
                if entry["entry_id"] == entry_id:
                    return entry
        return None

    def clear(self) -> None:
        """Remove all stored debug entries."""
        with self._lock:
            self._entries.clear()

    def reset(self) -> None:
        """Alias for clear — used by conftest between tests."""
        self.clear()
webhook_debug_store = WebhookDebugStore()


class FeaturedStore:
    """Admin-curated list of featured marketplace listings.

    Stores featured metadata: listing_id, featured_at, featured_by, blurb.
    Thread-safe via a reentrant lock.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: dict[str, dict[str, Any]] = {}

    def feature(self, listing_id: str, admin_id: str, blurb: str = "") -> dict[str, Any]:
        """Mark a listing as featured. Returns the featured entry dict."""
        entry: dict[str, Any] = {
            "listing_id": listing_id,
            "featured_at": time.time(),
            "featured_by": admin_id,
            "blurb": blurb,
        }
        with self._lock:
            self._entries[listing_id] = entry
        return entry

    def unfeature(self, listing_id: str) -> bool:
        """Remove a listing from the featured list. Returns False if not found."""
        with self._lock:
            return self._entries.pop(listing_id, None) is not None

    def is_featured(self, listing_id: str) -> bool:
        """Check whether a listing is currently featured."""
        with self._lock:
            return listing_id in self._entries

    def get(self, listing_id: str) -> dict[str, Any] | None:
        """Return featured metadata for a listing, or None if not featured."""
        with self._lock:
            return self._entries.get(listing_id)

    def list_featured(self) -> list[dict[str, Any]]:
        """Return all featured entries, newest first (by featured_at)."""
        with self._lock:
            items = list(self._entries.values())
        items.sort(key=lambda e: e["featured_at"], reverse=True)
        return items

    def reset(self) -> None:
        """Clear all featured entries (for testing)."""
        with self._lock:
            self._entries.clear()
featured_store = FeaturedStore()


class TestSuiteStore:
    """Thread-safe in-memory store for workflow test cases and their results.

    Test cases define expected outputs for a workflow. Results capture the
    outcome of running a test case against the live execution engine.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tests: dict[str, dict[str, Any]] = {}  # test_id -> test_case
        self._results: list[dict[str, Any]] = []

    def add_test(
        self,
        flow_id: str,
        name: str,
        description: str,
        input_data: dict[str, Any],
        expected_output: dict[str, Any],
        match_mode: str = "contains",
        created_by: str = "",
    ) -> dict[str, Any]:
        """Create a new test case and return it."""
        with self._lock:
            test_id = str(uuid.uuid4())
            test_case: dict[str, Any] = {
                "test_id": test_id,
                "flow_id": flow_id,
                "name": name,
                "description": description,
                "input": input_data,
                "expected_output": expected_output,
                "match_mode": match_mode,
                "created_at": time.time(),
                "created_by": created_by,
            }
            self._tests[test_id] = test_case
            return test_case

    def get_test(self, test_id: str) -> dict[str, Any] | None:
        """Return a test case by ID, or None if not found."""
        with self._lock:
            return self._tests.get(test_id)

    def list_tests(self, flow_id: str) -> list[dict[str, Any]]:
        """Return all test cases for a given flow."""
        with self._lock:
            return [t for t in self._tests.values() if t["flow_id"] == flow_id]

    def delete_test(self, test_id: str) -> bool:
        """Delete a test case. Returns True if found and deleted, False otherwise."""
        with self._lock:
            if test_id in self._tests:
                del self._tests[test_id]
                return True
            return False

    def add_result(self, result: dict[str, Any]) -> dict[str, Any]:
        """Store a test result and return it."""
        with self._lock:
            result.setdefault("result_id", str(uuid.uuid4()))
            self._results.append(result)
            return result

    def list_results(
        self,
        test_id: str | None = None,
        flow_id: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Return results filtered by test_id or flow_id, newest first."""
        with self._lock:
            filtered = self._results
            if test_id is not None:
                filtered = [r for r in filtered if r.get("test_id") == test_id]
            if flow_id is not None:
                filtered = [r for r in filtered if r.get("flow_id") == flow_id]
            return list(reversed(filtered[-limit:]))

    def suite_summary(self, flow_id: str) -> dict[str, Any]:
        """Return aggregate pass/fail/error counts for a flow."""
        with self._lock:
            results = [r for r in self._results if r.get("flow_id") == flow_id]
            total = len(results)
            passed = sum(1 for r in results if r.get("status") == "pass")
            failed = sum(1 for r in results if r.get("status") == "fail")
            error = sum(1 for r in results if r.get("status") == "error")
            pass_rate = round((passed / total) * 100, 2) if total > 0 else 0.0
            return {
                "total": total,
                "passed": passed,
                "failed": failed,
                "error": error,
                "pass_rate_pct": pass_rate,
            }

    def reset(self) -> None:
        """Clear all stored test cases and results."""
        with self._lock:
            self._tests.clear()
            self._results.clear()
test_suite_store = TestSuiteStore()


class ExecutionDashboardStore:
    """In-memory registry of active/recent workflow executions for real-time dashboard.

    Tracks: run_id, flow_id, flow_name, user_id, status, started_at,
    updated_at, node_count, completed_nodes, input_size_bytes, output_size_bytes,
    paused (bool), killed (bool)
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: dict[str, dict[str, Any]] = {}

    def _build_entry(self, entry: dict[str, Any]) -> dict[str, Any]:
        """Return a copy of the entry with computed fields."""
        e = dict(entry)
        node_count = e.get("node_count", 0)
        completed = e.get("completed_nodes", 0)
        e["progress_pct"] = (completed / node_count * 100) if node_count > 0 else 0.0
        started = e.get("started_at", 0.0)
        updated = e.get("updated_at", started)
        e["duration_ms"] = (updated - started) * 1000
        return e

    def register(
        self,
        run_id: str,
        flow_id: str,
        flow_name: str,
        user_id: str,
        node_count: int,
        input_size_bytes: int = 0,
    ) -> dict[str, Any]:
        """Register a new execution. Returns the created entry dict."""
        now = time.time()
        entry: dict[str, Any] = {
            "run_id": run_id,
            "flow_id": flow_id,
            "flow_name": flow_name,
            "user_id": user_id,
            "status": "running",
            "started_at": now,
            "updated_at": now,
            "node_count": node_count,
            "completed_nodes": 0,
            "input_size_bytes": input_size_bytes,
            "output_size_bytes": 0,
            "paused": False,
            "killed": False,
        }
        with self._lock:
            self._entries[run_id] = entry
        return self._build_entry(entry)

    def update_status(
        self,
        run_id: str,
        status: str,
        completed_nodes: int | None = None,
        output_size_bytes: int | None = None,
    ) -> bool:
        """Update the status of an execution. Returns False if run_id not found."""
        with self._lock:
            entry = self._entries.get(run_id)
            if entry is None:
                return False
            entry["status"] = status
            entry["updated_at"] = time.time()
            if completed_nodes is not None:
                entry["completed_nodes"] = completed_nodes
            if output_size_bytes is not None:
                entry["output_size_bytes"] = output_size_bytes
        return True

    def pause(self, run_id: str) -> bool:
        """Set paused=True for the given run. Returns False if not found."""
        with self._lock:
            entry = self._entries.get(run_id)
            if entry is None:
                return False
            entry["paused"] = True
            entry["status"] = "paused"
            entry["updated_at"] = time.time()
        return True

    def resume(self, run_id: str) -> bool:
        """Set paused=False for the given run. Returns False if not found."""
        with self._lock:
            entry = self._entries.get(run_id)
            if entry is None:
                return False
            entry["paused"] = False
            entry["status"] = "running"
            entry["updated_at"] = time.time()
        return True

    def kill(self, run_id: str) -> bool:
        """Set killed=True and status='killed'. Returns False if not found."""
        with self._lock:
            entry = self._entries.get(run_id)
            if entry is None:
                return False
            entry["killed"] = True
            entry["status"] = "killed"
            entry["updated_at"] = time.time()
        return True

    def get(self, run_id: str) -> dict[str, Any] | None:
        """Return a single entry by run_id, or None."""
        with self._lock:
            entry = self._entries.get(run_id)
            if entry is None:
                return None
            return self._build_entry(entry)

    def list_active(self) -> list[dict[str, Any]]:
        """Return entries with status in ('running', 'paused'), newest first."""
        with self._lock:
            active = [
                self._build_entry(e)
                for e in self._entries.values()
                if e.get("status") in ("running", "paused")
            ]
        active.sort(key=lambda e: e.get("started_at", 0), reverse=True)
        return active

    def list_recent(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return all entries, newest first, up to *limit*."""
        with self._lock:
            entries = [self._build_entry(e) for e in self._entries.values()]
        entries.sort(key=lambda e: e.get("started_at", 0), reverse=True)
        return entries[:limit]

    def stats(self) -> dict[str, Any]:
        """Return aggregate statistics for the dashboard."""
        now = time.time()
        today_start = now - (now % 86400)  # midnight UTC approximation
        with self._lock:
            all_entries = list(self._entries.values())

        active_count = 0
        total_today = 0
        kill_count = 0
        durations: list[float] = []

        for e in all_entries:
            if e.get("status") in ("running", "paused"):
                active_count += 1
            if e.get("started_at", 0) >= today_start:
                total_today += 1
            if e.get("killed"):
                kill_count += 1
            started = e.get("started_at", 0)
            updated = e.get("updated_at", started)
            durations.append((updated - started) * 1000)

        avg_duration_ms = sum(durations) / len(durations) if durations else 0.0

        return {
            "active_count": active_count,
            "total_today": total_today,
            "avg_duration_ms": round(avg_duration_ms, 2),
            "kill_count": kill_count,
        }

    def stats_for_flow(self, flow_id: str) -> dict[str, Any]:
        """Return per-flow aggregate statistics.

        Returns total_runs, success_count, failure_count, last_run_at (ISO or None),
        avg_duration_ms, and active_count (currently running/paused for this flow).
        """
        with self._lock:
            flow_entries = [e for e in self._entries.values() if e.get("flow_id") == flow_id]

        total_runs = len(flow_entries)
        success_count = sum(1 for e in flow_entries if e.get("status") == "completed")
        failure_count = sum(1 for e in flow_entries if e.get("status") == "failed")
        active_count = sum(
            1 for e in flow_entries if e.get("status") in ("running", "paused")
        )
        durations: list[float] = []
        last_started: float = 0.0
        for e in flow_entries:
            started = e.get("started_at", 0.0)
            updated = e.get("updated_at", started)
            durations.append((updated - started) * 1000)
            if started > last_started:
                last_started = started

        avg_duration_ms = round(sum(durations) / len(durations), 2) if durations else 0.0
        last_run_at = (
            datetime.fromtimestamp(last_started, tz=UTC).isoformat() if last_started else None
        )
        return {
            "flow_id": flow_id,
            "total_runs": total_runs,
            "success_count": success_count,
            "failure_count": failure_count,
            "active_count": active_count,
            "avg_duration_ms": avg_duration_ms,
            "last_run_at": last_run_at,
        }

    def reset(self) -> None:
        """Clear all entries."""
        with self._lock:
            self._entries.clear()
execution_dashboard_store = ExecutionDashboardStore()


class RatingStore:
    """Per-listing star ratings. One rating per user per listing (upsert on re-rate)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # listing_id -> {user_id: int (1-5)}
        self._ratings: dict[str, dict[str, int]] = {}

    def rate(self, listing_id: str, user_id: str, stars: int) -> dict[str, Any]:
        """Upsert a rating. Returns {avg_rating, rating_count}."""
        with self._lock:
            bucket = self._ratings.setdefault(listing_id, {})
            bucket[user_id] = stars
            return self._stats(listing_id)

    def get_stats(self, listing_id: str) -> dict[str, Any]:
        """Return {avg_rating: float, rating_count: int}."""
        with self._lock:
            return self._stats(listing_id)

    def _stats(self, listing_id: str) -> dict[str, Any]:
        bucket = self._ratings.get(listing_id, {})
        if not bucket:
            return {"avg_rating": 0.0, "rating_count": 0}
        vals = list(bucket.values())
        return {"avg_rating": round(sum(vals) / len(vals), 2), "rating_count": len(vals)}

    def reset(self) -> None:
        with self._lock:
            self._ratings.clear()


class ReviewStore:
    """Text reviews with optional star rating per listing."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # listing_id -> list[review_dict]
        self._reviews: dict[str, list[dict[str, Any]]] = {}

    def add(
        self, listing_id: str, user_id: str, text: str, stars: int | None = None
    ) -> dict[str, Any]:
        """Add a review for a listing. Returns the new review dict."""
        with self._lock:
            review: dict[str, Any] = {
                "review_id": str(uuid.uuid4()),
                "listing_id": listing_id,
                "user_id": user_id,
                "text": text,
                "stars": stars,
                "created_at": time.time(),
            }
            self._reviews.setdefault(listing_id, []).append(review)
            return review

    def list(self, listing_id: str, limit: int = 20) -> list[dict[str, Any]]:
        """Return reviews for a listing, newest first, up to limit."""
        with self._lock:
            items = self._reviews.get(listing_id, [])
            # newest first
            return list(reversed(items))[:limit]

    def reset(self) -> None:
        with self._lock:
            self._reviews.clear()


class ReplyStore:
    """Publisher replies to reviews. One reply per review (upsert on re-reply)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # review_id -> reply dict
        self._replies: dict[str, dict[str, Any]] = {}

    def add_reply(self, review_id: str, publisher_id: str, text: str) -> dict[str, Any]:
        """Add or update a publisher reply for a review."""
        with self._lock:
            reply: dict[str, Any] = {
                "reply_id": str(uuid.uuid4()),
                "review_id": review_id,
                "publisher_id": publisher_id,
                "text": text,
                "created_at": time.time(),
            }
            self._replies[review_id] = reply
            return reply

    def get_reply(self, review_id: str) -> dict[str, Any] | None:
        """Return the reply for a review, or None if no reply exists."""
        with self._lock:
            return self._replies.get(review_id)

    def reset(self) -> None:
        """Clear all stored replies."""
        with self._lock:
            self._replies.clear()


class IssueStore:
    """Issue reports for marketplace listings."""

    VALID_TYPES = {"broken", "malware", "spam", "outdated", "other"}

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # listing_id -> list[issue_dict]
        self._issues: dict[str, list[dict[str, Any]]] = {}

    def report(
        self, listing_id: str, user_id: str, issue_type: str, description: str
    ) -> dict[str, Any]:
        """File an issue report for a listing. Returns the new issue dict."""
        with self._lock:
            issue: dict[str, Any] = {
                "issue_id": str(uuid.uuid4()),
                "listing_id": listing_id,
                "user_id": user_id,
                "type": issue_type,
                "description": description,
                "created_at": time.time(),
            }
            self._issues.setdefault(listing_id, []).append(issue)
            return issue

    def list(self, listing_id: str) -> list[dict[str, Any]]:
        """Return all issue reports for a listing, newest first."""
        with self._lock:
            return list(reversed(self._issues.get(listing_id, [])))

    def reset(self) -> None:
        """Clear all stored issues."""
        with self._lock:
            self._issues.clear()


class PresenceStore:
    """Thread-safe in-memory store tracking who is viewing/editing each flow."""

    _EXPIRY_SECONDS = 30

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # flow_id -> {user_id -> {user_id, username, color, last_seen}}
        self._presence: dict[str, dict[str, dict[str, Any]]] = {}

    def join(self, flow_id: str, user_id: str, username: str, color: str) -> None:
        """Register a user as present on a flow."""
        with self._lock:
            self._presence.setdefault(flow_id, {})[user_id] = {
                "user_id": user_id,
                "username": username,
                "color": color,
                "last_seen": time.time(),
            }

    def heartbeat(self, flow_id: str, user_id: str) -> None:
        """Update last_seen timestamp for a user on a flow."""
        with self._lock:
            flow_users = self._presence.get(flow_id, {})
            if user_id in flow_users:
                flow_users[user_id]["last_seen"] = time.time()

    def leave(self, flow_id: str, user_id: str) -> None:
        """Remove a user from a flow's presence list."""
        with self._lock:
            flow_users = self._presence.get(flow_id, {})
            flow_users.pop(user_id, None)

    def get_presence(self, flow_id: str) -> list[dict[str, Any]]:
        """Return active users (seen within the last 30 seconds)."""
        cutoff = time.time() - self._EXPIRY_SECONDS
        with self._lock:
            flow_users = self._presence.get(flow_id, {})
            return [
                dict(entry) for entry in flow_users.values()
                if entry["last_seen"] >= cutoff
            ]

    def reset(self) -> None:
        """Clear all presence state."""
        with self._lock:
            self._presence.clear()


class NodeLockStore:
    """Thread-safe in-memory optimistic locking for workflow nodes."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # flow_id -> {node_id -> {user_id, username, acquired_at}}
        self._locks: dict[str, dict[str, dict[str, Any]]] = {}

    def acquire(self, flow_id: str, node_id: str, user_id: str, username: str) -> bool:
        """Acquire a lock on a node. Returns False if already locked by another user."""
        with self._lock:
            flow_locks = self._locks.setdefault(flow_id, {})
            existing = flow_locks.get(node_id)
            if existing and existing["user_id"] != user_id:
                return False
            flow_locks[node_id] = {
                "user_id": user_id,
                "username": username,
                "acquired_at": datetime.now(UTC).isoformat(),
            }
            return True

    def release(self, flow_id: str, node_id: str, user_id: str) -> bool:
        """Release a node lock. Only the lock owner can release it."""
        with self._lock:
            flow_locks = self._locks.get(flow_id, {})
            existing = flow_locks.get(node_id)
            if existing and existing["user_id"] == user_id:
                del flow_locks[node_id]
                return True
            return False

    def release_all_for_user(self, flow_id: str, user_id: str) -> int:
        """Release all locks held by a user on a flow. Returns count released."""
        released = 0
        with self._lock:
            flow_locks = self._locks.get(flow_id, {})
            to_remove = [
                nid for nid, info in flow_locks.items()
                if info["user_id"] == user_id
            ]
            for nid in to_remove:
                del flow_locks[nid]
                released += 1
        return released

    def get_locks(self, flow_id: str) -> dict[str, dict[str, Any]]:
        """Return all active locks for a flow."""
        with self._lock:
            return {
                nid: dict(info)
                for nid, info in self._locks.get(flow_id, {}).items()
            }

    def reset(self) -> None:
        """Clear all lock state."""
        with self._lock:
            self._locks.clear()


class CollaborationActivityStore:
    """Thread-safe in-memory per-flow activity feed (last 50 events per flow)."""

    _MAX_EVENTS = 50

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._events: dict[str, list[dict[str, Any]]] = {}

    def record(
        self,
        flow_id: str,
        user_id: str,
        username: str,
        action: str,
        detail: str = "",
    ) -> dict[str, Any]:
        """Append an activity event to the flow's feed."""
        event: dict[str, Any] = {
            "id": str(uuid.uuid4()),
            "flow_id": flow_id,
            "user_id": user_id,
            "username": username,
            "action": action,
            "detail": detail,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        with self._lock:
            events = self._events.setdefault(flow_id, [])
            events.append(event)
            # Trim to most recent _MAX_EVENTS
            if len(events) > self._MAX_EVENTS:
                self._events[flow_id] = events[-self._MAX_EVENTS:]
        return event

    def get_activity(self, flow_id: str, limit: int = 20) -> list[dict[str, Any]]:
        """Return most recent events for a flow, newest first."""
        with self._lock:
            events = list(self._events.get(flow_id, []))
        events.sort(key=lambda e: e["timestamp"], reverse=True)
        return events[:limit]

    def reset(self) -> None:
        """Clear all activity state."""
        with self._lock:
            self._events.clear()


class PluginManifest(BaseModel):
    """Schema describing a third-party plugin that can be used as a workflow node."""

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


class PluginRegistry:
    """Thread-safe in-memory store for registered marketplace plugins."""

    # Node types reserved for built-in applets -- plugins cannot claim these.
    RESERVED_NODE_TYPES: set[str] = {
        "llm",
        "imagegen",
        "code",
        "http_request",
        "transform",
        "if_else",
        "merge",
        "foreach",
        "start",
        "end",
        "webhook_trigger",
        "scheduler",
        "subflow",
        "branch",
        "compound_merge",
    }

    def __init__(self) -> None:
        self._plugins: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def register(self, manifest: PluginManifest) -> str:
        """Register a plugin and return a unique plugin_id.

        Raises ValueError if the manifest's node_type collides with a built-in.
        """
        if manifest.node_type in self.RESERVED_NODE_TYPES:
            raise ValueError(
                f"node_type '{manifest.node_type}' is reserved for built-in applets"
            )
        plugin_id = str(uuid.uuid4())
        with self._lock:
            self._plugins[plugin_id] = {
                "id": plugin_id,
                "manifest": manifest.model_dump(),
                "installed_at": time.time(),
                "install_count": 0,
            }
        return plugin_id

    def unregister(self, plugin_id: str) -> bool:
        """Remove a plugin. Returns True if found and removed, False otherwise."""
        with self._lock:
            return self._plugins.pop(plugin_id, None) is not None

    def get(self, plugin_id: str) -> dict[str, Any] | None:
        """Return a plugin entry by id, or None if not found."""
        with self._lock:
            return self._plugins.get(plugin_id)

    def get_by_node_type(self, node_type: str) -> dict[str, Any] | None:
        """Return the first plugin whose manifest matches *node_type*."""
        with self._lock:
            for entry in self._plugins.values():
                if entry["manifest"]["node_type"] == node_type:
                    return entry
            return None

    def list_all(self) -> list[dict[str, Any]]:
        """Return a shallow copy of all registered plugin entries."""
        with self._lock:
            return list(self._plugins.values())

    def increment_install_count(self, plugin_id: str) -> None:
        """Bump the install counter for a plugin (no-op if id missing)."""
        with self._lock:
            if plugin_id in self._plugins:
                self._plugins[plugin_id]["install_count"] += 1

    def reset(self) -> None:
        """Remove all plugins -- used between tests."""
        with self._lock:
            self._plugins.clear()


# ---------------------------------------------------------------------------
# Singleton instantiations (late-bound — class bodies appear earlier)
# ---------------------------------------------------------------------------

workflow_variable_store = WorkflowVariableStore()

workflow_secret_store = WorkflowSecretStore()

alert_rule_store = AlertRuleStore()

alert_engine = AlertEngine(alert_rule_store)

oauth_client_registry = OAuthClientRegistry()

auth_code_store = AuthorizationCodeStore()

rating_store = RatingStore()

review_store = ReviewStore()

reply_store = ReplyStore()

issue_store = IssueStore()

presence_store = PresenceStore()

node_lock_store = NodeLockStore()

collaboration_activity_store = CollaborationActivityStore()

plugin_registry = PluginRegistry()


# ---------------------------------------------------------------------------
# Additional module-level constants moved from main.py to support store classes
# ---------------------------------------------------------------------------

_ALLOWED_REACTIONS: frozenset[str] = frozenset(
    ["👍", "👎", "❤️", "🔥", "🎉", "🚀", "⚠️", "✅", "❌", "🤔"]
)

_WEBHOOK_EVENTS: frozenset[str] = frozenset(
    ["run.started", "run.completed", "run.failed", "flow.updated", "flow.deleted"]
)

_CUSTOM_FIELD_TYPES: frozenset[str] = frozenset(["string", "number", "boolean", "date"])

_COLLABORATOR_ROLES: frozenset[str] = frozenset(["owner", "editor", "viewer", "commenter"])

_ENV_NAMES: frozenset[str] = frozenset(["development", "staging", "production"])

_NOTIF_EVENTS: frozenset[str] = frozenset(
    ["run.completed", "run.failed", "flow.updated", "flow.deleted", "collaborator.added"]
)

_NOTIF_CHANNELS: frozenset[str] = frozenset(["email", "slack", "in_app"])

_COST_CURRENCIES: frozenset[str] = frozenset(["USD", "EUR", "GBP", "JPY", "AUD", "CAD"])

_VISIBILITY_LEVELS: frozenset[str] = frozenset(["private", "internal", "public"])

_TRIGGER_TYPES: frozenset[str] = frozenset(["manual", "webhook", "schedule", "event", "api"])

_OUTPUT_DEST_TYPES: frozenset[str] = frozenset(["webhook", "s3", "database", "file", "none"])

_ACL_PERMISSIONS: frozenset[str] = frozenset(["read", "write", "execute", "admin"])

_EXECUTION_MODES: frozenset[str] = frozenset(["async", "sync", "dry_run"])

_GEO_MODES: frozenset[str] = frozenset(["allowlist", "blocklist", "none"])

_DATA_CLASSIFICATION_LEVELS: frozenset[str] = frozenset(
    ["public", "internal", "confidential", "restricted"]
)

_NOTIF_CHANNEL_TYPES: frozenset[str] = frozenset(["email", "slack", "webhook", "pagerduty"])

_NOTIF_CHANNEL_EVENTS: frozenset[str] = frozenset(
    ["run.started", "run.completed", "run.failed", "run.cancelled"]
)
