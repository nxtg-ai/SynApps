"""Tests for Marketplace Revenue — Credit Ledger (N-47).

Covers:
  - CreditLedger unit tests (8)
  - Credit-earned-on-install integration tests (4)
  - Credits endpoints integration tests (6)
  - Payout report integration tests (4)

Total: ~22 tests.
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from apps.orchestrator.main import app
from apps.orchestrator.stores import (
    CreditLedger,
    credit_ledger,
    marketplace_registry,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _register(client: TestClient) -> str:
    """Register a fresh user and return the access_token."""
    email = f"u-{uuid.uuid4().hex[:8]}@example.com"
    resp = client.post("/api/v1/auth/register", json={"email": email, "password": "Pass1234!"})
    assert resp.status_code == 201, resp.text
    return resp.json()["access_token"]


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _publish_listing(
    registry,
    name: str = "Test Listing",
    category: str = "notification",
    publisher_id: str | None = None,
) -> dict:
    """Publish a listing directly into the registry with a known publisher_id."""
    entry = registry.publish(
        {
            "name": name,
            "description": f"Description for {name}",
            "category": category,
            "tags": [],
            "author": "test-author",
            "publisher_id": publisher_id,
            "nodes": [
                {"id": "n1", "type": "start", "position": {"x": 0, "y": 0}, "data": {}},
            ],
            "edges": [],
        }
    )
    return entry


# ---------------------------------------------------------------------------
# TestCreditLedger — 8 unit tests
# ---------------------------------------------------------------------------


class TestCreditLedger:
    """Unit tests for the CreditLedger class (no HTTP)."""

    def test_credit_adds_entry(self):
        """credit() creates an entry with correct fields."""
        ledger = CreditLedger()
        entry = ledger.credit("pub1", "list1", "My Template", 10)
        assert entry["type"] == "credit"
        assert entry["amount"] == 10
        assert entry["publisher_id"] == "pub1"
        assert entry["listing_id"] == "list1"
        assert entry["listing_name"] == "My Template"
        assert "entry_id" in entry
        assert "created_at" in entry

    def test_debit_reduces_balance(self):
        """debit() subtracts from available balance."""
        ledger = CreditLedger()
        ledger.credit("pub1", "list1", "Template", 50)
        ledger.debit("pub1", 20, note="payout")
        assert ledger.balance("pub1") == 30

    def test_debit_raises_on_insufficient_balance(self):
        """debit() raises ValueError when balance is too low."""
        ledger = CreditLedger()
        ledger.credit("pub1", "list1", "Template", 10)
        with pytest.raises(ValueError, match="Insufficient balance"):
            ledger.debit("pub1", 20)

    def test_balance_starts_at_zero(self):
        """balance() returns 0 for unknown publisher."""
        ledger = CreditLedger()
        assert ledger.balance("nonexistent") == 0

    def test_ledger_newest_first(self):
        """ledger() returns entries in reverse chronological order."""
        ledger = CreditLedger()
        ledger.credit("pub1", "list1", "First", 10)
        ledger.credit("pub1", "list2", "Second", 20)
        entries = ledger.ledger("pub1")
        assert isinstance(entries, list)
        assert len(entries) >= 2  # Gate 2
        assert entries[0]["listing_name"] == "Second"
        assert entries[1]["listing_name"] == "First"

    def test_total_earned_excludes_debits(self):
        """total_earned() sums only credit entries."""
        ledger = CreditLedger()
        ledger.credit("pub1", "list1", "Template", 30)
        ledger.credit("pub1", "list2", "Template2", 20)
        ledger.debit("pub1", 10)
        assert ledger.total_earned("pub1") == 50
        assert ledger.balance("pub1") == 40

    def test_payout_report_structure(self):
        """payout_report() returns all expected keys."""
        ledger = CreditLedger()
        ledger.credit("pub1", "list1", "Template", 30)
        ledger.debit("pub1", 10, note="test payout")
        report = ledger.payout_report("pub1")
        assert report["balance"] == 20
        assert report["total_earned"] == 30
        assert report["total_paid_out"] == 10
        assert report["entry_count"] == 2
        assert isinstance(report["per_listing"], list)
        assert len(report["per_listing"]) >= 1  # Gate 2

    def test_reset_clears_all(self):
        """reset() wipes all entries."""
        ledger = CreditLedger()
        ledger.credit("pub1", "list1", "Template", 10)
        assert ledger.balance("pub1") == 10
        ledger.reset()
        assert ledger.balance("pub1") == 0


# ---------------------------------------------------------------------------
# TestCreditEarnedOnInstall — 4 integration tests
# ---------------------------------------------------------------------------


class TestCreditEarnedOnInstall:
    """Integration: installing a marketplace listing awards credits."""

    def test_install_awards_credits_to_publisher(self):
        """POST /marketplace/install/{id} credits the publisher."""
        with TestClient(app) as client:
            token = _register(client)
            # Get the user ID from the token
            me = client.get("/api/v1/auth/me", headers=_auth_headers(token))
            user_id = me.json()["id"]

            listing = _publish_listing(
                marketplace_registry, name="Credit Flow", publisher_id=user_id
            )

            client.post(
                f"/api/v1/marketplace/install/{listing['id']}",
                json={},
                headers=_auth_headers(token),
            )
            assert credit_ledger.balance(user_id) == CreditLedger.CREDITS_PER_INSTALL

    def test_second_install_adds_more_credits(self):
        """Two installs award 2x CREDITS_PER_INSTALL."""
        with TestClient(app) as client:
            token = _register(client)
            me = client.get("/api/v1/auth/me", headers=_auth_headers(token))
            user_id = me.json()["id"]

            listing = _publish_listing(
                marketplace_registry, name="Double Install", publisher_id=user_id
            )

            client.post(
                f"/api/v1/marketplace/install/{listing['id']}",
                json={},
                headers=_auth_headers(token),
            )
            client.post(
                f"/api/v1/marketplace/install/{listing['id']}",
                json={},
                headers=_auth_headers(token),
            )
            assert credit_ledger.balance(user_id) == 2 * CreditLedger.CREDITS_PER_INSTALL

    def test_unregistered_listing_does_not_crash(self):
        """Installing a nonexistent listing returns 404 and no credits."""
        with TestClient(app) as client:
            token = _register(client)
            resp = client.post(
                "/api/v1/marketplace/install/nonexistent-id",
                json={},
                headers=_auth_headers(token),
            )
            assert resp.status_code == 404

    def test_credit_count_after_multiple_installs(self):
        """Gate 2: confirm ledger has correct entry count after 3 installs."""
        with TestClient(app) as client:
            token = _register(client)
            me = client.get("/api/v1/auth/me", headers=_auth_headers(token))
            user_id = me.json()["id"]

            listing = _publish_listing(
                marketplace_registry, name="Multi Install", publisher_id=user_id
            )

            for _ in range(3):
                client.post(
                    f"/api/v1/marketplace/install/{listing['id']}",
                    json={},
                    headers=_auth_headers(token),
                )

            entries = credit_ledger.ledger(user_id)
            assert isinstance(entries, list)
            assert len(entries) >= 3  # Gate 2
            assert credit_ledger.balance(user_id) == 3 * CreditLedger.CREDITS_PER_INSTALL


# ---------------------------------------------------------------------------
# TestCreditsEndpoints — 6 integration tests
# ---------------------------------------------------------------------------


class TestCreditsEndpoints:
    """Integration tests for the /marketplace/publisher/credits/* endpoints."""

    def test_get_credits_returns_correct_shape(self):
        """GET /marketplace/publisher/credits returns 200 with expected keys."""
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get(
                "/api/v1/marketplace/publisher/credits",
                headers=_auth_headers(token),
            )
            assert resp.status_code == 200
            data = resp.json()
            assert "balance" in data
            assert "total_earned" in data
            assert "total_paid_out" in data
            assert "entry_count" in data

    def test_get_credits_requires_auth(self):
        """GET /marketplace/publisher/credits without auth returns 401."""
        with TestClient(app) as client:
            # Register a user so auth is enforced (not bypass mode)
            _register(client)
            resp = client.get("/api/v1/marketplace/publisher/credits")
            assert resp.status_code == 401

    def test_ledger_includes_entries(self):
        """GET /marketplace/publisher/credits/ledger shows credit entries."""
        with TestClient(app) as client:
            token = _register(client)
            me = client.get("/api/v1/auth/me", headers=_auth_headers(token))
            user_id = me.json()["id"]

            # Seed credits directly
            credit_ledger.credit(user_id, "list-a", "Template A", 10)

            resp = client.get(
                "/api/v1/marketplace/publisher/credits/ledger",
                headers=_auth_headers(token),
            )
            assert resp.status_code == 200
            data = resp.json()
            assert isinstance(data["entries"], list)
            assert len(data["entries"]) >= 1  # Gate 2
            assert data["entries"][0]["listing_name"] == "Template A"

    def test_payout_succeeds(self):
        """POST /marketplace/publisher/credits/payout deducts credits."""
        with TestClient(app) as client:
            token = _register(client)
            me = client.get("/api/v1/auth/me", headers=_auth_headers(token))
            user_id = me.json()["id"]

            credit_ledger.credit(user_id, "list-a", "Template A", 50)

            resp = client.post(
                "/api/v1/marketplace/publisher/credits/payout",
                json={"amount": 30},
                headers=_auth_headers(token),
            )
            assert resp.status_code == 200
            assert resp.json()["balance"] == 20

    def test_payout_400_on_insufficient(self):
        """POST /marketplace/publisher/credits/payout returns 400 if balance too low."""
        with TestClient(app) as client:
            token = _register(client)
            resp = client.post(
                "/api/v1/marketplace/publisher/credits/payout",
                json={"amount": 100},
                headers=_auth_headers(token),
            )
            assert resp.status_code == 400
            assert "Insufficient" in resp.json()["error"]["message"]

    def test_payout_report_has_per_listing(self):
        """GET /marketplace/publisher/credits/payout-report includes per_listing."""
        with TestClient(app) as client:
            token = _register(client)
            me = client.get("/api/v1/auth/me", headers=_auth_headers(token))
            user_id = me.json()["id"]

            credit_ledger.credit(user_id, "list-a", "Template A", 10)

            resp = client.get(
                "/api/v1/marketplace/publisher/credits/payout-report",
                headers=_auth_headers(token),
            )
            assert resp.status_code == 200
            data = resp.json()
            assert isinstance(data["per_listing"], list)
            assert len(data["per_listing"]) >= 1  # Gate 2
            assert data["per_listing"][0]["listing_id"] == "list-a"


# ---------------------------------------------------------------------------
# TestPayoutReport — 4 integration tests
# ---------------------------------------------------------------------------


class TestPayoutReport:
    """Integration tests for payout report content."""

    def test_empty_report_for_new_publisher(self):
        """payout_report for unknown publisher returns zero values."""
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get(
                "/api/v1/marketplace/publisher/credits/payout-report",
                headers=_auth_headers(token),
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["balance"] == 0
            assert data["total_earned"] == 0
            assert data["total_paid_out"] == 0
            assert data["entry_count"] == 0
            assert data["per_listing"] == []

    def test_report_reflects_installs(self):
        """Report totals match the credits awarded from installs."""
        with TestClient(app) as client:
            token = _register(client)
            me = client.get("/api/v1/auth/me", headers=_auth_headers(token))
            user_id = me.json()["id"]

            listing = _publish_listing(
                marketplace_registry, name="Report Flow", publisher_id=user_id
            )

            for _ in range(3):
                client.post(
                    f"/api/v1/marketplace/install/{listing['id']}",
                    json={},
                    headers=_auth_headers(token),
                )

            resp = client.get(
                "/api/v1/marketplace/publisher/credits/payout-report",
                headers=_auth_headers(token),
            )
            data = resp.json()
            assert data["total_earned"] == 30
            assert data["balance"] == 30
            assert data["entry_count"] == 3

    def test_per_listing_breakdown_correct(self):
        """Per-listing breakdown shows installs and credits for each listing."""
        with TestClient(app) as client:
            token = _register(client)
            me = client.get("/api/v1/auth/me", headers=_auth_headers(token))
            user_id = me.json()["id"]

            credit_ledger.credit(user_id, "list-x", "Template X", 10)
            credit_ledger.credit(user_id, "list-x", "Template X", 10)

            resp = client.get(
                "/api/v1/marketplace/publisher/credits/payout-report",
                headers=_auth_headers(token),
            )
            data = resp.json()
            assert isinstance(data["per_listing"], list)
            assert len(data["per_listing"]) >= 1  # Gate 2
            entry = data["per_listing"][0]
            assert entry["listing_id"] == "list-x"
            assert entry["installs"] == 2
            assert entry["credits_earned"] == 20

    def test_multiple_listings_show_separately(self):
        """Credits from different listings appear as separate per_listing entries."""
        with TestClient(app) as client:
            token = _register(client)
            me = client.get("/api/v1/auth/me", headers=_auth_headers(token))
            user_id = me.json()["id"]

            credit_ledger.credit(user_id, "list-a", "Template A", 10)
            credit_ledger.credit(user_id, "list-b", "Template B", 10)

            resp = client.get(
                "/api/v1/marketplace/publisher/credits/payout-report",
                headers=_auth_headers(token),
            )
            data = resp.json()
            assert isinstance(data["per_listing"], list)
            assert len(data["per_listing"]) >= 2  # Gate 2
            listing_ids = {e["listing_id"] for e in data["per_listing"]}
            assert "list-a" in listing_ids
            assert "list-b" in listing_ids
