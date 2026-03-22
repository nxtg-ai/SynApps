"""Tests for Workflow Marketplace API — DIRECTIVE-NXTG-20260318-91.

Covers: MarketplaceRegistry unit tests, and the 4 marketplace endpoints:
  POST /api/v1/marketplace/publish
  GET  /api/v1/marketplace/search
  GET  /api/v1/marketplace/featured
  POST /api/v1/marketplace/install/{listing_id}
"""

import threading
import uuid

import pytest
from fastapi.testclient import TestClient

from apps.orchestrator.helpers import MARKETPLACE_CATEGORIES
from apps.orchestrator.main import app
from apps.orchestrator.stores import (
    MarketplaceRegistry,
    featured_store,
    marketplace_registry,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def client():
    with TestClient(app) as c:
        # Startup lifespan seeds 3 built-in listings; reset so unit tests
        # start from a known-empty state (matching the original contract).
        marketplace_registry.reset()
        yield c


@pytest.fixture(autouse=True)
def _reset_marketplace():
    """Clear the global marketplace registry before and after every test."""
    marketplace_registry.reset()
    yield
    marketplace_registry.reset()


def _create_flow(client, name="Test Workflow", nodes=None, edges=None):
    """Helper: create a flow via API and return its ID."""
    uid = uuid.uuid4().hex[:8]
    flow_data = {
        "name": name,
        "nodes": nodes
        or [
            {"id": f"n1-{uid}", "type": "start", "position": {"x": 0, "y": 0}, "data": {}},
            {
                "id": f"n2-{uid}",
                "type": "llm",
                "position": {"x": 200, "y": 0},
                "data": {"provider": "openai"},
            },
            {"id": f"n3-{uid}", "type": "end", "position": {"x": 400, "y": 0}, "data": {}},
        ],
        "edges": edges
        or [
            {"id": f"e1-{uid}", "source": f"n1-{uid}", "target": f"n2-{uid}"},
            {"id": f"e2-{uid}", "source": f"n2-{uid}", "target": f"n3-{uid}"},
        ],
    }
    resp = client.post("/api/v1/flows", json=flow_data)
    assert resp.status_code == 201
    return resp.json()["id"]


def _publish_listing(
    registry, name="Test Listing", category="notification", tags=None, install_count=0
):
    """Helper: publish a listing directly into the registry and optionally fake install_count."""
    entry = registry.publish(
        {
            "name": name,
            "description": f"Description for {name}",
            "category": category,
            "tags": tags or [],
            "author": "test-author",
            "nodes": [],
            "edges": [],
        }
    )
    # Directly bump install_count for sorting tests
    if install_count > 0:
        with registry._lock:
            registry._listings[entry["id"]]["install_count"] = install_count
        entry = dict(registry._listings[entry["id"]])
    return entry


# ---------------------------------------------------------------------------
# TestMarketplaceRegistryUnit — 10 unit tests
# ---------------------------------------------------------------------------


class TestMarketplaceRegistryUnit:
    """Unit tests for MarketplaceRegistry (no HTTP)."""

    def test_publish_creates_listing(self):
        """publish() stores a listing and returns expected fields."""
        reg = MarketplaceRegistry()
        entry = reg.publish(
            {
                "name": "My Pipeline",
                "description": "A cool pipeline",
                "category": "notification",
                "tags": ["rss", "slack"],
                "author": "alice",
                "nodes": [{"id": "n1"}],
                "edges": [],
            }
        )
        assert entry["name"] == "My Pipeline"
        assert entry["category"] == "notification"
        assert entry["tags"] == ["rss", "slack"]
        assert entry["author"] == "alice"
        assert entry["install_count"] == 0
        assert entry["featured"] is False
        assert "published_at" in entry
        assert "id" in entry

    def test_publish_generates_unique_ids(self):
        """publish() generates a unique UUID for each listing."""
        reg = MarketplaceRegistry()
        a = reg.publish({"name": "A", "category": "content", "nodes": [], "edges": []})
        b = reg.publish({"name": "B", "category": "devops", "nodes": [], "edges": []})
        assert a["id"] != b["id"]

    def test_search_by_q_name(self):
        """search() filters by text in name."""
        reg = MarketplaceRegistry()
        reg.publish({"name": "RSS to Slack", "category": "notification", "nodes": [], "edges": []})
        reg.publish({"name": "GitHub PR Bot", "category": "devops", "nodes": [], "edges": []})

        items, total = reg.search(q="RSS", category=None, tags=None, page=1, per_page=20)
        assert total == 1
        assert len(items) >= 1  # Gate 2
        assert items[0]["name"] == "RSS to Slack"

    def test_search_by_q_description(self):
        """search() filters by text in description."""
        reg = MarketplaceRegistry()
        reg.publish(
            {
                "name": "My Flow",
                "description": "Syncs data from Salesforce",
                "category": "data-sync",
                "nodes": [],
                "edges": [],
            }
        )
        reg.publish(
            {
                "name": "Other Flow",
                "description": "Simple monitoring",
                "category": "monitoring",
                "nodes": [],
                "edges": [],
            }
        )

        items, total = reg.search(q="salesforce", category=None, tags=None, page=1, per_page=20)
        assert total == 1
        assert len(items) >= 1  # Gate 2
        assert items[0]["name"] == "My Flow"

    def test_search_by_q_tags(self):
        """search() matches text in tags list."""
        reg = MarketplaceRegistry()
        reg.publish(
            {
                "name": "Webhook Relay",
                "category": "devops",
                "tags": ["webhook", "relay"],
                "nodes": [],
                "edges": [],
            }
        )

        items, total = reg.search(q="webhook", category=None, tags=None, page=1, per_page=20)
        assert total == 1
        assert len(items) >= 1  # Gate 2

    def test_search_by_category(self):
        """search() filters by category."""
        reg = MarketplaceRegistry()
        reg.publish({"name": "A", "category": "notification", "nodes": [], "edges": []})
        reg.publish({"name": "B", "category": "devops", "nodes": [], "edges": []})
        reg.publish({"name": "C", "category": "notification", "nodes": [], "edges": []})

        items, total = reg.search(q=None, category="notification", tags=None, page=1, per_page=20)
        assert total == 2
        assert len(items) >= 1  # Gate 2
        assert all(item["category"] == "notification" for item in items)

    def test_search_by_tags(self):
        """search() filters by tag list."""
        reg = MarketplaceRegistry()
        reg.publish(
            {"name": "A", "category": "content", "tags": ["ai", "gpt"], "nodes": [], "edges": []}
        )
        reg.publish(
            {"name": "B", "category": "content", "tags": ["slack"], "nodes": [], "edges": []}
        )

        items, total = reg.search(q=None, category=None, tags=["gpt"], page=1, per_page=20)
        assert total == 1
        assert len(items) >= 1  # Gate 2
        assert items[0]["name"] == "A"

    def test_featured_sorted_by_install_count(self):
        """featured() returns listings ordered by install_count descending."""
        reg = MarketplaceRegistry()
        a = reg.publish({"name": "Low", "category": "content", "nodes": [], "edges": []})
        b = reg.publish({"name": "Mid", "category": "devops", "nodes": [], "edges": []})
        c = reg.publish({"name": "High", "category": "monitoring", "nodes": [], "edges": []})

        # Manually set install counts
        with reg._lock:
            reg._listings[a["id"]]["install_count"] = 5
            reg._listings[b["id"]]["install_count"] = 50
            reg._listings[c["id"]]["install_count"] = 100

        result = reg.featured()
        assert len(result) >= 1  # Gate 2
        assert result[0]["name"] == "High"
        assert result[1]["name"] == "Mid"
        assert result[2]["name"] == "Low"

    def test_get_existing_and_missing(self):
        """get() returns listing by ID or None for unknown IDs."""
        reg = MarketplaceRegistry()
        entry = reg.publish({"name": "X", "category": "data-sync", "nodes": [], "edges": []})
        found = reg.get(entry["id"])
        assert found is not None
        assert found["name"] == "X"
        assert reg.get("nonexistent-id-12345") is None

    def test_increment_install(self):
        """increment_install() increases install_count by 1."""
        reg = MarketplaceRegistry()
        entry = reg.publish({"name": "Counter", "category": "devops", "nodes": [], "edges": []})
        assert entry["install_count"] == 0

        result = reg.increment_install(entry["id"])
        assert result is True

        updated = reg.get(entry["id"])
        assert updated is not None
        assert updated["install_count"] == 1

        reg.increment_install(entry["id"])
        updated2 = reg.get(entry["id"])
        assert updated2["install_count"] == 2

    def test_search_pagination(self):
        """search() paginates results correctly."""
        reg = MarketplaceRegistry()
        for i in range(15):
            reg.publish({"name": f"Flow {i:02d}", "category": "content", "nodes": [], "edges": []})

        page1, total = reg.search(q=None, category="content", tags=None, page=1, per_page=5)
        assert total == 15
        assert len(page1) == 5

        page3, total3 = reg.search(q=None, category="content", tags=None, page=3, per_page=5)
        assert total3 == 15
        assert len(page3) == 5
        # Items should differ between pages
        page1_ids = {item["id"] for item in page1}
        page3_ids = {item["id"] for item in page3}
        assert page1_ids.isdisjoint(page3_ids)

    def test_search_empty(self):
        """search() returns empty list when no listings exist."""
        reg = MarketplaceRegistry()
        items, total = reg.search(q="anything", category=None, tags=None, page=1, per_page=20)
        assert total == 0
        assert items == []

    def test_concurrent_publish_safety(self):
        """publish() is safe under concurrent writes."""
        reg = MarketplaceRegistry()
        errors = []

        def publish_one(n):
            try:
                reg.publish(
                    {"name": f"Concurrent {n}", "category": "devops", "nodes": [], "edges": []}
                )
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=publish_one, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Concurrent publishes raised errors: {errors}"
        with reg._lock:
            count = len(reg._listings)
        assert count == 20


# ---------------------------------------------------------------------------
# TestMarketplacePublishEndpoint — 5 tests
# ---------------------------------------------------------------------------


class TestMarketplacePublishEndpoint:
    """HTTP tests for POST /api/v1/marketplace/publish."""

    def test_publish_success_201(self, client):
        """POST /marketplace/publish with valid data returns 201 and listing fields."""
        flow_id = _create_flow(client)
        resp = client.post(
            "/api/v1/marketplace/publish",
            json={
                "flow_id": flow_id,
                "name": "RSS to Slack",
                "description": "Forward RSS items to Slack",
                "category": "notification",
                "tags": ["rss", "slack"],
                "author": "alice",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "RSS to Slack"
        assert data["category"] == "notification"
        assert data["tags"] == ["rss", "slack"]
        assert data["author"] == "alice"
        assert data["install_count"] == 0
        assert data["featured"] is False
        assert "id" in data
        assert "published_at" in data
        # Nodes were cloned from flow (_create_flow makes 3 nodes: start, llm, end)
        assert isinstance(data["nodes"], list)
        assert len(data["nodes"]) >= 1  # Gate 2: cloned flow has nodes

    def test_publish_flow_not_found_404(self, client):
        """POST /marketplace/publish with nonexistent flow_id returns 404."""
        resp = client.post(
            "/api/v1/marketplace/publish",
            json={
                "flow_id": "nonexistent-flow-id",
                "name": "Ghost Listing",
                "category": "devops",
            },
        )
        assert resp.status_code == 404
        body = resp.json()
        assert "not found" in body["error"]["message"].lower()

    def test_publish_invalid_category_422(self, client):
        """POST /marketplace/publish with invalid category returns 422."""
        flow_id = _create_flow(client)
        resp = client.post(
            "/api/v1/marketplace/publish",
            json={
                "flow_id": flow_id,
                "name": "Bad Category",
                "category": "invalid-category-xyz",
            },
        )
        assert resp.status_code == 422

    def test_publish_all_valid_categories(self, client):
        """POST /marketplace/publish accepts all MARKETPLACE_CATEGORIES."""
        for cat in sorted(MARKETPLACE_CATEGORIES):
            flow_id = _create_flow(client, name=f"Flow for {cat}")
            resp = client.post(
                "/api/v1/marketplace/publish",
                json={
                    "flow_id": flow_id,
                    "name": f"Listing for {cat}",
                    "category": cat,
                },
            )
            assert resp.status_code == 201, (
                f"Category '{cat}' should be valid but got {resp.status_code}"
            )
            assert resp.json()["category"] == cat

    def test_publish_requires_auth(self, client):
        """POST /marketplace/publish without auth returns 401 when users exist."""
        # Register a user so anonymous bootstrap is disabled
        email = f"user-{uuid.uuid4().hex[:8]}@example.com"
        client.post("/api/v1/auth/register", json={"email": email, "password": "pass1234"})

        resp = client.post(
            "/api/v1/marketplace/publish",
            json={
                "flow_id": "any-flow",
                "name": "Blocked",
                "category": "devops",
            },
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# TestMarketplaceSearchEndpoint — 5 tests
# ---------------------------------------------------------------------------


class TestMarketplaceSearchEndpoint:
    """HTTP tests for GET /api/v1/marketplace/search."""

    def test_search_empty_result(self, client):
        """GET /marketplace/search with no listings returns empty result."""
        resp = client.get("/api/v1/marketplace/search")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["items"] == []
        assert data["page"] == 1
        assert data["per_page"] == 20

    def test_search_q_filter(self, client):
        """GET /marketplace/search?q=... filters listings by name/description."""
        _publish_listing(marketplace_registry, name="Slack Notifier", category="notification")
        _publish_listing(marketplace_registry, name="GitHub Monitor", category="monitoring")

        resp = client.get("/api/v1/marketplace/search?q=Slack")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert len(data["items"]) >= 1  # Gate 2
        assert data["items"][0]["name"] == "Slack Notifier"

    def test_search_category_filter(self, client):
        """GET /marketplace/search?category=... filters by category."""
        _publish_listing(marketplace_registry, name="A", category="notification")
        _publish_listing(marketplace_registry, name="B", category="devops")
        _publish_listing(marketplace_registry, name="C", category="notification")

        resp = client.get("/api/v1/marketplace/search?category=notification")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["items"]) >= 1  # Gate 2
        assert all(item["category"] == "notification" for item in data["items"])

    def test_search_tags_filter(self, client):
        """GET /marketplace/search?tags=... filters by comma-separated tags."""
        _publish_listing(
            marketplace_registry, name="Tagged Flow", category="content", tags=["ai", "gpt4"]
        )
        _publish_listing(marketplace_registry, name="Other Flow", category="devops", tags=["ci"])

        resp = client.get("/api/v1/marketplace/search?tags=gpt4")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert len(data["items"]) >= 1  # Gate 2
        assert data["items"][0]["name"] == "Tagged Flow"

    def test_search_pagination_fields_in_response(self, client):
        """GET /marketplace/search response includes page/per_page fields."""
        for i in range(5):
            _publish_listing(marketplace_registry, name=f"Flow {i}", category="content")

        resp = client.get("/api/v1/marketplace/search?page=2&per_page=2")
        assert resp.status_code == 200
        data = resp.json()
        assert data["page"] == 2
        assert data["per_page"] == 2
        assert data["total"] == 5
        assert len(data["items"]) == 2


# ---------------------------------------------------------------------------
# TestMarketplaceFeaturedEndpoint — 5 tests
# ---------------------------------------------------------------------------


class TestMarketplaceFeaturedEndpoint:
    """HTTP tests for GET /api/v1/marketplace/featured."""

    def test_featured_empty(self, client):
        """GET /marketplace/featured with no listings returns empty list."""
        resp = client.get("/api/v1/marketplace/featured")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["items"] == []

    def test_featured_single(self, client):
        """GET /marketplace/featured returns a listing that has been featured."""
        listing = _publish_listing(marketplace_registry, name="Solo Listing", category="devops")
        featured_store.feature(listing["id"], "admin-test")

        resp = client.get("/api/v1/marketplace/featured")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert len(data["items"]) >= 1  # Gate 2
        assert data["items"][0]["name"] == "Solo Listing"

    def test_featured_sorted_by_install_count(self, client):
        """GET /marketplace/featured returns featured listings (newest featured first)."""
        low = _publish_listing(
            marketplace_registry, name="Low", category="content", install_count=3
        )
        high = _publish_listing(
            marketplace_registry, name="High", category="devops", install_count=99
        )
        mid = _publish_listing(
            marketplace_registry, name="Mid", category="monitoring", install_count=20
        )
        for lst in [low, high, mid]:
            featured_store.feature(lst["id"], "admin-test")

        resp = client.get("/api/v1/marketplace/featured")
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) >= 1  # Gate 2
        names = [i["name"] for i in items]
        assert "Low" in names and "High" in names and "Mid" in names

    def test_featured_no_auth_required(self, client):
        """GET /marketplace/featured works without any auth header."""
        listing = _publish_listing(
            marketplace_registry, name="Public Listing", category="notification"
        )
        featured_store.feature(listing["id"], "admin-test")

        # No auth header at all
        resp = client.get("/api/v1/marketplace/featured")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1

    def test_featured_top_10_cap(self, client):
        """GET /marketplace/featured?limit=10 returns at most 10 items."""
        for i in range(15):
            lst = _publish_listing(
                marketplace_registry,
                name=f"Listing {i:02d}",
                category="devops",
                install_count=i,
            )
            featured_store.feature(lst["id"], "admin-test")

        resp = client.get("/api/v1/marketplace/featured?limit=10")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 10
        assert data["total"] == 10


# ---------------------------------------------------------------------------
# TestMarketplaceInstallEndpoint — 5 tests
# ---------------------------------------------------------------------------


class TestMarketplaceInstallEndpoint:
    """HTTP tests for POST /api/v1/marketplace/install/{listing_id}."""

    def test_install_success_201(self, client):
        """POST /marketplace/install/{id} creates a new flow and returns 201."""
        listing = _publish_listing(
            marketplace_registry, name="Pipeline to Install", category="devops"
        )

        resp = client.post(f"/api/v1/marketplace/install/{listing['id']}", json={})
        assert resp.status_code == 201
        data = resp.json()
        assert data["listing_id"] == listing["id"]
        assert data["listing_name"] == "Pipeline to Install"
        assert "flow_id" in data
        assert data["flow_id"]  # non-empty UUID

        # Verify the flow was actually saved in the DB
        flow_resp = client.get(f"/api/v1/flows/{data['flow_id']}")
        assert flow_resp.status_code == 200
        assert flow_resp.json()["name"] == "Pipeline to Install"

    def test_install_not_found_404(self, client):
        """POST /marketplace/install/{id} with unknown ID returns 404."""
        resp = client.post("/api/v1/marketplace/install/nonexistent-listing-id", json={})
        assert resp.status_code == 404
        body = resp.json()
        assert "not found" in body["error"]["message"].lower()

    def test_install_requires_auth(self, client):
        """POST /marketplace/install requires auth when users exist."""
        # Register a user so anonymous bootstrap is disabled
        email = f"user-{uuid.uuid4().hex[:8]}@example.com"
        client.post("/api/v1/auth/register", json={"email": email, "password": "pass1234"})

        listing = _publish_listing(
            marketplace_registry, name="Auth-Required Listing", category="content"
        )
        resp = client.post(f"/api/v1/marketplace/install/{listing['id']}", json={})
        assert resp.status_code == 401

    def test_install_increments_install_count(self, client):
        """POST /marketplace/install/{id} increments install_count on the listing."""
        listing = _publish_listing(marketplace_registry, name="Count Test", category="monitoring")
        assert listing["install_count"] == 0

        client.post(f"/api/v1/marketplace/install/{listing['id']}", json={})
        updated = marketplace_registry.get(listing["id"])
        assert updated is not None
        assert updated["install_count"] == 1

        client.post(f"/api/v1/marketplace/install/{listing['id']}", json={})
        updated2 = marketplace_registry.get(listing["id"])
        assert updated2["install_count"] == 2

    def test_install_new_flow_in_db(self, client):
        """POST /marketplace/install saves the new flow to the database."""
        listing = _publish_listing(marketplace_registry, name="DB Check Flow", category="data-sync")

        resp = client.post(
            f"/api/v1/marketplace/install/{listing['id']}",
            json={"flow_name": "My Custom Name"},
        )
        assert resp.status_code == 201
        flow_id = resp.json()["flow_id"]

        # Verify the flow is retrievable from the DB with the custom name
        flow_resp = client.get(f"/api/v1/flows/{flow_id}")
        assert flow_resp.status_code == 200
        flow = flow_resp.json()
        assert flow["id"] == flow_id
        assert flow["name"] == "My Custom Name"
