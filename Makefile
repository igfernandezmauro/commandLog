AWS_REGION := ca-central-1
LOCALSTACK_ENDPOINT := http://localhost:4566

.PHONY: local-up local-down local-status local-seed local-reset sam-build invoke-list-decks

local-up:
	docker compose --env-file .env -f local/docker-compose.yml up -d
	@echo "Waiting for LocalStack..."
	@for attempt in $$(seq 1 30); do \
		if curl -sf http://localhost:4566/_localstack/health > /dev/null; then \
			echo "LocalStack is ready."; \
			exit 0; \
		fi; \
		sleep 2; \
	done; \
	echo "LocalStack did not become ready."; \
	docker compose --env-file .env-f local/docker-compose.yml logs --tail=100 localstack; \
	exit 1
	@echo "LocalStack is ready."

local-down:
	docker compose --env-file .env -f local/docker-compose.yml down

local-status:
	docker compose --env-file .env -f local/docker-compose.yml ps

local-seed:
	AWS_REGION=$(AWS_REGION) \
	AWS_ENDPOINT_URL=$(LOCALSTACK_ENDPOINT) \
	python3 scripts/seed_local.py

local-reset:
	docker compose --env-file .env -f local/docker-compose.yml down -v
	$(MAKE) local-up
	$(MAKE) local-seed

sam-build:
	sam build \
		--template-file infrastructure/template.yaml

invoke-list-decks: sam-build
	sam local invoke ListDecksFunction \
		--template-file .aws-sam/build/template.yaml \
		--event backend/tests/events/list-decks.json