from __future__ import annotations

from .domain import ExecutionPlan


class InvalidPlan(ValueError):
    """Raised when a generated execution plan violates structural constraints."""


class PlanValidator:
    def __init__(self, allowed_tools: set[str], max_steps: int = 20) -> None:
        self.allowed_tools = allowed_tools
        self.max_steps = max_steps

    def validate(self, plan: ExecutionPlan) -> None:
        if not plan.steps:
            raise InvalidPlan("A plan must contain at least one step")
        if len(plan.steps) > self.max_steps:
            raise InvalidPlan(f"Plan exceeds the {self.max_steps}-step limit")

        ids = [step.id for step in plan.steps]
        if len(ids) != len(set(ids)):
            raise InvalidPlan("Step IDs must be unique")

        known = set(ids)
        for step in plan.steps:
            if step.tool not in self.allowed_tools:
                raise InvalidPlan(f"Unknown tool: {step.tool}")
            missing = set(step.depends_on) - known
            if missing:
                raise InvalidPlan(f"Step {step.id} depends on missing steps: {sorted(missing)}")
            if step.id in step.depends_on:
                raise InvalidPlan(f"Step {step.id} cannot depend on itself")

        edges = {step.id: list(step.depends_on) for step in plan.steps}
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(step_id: str) -> None:
            if step_id in visiting:
                raise InvalidPlan("Plan dependency graph contains a cycle")
            if step_id in visited:
                return
            visiting.add(step_id)
            for dependency in edges[step_id]:
                visit(dependency)
            visiting.remove(step_id)
            visited.add(step_id)

        for step_id in ids:
            visit(step_id)
