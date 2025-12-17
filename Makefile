PORT ?= 8009

.PHONY: run install lint format

run:
	uv run uvicorn main:app --reload --host 0.0.0.0 --port $(PORT)

install:
	uv sync

lint:
	uv run ruff check .

format:
	uv run ruff format .

type-check:
	uv run ty check .
