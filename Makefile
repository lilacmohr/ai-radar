.PHONY: lint typecheck test test-unit test-contract check run

lint:
	uv run ruff check radar/ tests/
	uv run ruff format --check radar/ tests/

typecheck:
	uv run mypy radar/

test:
	uv run pytest tests/; test $$? -eq 0 -o $$? -eq 5

test-unit:
	uv run pytest tests/unit/; test $$? -eq 0 -o $$? -eq 5

test-contract:
	uv run pytest tests/contract/; test $$? -eq 0 -o $$? -eq 5

check: lint typecheck test

run:
	uv run python -m radar run
