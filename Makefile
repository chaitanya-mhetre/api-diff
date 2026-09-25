.PHONY: check lint fmt type test build compare
check: lint type test
lint:
	uv run ruff check .
	uv run ruff format --check .
fmt:
	uv run ruff format .
	uv run ruff check --fix .
type:
	uv run mypy
test:
	uv run pytest -q
build:
	uv build
compare:  # needs network + oasdiff (PATH or $$OASDIFF); see docs/comparison-oasdiff.md
	uv run python comparison/compare.py
	uv run python comparison/analyze.py > comparison/results/summary.md
