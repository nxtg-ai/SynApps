"""Tests for the SynApps Python SDK (apps/sdk/synapps/).

CRUCIBLE Gates 2 and 5 apply.

Import note
-----------
The repository has a root-level ``synapps/`` package (providers etc.) that
``main.py`` imports.  The SDK lives in ``apps/sdk/synapps/`` under the same
top-level name.  We load the SDK via importlib under the alias ``synapps_sdk``
so we never shadow or evict the root package.
"""
import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Load SDK as synapps_sdk (importlib alias — no sys.path mutation)
# ---------------------------------------------------------------------------
_SDK_DIR = Path(__file__).resolve().parent.parent.parent / "sdk" / "synapps"


_NS = "_synapps_d129"  # private namespace — avoids collision with root synapps_sdk package


def _load_sdk_module(name: str, filename: str):
    """Load a module from the SDK directory under the _synapps_d129.* namespace."""
    full_name = f"{_NS}.{name}" if name else _NS
    if full_name in sys.modules:
        return sys.modules[full_name]
    path = _SDK_DIR / filename
    spec = importlib.util.spec_from_file_location(full_name, path)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    sys.modules[full_name] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


# Register the package first so sub-module relative imports resolve
_pkg = types.ModuleType(_NS)
_pkg.__path__ = [str(_SDK_DIR)]  # type: ignore[attr-defined]
if _NS not in sys.modules:
    sys.modules[_NS] = _pkg

_models_mod = _load_sdk_module("models", "models.py")
_client_mod = _load_sdk_module("client", "client.py")
_async_mod = _load_sdk_module("async_client", "async_client.py")

Client = _client_mod.Client
AsyncClient = _async_mod.AsyncClient
Workflow = _models_mod.Workflow
WorkflowRun = _models_mod.WorkflowRun
ExecutionLog = _models_mod.ExecutionLog
MarketplaceListing = _models_mod.MarketplaceListing


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_sync_response(data: object) -> MagicMock:
    """Return a mock httpx response whose .json() returns *data*."""
    resp = MagicMock()
    resp.json.return_value = data
    resp.raise_for_status = MagicMock()
    return resp


def _make_async_http_mock(get_data: object = None, post_data: object = None) -> AsyncMock:
    """Return a mock for httpx.AsyncClient used as async context manager."""
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()

    mock_http = AsyncMock()
    mock_http.__aenter__ = AsyncMock(return_value=mock_http)
    mock_http.__aexit__ = AsyncMock(return_value=None)

    if get_data is not None:
        get_resp = MagicMock()
        get_resp.json.return_value = get_data
        get_resp.raise_for_status = MagicMock()
        mock_http.get = AsyncMock(return_value=get_resp)

    if post_data is not None:
        post_resp = MagicMock()
        post_resp.json.return_value = post_data
        post_resp.raise_for_status = MagicMock()
        mock_http.post = AsyncMock(return_value=post_resp)

    return mock_http


# ---------------------------------------------------------------------------
# TestSyncClientModels
# ---------------------------------------------------------------------------

class TestSyncClientModels:
    def test_workflow_model(self):
        wf = Workflow(id="x", name="y")
        assert wf.id == "x"
        assert wf.name == "y"
        assert wf.nodes == []
        assert wf.edges == []

    def test_workflow_run_model(self):
        run = WorkflowRun(run_id="r", status="success")
        assert run.run_id == "r"
        assert run.status == "success"
        assert run.output == {}
        assert run.error is None

    def test_execution_log_model(self):
        log = ExecutionLog(
            node_id="n",
            event="node_started",
            timestamp="2026-01-01T00:00:00",
        )
        assert log.node_id == "n"
        assert log.event == "node_started"
        assert log.timestamp == "2026-01-01T00:00:00"
        assert log.input == {}
        assert log.output == {}
        assert log.duration_ms is None
        assert log.error is None

    def test_marketplace_listing_model(self):
        listing = MarketplaceListing(id="m", name="Test")
        assert listing.id == "m"
        assert listing.name == "Test"
        assert listing.description == ""
        assert listing.category == ""
        assert listing.tags == []
        assert listing.install_count == 0

    def test_models_from_dict(self):
        wf = Workflow.model_validate({"id": "x", "name": "y", "nodes": [], "edges": []})
        assert wf.id == "x"
        assert wf.name == "y"
        assert isinstance(wf.nodes, list)
        assert isinstance(wf.edges, list)


