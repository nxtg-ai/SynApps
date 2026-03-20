from typing import Any

import httpx

from .models import ExecutionLog, MarketplaceListing, Workflow, WorkflowRun


class AsyncClient:
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

    async def _get(self, path: str, **params: Any) -> Any:
        async with httpx.AsyncClient(timeout=self._timeout) as http:
            r = await http.get(
                f"{self._base}{path}",
                headers=self._headers,
                params=params,
            )
            r.raise_for_status()
            return r.json()

    async def _post(self, path: str, body: dict[str, Any]) -> Any:
        async with httpx.AsyncClient(timeout=self._timeout) as http:
            r = await http.post(
                f"{self._base}{path}",
                headers=self._headers,
                json=body,
            )
            r.raise_for_status()
            return r.json()

    async def list_workflows(self) -> list[Workflow]:
        data = await self._get("/api/v1/flows")
        flows = data if isinstance(data, list) else data.get("flows", data.get("items", []))
        return [Workflow.model_validate(f) for f in flows]

    async def get_workflow(self, workflow_id: str) -> Workflow:
        data = await self._get(f"/api/v1/flows/{workflow_id}")
        return Workflow.model_validate(data)

    async def create_workflow(
        self,
        name: str,
        nodes: list[dict[str, Any]] | None = None,
        edges: list[dict[str, Any]] | None = None,
    ) -> Workflow:
        body: dict[str, Any] = {"name": name, "nodes": nodes or [], "edges": edges or []}
        data = await self._post("/api/v1/flows", body)
        flow_id = data.get("id", data.get("flow_id", ""))
        return await self.get_workflow(flow_id)

    async def run(self, workflow_id: str, input: dict[str, Any] | None = None) -> WorkflowRun:
        body: dict[str, Any] = {"input": input or {}}
        data = await self._post(f"/api/v1/flows/{workflow_id}/runs", body)
        run_id = data.get("run_id", data.get("id", ""))
        return WorkflowRun(
            run_id=run_id,
            status=data.get("status", "started"),
            output=data.get("output", {}),
        )

    async def get_logs(self, execution_id: str) -> list[ExecutionLog]:
        data = await self._get(f"/api/v1/executions/{execution_id}/logs")
        entries = data if isinstance(data, list) else data.get("logs", data.get("entries", []))
        return [ExecutionLog.model_validate(e) for e in entries]

    async def search_marketplace(self, query: str, limit: int = 20) -> list[MarketplaceListing]:
        data = await self._get("/api/v1/marketplace/listings", q=query, limit=limit)
        items = data.get("items", data if isinstance(data, list) else [])
        return [MarketplaceListing.model_validate(i) for i in items]

    async def get_analytics(self, workflow_id: str) -> dict[str, Any]:
        return await self._get(f"/api/v1/analytics/{workflow_id}")

    async def get_analytics_dashboard(self) -> dict[str, Any]:
        return await self._get("/api/v1/analytics/dashboard")
