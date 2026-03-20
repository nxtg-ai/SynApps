"""Tests for Marketplace Analytics — N-45.

Covers:
  - RatingStore unit tests
  - ReviewStore unit tests
  - TrendingService unit tests
  - Integration tests for the analytics endpoints:
      POST /api/v1/marketplace/{listing_id}/rate
      POST /api/v1/marketplace/{listing_id}/review
      GET  /api/v1/marketplace/{listing_id}/reviews
      GET  /api/v1/marketplace/trending
      GET  /api/v1/marketplace/publisher/dashboard
"""

import time
import uuid

import pytest
from fastapi.testclient import TestClient

from apps.orchestrator.main import (
    MarketplaceRegistry,
    RatingStore,
    ReviewStore,
    TrendingService,
    app,
    marketplace_registry,
    rating_store,
    review_store,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_all():
    """Clear all mutable singletons before and after each test."""
    marketplace_registry.reset()
    rating_store.reset()
    review_store.reset()
    yield
    marketplace_registry.reset()
    rating_store.reset()
    review_store.reset()


def _publish_direct(
    registry: MarketplaceRegistry,
    name: str = "Test Listing",
    category: str = "notification",
    tags: list[str] | None = None,
    publisher_id: str | None = None,
) -> dict:
    """Publish a listing directly into a registry for test setup."""
    return registry.publish(
        {
            "name": name,
            "description": f"Description for {name}",
            "category": category,
            "tags": tags or [],
            "author": "test-author",
            "publisher_id": publisher_id,
            "nodes": [],
            "edges": [],
        }
    )


def _register(client: TestClient) -> str:
    """Register a fresh user and return the access_token."""
    email = f"u-{uuid.uuid4().hex[:8]}@example.com"
    resp = client.post("/api/v1/auth/register", json={"email": email, "password": "Pass1234!"})
    assert resp.status_code == 201, resp.text
    return resp.json()["access_token"]


def _create_flow(client: TestClient, token: str, name: str = "Test Flow") -> str:
    """Create a minimal flow via API. Returns the flow ID."""
    uid = uuid.uuid4().hex[:8]
    resp = client.post(
        "/api/v1/flows",
        json={
            "name": name,
            "nodes": [
                {
                    "id": f"n1-{uid}",
                    "type": "start",
                    "position": {"x": 0, "y": 0},
                    "data": {},
                }
            ],
            "edges": [],
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _publish_via_api(
    client: TestClient, token: str, flow_id: str, name: str = "My Listing"
) -> dict:
    """Publish a flow as a marketplace listing via the API. Returns the listing."""
    resp = client.post(
        "/api/v1/marketplace/publish",
        json={
            "flow_id": flow_id,
            "name": name,
            "description": "A published listing",
            "category": "notification",
            "tags": ["test"],
            "author": "test-author",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# Unit tests — RatingStore
# ---------------------------------------------------------------------------


class TestRatingStore:
    """Unit tests for RatingStore (no HTTP)."""

    def test_rate_returns_avg_rating(self):
        """Rate once; avg_rating should equal the submitted stars."""
        store = RatingStore()
        result = store.rate("listing-1", "user-1", 4)
        assert result["avg_rating"] == 4.0
        assert result["rating_count"] == 1

    def test_rate_multiple_users_averages(self):
        """Two users rate 4 and 2; avg should be 3.0."""
        store = RatingStore()
        store.rate("listing-1", "user-1", 4)
        result = store.rate("listing-1", "user-2", 2)
        assert result["avg_rating"] == 3.0
        assert result["rating_count"] == 2

    def test_rate_upsert_replaces_existing(self):
        """Re-rating replaces the previous rating; rating_count stays at 1."""
        store = RatingStore()
        store.rate("listing-1", "user-1", 5)
        result = store.rate("listing-1", "user-1", 1)
        assert result["rating_count"] == 1
        assert result["avg_rating"] == 1.0

    def test_rating_stats_empty_listing(self):
        """get_stats for an unknown listing returns 0.0 avg and 0 count."""
        store = RatingStore()
        stats = store.get_stats("nonexistent-listing")
        assert stats["avg_rating"] == 0.0
        assert stats["rating_count"] == 0

    def test_reset_clears_all_ratings(self):
        """reset() wipes all stored ratings."""
        store = RatingStore()
        store.rate("listing-1", "user-1", 5)
        store.reset()
        stats = store.get_stats("listing-1")
        assert stats["rating_count"] == 0
        assert stats["avg_rating"] == 0.0


# ---------------------------------------------------------------------------
# Unit tests — ReviewStore
# ---------------------------------------------------------------------------


class TestReviewStore:
    """Unit tests for ReviewStore (no HTTP)."""

    def test_add_review_returns_review_dict(self):
        """add() returns a dict with review_id, text, and user_id fields."""
        store = ReviewStore()
        review = store.add("listing-1", "user-1", "Great workflow!")
        assert "review_id" in review
        assert review["text"] == "Great workflow!"
        assert review["user_id"] == "user-1"
        assert review["listing_id"] == "listing-1"
        assert review["stars"] is None

    def test_add_review_with_stars(self):
        """add() persists optional star rating alongside text."""
        store = ReviewStore()
        review = store.add("listing-1", "user-1", "Excellent", stars=5)
        assert review["stars"] == 5

    def test_list_reviews_newest_first(self):
        """list() returns reviews newest-first."""
        store = ReviewStore()
        store.add("listing-1", "user-1", "First review")
        # Tiny sleep to guarantee timestamp ordering
        time.sleep(0.01)
        store.add("listing-1", "user-2", "Second review")
        items = store.list("listing-1")
        assert len(items) >= 2  # Gate 2
        assert items[0]["text"] == "Second review"
        assert items[1]["text"] == "First review"

    def test_list_reviews_empty(self):
        """list() returns an empty list for a listing with no reviews."""
        store = ReviewStore()
        items = store.list("nonexistent-listing")
        assert items == []

    def test_reset_clears_reviews(self):
        """reset() removes all stored reviews."""
        store = ReviewStore()
        store.add("listing-1", "user-1", "Will be wiped")
        store.reset()
        assert store.list("listing-1") == []


# ---------------------------------------------------------------------------
# Unit tests — TrendingService
# ---------------------------------------------------------------------------


class TestTrendingService:
    """Unit tests for TrendingService (no HTTP)."""

    def test_trending_score_uses_install_count(self):
        """Score reflects all-time install_count when no recent installs."""
        listing = {"install_count": 7, "install_timestamps": []}
        # All installs are old; score == 7 * 1 == 7
        assert TrendingService.score(listing) == 7.0

    def test_trending_recent_installs_weighted_higher(self):
        """A listing with recent installs scores higher than one with only old installs."""
        now = time.time()
        recent_listing = {
            "install_count": 5,
            # 3 installs within the last hour (well within 7-day window)
            "install_timestamps": [now - 60, now - 120, now - 180],
        }
        old_listing = {
            "install_count": 30,
            # All installs are 8 days old (outside 7-day window)
            "install_timestamps": [now - (8 * 24 * 3600)] * 30,
        }
        recent_score = TrendingService.score(recent_listing)
        old_score = TrendingService.score(old_listing)
        # recent: 3 recent × 10 + 5 = 35; old: 0 recent × 10 + 30 = 30
        assert recent_score > old_score

    def test_top_returns_sorted_by_score(self):
        """top() returns listings ordered by trending score, highest first."""
        now = time.time()
        low = {"install_count": 1, "install_timestamps": [], "name": "Low"}
        mid = {"install_count": 10, "install_timestamps": [], "name": "Mid"}
        high = {
            "install_count": 5,
            "install_timestamps": [now - 10, now - 20, now - 30],
            "name": "High",
        }
        result = TrendingService.top([low, mid, high], limit=3)
        assert len(result) >= 1  # Gate 2
        # high: 3 recent × 10 + 5 = 35; mid: 10; low: 1
        assert result[0]["name"] == "High"
        assert result[1]["name"] == "Mid"
        assert result[2]["name"] == "Low"


# ---------------------------------------------------------------------------
# Integration tests — rate endpoint
# ---------------------------------------------------------------------------


class TestRateListingEndpoint:
    """HTTP tests for POST /api/v1/marketplace/{listing_id}/rate."""

    def test_rate_listing_returns_200(self):
        """Authenticated POST to rate returns 200 with avg_rating and rating_count."""
        with TestClient(app) as client:
            token = _register(client)
            listing = _publish_direct(marketplace_registry, name="Ratable Listing")
            resp = client.post(
                f"/api/v1/marketplace/{listing['id']}/rate",
                json={"stars": 4},
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "avg_rating" in data
        assert "rating_count" in data
        assert data["listing_id"] == listing["id"]

    def test_rate_listing_requires_auth(self):
        """POST to rate without a token returns 401 when users are registered."""
        with TestClient(app) as client:
            _register(client)  # disable anonymous bootstrap
            listing = _publish_direct(marketplace_registry, name="Auth Guard Listing")
            resp = client.post(
                f"/api/v1/marketplace/{listing['id']}/rate",
                json={"stars": 3},
            )
        assert resp.status_code == 401

    def test_rate_listing_404_unknown(self):
        """POST to rate with an unknown listing_id returns 404."""
        with TestClient(app) as client:
            token = _register(client)
            resp = client.post(
                "/api/v1/marketplace/nonexistent-listing-id/rate",
                json={"stars": 5},
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 404

    def test_rate_updates_avg_rating(self):
        """Rating with 5 stars produces avg_rating == 5.0 in the response."""
        with TestClient(app) as client:
            token = _register(client)
            listing = _publish_direct(marketplace_registry, name="Five Star Listing")
            resp = client.post(
                f"/api/v1/marketplace/{listing['id']}/rate",
                json={"stars": 5},
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 200
        assert resp.json()["avg_rating"] == 5.0


# ---------------------------------------------------------------------------
# Integration tests — review endpoints
# ---------------------------------------------------------------------------


class TestReviewListingEndpoints:
    """HTTP tests for POST/GET /api/v1/marketplace/{listing_id}/review(s)."""

    def test_review_listing_returns_201(self):
        """Authenticated POST review returns 201 and the new review dict."""
        with TestClient(app) as client:
            token = _register(client)
            listing = _publish_direct(marketplace_registry, name="Reviewable Listing")
            resp = client.post(
                f"/api/v1/marketplace/{listing['id']}/review",
                json={"text": "Really useful workflow.", "stars": 5},
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 201
        data = resp.json()
        assert "review_id" in data
        assert data["text"] == "Really useful workflow."

    def test_review_listing_requires_auth(self):
        """POST review without a token returns 401 when users are registered."""
        with TestClient(app) as client:
            _register(client)  # disable anonymous bootstrap
            listing = _publish_direct(marketplace_registry, name="Auth Guard Review Listing")
            resp = client.post(
                f"/api/v1/marketplace/{listing['id']}/review",
                json={"text": "Should be blocked"},
            )
        assert resp.status_code == 401

    def test_list_reviews_returns_200_no_auth(self):
        """GET reviews for a listing returns 200 without any auth header."""
        with TestClient(app) as client:
            _register(client)  # disable anonymous bootstrap
            listing = _publish_direct(marketplace_registry, name="Public Reviews Listing")
            resp = client.get(f"/api/v1/marketplace/{listing['id']}/reviews")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data

    def test_list_reviews_has_items_after_posting(self):
        """After posting a review, listing it returns at least 1 item (Gate 2)."""
        with TestClient(app) as client:
            token = _register(client)
            listing = _publish_direct(marketplace_registry, name="Review Count Listing")
            client.post(
                f"/api/v1/marketplace/{listing['id']}/review",
                json={"text": "Excellent workflow!"},
                headers={"Authorization": f"Bearer {token}"},
            )
            resp = client.get(f"/api/v1/marketplace/{listing['id']}/reviews")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data["items"], list)
        assert len(data["items"]) >= 1  # Gate 2


# ---------------------------------------------------------------------------
# Integration tests — trending endpoint
# ---------------------------------------------------------------------------


class TestTrendingEndpoint:
    """HTTP tests for GET /api/v1/marketplace/trending."""

    def test_trending_endpoint_returns_200_no_auth(self):
        """GET /marketplace/trending returns 200 without authentication."""
        with TestClient(app) as client:
            resp = client.get("/api/v1/marketplace/trending")
        assert resp.status_code == 200

    def test_trending_has_items_key(self):
        """Response includes an 'items' list and 'total' (Gate 2 when listings exist)."""
        with TestClient(app) as client:
            _publish_direct(marketplace_registry, name="Trending Listing A")
            _publish_direct(marketplace_registry, name="Trending Listing B")
            resp = client.get("/api/v1/marketplace/trending")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert isinstance(data["items"], list)
        assert len(data["items"]) >= 1  # Gate 2

    def test_trending_limit_param_respected(self):
        """The limit query param caps results correctly."""
        with TestClient(app) as client:
            for i in range(5):
                _publish_direct(marketplace_registry, name=f"Listing {i}")
            resp = client.get("/api/v1/marketplace/trending?limit=3")
        assert resp.status_code == 200
        assert len(resp.json()["items"]) <= 3


# ---------------------------------------------------------------------------
# Integration tests — publisher dashboard
# ---------------------------------------------------------------------------


class TestPublisherDashboard:
    """HTTP tests for GET /api/v1/marketplace/publisher/dashboard."""

    def test_publisher_dashboard_returns_200(self):
        """GET /marketplace/publisher/dashboard returns 200 for authenticated user."""
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get(
                "/api/v1/marketplace/publisher/dashboard",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "listings" in data
        assert "total" in data

    def test_publisher_dashboard_requires_auth(self):
        """GET /marketplace/publisher/dashboard returns 401 when no auth provided."""
        with TestClient(app) as client:
            _register(client)  # disable anonymous bootstrap
            resp = client.get("/api/v1/marketplace/publisher/dashboard")
        assert resp.status_code == 401

    def test_publisher_dashboard_shows_published_listings(self):
        """Dashboard lists only listings published by the current user (Gate 2)."""
        with TestClient(app) as client:
            token = _register(client)
            # Resolve caller's user ID
            me_resp = client.get(
                "/api/v1/auth/me",
                headers={"Authorization": f"Bearer {token}"},
            )
            user_id = me_resp.json()["id"]

            # Publish a listing as this user via the API
            flow_id = _create_flow(client, token, name="Dashboard Test Flow")
            _publish_via_api(client, token, flow_id, name="My Dashboard Listing")

            # Publish a listing as a different user (direct, different publisher_id)
            _publish_direct(
                marketplace_registry,
                name="Other User Listing",
                publisher_id="other-user-id",
            )

            resp = client.get(
                "/api/v1/marketplace/publisher/dashboard",
                headers={"Authorization": f"Bearer {token}"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data["listings"], list)
        assert len(data["listings"]) >= 1  # Gate 2
        # All listings belong to this user
        for listing in data["listings"]:
            assert listing.get("publisher_id") == user_id
        # Listings include analytics fields
        first = data["listings"][0]
        assert "avg_rating" in first
        assert "rating_count" in first
        assert "recent_reviews" in first
        assert "trending_score" in first

    def test_publisher_dashboard_empty_when_no_listings(self):
        """Dashboard returns an empty list when the user has not published anything."""
        with TestClient(app) as client:
            token = _register(client)
            # Publish a listing under a different publisher
            _publish_direct(
                marketplace_registry,
                name="Someone Else's Listing",
                publisher_id="some-other-user",
            )
            resp = client.get(
                "/api/v1/marketplace/publisher/dashboard",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["listings"] == []

    def test_publisher_dashboard_includes_rating_stats(self):
        """Dashboard listing includes avg_rating reflecting submitted ratings."""
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token)
            listing = _publish_via_api(client, token, flow_id, name="Rated Listing")

            # Rate the listing as the same user (self-rating allowed by design)
            client.post(
                f"/api/v1/marketplace/{listing['id']}/rate",
                json={"stars": 5},
                headers={"Authorization": f"Bearer {token}"},
            )

            resp = client.get(
                "/api/v1/marketplace/publisher/dashboard",
                headers={"Authorization": f"Bearer {token}"},
            )

        assert resp.status_code == 200
        listings = resp.json()["listings"]
        assert len(listings) >= 1  # Gate 2
        assert listings[0]["avg_rating"] == 5.0
        assert listings[0]["rating_count"] == 1
