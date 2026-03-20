"""Tests for the three built-in workflow templates (N-32 addition).

Covers:
- YAML template files exist and contain required fields
- Marketplace is seeded with all three templates at startup
- Search endpoints return the correct templates
- Each listing has non-empty tags, name, and description (CRUCIBLE Gate 2)
- Template install endpoint works for each listing
"""

from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from apps.orchestrator.main import app, marketplace_registry

# ---------------------------------------------------------------------------
# Repo root — used for locating YAML files
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_TEMPLATES_DIR = _REPO_ROOT / "templates"

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def client():
    """TestClient that triggers lifespan events (seeds the marketplace)."""
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _reset_and_reseed_marketplace():
    """Reset registry before each test, then reseed to simulate fresh startup."""
    marketplace_registry.reset()
    # Import the seed function and re-run it so the registry has built-in listings.
    from apps.orchestrator.main import _seed_marketplace_listings

    _seed_marketplace_listings()
    yield
    marketplace_registry.reset()


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _load_yaml(filename: str) -> dict:
    """Load a YAML template file from the templates/ directory."""
    path = _TEMPLATES_DIR / filename
    assert path.exists(), f"Template file not found: {path}"
    with open(path) as f:
        data = yaml.safe_load(f)
    assert isinstance(data, dict), f"Expected dict from {filename}, got {type(data)}"
    return data


def _search(client, q: str) -> list:
    """Run a marketplace search and return items list."""
    resp = client.get(f"/api/v1/marketplace/search?q={q}")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    return data["items"]


# ---------------------------------------------------------------------------
# YAML file existence and required field tests
# ---------------------------------------------------------------------------


class TestYamlTemplateFiles:
    """Gate: each YAML file exists and has required fields."""

    def test_social_media_monitor_yaml_exists(self):
        path = _TEMPLATES_DIR / "social_media_monitor.yaml"
        assert path.exists(), "social_media_monitor.yaml not found in templates/"

    def test_document_processor_yaml_exists(self):
        path = _TEMPLATES_DIR / "document_processor.yaml"
        assert path.exists(), "document_processor.yaml not found in templates/"

    def test_data_pipeline_yaml_exists(self):
        path = _TEMPLATES_DIR / "data_pipeline.yaml"
        assert path.exists(), "data_pipeline.yaml not found in templates/"

    def test_social_media_monitor_required_fields(self):
        data = _load_yaml("social_media_monitor.yaml")
        assert data.get("name"), "name is required"
        assert data.get("description"), "description is required"
        assert data.get("nodes"), "nodes is required"
        assert isinstance(data["nodes"], list)
        assert len(data["nodes"]) >= 1  # Gate 2

    def test_document_processor_required_fields(self):
        data = _load_yaml("document_processor.yaml")
        assert data.get("name"), "name is required"
        assert data.get("description"), "description is required"
        assert data.get("nodes"), "nodes is required"
        assert isinstance(data["nodes"], list)
        assert len(data["nodes"]) >= 1  # Gate 2

    def test_data_pipeline_required_fields(self):
        data = _load_yaml("data_pipeline.yaml")
        assert data.get("name"), "name is required"
        assert data.get("description"), "description is required"
        assert data.get("nodes"), "nodes is required"
        assert isinstance(data["nodes"], list)
        assert len(data["nodes"]) >= 1  # Gate 2

    def test_social_media_monitor_has_tags(self):
        data = _load_yaml("social_media_monitor.yaml")
        tags = data.get("tags", [])
        assert isinstance(tags, list)
        assert len(tags) >= 1  # Gate 2: non-empty tags

    def test_document_processor_has_tags(self):
        data = _load_yaml("document_processor.yaml")
        tags = data.get("tags", [])
        assert isinstance(tags, list)
        assert len(tags) >= 1  # Gate 2: non-empty tags

    def test_data_pipeline_has_tags(self):
        data = _load_yaml("data_pipeline.yaml")
        tags = data.get("tags", [])
        assert isinstance(tags, list)
        assert len(tags) >= 1  # Gate 2: non-empty tags


# ---------------------------------------------------------------------------
# Marketplace seeding tests
# ---------------------------------------------------------------------------


