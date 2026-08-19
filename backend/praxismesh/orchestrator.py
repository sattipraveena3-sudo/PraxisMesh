from __future__ import annotations

import re
import threading
from pathlib import Path
from typing import Any

from .audit import HashChainLedger
from .config import Settings
from .domain import (
    ApprovalRecord,
    PlanStep,
    PolicyEffect,
    RunRecord,
    RunStatus,
    StepStatus,
    new_id,
    utc_now,
)
from .plan_validation import PlanValidator
from .planner import Planner
from .policy import PolicyEngine
from .repository import Repository
from .tools import ToolContext, ToolRegistry
from .verifiers import VerifierRegistry


class RunNotFound(KeyError):
    pass


class InvalidRunState(RuntimeError):
    pass


REFERENCE = re.compile(r"^\$\{steps\.([a-zA-Z0-9_-]+)\.output(?:\.([a-zA-Z0-9_.-]+))?\}$")


class Orchestrator:
    def __init__(
        self,
        settings: Settings,
        repository: Repository,
        ledger: HashChainLedger,
        planner: Planner,
        tools: ToolRegistry,
        policy: PolicyEngine,
        verifiers: VerifierRegistry,
    ) -> None:
        self.settings = settings
        self.repository = repository
        self.ledger = ledger
        self.planner = planner
        self.tools = tools
        self.policy = policy
        self.verifiers = verifiers
        self.validator = PlanValidator(tools.names, settings.max_steps)
        self._locks: dict[str, threading.RLock] = {}
        self._locks_guard = threading.Lock()

    def create_run(self, goal: str) -> RunRecord:
        normalized_goal = goal.strip()
        if not normalized_goal:
            raise ValueError("goal must not be empty")
        if len(normalized_goal) > 10_000:
            raise ValueError("goal exceeds the 10,000 character limit")
        run = RunRecord(id=new_id("run"), goal=normalized_goal, planner=self.planner.name)
        self.repository.save_run(run)
        self.ledger.append(run.id, "run.created", {"goal": normalized_goal})
        try:
            run.status = RunStatus.PLANNING
            self.repository.save_run(run)
            plan = self.planner.plan(normalized_goal)
            self.validator.validate(plan)
            run.plan = plan
            run.status = RunStatus.READY
            self.repository.save_run(run)
            self.ledger.append(
                run.id,
                "plan.validated",
                {"plan_id": plan.id, "planner": self.planner.name, "steps": len(plan.steps)},
            )
        except Exception as exc:
            run.status = RunStatus.FAILED
            run.error = f"Planning failed: {exc}"
            self.repository.save_run(run)
            self.ledger.append(run.id, "run.failed", {"stage": "planning", "error": str(exc)})
        return run

    def execute_run(self, run_id: str) -> RunRecord:
        with self._lock_for(run_id):
            run = self._require_run(run_id)
            if run.status in {RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED}:
                return run
            if not run.plan:
                raise InvalidRunState("run has no validated plan")

            run.status = RunStatus.RUNNING
            run.error = None
            self.repository.save_run(run)
            self.ledger.append(run.id, "run.started", {"plan_id": run.plan.id})

            for step in run.plan.steps:
                if step.status == StepStatus.SUCCEEDED:
                    continue

                dependencies = [self._step(run, dependency) for dependency in step.depends_on]
                if any(item.status == StepStatus.FAILED for item in dependencies):
                    step.status = StepStatus.SKIPPED
                    step.error = "A dependency failed"
                    self.repository.save_run(run)
                    continue
                if any(item.status != StepStatus.SUCCEEDED for item in dependencies):
                    step.status = StepStatus.BLOCKED
                    self.repository.save_run(run)
                    continue

                decision = self.policy.evaluate(step)
                self.ledger.append(
                    run.id,
                    "policy.evaluated",
                    {"step_id": step.id, **decision.to_dict()},
                )
                if decision.effect == PolicyEffect.DENY:
                    return self._fail(run, step, "; ".join(decision.reasons), "policy")

                if decision.effect == PolicyEffect.REQUIRE_APPROVAL:
                    approval = self.repository.find_latest_approval(run.id, step.id)
                    if approval and approval.status == "denied":
                        return self._fail(run, step, "Human approval was denied", "approval")
                    if not approval:
                        approval = ApprovalRecord(
                            id=new_id("approval"),
                            run_id=run.id,
                            step_id=step.id,
                            risk=decision.risk,
                            reasons=decision.reasons,
                        )
                        self.repository.save_approval(approval)
                        self.ledger.append(
                            run.id, "approval.requested", {"approval": approval.to_dict()}
                        )
                    if approval.status != "approved":
                        step.status = StepStatus.WAITING_APPROVAL
                        run.status = RunStatus.WAITING_APPROVAL
                        self.repository.save_run(run)
                        return run

                try:
                    resolved_arguments = self._resolve_arguments(step.arguments, run)
                    step.status = StepStatus.RUNNING
                    step.started_at = utc_now()
                    step.error = None
                    self.repository.save_run(run)
                    self.ledger.append(
                        run.id,
                        "tool.started",
                        {"step_id": step.id, "tool": step.tool, "arguments": resolved_arguments},
                    )
                    workspace = self._workspace(run.id)
                    output = self.tools.execute(
                        step.tool,
                        resolved_arguments,
                        ToolContext(run.id, workspace, self.settings),
                    )
                    step.output = output
                    step.status = StepStatus.VERIFYING
                    self.repository.save_run(run)
                    verification = self.verifiers.verify(
                        step.verifier, step.output, step.verifier_config
                    )
                    self.ledger.append(
                        run.id,
                        "verification.completed",
                        {"step_id": step.id, **verification.to_dict()},
                    )
                    if not verification.passed:
                        return self._fail(run, step, verification.message, "verification")
                    step.status = StepStatus.SUCCEEDED
                    step.finished_at = utc_now()
                    self.repository.save_run(run)
                    self.ledger.append(
                        run.id,
                        "tool.succeeded",
                        {"step_id": step.id, "tool": step.tool, "output": output},
                    )
                except Exception as exc:
                    return self._fail(run, step, str(exc), "execution")

            if all(step.status == StepStatus.SUCCEEDED for step in run.plan.steps):
                run.status = RunStatus.SUCCEEDED
                self.repository.save_run(run)
                self.ledger.append(
                    run.id,
                    "run.succeeded",
                    {"steps": len(run.plan.steps), "workspace": str(self._workspace(run.id))},
                )
            elif any(step.status == StepStatus.FAILED for step in run.plan.steps):
                run.status = RunStatus.FAILED
                self.repository.save_run(run)
            return run

    def decide_approval(
        self,
        run_id: str,
        approval_id: str,
        approved: bool,
        decided_by: str,
        note: str | None = None,
    ) -> RunRecord:
        with self._lock_for(run_id):
            run = self._require_run(run_id)
            approval = self.repository.get_approval(approval_id)
            if not approval or approval.run_id != run_id:
                raise KeyError("approval not found for this run")
            if approval.status != "pending":
                raise InvalidRunState("approval has already been decided")
            approval.status = "approved" if approved else "denied"
            approval.decided_at = utc_now()
            approval.decided_by = decided_by.strip() or "operator"
            approval.note = note
            self.repository.save_approval(approval)
            self.ledger.append(
                run.id,
                "approval.decided",
                {
                    "approval_id": approval.id,
                    "step_id": approval.step_id,
                    "status": approval.status,
                    "decided_by": approval.decided_by,
                    "note": note,
                },
            )
            if approved:
                step = self._step(run, approval.step_id)
                step.status = StepStatus.PENDING
                run.status = RunStatus.READY
            else:
                step = self._step(run, approval.step_id)
                step.status = StepStatus.FAILED
                step.error = "Approval denied"
                run.status = RunStatus.FAILED
                run.error = f"Approval denied for step {step.id}"
            self.repository.save_run(run)
            return run

    def get_run(self, run_id: str) -> RunRecord:
        return self._require_run(run_id)

    def list_runs(self, limit: int = 50) -> list[RunRecord]:
        return self.repository.list_runs(limit)

    def approvals(self, run_id: str, status: str | None = None) -> list[ApprovalRecord]:
        self._require_run(run_id)
        return self.repository.list_approvals(run_id, status)

    def metrics(self) -> dict[str, Any]:
        metrics = self.repository.metrics()
        integrity, evidence = self.ledger.verify()
        metrics["audit_integrity"] = integrity
        metrics["audit_events"] = evidence.get("checked", 0)
        return metrics

    def _fail(self, run: RunRecord, step: PlanStep, error: str, stage: str) -> RunRecord:
        step.status = StepStatus.FAILED
        step.error = error
        step.finished_at = utc_now()
        run.status = RunStatus.FAILED
        run.error = f"Step '{step.name}' failed during {stage}: {error}"
        self.repository.save_run(run)
        self.ledger.append(
            run.id,
            "run.failed",
            {"stage": stage, "step_id": step.id, "error": error},
        )
        return run

    def _resolve_arguments(self, value: Any, run: RunRecord) -> Any:
        if isinstance(value, dict):
            return {key: self._resolve_arguments(item, run) for key, item in value.items()}
        if isinstance(value, list):
            return [self._resolve_arguments(item, run) for item in value]
        if not isinstance(value, str):
            return value
        match = REFERENCE.fullmatch(value)
        if not match:
            return value
        step = self._step(run, match.group(1))
        current: Any = step.output
        path = match.group(2)
        if path:
            for part in path.split("."):
                if isinstance(current, dict) and part in current:
                    current = current[part]
                else:
                    raise ValueError(f"Unresolvable reference: {value}")
        return current

    def _workspace(self, run_id: str) -> Path:
        workspace = (self.settings.workspace_root / run_id).resolve()
        root = self.settings.workspace_root.resolve()
        if root not in workspace.parents:
            raise RuntimeError("invalid workspace path")
        workspace.mkdir(parents=True, exist_ok=True)
        return workspace

    def _require_run(self, run_id: str) -> RunRecord:
        run = self.repository.get_run(run_id)
        if not run:
            raise RunNotFound(run_id)
        return run

    @staticmethod
    def _step(run: RunRecord, step_id: str) -> PlanStep:
        if not run.plan:
            raise InvalidRunState("run has no plan")
        for step in run.plan.steps:
            if step.id == step_id:
                return step
        raise KeyError(f"step not found: {step_id}")

    def _lock_for(self, run_id: str) -> threading.RLock:
        with self._locks_guard:
            return self._locks.setdefault(run_id, threading.RLock())
