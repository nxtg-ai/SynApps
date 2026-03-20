"""
DIRECTIVE-NXTG-20260319-130: E2E Integration Test — SDK + CLI + Full Platform

Tests the full SynApps platform end-to-end:
  create workflow via SDK → run via CLI → check analytics → verify audit trail

Test layout:
  - TestSDKWorkflow (4 tests)  — SDK Client with mocked httpx
  - TestCLIWorkflow  (4 tests)  — CLI commands via Click CliRunner with mocked httpx
  - TestFullPlatformE2E (2 tests) — FastAPI TestClient (no mocking; real DB)

CRUCIBLE Gates 2 and 5 apply throughout.

Import note
-----------
The repository contains a root-level ``synapps/`` package (providers, etc.) that
``apps/orchestrator/main.py`` imports at module level.  The SDK lives in
``apps/sdk/synapps/`` under the same top-level name.  To avoid shadowing one
with the other we load the SDK as a *synthetic* package called ``synapps_sdk``
and the CLI as ``synapps_cli`` using importlib — no sys.path mutation required.
"""

import importlib.util
import sys
import time
import types
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from apps.orchestrator.main import app

# ---------------------------------------------------------------------------
# Load the SDK under the alias ``_synapps_d129`` to avoid shadowing the root
# ``synapps`` package that main.py depends on, and to avoid colliding with
# the root-level ``synapps-sdk`` package (which exports SynApps/AsyncSynApps).
# ---------------------------------------------------------------------------

_SDK_DIR = Path(__file__).resolve().parent.parent.parent / "sdk" / "synapps"
_CLI_DIR = Path(__file__).resolve().parent.parent.parent / "cli" / "synapps_cli"


def _load_package(pkg_name: str, pkg_dir: Path, modules: list[str]) -> None:
    """Register *pkg_dir* as the importlib package *pkg_name* with *modules*."""
    if pkg_name in sys.modules:
        return  # already loaded (e.g. when the full test suite runs)
    pkg = types.ModuleType(pkg_name)
    pkg.__path__ = [str(pkg_dir)]  # type: ignore[attr-defined]
    pkg.__package__ = pkg_name
    sys.modules[pkg_name] = pkg
    for mod_name in modules:
        full_name = f"{pkg_name}.{mod_name}"
        if full_name in sys.modules:
            continue  # already loaded
        spec = importlib.util.spec_from_file_location(
            full_name, pkg_dir / f"{mod_name}.py"
        )
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot find {full_name} in {pkg_dir}")
        mod = importlib.util.module_from_spec(spec)
        mod.__package__ = pkg_name
        sys.modules[full_name] = mod
        spec.loader.exec_module(mod)  # type: ignore[union-attr]


_D129_NS = "_synapps_d129"  # private namespace — avoids collision with root synapps_sdk package
_load_package(_D129_NS, _SDK_DIR, ["models", "client", "async_client"])
_load_package("synapps_cli", _CLI_DIR, ["config", "main"])

from _synapps_d129.client import Client  # noqa: E402
from _synapps_d129.models import ExecutionLog, MarketplaceListing, Workflow, WorkflowRun  # noqa: E402
from synapps_cli.main import cli  # noqa: E402


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_sync_response(data: object) -> MagicMock:
    """Return a mock httpx response whose .json() returns *data*."""
    resp = MagicMock()
    resp.json.return_value = data
    resp.raise_for_status = MagicMock()
    return resp


def _mock_response(json_data, status_code: int = 200) -> MagicMock:
    """Build a mock httpx.Response-like object (CLI-style)."""
    import json as _json

    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.json.return_value = json_data
    mock_resp.text = _json.dumps(json_data)
    if status_code >= 400:
        from httpx import HTTPStatusError, Request, Response

        request = MagicMock(spec=Request)
        response = MagicMock(spec=Response)
        response.status_code = status_code
        response.text = _json.dumps(json_data)
        mock_resp.raise_for_status.side_effect = HTTPStatusError(
            message=str(status_code), request=request, response=response
        )
    else:
        mock_resp.raise_for_status.return_value = None
    return mock_resp


def _get_token(client: TestClient) -> tuple[str, str]:
    """Register a new user and return (access_token, email)."""
    email = f"e2e-sdk-cli-{uuid.uuid4().hex[:8]}@test.com"
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "E2ePass123!"},
    )
    assert resp.status_code in (200, 201), f"Registration failed: {resp.text}"
    return resp.json()["access_token"], email


