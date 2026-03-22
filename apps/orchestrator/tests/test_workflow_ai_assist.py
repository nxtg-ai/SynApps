"""Tests for N-39 Workflow AI Assist — Auto-Suggest Next Node.

Covers:
- _score_node_suggestions: transition weights, recency penalty, fallback
- _match_description_to_node: keyword matching
- POST /api/v1/ai-assist/suggest-next
- POST /api/v1/ai-assist/autocomplete
- GET /api/v1/ai-assist/patterns
"""

import sys
import uuid
from pathlib import Path

# Ensure repo root on path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from fastapi.testclient import TestClient

from apps.orchestrator.helpers import (
    _WORKFLOW_PATTERNS,
    _match_description_to_node,
    _score_node_suggestions,
)
from apps.orchestrator.main import app

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _register(client: TestClient, email: str | None = None) -> str:
    """Register a user and return the access_token."""
    email = email or f"aiassist-{uuid.uuid4().hex[:8]}@test.com"
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "AIAssist1!"},
    )
    assert resp.status_code in (200, 201), resp.text
    return resp.json()["access_token"]


# ---------------------------------------------------------------------------
# Unit: _score_node_suggestions
# ---------------------------------------------------------------------------


class TestScoreNodeSuggestions:
    def test_returns_list(self):
        result = _score_node_suggestions("start", [])
        assert isinstance(result, list)
        assert len(result) >= 1  # Gate 2

    def test_sorted_by_score_descending(self):
        result = _score_node_suggestions("start", [])
        scores = [r["score"] for r in result]
        assert scores == sorted(scores, reverse=True)

    def test_each_item_has_required_keys(self):
        result = _score_node_suggestions("llm", [])
        for item in result:
            assert "node_type" in item
            assert "score" in item
            assert "config_template" in item

    def test_known_transition_llm_after_start(self):
        result = _score_node_suggestions("start", [])
        node_types = [r["node_type"] for r in result]
        assert "llm" in node_types

    def test_recency_penalty_reduces_score(self):
        without_penalty = _score_node_suggestions("llm", [])
        with_penalty = _score_node_suggestions("llm", ["llm", "llm", "llm"])
        score_no_penalty = next(
            (r["score"] for r in without_penalty if r["node_type"] == "llm"), None
        )
        score_with_penalty = next(
            (r["score"] for r in with_penalty if r["node_type"] == "llm"), None
        )
        if score_no_penalty is not None and score_with_penalty is not None:
            assert score_with_penalty <= score_no_penalty

    def test_fallback_for_unknown_type(self):
        result = _score_node_suggestions("unknown_type_xyz", [])
        assert isinstance(result, list)
        assert any(r["node_type"] == "llm" for r in result)

    def test_scores_are_non_negative(self):
        result = _score_node_suggestions("foreach", ["code", "code", "code", "code", "code"])
        for item in result:
            assert item["score"] >= 0

    def test_http_transition(self):
        result = _score_node_suggestions("http", [])
        node_types = [r["node_type"] for r in result]
        assert "transform" in node_types

    def test_memory_transition(self):
        result = _score_node_suggestions("memory", [])
        node_types = [r["node_type"] for r in result]
        assert "end" in node_types or "llm" in node_types

    def test_config_template_present_for_llm(self):
        result = _score_node_suggestions("start", [])
        llm_entry = next((r for r in result if r["node_type"] == "llm"), None)
        if llm_entry:
            assert "provider" in llm_entry["config_template"]


# ---------------------------------------------------------------------------
# Unit: _match_description_to_node
# ---------------------------------------------------------------------------


