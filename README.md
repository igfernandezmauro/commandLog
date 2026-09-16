# CommandLog

CommandLog is a personal Magic: The Gathering Commander tracking and analytics app.

It keeps a history of how decks change over time, records Commander games, and turns that data into useful statistics about decks, cards, and play history.

The project started as a way to combine two things I enjoy: **Magic: The Gathering** and **data engineering / analytics**.

**Live app:** https://commandlog.app

---

## What it does

CommandLog currently supports:

* Importing public Commander decks from Archidekt
* Tracking deck versions and card changes over time
* Viewing cards added and removed between deck versions
* Recording Commander games
* Tracking wins, losses, opponents, stores, turn order, mulligans, and other match metadata
* Random deck selection
* Deck and gameplay statistics
* Scryfall-backed card data
* Commander lookup data generated from Scryfall
* User authentication through Amazon Cognito

The long-term goal is for CommandLog decks to become independent objects that can be imported from multiple sources, edited directly in the app, and analyzed over their full lifetime.

---

## Why I built it

Most deck-building platforms are very good at representing what a deck looks like **right now**.

I wanted to keep track of what happens over time:

* How long has a card been in a deck?
* What cards were recently added or removed?
* How often do I actually play each deck?
* Which decks perform better?
* How does a deck change as I play and tune it?
* Which cards appear in decks that win more often?
* How do my decks and play habits evolve over months or years?

CommandLog is built around preserving that history rather than only storing the latest decklist.

---

## Architecture

CommandLog runs entirely on AWS using a serverless architecture.

```text
                        ┌─────────────────────┐
                        │   commandlog.app    │
                        │   CloudFront + S3   │
                        └──────────┬──────────┘
                                   │
                                   ▼
                        ┌─────────────────────┐
                        │ api.commandlog.app  │
                        │   API Gateway       │
                        └──────────┬──────────┘
                                   │
                                   ▼
                         ┌───────────────────┐
                         │   AWS Lambda      │
                         │   Python 3.11     │
                         └───────┬───────────┘
                                 │
             ┌───────────────────┼───────────────────┐
             ▼                   ▼                   ▼
      ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
      │  DynamoDB    │    │      S3      │    │   Scryfall   │
      │ app state    │    │ snapshots /  │    │  card data   │
      │ & history    │    │ raw / assets │    │              │
      └──────────────┘    └──────────────┘    └──────────────┘
```

### Main AWS services

* AWS Lambda
* API Gateway HTTP API
* DynamoDB
* S3
* CloudFront
* Cognito
* EventBridge
* Route 53
* ACM
* IAM
* CloudFormation / AWS SAM

Production infrastructure is managed as code.

---

## Repository structure

```text
backend/
  commandlog/       Shared application/domain code
  functions/        Lambda entry points
  tests/            Unit tests, fixtures, and Lambda events

frontend/
  index.html        Current web application

infrastructure/
  template.yaml     Main application stack
  data.yaml         Development data resources
  auth.yaml         Development authentication
  frontend.yaml     Frontend infrastructure
  production-storage.yaml
  domain.yaml
  domain-global.yaml

local/
  docker-compose.yml

scripts/
  dev               Development/deployment CLI
  seed_local.py     Local development data

docs/
  infrastructure/   Architecture and production documentation
  inventory/        Historical infrastructure inventory
```

---

## Local development

CommandLog can run locally without connecting the application to production AWS resources.

### Requirements

* Docker
* AWS SAM CLI
* Python 3.11+
* AWS CLI

Local AWS services are provided by LocalStack.

Create:

```text
local/.env.local
```

with:

```text
LOCALSTACK_AUTH_TOKEN=<your-localstack-token>
```

Then start the local application:

```bash
./scripts/dev local
```

Local services:

| Service    | URL                   |
| ---------- | --------------------- |
| Frontend   | http://localhost:8080 |
| API        | http://localhost:3000 |
| LocalStack | http://localhost:4566 |

The local environment uses seeded development data and does not require production authentication.

Stop LocalStack with:

```bash
./scripts/dev local-down
```

---

## Testing

Run the full local CI suite with:

```bash
./scripts/dev ci
```

The project includes unit tests for application behavior as well as infrastructure validation and smoke-test tooling.

Production can also be validated with:

```bash
./scripts/dev prod-smoke-test
```

---

## Deployment

CommandLog uses GitHub Actions and AWS OIDC for deployment.

The normal workflow is:

```text
feature branch
      │
      ▼
Pull Request
      │
      ▼
CI
      │
      ▼
main
      │
      ▼
manual production deployment
      │
      ▼
AWS via GitHub OIDC
```

Direct pushes to `main` are intentionally avoided.

Production deployment updates the backend infrastructure, publishes the frontend, invalidates CloudFront, and runs production smoke tests.

---

## Current production endpoints

* Frontend: https://commandlog.app
* API: https://api.commandlog.app

The application uses Cognito JWT authentication for protected API endpoints.

---

## Deck history

One of the main ideas behind CommandLog is that a deck is not just its current list.

When an imported deck changes, CommandLog can preserve a historical snapshot and record the change.

Conceptually:

```text
Import / Refresh deck
        │
        ▼
Normalize decklist
        │
        ▼
Calculate list hash
        │
        ├── unchanged ──► update last-seen information
        │
        ▼
      changed
        │
        ├── save snapshot
        ├── record change event
        ├── calculate deck diff
        └── update current deck state
```

This makes it possible to analyze how decks evolve instead of overwriting previous versions.

---

## Scryfall ingestion

CommandLog maintains card reference data using Scryfall bulk data.

The current pipeline supports Scryfall's gzip-compressed JSONL Oracle Cards dataset through `jsonl_download_uri`.

Background jobs download and process the bulk data and generate Commander lookup data used by the frontend.

---

## Roadmap

Some of the next areas of work include:

* Explicit deck importing and refresh workflows
* Making decks independent from their original provider
* Text-based deck imports
* Safe re-import and duplicate detection
* Better signup and onboarding
* Deck retirement / deactivation
* Match-history editing
* Winner commander tracking
* More deck and card analytics
* In-app deck editing

The immediate focus is making it easier for new users to sign up, import their decks, keep them updated, and start getting useful history and analytics from CommandLog.

---

## Project status

CommandLog is under active development.

The application is deployed and usable, but some workflows and data models are still evolving as the project moves from a personal tool toward something other Commander players can use.

---

## Security

Secrets and local environment files are not committed to the repository.

The project uses:

* GitHub OIDC instead of long-lived AWS credentials for deployments
* Environment-scoped AWS deployment roles
* Cognito for authentication
* Private S3 origins behind CloudFront
* IAM roles with scoped permissions
* Automated production smoke tests

If you find a security issue, please do not open a public issue containing sensitive details.

---

## License

Copyright © 2026 Ignacio Fernandez. All rights reserved.

This repository is publicly available for viewing, but no open-source license is currently granted.
