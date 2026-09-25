"""Time api-diff on a large synthetic spec.

Generates N paths x 4 operations, each with parameters and a nested $ref'd response schema,
then diffs it against a copy with a few changes.

    uv run python benchmarks/large_spec.py [N]
"""

from __future__ import annotations

import copy
import json
import platform
import sys
import time
from typing import Any

from api_diff import diff


def build(n: int) -> dict[str, Any]:
    schemas = {
        f"Item{i}": {
            "type": "object",
            "required": ["id", "name"],
            "properties": {
                "id": {"type": "integer"},
                "name": {"type": "string", "maxLength": 100},
                "tags": {"type": "array", "items": {"type": "string"}},
                "owner": {"$ref": f"#/components/schemas/Owner{i}"},
            },
        }
        for i in range(n)
    }
    schemas.update(
        {f"Owner{i}": {"type": "object", "properties": {"email": {"type": "string"}}} for i in range(n)}
    )
    paths: dict[str, Any] = {}
    for i in range(n):
        ref = {"$ref": f"#/components/schemas/Item{i}"}
        ok = {"description": "ok", "content": {"application/json": {"schema": ref}}}
        paths[f"/r{i}/{{id}}"] = {
            "parameters": [{"name": "id", "in": "path", "required": True, "schema": {"type": "integer"}}],
            "get": {
                "parameters": [{"name": "q", "in": "query", "schema": {"type": "string"}}],
                "responses": {"200": ok},
            },
            "put": {
                "requestBody": {"content": {"application/json": {"schema": ref}}},
                "responses": {"200": ok},
            },
            "delete": {"responses": {"204": {"description": "gone"}}},
        }
        paths[f"/r{i}"] = {
            "post": {
                "requestBody": {"content": {"application/json": {"schema": ref}}},
                "responses": {"201": ok},
            }
        }
    return {
        "openapi": "3.0.3",
        "info": {"title": "big", "version": "1"},
        "paths": paths,
        "components": {"schemas": schemas},
    }


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 2000
    old = build(n)
    new = copy.deepcopy(old)
    new["components"]["schemas"]["Item0"]["required"] = ["id"]
    del new["paths"]["/r1/{id}"]["delete"]
    size_mb = len(json.dumps(old)) / 1e6
    start = time.perf_counter()
    report = diff(old, new)
    elapsed = time.perf_counter() - start
    print(f"python {platform.python_version()} on {platform.machine()} ({platform.system()})")
    print(f"{n} resources, {4 * n} operations, {size_mb:.1f} MB as JSON")
    print(f"diff took {elapsed:.2f} s; {len(report.changes)} changes, {len(report.breaking)} breaking")


if __name__ == "__main__":
    main()
