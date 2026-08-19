from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class Settings:
    environment: str
    host: str
    port: int
    data_dir: Path
    database_path: Path
    workspace_root: Path
    planner: str
    openai_model: str
    allow_http: bool
    http_allowlist: tuple[str, ...]
    auto_approve_low_risk: bool
    max_steps: int
    tool_timeout_seconds: int

    @classmethod
    def from_env(cls) -> "Settings":
        data_dir = Path(os.getenv("PRAXISMESH_DATA_DIR", ".praxismesh")).resolve()
        database = Path(
            os.getenv("PRAXISMESH_DATABASE", str(data_dir / "praxismesh.db"))
        ).resolve()
        workspace = Path(
            os.getenv("PRAXISMESH_WORKSPACE", str(data_dir / "workspaces"))
        ).resolve()
        allowlist = tuple(
            item.strip().lower()
            for item in os.getenv("PRAXISMESH_HTTP_ALLOWLIST", "api.github.com").split(",")
            if item.strip()
        )
        return cls(
            environment=os.getenv("PRAXISMESH_ENV", "development"),
            host=os.getenv("PRAXISMESH_HOST", "0.0.0.0"),
            port=int(os.getenv("PRAXISMESH_PORT", "8000")),
            data_dir=data_dir,
            database_path=database,
            workspace_root=workspace,
            planner=os.getenv("PRAXISMESH_PLANNER", "deterministic").lower(),
            openai_model=os.getenv("PRAXISMESH_OPENAI_MODEL", "gpt-5.6"),
            allow_http=_as_bool(os.getenv("PRAXISMESH_ALLOW_HTTP")),
            http_allowlist=allowlist,
            auto_approve_low_risk=_as_bool(
                os.getenv("PRAXISMESH_AUTO_APPROVE_LOW_RISK"), True
            ),
            max_steps=int(os.getenv("PRAXISMESH_MAX_STEPS", "20")),
            tool_timeout_seconds=int(os.getenv("PRAXISMESH_TOOL_TIMEOUT_SECONDS", "20")),
        )

    def ensure_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.workspace_root.mkdir(parents=True, exist_ok=True)

