"""Render a report as text, JSON, Markdown (PR comments) or GitHub workflow annotations."""

from __future__ import annotations

import json

from api_diff.model import Change, Report
from api_diff.rules import SEVERITY_ORDER, Severity

ICONS: dict[Severity, str] = {"breaking": "❌", "warning": "⚠️", "info": "ℹ️"}


def _sorted(changes: list[Change]) -> list[Change]:
    return sorted(changes, key=lambda c: (-SEVERITY_ORDER[c.severity], c.operation or "", c.location))


def _summary(report: Report) -> str:
    counts = {s: len(report.of(s)) for s in ("breaking", "warning", "info")}
    extra = f", {len(report.ignored)} ignored" if report.ignored else ""
    return f"{counts['breaking']} breaking, {counts['warning']} warning, {counts['info']} info{extra}"


def to_text(report: Report, min_severity: Severity = "info") -> str:
    lines = []
    for c in _sorted(report.changes):
        if SEVERITY_ORDER[c.severity] < SEVERITY_ORDER[min_severity]:
            continue
        where = f"{c.operation}: " if c.operation else ""
        lines.append(f"[{c.severity.upper():8}] {c.rule_id}  {where}{c.message}")
        lines.append(f"           at {c.location}")
    lines.append(_summary(report))
    return "\n".join(lines)


def to_json(report: Report) -> str:
    return json.dumps(
        {
            "summary": {s: len(report.of(s)) for s in ("breaking", "warning", "info")},
            "changes": [c.as_dict() for c in _sorted(report.changes)],
            "ignored": [c.as_dict() for c in report.ignored],
        },
        indent=2,
        default=str,
    )


def _md_escape(text: str) -> str:
    return text.replace("|", "\\|")


def to_markdown(report: Report) -> str:
    lines = ["## API changes", "", f"**{_summary(report)}**", ""]
    if report.changes:
        lines += ["| | Rule | Operation | Change |", "|---|---|---|---|"]
        for c in _sorted(report.changes):
            lines.append(
                f"| {ICONS[c.severity]} | `{c.rule_id}` | {_md_escape(c.operation or '-')} | "
                f"{_md_escape(c.message)} |"
            )
    else:
        lines.append("No changes detected.")
    return "\n".join(lines) + "\n"


def to_github(report: Report) -> str:
    """``::error``/``::warning`` workflow commands: GitHub shows them as annotations."""
    level = {"breaking": "error", "warning": "warning", "info": "notice"}
    return "\n".join(
        f"::{level[c.severity]} title=api-diff {c.rule_id}::{c.operation or ''} {c.message} ({c.location})"
        for c in _sorted(report.changes)
    )


RENDERERS = {"text": to_text, "json": to_json, "markdown": to_markdown, "github": to_github}
