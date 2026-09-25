"""Summarise comparison/results/*.json (written by compare.py) as Markdown tables.

    uv run python comparison/analyze.py > comparison/results/summary.md

"Misses" are oasdiff ERR findings on operations api-diff did not flag as breaking, grouped by
oasdiff rule id. "Extras" are api-diff breaking findings on operations oasdiff did not flag.
Classifying each group (policy difference vs. api-diff gap vs. oasdiff noise) is done by hand in
docs/comparison-oasdiff.md.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

RESULTS = Path(__file__).parent / "results"


def norm(method: str, path: str) -> str:
    return f"{method.upper()} {re.sub(r'\{[^}]*\}', '{}', path)}"


def main() -> None:
    summary = json.loads((RESULTS / "summary.json").read_text())
    print(f"oasdiff version: `{summary['oasdiff_version']}`\n")
    print(
        "| pair | api-diff ops | oasdiff ops | both | only api-diff | only oasdiff "
        "| time api-diff / oasdiff |"
    )
    print("|---|---:|---:|---:|---:|---:|---|")
    misses: Counter[str] = Counter()
    extras: Counter[str] = Counter()
    for row in summary["pairs"]:
        ours = row["api_diff"]
        if "oasdiff_error" in row:
            print(
                f"| {row['id']} | {len(ours['breaking_ops'])} | oasdiff error | – | – | – | "
                f"{ours['seconds']}s / – |"
            )
            continue
        theirs = row["oasdiff"]
        print(
            f"| {row['id']} | {len(ours['breaking_ops'])} | {len(theirs['breaking_ops'])} | "
            f"{len(row['both'])} | {len(row['only_api_diff'])} | {len(row['only_oasdiff'])} | "
            f"{ours['seconds']}s / {theirs['seconds']}s |"
        )
        detail = json.loads((RESULTS / f"{row['id']}.json").read_text())
        only_theirs, only_ours = set(row["only_oasdiff"]), set(row["only_api_diff"])
        for c in detail["oasdiff_changes"]:
            if c.get("operation") and norm(c["operation"], c["path"]) in only_theirs:
                misses[c["id"]] += 1
        for c in detail["api_diff_changes"]:
            if c["operation"] and norm(*c["operation"].split(" ", 1)) in only_ours:
                extras[c["rule_id"]] += 1
    print("\n**oasdiff ERR findings on operations api-diff did not flag (by oasdiff rule):**\n")
    print("| oasdiff rule | findings |\n|---|---:|")
    for rule, n in misses.most_common():
        print(f"| `{rule}` | {n} |")
    print("\n**api-diff breaking findings on operations oasdiff did not flag (by api-diff rule):**\n")
    print("| api-diff rule | findings |\n|---|---:|")
    for rule, n in extras.most_common():
        print(f"| `{rule}` | {n} |")


if __name__ == "__main__":
    main()
