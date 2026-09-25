"""Compare api-diff against oasdiff on real historical versions of public OpenAPI specs.

Usage (from the repo root):
    uv run python comparison/compare.py              # fetch specs, run both tools, write results/
    OASDIFF=/path/to/oasdiff uv run python comparison/compare.py

Specs are downloaded by exact commit SHA into comparison/.cache/ (gitignored) and are never
committed. Needs network access and the oasdiff binary (on PATH or via $OASDIFF).

Comparison unit: the set of *operations* ("METHOD /path/{}") each tool reports as having at least
one breaking change. For oasdiff "breaking" means level ERR; for api-diff severity "breaking".
Path parameter names are normalised to "{}" on both sides, because both tools treat a renamed
path parameter as the same route.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

from api_diff import diff

HERE = Path(__file__).parent
CACHE = HERE / ".cache"
RESULTS = HERE / "results"
RAW = "https://raw.githubusercontent.com/{repo}/{sha}/{path}"


def fetch(repo: str, sha: str, path: str) -> Path:
    dest = CACHE / repo.replace("/", "__") / sha / Path(path).name
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        url = RAW.format(repo=repo, sha=sha, path=path)
        with urllib.request.urlopen(url, timeout=120) as resp:  # noqa: S310 (fixed https host)
            dest.write_bytes(resp.read())
    return dest


def norm_op(method: str, path: str) -> str:
    return f"{method.upper()} {re.sub(r'\{[^}]*\}', '{}', path)}"


def run_api_diff(old: Path, new: Path) -> dict[str, Any]:
    start = time.perf_counter()
    report = diff(old, new)
    seconds = time.perf_counter() - start
    breaking_ops = sorted({norm_op(*c.operation.split(" ", 1)) for c in report.breaking if c.operation})
    return {
        "seconds": round(seconds, 2),
        "breaking_changes": len(report.breaking),
        "warnings": len(report.warnings),
        "breaking_ops": breaking_ops,
        "global_breaking": [c.as_dict() for c in report.breaking if not c.operation],
        "changes": [c.as_dict() for c in report.breaking],
    }


def run_oasdiff(binary: str, old: Path, new: Path) -> dict[str, Any]:
    start = time.perf_counter()
    cmd = [binary, "breaking", str(old), str(new), "-f", "json", "--auto-upgrade"]
    if shutil.which("systemd-run"):
        # Cap memory so a huge spec can't push the machine into OOM (oasdiff was killed on Stripe).
        cmd = [
            "systemd-run",
            "--user",
            "--scope",
            "--quiet",
            "-p",
            "MemoryMax=2G",
            "-p",
            "MemorySwapMax=0",
            *cmd,
        ]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
    )
    seconds = time.perf_counter() - start
    if proc.returncode not in (0, 1):
        raise RuntimeError(f"oasdiff failed ({proc.returncode}): {proc.stderr[:500]}")
    items: list[dict[str, Any]] = json.loads(proc.stdout or "[]") or []
    errors = [i for i in items if i.get("level") == 3]
    warns = [i for i in items if i.get("level") == 2]
    ops = sorted({norm_op(i["operation"], i["path"]) for i in errors if i.get("operation")})
    return {
        "seconds": round(seconds, 2),
        "breaking_changes": len(errors),
        "warnings": len(warns),
        "breaking_ops": ops,
        "changes": errors,
    }


def main() -> int:
    binary = os.environ.get("OASDIFF") or shutil.which("oasdiff")
    if not binary:
        print("oasdiff not found: put it on PATH or set $OASDIFF", file=sys.stderr)
        return 2
    version = subprocess.run([binary, "--version"], capture_output=True, text=True).stdout.strip()
    pairs = json.loads((HERE / "pairs.json").read_text())["pairs"]
    RESULTS.mkdir(exist_ok=True)
    summary = []
    for p in pairs:
        old = fetch(p["repo"], p["base"], p["path"])
        new = fetch(p["repo"], p["revision"], p["path"])
        ours = run_api_diff(old, new)
        try:
            theirs = run_oasdiff(binary, old, new)
        except RuntimeError as exc:  # e.g. oasdiff rejects a spec that api-diff accepts
            print(f"{p['id']:<28} oasdiff error: {str(exc)[:160]}")
            summary.append(
                {
                    "id": p["id"],
                    "api_diff": {k: v for k, v in ours.items() if k != "changes"},
                    "oasdiff_error": str(exc)[:500],
                }
            )
            continue
        a, b = set(ours["breaking_ops"]), set(theirs["breaking_ops"])
        row = {
            "id": p["id"],
            "api_diff": {k: v for k, v in ours.items() if k != "changes"},
            "oasdiff": {k: v for k, v in theirs.items() if k != "changes"},
            "both": sorted(a & b),
            "only_api_diff": sorted(a - b),
            "only_oasdiff": sorted(b - a),
        }
        (RESULTS / f"{p['id']}.json").write_text(
            json.dumps(
                {**row, "api_diff_changes": ours["changes"], "oasdiff_changes": theirs["changes"]},
                indent=2,
                default=str,
            )
        )
        summary.append(row)
        print(
            f"{p['id']:<28} api-diff ops={len(a):>4} oasdiff ops={len(b):>4} "
            f"both={len(a & b):>4} only-ours={len(a - b):>4} only-theirs={len(b - a):>4} "
            f"({ours['seconds']}s vs {theirs['seconds']}s)"
        )
    (RESULTS / "summary.json").write_text(
        json.dumps({"oasdiff_version": version, "pairs": summary}, indent=2)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