# ---------------------------------------------------------------------------
# TestSyncClientMethods
# ---------------------------------------------------------------------------

class TestSyncClientMethods:
    def setup_method(self):
        self.client = Client(base_url="http://testserver", token="tok123")

    def test_list_workflows(self):
        flows = [
            {"id": "1", "name": "Flow A", "nodes": [], "edges": []},
            {"id": "2", "name": "Flow B", "nodes": [], "edges": []},
        ]
        with patch("httpx.get", return_value=_make_sync_response(flows)):
            result = self.client.list_workflows()
        assert isinstance(result, list)
        assert len(result) >= 1  # Gate 2: confirm data was not silently lost
        assert all(isinstance(w, Workflow) for w in result)
        assert result[0].id == "1"

    def test_get_workflow(self):
        flow_data = {"id": "abc", "name": "My Flow", "nodes": [], "edges": []}
        with patch("httpx.get", return_value=_make_sync_response(flow_data)):
            result = self.client.get_workflow("abc")
        assert isinstance(result, Workflow)
        assert result.id == "abc"
        assert result.name == "My Flow"

    def test_create_workflow(self):
        post_resp = {"id": "new1", "message": "created"}
        get_resp = {"id": "new1", "name": "New Flow", "nodes": [], "edges": []}
        with patch("httpx.post", return_value=_make_sync_response(post_resp)), \
             patch("httpx.get", return_value=_make_sync_response(get_resp)):
            result = self.client.create_workflow("New Flow")
        assert isinstance(result, Workflow)
        assert result.id == "new1"
        assert result.name == "New Flow"

    def test_run_workflow(self):
        run_resp = {"run_id": "r1", "status": "started", "output": {}}
        with patch("httpx.post", return_value=_make_sync_response(run_resp)):
            result = self.client.run("wf1")
        assert isinstance(result, WorkflowRun)
        assert result.run_id == "r1"
        assert result.status == "started"

    def test_run_with_input(self):
        run_resp = {"run_id": "r2", "status": "started", "output": {}}
        captured = {}

        def fake_post(url, headers, json, timeout):
            captured["body"] = json
            return _make_sync_response(run_resp)

        with patch("httpx.post", side_effect=fake_post):
            result = self.client.run("wf2", input={"key": "value"})

        assert result.run_id == "r2"
        assert captured["body"]["input"] == {"key": "value"}

    def test_get_logs(self):
        logs = [
            {
                "node_id": "n1",
                "event": "node_started",
                "timestamp": "2026-01-01T00:00:00",
                "input": {},
                "output": {},
            },
            {
                "node_id": "n1",
                "event": "node_completed",
                "timestamp": "2026-01-01T00:00:01",
                "input": {},
                "output": {"result": "ok"},
                "duration_ms": 123.4,
            },
        ]
        with patch("httpx.get", return_value=_make_sync_response(logs)):
            result = self.client.get_logs("exec1")
        assert isinstance(result, list)
        assert len(result) >= 1  # Gate 2: confirm data was not silently lost
        assert all(isinstance(entry, ExecutionLog) for entry in result)
        assert result[0].node_id == "n1"

    def test_search_marketplace(self):
        marketplace_data = {
            "items": [
                {
                    "id": "m1",
                    "name": "GPT Node",
                    "description": "OpenAI node",
                    "category": "ai",
                    "tags": ["openai"],
                    "install_count": 500,
                }
            ]
        }
        with patch("httpx.get", return_value=_make_sync_response(marketplace_data)):
            result = self.client.search_marketplace("gpt")
        assert isinstance(result, list)
        assert len(result) >= 1  # Gate 2: confirm data was not silently lost
        assert isinstance(result[0], MarketplaceListing)
        assert result[0].id == "m1"

    def test_get_analytics(self):
        analytics_data = {"workflow_id": "wf1", "total_runs": 42, "success_rate": 0.95}
        with patch("httpx.get", return_value=_make_sync_response(analytics_data)):
            result = self.client.get_analytics("wf1")
        assert isinstance(result, dict)
        assert result["total_runs"] == 42

    def test_get_analytics_dashboard(self):
        dashboard_data = {"total_workflows": 10, "total_runs": 200, "active_users": 5}
        with patch("httpx.get", return_value=_make_sync_response(dashboard_data)):
            result = self.client.get_analytics_dashboard()
        assert isinstance(result, dict)
        assert result["total_workflows"] == 10


