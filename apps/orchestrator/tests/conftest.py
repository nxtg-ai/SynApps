import importlib

import pytest

import apps.orchestrator.db as db_module
from apps.orchestrator.main import (
    activity_feed_store,
    admin_key_registry,
    alert_rule_store,
    audit_log_store,
    auth_code_store,
    collaboration_activity_store,
    connector_health,
    cost_tracker_store,
    credit_ledger,
    debug_session_store,
    execution_dashboard_store,
    execution_log_store,
    execution_quota_store,
    featured_store,
    flow_access_log_store,
    flow_alias_store,
    flow_annotation_store,
    flow_archive_store,
    flow_bookmark_store,
    flow_changelog_store,
    flow_collaborator_store,
    flow_concurrency_store,
    flow_contact_store,
    flow_cost_config_store,
    flow_custom_field_store,
    flow_dependency_store,
    flow_description_store,
    flow_edit_lock_store,
    flow_environment_store,
    flow_expiry_store,
    flow_favorite_store,
    flow_group_store,
    flow_input_schema_store,
    flow_label_store,
    flow_metadata_store,
    flow_notif_pref_store,
    flow_output_schema_store,
    flow_pin_store,
    flow_priority_store,
    flow_rate_limit_store,
    flow_reaction_store,
    flow_retry_policy_store,
    flow_run_preset_store,
    flow_schedule_store,
    flow_share_store,
    flow_snapshot_store,
    flow_tag_store,
    flow_timeout_store,
    flow_visibility_store,
    flow_watch_store,
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
        # Use a higher burst in tests so that polling loops (up to 1 req/s) don't
        # exhaust the default TOKEN_BUCKET_BURST=10 before the run reaches a
        # terminal status — especially under full-suite event loop contention.
        TokenBucketRegistry(default_burst=100),
    )


def _reset_all_stores() -> None:
    """Reset every in-memory singleton store to a clean state."""
    # Core execution / quota
    execution_quota_store.reset()
    execution_log_store.reset()
    execution_dashboard_store.reset()
    replay_store.reset()
    cost_tracker_store.reset()
    sse_event_bus.reset()
    # Audit / compliance
    audit_log_store.reset()
    rollback_audit_store.reset()
    # Auth / keys
    admin_key_registry.reset()
    auth_code_store.reset()
    oauth_client_registry.reset()
    # Workflows: variables, secrets, versions, test, permissions, notifications
    workflow_variable_store.reset()
    workflow_secret_store.reset()
    workflow_version_store.reset()
    workflow_test_store.reset()
    workflow_permission_store.reset()
    notification_store.reset()
    # Debugging
    debug_session_store.reset()
    # Marketplace / publisher
    marketplace_registry.reset()
    template_registry.reset()
    rating_store.reset()
    review_store.reset()
    reply_store.reset()
    issue_store.reset()
    credit_ledger.reset()
    featured_store.reset()
    # Monitoring / SLA / connectors
    sla_store.reset()
    alert_rule_store.reset()
    connector_health.reset()
    # Collaboration
    presence_store.reset()
    node_lock_store.reset()
    collaboration_activity_store.reset()
    activity_feed_store.reset()
    node_comment_store.reset()
    # Webhooks / triggers / tasks
    webhook_debug_store.reset()
    webhook_trigger_registry.reset()
    task_queue.reset()
    # Subflows / plugins
    subflow_registry.reset()
    plugin_registry.reset()
    # Suites
    test_suite_store.reset()
    # Flow tags / favorites / descriptions / archive / pins / labels / shares / groups / access log
    flow_tag_store.reset()
    flow_favorite_store.reset()
    flow_pin_store.reset()
    flow_description_store.reset()
    flow_archive_store.reset()
    flow_label_store.reset()
    flow_share_store.reset()
    flow_group_store.reset()
    flow_access_log_store.reset()
    flow_watch_store.reset()
    flow_webhook_store.reset()
    flow_edit_lock_store.reset()
    flow_environment_store.reset()
    flow_expiry_store.reset()
    flow_alias_store.reset()
    flow_annotation_store.reset()
    flow_bookmark_store.reset()
    flow_changelog_store.reset()
    flow_collaborator_store.reset()
    flow_custom_field_store.reset()
    flow_snapshot_store.reset()
    flow_dependency_store.reset()
    flow_rate_limit_store.reset()
    flow_reaction_store.reset()
    flow_run_preset_store.reset()
    flow_schedule_store.reset()
    flow_metadata_store.reset()
    flow_notif_pref_store.reset()
    flow_priority_store.reset()
    flow_concurrency_store.reset()
    flow_contact_store.reset()
    flow_cost_config_store.reset()
    flow_input_schema_store.reset()
    flow_output_schema_store.reset()
    flow_retry_policy_store.reset()
    flow_timeout_store.reset()
    flow_visibility_store.reset()


@pytest.fixture(autouse=True)
def _reset_shared_stores():
    """Reset every in-memory store singleton between tests.

    Prevents state from one test bleeding into later tests, which is the
    root cause of intermittent failures (429s, stale audit entries,
    lingering webhook triggers, debug sessions with dangling tasks, etc.).
    """
    _reset_all_stores()
    yield
    # Belt-and-suspenders: clean up anything written during the test too.
    _reset_all_stores()
