from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import Literal

from pydantic import BaseModel, Field

from .config import Settings
from .domain import ExecutionPlan, PlanStep, new_id
from .tools import ToolRegistry


class Planner(ABC):
    name: str

    @abstractmethod
    def plan(self, goal: str) -> ExecutionPlan:
        raise NotImplementedError


class DeterministicPlanner(Planner):
    name = "deterministic"

    def plan(self, goal: str) -> ExecutionPlan:
        return ExecutionPlan(
            id=new_id("plan"),
            goal=goal,
            rationale=(
                "Build a verified execution brief through bounded transformations, then request "
                "approval before committing the persistent artifact."
            ),
            steps=[
                PlanStep(
                    id="intake",
                    name="Capture goal",
                    description="Normalize the requested outcome into the execution context.",
                    tool="capture_goal",
                    arguments={"goal": goal},
                    verifier="keys_present",
                    verifier_config={"keys": ["goal", "run_id"]},
                ),
                PlanStep(
                    id="analyze",
                    name="Analyze complexity",
                    description="Extract deterministic complexity signals and key concepts.",
                    tool="text_analyze",
                    arguments={"text": "${steps.intake.output.goal}"},
                    depends_on=["intake"],
                    verifier="keys_present",
                    verifier_config={"keys": ["word_count", "top_keywords"]},
                ),
                PlanStep(
                    id="report",
                    name="Compose execution brief",
                    description="Create a human-readable report from verified upstream evidence.",
                    tool="compose_report",
                    arguments={
                        "title": "PraxisMesh Verified Execution Brief",
                        "goal": "${steps.intake.output.goal}",
                        "analysis": "${steps.analyze.output}",
                    },
                    depends_on=["intake", "analyze"],
                    verifier="keys_present",
                    verifier_config={"keys": ["format", "content"]},
                ),
                PlanStep(
                    id="write_report",
                    name="Commit approved artifact",
                    description="Write the report inside the isolated run workspace.",
                    tool="artifact_write",
                    arguments={
                        "path": "execution-brief.md",
                        "content": "${steps.report.output.content}",
                    },
                    depends_on=["report"],
                    verifier="artifact_sha256",
                ),
                PlanStep(
                    id="verify_report",
                    name="Read back and verify",
                    description="Independently read the artifact and verify required content.",
                    tool="artifact_read",
                    arguments={"path": "execution-brief.md"},
                    depends_on=["write_report"],
                    verifier="contains",
                    verifier_config={"text": "Safety contract"},
                ),
            ],
        )


class LLMStep(BaseModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{1,40}$")
    name: str
    description: str
    tool: Literal[
        "capture_goal",
        "text_analyze",
        "compose_report",
        "artifact_write",
        "artifact_read",
        "http_get",
    ]
    arguments: dict[str, object]
    depends_on: list[str]
    verifier: Literal["non_empty", "keys_present", "artifact_sha256", "contains", "regex"]
    verifier_config: dict[str, object]


class LLMPlan(BaseModel):
    rationale: str
    steps: list[LLMStep] = Field(min_length=1, max_length=20)


class OpenAIPlanner(Planner):
    name = "openai"

    def __init__(self, model: str, tools: ToolRegistry) -> None:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("Install PraxisMesh with the 'openai' extra") from exc
        self.model = model
        self.tools = tools
        self.client = OpenAI()

    def plan(self, goal: str) -> ExecutionPlan:
        catalog = "\n".join(
            f"- {item['name']}: {item['description']}" for item in self.tools.catalog()
        )
        instructions = (
            "You are the planning component of PraxisMesh. Produce the smallest safe DAG that "
            "achieves the goal using only the provided tools. You do not execute actions and may "
            "not bypass approval, policy, verification, or workspace boundaries. Use references "
            "like ${steps.step_id.output.key} for prior outputs. Every non-root dependency must "
            "refer to an earlier step. Persistent output must use artifact_write and must be read "
            "back with artifact_read.\n\nAvailable tools:\n" + catalog
        )
        response = self.client.responses.parse(
            model=self.model,
            reasoning={"effort": "low"},
            input=[
                {"role": "system", "content": instructions},
                {"role": "user", "content": goal},
            ],
            text_format=LLMPlan,
        )
        parsed = response.output_parsed
        if parsed is None:
            raise RuntimeError("The planner returned no structured plan")
        steps = [PlanStep(**step.model_dump()) for step in parsed.steps]
        return ExecutionPlan(
            id=new_id("plan"), goal=goal, rationale=parsed.rationale, steps=steps
        )


def build_planner(settings: Settings, tools: ToolRegistry) -> Planner:
    if settings.planner == "openai" and os.getenv("OPENAI_API_KEY"):
        return OpenAIPlanner(settings.openai_model, tools)
    return DeterministicPlanner()