# ---------------------------------------------------------------------------
# TestAsyncClientMethods
# ---------------------------------------------------------------------------

class TestAsyncClientMethods:
    def setup_method(self):
        self.client = AsyncClient(base_url="http://testserver", token="tok456")

    @pytest.mark.asyncio
    async def test_async_list_workflows(self):
        flows = [
            {"id": "a1", "name": "Async Flow 1", "nodes": [], "edges": []},
            {"id": "a2", "name": "Async Flow 2", "nodes": [], "edges": []},
        ]
        mock_http = _make_async_http_mock(get_data=flows)
        with patch("httpx.AsyncClient", return_value=mock_http):
            result = await self.client.list_workflows()
        assert isinstance(result, list)
        assert len(result) >= 1  # Gate 2: confirm data was not silently lost
        assert all(isinstance(w, Workflow) for w in result)
        assert result[0].id == "a1"

    @pytest.mark.asyncio
    async def test_async_run_workflow(self):
        run_resp = {"run_id": "ar1", "status": "started", "output": {}}
        mock_http = _make_async_http_mock(post_data=run_resp)
        with patch("httpx.AsyncClient", return_value=mock_http):
            result = await self.client.run("wf_async")
        assert isinstance(result, WorkflowRun)
        assert result.run_id == "ar1"
        assert result.status == "started"

    @pytest.mark.asyncio
    async def test_async_get_logs(self):
        logs = [
            {
                "node_id": "n2",
                "event": "node_started",
                "timestamp": "2026-03-19T10:00:00",
                "input": {},
                "output": {},
            }
        ]
        mock_http = _make_async_http_mock(get_data=logs)
        with patch("httpx.AsyncClient", return_value=mock_http):
            result = await self.client.get_logs("exec_async")
        assert isinstance(result, list)
        assert len(result) >= 1  # Gate 2: confirm data was not silently lost
        assert isinstance(result[0], ExecutionLog)
        assert result[0].node_id == "n2"

    @pytest.mark.asyncio
    async def test_async_search_marketplace(self):
        marketplace_data = {
            "items": [
                {
                    "id": "am1",
                    "name": "Async Node",
                    "description": "An async-capable node",
                    "category": "utility",
                    "tags": ["async"],
                    "install_count": 100,
                }
            ]
        }
        mock_http = _make_async_http_mock(get_data=marketplace_data)
        with patch("httpx.AsyncClient", return_value=mock_http):
            result = await self.client.search_marketplace("async")
        assert isinstance(result, list)
        assert len(result) >= 1  # Gate 2: confirm data was not silently lost
        assert result[0].name == "Async Node"

    @pytest.mark.asyncio
    async def test_async_create_workflow(self):
        post_resp = {"id": "anew1", "message": "created"}
        get_resp = {"id": "anew1", "name": "Async New Flow", "nodes": [], "edges": []}

        # create_workflow calls _post then _get — two separate AsyncClient instantiations
        call_count = 0
        post_mock = _make_async_http_mock(post_data=post_resp)
        get_mock = _make_async_http_mock(get_data=get_resp)

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return post_mock if call_count == 1 else get_mock

        with patch("httpx.AsyncClient", side_effect=side_effect):
            result = await self.client.create_workflow("Async New Flow")
        assert isinstance(result, Workflow)
        assert result.id == "anew1"
        assert result.name == "Async New Flow"

    @pytest.mark.asyncio
    async def test_async_get_analytics_dashboard(self):
        dashboard_data = {"total_workflows": 7, "total_runs": 150}
        mock_http = _make_async_http_mock(get_data=dashboard_data)
        with patch("httpx.AsyncClient", return_value=mock_http):
            result = await self.client.get_analytics_dashboard()
        assert isinstance(result, dict)
        assert result["total_workflows"] == 7


# ---------------------------------------------------------------------------
# TestClientAuth
# ---------------------------------------------------------------------------

class TestClientAuth:
    def test_auth_header_set(self):
        client = Client(base_url="http://testserver", token="secret_token")
        headers = client._headers
        assert "Authorization" in headers
        assert headers["Authorization"] == "Bearer secret_token"

    def test_no_auth_header(self):
        client = Client(base_url="http://testserver")
        headers = client._headers
        assert "Authorization" not in headers
        assert headers["Content-Type"] == "application/json"
