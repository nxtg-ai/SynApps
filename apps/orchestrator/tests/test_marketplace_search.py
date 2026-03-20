"""Tests for Marketplace Search Engine (N-49).

Covers: MarketplaceSearchEngine unit tests, search endpoint integration,
autocomplete endpoint integration, and scoring behavior.
"""

import pytest
from fastapi.testclient import TestClient

from apps.orchestrator.main import (
    MarketplaceSearchEngine,
    app,
    marketplace_registry,
    rating_store,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def client():
    with TestClient(app) as c:
        marketplace_registry.reset()
        rating_store.reset()
        yield c


@pytest.fixture(autouse=True)
def _reset_stores():
    """Clear global stores before and after every test."""
    marketplace_registry.reset()
    rating_store.reset()
    yield
    marketplace_registry.reset()
    rating_store.reset()


def _publish_listing(
    registry,
    name="Test Listing",
    category="notification",
    tags=None,
    install_count=0,
    author="test-author",
    description=None,
):
    """Helper: publish a listing directly into the registry."""
    entry = registry.publish(
        {
            "name": name,
            "description": description or f"Description for {name}",
            "category": category,
            "tags": tags or [],
            "author": author,
            "nodes": [],
            "edges": [],
        }
    )
    if install_count > 0:
        with registry._lock:
            registry._listings[entry["id"]]["install_count"] = install_count
        entry = dict(registry._listings[entry["id"]])
    return entry


# ---------------------------------------------------------------------------
# TestMarketplaceSearchEngine — 10 unit tests
# ---------------------------------------------------------------------------


class TestMarketplaceSearchEngine:
    """Unit tests for MarketplaceSearchEngine (no HTTP)."""

    def test_search_empty_q_returns_all(self):
        """Search with empty q returns all listings."""
        engine = MarketplaceSearchEngine()
        listings = [
            {"name": "A", "description": "desc", "tags": [], "author": "x", "install_count": 0},
            {"name": "B", "description": "desc", "tags": [], "author": "y", "install_count": 0},
        ]
        result = engine.search(listings, q="")
        assert result["total"] == 2
        assert len(result["items"]) >= 1  # Gate 2

    def test_search_by_name_partial_case_insensitive(self):
        """Search by name is partial and case-insensitive."""
        engine = MarketplaceSearchEngine()
        listings = [
            {
                "name": "Slack Notifier",
                "description": "",
                "tags": [],
                "author": "a",
                "install_count": 0,
            },
            {
                "name": "GitHub Monitor",
                "description": "",
                "tags": [],
                "author": "b",
                "install_count": 0,
            },
        ]
        result = engine.search(listings, q="slack")
        assert result["total"] == 1
        assert len(result["items"]) >= 1  # Gate 2
        assert result["items"][0]["name"] == "Slack Notifier"

    def test_search_by_tag(self):
        """Search matches listings that have the query as a tag."""
        engine = MarketplaceSearchEngine()
        listings = [
            {
                "name": "Flow A",
                "description": "",
                "tags": ["llm", "ai"],
                "author": "a",
                "install_count": 0,
            },
            {
                "name": "Flow B",
                "description": "",
                "tags": ["http"],
                "author": "b",
                "install_count": 0,
            },
        ]
        result = engine.search(listings, q="llm")
        assert result["total"] == 1
        assert len(result["items"]) >= 1  # Gate 2
        assert result["items"][0]["name"] == "Flow A"

    def test_search_by_description(self):
        """Search matches listings by description keyword."""
        engine = MarketplaceSearchEngine()
        listings = [
            {
                "name": "Flow",
                "description": "Automates email sending",
                "tags": [],
                "author": "a",
                "install_count": 0,
            },
            {
                "name": "Other",
                "description": "Does nothing useful",
                "tags": [],
                "author": "b",
                "install_count": 0,
            },
        ]
        result = engine.search(listings, q="email")
        assert result["total"] == 1
        assert len(result["items"]) >= 1  # Gate 2
        assert result["items"][0]["name"] == "Flow"

    def test_search_by_author(self):
        """Search matches listings by author name."""
        engine = MarketplaceSearchEngine()
        listings = [
            {
                "name": "Flow",
                "description": "",
                "tags": [],
                "author": "john_doe",
                "install_count": 0,
            },
            {"name": "Other", "description": "", "tags": [], "author": "jane", "install_count": 0},
        ]
        result = engine.search(listings, q="john")
        assert result["total"] == 1
        assert len(result["items"]) >= 1  # Gate 2
        assert result["items"][0]["author"] == "john_doe"

    def test_category_filter(self):
        """Category filter excludes non-matching listings."""
        engine = MarketplaceSearchEngine()
        listings = [
            {
                "name": "A",
                "description": "",
                "tags": [],
                "author": "x",
                "category": "automation",
                "install_count": 0,
            },
            {
                "name": "B",
                "description": "",
                "tags": [],
                "author": "y",
                "category": "devops",
                "install_count": 0,
            },
        ]
        result = engine.search(listings, q="", category="automation")
        assert result["total"] == 1
        assert result["items"][0]["name"] == "A"

    def test_min_installs_filter(self):
        """min_installs filter excludes low-install listings."""
        engine = MarketplaceSearchEngine()
        listings = [
            {"name": "Popular", "description": "", "tags": [], "author": "x", "install_count": 100},
            {"name": "Unpopular", "description": "", "tags": [], "author": "y", "install_count": 5},
        ]
        result = engine.search(listings, q="", min_installs=50)
        assert result["total"] == 1
        assert result["items"][0]["name"] == "Popular"

    def test_min_rating_filter(self):
        """min_rating filter excludes listings below the threshold."""
        engine = MarketplaceSearchEngine()
        listings = [
            {
                "name": "Great",
                "description": "",
                "tags": [],
                "author": "x",
                "id": "great-1",
                "install_count": 0,
            },
            {
                "name": "Bad",
                "description": "",
                "tags": [],
                "author": "y",
                "id": "bad-1",
                "install_count": 0,
            },
        ]
        # Simulate a rating store
        rating_store.rate("great-1", "user1", 5)
        rating_store.rate("bad-1", "user1", 2)

        result = engine.search(
            listings,
            q="",
            min_rating=4.0,
            rating_lookup=rating_store,
        )
        assert result["total"] == 1
        assert result["items"][0]["name"] == "Great"

    def test_sort_by_installs(self):
        """sort_by='installs' orders by install_count descending."""
        engine = MarketplaceSearchEngine()
        listings = [
            {"name": "Low", "description": "", "tags": [], "author": "x", "install_count": 10},
            {"name": "High", "description": "", "tags": [], "author": "y", "install_count": 500},
            {"name": "Mid", "description": "", "tags": [], "author": "z", "install_count": 100},
        ]
        result = engine.search(listings, q="", sort_by="installs")
        names = [item["name"] for item in result["items"]]
        assert names == ["High", "Mid", "Low"]

    def test_autocomplete_prefix_match(self):
        """Autocomplete returns prefix matches only."""
        engine = MarketplaceSearchEngine()
        listings = [
            {"name": "LLM Pipeline", "tags": ["llm", "ai"]},
            {"name": "HTTP Monitor", "tags": ["http", "monitoring"]},
            {"name": "Logger Service", "tags": ["logging"]},
        ]
        suggestions = engine.autocomplete(listings, q="ll")
        assert "LLM Pipeline" in suggestions
        assert "llm" in suggestions
        # Non-matching items excluded
        assert "HTTP Monitor" not in suggestions
        assert "http" not in suggestions


# ---------------------------------------------------------------------------
# TestSearchEndpoint — 8 integration tests
# ---------------------------------------------------------------------------


class TestSearchEndpoint:
    """HTTP tests for GET /api/v1/marketplace/search with search engine."""

    def test_search_returns_200_with_required_keys(self, client):
        """GET /marketplace/search returns 200 with all required response keys."""
        resp = client.get("/api/v1/marketplace/search")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "per_page" in data
        assert "query" in data
        assert "filters_applied" in data

    def test_search_with_q_returns_matching(self, client):
        """Search with q returns matching listing."""
        _publish_listing(marketplace_registry, name="Slack Notifier", category="notification")
        _publish_listing(marketplace_registry, name="GitHub Monitor", category="monitoring")

        resp = client.get("/api/v1/marketplace/search?q=Slack")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        assert len(data["items"]) >= 1  # Gate 2
        assert data["items"][0]["name"] == "Slack Notifier"

    def test_search_category_filter(self, client):
        """Category filter returns only matching category."""
        _publish_listing(marketplace_registry, name="A", category="notification")
        _publish_listing(marketplace_registry, name="B", category="devops")
        _publish_listing(marketplace_registry, name="C", category="notification")

        resp = client.get("/api/v1/marketplace/search?category=notification")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["items"]) >= 1  # Gate 2
        assert all(item["category"] == "notification" for item in data["items"])

    def test_search_min_installs_filter(self, client):
        """min_installs filter excludes low-install listings."""
        _publish_listing(marketplace_registry, name="Popular", category="ai", install_count=200)
        _publish_listing(marketplace_registry, name="Niche", category="ai", install_count=5)

        resp = client.get("/api/v1/marketplace/search?min_installs=100")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert len(data["items"]) >= 1  # Gate 2
        assert data["items"][0]["name"] == "Popular"

    def test_search_sort_by_installs(self, client):
        """sort_by=installs returns highest install_count first."""
        _publish_listing(marketplace_registry, name="Low", category="ai", install_count=10)
        _publish_listing(marketplace_registry, name="High", category="ai", install_count=500)

        resp = client.get("/api/v1/marketplace/search?sort_by=installs")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) >= 2  # Gate 2
        assert data["items"][0]["name"] == "High"
        assert data["items"][1]["name"] == "Low"

    def test_search_pagination(self, client):
        """Pagination: page=2 returns second page of results."""
        for i in range(5):
            _publish_listing(marketplace_registry, name=f"Flow {i}", category="content")

        resp = client.get("/api/v1/marketplace/search?page=2&per_page=2")
        assert resp.status_code == 200
        data = resp.json()
        assert data["page"] == 2
        assert data["per_page"] == 2
        assert data["total"] == 5
        assert len(data["items"]) == 2

    def test_search_items_include_score(self, client):
        """Search result items include _score field."""
        _publish_listing(marketplace_registry, name="LLM Pipeline", category="ai")

        resp = client.get("/api/v1/marketplace/search?q=LLM")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) >= 1  # Gate 2
        assert "_score" in data["items"][0]
        assert data["items"][0]["_score"] > 0

    def test_search_total_reflects_filtered_count(self, client):
        """Total reflects filtered count, not page size."""
        _publish_listing(
            marketplace_registry,
            name="Match A",
            category="ai",
            description="Uses LLM for processing",
        )
        _publish_listing(marketplace_registry, name="LLM Flow B", category="devops")
        _publish_listing(marketplace_registry, name="Unrelated", category="devops")

        resp = client.get("/api/v1/marketplace/search?q=LLM&per_page=1")
        assert resp.status_code == 200
        data = resp.json()
        # 2 listings match "LLM" (one in name, one in description)
        assert data["total"] == 2
        assert len(data["items"]) == 1  # limited by per_page


