oasdiff version: `oasdiff version 1.32.1`

| pair | api-diff ops | oasdiff ops | both | only api-diff | only oasdiff | time api-diff / oasdiff |
|---|---:|---:|---:|---:|---:|---|
| openai-2025-04_2026-08 | 56 | 120 | 55 | 1 | 65 | 3.92s / 1.07s |
| openai-2026-08_2026-09 | 11 | 26 | 11 | 0 | 15 | 7.36s / 1.94s |
| twilio-verify-2024-10_2026-09 | 1 | 18 | 1 | 0 | 17 | 0.67s / 0.23s |
| twilio-2024-09_2025-10 | 20 | 69 | 20 | 0 | 49 | 3.06s / 0.85s |
| twilio-2026-03_2026-09 | 0 | 0 | 0 | 0 | 0 | 3.1s / 0.81s |
| box-2025-12_2026-05 | 6 | 6 | 6 | 0 | 0 | 3.32s / 0.52s |
| box-2026-07_2026-09 | 0 | 0 | 0 | 0 | 0 | 3.36s / 0.45s |
| pagerduty-2026-06_2026-09 | 0 | oasdiff error | – | – | – | 5.21s / – |
| k8s-apps-v1-1.30_1.34 | 18 | 12 | 12 | 6 | 0 | 2.69s / 1.47s |
| k8s-batch-v1-1.30_1.34 | 6 | 6 | 6 | 0 | 0 | 1.45s / 0.8s |

**oasdiff ERR findings on operations api-diff did not flag (by oasdiff rule):**

| oasdiff rule | findings |
|---|---:|
| `response-property-list-of-types-widened` | 216 |
| `response-property-enum-value-added` | 160 |
| `request-parameter-type-changed` | 59 |
| `response-required-property-removed` | 54 |
| `response-property-any-of-added` | 48 |
| `response-property-type-changed` | 44 |
| `request-property-enum-value-removed` | 23 |
| `response-property-one-of-added` | 16 |
| `response-property-min-unset` | 14 |
| `response-property-max-length-unset` | 12 |
| `response-property-max-unset` | 8 |
| `response-property-max-properties-unset` | 6 |
| `response-property-max-items-unset` | 3 |
| `request-property-one-of-removed` | 2 |
| `response-body-one-of-added` | 2 |
| `request-property-any-of-removed` | 2 |
| `response-body-any-of-added` | 1 |
| `new-request-path-parameter` | 1 |
| `request-property-type-changed` | 1 |

**api-diff breaking findings on operations oasdiff did not flag (by api-diff rule):**

| api-diff rule | findings |
|---|---:|
| `response-property-became-optional` | 30 |
| `response-became-nullable` | 1 |
