"""
Execution router for SynApps Orchestrator.

Extracted from main.py (Step 3 of M-1 router decomposition).
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
)

from apps.orchestrator.dependencies import (
    get_authenticated_user,
)
from apps.orchestrator.helpers import (
    _WORKFLOW_PATTERNS,
    HISTORY_VALID_STATUSES,
    _build_history_entry,
    _build_run_diff,
    _diff_workflows,
    _estimate_node_cost,
    _extract_final_output,
    _extract_trace_from_run,
    _match_description_to_node,
    _match_output,
    _run_flow_debug,
    _run_flow_impl,
    _score_node_suggestions,
    _trace_value,
    paginate,
)
from apps.orchestrator.repositories import FlowRepository, WorkflowRunRepository
from apps.orchestrator.request_models import (
    AISuggestRequest,
    AutocompleteRequest,
    CostEstimateRequest,
    PayoutRequest,
    RateListingRequest,
    ReplyToReviewRequest,
    ReportIssueRequest,
    RerunFlowRequest,
    ReviewListingRequest,
    RunFlowRequest,
    RunTestSuiteRequest,
    StartDebugRequest,
    SuggestNextNodeRequest,
    TestCaseRequest,
    TrendingService,
    UpdateBreakpointsRequest,
    WorkflowDiffRequest,
    WorkflowProfilerService,
    WorkflowVersionSaveRequest,
)
from apps.orchestrator.stores import (
    cost_tracker_store,
    credit_ledger,
    debug_session_store,
    execution_log_store,
    flow_run_preset_store,
    issue_store,
    marketplace_registry,
    rating_store,
    replay_store,
    reply_store,
    review_store,
    test_suite_store,
    workflow_version_store,
)

logger = logging.getLogger("orchestrator")


# Orchestrator and applet_registry are populated by main.py after all modules load.
# They start as None/empty and are set via _setup_router_globals() in main.py.
Orchestrator = None  # type: ignore[assignment]
applet_registry: dict = {}

# workflow_profiler is created as a module-level instance of WorkflowProfilerService
workflow_profiler = WorkflowProfilerService()

router = APIRouter()


# ============================================================
# Execution Routes
# ============================================================

@router.post("/flows/{flow_id}/runs", status_code=202, tags=["Runs"])
async def create_flow_run(
    flow_id: str,
    body: RunFlowRequest,
    debug: bool = Query(
        False, description="When true, poll until terminal then return execution logs inline"
    ),
    preset_id: str | None = Query(None, description="Use a saved run preset as the input payload."),
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """RESTful run creation endpoint for a flow.

    Pass ``?debug=true`` to block until the run reaches a terminal state and
    return the full per-node execution log inline with the response.
    Pass ``?preset_id=<id>`` to load a saved input preset (overrides body.input).
    """
    if preset_id is not None:
        preset = flow_run_preset_store.get(flow_id, preset_id)
        if preset is None:
            raise HTTPException(status_code=404, detail="Preset not found")
        body = RunFlowRequest(input=preset["input"])
    result = await _run_flow_impl(flow_id, body, current_user)
    if not debug:
        return result
    run_id = result["run_id"]
    # Poll until terminal (max 60 s)
    deadline = time.time() + 60.0
    run = None
    while time.time() < deadline:
        await asyncio.sleep(0.1)
        run = await WorkflowRunRepository.get_by_run_id(run_id)
        if run and run.get("status") in ("success", "error"):
            break
    logs = execution_log_store.get(run_id)
    return {
        "run_id": run_id,
        "status": run.get("status") if run else "unknown",
        "logs": logs,
    }


@router.post("/flows/{flow_id}/run", deprecated=True, tags=["Runs"])
async def run_flow_legacy(
    flow_id: str,
    body: RunFlowRequest,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Backward-compatible alias for flow execution."""
    return await _run_flow_impl(flow_id, body, current_user)


