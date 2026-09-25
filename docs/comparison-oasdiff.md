# api-diff vs oasdiff on real public specs

**Short version:** oasdiff finds more, and runs 2–7× faster. The comparison found **three real api-diff bugs**
(fixed, with regression fixtures). Every operation api-diff flags as breaking is also flagged by oasdiff, with two
exceptions: 6 Kubernetes operations where both tools find the change but oasdiff grades it WARN, and 1 real change
that oasdiff didn't report at ERR. The README still recommends oasdiff for production CI.

- Date: 2026-09-25. oasdiff **1.32.1** (release binary), api-diff at the commit that adds this file.
- Machine: a busy 14 GB laptop running other workloads. Timings are single runs, so they're rough.
- Reproduce: `OASDIFF=/path/to/oasdiff make compare`. Specs are fetched by exact commit SHA and never committed.
  Pair list: [`comparison/pairs.json`](../comparison/pairs.json). Raw tables: [`comparison/results/summary.md`](../comparison/results/summary.md).

## Method

- **10 pairs** of real historical versions of 6 public specs, each pinned to an exact commit:
  OpenAI (×2), Twilio Api v2010 (×2), Twilio Verify v2, Box (×2), PagerDuty, and Kubernetes `apps/v1` and `batch/v1` (v1.30.0 → v1.34.0).
- **Unit of comparison:** the set of *operations* (`METHOD /path/{}`) each tool reports as having at least one breaking change.
  - oasdiff: level ERR.
  - api-diff: severity `breaking`.
  - Path-parameter names are normalised on both sides.
- oasdiff ran with `--auto-upgrade` (its documented mode for comparing across OpenAPI versions), under a 2 GB memory cap.
- **Excluded:** Stripe `spec3.yaml`. oasdiff was OOM-killed comparing two ~7 MB versions on this laptop, so the pair was dropped rather than retried in a way that could crash the machine.

## Results (after the fixes below)

| pair | api-diff ops | oasdiff ops | both | only api-diff | only oasdiff | time api-diff / oasdiff |
|---|---:|---:|---:|---:|---:|---|
| openai 2025-04 → 2026-08 (3.0 → 3.1) | 56 | 120 | 55 | 1 | 65 | 3.9s / 1.1s |
| openai 2026-08 → 2026-09 | 11 | 26 | 11 | 0 | 15 | 7.4s / 1.9s |
| twilio verify 2024-10 → 2026-09 | 1 | 18 | 1 | 0 | 17 | 0.7s / 0.2s |
| twilio v2010 2024-09 → 2025-10 | 20 | 69 | 20 | 0 | 49 | 3.1s / 0.9s |
| twilio v2010 2026-03 → 2026-09 | 0 | 0 | 0 | 0 | 0 | 3.1s / 0.8s |
| box 2025-12 → 2026-05 | 6 | 6 | 6 | 0 | 0 | 3.3s / 0.5s |
| box 2026-07 → 2026-09 | 0 | 0 | 0 | 0 | 0 | 3.4s / 0.5s |
| pagerduty 2026-06 → 2026-09 | 0 | *oasdiff error* | – | – | – | 5.2s / – |
| k8s apps/v1 1.30 → 1.34 | 18 | 12 | 12 | 6 | 0 | 2.7s / 1.5s |
| k8s batch/v1 1.30 → 1.34 | 6 | 6 | 6 | 0 | 0 | 1.5s / 0.8s |

- **PagerDuty:** oasdiff refuses to load the base spec, which has a `requestBodies` entry that points at a response
  object. That's invalid. api-diff loads it anyway, which is more lenient, not more correct.

## Bugs found in api-diff and fixed

