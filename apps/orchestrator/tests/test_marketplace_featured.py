"""Tests for Marketplace Featured Section — N-48.

Covers:
  - FeaturedStore unit tests (5 tests)
  - Featured admin endpoints integration tests (8 tests)
  - Featured hero integration tests (4 tests)

Total: 17 tests.
"""

import time
import uuid

import pytest
from fastapi.testclient import TestClient

from apps.orchestrator.main import (
    FeaturedStore,
    app,
    featured_store,
    marketplace_registry,
)

# ---------------------------------------------------------------------------
# Shared fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_all():
    """Clear mutable singletons before and after each test."""
    marketplace_registry.reset()
    featured_store.reset()
    yield
    marketplace_registry.reset()
    featured_store.reset()


def _publish_direct(
    name: str = "Test Listing",
    category: str = "automation",
    description: str = "A test listing",
) -> dict:
    """Publish a listing directly into the marketplace registry."""
    return marketplace_registry.publish(
        {
            "name": name,
            "description": description,
            "category": category,
            "tags": ["test"],
            "author": "test-author",
            "nodes": [{"id": "n1", "type": "llm"}],
            "edges": [],
        }
    )


def _register(client: TestClient) -> str:
    """Register a non-admin user and return the access_token."""
    email = f"user-{uuid.uuid4().hex[:8]}@example.com"
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Pass1234!"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["access_token"]


def _register_admin(client: TestClient) -> str:
    """Register an admin user (email starts with 'admin') and return the access_token."""
    email = f"admin{uuid.uuid4().hex[:6]}@test.com"
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "P@ss1234"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["access_token"]


# ---------------------------------------------------------------------------
# TestFeaturedStore — unit tests
# ---------------------------------------------------------------------------


class TestFeaturedStore:
    """Unit tests for the FeaturedStore class."""

    def test_feature_returns_correct_fields(self):
        store = FeaturedStore()
        entry = store.feature("lid-1", "admin-1", blurb="Great workflow")
        assert entry["listing_id"] == "lid-1"
        assert entry["featured_by"] == "admin-1"
        assert entry["blurb"] == "Great workflow"
        assert isinstance(entry["featured_at"], float)

    def test_is_featured_returns_true_after_featuring(self):
        store = FeaturedStore()
        assert store.is_featured("lid-1") is False
        store.feature("lid-1", "admin-1")
        assert store.is_featured("lid-1") is True

    def test_unfeature_returns_false_for_unknown(self):
        store = FeaturedStore()
        assert store.unfeature("nonexistent") is False

    def test_list_featured_newest_first(self):
        store = FeaturedStore()
        store.feature("lid-1", "admin-1")
        time.sleep(0.01)
        store.feature("lid-2", "admin-1")
        items = store.list_featured()
        assert len(items) == 2
        assert items[0]["listing_id"] == "lid-2"
        assert items[1]["listing_id"] == "lid-1"

    def test_reset_clears_all(self):
        store = FeaturedStore()
        store.feature("lid-1", "admin-1")
        store.feature("lid-2", "admin-1")
        assert len(store.list_featured()) == 2
        store.reset()
        assert len(store.list_featured()) == 0


# ---------------------------------------------------------------------------
# TestFeaturedEndpoints — integration tests
# ---------------------------------------------------------------------------


