"""Tests for the SynApps CLI package.

Imports the CLI modules via sys.path manipulation so the test suite can run
from the repo root without installing the package.
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

# Make synapps_cli importable from the repo root test runner
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "cli"))

from synapps_cli.config import DEFAULT_URL, get_config  # noqa: E402
from synapps_cli.main import cli  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_response(json_data, status_code=200):
    """Build a mock httpx.Response-like object."""
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.json.return_value = json_data
    mock_resp.text = json.dumps(json_data)
    if status_code >= 400:
        from httpx import HTTPStatusError, Request, Response
        # Create a real HTTPStatusError so raise_for_status raises it
        request = MagicMock(spec=Request)
        response = MagicMock(spec=Response)
        response.status_code = status_code
        response.text = json.dumps(json_data)
        mock_resp.raise_for_status.side_effect = HTTPStatusError(
            message=f"{status_code}",
            request=request,
            response=response,
        )
    else:
        mock_resp.raise_for_status.return_value = None
    return mock_resp


# ---------------------------------------------------------------------------
# TestCLIConfig
# ---------------------------------------------------------------------------

class TestCLIConfig:
    def test_default_url(self, monkeypatch):
        """get_config() returns DEFAULT_URL when no env vars or config file."""
        monkeypatch.delenv("SYNAPPS_URL", raising=False)
        monkeypatch.delenv("SYNAPPS_TOKEN", raising=False)
        # Patch CONFIG_PATH to a non-existent path so file branch is skipped
        with patch("synapps_cli.config.CONFIG_PATH", Path("/nonexistent/__synapps_test.json")):
            cfg = get_config()
        assert cfg["url"] == DEFAULT_URL

    def test_env_override(self, monkeypatch):
        """SYNAPPS_URL env var overrides the default URL."""
        monkeypatch.setenv("SYNAPPS_URL", "https://api.example.com/")
        monkeypatch.delenv("SYNAPPS_TOKEN", raising=False)
        with patch("synapps_cli.config.CONFIG_PATH", Path("/nonexistent/__synapps_test.json")):
            cfg = get_config()
        # Trailing slash should be stripped
        assert cfg["url"] == "https://api.example.com"

    def test_token_from_env(self, monkeypatch):
        """SYNAPPS_TOKEN env var sets the token in config."""
        monkeypatch.setenv("SYNAPPS_TOKEN", "my-secret-token")
        monkeypatch.delenv("SYNAPPS_URL", raising=False)
        with patch("synapps_cli.config.CONFIG_PATH", Path("/nonexistent/__synapps_test.json")):
            cfg = get_config()
        assert cfg["token"] == "my-secret-token"


# ---------------------------------------------------------------------------
# TestListCommand
# ---------------------------------------------------------------------------

class TestListCommand:
    def test_list_shows_table(self):
        """Mock GET /flows returning 2 flows — both IDs must appear in output."""
        runner = CliRunner()
        flows = [
            {"id": "flow-aaa-111", "name": "Alpha Flow", "nodes": [1, 2, 3]},
            {"id": "flow-bbb-222", "name": "Beta Flow", "nodes": []},
        ]
        mock_resp = _mock_response(flows)
        with patch("httpx.get", return_value=mock_resp):
            result = runner.invoke(cli, ["list"])
        assert result.exit_code == 0
        assert "flow-aaa-111" in result.output
        assert "flow-bbb-222" in result.output
        assert "Alpha Flow" in result.output
        assert "Beta Flow" in result.output
        # Node counts
        assert "3" in result.output
        assert "0" in result.output

    def test_list_json_flag(self):
        """With --json, output must be parseable JSON matching the server response."""
        runner = CliRunner()
        flows = [{"id": "flow-json-1", "name": "JSON Flow", "nodes": []}]
        mock_resp = _mock_response(flows)
        with patch("httpx.get", return_value=mock_resp):
            result = runner.invoke(cli, ["list", "--json"])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert isinstance(parsed, list)
        assert len(parsed) >= 1
        assert parsed[0]["id"] == "flow-json-1"

    def test_list_empty(self):
        """Empty flow list from server → 'No workflows found.' message."""
        runner = CliRunner()
        mock_resp = _mock_response([])
        with patch("httpx.get", return_value=mock_resp):
            result = runner.invoke(cli, ["list"])
        assert result.exit_code == 0
        assert "No workflows found." in result.output

    def test_list_http_error(self):
        """401 HTTP error → error message printed, exit code 1."""
        runner = CliRunner()
        mock_resp = _mock_response({"detail": "Unauthorized"}, status_code=401)
        with patch("httpx.get", return_value=mock_resp):
            result = runner.invoke(cli, ["list"])
        assert result.exit_code == 1
        assert "Error:" in result.output

    def test_list_connection_error(self):
        """Network RequestError → 'Connection error' message, exit code 1."""
        runner = CliRunner()
        import httpx as _httpx
        with patch("httpx.get", side_effect=_httpx.ConnectError("refused")):
            result = runner.invoke(cli, ["list"])
        assert result.exit_code == 1
        assert "Connection error" in result.output


# ---------------------------------------------------------------------------
# TestRunCommand
# ---------------------------------------------------------------------------

class TestRunCommand:
    def test_run_success(self):
        """Mock POST returns run_id — must be printed with status."""
        runner = CliRunner()
        payload = {"run_id": "run-xyz-999", "status": "queued"}
        mock_resp = _mock_response(payload)
        with patch("httpx.post", return_value=mock_resp):
            result = runner.invoke(cli, ["run", "flow-aaa-111"])
        assert result.exit_code == 0
        assert "run-xyz-999" in result.output
        assert "queued" in result.output

    def test_run_invalid_json(self):
        """--input with invalid JSON → error message, exit code 1 (no HTTP call made)."""
        runner = CliRunner()
        with patch("httpx.post") as mock_post:
            result = runner.invoke(cli, ["run", "flow-aaa-111", "--input", "not-json{{"])
        assert result.exit_code == 1
        assert "Invalid --input JSON" in result.output
        mock_post.assert_not_called()

    def test_run_http_error(self):
        """404 HTTP error during run → error message, exit code 1."""
        runner = CliRunner()
        mock_resp = _mock_response({"detail": "Not Found"}, status_code=404)
        with patch("httpx.post", return_value=mock_resp):
            result = runner.invoke(cli, ["run", "missing-flow"])
        assert result.exit_code == 1
        assert "Error:" in result.output

    def test_run_with_input(self):
        """--input JSON payload is correctly forwarded to the POST body."""
        runner = CliRunner()
        payload = {"run_id": "run-input-test", "status": "running"}
        mock_resp = _mock_response(payload)
        captured_kwargs = {}

        def fake_post(url, **kwargs):
            captured_kwargs.update(kwargs)
            return mock_resp

        with patch("httpx.post", side_effect=fake_post):
            result = runner.invoke(cli, ["run", "flow-aaa-111", "--input", '{"text": "hello"}'])
        assert result.exit_code == 0
        assert captured_kwargs["json"]["input"] == {"text": "hello"}


# ---------------------------------------------------------------------------
# TestLogsCommand
# ---------------------------------------------------------------------------

class TestLogsCommand:
    def test_logs_shows_entries(self):
        """Mock returns log list — node IDs and events must appear in output."""
        runner = CliRunner()
        logs = [
            {"timestamp": "2026-03-19T10:00:00Z", "node_id": "node-llm-1", "event": "started"},
            {"timestamp": "2026-03-19T10:00:05Z", "node_id": "node-llm-1", "event": "completed"},
        ]
        mock_resp = _mock_response(logs)
        with patch("httpx.get", return_value=mock_resp):
            result = runner.invoke(cli, ["logs", "exec-run-001"])
        assert result.exit_code == 0
        assert "node-llm-1" in result.output
        assert "started" in result.output
        assert "completed" in result.output

    def test_logs_json_flag(self):
        """--json flag outputs raw JSON log entries."""
        runner = CliRunner()
        logs = [{"timestamp": "2026-03-19T10:00:00Z", "node_id": "n1", "event": "ok"}]
        mock_resp = _mock_response(logs)
        with patch("httpx.get", return_value=mock_resp):
            result = runner.invoke(cli, ["logs", "exec-run-001", "--json"])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert isinstance(parsed, list)
        assert len(parsed) >= 1
        assert parsed[0]["node_id"] == "n1"

    def test_logs_empty(self):
        """Empty log entries → 'No log entries found.' message."""
        runner = CliRunner()
        mock_resp = _mock_response([])
        with patch("httpx.get", return_value=mock_resp):
            result = runner.invoke(cli, ["logs", "exec-empty"])
        assert result.exit_code == 0
        assert "No log entries found." in result.output

    def test_logs_http_error(self):
        """404 error fetching logs → error message, exit code 1."""
        runner = CliRunner()
        mock_resp = _mock_response({"detail": "Not Found"}, status_code=404)
        with patch("httpx.get", return_value=mock_resp):
            result = runner.invoke(cli, ["logs", "exec-missing"])
        assert result.exit_code == 1
        assert "Error:" in result.output


# ---------------------------------------------------------------------------
# TestMarketplaceSearch
# ---------------------------------------------------------------------------

class TestMarketplaceSearch:
    def test_search_shows_results(self):
        """Mock returns marketplace items — names must appear in table output."""
        runner = CliRunner()
        data = {
            "items": [
                {"id": "tpl-aaa", "name": "Summariser", "category": "nlp"},
                {"id": "tpl-bbb", "name": "Image Tagger", "category": "vision"},
            ],
            "total": 2,
        }
        mock_resp = _mock_response(data)
        with patch("httpx.get", return_value=mock_resp):
            result = runner.invoke(cli, ["marketplace", "search", "ai"])
        assert result.exit_code == 0
        assert "Summariser" in result.output
        assert "Image Tagger" in result.output
        assert "nlp" in result.output
        assert "vision" in result.output

    def test_search_json_flag(self):
        """--json flag outputs raw JSON from server."""
        runner = CliRunner()
        data = {"items": [{"id": "tpl-ccc", "name": "Chat Bot", "category": "chat"}], "total": 1}
        mock_resp = _mock_response(data)
        with patch("httpx.get", return_value=mock_resp):
            result = runner.invoke(cli, ["marketplace", "search", "chat", "--json"])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert "items" in parsed
        assert isinstance(parsed["items"], list)
        assert len(parsed["items"]) >= 1
        assert parsed["items"][0]["id"] == "tpl-ccc"

    def test_search_no_results(self):
        """Empty results → 'Found 0 result(s)' in output."""
        runner = CliRunner()
        data = {"items": [], "total": 0}
        mock_resp = _mock_response(data)
        with patch("httpx.get", return_value=mock_resp):
            result = runner.invoke(cli, ["marketplace", "search", "xyzzy-nonexistent"])
        assert result.exit_code == 0
        assert "Found 0 result(s)" in result.output

    def test_search_http_error(self):
        """500 server error → error message, exit code 1."""
        runner = CliRunner()
        mock_resp = _mock_response({"detail": "Internal Server Error"}, status_code=500)
        with patch("httpx.get", return_value=mock_resp):
            result = runner.invoke(cli, ["marketplace", "search", "any"])
        assert result.exit_code == 1
        assert "Error:" in result.output
