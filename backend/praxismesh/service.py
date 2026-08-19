from __future__ import annotations

from functools import lru_cache

from .audit import HashChainLedger
from .config import Settings
from .orchestrator import Orchestrator
from .planner import build_planner
from .policy import PolicyEngine
from .repository import Repository
from .tools import ToolRegistry
from .verifiers import VerifierRegistry


@lru_cache(maxsize=1)
def build_orchestrator() -> Orchestrator:
    settings = Settings.from_env()
    settings.ensure_directories()
    tools = ToolRegistry.default()
    return Orchestrator(
        settings=settings,
        repository=Repository(settings.database_path),
        ledger=HashChainLedger(settings.data_dir / "audit-ledger.jsonl"),
        planner=build_planner(settings, tools),
        tools=tools,
        policy=PolicyEngine(settings),
        verifiers=VerifierRegistry(),
    )

