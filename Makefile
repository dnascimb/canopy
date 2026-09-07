.PHONY: install dev run test lint seed screenshots docker

install:
	pip install -r requirements.txt

dev:
	pip install -r requirements-dev.txt

run:
	flask --app wsgi run --debug

seed:
	flask --app wsgi init-db
	flask --app wsgi seed-demo

test:
	pytest --cov=canopy --cov-report=term-missing

lint:
	ruff check canopy tests

screenshots:
	python scripts/screenshots.py

docker:
	docker compose up --build