class TestMarketplaceSeeding:
    """The three built-in templates appear in the marketplace after startup."""

    def test_marketplace_seeded_with_three_listings(self):
        with marketplace_registry._lock:
            listings = list(marketplace_registry._listings.values())
        assert isinstance(listings, list)
        assert len(listings) >= 3  # Gate 2: all three are present

    def test_social_media_monitor_seeded(self):
        with marketplace_registry._lock:
            names = [e["name"] for e in marketplace_registry._listings.values()]
        assert "Social Media Monitor" in names

    def test_document_processor_seeded(self):
        with marketplace_registry._lock:
            names = [e["name"] for e in marketplace_registry._listings.values()]
        assert "Document Processor" in names

    def test_data_pipeline_seeded(self):
        with marketplace_registry._lock:
            names = [e["name"] for e in marketplace_registry._listings.values()]
        assert "Data Pipeline" in names

    def test_seed_is_idempotent(self):
        """Calling _seed_marketplace_listings twice must not create duplicates."""
        from apps.orchestrator.main import _seed_marketplace_listings

        _seed_marketplace_listings()  # second call
        with marketplace_registry._lock:
            listings = list(marketplace_registry._listings.values())
        # Still exactly 3 (or however many were seeded originally) — no doubling
        assert len(listings) == 3  # Gate 2


# ---------------------------------------------------------------------------
# Marketplace search endpoint tests
# ---------------------------------------------------------------------------


class TestMarketplaceSearchEndpoints:
    """Search queries return the expected built-in templates."""

    def test_search_social_media_returns_result(self, client):
        items = _search(client, "social+media")
        assert len(items) >= 1  # Gate 2
        names = [i["name"] for i in items]
        assert "Social Media Monitor" in names

    def test_search_document_returns_result(self, client):
        items = _search(client, "document")
        assert len(items) >= 1  # Gate 2
        names = [i["name"] for i in items]
        assert "Document Processor" in names

    def test_search_pipeline_returns_result(self, client):
        items = _search(client, "pipeline")
        assert len(items) >= 1  # Gate 2
        names = [i["name"] for i in items]
        assert "Data Pipeline" in names

    def test_each_listing_has_non_empty_name(self, client):
        # Retrieve all listings via the search endpoint (no filter needed)
        resp = client.get("/api/v1/marketplace/search")
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) >= 3  # Gate 2: all three built-in listings are present
        for item in items:
            assert item.get("name"), "listing name must not be empty"

    def test_each_listing_has_non_empty_description(self, client):
        resp = client.get("/api/v1/marketplace/search")
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) >= 3  # Gate 2
        for item in items:
            assert item.get("description"), "listing description must not be empty"

    def test_each_listing_has_non_empty_tags(self, client):
        resp = client.get("/api/v1/marketplace/search")
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) >= 3  # Gate 2
        for item in items:
            tags = item.get("tags", [])
            assert isinstance(tags, list)
            assert len(tags) >= 1, f"listing '{item['name']}' must have at least one tag"


# ---------------------------------------------------------------------------
# Marketplace install endpoint tests
# ---------------------------------------------------------------------------


class TestMarketplaceInstall:
    """Installing each built-in template via POST /marketplace/install/{id} succeeds."""

    def _get_listing_id(self, name: str) -> str:
        """Look up a listing ID by name from the in-memory registry."""
        with marketplace_registry._lock:
            for listing_id, entry in marketplace_registry._listings.items():
                if entry["name"] == name:
                    return listing_id
        raise AssertionError(f"Listing '{name}' not found in registry")

    def _auth_headers(self, client) -> dict:
        """Register + login and return Bearer headers for authenticated requests."""
        uid = __import__("uuid").uuid4().hex[:8]
        email = f"tpl_user_{uid}@test.com"
        client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "Password1!"},
        )
        resp = client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "Password1!"},
        )
        token = resp.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    def test_install_social_media_monitor(self, client):
        listing_id = self._get_listing_id("Social Media Monitor")
        headers = self._auth_headers(client)
        resp = client.post(
            f"/api/v1/marketplace/install/{listing_id}",
            json={},
            headers=headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data.get("flow_id"), "install must return a flow_id"

    def test_install_document_processor(self, client):
        listing_id = self._get_listing_id("Document Processor")
        headers = self._auth_headers(client)
        resp = client.post(
            f"/api/v1/marketplace/install/{listing_id}",
            json={},
            headers=headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data.get("flow_id"), "install must return a flow_id"

    def test_install_data_pipeline(self, client):
        listing_id = self._get_listing_id("Data Pipeline")
        headers = self._auth_headers(client)
        resp = client.post(
            f"/api/v1/marketplace/install/{listing_id}",
            json={},
            headers=headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data.get("flow_id"), "install must return a flow_id"