# ---------------------------------------------------------------------------
# Minimal flow definition used by the platform E2E tests
# ---------------------------------------------------------------------------

_SIMPLE_FLOW = {
    "name": "SDK-CLI E2E Flow",
    "nodes": [
        {
            "id": "start",
            "type": "transform",
            "position": {"x": 100, "y": 100},
            "data": {"label": "Start", "expression": "input"},
        },
        {
            "id": "end",
            "type": "end",
            "position": {"x": 100, "y": 250},
            "data": {"label": "End"},
        },
    ],
    "edges": [{"id": "s-e", "source": "start", "target": "end"}],
}


# ===========================================================================
# Class TestSDKWorkflow — 4 tests — simulates SDK operations via mocked httpx
# ===========================================================================


class TestSDKWorkflow:
    """Simulate what the SynApps Python SDK does, verifying response parsing."""

    def setup_method(self):
        self.client = Client(base_url="http://testserver", token="test-token")

    # ------------------------------------------------------------------
    # 1. list_workflows parses the API response into Workflow objects
    # ------------------------------------------------------------------

    def test_sdk_list_workflows(self):
        """SDK parses a realistic /flows response into Workflow objects."""
        flows = [
            {"id": "flow-sdk-1", "name": "Compliance Pipeline", "nodes": [], "edges": []},
            {"id": "flow-sdk-2", "name": "Data Enrichment", "nodes": [], "edges": []},
        ]
        with patch("httpx.get", return_value=_make_sync_response(flows)):
            result = self.client.list_workflows()

        assert isinstance(result, list)
        assert len(result) >= 1  # Gate 2: data must not be silently lost
        assert all(isinstance(w, Workflow) for w in result)
        assert result[0].id == "flow-sdk-1"
        assert result[0].name == "Compliance Pipeline"

    # ------------------------------------------------------------------
    # 2. create_and_run chains POST /flows → GET /flows/{id} → POST run
    # ------------------------------------------------------------------

    def test_sdk_create_and_run(self):
        """SDK create + run returns a WorkflowRun with correct run_id."""
        post_flow_resp = {"id": "flow-1", "message": "created"}
        get_flow_resp = {
            "id": "flow-1",
            "name": "SDK Created Flow",
            "nodes": [],
            "edges": [],
        }
        run_resp = {"run_id": "run-1", "status": "started", "output": {}}

        with (
            patch("httpx.post", return_value=_make_sync_response(post_flow_resp)),
            patch("httpx.get", return_value=_make_sync_response(get_flow_resp)),
        ):
            workflow = self.client.create_workflow("SDK Created Flow")

        assert isinstance(workflow, Workflow)
        assert workflow.id == "flow-1"

        with patch("httpx.post", return_value=_make_sync_response(run_resp)):
            run = self.client.run("flow-1")

        assert isinstance(run, WorkflowRun)  # Gate 2: object type confirmed
        assert run.run_id == "run-1"
        assert run.status == "started"

    # ------------------------------------------------------------------
    # 3. get_logs parses log entry list into ExecutionLog objects
    # ------------------------------------------------------------------

    def test_sdk_get_logs(self):
        """SDK get_logs returns a non-empty list of ExecutionLog instances."""
        logs = [
            {
                "node_id": "node-transform-1",
                "event": "node_started",
                "timestamp": "2026-03-19T10:00:00Z",
                "input": {"text": "hello"},
                "output": {},
            },
            {
                "node_id": "node-transform-1",
                "event": "node_completed",
                "timestamp": "2026-03-19T10:00:01Z",
                "input": {"text": "hello"},
                "output": {"result": "HELLO"},
                "duration_ms": 45.2,
            },
        ]
        with patch("httpx.get", return_value=_make_sync_response(logs)):
            result = self.client.get_logs("run-1")

        assert isinstance(result, list)
        assert len(result) >= 1  # Gate 2: log entries must not be silently lost
        assert all(isinstance(entry, ExecutionLog) for entry in result)
        assert result[0].node_id == "node-transform-1"
        assert result[0].event == "node_started"

    # ------------------------------------------------------------------
    # 4. search_marketplace returns MarketplaceListing objects
    # ------------------------------------------------------------------

    def test_sdk_search_marketplace(self):
        """SDK search_marketplace returns non-empty list of MarketplaceListing."""
        marketplace_data = {
            "items": [
                {
                    "id": "listing-compliance-1",
                    "name": "Compliance Audit Template",
                    "description": "Automate SOC-2 audit log collection.",
                    "category": "compliance",
                    "tags": ["audit", "soc2", "compliance"],
                    "install_count": 128,
                },
                {
                    "id": "listing-compliance-2",
                    "name": "GDPR Data Flow Scanner",
                    "description": "Scan data flows for GDPR compliance.",
                    "category": "compliance",
                    "tags": ["gdpr", "privacy"],
                    "install_count": 74,
                },
            ]
        }
        with patch("httpx.get", return_value=_make_sync_response(marketplace_data)):
            result = self.client.search_marketplace("compliance")

        assert isinstance(result, list)
        assert len(result) >= 1  # Gate 2: marketplace items must not be silently lost
        assert all(isinstance(item, MarketplaceListing) for item in result)
        assert result[0].id == "listing-compliance-1"
        assert result[0].name == "Compliance Audit Template"


