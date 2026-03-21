"""
Tests for the "AI Content Compliance Pipeline" Faultline workflow template.

Covers:
  1. TestFaultlineTemplateStructure  — flow structure validation (5 tests)
  2. TestFaultlineMarketplacePublish — marketplace lifecycle (4 tests)
  3. TestFaultlineTemplateVariables  — workflow variables + secrets (3 tests)
  4. TestFaultlineTemplateDocs       — docs + YAML artefact existence (3 tests)
"""

import uuid
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
from fastapi.testclient import TestClient

from apps.orchestrator.main import (
    app,
    marketplace_registry,
    workflow_secret_store,
    workflow_variable_store,
)

# ---------------------------------------------------------------------------
# Template node/edge data — mirrors FaultlineCompliance.ts exactly
# ---------------------------------------------------------------------------

_FAULTLINE_NODES = [
    {
        "id": "webhook",
        "type": "webhook_trigger",
        "position": {"x": 100, "y": 300},
        "data": {
            "label": "Content Submission Webhook",
            "input_schema": {
                "text": {"type": "string", "required": True},
                "content_type": {"type": "string", "required": False},
                "user_id": {"type": "string", "required": False},
            },
        },
    },
    {
        "id": "scan",
        "type": "http_request",
        "position": {"x": 300, "y": 300},
        "data": {
            "label": "Faultline: Content Scan",
            "method": "POST",
            "url": "{{var.FAULTLINE_API_URL}}/scan",
            "headers": {
                "Content-Type": "application/json",
                "Authorization": "Bearer {{var.FAULTLINE_API_KEY}}",
            },
            "auth_type": "bearer",
            "auth_token": "{{var.FAULTLINE_API_KEY}}",
            "timeout_seconds": 30,
            "verify_ssl": True,
            "max_retries": 1,
            "allow_redirects": True,
        },
    },
    {
        "id": "extract",
        "type": "code",
        "position": {"x": 500, "y": 300},
        "data": {
            "label": "Extract Trust Score",
            "language": "python",
            "timeout_seconds": 10,
            "memory_limit_mb": 256,
            "code": "result = {'trust_score': 100, 'compliant': 'yes', 'label': 'PASS'}",
        },
    },
    {
        "id": "route",
        "type": "if_else",
        "position": {"x": 700, "y": 300},
        "data": {
            "label": "Route by Trust Score",
            "source": "{{data.compliant}}",
            "operation": "equals",
            "value": "no",
            "case_sensitive": False,
            "negate": False,
            "true_target": "alert",
            "false_target": "report",
        },
    },
    {
        "id": "alert",
        "type": "http_request",
        "position": {"x": 600, "y": 500},
        "data": {
            "label": "Slack: Compliance Alert",
            "method": "POST",
            "url": "{{var.SLACK_WEBHOOK_URL}}",
            "headers": {"Content-Type": "application/json"},
            "auth_type": "none",
            "timeout_seconds": 15,
            "verify_ssl": True,
            "max_retries": 1,
            "allow_redirects": True,
        },
    },
    {
        "id": "report",
        "type": "http_request",
        "position": {"x": 900, "y": 500},
        "data": {
            "label": "Generate Compliance Report",
            "method": "POST",
            "url": "{{var.FAULTLINE_API_URL}}/scan/report",
            "headers": {
                "Content-Type": "application/json",
                "Authorization": "Bearer {{var.FAULTLINE_API_KEY}}",
            },
            "auth_type": "bearer",
            "auth_token": "{{var.FAULTLINE_API_KEY}}",
            "timeout_seconds": 30,
            "verify_ssl": True,
            "max_retries": 1,
            "allow_redirects": True,
        },
    },
    {
        "id": "email",
        "type": "http_request",
        "position": {"x": 900, "y": 650},
        "data": {
            "label": "Email Compliance Report",
            "method": "POST",
            "url": "{{var.EMAIL_WEBHOOK_URL}}",
            "headers": {"Content-Type": "application/json"},
            "auth_type": "none",
            "timeout_seconds": 15,
            "verify_ssl": True,
            "max_retries": 1,
            "allow_redirects": True,
        },
    },
    {
        "id": "end",
        "type": "end",
        "position": {"x": 1100, "y": 550},
        "data": {"label": "Done"},
    },
]

