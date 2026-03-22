"""
D-13: API Rate Limiting + Usage Quotas — Per-user execution quotas.
Tests for ExecutionQuotaStore and integration with POST /flows/{id}/runs.
"""

import uuid

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from apps.orchestrator.main import app
from apps.orchestrator.stores import (
    ExecutionQuotaStore,
    audit_log_store,
    execution_quota_store,
    workflow_permission_store,
)


@pytest.fixture(autouse=True)
def _clean():
    audit_log_store.reset()
    workflow_permission_store.reset()
    execution_quota_store.reset()
    yield
    audit_log_store.reset()
    workflow_permission_store.reset()
    execution_quota_store.reset()


def _register(client: TestClient, email: str | None = None) -> tuple[str, str]:
    email = email or f"quota-{uuid.uuid4().hex[:8]}@test.com"
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "QuotaPass1!"},
    )
    return resp.json()["access_token"], email


# ===========================================================================
# ExecutionQuotaStore unit tests
# ===========================================================================


class TestExecutionQuotaStoreUnit:
    def test_get_usage_returns_dict(self):
        store = ExecutionQuotaStore()
        usage = store.get_usage("user@test.com")
        assert isinstance(usage, dict)  # Gate 2
        assert "executions_this_hour" in usage  # Gate 2
        assert "hourly_limit" in usage  # Gate 2
        assert "monthly_limit" in usage  # Gate 2

    def test_initial_usage_is_zero(self):
        store = ExecutionQuotaStore()
        usage = store.get_usage("user@test.com")
        assert usage["executions_this_hour"] == 0  # Gate 2
        assert usage["executions_this_month"] == 0  # Gate 2

    def test_check_and_record_increments_counters(self):
        store = ExecutionQuotaStore()
        store.check_and_record("user@test.com")
        usage = store.get_usage("user@test.com")
        assert usage["executions_this_hour"] == 1  # Gate 2
        assert usage["executions_this_month"] == 1  # Gate 2

    def test_multiple_records_accumulate(self):
        store = ExecutionQuotaStore()
        for _ in range(5):
            store.check_and_record("user@test.com")
        usage = store.get_usage("user@test.com")
        assert usage["executions_this_hour"] == 5  # Gate 2
        assert usage["executions_this_month"] == 5  # Gate 2

    def test_hourly_limit_raises_429(self):
        store = ExecutionQuotaStore()
        store.set_limits("user@test.com", hourly_limit=2)
        store.check_and_record("user@test.com")
        store.check_and_record("user@test.com")
        with pytest.raises(HTTPException) as exc:
            store.check_and_record("user@test.com")
        assert exc.value.status_code == 429  # Gate 2
        assert exc.value.headers.get("Retry-After") is not None  # Gate 2

    def test_monthly_limit_raises_429(self):
        store = ExecutionQuotaStore()
        store.set_limits("user@test.com", hourly_limit=100, monthly_limit=2)
        store.check_and_record("user@test.com")
        store.check_and_record("user@test.com")
        with pytest.raises(HTTPException) as exc:
            store.check_and_record("user@test.com")
        assert exc.value.status_code == 429  # Gate 2

    def test_default_hourly_limit_is_60(self):
        store = ExecutionQuotaStore()
        usage = store.get_usage("user@test.com")
        assert usage["hourly_limit"] == 60  # Gate 2

    def test_default_monthly_limit_is_1000(self):
        store = ExecutionQuotaStore()
        usage = store.get_usage("user@test.com")
        assert usage["monthly_limit"] == 1000  # Gate 2

    def test_set_limits_overrides_defaults(self):
        store = ExecutionQuotaStore()
        store.set_limits("user@test.com", hourly_limit=10, monthly_limit=50)
        usage = store.get_usage("user@test.com")
        assert usage["hourly_limit"] == 10  # Gate 2
        assert usage["monthly_limit"] == 50  # Gate 2

    def test_hourly_remaining_decrements(self):
        store = ExecutionQuotaStore()
        store.set_limits("user@test.com", hourly_limit=5)
        store.check_and_record("user@test.com")
        store.check_and_record("user@test.com")
        usage = store.get_usage("user@test.com")
        assert usage["hourly_remaining"] == 3  # Gate 2

    def test_monthly_remaining_decrements(self):
        store = ExecutionQuotaStore()
        store.set_limits("user@test.com", monthly_limit=10)
        for _ in range(3):
            store.check_and_record("user@test.com")
        usage = store.get_usage("user@test.com")
        assert usage["monthly_remaining"] == 7  # Gate 2

    def test_reset_clears_all_records(self):
        store = ExecutionQuotaStore()
        store.check_and_record("user@test.com")
        store.reset()
        usage = store.get_usage("user@test.com")
        assert usage["executions_this_hour"] == 0  # Gate 2

    def test_different_users_isolated(self):
        store = ExecutionQuotaStore()
        store.check_and_record("alice@test.com")
        store.check_and_record("alice@test.com")
        store.check_and_record("bob@test.com")
        alice = store.get_usage("alice@test.com")
        bob = store.get_usage("bob@test.com")
        assert alice["executions_this_hour"] == 2  # Gate 2
        assert bob["executions_this_hour"] == 1  # Gate 2

    def test_429_detail_contains_error_key(self):
        store = ExecutionQuotaStore()
        store.set_limits("user@test.com", hourly_limit=1)
        store.check_and_record("user@test.com")
        with pytest.raises(HTTPException) as exc:
            store.check_and_record("user@test.com")
        assert "error" in exc.value.detail  # Gate 2


