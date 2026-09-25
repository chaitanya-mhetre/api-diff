# Benchmarks

## Diff time on a large spec (measured 2026-09-25)
Script: [`benchmarks/large_spec.py`](../benchmarks/large_spec.py). It builds a synthetic spec (N resources, each with 4 operations,
path + query parameters, and `$ref`'d nested schemas), then diffs it against a copy with two changes.

Environment: Python 3.12.14, x86_64 Linux laptop, single process. Loading/parsing YAML is **not** included (the dicts are built in memory).

| Resources | Operations | Size as JSON | Diff time |
|---|---|---|---|
| 2,000 | 8,000 | 2.5 MB | 0.70 s |
| 5,000 | 20,000 | 6.1 MB | 1.83 s |

It's one run on one machine, so treat it as an order of magnitude, not a promise. Parsing a large YAML file adds time on top (TBD).

Not measured (TBD): how often api-diff disagrees with oasdiff on a corpus of real-world specs.
