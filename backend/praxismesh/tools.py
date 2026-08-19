from __future__ import annotations

import hashlib
import json
import re
import urllib.request
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlparse

from .config import Settings


class ToolFailure(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ToolContext:
    run_id: str
    workspace: Path
    settings: Settings


class Tool(Protocol):
    name: str
    description: str

    def execute(self, arguments: dict[str, Any], context: ToolContext) -> Any: ...


class CaptureGoalTool:
    name = "capture_goal"
    description = "Normalize and capture the user's goal."

    def execute(self, arguments: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        goal = str(arguments.get("goal", "")).strip()
        if not goal:
            raise ToolFailure("goal is required")
        return {"goal": goal, "characters": len(goal), "run_id": context.run_id}


class TextAnalyzeTool:
    name = "text_analyze"
    description = "Compute deterministic text features for planning and verification."
    STOP_WORDS = {
        "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in", "is",
        "it", "of", "on", "or", "that", "the", "this", "to", "with", "we", "you",
    }

    def execute(self, arguments: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        text = str(arguments.get("text", "")).strip()
        tokens = re.findall(r"[A-Za-z0-9'-]+", text.lower())
        keywords = [token for token in tokens if token not in self.STOP_WORDS and len(token) > 2]
        return {
            "word_count": len(tokens),
            "sentence_count": max(1, len(re.findall(r"[.!?]+", text))) if text else 0,
            "top_keywords": [word for word, _ in Counter(keywords).most_common(8)],
            "estimated_complexity": "high" if len(tokens) >= 18 else "medium",
        }


class ComposeReportTool:
    name = "compose_report"
    description = "Create a deterministic Markdown execution brief from verified inputs."

    def execute(self, arguments: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        title = str(arguments.get("title", "PraxisMesh Execution Brief"))
        goal = str(arguments.get("goal", ""))
        analysis = arguments.get("analysis", {})
        if not isinstance(analysis, dict):
            raise ToolFailure("analysis must be an object")
        keywords = ", ".join(str(item) for item in analysis.get("top_keywords", [])) or "none"
        markdown = (
            f"# {title}\n\n"
            f"## Goal\n\n{goal}\n\n"
            "## Deterministic analysis\n\n"
            f"- Words: {analysis.get('word_count', 0)}\n"
            f"- Estimated complexity: {analysis.get('estimated_complexity', 'unknown')}\n"
            f"- Key concepts: {keywords}\n\n"
            "## Safety contract\n\n"
            "Every persistent action is policy-checked, approval-gated, independently "
            "verified, and committed to the audit chain.\n"
        )
        return {"format": "markdown", "content": markdown, "characters": len(markdown)}


def _safe_workspace_path(workspace: Path, relative_path: str) -> Path:
    if not relative_path or Path(relative_path).is_absolute():
        raise ToolFailure("path must be relative to the run workspace")
    resolved_workspace = workspace.resolve()
    candidate = (resolved_workspace / relative_path).resolve()
    if candidate != resolved_workspace and resolved_workspace not in candidate.parents:
        raise ToolFailure("path escapes the run workspace")
    return candidate


class ArtifactWriteTool:
    name = "artifact_write"
    description = "Write a UTF-8 artifact inside the isolated run workspace."

    def execute(self, arguments: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        target = _safe_workspace_path(context.workspace, str(arguments.get("path", "")))
        content = str(arguments.get("content", ""))
        overwrite = bool(arguments.get("overwrite", False))
        if target.exists() and not overwrite:
            raise ToolFailure(f"artifact already exists: {target.name}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        return {
            "path": str(target),
            "relative_path": str(target.relative_to(context.workspace.resolve())),
            "bytes": len(content.encode("utf-8")),
            "sha256": digest,
        }


class ArtifactReadTool:
    name = "artifact_read"
    description = "Read a bounded UTF-8 artifact from the isolated run workspace."

    def execute(self, arguments: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        target = _safe_workspace_path(context.workspace, str(arguments.get("path", "")))
        if not target.is_file():
            raise ToolFailure(f"artifact does not exist: {target.name}")
        content = target.read_text(encoding="utf-8")
        if len(content.encode("utf-8")) > 1_000_000:
            raise ToolFailure("artifact exceeds the 1 MB read limit")
        return {
            "path": str(target),
            "content": content,
            "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        }


class HttpGetTool:
    name = "http_get"
    description = "Read JSON from an explicitly allowlisted HTTPS endpoint."

    def execute(self, arguments: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        url = str(arguments.get("url", ""))
        parsed = urlparse(url)
        if parsed.scheme != "https":
            raise ToolFailure("only HTTPS endpoints are supported")
        if (parsed.hostname or "").lower() not in context.settings.http_allowlist:
            raise ToolFailure("host is not allowlisted")
        request = urllib.request.Request(url, headers={"User-Agent": "PraxisMesh/0.1"})
        with urllib.request.urlopen(  # noqa: S310 - URL is allowlisted above
            request, timeout=context.settings.tool_timeout_seconds
        ) as response:
            body = response.read(500_001)
        if len(body) > 500_000:
            raise ToolFailure("response exceeds the 500 KB limit")
        text = body.decode("utf-8")
        try:
            content: Any = json.loads(text)
        except json.JSONDecodeError:
            content = text
        return {"url": url, "content": content, "bytes": len(body)}


class ToolRegistry:
    def __init__(self, tools: list[Tool]) -> None:
        self._tools = {tool.name: tool for tool in tools}

    @classmethod
    def default(cls) -> "ToolRegistry":
        return cls(
            [
                CaptureGoalTool(),
                TextAnalyzeTool(),
                ComposeReportTool(),
                ArtifactWriteTool(),
                ArtifactReadTool(),
                HttpGetTool(),
            ]
        )

    @property
    def names(self) -> set[str]:
        return set(self._tools)

    def catalog(self) -> list[dict[str, str]]:
        return [
            {"name": tool.name, "description": tool.description}
            for tool in sorted(self._tools.values(), key=lambda item: item.name)
        ]

    def execute(self, name: str, arguments: dict[str, Any], context: ToolContext) -> Any:
        try:
            tool = self._tools[name]
        except KeyError as exc:
            raise ToolFailure(f"unknown tool: {name}") from exc
        return tool.execute(arguments, context)