@router.get("/runs", tags=["Runs"])
async def list_runs(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """List all workflow runs with pagination."""
    runs = await WorkflowRunRepository.get_all()
    return paginate(runs, page, page_size)


@router.get("/runs/{run_id}", tags=["Runs"])
async def get_run(
    run_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Get a workflow run by ID."""
    run = await WorkflowRunRepository.get_by_run_id(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@router.get("/runs/{run_id}/trace", tags=["Runs"])
async def get_run_trace(
    run_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Return normalized full execution trace for a workflow run."""
    run = await WorkflowRunRepository.get_by_run_id(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return _extract_trace_from_run(run)


@router.get("/runs/{run_id}/diff", tags=["Runs"])
async def get_run_diff(
    run_id: str,
    other_run_id: str = Query(..., min_length=1, description="Run ID to compare against"),
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Return structural execution diff between two workflow runs."""
    if run_id == other_run_id:
        raise HTTPException(status_code=400, detail="Cannot diff a run against itself")

    base_run = await WorkflowRunRepository.get_by_run_id(run_id)
    if not base_run:
        raise HTTPException(status_code=404, detail="Base run not found")

    compare_run = await WorkflowRunRepository.get_by_run_id(other_run_id)
    if not compare_run:
        raise HTTPException(status_code=404, detail="Comparison run not found")

    diff_payload = _build_run_diff(base_run, compare_run)
    diff_payload["same_flow"] = base_run.get("flow_id") == compare_run.get("flow_id")
    return diff_payload


@router.get("/executions/{run_id}/logs", tags=["Executions"])
async def get_execution_logs(
    run_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Fetch the full per-node execution log for a run.

    Returns an ordered list of log entries, one per event:
    ``node_start``, ``node_retry``, ``node_success``, ``node_fallback``, ``node_error``.
    Returns 404 if the run has no recorded logs.
    """
    if not execution_log_store.has(run_id):
        raise HTTPException(status_code=404, detail="No execution logs found for this run")
    logs = execution_log_store.get(run_id)
    logs = sorted(logs, key=lambda e: e.get("timestamp", ""))
    return {"run_id": run_id, "count": len(logs), "logs": logs}


@router.post("/runs/{run_id}/rerun", status_code=202, tags=["Runs"])
async def rerun_workflow(
    run_id: str,
    body: RerunFlowRequest,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Re-run a previous workflow execution using original or overridden input."""
    source_run = await WorkflowRunRepository.get_by_run_id(run_id)
    if not source_run:
        raise HTTPException(status_code=404, detail="Run not found")

    flow_id = source_run.get("flow_id")
    if not isinstance(flow_id, str) or not flow_id:
        raise HTTPException(status_code=400, detail="Source run is missing a valid flow_id")

    flow = await FlowRepository.get_by_id(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found for source run")

    flow = await Orchestrator.auto_migrate_legacy_nodes(flow, persist=True)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found for source run")

    source_input = source_run.get("input_data")
    if not isinstance(source_input, dict):
        source_trace = _extract_trace_from_run(source_run)
        trace_input = source_trace.get("input")
        source_input = trace_input if isinstance(trace_input, dict) else {}

    override_input = body.input if isinstance(body.input, dict) else {}
    if body.merge_with_original_input:
        rerun_input: dict[str, Any] = dict(source_input)
        rerun_input.update(override_input)
    else:
        rerun_input = dict(override_input)

    rerun_input = _trace_value(rerun_input)
    if not isinstance(rerun_input, dict):
        rerun_input = {}

    new_run_id = await Orchestrator.execute_flow(flow, rerun_input)
    return {
        "run_id": new_run_id,
        "source_run_id": run_id,
        "flow_id": flow_id,
        "input": rerun_input,
    }


@router.post("/ai/suggest", tags=["Applets"])
async def ai_suggest(
    body: AISuggestRequest,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Generate code suggestions using AI."""
    raise HTTPException(
        status_code=501,
        detail="AI code suggestion is not implemented in the Alpha release. Please check back in a future version.",
    )


@router.get("/history", tags=["History"])
async def list_execution_history(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    status: str | None = Query(None, description="Filter by status: idle, running, success, error"),
    template: str | None = Query(
        None, description="Filter by flow/template name (substring match)"
    ),
    start_after: float | None = Query(
        None, description="Filter runs started after this Unix timestamp"
    ),
    start_before: float | None = Query(
        None, description="Filter runs started before this Unix timestamp"
    ),
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """List past workflow executions with filtering by status, date range, and template name."""
    if status and status not in HISTORY_VALID_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status. Valid: {sorted(HISTORY_VALID_STATUSES)}",
        )

    all_runs = await WorkflowRunRepository.get_all()

    # Sort by start_time descending (most recent first)
    all_runs.sort(key=lambda r: r.get("start_time", 0), reverse=True)

    # Apply filters
    if status:
        all_runs = [r for r in all_runs if r.get("status") == status]

    if start_after is not None:
        all_runs = [r for r in all_runs if (r.get("start_time") or 0) >= start_after]

    if start_before is not None:
        all_runs = [r for r in all_runs if (r.get("start_time") or 0) <= start_before]

    # Template/flow name filter requires flow lookup
    if template:
        template_lower = template.lower()
        filtered = []
        for r in all_runs:
            fid = r.get("flow_id")
            if fid:
                flow = await FlowRepository.get_by_id(fid)
                if flow and template_lower in (flow.get("name", "").lower()):
                    filtered.append(r)
        all_runs = filtered

    total = len(all_runs)

    # Paginate
    start = (page - 1) * page_size
    page_runs = all_runs[start : start + page_size]

    entries = [await _build_history_entry(r) for r in page_runs]

    return {
        "history": entries,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/history/{run_id}", tags=["History"])
async def get_execution_detail(
    run_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Get full execution detail for a past run, including step-by-step trace."""
    run = await WorkflowRunRepository.get_by_run_id(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")

    entry = await _build_history_entry(run)
    trace = _extract_trace_from_run(run)

    return {
        **entry,
        "input_data": run.get("input_data"),
        "trace": trace,
    }


@router.post("/workflows/{flow_id}/estimate-cost", tags=["Cost"])
async def estimate_workflow_cost(
    flow_id: str,
    body: CostEstimateRequest,
    current_user: dict = Depends(get_authenticated_user),
):
    """Estimate the execution cost of a workflow before running it.

    Args:
        flow_id: The workflow/flow ID to estimate costs for.
        body: Optional input_text used to derive rough token counts for LLM nodes.
        current_user: Authenticated user (injected by FastAPI).

    Returns:
        A dict with per-node breakdown and aggregate estimated_usd.
    """
    flow = await FlowRepository.get_by_id(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")

    nodes: list[dict] = flow.get("nodes", [])
    input_text_len = len(body.input_text)

    breakdown: list[dict] = []
    llm_node_count = 0
    http_node_count = 0
    total_token_input = 0
    total_token_output = 0
    total_usd = 0.0

    for node in nodes:
        node_id = str(node.get("id", ""))
        node_type = str(node.get("type", "")).lower().strip()
        node_data = node.get("data", {})

        # Build a synthetic node_data for LLM nodes that incorporates input_text length.
        if node_type == "llm":
            llm_node_count += 1
            token_input = max(input_text_len // 4, 100)
            token_output = 200
            model = str(node_data.get("model", "gpt-4o"))
            est_usd = float(token_input * 0.000005 + token_output * 0.000015)
            total_token_input += token_input
            total_token_output += token_output
            total_usd += est_usd
            breakdown.append(
                {
                    "node_id": node_id,
                    "node_type": node_type,
                    "model": model,
                    "estimated_usd": est_usd,
                    "tokens": token_input + token_output,
                }
            )
        elif node_type in ("http", "http_request"):
            http_node_count += 1
            breakdown.append(
                {
                    "node_id": node_id,
                    "node_type": node_type,
                    "model": "",
                    "estimated_usd": 0.0,
                    "tokens": 0,
                }
            )
        else:
            cost = _estimate_node_cost(node_type, node_data, {})
            breakdown.append(
                {
                    "node_id": node_id,
                    "node_type": node_type,
                    "model": cost.get("model", ""),
                    "estimated_usd": cost["estimated_usd"],
                    "tokens": cost["token_input"] + cost["token_output"],
                }
            )
            total_usd += cost["estimated_usd"]
            total_token_input += cost["token_input"]
            total_token_output += cost["token_output"]

    # Confidence: low if >3 LLM nodes, high if 0 LLM nodes, medium otherwise.
    if llm_node_count == 0:
        confidence = "high"
    elif llm_node_count > 3:
        confidence = "low"
    else:
        confidence = "medium"

    return {
        "flow_id": flow_id,
        "node_count": len(nodes),
        "llm_node_count": llm_node_count,
        "http_node_count": http_node_count,
        "estimated_token_input": total_token_input,
        "estimated_token_output": total_token_output,
        "estimated_usd": total_usd,
        "estimated_usd_formatted": f"${total_usd:.5f}",
        "confidence": confidence,
        "breakdown": breakdown,
    }


@router.get("/executions/{execution_id}/cost", tags=["Cost"])
async def get_execution_cost(
    execution_id: str,
    current_user: dict = Depends(get_authenticated_user),
):
    """Return cost breakdown for a specific execution.

    Returns 404 if no cost record exists for the given execution_id.
    """
    rec = cost_tracker_store.get(execution_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="Cost record not found for this execution")
    return {
        "execution_id": rec.execution_id,
        "flow_id": rec.flow_id,
        "node_costs": rec.node_costs,
        "total_usd": rec.total_usd,
        "total_tokens": rec.total_tokens,
        "created_at": rec.created_at,
    }


@router.get("/workflows/{flow_id}/cost-summary", tags=["Cost"])
async def get_workflow_cost_summary(
    flow_id: str,
    current_user: dict = Depends(get_authenticated_user),
):
    """Return aggregated cost summary for all runs of a workflow."""
    records = cost_tracker_store.list_for_flow(flow_id)
    run_count = len(records)
    if run_count == 0:
        return {
            "flow_id": flow_id,
            "run_count": 0,
            "total_usd": 0.0,
            "avg_usd_per_run": 0.0,
            "total_tokens": 0,
            "avg_tokens_per_run": 0.0,
            "records": [],
        }
    total_usd = sum(r.total_usd for r in records)
    total_tokens = sum(r.total_tokens for r in records)
    return {
        "flow_id": flow_id,
        "run_count": run_count,
        "total_usd": total_usd,
        "avg_usd_per_run": total_usd / run_count,
        "total_tokens": total_tokens,
        "avg_tokens_per_run": total_tokens / run_count,
        "records": [
            {
                "execution_id": r.execution_id,
                "flow_id": r.flow_id,
                "node_costs": r.node_costs,
                "total_usd": r.total_usd,
                "total_tokens": r.total_tokens,
                "created_at": r.created_at,
            }
            for r in records
        ],
    }


@router.post("/executions/{execution_id}/replay", status_code=202, tags=["Replay"])
async def replay_execution(
    execution_id: str,
    current_user: dict = Depends(get_authenticated_user),
):
    """Replay a previous execution using its original input data.

    Looks up the stored input for *execution_id*, launches a new async
    execution, and registers it in the replay chain.  Returns 404 if the
    execution was never recorded.
    """
    stored = execution_log_store.get_input(execution_id)
    if stored is None:
        raise HTTPException(status_code=404, detail="Execution not found")
    flow_id, input_data = stored

    # Determine root of chain so replays stay flat under the original
    original_run_id = replay_store.get_original(execution_id)

    replay_run_id = str(uuid.uuid4())
    replay_store.register_replay(original_run_id, replay_run_id)

    # Fire-and-forget replay via existing flow machinery
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    flow = await Orchestrator.auto_migrate_legacy_nodes(flow, persist=True)

    async def _replay_task() -> None:
        try:
            # Re-use _run_flow_impl path: execute then register input for chaining
            actual_run_id = await Orchestrator.execute_flow(flow, input_data)
            execution_log_store.record_input(actual_run_id, flow_id, input_data)
            # Re-register under the correct replay_run_id alias
            replay_store.register_replay(original_run_id, actual_run_id)
        except Exception as exc:
            logger.warning("Replay task for %s failed: %s", replay_run_id, exc)

    asyncio.create_task(_replay_task())

    return {
        "replay_run_id": replay_run_id,
        "original_run_id": original_run_id,
        "flow_id": flow_id,
        "status": "started",
    }


@router.get("/executions/{execution_id}/replay-history", tags=["Replay"])
async def get_replay_history(
    execution_id: str,
    current_user: dict = Depends(get_authenticated_user),
):
    """Return the replay chain for an execution.

    Returns the full ordered chain [original, replay1, replay2, ...].
    If the execution has never been replayed, returns an empty chain.
    """
    chain = replay_store.get_chain(execution_id)
    # If the run is not the root AND has never been seen, chain will just be [execution_id]
    # with no replays. But if execution_id was never recorded at all, still return gracefully.
    return {
        "execution_id": execution_id,
        "chain": chain,
        "length": len(chain),
    }


@router.post("/workflows/{flow_id}/diff", tags=["Workflow Diff"])
async def workflow_diff(
    flow_id: str,
    body: WorkflowDiffRequest,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    """Compute a structural diff between two workflow snapshots."""
    return _diff_workflows(body.v1, body.v2)


@router.post("/workflows/{flow_id}/versions", tags=["Workflow Diff"])
async def workflow_save_version(
    flow_id: str,
    body: WorkflowVersionSaveRequest,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    """Save a workflow snapshot as a new named version."""
    record = workflow_version_store.save_version(flow_id, body.snapshot, body.label)
    return {**record, "flow_id": flow_id}


@router.get("/workflows/{flow_id}/version-history", tags=["Workflow Diff"])
async def workflow_version_history(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    """Return all version summaries for a workflow (no full snapshots)."""
    versions = workflow_version_store.list_versions(flow_id)
    return {"flow_id": flow_id, "versions": versions, "total": len(versions)}


@router.get("/workflows/{flow_id}/versions/{version_id}", tags=["Workflow Diff"])
async def workflow_get_version(
    flow_id: str,
    version_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    """Return the full snapshot record for a specific workflow version."""
    record = workflow_version_store.get_version(flow_id, version_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Version not found")
    return record


@router.get("/workflows/{flow_id}/profile", tags=["Node Profiler"])
async def workflow_profile(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    """Return aggregated node performance statistics for a workflow."""
    return workflow_profiler.profile_workflow(flow_id)


@router.get("/executions/{execution_id}/profile", tags=["Node Profiler"])
async def execution_profile(
    execution_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict:
    """Return per-node performance profile for a single execution run."""
    result = workflow_profiler.profile_execution(execution_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Execution not found or no logs available")
    return result


@router.post("/ai-assist/suggest-next", tags=["AI Assist"])
async def ai_assist_suggest_next(
    body: SuggestNextNodeRequest,
    current_user: dict = Depends(get_authenticated_user),
):
    """Suggest likely next-node types given the current node type.

    Uses a weighted transition table derived from common workflow patterns,
    adjusted by recency penalty for node types already present in the workflow.
    Returns up to *limit* suggestions ordered by score descending.
    """
    suggestions = _score_node_suggestions(body.current_node_type, body.existing_node_types)
    return {"suggestions": suggestions[: body.limit]}


@router.post("/ai-assist/autocomplete", tags=["AI Assist"])
async def ai_assist_autocomplete(
    body: AutocompleteRequest,
    current_user: dict = Depends(get_authenticated_user),
):
    """Suggest node configurations from a natural-language description.

    Matches keywords in *description* against known node-type vocabulary.
    Returns matching node types with their default configuration templates.
    """
    matches = _match_description_to_node(body.description)
    return {"matches": matches[: body.limit]}


@router.get("/ai-assist/patterns", tags=["AI Assist"])
async def ai_assist_patterns(
    tag: str | None = None,
    current_user: dict = Depends(get_authenticated_user),
):
    """Return the built-in workflow pattern library.

    Optionally filter by *tag* (case-insensitive substring match).
    Each pattern includes a name, description, node sequence, and tags.
    """
    patterns = _WORKFLOW_PATTERNS
    if tag:
        tag_lower = tag.lower()
        patterns = [p for p in patterns if any(tag_lower in t for t in p["tags"])]
    return {"patterns": patterns, "total": len(patterns)}


@router.post("/workflows/{flow_id}/debug", tags=["Debug"], status_code=201)
async def start_debug_session(
    flow_id: str,
    body: StartDebugRequest,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict[str, Any]:
    """Start a new step-through debug execution for a flow.

    Creates a DebugSession and launches the debug execution as a background
    task. Returns the session_id and run_id immediately so the caller can
    poll GET /debug/{session_id} for state.

    Args:
        flow_id: The flow to debug.
        body: input_data and list of breakpoint node IDs.
        current_user: Authenticated user (injected by FastAPI).

    Returns:
        JSON with session_id, run_id, status, and breakpoints.
    """
    flow = await FlowRepository.get_by_id(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")

    run_id = str(uuid.uuid4())
    session = debug_session_store.create(
        run_id=run_id,
        flow_id=flow_id,
        breakpoints=body.breakpoints,
    )
    initial_status = session.status  # capture before background task can mutate it

    asyncio.create_task(
        _run_flow_debug(
            flow_id=flow_id,
            run_id=run_id,
            session_id=session.session_id,
            input_data=dict(body.input_data),
        )
    )

    logger.info(
        "Debug session %s started for flow %s (run_id=%s, breakpoints=%s)",
        session.session_id,
        flow_id,
        run_id,
        body.breakpoints,
    )

    return {
        "session_id": session.session_id,
        "run_id": run_id,
        "status": initial_status,
        "breakpoints": sorted(session.breakpoints),
    }


@router.get("/debug/{session_id}", tags=["Debug"])
async def get_debug_session(
    session_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict[str, Any]:
    """Return the current state of a debug session.

    Args:
        session_id: The debug session to query.
        current_user: Authenticated user.

    Returns:
        Full session state dict including execution history.

    Raises:
        HTTPException 404: When session_id is not found.
    """
    session = debug_session_store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Debug session not found")
    return session.to_dict()


@router.post("/debug/{session_id}/continue", tags=["Debug"])
async def debug_continue(
    session_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict[str, Any]:
    """Resume execution from a breakpoint.

    Signals the paused background task to continue to the next node (or next
    breakpoint). If the session is not currently paused the call is a no-op
    that still returns 200.

    Args:
        session_id: The debug session to resume.
        current_user: Authenticated user.

    Returns:
        Updated session state.

    Raises:
        HTTPException 404: When session_id is not found.
    """
    session = debug_session_store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Debug session not found")

    if session.status == "paused":
        session._skip_flag = False
        session.status = "running"
        session._resume_event.set()
        logger.info("Debug session %s resumed (continue)", session_id)

    return session.to_dict()


@router.post("/debug/{session_id}/skip", tags=["Debug"])
async def debug_skip(
    session_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict[str, Any]:
    """Skip the currently paused node and resume execution.

    The paused node's output is recorded as an empty dict and marked
    ``skipped=True`` in the execution history.

    Args:
        session_id: The debug session in which to skip the current node.
        current_user: Authenticated user.

    Returns:
        Updated session state.

    Raises:
        HTTPException 404: When session_id is not found.
    """
    session = debug_session_store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Debug session not found")

    if session.status == "paused":
        session._skip_flag = True
        session.status = "running"
        session._resume_event.set()
        logger.info(
            "Debug session %s resumed with skip at node %s", session_id, session.current_node_id
        )

    return session.to_dict()


@router.post("/debug/{session_id}/breakpoints", tags=["Debug"])
async def update_debug_breakpoints(
    session_id: str,
    body: UpdateBreakpointsRequest,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict[str, Any]:
    """Replace the breakpoint set for a debug session.

    The new list takes effect immediately: the next node evaluated against the
    breakpoint set will see the updated collection.

    Args:
        session_id: The debug session to update.
        body: New breakpoints list (replaces existing set).
        current_user: Authenticated user.

    Returns:
        Updated session state.

    Raises:
        HTTPException 404: When session_id is not found.
    """
    session = debug_session_store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Debug session not found")

    session.breakpoints = set(body.breakpoints)
    logger.info("Debug session %s breakpoints updated: %s", session_id, body.breakpoints)
    return session.to_dict()


@router.delete("/debug/{session_id}", tags=["Debug"], status_code=204)
async def abort_debug_session(
    session_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> None:
    """Abort a debug session, stopping the background execution task.

    Sets status to "aborted" and signals the resume event so the background
    task can detect the abort and exit cleanly.

    Args:
        session_id: The debug session to abort.
        current_user: Authenticated user.

    Raises:
        HTTPException 404: When session_id is not found.
    """
    session = debug_session_store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Debug session not found")

    session.status = "aborted"
    session._resume_event.set()  # unblock any waiting background task
    logger.info("Debug session %s aborted", session_id)


@router.get("/marketplace/trending", tags=["Marketplace"])
async def get_trending_listings(
    limit: int = Query(10, ge=1, le=50),
) -> dict[str, Any]:
    """Return trending marketplace listings (no auth required).

    Trending score = recent installs (last 7 days) × 10 + all-time install_count.
    """
    all_listings = marketplace_registry.list_all()
    top = TrendingService.top(all_listings, limit=limit)
    return {"items": top, "total": len(top)}


@router.get("/marketplace/publisher/dashboard", tags=["Marketplace"])
async def publisher_dashboard(
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict[str, Any]:
    """Return the publisher's own listings with rating and review stats."""
    all_listings = marketplace_registry.list_all()
    my_listings = [lst for lst in all_listings if lst.get("publisher_id") == current_user["id"]]
    result = []
    for listing in my_listings:
        lid = listing.get("listing_id", listing.get("id", ""))
        stats = rating_store.get_stats(lid)
        reviews = review_store.list(lid, limit=5)
        result.append(
            {
                **listing,
                "avg_rating": stats["avg_rating"],
                "rating_count": stats["rating_count"],
                "recent_reviews": reviews,
                "trending_score": TrendingService.score(listing),
            }
        )
    return {"listings": result, "total": len(result)}


@router.post("/marketplace/{listing_id}/rate", tags=["Marketplace"])
async def rate_listing(
    listing_id: str,
    body: RateListingRequest,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict[str, Any]:
    """Submit or update a star rating for a marketplace listing."""
    listing = marketplace_registry.get(listing_id)
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    stats = rating_store.rate(listing_id, current_user["id"], body.stars)
    return {"listing_id": listing_id, **stats}


@router.post("/marketplace/{listing_id}/review", status_code=201, tags=["Marketplace"])
async def add_review(
    listing_id: str,
    body: ReviewListingRequest,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict[str, Any]:
    """Submit a text review for a marketplace listing."""
    listing = marketplace_registry.get(listing_id)
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    review = review_store.add(listing_id, current_user["id"], body.text, body.stars)
    return review


@router.get("/marketplace/{listing_id}/reviews", tags=["Marketplace"])
async def list_reviews(
    listing_id: str,
    limit: int = Query(20, ge=1, le=100),
) -> dict[str, Any]:
    """List reviews for a marketplace listing (no auth required).

    Each review includes a ``reply`` field containing the publisher's reply
    (or ``None`` if no reply exists).
    """
    items = review_store.list(listing_id, limit=limit)
    enriched = []
    for review in items:
        enriched.append({**review, "reply": reply_store.get_reply(review["review_id"])})
    return {"listing_id": listing_id, "items": enriched, "total": len(enriched)}


@router.post("/marketplace/reviews/{review_id}/reply", tags=["Marketplace"])
async def reply_to_review(
    review_id: str,
    body: ReplyToReviewRequest,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict[str, Any]:
    """Submit a publisher reply to a review (auth required)."""
    reply = reply_store.add_reply(review_id, current_user["id"], body.text)
    return reply


@router.post("/marketplace/{listing_id}/report", status_code=201, tags=["Marketplace"])
async def report_issue(
    listing_id: str,
    body: ReportIssueRequest,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict[str, Any]:
    """Report an issue with a marketplace listing (auth required)."""
    issue = issue_store.report(listing_id, current_user["id"], body.type, body.description)
    return issue


@router.get("/marketplace/publisher/credits", tags=["Marketplace"])
async def publisher_credits(
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict[str, Any]:
    """Return credit summary for the authenticated publisher."""
    uid = current_user["id"]
    return {
        "balance": credit_ledger.balance(uid),
        "total_earned": credit_ledger.total_earned(uid),
        "total_paid_out": credit_ledger.total_earned(uid) - credit_ledger.balance(uid),
        "entry_count": len(credit_ledger.ledger(uid, limit=10_000)),
    }


@router.get("/marketplace/publisher/credits/ledger", tags=["Marketplace"])
async def publisher_credits_ledger(
    limit: int = Query(50, ge=1, le=500),
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict[str, Any]:
    """Return ledger entries for the authenticated publisher."""
    uid = current_user["id"]
    return {
        "entries": credit_ledger.ledger(uid, limit=limit),
        "balance": credit_ledger.balance(uid),
    }


@router.get("/marketplace/publisher/credits/payout-report", tags=["Marketplace"])
async def publisher_payout_report(
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict[str, Any]:
    """Return full payout report including per-listing breakdown."""
    return credit_ledger.payout_report(current_user["id"])


@router.post("/marketplace/publisher/credits/payout", tags=["Marketplace"])
async def publisher_payout(
    body: PayoutRequest,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict[str, Any]:
    """Request a credit payout. Returns updated balance."""
    try:
        credit_ledger.debit(current_user["id"], body.amount, note="payout")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"balance": credit_ledger.balance(current_user["id"])}


@router.post("/flows/{flow_id}/tests", status_code=201, tags=["Testing"])
async def add_flow_test_case(
    flow_id: str,
    body: TestCaseRequest,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict[str, Any]:
    """Add a test case to a flow's test suite."""
    flow = await FlowRepository.get_by_id(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
    return test_suite_store.add_test(
        flow_id=flow_id,
        name=body.name,
        description=body.description,
        input_data=body.input,
        expected_output=body.expected_output,
        match_mode=body.match_mode,
        created_by=current_user.get("email", ""),
    )


@router.get("/flows/{flow_id}/tests", tags=["Testing"])
async def list_flow_test_cases(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict[str, Any]:
    """List all test cases for a flow."""
    tests = test_suite_store.list_tests(flow_id)
    return {"tests": tests, "total": len(tests)}


@router.get("/flows/{flow_id}/tests/results", tags=["Testing"])
async def list_flow_test_results(
    flow_id: str,
    limit: int = Query(50, ge=1, le=500),
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict[str, Any]:
    """List test results for a flow, newest first."""
    results = test_suite_store.list_results(flow_id=flow_id, limit=limit)
    return {"results": results, "total": len(results)}


@router.get("/flows/{flow_id}/tests/summary", tags=["Testing"])
async def get_flow_test_summary(
    flow_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict[str, Any]:
    """Return aggregate test suite summary for a flow."""
    return test_suite_store.suite_summary(flow_id)


@router.post("/flows/{flow_id}/tests/run", tags=["Testing"])
async def run_flow_test_suite(
    flow_id: str,
    body: RunTestSuiteRequest | None = None,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict[str, Any]:
    """Run all or selected test cases for a flow and return results with exit_code."""
    flow = await FlowRepository.get_by_id(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")

    flow = await Orchestrator.auto_migrate_legacy_nodes(flow, persist=True)

    all_tests = test_suite_store.list_tests(flow_id)
    requested_ids = body.test_ids if body and body.test_ids else []
    if requested_ids:
        all_tests = [t for t in all_tests if t["test_id"] in requested_ids]

    results: list[dict[str, Any]] = []
    for test_case in all_tests:
        start_ms = time.time() * 1000
        try:
            run_id = await Orchestrator.execute_flow(flow, test_case["input"])

            # Poll for completion (max 60s)
            deadline = time.time() + 60.0
            run: dict[str, Any] | None = None
            while time.time() < deadline:
                await asyncio.sleep(0.1)
                run = await WorkflowRunRepository.get_by_run_id(run_id)
                if run and run.get("status") in ("success", "error"):
                    break

            if run is None:
                run = {"status": "unknown", "results": {}}

            actual_output = _extract_final_output(run)
            passed, diff = _match_output(
                actual_output,
                test_case["expected_output"],
                test_case["match_mode"],
            )

            status = "pass" if passed else "fail"
            if run.get("status") == "error":
                status = "error"

            result: dict[str, Any] = {
                "result_id": str(uuid.uuid4()),
                "test_id": test_case["test_id"],
                "flow_id": flow_id,
                "run_id": run_id,
                "status": status,
                "actual_output": actual_output,
                "expected_output": test_case["expected_output"],
                "diff": diff,
                "error_message": run.get("error", "") if status == "error" else "",
                "duration_ms": time.time() * 1000 - start_ms,
                "ran_at": time.time(),
            }
        except Exception as exc:
            logger.warning(
                "Test case %s failed with error: %s", test_case["test_id"], exc
            )
            result = {
                "result_id": str(uuid.uuid4()),
                "test_id": test_case["test_id"],
                "flow_id": flow_id,
                "run_id": "",
                "status": "error",
                "actual_output": {},
                "expected_output": test_case["expected_output"],
                "diff": {},
                "error_message": str(exc),
                "duration_ms": time.time() * 1000 - start_ms,
                "ran_at": time.time(),
            }

        test_suite_store.add_result(result)
        results.append(result)

    summary = test_suite_store.suite_summary(flow_id)
    all_passed = all(r["status"] == "pass" for r in results)
    exit_code = 0 if (all_passed or len(results) == 0) else 1

    return {"results": results, "summary": summary, "exit_code": exit_code}


@router.get("/flows/{flow_id}/tests/{test_id}", tags=["Testing"])
async def get_flow_test_case(
    flow_id: str,
    test_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> dict[str, Any]:
    """Get a single test case by ID."""
    test = test_suite_store.get_test(test_id)
    if not test or test.get("flow_id") != flow_id:
        raise HTTPException(status_code=404, detail="Test case not found")
    return test


@router.delete("/flows/{flow_id}/tests/{test_id}", status_code=204, tags=["Testing"])
async def delete_flow_test_case(
    flow_id: str,
    test_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
) -> None:
    """Delete a test case."""
    test = test_suite_store.get_test(test_id)
    if not test or test.get("flow_id") != flow_id:
        raise HTTPException(status_code=404, detail="Test case not found")
    test_suite_store.delete_test(test_id)
    return None

