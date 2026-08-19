.PHONY: install dev test lint demo docker-up docker-down

install:
	python -m pip install -e ".[dev,openai]"

dev:
	uvicorn praxismesh.api:app --app-dir backend --reload --host 0.0.0.0 --port 8000

test:
	python -m unittest discover -s tests -v

lint:
	ruff check backend tests
	python -m compileall -q backend tests

demo:
	PYTHONPATH=backend python -m praxismesh.cli demo --auto-approve

docker-up:
	docker compose up --build

docker-down:
	docker compose down

