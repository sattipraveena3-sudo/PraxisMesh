from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from praxismesh.domain import RunStatus, StepStatus

from tests.helpers import orchestrator_for


class OrchestratorIntegrationTests(unittest.TestCase):
    def test_pause_approve_resume_and_verify(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            orchestrator = orchestrator_for(Path(directory))
            run = orchestrator.create_run(
                "Prepare a verified research launch brief with safety and reproducibility evidence."
            )
            self.assertEqual(run.status, RunStatus.READY)

            paused = orchestrator.execute_run(run.id)
            self.assertEqual(paused.status, RunStatus.WAITING_APPROVAL)
            self.assertEqual(paused.plan.steps[3].status, StepStatus.WAITING_APPROVAL)
            self.assertEqual(paused.plan.steps[0].status, StepStatus.SUCCEEDED)

            approvals = orchestrator.approvals(run.id, status="pending")
            self.assertEqual(len(approvals), 1)
            orchestrator.decide_approval(
                run.id,
                approvals[0].id,
                approved=True,
                decided_by="integration-test",
            )
            completed = orchestrator.execute_run(run.id)

            self.assertEqual(completed.status, RunStatus.SUCCEEDED)
            self.assertTrue(
                all(step.status == StepStatus.SUCCEEDED for step in completed.plan.steps)
            )
            artifact = Path(completed.plan.steps[3].output["path"])
            self.assertTrue(artifact.is_file())
            self.assertIn("Safety contract", artifact.read_text(encoding="utf-8"))
            integrity, evidence = orchestrator.ledger.verify()
            self.assertTrue(integrity)
            self.assertGreaterEqual(evidence["checked"], 20)

    def test_denial_terminates_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            orchestrator = orchestrator_for(Path(directory))
            run = orchestrator.create_run("Create a durable, policy-checked execution artifact.")
            paused = orchestrator.execute_run(run.id)
            approval = orchestrator.approvals(paused.id, status="pending")[0]
            denied = orchestrator.decide_approval(
                paused.id,
                approval.id,
                approved=False,
                decided_by="integration-test",
            )
            self.assertEqual(denied.status, RunStatus.FAILED)
            self.assertIn("Approval denied", denied.error)


if __name__ == "__main__":
    unittest.main()
