.PHONY: up test down

up:
	docker compose up --build

test:
	docker compose --profile test run --rm tests

down:
	docker compose down -v
