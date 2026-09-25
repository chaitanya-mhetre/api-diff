# Changelog

## 0.1.0 — 2026-09-25 (unreleased, not on PyPI)
- OpenAPI 3.0/3.1 loader (YAML/JSON, file or URL) with local and relative-file `$ref` resolution.
- 35 rules across operations, parameters, request bodies, responses and schemas; direction-aware.
- `allOf` flattening; `oneOf`/`anyOf` compared pairwise when shapes match, otherwise flagged for review.
- Path-parameter renames are matched as the same route.
- Reporters: text, JSON, Markdown, GitHub annotations. Ignore file with mandatory reasons.
- Composite GitHub Action, and a `assert_compatible()` helper for pytest baselines (e.g. FastAPI).
