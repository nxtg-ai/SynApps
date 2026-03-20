from typing import Any

from pydantic import BaseModel, Field


class Workflow(BaseModel):
    id: str
    name: str
    nodes: list[dict[str, Any]] = Field(default_factory=list)
    edges: list[dict[str, Any]] = Field(default_factory=list)


class WorkflowRun(BaseModel):
    run_id: str
    status: str
    output: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class ExecutionLog(BaseModel):
    node_id: str
    event: str
    timestamp: str
    input: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] = Field(default_factory=dict)
    duration_ms: float | None = None
    error: str | None = None


class MarketplaceListing(BaseModel):
    id: str
    name: str
    description: str = ""
    category: str = ""
    tags: list[str] = Field(default_factory=list)
    install_count: int = 0
