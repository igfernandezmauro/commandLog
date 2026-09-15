# CommandLog Production Infrastructure Inventory

Last verified: 2026-09-15

## Purpose

This document describes the **current production infrastructure** for CommandLog after completion of the AWS infrastructure migration and legacy-resource cleanup.

Historical pre-migration infrastructure details are intentionally not maintained here. See the inventory and production cutover documentation for the architecture that existed before the migration.

## Production environment

* Primary AWS region: `ca-central-1`
* Global certificate region: `us-east-1`
* Frontend: `https://commandlog.app`
* API: `https://api.commandlog.app`
* Infrastructure management: AWS SAM / CloudFormation
* Deployment source: GitHub
* Production deployment mechanism: GitHub Actions using AWS OIDC
* Primary branch: `main`

Production infrastructure is managed as a set of dedicated CommandLog CloudFormation stacks.

## CloudFormation stacks

### ca-central-1

| Stack                      | Purpose                                                             |
| -------------------------- | ------------------------------------------------------------------- |
| `commandlog-prod-app`      | API Gateway, Lambda functions, permissions, and application runtime |
| `commandlog-prod-storage`  | Production S3 storage                                               |
| `commandlog-prod-frontend` | Production frontend S3 and CloudFront delivery                      |
| `commandlog-prod-domain`   | Regional API custom domain and DNS                                  |

### us-east-1

| Stack                           | Purpose                                              |
| ------------------------------- | ---------------------------------------------------- |
| `commandlog-prod-domain-global` | ACM certificate used by the CloudFront custom domain |

The production Cognito resources and DynamoDB application data remain stateful resources referenced by the CommandLog application.

## Lambda functions

All current production application Lambdas use Python 3.11.

| Function                                 |
| ---------------------------------------- |
| `commandlog-prod-profile`                |
| `commandlog-prod-list-decks`             |
| `commandlog-prod-deck-versions`          |
| `commandlog-prod-get-diff`               |
| `commandlog-prod-get-games`              |
| `commandlog-prod-get-random-decks`       |
| `commandlog-prod-log-play-event`         |
| `commandlog-prod-stats-summary`          |
| `commandlog-prod-stats-version`          |
| `commandlog-prod-sync-decks`             |
| `commandlog-prod-scryfall-download`      |
| `commandlog-prod-scryfall-load`          |
| `commandlog-prod-build-commanders-index` |

Legacy `mtg-app-*` Lambda functions have been removed.

## HTTP API

Production API:

* Name: `commandlog-prod-api`
* API ID: `43z1wttq6f`
* Protocol: HTTP API
* Custom domain: `https://api.commandlog.app`
* Authentication: Cognito JWT
* Frontend CORS origin: `https://commandlog.app`

### Routes

| Route                       | Purpose                                 |
| --------------------------- | --------------------------------------- |
| `GET /stats/version`        | Statistics and data version information |
| `GET /me/profile`           | Retrieve user profile                   |
| `PUT /me/profile`           | Update user profile                     |
| `GET /decks`                | List decks                              |
| `GET /decks/{deck_id}`      | Retrieve deck/version information       |
| `GET /decks/{deck_id}/diff` | Compare deck versions                   |
| `GET /games`                | Retrieve recorded games                 |
| `GET /pick`                 | Pick random eligible decks              |
| `POST /play`                | Record a Commander game                 |
| `GET /stats/summary`        | Retrieve aggregate statistics           |

The previous `log-play-events-api` API has been decommissioned.

## Authentication and identity

Production authentication uses the existing Cognito User Pool:

* User Pool: `ca-central-1_e6TWFI8D9`
* SPA client: `m2p7rqmpkq838hhlum98r1msb`
* Authentication flow: OAuth authorization code
* Scopes: `openid`, `email`, `profile`
* Callback URL: `https://commandlog.app/`
* Logout URL: `https://commandlog.app/`

The production Cognito User Pool contains stateful user identity data and is not recreated as part of normal application deployments.

## DynamoDB

The current CommandLog runtime continues to use production DynamoDB tables whose names predate the CommandLog rename.

| Table                     | Purpose                        |
| ------------------------- | ------------------------------ |
| `mtg_app_deck_state_v2`   | Current deck state             |
| `mtg_app_user_profile`    | User configuration and profile |
| `mtg_app_play_events`     | Recorded Commander games       |
| `mtg_app_deck_change_log` | Historical deck changes        |
| `mtg_app_deck_diffs`      | Cached deck diffs              |
| `mtg_app_cards_dim`       | Card reference data            |

These tables are stateful production resources and must not be replaced or deleted by routine infrastructure deployments.

Renaming or redesigning the database layer to use CommandLog-native resource names is a separate future project.

## S3 storage

Current production buckets:

| Bucket                                                | Purpose                                              |
| ----------------------------------------------------- | ---------------------------------------------------- |
| `commandlog-prod-280535250460-ca-central-1-snapshots` | Historical deck snapshots                            |
| `commandlog-prod-280535250460-ca-central-1-raw`       | Raw ingestion data, including Scryfall               |
| `commandlog-prod-280535250460-ca-central-1-generated` | Generated application data such as commander indexes |
| `commandlog-prod-280535250460-ca-central-1-web`       | Deployed frontend assets                             |

