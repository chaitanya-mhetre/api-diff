"""Compare a live spec (e.g. FastAPI's ``app.openapi()``) with a committed baseline, in a test.

    def test_api_is_backwards_compatible():
        assert_compatible(app.openapi(), Path("openapi.baseline.json"))

Run with ``API_DIFF_UPDATE_BASELINE=1`` after an *intended* change to rewrite the baseline.
No binary and no CI plugin needed: it's just a pytest assertion.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from api_diff import diff
from api_diff.model import Report
from api_diff.reporters import to_text
from api_diff.rules import Severity


def assert_compatible(
    current: dict[str, Any],
    baseline: Path,
    fail_on: Severity = "breaking",
    update: bool | None = None,
) -> Report:
    if update is None:
        update = os.environ.get("API_DIFF_UPDATE_BASELINE") == "1"
    if update or not baseline.exists():
        baseline.write_text(json.dumps(current, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return Report()
    report = diff(json.loads(baseline.read_text(encoding="utf-8")), current)
    if report.fails(fail_on):
        raise AssertionError(
            f"API changes at '{fail_on}' level vs {baseline}:\n{to_text(report, fail_on)}\n"
            "If this change is intended, re-run with API_DIFF_UPDATE_BASELINE=1."
        )
    return report
