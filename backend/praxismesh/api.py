from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

from fastapi import BackgroundTasks, FastAPI, HTTPException, Path as ApiPath, Query
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .domain import RunStatus
from .orchestrator import InvalidRunState, RunNotFound
from .service import build_orchestrator


class CreateRunRequest(BaseModel):
    goal: str = Field(min_length=3, max_length=10_000)
    auto_start: bool = True


class ApprovalDecisionRequest(BaseModel):
    decision: Literal["approve", "deny"]
    decided_by: str = Field(default="console-operator", min_length=2, max_length=120)
    note: str | None = Field(default=None, max_length=1_000)
    resume: bool = True


app = FastAPI(
    title="PraxisMesh API",
    description="Verified agent operations with policy gates, approvals, and evidence.",
    version="0.1.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)
orchestrator = build_orchestrator()


@app.exception_handler(RunNotFound)
async def handle_missing_run(_, exc: RunNotFound) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": f"Run not found: {exc.args[0]}"})


@app.exception_handler(InvalidRunState)
async def handle_invalid_state(_, exc: InvalidRunState) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.get("/health")
def health() -> dict[str, object]:
    integrity, evidence = orchestrator.ledger.verify()
    return {
        "status": "ok" if integrity else "degraded",
        "service": "praxismesh",
        "version": "0.1.0",
        "planner": orchestrator.planner.name,
        "audit_integrity": integrity,
        "audit_head": evidence.get("head"),
    }


@app.post("/api/runs", status_code=201)
def create_run(request: CreateRunRequest, background: BackgroundTasks) -> dict[str, object]:
    run = orchestrator.create_run(request.goal)
    if request.auto_start and run.status == RunStatus.READY:
        background.add_task(orchestrator.execute_run, run.id)
    return _run_payload(run)


@app.get("/api/runs")
def list_runs(limit: Annotated[int, Query(ge=1, le=200)] = 50) -> dict[str, object]:
    runs = orchestrator.list_runs(limit)
    return {"items": [_run_payload(run) for run in runs], "count": len(runs)}


@app.get("/api/runs/{run_id}")
def get_run(run_id: Annotated[str, ApiPath(pattern=r"^run_[a-f0-9]{12}$")]) -> dict[str, object]:
    return _run_payload(orchestrator.get_run(run_id))


@app.post("/api/runs/{run_id}/execute")
def execute_run(
    run_id: Annotated[str, ApiPath(pattern=r"^run_[a-f0-9]{12}$")],
    background: BackgroundTasks,
) -> dict[str, object]:
    run = orchestrator.get_run(run_id)
    background.add_task(orchestrator.execute_run, run_id)
    return {"accepted": True, "run": _run_payload(run)}


@app.get("/api/runs/{run_id}/approvals")
def list_approvals(
    run_id: Annotated[str, ApiPath(pattern=r"^run_[a-f0-9]{12}$")],
) -> dict[str, object]:
    approvals = orchestrator.approvals(run_id)
    return {"items": [approval.to_dict() for approval in approvals], "count": len(approvals)}


@app.post("/api/runs/{run_id}/approvals/{approval_id}")
def decide_approval(
    run_id: Annotated[str, ApiPath(pattern=r"^run_[a-f0-9]{12}$")],
    approval_id: Annotated[str, ApiPath(pattern=r"^approval_[a-f0-9]{12}$")],
    request: ApprovalDecisionRequest,
    background: BackgroundTasks,
) -> dict[str, object]:
    try:
        run = orchestrator.decide_approval(
            run_id,
            approval_id,
            approved=request.decision == "approve",
            decided_by=request.decided_by,
            note=request.note,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if request.resume and request.decision == "approve":
        background.add_task(orchestrator.execute_run, run_id)
    return _run_payload(run)


@app.get("/api/runs/{run_id}/events")
def list_events(
    run_id: Annotated[str, ApiPath(pattern=r"^run_[a-f0-9]{12}$")],
) -> dict[str, object]:
    orchestrator.get_run(run_id)
    events = orchestrator.ledger.list(run_id=run_id)
    return {"items": [event.to_dict() for event in events], "count": len(events)}


@app.get("/api/runs/{run_id}/artifacts")
def list_artifacts(
    run_id: Annotated[str, ApiPath(pattern=r"^run_[a-f0-9]{12}$")],
) -> dict[str, object]:
    orchestrator.get_run(run_id)
    workspace = (orchestrator.settings.workspace_root / run_id).resolve()
    root = orchestrator.settings.workspace_root.resolve()
    if root not in workspace.parents or not workspace.exists():
        return {"items": [], "count": 0}
    items = [
        {
            "name": str(path.relative_to(workspace)),
            "bytes": path.stat().st_size,
            "download_url": f"/api/runs/{run_id}/artifacts/{path.relative_to(workspace)}",
        }
        for path in workspace.rglob("*")
        if path.is_file()
    ]
    return {"items": items, "count": len(items)}


@app.get("/api/runs/{run_id}/artifacts/{artifact_path:path}")
def download_artifact(
    run_id: Annotated[str, ApiPath(pattern=r"^run_[a-f0-9]{12}$")], artifact_path: str
) -> FileResponse:
    orchestrator.get_run(run_id)
    workspace = (orchestrator.settings.workspace_root / run_id).resolve()
    candidate = (workspace / artifact_path).resolve()
    if workspace not in candidate.parents or not candidate.is_file():
        raise HTTPException(status_code=404, detail="Artifact not found")
    return FileResponse(candidate, filename=candidate.name)


@app.get("/api/tools")
def tools() -> dict[str, object]:
    catalog = orchestrator.tools.catalog()
    return {"items": catalog, "count": len(catalog)}


@app.get("/api/metrics")
def metrics_json() -> dict[str, object]:
    return orchestrator.metrics()


@app.get("/metrics", response_class=PlainTextResponse)
def prometheus_metrics() -> str:
    metrics = orchestrator.metrics()
    lines = [
        "# HELP praxismesh_runs_total Total submitted runs.",
        "# TYPE praxismesh_runs_total gauge",
        f"praxismesh_runs_total {metrics['runs_total']}",
        "# HELP praxismesh_pending_approvals Pending approval decisions.",
        "# TYPE praxismesh_pending_approvals gauge",
        f"praxismesh_pending_approvals {metrics['pending_approvals']}",
        "# HELP praxismesh_success_rate Fraction of terminal runs that succeeded.",
        "# TYPE praxismesh_success_rate gauge",
        f"praxismesh_success_rate {metrics['success_rate']}",
        "# HELP praxismesh_audit_integrity Audit chain integrity (1=valid).",
        "# TYPE praxismesh_audit_integrity gauge",
        f"praxismesh_audit_integrity {1 if metrics['audit_integrity'] else 0}",
    ]
    for status, value in metrics["runs_by_status"].items():
        lines.append(f'praxismesh_runs_by_status{{status="{status}"}} {value}')
    return "\n".join(lines) + "\n"


def _run_payload(run) -> dict[str, object]:
    payload = run.to_dict()
    payload["approvals"] = [item.to_dict() for item in orchestrator.approvals(run.id)]
    return payload


frontend = Path(__file__).resolve().parents[2] / "frontend"
if frontend.exists():
    app.mount("/", StaticFiles(directory=frontend, html=True), name="frontend")
