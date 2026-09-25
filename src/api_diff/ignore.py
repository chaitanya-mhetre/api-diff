"""Suppressing known, accepted changes. Every suppression must say *why*.

```yaml
ignore:
  - rule: response-optional-property-removed
    location: "/paths/~1legacy*"      # fnmatch glob on the change location (optional)
    reason: "legacy endpoint, clients migrated in v4"
```
"""

from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path

import yaml

from api_diff.loader import SpecError
from api_diff.model import Change, Report
from api_diff.rules import RULES


@dataclass(frozen=True)
class IgnoreEntry:
    rule: str
    reason: str
    location: str = "*"
    operation: str = "*"

    def matches(self, change: Change) -> bool:
        return (
            (self.rule == "*" or self.rule == change.rule_id)
            and fnmatchcase(change.location, self.location)
            and fnmatchcase(change.operation or "", self.operation)
        )


def load_ignore(path: Path) -> list[IgnoreEntry]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    entries = []
    for i, item in enumerate(raw.get("ignore") or []):
        if not isinstance(item, dict) or not item.get("reason"):
            raise SpecError(f"{path}: ignore entry {i} needs a 'reason'")
        rule = str(item.get("rule", "*"))
        if rule != "*" and rule not in RULES:
            raise SpecError(f"{path}: ignore entry {i}: unknown rule {rule!r}")
        entries.append(
            IgnoreEntry(
                rule=rule,
                reason=str(item["reason"]),
                location=str(item.get("location", "*")),
                operation=str(item.get("operation", "*")),
            )
        )
    return entries


def apply_ignores(report: Report, entries: list[IgnoreEntry]) -> Report:
    kept: list[Change] = []
    ignored = list(report.ignored)
    for change in report.changes:
        (ignored if any(e.matches(change) for e in entries) else kept).append(change)
    return Report(changes=kept, ignored=ignored)