| # | Bug | Where it showed up | Effect | Fix + regression fixture |
|---|---|---|---|---|
| 1 | The 3.1 nullable form `anyOf: [X, {type: "null"}]` wasn't understood | OpenAI 3.0 → 3.1 | **94 false `response-property-removed`** findings (the new wrapper had no properties) and changes inside `X` weren't compared | unwrap nullable unions into `X` + `null` · `request_nullable_anyof_31_enum_value_removed`, `request_nullable_30_to_anyof_31_is_fine`, `request_became_non_nullable_anyof`, `response_became_nullable_anyof`, `recursive_nullable_union_terminates` |
| 2 | When a `oneOf`/`anyOf` gained or lost members, surviving variants weren't compared at all | OpenAI `ComputerToolCall.action` became optional inside a growing `oneOf` | **3 missed real breaking changes** hidden behind a "review manually" warning | also compare members that share a `$ref` · `response_oneof_variant_added_still_compares_same_ref` |
| 3 | 3.0 boolean `exclusiveMinimum: true` vs 3.1 numeric form, and int64 limits re-serialised as `9223372036854776000` | OpenAI | **8 false `request-constraint-tightened`** findings | normalise exclusive bounds and compare as doubles above 2^53 · `request_exclusive_minimum_bool_to_number_is_fine`, `request_int64_bounds_reserialized_is_fine`, `request_minimum_became_exclusive_is_tightened` (a real tightening must still be caught) |

After fix 1, api-diff also reports **82 correct `response-became-nullable`** findings on that pair.

## Where the tools disagree, classified

Counts are individual findings on operations the *other* tool didn't flag. "Checked" means cases were inspected
by hand against both spec versions. Groups not marked checked are classified from the rule definitions only.

### oasdiff ERR, api-diff not breaking

| oasdiff rule | findings | classification |
|---|---:|---|
| `response-property-enum-value-added` | 160 | **Policy.** api-diff grades this `warning` (clients with exhaustive matches may break, many don't) |
| `response-property-*-unset` (min, maxLength, max, maxProperties, maxItems) | 43 | **Policy.** api-diff reports `response-constraint-loosened` as `warning` |
| `request-parameter-type-changed` (Twilio `PageSize`: format none → `int64`) | 59 | **Policy / known gap.** api-diff only compares `format` when both sides have one. In JSON Schema 2020-12 `format` is an annotation by default |
| `response-property-list-of-types-widened` | 216 | **Mostly oasdiff noise on the 3.0 → 3.1 pair** (all 216 from that pair). Checked 2 (`AssistantObject.description`, `.instructions`): both were already `nullable: true` in 3.0, and `--auto-upgrade` still reported "added null". Not fully audited |
| `response-required-property-removed` | 54 | **Mostly noise, same cause** (54 of 54 from the 3.0 → 3.1 pair). Checked 2: `FineTuningJob.error.{code,message}` are unchanged inside the new nullable wrapper |
| `response-property-type-changed` | 44 | **Mostly noise** (40 from the 3.0 → 3.1 pair, e.g. "object,null → any" for a nullable wrapper). 3 from the second OpenAI pair were not audited. 1 Twilio case is a response `format` removed, which api-diff doesn't flag (policy) |
| `request-property-enum-value-removed` | 23 | **Noise** (all from the 3.0 → 3.1 pair). Checked 2: `reasoning_effort` values `high` and `low` are still present in the new enum |
| `response-(property\|body)-(any\|one)-of-added` | 67 | **Mixed.** Some are nullable-wrapper noise; some are real new variants. **api-diff gap:** a new response variant is only a `composition-changed` warning, with no dedicated breaking rule |
| `request-property-(any\|one)-of-removed`, `request-property-type-changed`, `new-request-path-parameter` | 6 | **api-diff gap (small):** request variant removal is only a `composition-changed` warning |

### api-diff breaking, oasdiff not ERR

| api-diff rule | findings | classification |
|---|---:|---|
| `response-property-became-optional` (k8s `StatefulSetSpec.serviceName`, 6 operations) | 30 | **Severity difference.** oasdiff finds the same change and grades it WARN. It really did become optional in 1.34 |
| `response-became-nullable` (OpenAI `POST /organization/admin_api_keys`, `name`) | 1 | **api-diff true positive.** `string` became `anyOf: [string, null]`. oasdiff didn't report it at ERR |

## Known gaps (not fixed)

- No dedicated rules for **added response variants** or **removed request variants** in `oneOf`/`anyOf`. Both only
  produce a `composition-changed` warning.
- A `format` being **added** (request) or **removed** (response) isn't reported.
- The unit of comparison is the operation, so two tools can agree on an operation for different reasons. Rule-level agreement wasn't measured.
- The corpus is small (10 pairs, 6 APIs), and one pair (OpenAI 3.0 → 3.1) accounts for most of the disagreement.
- Speed: oasdiff was faster on every pair (roughly 2–7×).