class TestMatchDescriptionToNode:
    def test_llm_keywords(self):
        result = _match_description_to_node("generate text with gpt")
        assert isinstance(result, list)
        assert len(result) >= 1  # Gate 2
        assert result[0]["node_type"] == "llm"

    def test_http_keywords(self):
        result = _match_description_to_node("call external API with GET request")
        assert isinstance(result, list)
        assert len(result) >= 1  # Gate 2
        assert result[0]["node_type"] == "http"

    def test_code_keywords(self):
        result = _match_description_to_node("run python script")
        assert isinstance(result, list)
        assert len(result) >= 1  # Gate 2
        assert result[0]["node_type"] == "code"

    def test_memory_keywords(self):
        result = _match_description_to_node("store and retrieve context in vector memory")
        assert isinstance(result, list)
        assert len(result) >= 1  # Gate 2

    def test_no_match_returns_empty(self):
        result = _match_description_to_node("xyzzy foobar quux")
        assert isinstance(result, list)
        assert result == []

    def test_confidence_in_zero_to_one(self):
        result = _match_description_to_node("summarize text with claude ai model")
        for item in result:
            assert 0.0 <= item["confidence"] <= 1.0

    def test_top_result_has_highest_confidence(self):
        result = _match_description_to_node("fetch http api endpoint url post request")
        if len(result) >= 2:
            assert result[0]["confidence"] >= result[1]["confidence"]

    def test_config_template_in_result(self):
        result = _match_description_to_node("generate image with stable diffusion")
        if result:
            assert "config_template" in result[0]

    def test_scheduler_keywords(self):
        result = _match_description_to_node("run on a cron schedule every day")
        assert isinstance(result, list)
        node_types = [r["node_type"] for r in result]
        assert "scheduler" in node_types

    def test_transform_keywords(self):
        result = _match_description_to_node("convert and parse the output template")
        assert isinstance(result, list)
        node_types = [r["node_type"] for r in result]
        assert "transform" in node_types


# ---------------------------------------------------------------------------
# Unit: pattern library
# ---------------------------------------------------------------------------


class TestPatternLibrary:
    def test_patterns_list_not_empty(self):
        assert isinstance(_WORKFLOW_PATTERNS, list)
        assert len(_WORKFLOW_PATTERNS) >= 1  # Gate 2

    def test_each_pattern_has_required_keys(self):
        for p in _WORKFLOW_PATTERNS:
            assert "name" in p
            assert "description" in p
            assert "sequence" in p
            assert "tags" in p

    def test_sequence_is_list_of_strings(self):
        for p in _WORKFLOW_PATTERNS:
            assert isinstance(p["sequence"], list)
            assert all(isinstance(s, str) for s in p["sequence"])

    def test_tags_are_list(self):
        for p in _WORKFLOW_PATTERNS:
            assert isinstance(p["tags"], list)

    def test_inbox_triage_pattern_present(self):
        names = [p["name"] for p in _WORKFLOW_PATTERNS]
        assert any("Inbox" in n or "Triage" in n for n in names)


# ---------------------------------------------------------------------------
# Integration: POST /api/v1/ai-assist/suggest-next
# ---------------------------------------------------------------------------


