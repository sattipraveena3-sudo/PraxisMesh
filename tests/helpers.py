from __future__ import annotations

from pathlib import Path

from praxismesh.audit import HashChainLedger
from praxismesh.config import Settings
from praxismesh.orchestrator import Orchestrator
from praxismesh.planner import DeterministicPlanner
from praxismesh.policy import PolicyEngine
from praxismesh.repository import Repository
from praxismesh.tools import ToolRegistry
from praxismesh.verifiers import VerifierRegistry


def settings_for(root: Path) -> Settings:
    return Settings(
        environment="test",
        host="127.0.0.1",
        port=8000,
        data_dir=root,
        database_path=root / "test.db",
        workspace_root=root / "workspaces",
        planner="deterministic",
        openai_model="gpt-5.6",
        allow_http=False,
        http_allowlist=("api.github.com",),
        auto_approve_low_risk=True,
        max_steps=20,
        tool_timeout_seconds=3,
    )


def orchestrator_for(root: Path) -> Orchestrator:
    settings = settings_for(root)
    settings.ensure_directories()
    tools = ToolRegistry.default()
    return Orchestrator(
        settings=settings,
        repository=Repository(settings.database_path),
        ledger=HashChainLedger(root / "audit.jsonl"),
        planner=DeterministicPlanner(),
        tools=tools,
        policy=PolicyEngine(settings),
        verifiers=VerifierRegistry(),
    )
