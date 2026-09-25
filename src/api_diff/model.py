"""Changes and the report that collects them."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from api_diff.rules import RULES, SEVERITY_ORDER, Severity


@dataclass(frozen=True)
class Change:
    rule_id: str
    location: str  # JSON-pointer-like path into the *new* (or old, if removed) spec
    operation: str | None  # e.g. "GET /users/{}"
    message: str
    old: Any = None
    new: Any = None

    @property
    def severity(self) -> Severity:
        return RULES[self.rule_id].severity

    def as_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "severity": self.severity,
            "operation": self.operation,
            "location": self.location,
            "message": self.message,
            "old": self.old,
            "new": self.new,
        }


@dataclass
class Report:
    changes: list[Change] = field(default_factory=list)
    ignored: list[Change] = field(default_factory=list)

    def of(self, severity: Severity) -> list[Change]:
        return [c for c in self.changes if c.severity == severity]

    @property
    def breaking(self) -> list[Change]:
        return self.of("breaking")

    @property
    def warnings(self) -> list[Change]:
        return self.of("warning")

    def fails(self, fail_on: Severity) -> bool:
        threshold = SEVERITY_ORDER[fail_on]
        return any(SEVERITY_ORDER[c.severity] >= threshold for c in self.changes)

    def rule_ids(self) -> list[str]:
        return sorted(c.rule_id for c in self.changes)
