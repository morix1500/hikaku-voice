PORT ?= 8009

.PHONY: run install lint format

run:
	uv run uvicorn main:app --reload --host 0.0.0.0 --port $(PORT)

install:
	uv sync
	@if [ -f requirements-local.txt ]; then \
		echo "Installing local plugins..."; \
		uv pip install -r requirements-local.txt; \
	fi

lint:
	uv run ruff check .

format:
	uv run ruff format .

type-check:
	uv run ty check .