# ===========================================================================
# Class TestCLIWorkflow — 4 tests — simulates CLI operations
# ===========================================================================


class TestCLIWorkflow:
    """Simulate what the SynApps CLI does, using Click CliRunner + mocked httpx."""

    # env injected for every invocation
    _CLI_ENV = {
        "SYNAPPS_URL": "http://localhost:8000",
        "SYNAPPS_TOKEN": "test-token",
    }

    # ------------------------------------------------------------------
    # 1. synapps list — table shows both flow IDs
    # ------------------------------------------------------------------

    def test_cli_list(self):
        """CLI list renders a table containing both flow IDs and names."""
        flows = [
            {"id": "flow-cli-aaa", "name": "Alpha Pipeline", "nodes": [1, 2, 3]},
            {"id": "flow-cli-bbb", "name": "Beta Pipeline", "nodes": []},
        ]
        mock_resp = _mock_response(flows)
        runner = CliRunner()
        with patch("httpx.get", return_value=mock_resp):
            result = runner.invoke(cli, ["list"], env=self._CLI_ENV)

        assert result.exit_code == 0, f"CLI exited non-zero: {result.output}"
        assert "flow-cli-aaa" in result.output
        assert "flow-cli-bbb" in result.output
        assert "Alpha Pipeline" in result.output
        assert "Beta Pipeline" in result.output

    # ------------------------------------------------------------------
    # 2. synapps run — run_id appears in output
    # ------------------------------------------------------------------

    def test_cli_run(self):
        """CLI run command prints the run_id returned by the server."""
        payload = {"run_id": "run-cli-xyz-789", "status": "queued"}
        mock_resp = _mock_response(payload)
        runner = CliRunner()
        with patch("httpx.post", return_value=mock_resp):
            result = runner.invoke(cli, ["run", "flow-cli-aaa"], env=self._CLI_ENV)

        assert result.exit_code == 0, f"CLI exited non-zero: {result.output}"
        assert "run-cli-xyz-789" in result.output

    # ------------------------------------------------------------------
    # 3. synapps logs — node names appear in output
    # ------------------------------------------------------------------

    def test_cli_logs(self):
        """CLI logs command renders node IDs and events from the server response."""
        logs = [
            {
                "timestamp": "2026-03-19T12:00:00Z",
                "node_id": "node-llm-audit",
                "event": "started",
            },
            {
                "timestamp": "2026-03-19T12:00:02Z",
                "node_id": "node-llm-audit",
                "event": "completed",
            },
        ]
        mock_resp = _mock_response(logs)
        runner = CliRunner()
        with patch("httpx.get", return_value=mock_resp):
            result = runner.invoke(cli, ["logs", "run-456"], env=self._CLI_ENV)

        assert result.exit_code == 0, f"CLI exited non-zero: {result.output}"
        assert "node-llm-audit" in result.output
        assert "started" in result.output
        assert "completed" in result.output

    # ------------------------------------------------------------------
    # 4. synapps marketplace search compliance — listing name in output
    # ------------------------------------------------------------------

    def test_cli_marketplace_search(self):
        """CLI marketplace search renders listing names in the output table."""
        data = {
            "items": [
                {
                    "id": "tpl-compliance-001",
                    "name": "Compliance Audit Kit",
                    "category": "compliance",
                },
                {
                    "id": "tpl-compliance-002",
                    "name": "HIPAA Log Validator",
                    "category": "compliance",
                },
            ],
            "total": 2,
        }
        mock_resp = _mock_response(data)
        runner = CliRunner()
        with patch("httpx.get", return_value=mock_resp):
            result = runner.invoke(
                cli, ["marketplace", "search", "compliance"], env=self._CLI_ENV
            )

        assert result.exit_code == 0, f"CLI exited non-zero: {result.output}"
        assert "Compliance Audit Kit" in result.output
        assert "HIPAA Log Validator" in result.output