The original `ignacio-mtg-app-raw-ca-central-1` and `mtg-app-ui` buckets have been decommissioned.

## Frontend delivery

Production frontend:

* URL: `https://commandlog.app`
* CloudFront distribution ID: `E2NBU7K9T63NEI`
* CloudFront domain: `d2977zjw96ev6m.cloudfront.net`
* Web bucket: `commandlog-prod-280535250460-ca-central-1-web`
* Generated-data bucket: `commandlog-prod-280535250460-ca-central-1-generated`

CloudFront serves the application frontend from the production web bucket.

Generated application assets under `/data/*`, including the commander index, are served from the production generated-data bucket.

The frontend communicates with the backend through:

`https://api.commandlog.app`

The previous CloudFront distribution `EXPMYKBU51WF2` / `d2cux7a98zqlb4.cloudfront.net` has been removed.

## Background automation

### EventBridge Scheduler

Current production schedules:

| Schedule                           | Target                                   |
| ---------------------------------- | ---------------------------------------- |
| `commandlog-prod-scryfall-sync`    | `commandlog-prod-scryfall-download`      |
| `commandlog-prod-commanders-index` | `commandlog-prod-build-commanders-index` |

The legacy Moxfield synchronization schedule has been removed.

CommandLog does not currently run periodic Moxfield synchronization.

### EventBridge rule

Production includes:

`commandlog-prod-scryfall-latest-created`

This rule participates in the Scryfall ingestion pipeline after new raw bulk data is stored.

## Scryfall ingestion

The current Scryfall pipeline uses the Oracle Cards JSONL bulk-data format.

The downloader supports:

* `jsonl_download_uri`
* gzip-compressed JSONL
* `.jsonl.gz` objects

Current flow:

1. `commandlog-prod-scryfall-sync` invokes `commandlog-prod-scryfall-download`.
2. The downloader retrieves the Scryfall Oracle Cards JSONL gzip bulk file.
3. Raw data is stored in the production raw-data bucket.
4. The ingestion event invokes `commandlog-prod-scryfall-load`.
5. Card reference data is updated for application use.
6. The commander-index process generates frontend lookup data in the generated-data bucket.

The application no longer depends on the older JSON-array Scryfall bulk format.

## Deck ingestion

Current deck ingestion is Archidekt-based.

Moxfield ingestion was intentionally not carried forward into the migrated production application.

The current architecture still contains `commandlog-prod-sync-decks`, but the old periodic Moxfield synchronization process has been removed.

A future redesign will make CommandLog decks independent first-class objects with explicit imports, safe re-importing, provider-independent text import, and in-application editing.

## Production deployment

Production deployments run from `main` through the production GitHub Actions workflow.

The deployment process:

1. Builds and validates the application.
2. Deploys the production application stack.
3. Publishes `frontend/index.html` to the production web bucket.
4. Invalidates the CloudFront frontend cache.
5. Runs production smoke tests.

Production frontend CORS is configured for:

`https://commandlog.app`

Production application configuration keeps automatic profile-save ingestion disabled:

`InvokeIngestOnSave=false`

## Production validation

The production smoke test verifies at minimum:

* `https://commandlog.app` is reachable.
* `https://api.commandlog.app` is reachable.
* Unauthenticated protected API requests return `401`.
* CORS allows `https://commandlog.app`.
* Production background automation is enabled.
* Profile-save ingestion remains disabled.

The production smoke test was run successfully throughout the legacy infrastructure cleanup.

## Legacy infrastructure decommissioning

The original MTG application infrastructure was removed after the CommandLog replacement had been validated.

Decommissioned resources included:

* Legacy `mtg-app-*` Lambda functions
* `log_play_event`
* `mtgAppProfile`
* Legacy `log-play-events-api`
* Legacy EventBridge Scheduler jobs
* Legacy CloudFront distribution
* `mtg-app-ui`
* Legacy Lambda and Scheduler IAM roles
* Orphaned legacy IAM policies
* `ignacio-mtg-app-raw-ca-central-1`

### Snapshot migration validation

Before deleting the legacy raw bucket, every deck-change snapshot referenced by production change history was verified against the CommandLog production snapshot bucket.

Final migration audit:

```text
copied=0
already_exists=99
skipped=12
missing_source=0
repaired=0
unresolved=0
```

The legacy raw bucket was deleted only after:

* the migration audit reported no missing source objects,
* no active Lambda referenced it,
* its stale legacy S3 event notification was removed,
* and the production smoke test passed.

## Current ownership boundary

### IaC-managed

* Production Lambda functions
* HTTP API
* API custom domain
* API and Lambda permissions
* EventBridge schedules and rules
* Production S3 infrastructure
* Frontend S3 and CloudFront delivery
* Production custom-domain infrastructure

### Existing stateful resources

* Production Cognito User Pool and SPA client
* Production DynamoDB application tables

These stateful resources should continue to be treated conservatively until explicitly migrated or redesigned.

## Current status

The CommandLog production infrastructure migration is complete.

The application now runs on the IaC-managed CommandLog production infrastructure, uses the `commandlog.app` custom domains, and no longer depends on the legacy MTG application compute, delivery, scheduling, IAM, or raw-storage infrastructure.

Future infrastructure work should treat this document as the baseline production inventory rather than the pre-migration architecture.