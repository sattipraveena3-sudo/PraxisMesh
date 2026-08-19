from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from praxismesh.audit import HashChainLedger


class HashChainLedgerTests(unittest.TestCase):
    def test_chain_verifies_and_detects_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "audit.jsonl"
            ledger = HashChainLedger(path)
            first = ledger.append("run_1", "run.created", {"goal": "safe objective"})
            second = ledger.append("run_1", "plan.validated", {"steps": 2})

            valid, evidence = ledger.verify()
            self.assertTrue(valid)
            self.assertEqual(evidence["checked"], 2)
            self.assertEqual(second.previous_hash, first.event_hash)

            lines = path.read_text(encoding="utf-8").splitlines()
            payload = json.loads(lines[0])
            payload["payload"]["goal"] = "tampered objective"
            lines[0] = json.dumps(payload, sort_keys=True)
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")

            valid, evidence = ledger.verify()
            self.assertFalse(valid)
            self.assertEqual(evidence["broken_at"], 1)


if __name__ == "__main__":
    unittest.main()

