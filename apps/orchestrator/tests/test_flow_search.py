"""
N-132: Flow Search — GET /api/v1/flows/search

Tests:
  - No params returns all flows (same as GET /flows)
  - ?q= matches flow name substring (case-insensitive)
  - ?q= with no match returns empty items list
  - ?tag= filters by single tag
  - Multiple ?tag= values = AND logic (flow must have all tags)
  - ?q= and ?tag= combined (both must match)
  - Pagination: page/page_size respected
  - 401 without auth
  - Response shape: items, total, page, page_size
"""

import uuid

from fastapi.testclient import TestClient

from apps.orchestrator.main import app

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _register(client: TestClient) -> str:
    uid = uuid.uuid4().hex[:8]
    r = client.post(
        "/api/v1/auth/register",
        json={"email": f"search-{uid}@test.com", "password": "pass1234"},
    )
    assert r.status_code == 201
    return r.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_flow(client: TestClient, token: str, name: str) -> str:
    resp = client.post(
        "/api/v1/flows",
        json={"name": name, "nodes": [], "edges": []},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _tag(client: TestClient, token: str, flow_id: str, tag: str) -> None:
    resp = client.post(
        f"/api/v1/flows/{flow_id}/tags",
        json={"tag": tag},
        headers=_auth(token),
    )
    assert resp.status_code == 201


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestFlowSearchName:
    def test_no_params_returns_all_flows(self):
        with TestClient(app) as client:
            token = _register(client)
            _create_flow(client, token, "Alpha Flow")
            _create_flow(client, token, "Beta Flow")
            resp = client.get("/api/v1/flows/search", headers=_auth(token))
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 2  # Gate 2: both flows present

    def test_q_matches_substring(self):
        with TestClient(app) as client:
            token = _register(client)
            _create_flow(client, token, "my-special-flow")
            _create_flow(client, token, "other-flow")
            resp = client.get("/api/v1/flows/search?q=special", headers=_auth(token))
        data = resp.json()
        names = [f["name"] for f in data["items"]]
        assert any("special" in n for n in names)
        assert all("special" in n for n in names)

    def test_q_is_case_insensitive(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_id = _create_flow(client, token, "CamelCase Flow")
            resp = client.get("/api/v1/flows/search?q=camelcase", headers=_auth(token))
        data = resp.json()
        ids = [f["id"] for f in data["items"]]
        assert flow_id in ids

    def test_q_no_match_returns_empty(self):
        with TestClient(app) as client:
            token = _register(client)
            _create_flow(client, token, "Unrelated Flow")
            uid = uuid.uuid4().hex
            resp = client.get(f"/api/v1/flows/search?q={uid}", headers=_auth(token))
        data = resp.json()
        assert data["total"] == 0
        assert data["items"] == []

    def test_response_shape(self):
        with TestClient(app) as client:
            token = _register(client)
            _create_flow(client, token, "Shape Test Flow")
            resp = client.get("/api/v1/flows/search?q=Shape+Test", headers=_auth(token))
        data = resp.json()
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "page_size" in data


class TestFlowSearchTag:
    def test_tag_filter_single(self):
        with TestClient(app) as client:
            token = _register(client)
            flow_a = _create_flow(client, token, "Flow A")
            flow_b = _create_flow(client, token, "Flow B")
            _tag(client, token, flow_a, "production")
            resp = client.get("/api/v1/flows/search?tag=production", headers=_auth(token))
        data = resp.json()
        ids = [f["id"] for f in data["items"]]
        assert flow_a in ids  # Gate 2: tagged flow is present
        assert flow_b not in ids

    def test_tag_filter_and_logic(self):
        """Flow must have ALL specified tags."""
        with TestClient(app) as client:
            token = _register(client)
            both = _create_flow(client, token, "Both Tags")
            one_only = _create_flow(client, token, "One Tag")
            _tag(client, token, both, "alpha")
            _tag(client, token, both, "beta")
            _tag(client, token, one_only, "alpha")
            resp = client.get(
                "/api/v1/flows/search?tag=alpha&tag=beta",
                headers=_auth(token),
            )
        data = resp.json()
        ids = [f["id"] for f in data["items"]]
        assert both in ids  # Gate 2: flow with both tags present
        assert one_only not in ids

    def test_tag_filter_no_match_returns_empty(self):
        with TestClient(app) as client:
            token = _register(client)
            _create_flow(client, token, "Untagged Flow")
            resp = client.get(
                "/api/v1/flows/search?tag=nonexistent-tag-xyz",
                headers=_auth(token),
            )
        data = resp.json()
        assert data["total"] == 0


class TestFlowSearchCombined:
    def test_q_and_tag_combined(self):
        with TestClient(app) as client:
            token = _register(client)
            match = _create_flow(client, token, "prod-workflow")
            no_tag = _create_flow(client, token, "prod-workflow-2")
            wrong_name = _create_flow(client, token, "staging-workflow")
            _tag(client, token, match, "prod")
            _tag(client, token, wrong_name, "prod")
            resp = client.get(
                "/api/v1/flows/search?q=prod-workflow&tag=prod",
                headers=_auth(token),
            )
        data = resp.json()
        ids = [f["id"] for f in data["items"]]
        assert match in ids
        assert no_tag not in ids
        assert wrong_name not in ids


class TestFlowSearchAuth:
    def test_search_requires_auth(self):
        with TestClient(app) as client:
            _register(client)  # activates auth enforcement (disables anonymous bootstrap)
            resp = client.get("/api/v1/flows/search?q=test")
        assert resp.status_code == 401

    def test_search_pagination(self):
        with TestClient(app) as client:
            token = _register(client)
            for i in range(5):
                _create_flow(client, token, f"paginate-flow-{i}")
            resp = client.get(
                "/api/v1/flows/search?q=paginate-flow&page=1&page_size=3",
                headers=_auth(token),
            )
        data = resp.json()
        assert len(data["items"]) == 3
        assert data["total"] >= 5  # Gate 2: all flows counted
        assert data["page"] == 1
        assert data["page_size"] == 3
