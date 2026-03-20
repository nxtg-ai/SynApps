"""Tests for N-36 OAuth2 Provider — SSO for Enterprise.

Covers:
  - OAuthClientRegistry unit tests
  - AuthorizationCodeStore unit tests
  - Full OAuth2 authorization_code and client_credentials flows via HTTP
  - Token introspection (RFC 7662)
"""

import time
import uuid
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from apps.orchestrator.main import (
    AuthorizationCodeStore,
    OAuthClientRegistry,
    app,
    auth_code_store,
    oauth_client_registry,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _reset_oauth_state():
    """Isolate each test by resetting both in-memory stores."""
    oauth_client_registry.reset()
    auth_code_store.reset()
    yield
    oauth_client_registry.reset()
    auth_code_store.reset()


@pytest.fixture
def auth_headers(client):
    """Register a test user and return Authorization headers with their access token."""
    email = f"oauth-test-{uuid.uuid4().hex[:8]}@example.com"
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "OAuthTest1!"},
    )
    assert resp.status_code == 201
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def registered_client():
    """Register a test OAuth2 client and return the full record (including plain secret)."""
    return oauth_client_registry.register(
        name="Test App",
        redirect_uris=["https://app.example.com/callback"],
        allowed_scopes=["read", "write"],
        grant_types=["authorization_code", "client_credentials"],
    )


# ---------------------------------------------------------------------------
# TestOAuthClientRegistry — unit tests
# ---------------------------------------------------------------------------


class TestOAuthClientRegistry:
    def test_register_returns_record_with_secret(self):
        """register() returns a full client record including the plain client_secret."""
        reg = OAuthClientRegistry()
        record = reg.register(
            name="My App",
            redirect_uris=["https://example.com/cb"],
            allowed_scopes=["read"],
            grant_types=["authorization_code"],
        )
        assert "client_id" in record
        assert "client_secret" in record
        assert len(record["client_secret"]) == 64  # secrets.token_hex(32)
        assert record["name"] == "My App"
        assert record["redirect_uris"] == ["https://example.com/cb"]
        assert record["allowed_scopes"] == ["read"]
        assert record["grant_types"] == ["authorization_code"]
        assert record["is_active"] is True

    def test_get_returns_record_without_secret_hash(self):
        """get() returns the client record and never exposes the internal secret hash."""
        reg = OAuthClientRegistry()
        created = reg.register(
            name="App",
            redirect_uris=["https://example.com/cb"],
            allowed_scopes=["read"],
            grant_types=["authorization_code"],
        )
        fetched = reg.get(created["client_id"])
        assert fetched is not None
        assert fetched["client_id"] == created["client_id"]
        assert "_secret_hash" not in fetched
        assert "client_secret" not in fetched

    def test_validate_secret_correct(self):
        """validate_secret() returns True when the correct plain secret is supplied."""
        reg = OAuthClientRegistry()
        record = reg.register(
            name="App",
            redirect_uris=["https://example.com/cb"],
            allowed_scopes=["read"],
            grant_types=["authorization_code"],
        )
        assert reg.validate_secret(record["client_id"], record["client_secret"]) is True

    def test_validate_secret_wrong(self):
        """validate_secret() returns False for an incorrect secret."""
        reg = OAuthClientRegistry()
        record = reg.register(
            name="App",
            redirect_uris=["https://example.com/cb"],
            allowed_scopes=["read"],
            grant_types=["authorization_code"],
        )
        assert reg.validate_secret(record["client_id"], "wrong-secret") is False

    def test_list_all_excludes_secret(self):
        """list_all() returns all clients without secret hashes; Gate 2 length guard."""
        reg = OAuthClientRegistry()
        reg.register(
            name="A",
            redirect_uris=["https://a.example.com/cb"],
            allowed_scopes=["read"],
            grant_types=["authorization_code"],
        )
        reg.register(
            name="B",
            redirect_uris=["https://b.example.com/cb"],
            allowed_scopes=["write"],
            grant_types=["client_credentials"],
        )
        clients = reg.list_all()
        assert isinstance(clients, list)
        assert len(clients) >= 2  # Gate 2: confirm both registrations persisted
        for c in clients:
            assert "_secret_hash" not in c
            assert "client_secret" not in c

    def test_revoke_deactivates_client(self):
        """revoke() sets is_active=False; subsequent validate_secret() returns False."""
        reg = OAuthClientRegistry()
        record = reg.register(
            name="App",
            redirect_uris=["https://example.com/cb"],
            allowed_scopes=["read"],
            grant_types=["authorization_code"],
        )
        client_id = record["client_id"]
        assert reg.revoke(client_id) is True
        # validate_secret must refuse inactive clients
        assert reg.validate_secret(client_id, record["client_secret"]) is False

    def test_get_unknown_client_returns_none(self):
        """get() returns None for a client_id that was never registered."""
        reg = OAuthClientRegistry()
        assert reg.get("nonexistent-id") is None

    def test_revoke_unknown_client_returns_false(self):
        """revoke() returns False when the client_id does not exist."""
        reg = OAuthClientRegistry()
        assert reg.revoke("does-not-exist") is False