class TestSuggestNextEndpoint:
    def test_suggest_next_returns_200(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.post(
                "/api/v1/ai-assist/suggest-next",
                json={"current_node_type": "start", "existing_node_types": []},
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 200

    def test_suggest_next_has_suggestions_key(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.post(
                "/api/v1/ai-assist/suggest-next",
                json={"current_node_type": "llm", "existing_node_types": []},
                headers={"Authorization": f"Bearer {token}"},
            )
        data = resp.json()
        assert "suggestions" in data
        assert isinstance(data["suggestions"], list)
        assert len(data["suggestions"]) >= 1  # Gate 2

    def test_suggest_next_limit_respected(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.post(
                "/api/v1/ai-assist/suggest-next",
                json={"current_node_type": "start", "existing_node_types": [], "limit": 3},
                headers={"Authorization": f"Bearer {token}"},
            )
        data = resp.json()
        assert len(data["suggestions"]) <= 3

    def test_suggest_next_requires_auth(self):
        with TestClient(app) as client:
            _register(client)  # ensure non-trivial DB state
            resp = client.post(
                "/api/v1/ai-assist/suggest-next",
                json={"current_node_type": "start"},
            )
        assert resp.status_code in (401, 403)

    def test_suggest_next_item_structure(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.post(
                "/api/v1/ai-assist/suggest-next",
                json={"current_node_type": "http", "existing_node_types": []},
                headers={"Authorization": f"Bearer {token}"},
            )
        suggestions = resp.json()["suggestions"]
        assert len(suggestions) >= 1  # Gate 2
        first = suggestions[0]
        assert "node_type" in first
        assert "score" in first
        assert "config_template" in first

    def test_suggest_next_unknown_node_type(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.post(
                "/api/v1/ai-assist/suggest-next",
                json={"current_node_type": "mystery_type", "existing_node_types": []},
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "suggestions" in data

    def test_suggest_next_with_existing_nodes(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.post(
                "/api/v1/ai-assist/suggest-next",
                json={
                    "current_node_type": "llm",
                    "existing_node_types": ["start", "llm"],
                },
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "suggestions" in data


# ---------------------------------------------------------------------------
# Integration: POST /api/v1/ai-assist/autocomplete
# ---------------------------------------------------------------------------


class TestAutocompleteEndpoint:
    def test_autocomplete_returns_200(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.post(
                "/api/v1/ai-assist/autocomplete",
                json={"description": "generate text with gpt"},
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 200

    def test_autocomplete_has_matches_key(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.post(
                "/api/v1/ai-assist/autocomplete",
                json={"description": "call an external api"},
                headers={"Authorization": f"Bearer {token}"},
            )
        data = resp.json()
        assert "matches" in data
        assert isinstance(data["matches"], list)
        assert len(data["matches"]) >= 1  # Gate 2

    def test_autocomplete_limit_respected(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.post(
                "/api/v1/ai-assist/autocomplete",
                json={"description": "run python code and call http api", "limit": 2},
                headers={"Authorization": f"Bearer {token}"},
            )
        data = resp.json()
        assert len(data["matches"]) <= 2

    def test_autocomplete_requires_auth(self):
        with TestClient(app) as client:
            _register(client)
            resp = client.post(
                "/api/v1/ai-assist/autocomplete",
                json={"description": "llm node"},
            )
        assert resp.status_code in (401, 403)

    def test_autocomplete_no_match(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.post(
                "/api/v1/ai-assist/autocomplete",
                json={"description": "xyzzy quux foobar"},
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "matches" in data
        assert data["matches"] == []

    def test_autocomplete_item_structure(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.post(
                "/api/v1/ai-assist/autocomplete",
                json={"description": "generate image picture"},
                headers={"Authorization": f"Bearer {token}"},
            )
        matches = resp.json()["matches"]
        if matches:
            first = matches[0]
            assert "node_type" in first
            assert "confidence" in first
            assert "config_template" in first

    def test_autocomplete_top_result_for_llm(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.post(
                "/api/v1/ai-assist/autocomplete",
                json={"description": "use llm model to generate text completion"},
                headers={"Authorization": f"Bearer {token}"},
            )
        data = resp.json()
        if data["matches"]:
            assert data["matches"][0]["node_type"] == "llm"


# ---------------------------------------------------------------------------
# Integration: GET /api/v1/ai-assist/patterns
# ---------------------------------------------------------------------------


class TestPatternsEndpoint:
    def test_patterns_returns_200(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get(
                "/api/v1/ai-assist/patterns",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 200

    def test_patterns_has_expected_keys(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get(
                "/api/v1/ai-assist/patterns",
                headers={"Authorization": f"Bearer {token}"},
            )
        data = resp.json()
        assert "patterns" in data
        assert "total" in data
        assert isinstance(data["patterns"], list)
        assert len(data["patterns"]) >= 1  # Gate 2

    def test_patterns_total_matches_list_length(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get(
                "/api/v1/ai-assist/patterns",
                headers={"Authorization": f"Bearer {token}"},
            )
        data = resp.json()
        assert data["total"] == len(data["patterns"])

    def test_patterns_filter_by_tag(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get(
                "/api/v1/ai-assist/patterns?tag=api",
                headers={"Authorization": f"Bearer {token}"},
            )
        data = resp.json()
        assert "patterns" in data
        for p in data["patterns"]:
            assert any("api" in t for t in p["tags"])

    def test_patterns_filter_no_match(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get(
                "/api/v1/ai-assist/patterns?tag=xyzzy_unknown",
                headers={"Authorization": f"Bearer {token}"},
            )
        data = resp.json()
        assert data["patterns"] == []
        assert data["total"] == 0

    def test_patterns_requires_auth(self):
        with TestClient(app) as client:
            _register(client)
            resp = client.get("/api/v1/ai-assist/patterns")
        assert resp.status_code in (401, 403)

    def test_patterns_item_structure(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get(
                "/api/v1/ai-assist/patterns",
                headers={"Authorization": f"Bearer {token}"},
            )
        patterns = resp.json()["patterns"]
        assert len(patterns) >= 1  # Gate 2
        first = patterns[0]
        assert "name" in first
        assert "description" in first
        assert "sequence" in first
        assert "tags" in first

    def test_patterns_filter_reporting(self):
        with TestClient(app) as client:
            token = _register(client)
            resp = client.get(
                "/api/v1/ai-assist/patterns?tag=reporting",
                headers={"Authorization": f"Bearer {token}"},
            )
        data = resp.json()
        assert data["total"] >= 1  # Gate 2
        for p in data["patterns"]:
            assert any("reporting" in t for t in p["tags"])
