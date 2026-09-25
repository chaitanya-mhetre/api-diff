"""api-diff: detect breaking changes between two OpenAPI 3.x specs.

from api_diff import diff
report = diff("old.yaml", "new.yaml")
assert not report.breaking
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from api_diff.differ import diff_specs
from api_diff.loader import SpecError, load_spec
from api_diff.model import Change, Report
from api_diff.rules import RULES, Rule

__version__ = "0.1.0"


def diff(old: str | Path | dict[str, Any], new: str | Path | dict[str, Any]) -> Report:
    """Compare two specs (file paths, URLs, or already-parsed dicts)."""
    return Report(changes=diff_specs(load_spec(old), load_spec(new)))


__all__ = ["RULES", "Change", "Report", "Rule", "SpecError", "diff"]
