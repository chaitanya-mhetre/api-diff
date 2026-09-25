# api-diff
> Detect breaking changes between two OpenAPI specs, as a CLI and a GitHub Action.

## 1. Problem & why it exists
When a backend changes its API (removes an endpoint, makes a field required, changes a type), mobile and web clients break, often only after release. Teams need a CI check that fails the PR on breaking changes.

**Existing tools in this space (strong and mature):**
- **oasdiff** (Go): comprehensive OpenAPI diff and breaking-change detection, with a GitHub Action. It's the de-facto standard.
- **openapi-diff** (OpenAPITools, Java) and **openapi-diff** (Atlassian, TypeScript).
- **Optic**: API change management that includes breaking-change checks.

**Honest positioning:** this is **primarily a learning project**. Building a spec differ teaches schema traversal, `$ref` resolution, the semantics of request vs response compatibility, and GitHub Action packaging. If it's published, the README must point to oasdiff for production use.

A possible small differentiator, **only if actually built**: a Python-native library API (`from api_diff import diff`) for FastAPI projects, e.g. a pytest plugin that compares `app.openapi()` against a committed baseline, so no binary is needed in CI.

## 2. What this proves to an employer
| Skill | Target requirement |
|---|---|
| Deep REST/OpenAPI knowledge, API versioning | Backend roles (Zeko, EaseOps, Atlassian) |
| Recursive algorithms over trees/graphs (`$ref` cycles) | DSA applied to real code |
| CI/CD integration (GitHub Actions) | CI/CD (Razorpay, EaseOps) |
| Careful rule design with test-driven development | Testing culture |

## 3. Scope
### In scope (v1)
- OpenAPI 3.0 and 3.1, in JSON or YAML, from local files (and URLs in M4).
- `$ref` resolution, both local and relative-file, with cycle detection.
- Change detection:
  - endpoints/operations removed
  - parameters added/removed or made required
  - request body fields removed or made required
  - response fields removed
  - type changes
  - enum values removed (in responses) or added (in requests)
  - response status codes removed
- Each change gets a severity (`breaking` / `warning` / `info`), with a documented reason per rule.
- Output formats: text, JSON, Markdown (for PR comments), and exit codes for CI.
- GitHub Action: compares against the base-branch spec and posts a Markdown summary.

### Out of scope (explicitly)
- Swagger 2.0 (maybe later, via conversion).
- AsyncAPI, GraphQL, gRPC.
- Semantic changes that the schema can't express.

## 4. Architecture
```
loader (file/URL, YAML/JSON) ─► ref resolver (cycle-safe) ─► normalized model
                                                              │
                          old model ──┐                       ▼
                                      ├─► differ (walks paths/ops/params/schemas)
                          new model ──┘            │
                                                   ▼
                                  rule engine (ChangeRule classes → Change objects)
                                                   │
                                 reporters: text | json | markdown | github-annotations
```
- **Resolver:** real specs use `$ref` heavily, and circular schemas are common (trees, comments).
- **Normalized model:** hides the 3.0 vs 3.1 differences (`nullable` vs `type: [.., "null"]`).
- **Rule engine:** every rule is a small, testable class. Direction matters: removing a response field breaks clients, while removing an optional request field usually doesn't.
- **Reporters:** separated so the CLI and the Action share one core.

## 5. Tech stack & justification
Python 3.12, `uv`, Typer (CLI), `pyyaml`/`ruamel.yaml`, pydantic for the change model, `pytest` + `hypothesis`, and a composite GitHub Action (Python setup + CLI). No full OpenAPI parser library: the point is to learn the traversal. `openapi-spec-validator` is used only for input validation.

## 6. Data model
`Change { rule_id: str, severity: Literal["breaking","warning","info"], location: str (JSON pointer), operation: "GET /users/{id}" | None, message: str, old: Any, new: Any }`
Rule registry: `rule_id → ChangeRule` (id, description, rationale, default severity, configurable).

## 7. API / interface design
```
api-diff old.yaml new.yaml                       # text, exit 1 if breaking
api-diff old.yaml new.yaml --format json
api-diff old.yaml new.yaml --fail-on warning
api-diff old.yaml new.yaml --ignore rules.yaml   # suppress with justification
api-diff rules                                   # list all rules + rationale
```
```yaml
# .github/workflows/api.yml
- uses: <owner>/api-diff@v0
  with: { spec: openapi.yaml, base-ref: main }
```
```python
from api_diff import diff

report = diff(old_spec, new_spec)
assert not report.breaking
```

## 8. Key engineering problems
- Cycle-safe `$ref` resolution (visited set keyed by pointer; compare schemas lazily).
- **Compatibility direction:** request schemas are contravariant and response schemas are covariant. Document this clearly; it's the core insight.
- `oneOf`/`anyOf`/`allOf` composition: v1 detects changes conservatively and flags "complex change: manual review".
- Path matching when parameter names are renamed (`/users/{id}` vs `/users/{userId}` is the same operation).
- Keeping false positives low, since noisy CI checks get disabled.

## 9. Milestones
- **M1: Loader + resolver + endpoint removal.** Accept when: fixtures with cycles resolve; removed operations are detected.
- **M2: Parameter and request-body rules.** Accept when: ≥ 15 rule fixtures (old/new/expected) pass.
- **M3: Response rules + type/enum changes + 3.1 nullability.** Accept when: fixture suite ≥ 40 cases.
- **M4: Reporters + exit codes + ignore file.** Accept when: the Markdown output renders in a PR.
- **M5: GitHub Action + PyPI 0.1.0.** Accept when: a demo repo shows the Action failing a breaking PR.
- **M6 (optional): pytest plugin for FastAPI baselines.**

## 10. Testing strategy
Table-driven fixture tests (`tests/fixtures/<rule>/{old,new,expected}.yaml`). Real-world specs (public ones such as Petstore, or a GitHub spec subset) as regression tests. Hypothesis tests check that `diff(x, x)` is always empty. Optionally, compare results against oasdiff on the same inputs to find disagreements.

## 11. Observability
Not applicable beyond a `--verbose` trace of rule evaluation.

## 12. Security
- Loading from URLs: timeouts and size limits, no redirects to file://.
- YAML safe-load only.

## 13. Deployment
PyPI package, plus a GitHub Action tagged `v0`.

## 14. Evaluation / measurements to collect
- Runtime on a large spec (e.g. ~5 MB): TBD, measure.
- Disagreement rate with oasdiff on the regression corpus: TBD.

## 15. Prerequisite learning
`learning/backend-02-rest-api-design`, `learning/python-03-classes-oop`, `learning/python-09-testing`, DSA trees and graphs (`dsa/10-trees`, `dsa/13-graphs`).

## 16. Interview talking points
- What counts as a breaking API change, and why do requests and responses differ?
- How do you version APIs, and when do you bump a major version?
- How do you traverse a graph with cycles?
- How do you keep a CI gate trustworthy (false positives)?

## 17. Resume bullet templates
- "Built api-diff, a Python CLI and GitHub Action detecting [N] classes of breaking OpenAPI changes with cycle-safe $ref resolution; [N] fixture tests."

## 18. Open questions / uncertainties
- Is it worth publishing at all, given oasdiff exists? Decide after M3. It's fine to keep it as a learning repo.
