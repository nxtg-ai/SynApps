"""Tests for Publisher Analytics Dashboard — N-50.

Covers:
  - PublisherAnalyticsService unit tests (6)
  - Publisher analytics endpoint integration tests (8)
  - Listing analytics endpoint integration tests (5)
  - Growth trend integration tests (3)

Total: 22 tests.
"""

import time
import uuid
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from apps.orchestrator.main import app
from apps.orchestrator.request_models import PublisherAnalyticsService
from apps.orchestrator.stores import (
    credit_ledger,
    featured_store,
    marketplace_registry,
    rating_store,
    reply_store,
    review_store,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _register(client: TestClient) -> str:
    """Register a fresh user and return the access_token."""
    email = f"u-{uuid.uuid4().hex[:8]}@example.com"
    resp = client.post("/api/v1/auth/register", json={"email": email, "password": "Pass1234!"})
    assert resp.status_code == 201, resp.text
    return resp.json()["access_token"]


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _get_user_id(client: TestClient, token: str) -> str:
    """Extract user ID from the authenticated user's profile."""
    resp = client.get("/api/v1/auth/me", headers=_auth_headers(token))
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


def _publish_direct(
    name: str = "Test Listing",
    category: str = "automation",
    publisher_id: str | None = None,
) -> dict:
    """Publish a listing directly into the registry."""
    return marketplace_registry.publish(
        {
            "name": name,
            "description": f"Description for {name}",
            "category": category,
            "tags": ["test"],
            "author": "test-author",
            "publisher_id": publisher_id,
            "nodes": [{"id": "n1", "type": "llm"}],
            "edges": [],
        }
    )


def _reset_all():
    """Clear all mutable singletons."""
    marketplace_registry.reset()
    rating_store.reset()
    review_store.reset()
    credit_ledger.reset()
    featured_store.reset()
    reply_store.reset()


# ---------------------------------------------------------------------------
# TestPublisherAnalyticsService — 6 unit tests
# ---------------------------------------------------------------------------


class TestPublisherAnalyticsService:
    """Unit tests for the PublisherAnalyticsService class (no HTTP)."""

    def setup_method(self):
        _reset_all()

    def teardown_method(self):
        _reset_all()

    def test_summary_returns_zeros_for_publisher_with_no_listings(self):
        """summary() returns zeroed KPIs when publisher has no listings."""
        result = PublisherAnalyticsService.summary("no-listings-publisher")
        assert result["total_installs"] == 0
        assert result["total_listings"] == 0
        assert result["avg_rating"] == 0.0
        assert result["total_credits_earned"] == 0
        assert result["credit_balance"] == 0
        assert result["total_reviews"] == 0
        assert result["featured_count"] == 0

    def test_summary_reflects_install_count(self):
        """summary() total_installs sums install counts from listings."""
        pub_id = "pub-installs"
        lst1 = _publish_direct(name="Flow A", publisher_id=pub_id)
        lst2 = _publish_direct(name="Flow B", publisher_id=pub_id)
        # Simulate installs
        marketplace_registry.increment_install(lst1["id"])
        marketplace_registry.increment_install(lst1["id"])
        marketplace_registry.increment_install(lst2["id"])

        result = PublisherAnalyticsService.summary(pub_id)
        assert result["total_installs"] == 3
        assert result["total_listings"] == 2

    def test_per_listing_sorted_by_install_count_desc(self):
        """per_listing() returns listings sorted by install_count descending."""
        pub_id = "pub-sort"
        lst_low = _publish_direct(name="Low Installs", publisher_id=pub_id)
        lst_high = _publish_direct(name="High Installs", publisher_id=pub_id)
        marketplace_registry.increment_install(lst_high["id"])
        marketplace_registry.increment_install(lst_high["id"])
        marketplace_registry.increment_install(lst_low["id"])

        result = PublisherAnalyticsService.per_listing(pub_id)
        assert isinstance(result, list)
        assert len(result) >= 2  # Gate 2
        assert result[0]["name"] == "High Installs"
        assert result[0]["install_count"] == 2
        assert result[1]["name"] == "Low Installs"
        assert result[1]["install_count"] == 1

    def test_growth_trend_returns_n_entries_for_n_days(self):
        """growth_trend() returns exactly N date entries for N days."""
        pub_id = "pub-trend-len"
        _publish_direct(name="Trend Flow", publisher_id=pub_id)
        result = PublisherAnalyticsService.growth_trend(pub_id, days=7)
        assert len(result) == 7
        for entry in result:
            assert "date" in entry
            assert "installs" in entry

    def test_growth_trend_counts_in_correct_date_buckets(self):
        """growth_trend() counts installs in the correct date bucket."""
        pub_id = "pub-trend-bucket"
        lst = _publish_direct(name="Bucket Flow", publisher_id=pub_id)
        # Manually add a timestamp for today
        now = time.time()
        lst["install_timestamps"].append(now)
        lst["install_count"] += 1

        result = PublisherAnalyticsService.growth_trend(pub_id, days=7)
        today_str = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        today_entry = next((e for e in result if e["date"] == today_str), None)
        assert today_entry is not None
        assert today_entry["installs"] == 1

    def test_top_templates_returns_at_most_limit(self):
        """top_templates() respects the limit parameter."""
        pub_id = "pub-top"
        for i in range(8):
            _publish_direct(name=f"Template {i}", publisher_id=pub_id)
        result = PublisherAnalyticsService.top_templates(pub_id, limit=3)
        assert len(result) == 3


# ---------------------------------------------------------------------------
# TestPublisherAnalyticsEndpoint — 8 integration tests
# ---------------------------------------------------------------------------


class TestPublisherAnalyticsEndpoint:
    """Integration tests for GET /marketplace/publisher/analytics."""

    def setup_method(self):
        _reset_all()

    def teardown_method(self):
        _reset_all()

    def test_returns_200_with_all_keys(self):
        """GET /marketplace/publisher/analytics returns 200 with expected keys."""
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get(
                "/api/v1/marketplace/publisher/analytics",
                headers=_auth_headers(token),
            )
            assert resp.status_code == 200
            data = resp.json()
            assert "summary" in data
            assert "per_listing" in data
            assert "growth_trend" in data
            assert "top_templates" in data

    def test_requires_auth(self):
        """GET /marketplace/publisher/analytics returns 401 without auth."""
        with TestClient(app) as client:
            # Register a user first so anonymous bootstrap bypass is disabled
            _register(client)
            resp = client.get("/api/v1/marketplace/publisher/analytics")
            assert resp.status_code == 401
            assert "error" in resp.json()

    def test_summary_total_listings_reflects_published_templates(self):
        """summary.total_listings reflects how many templates the publisher has."""
        with TestClient(app) as client:
            token = _register(client)
            user_id = _get_user_id(client, token)
            _publish_direct(name="My Template 1", publisher_id=user_id)
            _publish_direct(name="My Template 2", publisher_id=user_id)

            resp = client.get(
                "/api/v1/marketplace/publisher/analytics",
                headers=_auth_headers(token),
            )
            data = resp.json()
            assert data["summary"]["total_listings"] == 2  # Gate 2: > 0

    def test_per_listing_has_correct_structure(self):
        """per_listing entries contain all expected fields."""
        with TestClient(app) as client:
            token = _register(client)
            user_id = _get_user_id(client, token)
            _publish_direct(name="Struct Flow", publisher_id=user_id)

            resp = client.get(
                "/api/v1/marketplace/publisher/analytics",
                headers=_auth_headers(token),
            )
            per = resp.json()["per_listing"]
            assert isinstance(per, list)
            assert len(per) >= 1  # Gate 2
            entry = per[0]
            for key in (
                "listing_id",
                "name",
                "install_count",
                "avg_rating",
                "rating_count",
                "review_count",
                "credits_earned",
                "trending_score",
                "is_featured",
                "published_at",
            ):
                assert key in entry, f"Missing key: {key}"

    def test_growth_trend_has_date_and_installs(self):
        """growth_trend entries have date + installs keys."""
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get(
                "/api/v1/marketplace/publisher/analytics",
                headers=_auth_headers(token),
            )
            trend = resp.json()["growth_trend"]
            assert isinstance(trend, list)
            assert len(trend) == 30  # default days
            for entry in trend:
                assert "date" in entry
                assert "installs" in entry

    def test_top_templates_list_present(self):
        """top_templates list is present in the response."""
        with TestClient(app) as client:
            token = _register(client)
            user_id = _get_user_id(client, token)
            _publish_direct(name="Top Flow", publisher_id=user_id)

            resp = client.get(
                "/api/v1/marketplace/publisher/analytics",
                headers=_auth_headers(token),
            )
            top = resp.json()["top_templates"]
            assert isinstance(top, list)
            assert len(top) >= 1  # Gate 2

    def test_days_param_changes_trend_length(self):
        """days param changes the growth_trend window length."""
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get(
                "/api/v1/marketplace/publisher/analytics?days=7",
                headers=_auth_headers(token),
            )
            trend = resp.json()["growth_trend"]
            assert len(trend) == 7

    def test_avg_rating_in_summary_reflects_ratings(self):
        """avg_rating in summary reflects ratings given to publisher's listings."""
        with TestClient(app) as client:
            token = _register(client)
            user_id = _get_user_id(client, token)
            lst = _publish_direct(name="Rated Flow", publisher_id=user_id)
            rating_store.rate(lst["id"], "rater1", 5)
            rating_store.rate(lst["id"], "rater2", 3)

            resp = client.get(
                "/api/v1/marketplace/publisher/analytics",
                headers=_auth_headers(token),
            )
            summary = resp.json()["summary"]
            assert summary["avg_rating"] == 4.0


# ---------------------------------------------------------------------------
# TestListingAnalyticsEndpoint — 5 integration tests
# ---------------------------------------------------------------------------


class TestListingAnalyticsEndpoint:
    """Integration tests for GET /marketplace/publisher/analytics/{listing_id}."""

    def setup_method(self):
        _reset_all()

    def teardown_method(self):
        _reset_all()

    def test_returns_200_for_own_listing(self):
        """GET /marketplace/publisher/analytics/{id} returns 200 for own listing."""
        with TestClient(app) as client:
            token = _register(client)
            user_id = _get_user_id(client, token)
            lst = _publish_direct(name="Detail Flow", publisher_id=user_id)

            resp = client.get(
                f"/api/v1/marketplace/publisher/analytics/{lst['id']}",
                headers=_auth_headers(token),
            )
            assert resp.status_code == 200
            data = resp.json()
            assert "listing" in data
            assert "stats" in data
            assert "recent_reviews" in data
            assert "install_trend" in data

    def test_returns_403_for_other_publishers_listing(self):
        """Returns 403 when listing belongs to a different publisher."""
        with TestClient(app) as client:
            token = _register(client)
            lst = _publish_direct(name="Other Publisher Flow", publisher_id="other-pub-id")

            resp = client.get(
                f"/api/v1/marketplace/publisher/analytics/{lst['id']}",
                headers=_auth_headers(token),
            )
            assert resp.status_code == 403
            assert "error" in resp.json()

    def test_returns_404_for_unknown_listing(self):
        """Returns 404 for a non-existent listing ID."""
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get(
                "/api/v1/marketplace/publisher/analytics/nonexistent-id",
                headers=_auth_headers(token),
            )
            assert resp.status_code == 404
            assert "error" in resp.json()

    def test_recent_reviews_list_present(self):
        """recent_reviews list is present in the detail response."""
        with TestClient(app) as client:
            token = _register(client)
            user_id = _get_user_id(client, token)
            lst = _publish_direct(name="Reviewed Flow", publisher_id=user_id)
            review_store.add(lst["id"], "reviewer1", "Great template!", 5)

            resp = client.get(
                f"/api/v1/marketplace/publisher/analytics/{lst['id']}",
                headers=_auth_headers(token),
            )
            data = resp.json()
            reviews = data["recent_reviews"]
            assert isinstance(reviews, list)
            assert len(reviews) >= 1  # Gate 2
            assert reviews[0]["text"] == "Great template!"

    def test_install_trend_has_date_entries(self):
        """install_trend entries have date + installs keys."""
        with TestClient(app) as client:
            token = _register(client)
            user_id = _get_user_id(client, token)
            lst = _publish_direct(name="Trend Detail Flow", publisher_id=user_id)

            resp = client.get(
                f"/api/v1/marketplace/publisher/analytics/{lst['id']}",
                headers=_auth_headers(token),
            )
            trend = resp.json()["install_trend"]
            assert isinstance(trend, list)
            assert len(trend) == 30
            for entry in trend:
                assert "date" in entry
                assert "installs" in entry


# ---------------------------------------------------------------------------
# TestGrowthTrend — 3 integration tests
# ---------------------------------------------------------------------------


class TestGrowthTrend:
    """Integration tests for growth trend accuracy."""

    def setup_method(self):
        _reset_all()

    def teardown_method(self):
        _reset_all()

    def test_install_today_appears_in_trend(self):
        """An install recorded today appears in the trend for today."""
        with TestClient(app) as client:
            token = _register(client)
            user_id = _get_user_id(client, token)
            lst = _publish_direct(name="Today Install", publisher_id=user_id)
            marketplace_registry.increment_install(lst["id"])

            resp = client.get(
                "/api/v1/marketplace/publisher/analytics",
                headers=_auth_headers(token),
            )
            trend = resp.json()["growth_trend"]
            today_str = datetime.now(tz=UTC).strftime("%Y-%m-%d")
            today_entry = next((e for e in trend if e["date"] == today_str), None)
            assert today_entry is not None
            assert today_entry["installs"] >= 1  # Gate 2

    def test_days_param_filters_trend_window(self):
        """days param correctly limits the trend window."""
        with TestClient(app) as client:
            token = _register(client)
            user_id = _get_user_id(client, token)
            _publish_direct(name="Days Filter Flow", publisher_id=user_id)

            resp = client.get(
                "/api/v1/marketplace/publisher/analytics?days=14",
                headers=_auth_headers(token),
            )
            trend = resp.json()["growth_trend"]
            assert len(trend) == 14

    def test_zero_install_days_still_appear(self):
        """Days with zero installs still appear in the trend (complete date range)."""
        with TestClient(app) as client:
            token = _register(client)
            user_id = _get_user_id(client, token)
            _publish_direct(name="Zero Days Flow", publisher_id=user_id)

            resp = client.get(
                "/api/v1/marketplace/publisher/analytics?days=7",
                headers=_auth_headers(token),
            )
            trend = resp.json()["growth_trend"]
            assert len(trend) == 7
            # All entries should have installs == 0 since no installs were made
            for entry in trend:
                assert entry["installs"] == 0
