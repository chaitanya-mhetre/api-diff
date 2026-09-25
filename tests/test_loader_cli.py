from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from typer.testing import CliRunner

from api_diff import SpecError, diff
from api_diff.cli import app, main
from api_diff.loader import Resolver, load_spec

ROOT = Path(__file__).parent.parent
EX = ROOT / "examples"
FILES = Path(__file__).parent / "files"
runner = CliRunner()


def test_example_upgrade_finds_the_expected_breaking_changes() -> None:
    report = diff(EX / "bookstore-v1.yaml", EX / "bookstore-v2.yaml")
    assert sorted({c.rule_id for c in report.breaking}) == [
        "operation-removed",  # DELETE /books/{id}
        "request-constraint-tightened",  # limit maximum 100 -> 50
        "request-property-became-required",  # isbn
        "response-property-became-optional",  # author
    ]
    assert {c.rule_id for c in report.warnings} == {"response-enum-value-added"}
    # the path-parameter rename {id} -> {bookId} is NOT reported as a removed GET
    assert not any(c.operation == "GET /books/{id}" for c in report.changes)


def test_relative_file_refs_with_cycles_resolve() -> None:
    report = diff(FILES / "root.yaml", FILES / "root.yaml")
    assert report.changes == []


def test_ref_chain_loop_is_an_error() -> None:
    doc: dict[str, Any] = {"a": {"$ref": "#/b"}, "b": {"$ref": "#/a"}}
    resolver = Resolver(documents={"<memory>": doc})
    with pytest.raises(SpecError, match="circular"):
        resolver.deref({"$ref": "#/a"}, "<memory>")


def test_unresolvable_ref() -> None:
    resolver = Resolver(documents={"<memory>": {}})
    with pytest.raises(SpecError, match="unresolvable"):
        resolver.deref({"$ref": "#/components/schemas/Nope"}, "<memory>")


def test_json_pointer_escapes() -> None:
    doc = {"paths": {"/a/b": {"x~y": 1}}}
    resolver = Resolver(documents={"<memory>": doc})
    assert resolver.deref({"$ref": "#/paths/~1a~1b"}, "<memory>")[0] == {"x~y": 1}


@pytest.mark.parametrize(
    ("text", "match"),
    [("swagger: '2.0'\n", "only OpenAPI 3.x"), ("- a\n", "top level"), ("a: [\n", "invalid YAML")],
)
def test_bad_inputs(tmp_path: Path, text: str, match: str) -> None:
    path = tmp_path / "s.yaml"
    path.write_text(text)
    with pytest.raises(SpecError, match=match):
        load_spec(path)


def test_json_input(tmp_path: Path) -> None:
    path = tmp_path / "s.json"
    path.write_text(json.dumps({"openapi": "3.0.0", "info": {"title": "t", "version": "1"}, "paths": {}}))
    assert load_spec(path).version == "3.0.0"


# ---- property test ------------------------------------------------------------------------------

schemas = st.recursive(
    st.sampled_from([{"type": "string"}, {"type": "integer"}, {"type": "number", "nullable": True}]),
    lambda inner: st.one_of(
        st.builds(lambda items: {"type": "array", "items": items}, inner),
        st.builds(
            lambda props: {"type": "object", "properties": props, "required": sorted(props)[:1]},
            st.dictionaries(st.text("abc", min_size=1, max_size=3), inner, max_size=3),
        ),
    ),
    max_leaves=8,
)


@settings(max_examples=60, deadline=None)
@given(schemas)
def test_diff_of_a_spec_with_itself_is_empty(schema: dict[str, Any]) -> None:
    spec = {
        "openapi": "3.0.3",
        "info": {"title": "t", "version": "1"},
        "paths": {
            "/x": {
                "post": {
                    "requestBody": {"content": {"application/json": {"schema": schema}}},
                    "responses": {
                        "200": {"description": "ok", "content": {"application/json": {"schema": schema}}}
                    },
                }
            }
        },
    }
    assert diff(spec, spec).changes == []


# ---- CLI ----------------------------------------------------------------------------------------


def test_cli_exit_codes() -> None:
    v1, v2 = str(EX / "bookstore-v1.yaml"), str(EX / "bookstore-v2.yaml")
    assert runner.invoke(app, ["diff", v1, v1]).exit_code == 0
    result = runner.invoke(app, ["diff", v1, v2])
    assert result.exit_code == 1 and "operation-removed" in result.output
    assert runner.invoke(app, ["diff", v1, v2, "--fail-on", "never"]).exit_code == 0
    assert runner.invoke(app, ["diff", v1, "missing.yaml"]).exit_code == 2


def test_cli_formats() -> None:
    v1, v2 = str(EX / "bookstore-v1.yaml"), str(EX / "bookstore-v2.yaml")
    data = json.loads(runner.invoke(app, ["diff", v1, v2, "-f", "json"]).output)
    assert data["summary"]["breaking"] == 6  # Book changes reported for each operation using it
    md = runner.invoke(app, ["diff", v1, v2, "-f", "markdown"]).output
    assert md.startswith("## API changes") and "| ❌ |" in md
    gh = runner.invoke(app, ["diff", v1, v2, "-f", "github"]).output
    assert "::error title=api-diff operation-removed::" in gh


def test_cli_ignore_file_requires_reason(tmp_path: Path) -> None:
    v1, v2 = str(EX / "bookstore-v1.yaml"), str(EX / "bookstore-v2.yaml")
    ok = runner.invoke(app, ["diff", v1, v2, "--ignore", str(EX / "ignore.yaml"), "--fail-on", "warning"])
    assert "3 ignored" in ok.output and ok.exit_code == 1  # breaking changes still fail
    bad = tmp_path / "i.yaml"
    bad.write_text("ignore:\n  - rule: operation-removed\n")
    assert runner.invoke(app, ["diff", v1, v2, "--ignore", str(bad)]).exit_code == 2


def test_rules_command_lists_every_rule() -> None:
    out = runner.invoke(app, ["rules"]).output
    assert "operation-removed" in out and "why:" in out


def test_shorthand_entry_point(monkeypatch: pytest.MonkeyPatch) -> None:
    v1 = str(EX / "bookstore-v1.yaml")
    monkeypatch.setattr(sys, "argv", ["api-diff", v1, v1])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 0
