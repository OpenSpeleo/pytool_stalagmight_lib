.PHONY: install test coverage lint build

install:
	uv sync --frozen --all-extras --dev

test:
	uv run pytest

coverage:
	uv run pytest --cov=stalagmight_lib --cov-report=term-missing

lint:
	uv run prek run --all-files

build:
	uv run flit build