# ===========================================================================
# GET /usage/me endpoint
# ===========================================================================


class TestUsageMeEndpoint:
    def test_requires_auth(self):
        with TestClient(app) as client:
            _register(client)
            resp = client.get("/api/v1/usage/me")
            assert resp.status_code in (401, 403)  # Gate 2

    def test_returns_200_with_auth(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            resp = client.get(
                "/api/v1/usage/me",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 200  # Gate 2

    def test_response_contains_usage_fields(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            resp = client.get(
                "/api/v1/usage/me",
                headers={"Authorization": f"Bearer {token}"},
            )
            body = resp.json()
            assert "executions_this_hour" in body  # Gate 2
            assert "hourly_limit" in body  # Gate 2
            assert "executions_this_month" in body  # Gate 2
            assert "monthly_limit" in body  # Gate 2

    def test_initial_usage_is_zero(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            resp = client.get(
                "/api/v1/usage/me",
                headers={"Authorization": f"Bearer {token}"},
            )
            body = resp.json()
            assert body["executions_this_hour"] == 0  # Gate 2
            assert body["executions_this_month"] == 0  # Gate 2

    def test_user_field_matches_email(self):
        with TestClient(app) as client:
            token, email = _register(client)
            resp = client.get(
                "/api/v1/usage/me",
                headers={"Authorization": f"Bearer {token}"},
            )
            body = resp.json()
            assert body["user"] == email  # Gate 2


# ===========================================================================
# 429 enforcement on POST /flows/{id}/runs
# ===========================================================================


class TestExecutionQuotaEnforcement:
    def _create_simple_flow(self, client: TestClient, token: str) -> str:
        flow = {
            "name": f"Quota Test {uuid.uuid4().hex[:6]}",
            "nodes": [
                {
                    "id": "start",
                    "type": "start",
                    "position": {"x": 0, "y": 0},
                    "data": {"label": "Start"},
                },
                {
                    "id": "end",
                    "type": "end",
                    "position": {"x": 0, "y": 100},
                    "data": {"label": "End"},
                },
            ],
            "edges": [{"id": "s-e", "source": "start", "target": "end"}],
        }
        resp = client.post(
            "/api/v1/flows",
            json=flow,
            headers={"Authorization": f"Bearer {token}"},
        )
        return resp.json()["id"]

    def test_quota_not_exceeded_returns_202(self):
        with TestClient(app) as client:
            token, email = _register(client)
            flow_id = self._create_simple_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/runs",
                json={"input": {}},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 202  # Gate 2

    def test_hourly_limit_exceeded_returns_429(self):
        with TestClient(app) as client:
            token, email = _register(client)
            # Set hourly limit to 1 for this user
            execution_quota_store.set_limits(email, hourly_limit=1)
            execution_quota_store.check_and_record(email)  # consume the 1 allowed

            flow_id = self._create_simple_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/runs",
                json={"input": {}},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 429  # Gate 2

    def test_429_response_has_retry_after_info(self):
        with TestClient(app) as client:
            token, email = _register(client)
            execution_quota_store.set_limits(email, hourly_limit=1)
            execution_quota_store.check_and_record(email)

            flow_id = self._create_simple_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/runs",
                json={"input": {}},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 429  # Gate 2
            # Retry-After header is preserved by the exception handler
            assert "retry-after" in resp.headers  # Gate 2
            assert int(resp.headers["retry-after"]) >= 1  # Gate 2

    def test_usage_increments_after_run(self):
        with TestClient(app) as client:
            token, email = _register(client)
            flow_id = self._create_simple_flow(client, token)
            client.post(
                f"/api/v1/flows/{flow_id}/runs",
                json={"input": {}},
                headers={"Authorization": f"Bearer {token}"},
            )
            usage = execution_quota_store.get_usage(email)
            assert usage["executions_this_hour"] >= 1  # Gate 2
            assert usage["executions_this_month"] >= 1  # Gate 2