# ---------------------------------------------------------------------------
# TestAuthorizationCodeStore — unit tests
# ---------------------------------------------------------------------------


class TestAuthorizationCodeStore:
    def test_create_returns_nonempty_code(self):
        """create() returns a non-empty string code."""
        store = AuthorizationCodeStore()
        code = store.create(
            client_id="cid",
            user_id="uid",
            scopes=["read"],
            redirect_uri="https://example.com/cb",
        )
        assert isinstance(code, str)
        assert len(code) > 10

    def test_consume_valid_code_once(self):
        """consume() returns the record on the first call."""
        store = AuthorizationCodeStore()
        code = store.create(
            client_id="cid",
            user_id="uid",
            scopes=["read"],
            redirect_uri="https://example.com/cb",
        )
        record = store.consume(code)
        assert record is not None
        assert record["client_id"] == "cid"
        assert record["user_id"] == "uid"
        assert record["scopes"] == ["read"]

    def test_consume_used_code_returns_none(self):
        """consume() returns None on the second call for the same code."""
        store = AuthorizationCodeStore()
        code = store.create(
            client_id="cid",
            user_id="uid",
            scopes=["read"],
            redirect_uri="https://example.com/cb",
        )
        store.consume(code)
        result = store.consume(code)
        assert result is None

    def test_consume_expired_code_returns_none(self):
        """consume() returns None when the code's TTL has elapsed."""
        store = AuthorizationCodeStore()
        code = store.create(
            client_id="cid",
            user_id="uid",
            scopes=["read"],
            redirect_uri="https://example.com/cb",
        )
        # Manually expire the code by patching time
        with patch("apps.orchestrator.main.time") as mock_time:
            mock_time.time.return_value = time.time() + 700  # past 600s TTL
            result = store.consume(code)
        assert result is None

    def test_cleanup_expired_removes_old_codes(self):
        """cleanup_expired() removes codes whose TTL has passed."""
        store = AuthorizationCodeStore()
        code = store.create(
            client_id="cid",
            user_id="uid",
            scopes=["read"],
            redirect_uri="https://example.com/cb",
        )
        # Force the code to appear expired
        with store._lock:
            store._codes[code]["expires_at"] = time.time() - 1
        store.cleanup_expired()
        # After cleanup the code is gone; consume must return None
        assert store.consume(code) is None


# ---------------------------------------------------------------------------
# TestOAuthFlows — HTTP integration tests
# ---------------------------------------------------------------------------


