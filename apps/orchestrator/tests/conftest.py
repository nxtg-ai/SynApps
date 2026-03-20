import importlib

import pytest

import apps.orchestrator.db as db_module
from apps.orchestrator.main import (
    audit_log_store,
    credit_ledger,
    execution_quota_store,
    issue_store,
    rating_store,
    reply_store,
    review_store,
    sla_store,
    webhook_debug_store,
)
from apps.orchestrator.middleware.rate_limiter import (
    TokenBucketRegistry,
    _SlidingWindowCounter,
)


@pytest.fixture(autouse=True)
def setup_default_db_env(monkeypatch):
    """
    Ensures that the default DATABASE_URL for tests is always in-memory SQLite.
    This runs before any other fixture, setting the environment variable.
    """
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    # Reload db module so the engine picks up the in-memory URL
    importlib.reload(db_module)


@pytest.fixture(autouse=True)
def _reset_rate_limit_counter(monkeypatch):
    """Reset the rate limiter sliding window counter and token buckets between tests.

    Without this, tests sharing the same anonymous IP key accumulate
    requests across the suite and hit 429 after 30 total requests.
    """
    monkeypatch.setattr(
        "apps.orchestrator.middleware.rate_limiter._counter",
        _SlidingWindowCounter(),
    )
    monkeypatch.setattr(
        "apps.orchestrator.middleware.rate_limiter._token_buckets",
        TokenBucketRegistry(),
    )


@pytest.fixture(autouse=True)
def _reset_shared_stores():
    """Reset in-memory stores that accumulate state across the full test suite.

    execution_quota_store and audit_log_store are module-level singletons.
    Without resetting them between tests, quota counts and audit entries from
    one test bleed into later tests — causing intermittent 429s and stale
    audit results in webhook/analytics integration tests.
    """
    execution_quota_store.reset()
    audit_log_store.reset()
    rating_store.reset()
    review_store.reset()
    reply_store.reset()
    issue_store.reset()
    credit_ledger.reset()
    sla_store.reset()
    webhook_debug_store.reset()
    yield
    # Post-test cleanup (belt-and-suspenders for any state written during test)
    execution_quota_store.reset()
    audit_log_store.reset()
    rating_store.reset()
    review_store.reset()
    reply_store.reset()
    issue_store.reset()
    credit_ledger.reset()
    sla_store.reset()
    webhook_debug_store.reset()
