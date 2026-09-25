from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest

from api_diff.baseline import assert_compatible

SPEC: dict[str, Any] = {
    "openapi": "3.1.0",
    "info": {"title": "t", "version": "1"},
    "paths": {"/a": {"get": {"responses": {"200": {"description": "ok"}}}}},
}


def test_first_run_writes_baseline(tmp_path: Path) -> None:
    path = tmp_path / "baseline.json"
    assert_compatible(SPEC, path)
    assert path.exists()


def test_breaking_change_fails_and_update_accepts_it(tmp_path: Path) -> None:
    path = tmp_path / "baseline.json"
    assert_compatible(SPEC, path)
    changed = copy.deepcopy(SPEC)
    changed["paths"] = {}
    with pytest.raises(AssertionError, match="operation-removed"):
        assert_compatible(changed, path, update=False)
    assert_compatible(changed, path, update=True)
    assert assert_compatible(changed, path, update=False).changes == []


def test_additive_change_passes(tmp_path: Path) -> None:
    path = tmp_path / "baseline.json"
    assert_compatible(SPEC, path)
    changed = copy.deepcopy(SPEC)
    changed["paths"]["/b"] = {"get": {"responses": {"200": {"description": "ok"}}}}
    report = assert_compatible(changed, path, update=False)
    assert [c.rule_id for c in report.changes] == ["operation-added"]
