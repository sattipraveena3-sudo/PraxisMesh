from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from .domain import ApprovalRecord, RunRecord, RunStatus, utc_now


class Repository:
    """SQLite persistence with a small domain-focused API."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def _initialize(self) -> None:
        with self._lock, self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY,
                    goal TEXT NOT NULL,
                    status TEXT NOT NULL,
                    planner TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status);
                CREATE INDEX IF NOT EXISTS idx_runs_created ON runs(created_at DESC);

                CREATE TABLE IF NOT EXISTS approvals (
                    id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    step_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    requested_at TEXT NOT NULL,
                    decided_at TEXT,
                    FOREIGN KEY(run_id) REFERENCES runs(id)
                );
                CREATE INDEX IF NOT EXISTS idx_approvals_run ON approvals(run_id, status);
                """
            )

    def save_run(self, run: RunRecord) -> RunRecord:
        run.updated_at = utc_now()
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO runs(id, goal, status, planner, payload, created_at, updated_at)
                VALUES(?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    goal=excluded.goal,
                    status=excluded.status,
                    planner=excluded.planner,
                    payload=excluded.payload,
                    updated_at=excluded.updated_at
                """,
                (
                    run.id,
                    run.goal,
                    run.status.value,
                    run.planner,
                    run.as_json(),
                    run.created_at,
                    run.updated_at,
                ),
            )
        return run

    def get_run(self, run_id: str) -> RunRecord | None:
        with self._connect() as connection:
            row = connection.execute("SELECT payload FROM runs WHERE id = ?", (run_id,)).fetchone()
        return RunRecord.from_dict(json.loads(row["payload"])) if row else None

    def list_runs(self, limit: int = 50) -> list[RunRecord]:
        safe_limit = max(1, min(limit, 200))
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload FROM runs ORDER BY created_at DESC LIMIT ?", (safe_limit,)
            ).fetchall()
        return [RunRecord.from_dict(json.loads(row["payload"])) for row in rows]

    def save_approval(self, approval: ApprovalRecord) -> ApprovalRecord:
        payload = json.dumps(approval.to_dict(), sort_keys=True, separators=(",", ":"))
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO approvals(
                    id, run_id, step_id, status, payload, requested_at, decided_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    status=excluded.status,
                    payload=excluded.payload,
                    decided_at=excluded.decided_at
                """,
                (
                    approval.id,
                    approval.run_id,
                    approval.step_id,
                    approval.status,
                    payload,
                    approval.requested_at,
                    approval.decided_at,
                ),
            )
        return approval

    def get_approval(self, approval_id: str) -> ApprovalRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM approvals WHERE id = ?", (approval_id,)
            ).fetchone()
        return ApprovalRecord.from_dict(json.loads(row["payload"])) if row else None

    def find_pending_approval(self, run_id: str, step_id: str) -> ApprovalRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT payload FROM approvals
                WHERE run_id = ? AND step_id = ? AND status = 'pending'
                ORDER BY requested_at DESC LIMIT 1
                """,
                (run_id, step_id),
            ).fetchone()
        return ApprovalRecord.from_dict(json.loads(row["payload"])) if row else None

    def find_latest_approval(self, run_id: str, step_id: str) -> ApprovalRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT payload FROM approvals
                WHERE run_id = ? AND step_id = ?
                ORDER BY requested_at DESC LIMIT 1
                """,
                (run_id, step_id),
            ).fetchone()
        return ApprovalRecord.from_dict(json.loads(row["payload"])) if row else None

    def list_approvals(
        self, run_id: str | None = None, status: str | None = None
    ) -> list[ApprovalRecord]:
        clauses: list[str] = []
        values: list[Any] = []
        if run_id:
            clauses.append("run_id = ?")
            values.append(run_id)
        if status:
            clauses.append("status = ?")
            values.append(status)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT payload FROM approvals{where} ORDER BY requested_at DESC", values
            ).fetchall()
        return [ApprovalRecord.from_dict(json.loads(row["payload"])) for row in rows]

    def metrics(self) -> dict[str, Any]:
        with self._connect() as connection:
            run_rows = connection.execute(
                "SELECT status, COUNT(*) AS count FROM runs GROUP BY status"
            ).fetchall()
            pending = connection.execute(
                "SELECT COUNT(*) AS count FROM approvals WHERE status = 'pending'"
            ).fetchone()["count"]
            total = connection.execute("SELECT COUNT(*) AS count FROM runs").fetchone()["count"]
        by_status = {status.value: 0 for status in RunStatus}
        by_status.update({row["status"]: row["count"] for row in run_rows})
        completed = by_status[RunStatus.SUCCEEDED.value] + by_status[RunStatus.FAILED.value]
        success_rate = (
            round(by_status[RunStatus.SUCCEEDED.value] / completed, 4) if completed else 0.0
        )
        return {
            "runs_total": total,
            "runs_by_status": by_status,
            "pending_approvals": pending,
            "success_rate": success_rate,
        }
