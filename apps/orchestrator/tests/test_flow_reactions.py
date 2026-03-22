"""
N-158: Flow Reactions — POST /flows/{id}/reactions
                        DELETE /flows/{id}/reactions/{emoji}
                        GET    /flows/{id}/reactions

Tests:
  - POST adds reaction; returns 201
  - POST response shape (flow_id, emoji, user)
  - POST unsupported emoji → 422
  - POST same emoji twice is idempotent (count stays 1)
  - GET returns empty reactions on fresh flow
  - GET aggregate counts after reactions
  - GET user_reactions lists only current user's reactions
  - GET shows allowed emojis list
  - GET flow_id in response
  - DELETE removes reaction; returns {deleted: true}
  - DELETE 404 for reaction not yet added
  - DELETE unsupported emoji → 422
  - GET after DELETE shows no user reaction
  - Two users react same emoji → count = 2
  - POST/GET/DELETE 404 for unknown flow
  - Auth required on all endpoints
"""

import uuid

from fastapi.testclient import TestClient

from apps.orchestrator.main import app

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _register(client: TestClient) -> tuple[str, str]:
    uid = uuid.uuid4().hex[:8]
    email = f"rxn-{uid}@test.com"
    r = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "pass1234"},
    )
    assert r.status_code == 201
    return r.json()["access_token"], email


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_flow(client: TestClient, token: str) -> str:
    resp = client.post(
        "/api/v1/flows",
        json={"name": "Reaction Test Flow", "nodes": [], "edges": []},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _react(client: TestClient, token: str, flow_id: str, emoji: str = "👍") -> dict:
    resp = client.post(
        f"/api/v1/flows/{flow_id}/reactions",
        json={"emoji": emoji},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    return resp.json()


# ---------------------------------------------------------------------------
# Tests — POST /flows/{id}/reactions
# ---------------------------------------------------------------------------


class TestFlowReactionPost:
    def test_post_returns_201(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/reactions",
                json={"emoji": "👍"},
                headers=_auth(token),
            )
        assert resp.status_code == 201
        data = resp.json()
        assert data["flow_id"] == flow_id

    def test_post_response_shape(self):
        with TestClient(app) as client:
            token, email = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/reactions",
                json={"emoji": "🔥"},
                headers=_auth(token),
            )
        data = resp.json()
        assert data["flow_id"] == flow_id
        assert data["emoji"] == "🔥"
        assert data["user"] == email

    def test_post_unsupported_emoji_422(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/reactions",
                json={"emoji": "🐉"},
                headers=_auth(token),
            )
        assert resp.status_code == 422
        assert "error" in resp.json()

    def test_post_same_emoji_idempotent(self):
        """Reacting with the same emoji twice keeps count at 1."""
        with TestClient(app) as client:
            token, _ = _register(client)
            flow_id = _create_flow(client, token)
            _react(client, token, flow_id, "👍")
            _react(client, token, flow_id, "👍")
            resp = client.get(f"/api/v1/flows/{flow_id}/reactions", headers=_auth(token))
        counts = {r["emoji"]: r["count"] for r in resp.json()["reactions"]}
        assert counts.get("👍", 0) == 1

    def test_post_404_unknown_flow(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            resp = client.post(
                "/api/v1/flows/nonexistent/reactions",
                json={"emoji": "👍"},
                headers=_auth(token),
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_post_requires_auth(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.post(
                f"/api/v1/flows/{flow_id}/reactions",
                json={"emoji": "👍"},
            )
        assert resp.status_code == 401
        assert "error" in resp.json()


# ---------------------------------------------------------------------------
# Tests — GET /flows/{id}/reactions
# ---------------------------------------------------------------------------


class TestFlowReactionGet:
    def test_get_empty_on_fresh_flow(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/reactions", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["reactions"] == []

    def test_get_aggregate_counts(self):
        with TestClient(app) as client:
            token_a, _ = _register(client)
            token_b, _ = _register(client)
            flow_id = _create_flow(client, token_a)
            _react(client, token_a, flow_id, "👍")
            _react(client, token_b, flow_id, "👍")
            _react(client, token_a, flow_id, "🔥")
            resp = client.get(f"/api/v1/flows/{flow_id}/reactions", headers=_auth(token_a))
        counts = {r["emoji"]: r["count"] for r in resp.json()["reactions"]}
        assert counts["👍"] == 2
        assert counts["🔥"] == 1

    def test_get_user_reactions(self):
        with TestClient(app) as client:
            token_a, _ = _register(client)
            token_b, _ = _register(client)
            flow_id = _create_flow(client, token_a)
            _react(client, token_a, flow_id, "👍")
            _react(client, token_b, flow_id, "👍")
            _react(client, token_a, flow_id, "🎉")
            resp = client.get(f"/api/v1/flows/{flow_id}/reactions", headers=_auth(token_a))
        mine = resp.json()["user_reactions"]
        assert "👍" in mine
        assert "🎉" in mine

    def test_get_allowed_emojis_present(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/reactions", headers=_auth(token))
        assert len(resp.json()["allowed"]) >= 10

    def test_get_flow_id_in_response(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/reactions", headers=_auth(token))
        assert resp.json()["flow_id"] == flow_id

    def test_get_404_unknown_flow(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            resp = client.get("/api/v1/flows/nonexistent/reactions", headers=_auth(token))
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_get_requires_auth(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.get(f"/api/v1/flows/{flow_id}/reactions")
        assert resp.status_code == 401
        assert "error" in resp.json()


# ---------------------------------------------------------------------------
# Tests — DELETE /flows/{id}/reactions/{emoji}
# ---------------------------------------------------------------------------


class TestFlowReactionDelete:
    def test_delete_removes_reaction(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            flow_id = _create_flow(client, token)
            _react(client, token, flow_id, "👍")
            resp = client.delete(
                f"/api/v1/flows/{flow_id}/reactions/👍", headers=_auth(token)
            )
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True

    def test_get_after_delete_shows_no_reaction(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            flow_id = _create_flow(client, token)
            _react(client, token, flow_id, "👍")
            client.delete(f"/api/v1/flows/{flow_id}/reactions/👍", headers=_auth(token))
            resp = client.get(f"/api/v1/flows/{flow_id}/reactions", headers=_auth(token))
        assert resp.json()["reactions"] == []
        assert resp.json()["user_reactions"] == []

    def test_delete_404_reaction_not_added(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.delete(
                f"/api/v1/flows/{flow_id}/reactions/👍", headers=_auth(token)
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_delete_unsupported_emoji_422(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            flow_id = _create_flow(client, token)
            resp = client.delete(
                f"/api/v1/flows/{flow_id}/reactions/🐉", headers=_auth(token)
            )
        assert resp.status_code == 422
        assert "error" in resp.json()

    def test_delete_404_unknown_flow(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            resp = client.delete(
                "/api/v1/flows/nonexistent/reactions/👍", headers=_auth(token)
            )
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_delete_requires_auth(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            flow_id = _create_flow(client, token)
            _react(client, token, flow_id, "👍")
            resp = client.delete(f"/api/v1/flows/{flow_id}/reactions/👍")
        assert resp.status_code == 401
        assert "error" in resp.json()

    def test_two_users_same_emoji_count_two(self):
        """Two distinct users reacting with 👍 yields count 2; deleting one → count 1."""
        with TestClient(app) as client:
            token_a, _ = _register(client)
            token_b, _ = _register(client)
            flow_id = _create_flow(client, token_a)
            _react(client, token_a, flow_id, "👍")
            _react(client, token_b, flow_id, "👍")
            # Delete user A's reaction
            client.delete(f"/api/v1/flows/{flow_id}/reactions/👍", headers=_auth(token_a))
            resp = client.get(f"/api/v1/flows/{flow_id}/reactions", headers=_auth(token_b))
        counts = {r["emoji"]: r["count"] for r in resp.json()["reactions"]}
        assert counts.get("👍", 0) == 1
