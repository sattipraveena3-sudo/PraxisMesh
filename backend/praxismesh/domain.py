from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class PolicyEffect(StrEnum):
    ALLOW = "allow"
    REQUIRE_APPROVAL = "require_approval"
    DENY = "deny"


class RunStatus(StrEnum):
    CREATED = "created"
    PLANNING = "planning"
    READY = "ready"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StepStatus(StrEnum):
    PENDING = "pending"
    BLOCKED = "blocked"
    WAITING_APPROVAL = "waiting_approval"
    RUNNING = "running"
    VERIFYING = "verifying"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(slots=True)
class PlanStep:
    id: str
    name: str
    description: str
    tool: str
    arguments: dict[str, Any] = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)
    verifier: str = "non_empty"
    verifier_config: dict[str, Any] = field(default_factory=dict)
    status: StepStatus = StepStatus.PENDING
    output: Any = None
    error: str | None = None
    started_at: str | None = None
    finished_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["status"] = self.status.value
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "PlanStep":
        data = dict(payload)
        data["status"] = StepStatus(data.get("status", StepStatus.PENDING))
        return cls(**data)


@dataclass(slots=True)
class ExecutionPlan:
    id: str
    goal: str
    rationale: str
    steps: list[PlanStep]
    created_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "goal": self.goal,
            "rationale": self.rationale,
            "created_at": self.created_at,
            "steps": [step.to_dict() for step in self.steps],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ExecutionPlan":
        return cls(
            id=payload["id"],
            goal=payload["goal"],
            rationale=payload["rationale"],
            created_at=payload.get("created_at", utc_now()),
            steps=[PlanStep.from_dict(item) for item in payload["steps"]],
        )


@dataclass(slots=True)
class PolicyDecision:
    effect: PolicyEffect
    risk: RiskLevel
    reasons: list[str]
    rule_ids: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "effect": self.effect.value,
            "risk": self.risk.value,
            "reasons": self.reasons,
            "rule_ids": self.rule_ids,
        }


@dataclass(slots=True)
class ApprovalRecord:
    id: str
    run_id: str
    step_id: str
    risk: RiskLevel
    reasons: list[str]
    status: str = "pending"
    requested_at: str = field(default_factory=utc_now)
    decided_at: str | None = None
    decided_by: str | None = None
    note: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["risk"] = self.risk.value
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ApprovalRecord":
        data = dict(payload)
        data["risk"] = RiskLevel(data["risk"])
        return cls(**data)


@dataclass(slots=True)
class RunRecord:
    id: str
    goal: str
    status: RunStatus = RunStatus.CREATED
    planner: str = "deterministic"
    plan: ExecutionPlan | None = None
    error: str | None = None
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "goal": self.goal,
            "status": self.status.value,
            "planner": self.planner,
            "plan": self.plan.to_dict() if self.plan else None,
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RunRecord":
        return cls(
            id=payload["id"],
            goal=payload["goal"],
            status=RunStatus(payload["status"]),
            planner=payload.get("planner", "deterministic"),
            plan=ExecutionPlan.from_dict(payload["plan"]) if payload.get("plan") else None,
            error=payload.get("error"),
            created_at=payload.get("created_at", utc_now()),
            updated_at=payload.get("updated_at", utc_now()),
        )

    def as_json(self) -> str:
        return json.dumps(self.to_dict(), separators=(",", ":"), sort_keys=True)

