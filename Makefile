.PHONY: up down build logs api-logs web-logs health shell-api validate-catalog test-e2e smoke-live

validate-catalog:
	python3 pipeline/validate_catalog.py catalog/catalog_V17.json

up:
	docker compose up --build

up-d:
	docker compose up --build -d

down:
	docker compose down

build:
	docker compose build

logs:
	docker compose logs -f

api-logs:
	docker compose logs -f api

web-logs:
	docker compose logs -f web

health:
	curl -s http://localhost:8000/health | python3 -m json.tool

shell-api:
	docker compose exec api bash

test-e2e:
	cd frontend && npm run test:e2e

smoke-live:
	./scripts/smoke_live.sh
