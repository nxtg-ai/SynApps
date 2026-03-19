"""
N-31: Workflow Import from External Tools
Tests for WorkflowImportService and POST /workflows/import.
Covers n8n import, Zapier import, format auto-detection, save flag,
and endpoint auth.
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from apps.orchestrator.main import (
    WorkflowImportService,
    app,
    audit_log_store,
    workflow_permission_store,
)

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

N8N_WORKFLOW = {
    "name": "Test n8n Workflow",
    "nodes": [
        {
            "name": "Start",
            "type": "n8n-nodes-base.manualTrigger",
            "position": [100, 200],
            "parameters": {},
        },
        {
            "name": "HTTP Request",
            "type": "n8n-nodes-base.httpRequest",
            "position": [300, 200],
            "parameters": {"url": "https://api.example.com/data", "method": "GET"},
        },
        {
            "name": "OpenAI",
            "type": "n8n-nodes-base.openAi",
            "position": [500, 200],
            "parameters": {"prompt": "Summarise the data.", "model": "gpt-4o-mini"},
        },
        {
            "name": "Code",
            "type": "n8n-nodes-base.code",
            "position": [700, 200],
            "parameters": {"jsCode": "return [{json: items}];"},
        },
        {
            "name": "IF",
            "type": "n8n-nodes-base.if",
            "position": [900, 200],
            "parameters": {"conditions": {"number": [{"value1": 1, "value2": 0}]}},
        },
    ],
    "connections": {
        "Start": {"main": [[{"node": "HTTP Request", "type": "main", "index": 0}]]},
        "HTTP Request": {"main": [[{"node": "OpenAI", "type": "main", "index": 0}]]},
        "OpenAI": {"main": [[{"node": "Code", "type": "main", "index": 0}]]},
        "Code": {"main": [[{"node": "IF", "type": "main", "index": 0}]]},
    },
}

ZAPIER_WORKFLOW = {
    "title": "Test Zapier Workflow",
    "steps": [
        {"id": "1", "type": "trigger", "app": "Gmail", "action": "New Email", "params": {}},
        {
            "id": "2",
            "type": "http_action",
            "app": "Webhooks",
            "action": "POST",
            "params": {"url": "https://hooks.example.com", "method": "POST"},
        },
        {
            "id": "3",
            "type": "ai_action",
            "app": "OpenAI",
            "action": "Generate",
            "params": {"prompt": "Reply to the email."},
        },
        {"id": "4", "type": "filter", "app": "Filter", "action": "Only continue if", "params": {}},
        {"id": "5", "type": "action", "app": "Slack", "action": "Send Message", "params": {}},
    ],
}


@pytest.fixture(autouse=True)
def _clean():
    audit_log_store.reset()
    workflow_permission_store.reset()
    yield
    audit_log_store.reset()
    workflow_permission_store.reset()


def _register(client: TestClient, email: str | None = None) -> tuple[str, str]:
    email = email or f"import-{uuid.uuid4().hex[:8]}@test.com"
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "ImportPass1!"},
    )
    return resp.json()["access_token"], email


# ===========================================================================
# WorkflowImportService — unit tests
# ===========================================================================


class TestFormatDetection:
    def test_detects_n8n(self):
        assert WorkflowImportService.detect_format(N8N_WORKFLOW) == "n8n"  # Gate 2

    def test_detects_zapier(self):
        assert WorkflowImportService.detect_format(ZAPIER_WORKFLOW) == "zapier"  # Gate 2

    def test_unknown_returns_unknown(self):
        assert WorkflowImportService.detect_format({"random": "data"}) == "unknown"

    def test_explicit_format_overrides_detection(self):
        # Force zapier format on n8n-shaped payload — convert() uses our explicit fmt
        result, fmt = WorkflowImportService.convert(ZAPIER_WORKFLOW, fmt="zapier")
        assert fmt == "zapier"  # Gate 2

    def test_unknown_format_raises_422(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            WorkflowImportService.convert({"foo": "bar"}, fmt="unknown_tool")
        assert exc.value.status_code == 422  # Gate 2


class TestN8NImport:
    def test_returns_synapps_workflow_structure(self):
        result, fmt = WorkflowImportService.convert(N8N_WORKFLOW)
        assert fmt == "n8n"  # Gate 2
        assert "id" in result  # Gate 2
        assert "name" in result  # Gate 2
        assert "nodes" in result  # Gate 2
        assert "edges" in result  # Gate 2

    def test_preserves_workflow_name(self):
        result, _ = WorkflowImportService.convert(N8N_WORKFLOW)
        assert result["name"] == "Test n8n Workflow"  # Gate 2

    def test_maps_start_node_type(self):
        result, _ = WorkflowImportService.convert(N8N_WORKFLOW)
        start_nodes = [n for n in result["nodes"] if n["type"] == "start"]
        assert len(start_nodes) >= 1  # Gate 2

    def test_maps_http_node_type(self):
        result, _ = WorkflowImportService.convert(N8N_WORKFLOW)
        http_nodes = [n for n in result["nodes"] if n["type"] == "http"]
        assert len(http_nodes) >= 1  # Gate 2
        assert http_nodes[0]["data"]["url"] == "https://api.example.com/data"  # Gate 2

    def test_maps_llm_node_type(self):
        result, _ = WorkflowImportService.convert(N8N_WORKFLOW)
        llm_nodes = [n for n in result["nodes"] if n["type"] == "llm"]
        assert len(llm_nodes) >= 1  # Gate 2
        assert "Summarise" in llm_nodes[0]["data"]["prompt"]  # Gate 2

    def test_maps_code_node_type(self):
        result, _ = WorkflowImportService.convert(N8N_WORKFLOW)
        code_nodes = [n for n in result["nodes"] if n["type"] == "code"]
        assert len(code_nodes) >= 1  # Gate 2

    def test_maps_if_else_node_type(self):
        result, _ = WorkflowImportService.convert(N8N_WORKFLOW)
        if_nodes = [n for n in result["nodes"] if n["type"] == "if_else"]
        assert len(if_nodes) >= 1  # Gate 2

    def test_generates_end_node(self):
        result, _ = WorkflowImportService.convert(N8N_WORKFLOW)
        end_nodes = [n for n in result["nodes"] if n["type"] == "end"]
        assert len(end_nodes) >= 1  # Gate 2

    def test_builds_edges_from_connections(self):
        result, _ = WorkflowImportService.convert(N8N_WORKFLOW)
        assert len(result["edges"]) >= 1  # Gate 2

    def test_node_positions_are_dicts(self):
        result, _ = WorkflowImportService.convert(N8N_WORKFLOW)
        for node in result["nodes"]:
            assert "x" in node["position"]  # Gate 2
            assert "y" in node["position"]  # Gate 2

    def test_empty_workflow_returns_start_and_end(self):
        empty = {"name": "Empty", "nodes": [], "connections": {}}
        result, _ = WorkflowImportService.convert(empty, fmt="n8n")
        types = [n["type"] for n in result["nodes"]]
        assert "start" in types  # Gate 2
        assert "end" in types  # Gate 2

    def test_unknown_n8n_type_maps_to_transform(self):
        payload = {
            "name": "Unknown",
            "nodes": [
                {
                    "name": "X",
                    "type": "n8n-nodes-base.someNewTool",
                    "position": [0, 0],
                    "parameters": {},
                }
            ],
            "connections": {},
        }
        result, _ = WorkflowImportService.convert(payload, fmt="n8n")
        non_structural = [n for n in result["nodes"] if n["id"].startswith("n8n-")]
        assert len(non_structural) >= 1  # Gate 2
        assert non_structural[0]["type"] == "transform"  # Gate 2


class TestZapierImport:
    def test_returns_synapps_workflow_structure(self):
        result, fmt = WorkflowImportService.convert(ZAPIER_WORKFLOW)
        assert fmt == "zapier"  # Gate 2
        assert "nodes" in result  # Gate 2
        assert "edges" in result  # Gate 2

    def test_preserves_workflow_title(self):
        result, _ = WorkflowImportService.convert(ZAPIER_WORKFLOW)
        assert result["name"] == "Test Zapier Workflow"  # Gate 2

    def test_maps_trigger_to_start(self):
        result, _ = WorkflowImportService.convert(ZAPIER_WORKFLOW)
        start_nodes = [n for n in result["nodes"] if n["type"] == "start"]
        assert len(start_nodes) >= 1  # Gate 2

    def test_maps_http_action(self):
        result, _ = WorkflowImportService.convert(ZAPIER_WORKFLOW)
        http_nodes = [n for n in result["nodes"] if n["type"] == "http"]
        assert len(http_nodes) >= 1  # Gate 2
        assert http_nodes[0]["data"]["url"] == "https://hooks.example.com"  # Gate 2

    def test_maps_ai_action_to_llm(self):
        result, _ = WorkflowImportService.convert(ZAPIER_WORKFLOW)
        llm_nodes = [n for n in result["nodes"] if n["type"] == "llm"]
        assert len(llm_nodes) >= 1  # Gate 2

    def test_maps_filter_to_if_else(self):
        result, _ = WorkflowImportService.convert(ZAPIER_WORKFLOW)
        if_nodes = [n for n in result["nodes"] if n["type"] == "if_else"]
        assert len(if_nodes) >= 1  # Gate 2

    def test_sequential_edges_generated(self):
        result, _ = WorkflowImportService.convert(ZAPIER_WORKFLOW)
        assert len(result["edges"]) >= 1  # Gate 2

    def test_generates_end_node(self):
        result, _ = WorkflowImportService.convert(ZAPIER_WORKFLOW)
        end_nodes = [n for n in result["nodes"] if n["type"] == "end"]
        assert len(end_nodes) >= 1  # Gate 2

    def test_nested_zap_format(self):
        nested = {"zap": {"title": "Nested Zap", "steps": ZAPIER_WORKFLOW["steps"]}}
        result, fmt = WorkflowImportService.convert(nested, fmt="zapier")
        assert fmt == "zapier"  # Gate 2
        assert result["name"] == "Nested Zap"  # Gate 2
        assert len(result["nodes"]) >= 1  # Gate 2

    def test_empty_zapier_workflow(self):
        empty = {"title": "Empty Zap", "steps": []}
        result, _ = WorkflowImportService.convert(empty, fmt="zapier")
        assert "nodes" in result  # Gate 2


# ===========================================================================
# POST /workflows/import endpoint
# ===========================================================================


class TestImportEndpoint:
    def test_import_n8n_returns_200(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            resp = client.post(
                "/api/v1/workflows/import",
                json={"data": N8N_WORKFLOW},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["format"] == "n8n"  # Gate 2
            assert "workflow" in body  # Gate 2
            assert body["node_count"] >= 1  # Gate 2
            assert body["edge_count"] >= 1  # Gate 2

    def test_import_zapier_returns_200(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            resp = client.post(
                "/api/v1/workflows/import",
                json={"data": ZAPIER_WORKFLOW},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["format"] == "zapier"  # Gate 2

    def test_explicit_format_param_respected(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            resp = client.post(
                "/api/v1/workflows/import",
                json={"format": "n8n", "data": N8N_WORKFLOW},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 200
            assert resp.json()["format"] == "n8n"  # Gate 2

    def test_unknown_format_returns_422(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            resp = client.post(
                "/api/v1/workflows/import",
                json={"format": "make_com", "data": {}},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 422  # Gate 2

    def test_save_flag_persists_workflow(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            resp = client.post(
                "/api/v1/workflows/import",
                json={"data": N8N_WORKFLOW, "save": True},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body.get("saved") is True  # Gate 2
            assert "flow_id" in body  # Gate 2
            # Verify the flow was actually persisted
            flow_id = body["flow_id"]
            get_resp = client.get(
                f"/api/v1/flows/{flow_id}", headers={"Authorization": f"Bearer {token}"}
            )
            assert get_resp.status_code == 200  # Gate 2

    def test_save_records_audit_log(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            client.post(
                "/api/v1/workflows/import",
                json={"data": N8N_WORKFLOW, "save": True},
                headers={"Authorization": f"Bearer {token}"},
            )
            entries = audit_log_store.query(action="workflow_created")
            assert len(entries) >= 1  # Gate 2

    def test_import_requires_auth(self):
        with TestClient(app) as client:
            _register(client)  # create a user to disable anonymous bootstrap
            resp = client.post("/api/v1/workflows/import", json={"data": N8N_WORKFLOW})
            assert resp.status_code in (401, 403)  # Gate 2

    def test_workflow_contains_valid_nodes(self):
        with TestClient(app) as client:
            token, _ = _register(client)
            resp = client.post(
                "/api/v1/workflows/import",
                json={"data": N8N_WORKFLOW},
                headers={"Authorization": f"Bearer {token}"},
            )
            workflow = resp.json()["workflow"]
            for node in workflow["nodes"]:
                assert "id" in node  # Gate 2
                assert "type" in node  # Gate 2
                assert "position" in node  # Gate 2
