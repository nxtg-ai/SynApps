from typing import Any

import httpx

from .models import ExecutionLog, MarketplaceListing, Workflow, WorkflowRun


class Client:
    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        token: str | None = None,
        timeout: float = 30.0,
    ):
        self._base = base_url.rstrip("/")
        self._token = token
        self._timeout = timeout

    @property
    def _headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self._token:
            h["Authorization"] = f"Bearer {self._token}"
        return h

    def _get(self, path: str, **params: Any) -> Any:
        r = httpx.get(
            f"{self._base}{path}",
            headers=self._headers,
            params=params,
            timeout=self._timeout,
        )
        r.raise_for_status()
        return r.json()

    def _post(self, path: str, body: dict[str, Any]) -> Any:
        r = httpx.post(
            f"{self._base}{path}",
            headers=self._headers,
            json=body,
            timeout=self._timeout,
        )
        r.raise_for_status()
        return r.json()

    def list_workflows(self) -> list[Workflow]:
        data = self._get("/api/v1/flows")
        flows = data if isinstance(data, list) else data.get("flows", data.get("items", []))
        return [Workflow.model_validate(f) for f in flows]

    def get_workflow(self, workflow_id: str) -> Workflow:
        data = self._get(f"/api/v1/flows/{workflow_id}")
        return Workflow.model_validate(data)

    def create_workflow(
        self,
        name: str,
        nodes: list[dict[str, Any]] | None = None,
        edges: list[dict[str, Any]] | None = None,
    ) -> Workflow:
        body: dict[str, Any] = {"name": name, "nodes": nodes or [], "edges": edges or []}
        data = self._post("/api/v1/flows", body)
        # POST /flows returns {message, id} — fetch full object
        flow_id = data.get("id", data.get("flow_id", ""))
        return self.get_workflow(flow_id)

    def run(self, workflow_id: str, input: dict[str, Any] | None = None) -> WorkflowRun:
        body: dict[str, Any] = {"input": input or {}}
        data = self._post(f"/api/v1/flows/{workflow_id}/runs", body)
        run_id = data.get("run_id", data.get("id", ""))
        return WorkflowRun(
            run_id=run_id,
            status=data.get("status", "started"),
            output=data.get("output", {}),
        )

    def get_logs(self, execution_id: str) -> list[ExecutionLog]:
        data = self._get(f"/api/v1/executions/{execution_id}/logs")
        entries = data if isinstance(data, list) else data.get("logs", data.get("entries", []))
        return [ExecutionLog.model_validate(e) for e in entries]

    def search_marketplace(self, query: str, limit: int = 20) -> list[MarketplaceListing]:
        data = self._get("/api/v1/marketplace/listings", q=query, limit=limit)
        items = data.get("items", data if isinstance(data, list) else [])
        return [MarketplaceListing.model_validate(i) for i in items]

    def get_analytics(self, workflow_id: str) -> dict[str, Any]:
        return self._get(f"/api/v1/analytics/{workflow_id}")

    def get_analytics_dashboard(self) -> dict[str, Any]:
        return self._get("/api/v1/analytics/dashboard")
