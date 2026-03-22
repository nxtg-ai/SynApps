"""Tests for Marketplace Review System — publisher replies, issue reporting, avg rating.

Covers:
  - ReplyStore unit tests (add_reply, get_reply, reset)
  - IssueStore unit tests (report, list, reset)
  - Integration tests for publisher reply endpoint
  - Integration tests for issue report endpoint
  - Integration tests for avg_rating on search results
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from apps.orchestrator.main import app
from apps.orchestrator.stores import (
    IssueStore,
    MarketplaceRegistry,
    ReplyStore,
    issue_store,
    marketplace_registry,
    rating_store,
    reply_store,
    review_store,
)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_all():
    """Clear all mutable singletons before and after each test."""
    marketplace_registry.reset()
    rating_store.reset()
    review_store.reset()
    reply_store.reset()
    issue_store.reset()
    yield
    marketplace_registry.reset()
    rating_store.reset()
    review_store.reset()
    reply_store.reset()
    issue_store.reset()


def _register(client: TestClient) -> str:
    """Register a fresh user and return the access_token."""
    email = f"u-{uuid.uuid4().hex[:8]}@example.com"
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Pass1234!"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["access_token"]


def _publish_direct(
    registry: MarketplaceRegistry,
    name: str = "Test Listing",
    category: str = "notification",
    publisher_id: str | None = None,
) -> dict:
    """Publish a listing directly into a registry for test setup."""
    return registry.publish(
        {
            "name": name,
            "description": f"Description for {name}",
            "category": category,
            "tags": [],
            "author": "test-author",
            "publisher_id": publisher_id,
            "nodes": [],
            "edges": [],
        }
    )


# ---------------------------------------------------------------------------
# Unit tests — ReplyStore
# ---------------------------------------------------------------------------


class TestReplyStore:
    """Unit tests for ReplyStore (no HTTP)."""

    def test_add_reply_returns_dict_with_fields(self):
        """add_reply returns a dict with reply_id, review_id, publisher_id, text."""
        store = ReplyStore()
        reply = store.add_reply("rev-1", "pub-1", "Thank you!")
        assert "reply_id" in reply
        assert reply["review_id"] == "rev-1"
        assert reply["publisher_id"] == "pub-1"
        assert reply["text"] == "Thank you!"
        assert "created_at" in reply

    def test_get_reply_returns_stored_reply(self):
        """get_reply returns the reply previously added for a review_id."""
        store = ReplyStore()
        store.add_reply("rev-1", "pub-1", "Thanks!")
        result = store.get_reply("rev-1")
        assert result is not None
        assert result["text"] == "Thanks!"

    def test_get_reply_returns_none_for_unknown(self):
        """get_reply returns None when no reply exists for the review_id."""
        store = ReplyStore()
        assert store.get_reply("nonexistent") is None

    def test_add_reply_upserts_on_same_review(self):
        """Adding a reply to the same review_id replaces the previous reply."""
        store = ReplyStore()
        store.add_reply("rev-1", "pub-1", "First reply")
        store.add_reply("rev-1", "pub-1", "Updated reply")
        result = store.get_reply("rev-1")
        assert result is not None
        assert result["text"] == "Updated reply"

    def test_reset_clears_all_replies(self):
        """reset() removes all stored replies."""
        store = ReplyStore()
        store.add_reply("rev-1", "pub-1", "A reply")
        store.reset()
        assert store.get_reply("rev-1") is None


# ---------------------------------------------------------------------------
# Unit tests — IssueStore
# ---------------------------------------------------------------------------


class TestIssueStore:
    """Unit tests for IssueStore (no HTTP)."""

    def test_report_returns_issue_dict(self):
        """report returns a dict with issue_id, listing_id, user_id, type, description."""
        store = IssueStore()
        issue = store.report("listing-1", "user-1", "broken", "It crashes on load")
        assert "issue_id" in issue
        assert issue["listing_id"] == "listing-1"
        assert issue["user_id"] == "user-1"
        assert issue["type"] == "broken"
        assert issue["description"] == "It crashes on load"
        assert "created_at" in issue

    def test_list_returns_issues_newest_first(self):
        """list returns issues in reverse chronological order."""
        store = IssueStore()
        store.report("listing-1", "user-1", "spam", "Looks like spam")
        store.report("listing-1", "user-2", "malware", "Suspicious code")
        items = store.list("listing-1")
        assert len(items) >= 2  # Gate 2
        assert items[0]["type"] == "malware"
        assert items[1]["type"] == "spam"

    def test_list_returns_empty_for_unknown(self):
        """list returns an empty list for a listing with no reports."""
        store = IssueStore()
        assert store.list("nonexistent") == []

    def test_reset_clears_all_issues(self):
        """reset() removes all stored issues."""
        store = IssueStore()
        store.report("listing-1", "user-1", "other", "Something wrong")
        store.reset()
        assert store.list("listing-1") == []


# ---------------------------------------------------------------------------
# Integration tests — publisher reply endpoint
# ---------------------------------------------------------------------------


class TestPublisherReplyEndpoint:
    """HTTP tests for POST /api/v1/marketplace/reviews/{review_id}/reply."""

    def test_reply_requires_auth(self):
        """POST reply without auth returns 401 when users exist."""
        with TestClient(app) as client:
            _register(client)  # disable anonymous bootstrap
            resp = client.post(
                "/api/v1/marketplace/reviews/some-review-id/reply",
                json={"text": "Thanks!"},
            )
        assert resp.status_code == 401
        assert "error" in resp.json()

    def test_reply_returns_200_with_valid_auth(self):
        """Authenticated POST reply returns 200 with reply data."""
        with TestClient(app) as client:
            token = _register(client)
            listing = _publish_direct(marketplace_registry, name="Reply Test Listing")
            # Create a review first
            review_resp = client.post(
                f"/api/v1/marketplace/{listing['id']}/review",
                json={"text": "Nice workflow!"},
                headers={"Authorization": f"Bearer {token}"},
            )
            review_id = review_resp.json()["review_id"]
            # Now reply to the review
            resp = client.post(
                f"/api/v1/marketplace/reviews/{review_id}/reply",
                json={"text": "Thank you for the feedback!"},
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["text"] == "Thank you for the feedback!"
        assert data["review_id"] == review_id

    def test_reply_appears_in_reviews_list(self):
        """After replying, GET reviews includes the reply on the review."""
        with TestClient(app) as client:
            token = _register(client)
            listing = _publish_direct(marketplace_registry, name="Reply List Test")
            # Add a review
            review_resp = client.post(
                f"/api/v1/marketplace/{listing['id']}/review",
                json={"text": "Good stuff"},
                headers={"Authorization": f"Bearer {token}"},
            )
            review_id = review_resp.json()["review_id"]
            # Reply to it
            client.post(
                f"/api/v1/marketplace/reviews/{review_id}/reply",
                json={"text": "Glad you like it!"},
                headers={"Authorization": f"Bearer {token}"},
            )
            # Check reviews list
            resp = client.get(f"/api/v1/marketplace/{listing['id']}/reviews")
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) >= 1  # Gate 2
        review = items[0]
        assert review["reply"] is not None
        assert review["reply"]["text"] == "Glad you like it!"

    def test_review_without_reply_has_null_reply(self):
        """Reviews without a publisher reply have reply=None."""
        with TestClient(app) as client:
            token = _register(client)
            listing = _publish_direct(marketplace_registry, name="No Reply Test")
            client.post(
                f"/api/v1/marketplace/{listing['id']}/review",
                json={"text": "Needs work"},
                headers={"Authorization": f"Bearer {token}"},
            )
            resp = client.get(f"/api/v1/marketplace/{listing['id']}/reviews")
        items = resp.json()["items"]
        assert len(items) >= 1  # Gate 2
        assert items[0]["reply"] is None


# ---------------------------------------------------------------------------
# Integration tests — issue report endpoint
# ---------------------------------------------------------------------------


class TestIssueReportEndpoint:
    """HTTP tests for POST /api/v1/marketplace/{listing_id}/report."""

    def test_report_returns_201_on_valid_request(self):
        """Authenticated POST report with valid type returns 201."""
        with TestClient(app) as client:
            token = _register(client)
            resp = client.post(
                "/api/v1/marketplace/some-listing/report",
                json={"type": "broken", "description": "Workflow fails on step 3"},
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 201
        data = resp.json()
        assert data["type"] == "broken"
        assert data["description"] == "Workflow fails on step 3"
        assert "issue_id" in data

    def test_report_returns_422_on_invalid_type(self):
        """POST report with invalid type returns 422 (validation error)."""
        with TestClient(app) as client:
            token = _register(client)
            resp = client.post(
                "/api/v1/marketplace/some-listing/report",
                json={"type": "invalid_type", "description": "Some description"},
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 422
        assert "error" in resp.json()

    def test_report_requires_auth(self):
        """POST report without auth returns 401 when users exist."""
        with TestClient(app) as client:
            _register(client)  # disable anonymous bootstrap
            resp = client.post(
                "/api/v1/marketplace/some-listing/report",
                json={"type": "spam", "description": "Spam listing"},
            )
        assert resp.status_code == 401
        assert "error" in resp.json()

    def test_report_validates_description_max_length(self):
        """POST report with description > 1000 chars returns 422."""
        with TestClient(app) as client:
            token = _register(client)
            resp = client.post(
                "/api/v1/marketplace/some-listing/report",
                json={"type": "other", "description": "x" * 1001},
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 422
        assert "error" in resp.json()


# ---------------------------------------------------------------------------
# Integration tests — avg_rating on search results
# ---------------------------------------------------------------------------


class TestAvgRatingOnSearch:
    """HTTP tests verifying avg_rating appears in marketplace search results."""

    def test_search_includes_avg_rating_fields(self):
        """Search results include avg_rating and rating_count fields."""
        with TestClient(app) as client:
            _publish_direct(marketplace_registry, name="Rated Search Listing")
            resp = client.get("/api/v1/marketplace/search")
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) >= 1  # Gate 2
        first = items[0]
        assert "avg_rating" in first
        assert "rating_count" in first

    def test_search_avg_rating_reflects_ratings(self):
        """After rating a listing, search results show the updated avg_rating."""
        with TestClient(app) as client:
            token = _register(client)
            listing = _publish_direct(marketplace_registry, name="Search Rating Listing")
            # Rate the listing
            client.post(
                f"/api/v1/marketplace/{listing['id']}/rate",
                json={"stars": 4},
                headers={"Authorization": f"Bearer {token}"},
            )
            # Search and verify
            resp = client.get("/api/v1/marketplace/search")
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) >= 1  # Gate 2
        matched = [i for i in items if i["id"] == listing["id"]]
        assert len(matched) >= 1  # Gate 2
        assert matched[0]["avg_rating"] == 4.0
        assert matched[0]["rating_count"] == 1

    def test_search_unrated_listing_has_zero_avg(self):
        """Unrated listings show avg_rating=0.0 and rating_count=0 in search."""
        with TestClient(app) as client:
            listing = _publish_direct(marketplace_registry, name="Unrated Listing")
            resp = client.get("/api/v1/marketplace/search")
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) >= 1  # Gate 2
        matched = [i for i in items if i["id"] == listing["id"]]
        assert len(matched) >= 1  # Gate 2
        assert matched[0]["avg_rating"] == 0.0
        assert matched[0]["rating_count"] == 0