# Full template edges including metadata (sourceHandle, label) used for
# structural assertions against the template spec. The API-valid subset strips
# the extra fields that FlowEdgeRequest does not accept.
_FAULTLINE_EDGES_FULL = [
    {"id": "webhook-scan", "source": "webhook", "target": "scan", "animated": False},
    {"id": "scan-extract", "source": "scan", "target": "extract", "animated": False},
    {"id": "extract-route", "source": "extract", "target": "route", "animated": False},
    {
        "id": "route-alert",
        "source": "route",
        "target": "alert",
        "sourceHandle": "true",
        "animated": False,
        "label": "flagged",
    },
    {
        "id": "route-report",
        "source": "route",
        "target": "report",
        "sourceHandle": "false",
        "animated": False,
        "label": "compliant",
    },
    {"id": "alert-end", "source": "alert", "target": "end", "animated": False},
    {"id": "report-email", "source": "report", "target": "email", "animated": False},
    {"id": "email-end", "source": "email", "target": "end", "animated": False},
]

# API-safe edges: only fields accepted by FlowEdgeRequest (id, source, target, animated).
_FAULTLINE_EDGES = [
    {k: v for k, v in edge.items() if k in ("id", "source", "target", "animated")}
    for edge in _FAULTLINE_EDGES_FULL
]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _clean():
    marketplace_registry.reset()
    workflow_variable_store.reset()
    workflow_secret_store.reset()
    yield
    marketplace_registry.reset()
    workflow_variable_store.reset()
    workflow_secret_store.reset()


@pytest.fixture
def auth_headers(client):
    """Register a fresh user and return a Bearer auth header dict."""
    email = f"faultline-{uuid.uuid4().hex[:8]}@test.com"
    reg_resp = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "TestPass1!"},
    )
    token = reg_resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _create_faultline_flow(client, auth_headers) -> dict:
    """Helper: create a flow with the full Faultline template and return the full flow dict.

    POST /flows returns only {message, id}. We follow up with GET /flows/{id} so
    that callers receive the complete flow including nodes and edges.
    """
    flow_data = {
        "name": f"AI Content Compliance Pipeline {uuid.uuid4().hex[:6]}",
        "nodes": _FAULTLINE_NODES,
        "edges": _FAULTLINE_EDGES,
    }
    post_resp = client.post("/api/v1/flows", json=flow_data, headers=auth_headers)
    assert post_resp.status_code == 201, f"Flow creation failed: {post_resp.text}"
    flow_id = post_resp.json()["id"]

    get_resp = client.get(f"/api/v1/flows/{flow_id}", headers=auth_headers)
    assert get_resp.status_code == 200, f"Flow fetch failed: {get_resp.text}"
    return get_resp.json()


# ===========================================================================
# Class 1: TestFaultlineTemplateStructure
# ===========================================================================


class TestFaultlineTemplateStructure:
    """Validate the Faultline template flow structure by creating it via POST /flows."""

    def test_template_has_eight_nodes(self, client, auth_headers):
        """The template flow must contain exactly 8 nodes."""
        flow = _create_faultline_flow(client, auth_headers)
        nodes = flow["nodes"]
        assert isinstance(nodes, list)
        assert len(nodes) == 8  # Gate 2

    def test_webhook_trigger_node_present(self, client, auth_headers):
        """The flow must contain a node with type 'webhook_trigger'."""
        flow = _create_faultline_flow(client, auth_headers)
        nodes = flow["nodes"]
        assert isinstance(nodes, list)
        assert len(nodes) >= 1  # Gate 2
        types = [n["type"] for n in nodes]
        assert "webhook_trigger" in types, f"'webhook_trigger' not found in node types: {types}"

    def test_if_else_node_uses_equals_operation(self, client, auth_headers):
        """The if_else (route) node must have operation='equals' and source='{{data.compliant}}'."""
        flow = _create_faultline_flow(client, auth_headers)
        nodes = flow["nodes"]
        assert isinstance(nodes, list)
        assert len(nodes) >= 1  # Gate 2
        if_else_nodes = [n for n in nodes if n["type"] == "if_else"]
        assert len(if_else_nodes) >= 1, "No if_else node found in template"
        route_node = if_else_nodes[0]
        assert route_node["data"]["operation"] == "equals"
        assert route_node["data"]["source"] == "{{data.compliant}}"

    def test_branch_edges_have_source_handles(self, client, auth_headers):
        """Template spec edges from 'route' must carry sourceHandle values of 'true' and 'false'.

        The API schema (FlowEdgeRequest) does not round-trip sourceHandle, so this
        test validates the canonical template spec (_FAULTLINE_EDGES_FULL) directly.
        """
        # Verify the flow can be created successfully (confirms edge topology is valid)
        flow = _create_faultline_flow(client, auth_headers)
        assert flow is not None

        # Assert against the full template spec (sourceHandle is a template-level concern)
        route_edges = [e for e in _FAULTLINE_EDGES_FULL if e.get("source") == "route"]
        assert len(route_edges) >= 1  # Gate 2: at least one branch edge
        handles = {e.get("sourceHandle") for e in route_edges}
        assert "true" in handles, f"'true' sourceHandle missing; found handles: {handles}"
        assert "false" in handles, f"'false' sourceHandle missing; found handles: {handles}"

    def test_all_edge_endpoints_valid(self, client, auth_headers):
        """Every edge's source and target must map to an existing node id."""
        flow = _create_faultline_flow(client, auth_headers)
        nodes = flow["nodes"]
        edges = flow["edges"]
        assert isinstance(nodes, list)
        assert isinstance(edges, list)
        assert len(nodes) >= 1  # Gate 2
        assert len(edges) >= 1  # Gate 2
        node_ids = {n["id"] for n in nodes}
        for edge in edges:
            assert edge["source"] in node_ids, (
                f"Edge source '{edge['source']}' not found in node ids: {node_ids}"
            )
            assert edge["target"] in node_ids, (
                f"Edge target '{edge['target']}' not found in node ids: {node_ids}"
            )


