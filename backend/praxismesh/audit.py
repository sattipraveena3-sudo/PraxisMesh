from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .domain import new_id, utc_now

GENESIS_HASH = "0" * 64


def _canonical(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


@dataclass(frozen=True, slots=True)
class AuditEvent:
    id: str
    sequence: int
    run_id: str
    event_type: str
    payload: dict[str, Any]
    previous_hash: str
    event_hash: str
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "sequence": self.sequence,
            "run_id": self.run_id,
            "event_type": self.event_type,
            "payload": self.payload,
            "previous_hash": self.previous_hash,
            "event_hash": self.event_hash,
            "created_at": self.created_at,
        }


class HashChainLedger:
    """Append-only JSONL ledger where every event commits to the previous event."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def append(self, run_id: str, event_type: str, payload: dict[str, Any]) -> AuditEvent:
        with self._lock:
            events = list(self._read_events())
            previous_hash = events[-1].event_hash if events else GENESIS_HASH
            event_id = new_id("evt")
            sequence = len(events) + 1
            created_at = utc_now()
            base: dict[str, Any] = {
                "id": event_id,
                "sequence": sequence,
                "run_id": run_id,
                "event_type": event_type,
                "payload": payload,
                "previous_hash": previous_hash,
                "created_at": created_at,
            }
            event_hash = hashlib.sha256(_canonical(base)).hexdigest()
            event = AuditEvent(
                id=event_id,
                sequence=sequence,
                run_id=run_id,
                event_type=event_type,
                payload=payload,
                previous_hash=previous_hash,
                event_hash=event_hash,
                created_at=created_at,
            )
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(event.to_dict(), sort_keys=True, default=str) + "\n")
                handle.flush()
            return event

    def list(self, run_id: str | None = None, limit: int = 500) -> list[AuditEvent]:
        with self._lock:
            events = list(self._read_events())
        if run_id:
            events = [event for event in events if event.run_id == run_id]
        return events[-limit:]

    def verify(self) -> tuple[bool, dict[str, Any]]:
        with self._lock:
            previous_hash = GENESIS_HASH
            checked = 0
            for event in self._read_events():
                checked += 1
                if event.previous_hash != previous_hash:
                    return False, {
                        "checked": checked,
                        "broken_at": event.sequence,
                        "reason": "previous_hash mismatch",
                    }
                base = event.to_dict()
                supplied_hash = base.pop("event_hash")
                expected_hash = hashlib.sha256(_canonical(base)).hexdigest()
                if supplied_hash != expected_hash:
                    return False, {
                        "checked": checked,
                        "broken_at": event.sequence,
                        "reason": "event_hash mismatch",
                    }
                previous_hash = supplied_hash
            return True, {"checked": checked, "head": previous_hash}

    def _read_events(self) -> Iterable[AuditEvent]:
        if not self.path.exists():
            return []
        events: list[AuditEvent] = []
        with self.path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    payload = json.loads(line)
                    events.append(AuditEvent(**payload))
                except (json.JSONDecodeError, TypeError) as exc:
                    raise ValueError(f"Invalid audit event at line {line_number}") from exc
        return events