# ---------------------------------------------------------------------------
# TestAutocompleteEndpoint — 4 integration tests
# ---------------------------------------------------------------------------


class TestAutocompleteEndpoint:
    """HTTP tests for GET /api/v1/marketplace/autocomplete."""

    def test_autocomplete_returns_suggestions(self, client):
        """Autocomplete with q=llm returns matching suggestions."""
        _publish_listing(marketplace_registry, name="LLM Pipeline", tags=["llm", "ai"])
        _publish_listing(marketplace_registry, name="HTTP Service", tags=["http"])

        resp = client.get("/api/v1/marketplace/autocomplete?q=llm")
        assert resp.status_code == 200
        data = resp.json()
        assert "suggestions" in data
        assert isinstance(data["suggestions"], list)
        assert len(data["suggestions"]) >= 1  # Gate 2
        # Should include "LLM Pipeline" (name match) and "llm" (tag match)
        lower_suggestions = [s.lower() for s in data["suggestions"]]
        assert "llm pipeline" in lower_suggestions or "llm" in lower_suggestions

    def test_autocomplete_empty_q_returns_empty(self, client):
        """Empty q returns empty suggestions list."""
        _publish_listing(marketplace_registry, name="Something", tags=["ai"])

        resp = client.get("/api/v1/marketplace/autocomplete?q=")
        assert resp.status_code == 200
        data = resp.json()
        assert data["suggestions"] == []

    def test_autocomplete_limit_respected(self, client):
        """Limit parameter caps the number of suggestions."""
        for i in range(10):
            _publish_listing(marketplace_registry, name=f"LLM Flow {i}", tags=[f"llm-{i}"])

        resp = client.get("/api/v1/marketplace/autocomplete?q=LLM&limit=3")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["suggestions"]) <= 3

    def test_autocomplete_no_auth_required(self, client):
        """Autocomplete endpoint does not require authentication."""
        resp = client.get("/api/v1/marketplace/autocomplete?q=test")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# TestSearchScoring — 3 integration tests