class TestOAuthFlows:
    def test_client_registration_api(self, client, auth_headers):
        """POST /oauth/clients creates a client and returns client_secret."""
        resp = client.post(
            "/api/v1/oauth/clients",
            json={
                "name": "Enterprise App",
                "redirect_uris": ["https://enterprise.example.com/cb"],
                "allowed_scopes": ["read", "write"],
                "grant_types": ["authorization_code"],
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "client_id" in data
        assert "client_secret" in data
        assert data["name"] == "Enterprise App"

    def test_list_clients_api(self, client, auth_headers):
        """GET /oauth/clients returns all clients; Gate 2 length guard after registration."""
        client.post(
            "/api/v1/oauth/clients",
            json={
                "name": "App1",
                "redirect_uris": ["https://app1.example.com/cb"],
                "allowed_scopes": ["read"],
                "grant_types": ["authorization_code"],
            },
            headers=auth_headers,
        )
        resp = client.get("/api/v1/oauth/clients", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 1  # Gate 2: at least the one we just registered

    def test_authorization_code_full_flow(self, client, auth_headers, registered_client):
        """Full authorization_code flow: authorize -> token."""
        # Step 1: get authorization code
        resp = client.get(
            "/api/v1/oauth/authorize",
            params={
                "client_id": registered_client["client_id"],
                "redirect_uri": "https://app.example.com/callback",
                "response_type": "code",
                "scope": "read",
                "state": "xyz123",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 200
        auth_data = resp.json()
        assert "code" in auth_data
        assert auth_data["state"] == "xyz123"

        # Step 2: exchange code for token
        token_resp = client.post(
            "/api/v1/oauth/token",
            data={
                "grant_type": "authorization_code",
                "client_id": registered_client["client_id"],
                "client_secret": registered_client["client_secret"],
                "code": auth_data["code"],
                "redirect_uri": "https://app.example.com/callback",
            },
        )
        assert token_resp.status_code == 200
        token_data = token_resp.json()
        assert "access_token" in token_data
        assert token_data["token_type"] == "bearer"
        assert "expires_in" in token_data
        assert "scope" in token_data

    def test_client_credentials_full_flow(self, client, registered_client):
        """client_credentials grant issues a token with sub=client_id."""
        resp = client.post(
            "/api/v1/oauth/token",
            data={
                "grant_type": "client_credentials",
                "client_id": registered_client["client_id"],
                "client_secret": registered_client["client_secret"],
                "scope": "read",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["scope"] == "read"

    def test_token_with_invalid_client_id(self, client):
        """Token endpoint returns 401 for an unknown client_id."""
        resp = client.post(
            "/api/v1/oauth/token",
            data={
                "grant_type": "client_credentials",
                "client_id": "nonexistent-client",
                "client_secret": "any-secret",
            },
        )
        assert resp.status_code == 401

    def test_token_with_wrong_client_secret(self, client, registered_client):
        """Token endpoint returns 401 when the client_secret is incorrect."""
        resp = client.post(
            "/api/v1/oauth/token",
            data={
                "grant_type": "client_credentials",
                "client_id": registered_client["client_id"],
                "client_secret": "wrong-secret-value",
            },
        )
        assert resp.status_code == 401

    def test_token_with_invalid_grant_type(self, client, registered_client):
        """Token endpoint returns 400 for an unsupported grant_type."""
        resp = client.post(
            "/api/v1/oauth/token",
            data={
                "grant_type": "password",
                "client_id": registered_client["client_id"],
                "client_secret": registered_client["client_secret"],
            },
        )
        assert resp.status_code == 400

    def test_authorize_requires_auth_header(self, client, registered_client):
        """Authorization endpoint returns 401 without a user Bearer token."""
        resp = client.get(
            "/api/v1/oauth/authorize",
            params={
                "client_id": registered_client["client_id"],
                "redirect_uri": "https://app.example.com/callback",
                "response_type": "code",
                "scope": "read",
            },
        )
        assert resp.status_code == 401

    def test_delete_client_endpoint(self, client, auth_headers, registered_client):
        """DELETE /oauth/clients/{id} deactivates a client."""
        resp = client.delete(
            f"/api/v1/oauth/clients/{registered_client['client_id']}",
            headers=auth_headers,
        )
        assert resp.status_code == 204

        # client_credentials for deactivated client must now fail
        token_resp = client.post(
            "/api/v1/oauth/token",
            data={
                "grant_type": "client_credentials",
                "client_id": registered_client["client_id"],
                "client_secret": registered_client["client_secret"],
            },
        )
        assert token_resp.status_code == 401


# ---------------------------------------------------------------------------
# TestOAuthIntrospect — token introspection tests
# ---------------------------------------------------------------------------


class TestOAuthIntrospect:
    def _get_oauth_token(self, client, registered_client) -> str:
        """Helper: obtain a client_credentials token for introspection tests."""
        resp = client.post(
            "/api/v1/oauth/token",
            data={
                "grant_type": "client_credentials",
                "client_id": registered_client["client_id"],
                "client_secret": registered_client["client_secret"],
                "scope": "read",
            },
        )
        assert resp.status_code == 200
        return resp.json()["access_token"]

    def test_introspect_active_token(self, client, registered_client):
        """Introspection returns active=True for a valid OAuth2 token."""
        token = self._get_oauth_token(client, registered_client)
        resp = client.post("/api/v1/oauth/introspect", data={"token": token})
        assert resp.status_code == 200
        data = resp.json()
        assert data["active"] is True
        assert data["client_id"] == registered_client["client_id"]

    def test_introspect_expired_token_returns_inactive(self, client, registered_client):
        """Introspection returns active=False for an expired token."""
        token = self._get_oauth_token(client, registered_client)
        # Decode then re-encode with past expiry via patching jwt.decode to raise
        with patch("apps.orchestrator.main.jwt.decode") as mock_decode:
            import jwt as pyjwt

            mock_decode.side_effect = pyjwt.ExpiredSignatureError("expired")
            resp = client.post("/api/v1/oauth/introspect", data={"token": token})
        assert resp.status_code == 200
        assert resp.json()["active"] is False

    def test_introspect_invalid_token_string(self, client):
        """Introspection returns active=False for a non-JWT string."""
        resp = client.post("/api/v1/oauth/introspect", data={"token": "this.is.not.a.jwt"})
        assert resp.status_code == 200
        assert resp.json()["active"] is False

    def test_introspect_non_oauth2_token_returns_inactive(self, client, auth_headers):
        """Introspection returns active=False for a regular access token (token_type!=oauth2)."""
        # Get a regular user access token
        email = f"introspect-{uuid.uuid4().hex[:8]}@example.com"
        resp = client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "Test1234!"},
        )
        assert resp.status_code == 201
        user_token = resp.json()["access_token"]

        introspect_resp = client.post("/api/v1/oauth/introspect", data={"token": user_token})
        assert introspect_resp.status_code == 200
        assert introspect_resp.json()["active"] is False

    def test_introspect_scope_included_in_response(self, client, registered_client):
        """Introspection response includes the scope field."""
        token = self._get_oauth_token(client, registered_client)
        resp = client.post("/api/v1/oauth/introspect", data={"token": token})
        assert resp.status_code == 200
        data = resp.json()
        assert data["active"] is True
        assert "scope" in data
        assert data["scope"] == "read"

    def test_introspect_exp_included_in_response(self, client, registered_client):
        """Introspection response includes the exp (expiry) field."""
        token = self._get_oauth_token(client, registered_client)
        resp = client.post("/api/v1/oauth/introspect", data={"token": token})
        assert resp.status_code == 200
        data = resp.json()
        assert data["active"] is True
        assert "exp" in data
        assert isinstance(data["exp"], int)

    def test_introspect_client_credentials_token_sub_is_client_id(self, client, registered_client):
        """For client_credentials tokens, sub equals client_id."""
        token = self._get_oauth_token(client, registered_client)
        resp = client.post("/api/v1/oauth/introspect", data={"token": token})
        assert resp.status_code == 200
        data = resp.json()
        assert data["active"] is True
        assert data["sub"] == registered_client["client_id"]
