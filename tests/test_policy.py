from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from praxismesh.domain import PlanStep, PolicyEffect, RiskLevel
from praxismesh.policy import PolicyEngine

from tests.helpers import settings_for


class PolicyEngineTests(unittest.TestCase):
    def test_allows_bounded_transform(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            engine = PolicyEngine(settings_for(Path(directory)))
            decision = engine.evaluate(
                PlanStep("s1", "Analyze", "local transform", "text_analyze", {"text": "hi"})
            )
            self.assertEqual(decision.effect, PolicyEffect.ALLOW)
            self.assertEqual(decision.risk, RiskLevel.LOW)

    def test_requires_approval_for_persistent_write(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            engine = PolicyEngine(settings_for(Path(directory)))
            decision = engine.evaluate(
                PlanStep(
                    "s1",
                    "Write",
                    "persistent mutation",
                    "artifact_write",
                    {"path": "brief.md", "content": "evidence"},
                )
            )
            self.assertEqual(decision.effect, PolicyEffect.REQUIRE_APPROVAL)
            self.assertEqual(decision.risk, RiskLevel.MEDIUM)

    def test_denies_workspace_escape_and_destructive_shell(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            engine = PolicyEngine(settings_for(Path(directory)))
            escape = engine.evaluate(
                PlanStep("s1", "Write", "escape", "artifact_write", {"path": "../../outside.txt"})
            )
            shell = engine.evaluate(
                PlanStep("s2", "Delete", "danger", "shell", {"command": "rm -rf /"})
            )
            self.assertEqual(escape.effect, PolicyEffect.DENY)
            self.assertEqual(shell.effect, PolicyEffect.DENY)
            self.assertEqual(shell.risk, RiskLevel.CRITICAL)


if __name__ == "__main__":
    unittest.main()