# ===========================================================================
# Class TestFullPlatformE2E — 2 tests — real FastAPI TestClient, no mocking
# ===========================================================================


class TestFullPlatformE2E:
    """Full platform tests using the real FastAPI app and in-memory SQLite."""

    # ------------------------------------------------------------------
    # 1. create → run → check audit trail for workflow_run_started
    # ------------------------------------------------------------------

    def test_create_workflow_run_and_check_audit(self):
        """Register user → create flow → run flow → audit log shows workflow_run_started."""
        with TestClient(app) as client:
            token, email = _get_token(client)
            auth = {"Authorization": f"Bearer {token}"}

            # Build a unique flow ID to isolate this test run
            flow_id = f"e2e-audit-{uuid.uuid4().hex[:8]}"
            flow = {**_SIMPLE_FLOW, "id": flow_id}

            # Create the flow
            resp = client.post("/api/v1/flows", json=flow, headers=auth)
            assert resp.status_code == 201, f"Flow creation failed: {resp.text}"

            # Run the flow
            resp = client.post(
                f"/api/v1/flows/{flow_id}/runs", json={}, headers=auth
            )
            assert resp.status_code == 202, f"Run failed: {resp.text}"
            run_data = resp.json()
            assert "run_id" in run_data  # Gate 2: run_id must be present

            # Fetch audit trail filtered by actor email
            resp = client.get(
                "/api/v1/audit",
                params={"actor": email},
                headers=auth,
            )
            assert resp.status_code == 200, f"Audit fetch failed: {resp.text}"
            audit_body = resp.json()
            assert "entries" in audit_body

            audit_entries = audit_body["entries"]
            assert isinstance(audit_entries, list)
            assert len(audit_entries) >= 1  # Gate 2: audit must have recorded something

            # At least one entry must be "workflow_run_started" for our flow
            run_started_entries = [
                e
                for e in audit_entries
                if e.get("action") == "workflow_run_started"
                and e.get("resource_id") == flow_id
            ]
            assert len(run_started_entries) >= 1, (
                f"No 'workflow_run_started' entry found for flow {flow_id} "
                f"in audit trail. Entries: {audit_entries}"
            )
            # Allow background execution task to finish before DB teardown
            time.sleep(0.3)

    # ------------------------------------------------------------------
    # 2. workflow lifecycle analytics — two runs, run_count >= 1
    # ------------------------------------------------------------------

    def test_workflow_lifecycle_analytics(self):
        """Register user → create flow → run twice → analytics shows run_count >= 1."""
        with TestClient(app) as client:
            token, email = _get_token(client)
            auth = {"Authorization": f"Bearer {token}"}

            flow_id = f"e2e-analytics-{uuid.uuid4().hex[:8]}"
            flow = {**_SIMPLE_FLOW, "id": flow_id}

            # Create the flow
            resp = client.post("/api/v1/flows", json=flow, headers=auth)
            assert resp.status_code == 201, f"Flow creation failed: {resp.text}"

            # Run the flow twice
            for run_num in range(1, 3):
                resp = client.post(
                    f"/api/v1/flows/{flow_id}/runs", json={}, headers=auth
                )
                assert resp.status_code == 202, f"Run {run_num} failed: {resp.text}"
                assert "run_id" in resp.json()  # Gate 2: run_id present each time

            # Fetch workflow-level analytics
            resp = client.get(
                "/api/v1/analytics/workflows",
                params={"flow_id": flow_id},
                headers=auth,
            )
            assert resp.status_code == 200, f"Analytics fetch failed: {resp.text}"
            body = resp.json()

            assert "workflows" in body
            assert isinstance(body["workflows"], list)
            assert len(body["workflows"]) >= 1  # Gate 2: our flow must appear

            # Locate our flow's analytics entry
            flow_analytics = next(
                (w for w in body["workflows"] if w.get("flow_id") == flow_id),
                None,
            )
            assert flow_analytics is not None, (
                f"Flow {flow_id} not found in analytics. Response: {body}"
            )
            assert flow_analytics["run_count"] >= 1, (
                f"Expected run_count >= 1, got: {flow_analytics['run_count']}"
            )
            # Allow background execution tasks to finish before DB teardown
            time.sleep(0.3)
