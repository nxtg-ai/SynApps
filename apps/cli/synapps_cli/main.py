import json
import sys

import click
import httpx

from .config import get_config


@click.group()
def cli():
    """SynApps CLI — manage AI workflows from your terminal."""
    pass


@cli.command("list")
@click.option("--json", "as_json", is_flag=True, help="Output raw JSON")
def list_workflows(as_json):
    """List all workflows."""
    cfg = get_config()
    headers = _auth_headers(cfg)
    try:
        r = httpx.get(f"{cfg['url']}/api/v1/flows", headers=headers, timeout=15)
        r.raise_for_status()
    except httpx.HTTPStatusError as exc:
        click.echo(f"Error: {exc.response.status_code} {exc.response.text}", err=True)
        sys.exit(1)
    except httpx.RequestError as exc:
        click.echo(f"Connection error: {exc}", err=True)
        sys.exit(1)
    data = r.json()
    if as_json:
        click.echo(json.dumps(data, indent=2))
        return
    flows = data if isinstance(data, list) else data.get("flows", data.get("items", []))
    if not flows:
        click.echo("No workflows found.")
        return
    click.echo(f"{'ID':<36}  {'NAME':<30}  {'NODES'}")
    click.echo("-" * 75)
    for f in flows:
        nodes = len(f.get("nodes", []))
        click.echo(f"{f.get('id', ''):<36}  {f.get('name', ''):<30}  {nodes}")


@cli.command("run")
@click.argument("workflow_id")
@click.option("--input", "input_data", default="{}", help="JSON input payload")
def run_workflow(workflow_id, input_data):
    """Execute a workflow by ID."""
    cfg = get_config()
    headers = _auth_headers(cfg)
    try:
        payload = json.loads(input_data)
    except json.JSONDecodeError as exc:
        click.echo(f"Invalid --input JSON: {exc}", err=True)
        sys.exit(1)
    try:
        r = httpx.post(
            f"{cfg['url']}/api/v1/flows/{workflow_id}/runs",
            headers=headers,
            json={"input": payload},
            timeout=30,
        )
        r.raise_for_status()
    except httpx.HTTPStatusError as exc:
        click.echo(f"Error: {exc.response.status_code} {exc.response.text}", err=True)
        sys.exit(1)
    except httpx.RequestError as exc:
        click.echo(f"Connection error: {exc}", err=True)
        sys.exit(1)
    result = r.json()
    run_id = result.get("run_id", result.get("id", "unknown"))
    status = result.get("status", "unknown")
    click.echo(f"Run started: {run_id}")
    click.echo(f"Status: {status}")


@cli.command("logs")
@click.argument("execution_id")
@click.option("--json", "as_json", is_flag=True)
def get_logs(execution_id, as_json):
    """Stream execution logs for a run."""
    cfg = get_config()
    headers = _auth_headers(cfg)
    try:
        r = httpx.get(
            f"{cfg['url']}/api/v1/executions/{execution_id}/logs",
            headers=headers,
            timeout=15,
        )
        r.raise_for_status()
    except httpx.HTTPStatusError as exc:
        click.echo(f"Error: {exc.response.status_code} {exc.response.text}", err=True)
        sys.exit(1)
    except httpx.RequestError as exc:
        click.echo(f"Connection error: {exc}", err=True)
        sys.exit(1)
    data = r.json()
    if as_json:
        click.echo(json.dumps(data, indent=2))
        return
    entries = data if isinstance(data, list) else data.get("logs", data.get("entries", []))
    if not entries:
        click.echo("No log entries found.")
        return
    for entry in entries:
        ts = entry.get("timestamp", "")[:19]
        node = entry.get("node_id", entry.get("node", ""))
        event = entry.get("event", entry.get("type", ""))
        click.echo(f"[{ts}] {node:<20} {event}")


@click.group("marketplace")
def marketplace_group():
    """Marketplace commands."""
    pass


@marketplace_group.command("search")
@click.argument("query")
@click.option("--json", "as_json", is_flag=True)
def marketplace_search(query, as_json):
    """Search marketplace templates."""
    cfg = get_config()
    headers = _auth_headers(cfg)
    try:
        r = httpx.get(
            f"{cfg['url']}/api/v1/marketplace/listings",
            headers=headers,
            params={"q": query},
            timeout=15,
        )
        r.raise_for_status()
    except httpx.HTTPStatusError as exc:
        click.echo(f"Error: {exc.response.status_code} {exc.response.text}", err=True)
        sys.exit(1)
    except httpx.RequestError as exc:
        click.echo(f"Connection error: {exc}", err=True)
        sys.exit(1)
    data = r.json()
    if as_json:
        click.echo(json.dumps(data, indent=2))
        return
    items = data.get("items", data if isinstance(data, list) else [])
    total = data.get("total", len(items))
    click.echo(f"Found {total} result(s) for '{query}':")
    if not items:
        return
    click.echo(f"\n{'ID':<36}  {'NAME':<30}  {'CATEGORY'}")
    click.echo("-" * 80)
    for item in items:
        click.echo(
            f"{item.get('id', ''):<36}  {item.get('name', ''):<30}  {item.get('category', '')}"
        )


cli.add_command(marketplace_group, "marketplace")


def _auth_headers(cfg: dict) -> dict:
    headers = {"Content-Type": "application/json"}
    if cfg.get("token"):
        headers["Authorization"] = f"Bearer {cfg['token']}"
    return headers


def main():
    cli()
