"""Table-driven rule tests: one YAML file per case in tests/cases/.

A case holds ``old_paths``/``new_paths`` (and optional ``*_components``, ``version``) plus the
sorted list of ``expected`` rule ids.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from api_diff import diff

CASES = sorted(Path(__file__).parent.joinpath("cases").glob("*.yaml"))


def build(case: dict[str, Any], side: str) -> dict[str, Any]:
    spec: dict[str, Any] = {
        "openapi": case.get("version", "3.0.3"),
        "info": {"title": "t", "version": "1"},
        "paths": case[f"{side}_paths"],
    }
    if f"{side}_components" in case:
        spec["components"] = case[f"{side}_components"]
    return spec


@pytest.mark.parametrize("path", CASES, ids=[p.stem for p in CASES])
def test_case(path: Path) -> None:
    case = yaml.safe_load(path.read_text())
    report = diff(build(case, "old"), build(case, "new"))
    assert report.rule_ids() == sorted(case["expected"]), [c.message for c in report.changes]


def test_there_are_at_least_40_cases() -> None:
    assert len(CASES) >= 40
