from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


@dataclass(frozen=True, slots=True)
class VerificationResult:
    passed: bool
    verifier: str
    evidence: dict[str, Any]
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "verifier": self.verifier,
            "evidence": self.evidence,
            "message": self.message,
        }


Verifier = Callable[[Any, dict[str, Any]], VerificationResult]


def verify_non_empty(output: Any, config: dict[str, Any]) -> VerificationResult:
    passed = output is not None and output != "" and output != {} and output != []
    return VerificationResult(
        passed=passed,
        verifier="non_empty",
        evidence={"output_type": type(output).__name__},
        message="Output is present." if passed else "Output is empty.",
    )


def verify_keys_present(output: Any, config: dict[str, Any]) -> VerificationResult:
    required = [str(item) for item in config.get("keys", [])]
    present = set(output) if isinstance(output, dict) else set()
    missing = sorted(set(required) - present)
    return VerificationResult(
        passed=not missing,
        verifier="keys_present",
        evidence={"required": required, "missing": missing},
        message="All required keys are present." if not missing else f"Missing keys: {missing}",
    )


def verify_artifact(output: Any, config: dict[str, Any]) -> VerificationResult:
    path_value = output.get("path") if isinstance(output, dict) else None
    digest_value = output.get("sha256") if isinstance(output, dict) else None
    if not path_value or not digest_value:
        return VerificationResult(False, "artifact_sha256", {}, "Artifact metadata is incomplete.")
    path = Path(str(path_value))
    if not path.is_file():
        return VerificationResult(False, "artifact_sha256", {"path": str(path)}, "File is missing.")
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    passed = actual == digest_value
    return VerificationResult(
        passed,
        "artifact_sha256",
        {"path": str(path), "expected": digest_value, "actual": actual},
        "Artifact digest matches." if passed else "Artifact digest mismatch.",
    )


def verify_contains(output: Any, config: dict[str, Any]) -> VerificationResult:
    needle = str(config.get("text", ""))
    haystack = output.get("content", "") if isinstance(output, dict) else str(output)
    passed = bool(needle) and needle in str(haystack)
    return VerificationResult(
        passed,
        "contains",
        {"needle": needle, "characters_checked": len(str(haystack))},
        "Expected content found." if passed else "Expected content not found.",
    )


def verify_regex(output: Any, config: dict[str, Any]) -> VerificationResult:
    pattern = str(config.get("pattern", ""))
    text = output.get("content", "") if isinstance(output, dict) else str(output)
    passed = bool(pattern) and re.search(pattern, str(text)) is not None
    return VerificationResult(
        passed,
        "regex",
        {"pattern": pattern},
        "Pattern matched." if passed else "Pattern did not match.",
    )


class VerifierRegistry:
    def __init__(self) -> None:
        self._verifiers: dict[str, Verifier] = {
            "non_empty": verify_non_empty,
            "keys_present": verify_keys_present,
            "artifact_sha256": verify_artifact,
            "contains": verify_contains,
            "regex": verify_regex,
        }

    def verify(self, name: str, output: Any, config: dict[str, Any]) -> VerificationResult:
        try:
            verifier = self._verifiers[name]
        except KeyError as exc:
            raise ValueError(f"unknown verifier: {name}") from exc
        return verifier(output, config)

