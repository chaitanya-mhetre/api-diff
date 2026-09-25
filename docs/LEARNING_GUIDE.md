# api-diff: learning guide

Read this with the code open. The goal is to be able to explain API compatibility rules and the traversal
algorithm on a whiteboard.

## 1. The big idea
An API change is **breaking** if a client that worked yesterday can fail today without changing its code.
What that means depends on which way the data flows:

| | Request (client → server) | Response (server → client) |
|---|---|---|
| Who must cope with the change | the **new server** handling **old clients' data** | **old clients** handling the **new server's data** |
| Safe | loosening: new optional fields, wider types, more enum values | tightening: fewer enum values, narrower types |
| Breaking | tightening: new required fields, stricter limits, removed enum values | loosening: removing guaranteed fields, adding `null`, new enum values (warning) |

In type-theory words, requests are **contravariant** and responses are **covariant**. The same idea explains why a
function that accepts `Animal` can stand in for one that accepts `Dog`, but not the other way round.

## 2. File tour (reading order)
| # | File | What to learn |
|---|---|---|
| 1 | `src/api_diff/rules.py` | Rules as data: id, severity, and a rationale you could defend in a design review. |
| 2 | `src/api_diff/model.py` | `Change` and `Report`; severity thresholds for exit codes. |
| 3 | `src/api_diff/loader.py` | Safe YAML/JSON loading, URL limits, and `Resolver.deref` (JSON Pointer, relative files, loop detection). |
| 4 | `src/api_diff/differ.py` | **The core.** Path matching, parameter keys, the direction-aware schema walker, `allOf` flattening, cycles. |
| 5 | `src/api_diff/ignore.py` | Suppressions with mandatory reasons, and glob matching. |
| 6 | `src/api_diff/reporters.py` | One report rendered four ways: text, JSON, Markdown, GitHub annotations. |
| 7 | `src/api_diff/cli.py` | Typer commands, exit codes as an API, and the `api-diff OLD NEW` shorthand. |
| 8 | `src/api_diff/baseline.py` | A snapshot/golden-file test pattern for APIs. |
| 9 | `action.yml` | Composite GitHub Actions and passing inputs safely through `env`. |
| 10 | `tests/cases/*.yaml`, `tests/test_cases.py` | Table-driven tests: adding a case is adding a file. |

## 3. Key concepts, with pointers

### `$ref` resolution and JSON Pointer (`loader.py`)
`#/components/schemas/User` is a JSON Pointer: split on `/`, and unescape `~1` → `/` and `~0` → `~` (so a path like
`/users/{id}` becomes `~1users~1{id}` inside a pointer). A ref can point into another file (`schemas.yaml#/Pet`), resolved
relative to the file that contains the ref. That's why `deref` returns the new `base` along with the node.
**Two kinds of cycles:**
- A ref *chain* that loops (`A → B → A` with no real node in between) is invalid, and `deref` raises.
- A *recursive schema* (a `Node` whose `children` are `Node`s) is valid and common. The differ handles it with a visited set.

### Traversing a graph with cycles (`differ.py::_schema`)
The two specs are walked **in parallel**. The visited key is `(old node identity, new node identity, direction)`.
If you've already started comparing this exact pair on the current path, stop. Without this, a recursive
schema recurses forever. `MAX_DEPTH` is a second safety net.
The visited set is reset at each root comparison (`depth == 0`), so a shared schema like `Book` is still checked (and reported)
for each operation that uses it.

### Matching things that were renamed
- **Paths:** `normalize_path` replaces `{anything}` with `{}`, so `/users/{id}` and `/users/{userId}` match.
- **Path parameters** are keyed by *position* in the template, not by name, for the same reason.
- **Other parameters** are keyed by `(in, name)`. If the same name shows up in a different `in`, that's a *location change*, not a removal plus an addition.

### Type compatibility (`_types`, `_covers`)
Types are compared as sets. `integer` is covered by `number` (every integer is a number, not vice versa).
Request: the new type set must cover the old one. Response: the old set must cover the new one. `null` is handled separately:
OpenAPI 3.0 writes `nullable: true`, 3.1 writes `type: [string, "null"]`, and `_type_set` normalises both.

### `allOf` flattening
`allOf: [A, B]` means "must satisfy A and B", so for comparison the properties and `required` lists are merged into one schema.
`oneOf`/`anyOf` ("exactly one of" / "any of") can't be merged. If both sides have the same number of branches they're compared pairwise;
otherwise a `composition-changed` warning asks for a human. Being conservative is better than confidently wrong.

### Designing a trustworthy CI gate
A gate with false positives gets disabled. So: severities (breaking / warning / info), `--fail-on` to choose the threshold,
an ignore file that forces a written reason, and exit code `2` (input error) kept separate from `1` (breaking changes found).

