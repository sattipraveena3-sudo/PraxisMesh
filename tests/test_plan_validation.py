from __future__ import annotations

import unittest

from praxismesh.domain import ExecutionPlan, PlanStep
from praxismesh.plan_validation import InvalidPlan, PlanValidator


class PlanValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.validator = PlanValidator({"capture_goal", "text_analyze"}, max_steps=5)

    def test_accepts_valid_dag(self) -> None:
        plan = ExecutionPlan(
            id="plan_1",
            goal="test",
            rationale="bounded plan",
            steps=[
                PlanStep("one", "One", "root", "capture_goal"),
                PlanStep("two", "Two", "child", "text_analyze", depends_on=["one"]),
            ],
        )
        self.validator.validate(plan)

    def test_rejects_cycle(self) -> None:
        plan = ExecutionPlan(
            id="plan_1",
            goal="test",
            rationale="invalid",
            steps=[
                PlanStep("one", "One", "root", "capture_goal", depends_on=["two"]),
                PlanStep("two", "Two", "child", "text_analyze", depends_on=["one"]),
            ],
        )
        with self.assertRaisesRegex(InvalidPlan, "cycle"):
            self.validator.validate(plan)

    def test_rejects_unknown_tool(self) -> None:
        plan = ExecutionPlan(
            id="plan_1",
            goal="test",
            rationale="invalid",
            steps=[PlanStep("one", "One", "root", "untrusted_tool")],
        )
        with self.assertRaisesRegex(InvalidPlan, "Unknown tool"):
            self.validator.validate(plan)


if __name__ == "__main__":
    unittest.main()