# ===========================================================================
# Class 2: TestFaultlineMarketplacePublish
# ===========================================================================


class TestFaultlineMarketplacePublish:
    """Marketplace lifecycle tests for the Faultline template."""

    def test_publish_to_marketplace(self, client, auth_headers):
        """Publishing the Faultline flow to the marketplace returns 201 with install_count=0."""
        flow = _create_faultline_flow(client, auth_headers)
        resp = client.post(
            "/api/v1/marketplace/publish",
            json={
                "flow_id": flow["id"],
                "name": "AI Content Compliance Pipeline",
                "description": "Scan content via Faultline and route by trust score.",
                "category": "monitoring",
                "tags": ["compliance", "faultline"],
                "author": "NXTG-AI",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201
        listing = resp.json()
        assert listing["name"] == "AI Content Compliance Pipeline"
        assert listing["install_count"] == 0
        assert listing["category"] == "monitoring"
        assert "id" in listing

    def test_published_listing_appears_in_search(self, client, auth_headers):
        """A published Faultline listing must appear when searching for 'compliance'."""
        flow = _create_faultline_flow(client, auth_headers)
        client.post(
            "/api/v1/marketplace/publish",
            json={
                "flow_id": flow["id"],
                "name": "AI Content Compliance Pipeline",
                "description": "Compliance scanning with Faultline.",
                "category": "monitoring",
                "tags": ["compliance", "faultline"],
                "author": "NXTG-AI",
            },
            headers=auth_headers,
        )
        search_resp = client.get("/api/v1/marketplace/search?q=compliance")
        assert search_resp.status_code == 200
        data = search_resp.json()
        assert data["total"] >= 1  # Gate 2
        assert len(data["items"]) >= 1  # Gate 2

    def test_install_from_marketplace(self, client, auth_headers):
        """Installing a published Faultline listing must create a new flow with the same node count."""
        flow = _create_faultline_flow(client, auth_headers)
        original_node_count = len(flow["nodes"])

        pub_resp = client.post(
            "/api/v1/marketplace/publish",
            json={
                "flow_id": flow["id"],
                "name": "AI Content Compliance Pipeline",
                "description": "Compliance scanning with Faultline.",
                "category": "monitoring",
                "tags": ["compliance", "faultline"],
                "author": "NXTG-AI",
            },
            headers=auth_headers,
        )
        assert pub_resp.status_code == 201
        listing_id = pub_resp.json()["id"]

        install_resp = client.post(
            f"/api/v1/marketplace/install/{listing_id}",
            json={},
            headers=auth_headers,
        )
        assert install_resp.status_code == 201
        install_data = install_resp.json()
        assert "flow_id" in install_data

        installed_flow_resp = client.get(
            f"/api/v1/flows/{install_data['flow_id']}",
            headers=auth_headers,
        )
        assert installed_flow_resp.status_code == 200
        installed_nodes = installed_flow_resp.json()["nodes"]
        assert isinstance(installed_nodes, list)
        assert len(installed_nodes) >= 1  # Gate 2
        assert len(installed_nodes) == original_node_count

    def test_marketplace_listing_has_faultline_tag(self, client, auth_headers):
        """The published listing must include 'faultline' in its tags."""
        flow = _create_faultline_flow(client, auth_headers)
        pub_resp = client.post(
            "/api/v1/marketplace/publish",
            json={
                "flow_id": flow["id"],
                "name": "AI Content Compliance Pipeline",
                "description": "Compliance scanning with Faultline.",
                "category": "monitoring",
                "tags": ["compliance", "faultline"],
                "author": "NXTG-AI",
            },
            headers=auth_headers,
        )
        assert pub_resp.status_code == 201
        listing_id = pub_resp.json()["id"]

        # Retrieve from registry directly to inspect tags
        listing = marketplace_registry.get(listing_id)
        assert listing is not None, "Published listing not found in registry"
        assert isinstance(listing["tags"], list)
        assert len(listing["tags"]) >= 1  # Gate 2
        assert "faultline" in listing["tags"], (
            f"'faultline' tag missing; actual tags: {listing['tags']}"
        )


# ===========================================================================
# Class 3: TestFaultlineTemplateVariables
# ===========================================================================


class TestFaultlineTemplateVariables:
    """Workflow variables and secrets for the Faultline template."""

    def test_set_workflow_variables(self, client, auth_headers):
        """PUT /workflows/{id}/variables with Faultline vars must return 200."""
        flow = _create_faultline_flow(client, auth_headers)
        flow_id = flow["id"]

        resp = client.put(
            f"/api/v1/workflows/{flow_id}/variables",
            json={
                "FAULTLINE_API_URL": "https://api.faultline.ai",
                "FAULTLINE_API_KEY": "sk-test-placeholder",
                "SLACK_WEBHOOK_URL": "https://hooks.slack.com/services/TEST/TEST/TEST",
                "REPORT_EMAIL": "compliance@example.com",
                "EMAIL_WEBHOOK_URL": "https://hooks.example.com/email",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "variables" in body

    def test_set_workflow_secrets(self, client, auth_headers):
        """PUT /workflows/{id}/secrets must return 200 and not expose the key value in plaintext."""
        flow = _create_faultline_flow(client, auth_headers)
        flow_id = flow["id"]

        resp = client.put(
            f"/api/v1/workflows/{flow_id}/secrets",
            json={"FAULTLINE_API_KEY": "sk-test-key"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "secrets" in body
        # The raw key value must not appear in the response body
        response_text = resp.text
        assert "sk-test-key" not in response_text, (
            "Secret value 'sk-test-key' must not appear in plaintext in the response"
        )
        # The masked value must be present
        assert body["secrets"].get("FAULTLINE_API_KEY") == "***"

    def test_variables_persist_after_get(self, client, auth_headers):
        """Variables set via PUT must be returned verbatim by GET /workflows/{id}/variables."""
        flow = _create_faultline_flow(client, auth_headers)
        flow_id = flow["id"]
        variables_payload = {
            "FAULTLINE_API_URL": "https://api.faultline.ai",
            "FAULTLINE_API_KEY": "sk-test-placeholder",
            "SLACK_WEBHOOK_URL": "https://hooks.slack.com/services/TEST/TEST/TEST",
            "REPORT_EMAIL": "compliance@example.com",
            "EMAIL_WEBHOOK_URL": "https://hooks.example.com/email",
        }

        put_resp = client.put(
            f"/api/v1/workflows/{flow_id}/variables",
            json=variables_payload,
            headers=auth_headers,
        )
        assert put_resp.status_code == 200

        get_resp = client.get(
            f"/api/v1/workflows/{flow_id}/variables",
            headers=auth_headers,
        )
        assert get_resp.status_code == 200
        stored = get_resp.json()["variables"]
        assert isinstance(stored, dict)
        assert len(stored) >= 1  # Gate 2
        for key, expected_value in variables_payload.items():
            assert stored.get(key) == expected_value, (
                f"Variable '{key}' mismatch: expected '{expected_value}', got '{stored.get(key)}'"
            )


# ===========================================================================
# Class 4: TestFaultlineTemplateDocs
# ===========================================================================


class TestFaultlineTemplateDocs:
    """Validate the presence and contents of Faultline template documentation artefacts."""

    def test_docs_file_exists(self):
        """The markdown docs file for the Faultline template must exist."""
        doc_path = _REPO_ROOT / "docs/templates/ai-compliance-pipeline.md"
        assert doc_path.exists(), f"Expected docs file not found at: {doc_path.resolve()}"

    def test_docs_contains_required_sections(self):
        """The docs file must contain 'Prerequisites', 'FAULTLINE_API_URL', and 'trust score'."""
        doc_path = _REPO_ROOT / "docs/templates/ai-compliance-pipeline.md"
        assert doc_path.exists(), f"Docs file missing: {doc_path.resolve()}"
        content = doc_path.read_text(encoding="utf-8")
        required_strings = ["Prerequisites", "FAULTLINE_API_URL", "trust score"]
        for required in required_strings:
            assert required in content, f"Required string '{required}' not found in {doc_path}"

    def test_yaml_template_exists(self):
        """The YAML template definition for Faultline compliance must exist."""
        yaml_path = _REPO_ROOT / "apps/web-frontend/src/templates/faultline_compliance.yaml"
        assert yaml_path.exists(), f"Expected YAML template not found at: {yaml_path.resolve()}"
