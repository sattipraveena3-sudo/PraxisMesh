from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from .config import Settings
from .domain import PlanStep, PolicyDecision, PolicyEffect, RiskLevel


@dataclass(frozen=True, slots=True)
class Guardrail:
    id: str
    explanation: str


class PolicyEngine:
    """Deterministic policy layer that the planner cannot override."""

    SAFE_TOOLS = {"capture_goal", "text_analyze", "compose_report", "artifact_read"}
    DESTRUCTIVE_PATTERNS = (
        r"\brm\s+-rf\b",
        r"\bmkfs\b",
        r"\bdd\s+if=",
        r"\b(drop|truncate)\s+(database|table)\b",
        r"\bshutdown\b",
        r"\breboot\b",
        r":\(\)\s*\{",
    )
    SECRET_PATTERNS = (
        r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
        r"\b(?:sk|ghp|xox[baprs])-[-A-Za-z0-9_]{16,}\b",
    )

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def evaluate(self, step: PlanStep) -> PolicyDecision:
        serialized = json.dumps(step.arguments, sort_keys=True, default=str)

        for pattern in self.SECRET_PATTERNS:
            if re.search(pattern, serialized, flags=re.IGNORECASE):
                return self._decision(
                    PolicyEffect.DENY,
                    RiskLevel.CRITICAL,
                    "secret-material",
                    "Possible secret material may not enter a tool call.",
                )

        if step.tool == "shell":
            for pattern in self.DESTRUCTIVE_PATTERNS:
                if re.search(pattern, serialized, flags=re.IGNORECASE):
                    return self._decision(
                        PolicyEffect.DENY,
                        RiskLevel.CRITICAL,
                        "destructive-command",
                        "The requested command matches a destructive-operation rule.",
                    )
            return self._decision(
                PolicyEffect.REQUIRE_APPROVAL,
                RiskLevel.HIGH,
                "shell-execution",
                "Arbitrary command execution requires explicit human approval.",
            )

        if step.tool == "artifact_write":
            path = str(step.arguments.get("path", ""))
            if path.startswith(("/", "~")) or ".." in path.split("/"):
                return self._decision(
                    PolicyEffect.DENY,
                    RiskLevel.HIGH,
                    "workspace-boundary",
                    "Artifacts must stay inside the run workspace.",
                )
            return self._decision(
                PolicyEffect.REQUIRE_APPROVAL,
                RiskLevel.MEDIUM,
                "persistent-write",
                "Creating a persistent artifact requires approval.",
            )

        if step.tool == "http_get":
            if not self.settings.allow_http:
                return self._decision(
                    PolicyEffect.DENY,
                    RiskLevel.HIGH,
                    "network-disabled",
                    "Outbound HTTP is disabled by configuration.",
                )
            hostname = (urlparse(str(step.arguments.get("url", ""))).hostname or "").lower()
            if hostname not in self.settings.http_allowlist:
                return self._decision(
                    PolicyEffect.DENY,
                    RiskLevel.HIGH,
                    "host-not-allowlisted",
                    f"Outbound host '{hostname}' is not allowlisted.",
                )
            return self._decision(
                PolicyEffect.REQUIRE_APPROVAL,
                RiskLevel.MEDIUM,
                "external-read",
                "Reading an external system requires approval.",
            )

        if step.tool in self.SAFE_TOOLS:
            return self._decision(
                PolicyEffect.ALLOW,
                RiskLevel.LOW,
                "read-or-transform",
                "The step is a bounded, local, non-mutating operation.",
            )

        return self._decision(
            PolicyEffect.DENY,
            RiskLevel.HIGH,
            "unknown-tool",
            f"Tool '{step.tool}' has no policy definition.",
        )

    @staticmethod
    def _decision(
        effect: PolicyEffect,
        risk: RiskLevel,
        rule_id: str,
        reason: str,
    ) -> PolicyDecision:
        return PolicyDecision(effect=effect, risk=risk, reasons=[reason], rule_ids=[rule_id])

