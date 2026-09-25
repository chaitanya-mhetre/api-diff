# api-diff

Detect **breaking changes** between two OpenAPI 3.x specs. It works as a CLI, a GitHub Action, or a pytest assertion.

```bash
api-diff openapi-old.yaml openapi-new.yaml      # exits 1 if anything breaks existing clients
```

> Status: 0.1.0, not published to PyPI. **The name `api-diff` must be checked for availability on PyPI before publishing.**
>
> **For production CI, use [oasdiff](https://github.com/oasdiff/oasdiff).** It's mature and far more complete.
> api-diff is primarily a learning project: a readable Python implementation of the same idea.

## Problem
Backend changes like removing an endpoint, making a field required, or changing a type break mobile and web clients,
often only after release. A CI check should catch this on the pull request.

## Why it exists
oasdiff (Go), OpenAPITools/openapi-diff (Java), Atlassian's openapi-diff (TypeScript) and Optic already solve this.
api-diff exists to learn the problem properly: `$ref` graph traversal with cycles, and the request-vs-response
compatibility rules. Its one small practical niche is a **pure-Python** `assert_compatible()` for FastAPI projects, which checks
`app.openapi()` against a committed baseline inside the normal pytest run, with no extra binary.

## Architecture
```
loader (file/URL, YAML/JSON) ──► Resolver (local + relative-file $ref, cached, chain-loop detection)
                                        │
          old Spec ──┐                  ▼
                     ├──► Differ: operations → parameters → request body → responses → schemas
          new Spec ──┘        (every schema comparison carries direction = request | response)
                                        │
                                  [Change(rule_id, location, operation, message)]
                                        │
               ignore file ──► Report ──► text | json | markdown | github annotations
```
- **The key idea: direction.** Request schemas are *contravariant*: the new server must still accept whatever old clients send,
  so tightening breaks. Response schemas are *covariant*: old clients must understand whatever the new server returns, so loosening
  (new enum values, new types, `null`) can break. One schema walker applies the right rule for each side.
- **Rules are data** (`rules.py`): an id, a severity and a written rationale. The differ only emits rule ids.
- **Cycle safety:** `$ref` chains that loop are errors. Recursive *schemas* (a tree node containing nodes) are fine; the walker
  keeps a visited set per traversal.

## Features
- OpenAPI 3.0 and 3.1, including `nullable` vs `type: [.., "null"]`.
- 35 rules (`api-diff rules` prints them with their rationale). They cover operations, required parameters and properties, parameter location,
  media types, status codes, type changes (knowing `number` accepts `integer`), enums, numeric and length bounds, `pattern`, `format`,
  and `allOf` flattening. `oneOf`/`anyOf` are compared pairwise when the shapes match, and flagged for manual review otherwise.
- Renamed path parameters (`/users/{id}` → `/users/{userId}`) are treated as the same route.
- Shared schemas are reported for **every operation** that uses them, so you can see exactly which endpoints are affected.
- An ignore file for accepted changes, where every entry needs a `reason`.

## Tech stack
Python 3.12+, Typer, PyYAML (`safe_load` only), pytest + Hypothesis. There's deliberately no OpenAPI parsing library, since the point was to
write the traversal.

## Quick start
```bash
uv sync
uv run api-diff examples/bookstore-v1.yaml examples/bookstore-v2.yaml
```
```
[BREAKING] operation-removed  DELETE /books/{id}: DELETE /books/{id} was removed
[BREAKING] request-constraint-tightened  GET /books: request maximum tightened 100 -> 50
[BREAKING] request-property-became-required  POST /books: request property 'isbn' is now required
[BREAKING] response-property-became-optional  GET /books: response property 'author' is no longer guaranteed
...
6 breaking, 3 warning, 5 info
```

## API usage
```
api-diff OLD NEW [--format text|json|markdown|github] [--fail-on breaking|warning|info|never] [--ignore FILE]
api-diff rules
```
Exit codes: `0` passed, `1` changes at or above `--fail-on`, `2` input error.

```python
from api_diff import diff

report = diff("old.yaml", "new.yaml")  # paths, URLs or dicts
for change in report.breaking:
    print(change.operation, change.message)
```

**pytest baseline (e.g. FastAPI):**
```python
from pathlib import Path
from api_diff.baseline import assert_compatible
from myapp import app


def test_api_backwards_compatible():
    assert_compatible(app.openapi(), Path("openapi.baseline.json"))


# after an intended breaking change:  API_DIFF_UPDATE_BASELINE=1 pytest
```

**GitHub Action** (`action.yml`, a composite action):
```yaml
on: pull_request
jobs:
  api-diff:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: <owner>/api-diff@v0
        with:
          spec: openapi.yaml
          fail-on: breaking          # optional
          ignore: .api-diff-ignore.yaml   # optional
```
It writes a Markdown table to the job summary and inline annotations, and fails the job on breaking changes.

## Demo
`examples/bookstore-v1.yaml` → `bookstore-v2.yaml` covers a removed operation, a renamed path parameter (not reported),
a tightened limit, a newly required property, a response field becoming optional, and a new enum value.
The action script was exercised locally against a throwaway git repo (base branch vs feature branch); it hasn't run on GitHub yet.

## Testing
`make check` runs ruff, `mypy --strict` and 71 tests:
- 52 table-driven fixture cases (`tests/cases/*.yaml`, each with old/new/expected rule ids)
- a Hypothesis property test (`diff(x, x)` is always empty)
- loader tests for relative-file refs with cycles and ref-chain loops
- CLI tests covering exit codes, formats and ignore files
- baseline-helper tests

## Deployment
PyPI via trusted publishing on a `v*` tag (`.github/workflows/release.yml`, not run yet), and the GitHub Action from a `v0` tag.
There's also a Docker image: `docker run --rm -v "$PWD:/work" api-diff old.yaml new.yaml`.

## Security
- YAML is loaded with `safe_load` only.
- URL inputs have a 10 s timeout, a 20 MB cap, and refuse redirects to non-HTTP schemes.
- The action passes inputs through environment variables, not string interpolation, so they can't inject shell commands.

## Performance
On one laptop: about 0.7 s for an 8,000-operation (2.5 MB) spec, and about 1.8 s for 20,000 operations (6.1 MB), excluding YAML parsing.
See [docs/benchmarks.md](docs/benchmarks.md).

## Engineering trade-offs
- **Conservative on composition.** Analysing `oneOf`/`anyOf` compatibility precisely is hard, so a changed shape becomes a
  `warning` for human review rather than a guess.
- **Removed request parameters/properties are warnings, not breaking.** Most servers ignore unknown input; strict servers
  (`additionalProperties: false`) are the exception.
- **Report per operation.** Shared schemas produce one change per affected operation. That's noisier, but it tells you exactly who's affected.
- **Low false positives over completeness**, because a noisy CI gate gets switched off.

## Limitations
- No Swagger 2.0, AsyncAPI or GraphQL.
- `discriminator`, `additionalProperties`, `readOnly`/`writeOnly`, security schemes, headers and links aren't analysed.
- The GitHub Action compares a single file (`git show base:spec`); specs split across files with relative `$ref`s need the CLI.
- Compared against oasdiff on 10 real spec version pairs ([docs/comparison-oasdiff.md](docs/comparison-oasdiff.md)).
  oasdiff finds more (partly policy: api-diff grades response enum additions and loosened response bounds as
  warnings) and is 2–7× faster. The comparison found and fixed three api-diff bugs.
- No dedicated rules for added response `oneOf`/`anyOf` variants or removed request variants (only a
  `composition-changed` warning), and an added/removed `format` isn't reported.

## Roadmap
- Response headers and security-scheme changes
- `readOnly`/`writeOnly` direction handling
- Dedicated rules for added/removed `oneOf`/`anyOf` variants (the largest real gap found vs oasdiff)

## Contributing
See [CONTRIBUTING.md](CONTRIBUTING.md). Licence: MIT.
