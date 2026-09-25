# Changelog

## Unreleased
- **Comparison with oasdiff** on 10 real historical spec pairs (OpenAI, Twilio, Box, PagerDuty, Kubernetes):
  `comparison/` scripts, `make compare`, results in `docs/comparison-oasdiff.md`.
- Fix: unwrap OpenAPI 3.1 nullable unions (`anyOf`/`oneOf: [X, {type: "null"}]`) so changes inside `X` are compared.
  Removed 94 false `response-property-removed` findings on OpenAI's 3.0 → 3.1 migration.
- Fix: when a `oneOf`/`anyOf` gains or loses members, still compare members with the same `$ref`
  (a breaking change inside a surviving variant was hidden).
- Fix: treat 3.0 boolean `exclusiveMinimum`/`exclusiveMaximum` like the 3.1 numeric form, and compare bounds
  above 2^53 as doubles (int64 limits re-serialised by JS were reported as tightened).

## 0.1.0 — 2026-09-25 (unreleased, not on PyPI)
- OpenAPI 3.0/3.1 loader (YAML/JSON, file or URL) with local and relative-file `$ref` resolution.
- 35 rules across operations, parameters, request bodies, responses and schemas; direction-aware.
- `allOf` flattening; `oneOf`/`anyOf` compared pairwise when shapes match, otherwise flagged for review.
- Path-parameter renames are matched as the same route.
- Reporters: text, JSON, Markdown, GitHub annotations. Ignore file with mandatory reasons.
- Composite GitHub Action, and a `assert_compatible()` helper for pytest baselines (e.g. FastAPI).