### Golden-file testing (`baseline.py`)
Store a known-good output (the baseline), compare on every run, and require an explicit action (`API_DIFF_UPDATE_BASELINE=1`) to accept a
change. The same pattern is used for snapshot tests, schema migrations and ML evaluation baselines.

### Safe GitHub Actions
Inputs go into `env:` and are referenced as `"$SPEC"` in bash. Writing `${{ inputs.spec }}` straight into the script
would let a crafted input inject shell commands (a well-known Actions injection risk).

## 4. Interview questions (with short answers)
1. **What makes an API change breaking?** Any change that makes a correct existing client fail without modifying it.
2. **Why is adding a required request field breaking, but adding a response field isn't?** Old clients don't send the new field, so
   requests become invalid. They simply ignore an extra response field.
3. **Why is adding an enum value to a response a warning?** Clients that `switch` exhaustively over the enum may crash on an unknown value.
   It's additive for tolerant clients, so it's flagged rather than failed.
4. **Explain covariance and contravariance using APIs.** Responses can get narrower (covariant); requests can get wider
   (contravariant). The mnemonic: be liberal in what you accept and conservative in what you send (Postel's law).
5. **How do you resolve `$ref`s across files?** Resolve relative to the referencing document's location, cache loaded documents by
   absolute path or URL, and follow JSON Pointer tokens with unescaping.
6. **How do you traverse a graph that has cycles?** Keep a visited set keyed by node identity (here, a pair of nodes plus direction) and a
   depth limit.
7. **How would you match `/users/{id}` with `/users/{userId}`?** Normalise template variables to a placeholder and key path parameters by position.
8. **How is OpenAPI 3.1 different from 3.0 for nullability?** 3.0 uses `nullable: true`; 3.1 uses JSON Schema's `type: [T, "null"]`.
9. **How do you keep CI checks trustworthy?** Low false positives, clear severities, configurable thresholds, justified suppressions,
   and distinct exit codes.
10. **Why table-driven tests?** Each rule gets an old/new/expected fixture. Adding coverage means adding a file, and regressions show up as a
    single failing case by name.
11. **What does the Hypothesis test prove?** Diffing any generated spec against itself reports nothing, which catches accidental asymmetry in rules.
12. **How do you version APIs, and when do you bump the major version?** Additive changes are minor. Breaking changes need a new major version (URL
    `/v2`, header or media type) and a deprecation period for the old one.
13. **How would you avoid breaking mobile apps specifically?** Old app versions live for months, so never remove or tighten. Add new fields and endpoints,
    deprecate, measure usage per client version, then remove.
14. **What are JSON Pointer escapes?** `~0` for `~` and `~1` for `/`, and you must decode `~1` before `~0`.
15. **What would you add next?** Response headers, security-scheme changes, `readOnly`/`writeOnly` (which flip the direction), and a
    disagreement study against oasdiff.
16. **Why report a shared schema change once per operation?** Reviewers need to know which endpoints and clients are affected. De-duplicating
    would hide that.
17. **Why is removing an optional response property only a warning?** The contract said it might be missing, so correct clients handle that.
    In practice many clients read it when present, so it's flagged.
18. **How did you validate api-diff against an established tool?** I ran it and oasdiff on 10 real historical version pairs of
    public specs, pinned to commit SHAs (`comparison/`), compared the sets of operations each flagged, and classified every
    disagreement group by hand: policy difference, api-diff bug, api-diff gap, or oasdiff noise. That found three real bugs. The
    biggest lesson was that a naive agreement percentage would be misleading: most disagreement came from one 3.0 → 3.1 migration
    and from deliberate severity choices (see `docs/comparison-oasdiff.md`).
19. **Why is `anyOf: [X, {type: "null"}]` special?** OpenAPI 3.1 dropped `nullable`, so that's how 3.1 says "X or null". A differ that
    treats it as an opaque `anyOf` stops comparing X and invents removals. api-diff unwraps it into X plus `null` (`Differ._normalize`)
    so both spellings compare as equal.
20. **Why compare numbers as doubles above 2^53?** JSON numbers are usually parsed as IEEE doubles, which can't represent every
    integer past 2^53. A JavaScript serializer writes int64 max as `9223372036854776000`. Treating that as a change is noise, so
    `_constraints` compares large bounds as doubles.

## 5. Try it yourself
- Add a dedicated rule for a new response `oneOf`/`anyOf` variant (the largest real gap in `docs/comparison-oasdiff.md`).
- Add a rule for response header removal, with fixtures.
- Handle `readOnly` (only in responses) and `writeOnly` (only in requests) properties.
- Run api-diff and oasdiff on a few public specs' version histories and write up where they disagree.
