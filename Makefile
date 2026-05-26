# Makefile for k3s-client dev and CI workflows

.PHONY: install test lint format check clean

install:
	python -m pip install --upgrade pip
	pip install -r requirements.txt
	pip install -e .

test:
	PYTHONPATH=. pytest -q

lint:
	PYTHONPATH=. ruff check .

format:
	ruff format .

check: test lint

clean:
	rm -rf .pytest_cache .ruff_cache *.egg-info
