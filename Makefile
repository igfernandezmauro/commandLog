AWS_REGION := ca-central-1
LOCALSTACK_ENDPOINT := http://localhost:4566

.PHONY: local-up local-down local-status local-seed local-reset sam-build invoke-list-decks invoke-get-games invoke-get-games-alora invoke-list-decks-unauthorized invoke-get-games-unauthorized invoke-log-play-event invoke-log-play-event-unauthorized invoke-log-play-event-missing-deck invoke-log-play-event-invalid invoke-stats-summary invoke-stats-summary-since invoke-stats-version invoke-stats-version-missing-deck invoke-get-random-decks invoke-get-random-decks-invalid invoke-deck-versions invoke-deck-versions-not-found invoke-get-diff invoke-get-diff-empty invoke-get-diff-not-found

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

invoke-get-games: sam-build
	sam local invoke GetGamesFunction \
		--template-file .aws-sam/build/template.yaml \
		--event backend/tests/events/get-games.json

invoke-get-games-alora: sam-build
	sam local invoke GetGamesFunction \
		--template-file .aws-sam/build/template.yaml \
		--event backend/tests/events/get-games-alora.json

invoke-list-decks-unauthorized: sam-build
	sam local invoke ListDecksFunction \
	--template-file .aws-sam/build/template.yaml \
	--event backend/tests/events/list-decks-unauthorized.json

invoke-get-games-unauthorized: sam-build
	sam local invoke GetGamesFunction \
	--template-file .aws-sam/build/template.yaml \
	--event backend/tests/events/get-games-unauthorized.json

invoke-log-play-event: sam-build
	sam local invoke LogPlayEventFunction \
	--template-file .aws-sam/build/template.yaml \
	--event backend/tests/events/log-play-event.json

invoke-log-play-event-unauthorized: sam-build
	sam local invoke LogPlayEventFunction \
	--template-file .aws-sam/build/template.yaml \
	--event backend/tests/events/log-play-event-unauthorized.json

invoke-log-play-event-missing-deck: sam-build
	sam local invoke LogPlayEventFunction \
	--template-file .aws-sam/build/template.yaml \
	--event backend/tests/events/log-play-event-missing-deck.json

invoke-log-play-event-invalid: sam-build
	sam local invoke LogPlayEventFunction \
	--template-file .aws-sam/build/template.yaml \
	--event backend/tests/events/log-play-event-invalid.json

invoke-stats-summary: sam-build
	sam local invoke StatsSummaryFunction \
	--template-file .aws-sam/build/template.yaml \
	--event backend/tests/events/stats-summary.json

invoke-stats-summary-since: sam-build
	sam local invoke StatsSummaryFunction \
	--template-file .aws-sam/build/template.yaml \
	--event backend/tests/events/stats-summary-since.json

invoke-stats-version: sam-build
	sam local invoke StatsVersionFunction \
	--template-file .aws-sam/build/template.yaml \
	--event backend/tests/events/stats-version.json

invoke-stats-version-missing-deck: sam-build
	sam local invoke StatsVersionFunction \
	--template-file .aws-sam/build/template.yaml \
	--event backend/tests/events/stats-version-missing-deck.json

invoke-get-random-decks: sam-build
	sam local invoke GetRandomDecksFunction \
	--template-file .aws-sam/build/template.yaml \
	--event backend/tests/events/get-random-decks.json

invoke-get-random-decks-invalid: sam-build
	sam local invoke GetRandomDecksFunction \
	--template-file .aws-sam/build/template.yaml \
	--event backend/tests/events/get-random-decks-invalid.json

invoke-deck-versions: sam-build
	sam local invoke DeckVersionsFunction \
	--template-file .aws-sam/build/template.yaml \
	--event backend/tests/events/deck-versions.json

invoke-deck-versions-not-found: sam-build
	sam local invoke DeckVersionsFunction \
	--template-file .aws-sam/build/template.yaml \
	--event backend/tests/events/deck-versions-not-found.json

invoke-get-diff: sam-build
	sam local invoke GetDiffFunction \
	--template-file .aws-sam/build/template.yaml \
	--event backend/tests/events/get-diff.json

invoke-get-diff-empty: sam-build
	sam local invoke GetDiffFunction \
	--template-file .aws-sam/build/template.yaml \
	--event backend/tests/events/get-diff-empty.json

invoke-get-diff-not-found: sam-build
	sam local invoke GetDiffFunction \
	--template-file .aws-sam/build/template.yaml \
	--event backend/tests/events/get-diff-not-found.json