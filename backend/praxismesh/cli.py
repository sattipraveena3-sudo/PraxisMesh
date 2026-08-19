from __future__ import annotations

import argparse
import json
from typing import Sequence

from .domain import RunStatus
from .service import build_orchestrator

DEFAULT_GOAL = (
    "Create a verified execution brief for launching a trustworthy AI research project, "
    "including explicit safety, evaluation, and reproducibility requirements."
)


def _demo(goal: str, auto_approve: bool) -> int:
    orchestrator = build_orchestrator()
    run = orchestrator.create_run(goal)
    run = orchestrator.execute_run(run.id)
    print(f"run={run.id} status={run.status.value}")
    if run.status == RunStatus.WAITING_APPROVAL:
        approvals = orchestrator.approvals(run.id, status="pending")
        if not approvals:
            print("run paused but no approval record was found")
            return 2
        approval = approvals[0]
        print(
            f"approval={approval.id} step={approval.step_id} risk={approval.risk.value} "
            f"reasons={'; '.join(approval.reasons)}"
        )
        if auto_approve:
            orchestrator.decide_approval(
                run.id,
                approval.id,
                approved=True,
                decided_by="cli-demo",
                note="Approved by the deterministic demo scenario.",
            )
            run = orchestrator.execute_run(run.id)
            print(f"resumed status={run.status.value}")
    print(json.dumps(run.to_dict(), indent=2, default=str))
    integrity, evidence = orchestrator.ledger.verify()
    print(f"audit_integrity={integrity} events_checked={evidence.get('checked', 0)}")
    return 0 if run.status in {RunStatus.SUCCEEDED, RunStatus.WAITING_APPROVAL} else 1


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="praxismesh")
    subparsers = parser.add_subparsers(dest="command", required=True)

    demo = subparsers.add_parser("demo", help="Run the safe pause-approve-resume scenario")
    demo.add_argument("--goal", default=DEFAULT_GOAL)
    demo.add_argument("--auto-approve", action="store_true")

    subparsers.add_parser("verify-ledger", help="Verify the audit hash chain")

    serve = subparsers.add_parser("serve", help="Start the API and dashboard")
    serve.add_argument("--host", default=None)
    serve.add_argument("--port", type=int, default=None)

    args = parser.parse_args(argv)
    if args.command == "demo":
        return _demo(args.goal, args.auto_approve)
    if args.command == "verify-ledger":
        integrity, evidence = build_orchestrator().ledger.verify()
        print(json.dumps({"integrity": integrity, **evidence}, indent=2))
        return 0 if integrity else 1
    if args.command == "serve":
        try:
            import uvicorn
        except ImportError as exc:
            raise SystemExit("Install the project dependencies before running the server") from exc
        service = build_orchestrator()
        uvicorn.run(
            "praxismesh.api:app",
            host=args.host or service.settings.host,
            port=args.port or service.settings.port,
            reload=service.settings.environment == "development",
        )
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
