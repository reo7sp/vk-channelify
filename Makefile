.PHONY: install format lint run test test-integration migrate docker-migrate docker-run docker-stop

install:
	poetry install

run: install
	poetry run python app.py

test: install
	poetry run pytest

test-integration:
	docker compose --profile test up --build --abort-on-container-exit --exit-code-from tests tests

migrate: install
	PYTHONPATH=. poetry run alembic upgrade head

docker-migrate:
	docker compose up --build --abort-on-container-exit --exit-code-from migrate migrate

docker-run:
	docker compose --profile app up --build app

docker-stop:
	docker compose --profile app --profile test down --remove-orphans

format: install
	poetry run ruff check --fix .
	poetry run ruff format .

lint: install
	poetry run ruff check .
	poetry run ruff format --check .