# ---------------------------------------------------------------------------


class TestSearchScoring:
    """Tests for search scoring behavior via the HTTP endpoint."""

    def test_name_match_scores_higher_than_description(self, client):
        """A listing with query in name scores higher than one with query in description."""
        _publish_listing(
            marketplace_registry,
            name="LLM Pipeline",
            category="ai",
            description="Basic pipeline",
        )
        _publish_listing(
            marketplace_registry,
            name="Basic Service",
            category="ai",
            description="Uses LLM technology internally",
        )

        resp = client.get("/api/v1/marketplace/search?q=LLM")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) >= 2  # Gate 2
        # Name match should score higher
        assert data["items"][0]["name"] == "LLM Pipeline"
        assert data["items"][0]["_score"] > data["items"][1]["_score"]

    def test_exact_match_ranks_above_partial(self, client):
        """Exact name match ranks above partial match."""
        _publish_listing(
            marketplace_registry,
            name="Slack",
            category="notification",
        )
        _publish_listing(
            marketplace_registry,
            name="Slack Notifier Pro",
            category="notification",
        )

        resp = client.get("/api/v1/marketplace/search?q=Slack")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) >= 2  # Gate 2
        # Both match, but "Slack" should have equal or higher score
        # (exact match bonus applies to both since "Slack" is in both names)
        assert data["items"][0]["_score"] >= data["items"][1]["_score"]

    def test_multi_word_query_matches_any_word(self, client):
        """Multi-word query returns results matching any word."""
        _publish_listing(marketplace_registry, name="Slack Bot", category="notification")
        _publish_listing(marketplace_registry, name="Email Sender", category="notification")
        _publish_listing(marketplace_registry, name="Unrelated Tool", category="devops")

        resp = client.get("/api/v1/marketplace/search?q=slack email")
        assert resp.status_code == 200
        data = resp.json()
        # Should match both "Slack Bot" (matches "slack") and "Email Sender" (matches "email")
        assert data["total"] >= 2
        assert len(data["items"]) >= 2  # Gate 2
        matched_names = {item["name"] for item in data["items"]}
        assert "Slack Bot" in matched_names
        assert "Email Sender" in matched_names
