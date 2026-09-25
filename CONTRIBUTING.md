# Contributing

1. `uv sync`, then `make check` (ruff, mypy --strict, pytest). All must pass.
2. **Every rule change needs a fixture.** Add `tests/cases/<name>.yaml` with `old_paths`, `new_paths` and the
   `expected` rule ids. The table-driven test picks it up automatically.
3. New rules go in `src/api_diff/rules.py` with a severity **and a rationale**. If you can't explain why a
   change breaks clients, it isn't a breaking rule.
4. Think about direction: request schemas must not get stricter; response schemas must not get looser.
5. Use conventional commits (`feat:`, `fix:`, `test:`, `docs:`).