class TestFeaturedEndpoints:
    """Integration tests for POST/DELETE/GET feature endpoints."""

    def test_post_feature_returns_200_when_admin(self):
        with TestClient(app) as client:
            token = _register_admin(client)
            listing = _publish_direct()
            resp = client.post(
                f"/api/v1/marketplace/{listing['id']}/feature",
                json={"blurb": "Editor pick"},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["listing_id"] == listing["id"]
            assert data["blurb"] == "Editor pick"

    def test_post_feature_returns_403_when_not_admin(self):
        with TestClient(app) as client:
            token = _register(client)
            listing = _publish_direct()
            resp = client.post(
                f"/api/v1/marketplace/{listing['id']}/feature",
                json={},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 403

    def test_delete_feature_returns_204_when_admin(self):
        with TestClient(app) as client:
            token = _register_admin(client)
            listing = _publish_direct()
            # Feature it first
            client.post(
                f"/api/v1/marketplace/{listing['id']}/feature",
                json={},
                headers={"Authorization": f"Bearer {token}"},
            )
            # Unfeature
            resp = client.delete(
                f"/api/v1/marketplace/{listing['id']}/feature",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 204

    def test_delete_feature_returns_403_when_not_admin(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.delete(
                "/api/v1/marketplace/some-id/feature",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 403

    def test_get_featured_returns_200_no_auth(self):
        with TestClient(app) as client:
            resp = client.get("/api/v1/marketplace/featured")
            assert resp.status_code == 200
            data = resp.json()
            assert "items" in data
            assert "total" in data

    def test_get_featured_returns_items_after_featuring(self):
        """Gate 2: confirm featured items list is non-empty after featuring."""
        with TestClient(app) as client:
            token = _register_admin(client)
            listing = _publish_direct(name="Featured Flow")
            client.post(
                f"/api/v1/marketplace/{listing['id']}/feature",
                json={"blurb": "Top pick"},
                headers={"Authorization": f"Bearer {token}"},
            )
            resp = client.get("/api/v1/marketplace/featured")
            assert resp.status_code == 200
            data = resp.json()
            assert isinstance(data["items"], list)
            assert len(data["items"]) >= 1  # Gate 2: non-empty
            assert data["items"][0]["name"] == "Featured Flow"

    def test_featured_listing_has_blurb_field(self):
        with TestClient(app) as client:
            token = _register_admin(client)
            listing = _publish_direct()
            client.post(
                f"/api/v1/marketplace/{listing['id']}/feature",
                json={"blurb": "Must try"},
                headers={"Authorization": f"Bearer {token}"},
            )
            resp = client.get("/api/v1/marketplace/featured")
            items = resp.json()["items"]
            assert len(items) >= 1
            assert items[0]["blurb"] == "Must try"

    def test_search_results_include_is_featured_flag(self):
        with TestClient(app) as client:
            token = _register_admin(client)
            listing = _publish_direct(name="Searchable Featured")
            # Feature the listing
            client.post(
                f"/api/v1/marketplace/{listing['id']}/feature",
                json={},
                headers={"Authorization": f"Bearer {token}"},
            )
            # Search all listings
            resp = client.get("/api/v1/marketplace/search")
            assert resp.status_code == 200
            items = resp.json()["items"]
            assert isinstance(items, list)
            assert len(items) >= 1
            featured_item = next(
                (i for i in items if i.get("id") == listing["id"]), None
            )
            assert featured_item is not None
            assert featured_item["is_featured"] is True


# ---------------------------------------------------------------------------
# TestFeaturedHero — hero section integration tests
# ---------------------------------------------------------------------------


class TestFeaturedHero:
    """Integration tests for the featured hero display."""

    def test_get_featured_with_limit_3(self):
        """GET /marketplace/featured?limit=3 returns at most 3 items."""
        with TestClient(app) as client:
            token = _register_admin(client)
            # Publish and feature 5 listings
            for i in range(5):
                listing = _publish_direct(name=f"Featured {i}")
                client.post(
                    f"/api/v1/marketplace/{listing['id']}/feature",
                    json={},
                    headers={"Authorization": f"Bearer {token}"},
                )
            resp = client.get("/api/v1/marketplace/featured?limit=3")
            assert resp.status_code == 200
            items = resp.json()["items"]
            assert len(items) == 3

    def test_featured_items_include_listing_metadata(self):
        """Featured items include name and description from listing."""
        with TestClient(app) as client:
            token = _register_admin(client)
            listing = _publish_direct(
                name="Metadata Test", description="Test description"
            )
            client.post(
                f"/api/v1/marketplace/{listing['id']}/feature",
                json={},
                headers={"Authorization": f"Bearer {token}"},
            )
            resp = client.get("/api/v1/marketplace/featured")
            items = resp.json()["items"]
            assert len(items) >= 1
            assert items[0]["name"] == "Metadata Test"
            assert items[0]["description"] == "Test description"
            assert items[0]["is_featured"] is True

    def test_unfeatured_listing_not_in_featured_list(self):
        """After unfeaturing, listing no longer appears in featured list."""
        with TestClient(app) as client:
            token = _register_admin(client)
            listing = _publish_direct()
            client.post(
                f"/api/v1/marketplace/{listing['id']}/feature",
                json={},
                headers={"Authorization": f"Bearer {token}"},
            )
            # Verify it is featured
            resp = client.get("/api/v1/marketplace/featured")
            assert len(resp.json()["items"]) >= 1
            # Unfeature
            client.delete(
                f"/api/v1/marketplace/{listing['id']}/feature",
                headers={"Authorization": f"Bearer {token}"},
            )
            resp = client.get("/api/v1/marketplace/featured")
            assert len(resp.json()["items"]) == 0

    def test_empty_featured_list_returns_empty(self):
        """Empty featured list returns {"items": [], "total": 0}."""
        with TestClient(app) as client:
            resp = client.get("/api/v1/marketplace/featured")
            assert resp.status_code == 200
            data = resp.json()
            assert data["items"] == []
            assert data["total"] == 0
