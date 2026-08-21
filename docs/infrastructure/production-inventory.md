# CommandLog Production Infrastructure Inventory

Last verified: 2026-08-17

## Production environment

- AWS region: `ca-central-1`
- Infrastructure origin: manually created AWS resources
- Current infrastructure is not CloudFormation/SAM-managed as a cohesive stack.
- This inventory is read-only and exists to establish the migration boundary before introducing IaC.

## Migration safety rule

Existing production stateful resources must not be replaced, deleted, or adopted into
CloudFormation until their usage and migration strategy have been explicitly verified.

During the initial IaC migration:

- Existing production DynamoDB tables are treated as externally managed state.
- Existing production S3 buckets are treated as externally managed state.
- New IaC-managed compute may reference existing stateful resources by parameter/name.
- Destructive cleanup happens only after the new production stack has been validated.

## Lambda functions

| Function | Runtime | Memory | Timeout | IAM Role |
|---|---:|---:|---:|---|
| log_play_event | Python 3.11 | 128 MB | 3s | mtg-app-play-events-lambda-role |
| mtg-app-stats-version | Python 3.11 | 128 MB | 3s | mtg-app-get-stats-lambda |
| mtg-app-scryfall-batch-loader | Python 3.11 | 1024 MB | 600s | mtg-app-scryfall-batch-loader |
| mtg-app-stats-summary | Python 3.11 | 128 MB | 3s | mtg-app-get-stats-lambda |
| mtg-app-sync-moxfield | Python 3.11 | 512 MB | 120s | mtg-app-lambda-role |
| mtgAppProfile | Python 3.11 | 128 MB | 3s | mtg-app-profile-role |
| mtg-app-get-random-decks | Python 3.11 | 128 MB | 3s | mtg-app-get-random-decks |
| mtg-app-list-decks | Python 3.11 | 128 MB | 3s | mtg-app-deck-scan |
| mtg-app-get-diff | Python 3.11 | 128 MB | 20s | mtg_app_get_diff |
| mtg-app-get-games | Python 3.11 | 128 MB | 3s | mtg-app-get-games |
| mtg-app-build-commanders-index | Python 3.11 | 3008 MB | 900s | mtg-app-commanders-index |
| mtg-app-scryfall-batch-download | Python 3.11 | 1024 MB | 120s | scryfall-batch-download |
| mtg-app-deck-versions | Python 3.11 | 128 MB | 3s | mtg-app-deck-versions |

## DynamoDB tables

Current production tables:

- `mtg_app_cards_dim`
- `mtg_app_deck_card_events`
- `mtg_app_deck_cards_current`
- `mtg_app_deck_change_log`
- `mtg_app_deck_diffs`
- `mtg_app_deck_state`
- `mtg_app_deck_state_v2`
- `mtg_app_play_events`
- `mtg_app_scryfall_print_map`
- `mtg_app_user_profile`

All tables are currently classified as **protected / ownership not yet determined**.

Potential legacy tables must not be deleted until their callers and data are verified.

## S3

CommandLog-related buckets:

| Bucket | Current assumed purpose | Classification |
|---|---|---|
| `ignacio-mtg-app-raw-ca-central-1` | Deck snapshots / Scryfall raw data | Protected |
| `mtg-app-ui` | Frontend assets / generated commander index | Protected pending inspection |

## HTTP API

- Name: `log-play-events-api`
- Protocol: HTTP
- Region: `ca-central-1`
- API ID: documented separately / environment-specific

The API name appears to predate its use as the broader CommandLog backend API.

Routes, integrations and JWT authorizer configuration still need inspection.

## EventBridge Scheduler

| Schedule | State |
|---|---|
| `mtg-app-sync-daily` | ENABLED |
| `mtg-app-scryfall-sync` | ENABLED |
| `mtg-app-commanders-index` | ENABLED |

Schedule expressions, targets, execution roles and payloads still need inspection.

## Known migration concerns

1. Production still runs `mtg-app-sync-moxfield`, while the migrated CommandLog ingestion path intentionally no longer supports Moxfield.
1. The exact trigger from Scryfall bulk download to Scryfall loader must be verified.
1. Several DynamoDB tables appear potentially legacy but their usage has not yet been proven.
1. Existing production stateful resources must remain outside CloudFormation ownership during the initial migration.

## Runtime wiring

### Scheduled jobs

| Schedule | Expression | Timezone | Target |
|---|---|---|---|
| `mtg-app-sync-daily` | `rate(30 minutes)` | America/Toronto | `mtg-app-sync-moxfield` |
| `mtg-app-scryfall-sync` | `rate(30 days)` | America/Toronto | `mtg-app-scryfall-batch-download` |
| `mtg-app-commanders-index` | `rate(30 days)` | America/Toronto | `mtg-app-build-commanders-index` |

All schedules currently have flexible time windows disabled.

Despite its name, `mtg-app-sync-daily` executes every 30 minutes.

### Scryfall production pipeline

Current production flow:

1. `mtg-app-scryfall-sync` invokes `mtg-app-scryfall-batch-download`.
2. Downloader writes Scryfall data to `ignacio-mtg-app-raw-ca-central-1`.
3. S3 notification `scryfall-oracle-cards-latest-ingest` invokes
   `mtg-app-scryfall-batch-loader`.
4. Current notification matches:
   - Event: `s3:ObjectCreated:Put`
   - Prefix: `scryfall/oracle_cards`
   - Suffix: `latest.json`

This notification is incompatible with the migrated Scryfall pipeline.

The migrated downloader writes `latest.jsonl.gz` using S3 CopyObject.
The IaC-managed notification must therefore match:

- Event: `s3:ObjectCreated:*`
- Prefix: `scryfall/oracle_cards/`
- Suffix: `latest.jsonl.gz`

This change must occur during the background-events migration, not during the inventory phase.

### Lambda runtime characteristics

All current CommandLog Lambdas:

- Runtime: Python 3.11
- Architecture: x86_64
- Ephemeral storage: 512 MB
- No Lambda layers
- No VPC attachment
- No dead-letter queue
- X-Ray tracing mode: PassThrough

Memory and timeout differ by function and are documented in the Lambda inventory.

### Automatic ingestion migration concern

Production currently invokes `mtg-app-sync-moxfield` every 30 minutes.

The migrated CommandLog implementation intentionally dropped Moxfield support.
The old schedule must not be blindly reproduced in the new infrastructure.
Its replacement/removal must be explicitly decided before production cutover.

## HTTP API

### API configuration

- Name: `log-play-events-api`
- Protocol: HTTP API
- Stage: `$default`
- Auto-deploy: enabled
- Lambda payload format: `2.0`
- Default execute-api endpoint: enabled

The API name is historical and no longer accurately describes its role as the main CommandLog backend API.

### JWT authentication

All application routes use the same JWT authorizer.

- Authorizer name: `MTG-app-login`
- Identity source: `$request.header.Authorization`
- Issuer: Cognito User Pool `ca-central-1_e6TWFI8D9`
- Audience / app client: `m2p7rqmpkq838hhlum98r1msb`

The Cognito User Pool and app client are production dependencies and must be inventoried separately.

### Routes

| Route | Lambda |
|---|---|
| `GET /stats/version` | `mtg-app-stats-version` |
| `GET /me/profile` | `mtgAppProfile` |
| `PUT /me/profile` | `mtgAppProfile` |
| `GET /decks` | `mtg-app-list-decks` |
| `GET /decks/{deck_id}` | `mtg-app-deck-versions` |
| `GET /decks/{deck_id}/diff` | `mtg-app-get-diff` |
| `GET /games` | `mtg-app-get-games` |
| `GET /pick` | `mtg-app-get-random-decks` |
| `POST /play` | `log_play_event` |
| `GET /stats/summary` | `mtg-app-stats-summary` |

### Orphan integration

API integration `o5cigkr` targets the deleted/nonexistent Lambda `mtg-app-get-cards-name`.

No current route references this integration.

Classification: legacy cleanup candidate. Do not remove during inventory.

### CORS

API Gateway currently allows origin:

`https://d2cux7a98zqlb4.cloudfront.net`

Allowed methods:

- GET
- POST
- OPTIONS
- PUT
- DELETE

Allowed headers:

- content-type
- authorization

There are currently no DELETE routes, so DELETE does not need to be carried forward unless required by a future endpoint.

`mtgAppProfile` independently defines `CORS_ORIGIN` as:

`https://d2cux7a98zqlb4.cloudfront.net/`

The trailing slash differs from the API Gateway CORS origin. Whether the Lambda still emits independent CORS headers must be verified before the IaC migration.

## Production resource dependencies

### DynamoDB

Confirmed active references:

| Resource | Referenced by |
|---|---|
| `mtg_app_play_events` | play logging, game retrieval, summary/version stats, random deck |
| `mtg_app_deck_state_v2` | play logging, deck listing, random deck, diff, ingestion |
| `mtg_app_user_profile` | profile, random deck, ingestion |
| `mtg_app_deck_change_log` | deck versions, diff, ingestion |
| `mtg_app_deck_diffs` | diff |
| `mtg_app_cards_dim` | diff, Scryfall loader |
| `mtg_app_scryfall_print_map` | existing production diff and ingestion |

Currently unreferenced by all Lambda environment configuration:

- `mtg_app_deck_state`
- `mtg_app_deck_card_events`
- `mtg_app_deck_cards_current`

These are legacy candidates, but are not approved for deletion.

### S3

`ignacio-mtg-app-raw-ca-central-1` is actively used for:

- deck snapshots
- Scryfall bulk data
- Scryfall loader event source

`mtg-app-ui` is actively used by the commander-index builder.

`mtg-app-ui` has no S3 event notifications.

## Authentication and identity

### Cognito User Pool

Production authentication uses Cognito User Pool:

`ca-central-1_e6TWFI8D9`

Configuration:

- Email is the username attribute.
- Email is automatically verified.
- MFA is disabled.
- Deletion protection is ACTIVE.
- Cognito hosted domain is configured.
- No custom Cognito domain is configured.

Classification: **PROTECTED STATEFUL PRODUCTION RESOURCE**

The existing production User Pool contains user identity state and must not be recreated or replaced during the initial IaC migration.

The production application stack should initially reference the existing User Pool by ID/issuer.

A separate Cognito User Pool should be created for the future development environment.

### Cognito SPA client

Production SPA client:

`m2p7rqmpkq838hhlum98r1msb`

Authentication:

- OAuth authorization code flow
- Scopes: email, openid, profile
- Cognito identity provider
- Refresh token authentication
- SRP authentication
- User existence errors suppressed

Current callback URL:

`https://d2cux7a98zqlb4.cloudfront.net/`

Current logout URL:

`https://d2cux7a98zqlb4.cloudfront.net/`

The client is currently coupled to the legacy CloudFront distribution hostname.

During frontend migration, the new frontend URL must be added to the Cognito
callback/logout configuration before the old URL is removed.

## Frontend delivery

Current CloudFront distribution:

- Distribution ID: `EXPMYKBU51WF2`
- Domain: `d2cux7a98zqlb4.cloudfront.net`
- Enabled: true
- Custom aliases: none
- Default root object: none
- Origin: `mtg-app-ui.s3.ca-central-1.amazonaws.com`
- Origin path: empty

There are no API Gateway custom domains.

Classification:

- Current CloudFront distribution: **REPLACEABLE COMPUTE/DELIVERY INFRASTRUCTURE**
- `mtg-app-ui` bucket: **PROTECTED pending content/security inspection**

Target architecture is not to preserve this CloudFront configuration verbatim.
It will eventually be replaced by an IaC-managed frontend delivery stack using private S3 + CloudFront OAC, with separate ownership for deployed frontend assets and runtime-generated data.

### Current frontend security and delivery

The current CloudFront distribution uses the S3 REST endpoint with Origin Access Control (OAC).

Positive existing configuration:

- S3 Origin Access Control is enabled.
- S3 Block Public Access has all four controls enabled.
- HTTP requests are redirected to HTTPS.
- CloudFront compression is enabled.
- S3 bucket versioning is enabled.
- S3 objects use SSE-S3 (`AES256`) server-side encryption.
- Default root object is `index.html`.

The initial inventory incorrectly reported no default root object. The detailed CloudFront distribution configuration confirms `index.html`.

### Configuration not to reproduce verbatim

The S3 bucket also has static website hosting enabled even though CloudFront uses the S3 REST endpoint through OAC. The website endpoint is therefore not required by the current delivery path and should not be enabled in the target architecture.

The CloudFront distribution currently uses `PriceClass_All`. A narrower price class should be evaluated for the target architecture because CommandLog is currently a low-traffic personal application.

The distribution currently uses the CloudFront default certificate and reports the `TLSv1` minimum protocol policy. The target custom-domain configuration should use ACM, SNI, and a modern TLS security policy.

### Outstanding security finding

`mtg-app-ui` has all S3 Public Access Block controls enabled, but
`get-bucket-policy-status` reports `IsPublic: true`.

The underlying bucket policy must be inspected. The target architecture should use an explicitly private bucket policy granting access only to the appropriate CloudFront distribution/OAC.

### AWS WAF

CloudFront currently has a WAFv2 Web ACL attached:

`CreatedByCloudFront-adc44157`

The Web ACL was not identified in the initial infrastructure inventory.

Its rules, purpose and cost justification must be inspected before deciding whether WAF belongs in the target architecture.

## Inventory conclusion

The production boundary is sufficiently understood to begin the IaC migration.

Protected existing state:

- Production Cognito User Pool
- Production DynamoDB tables currently used by the application
- `ignacio-mtg-app-raw-ca-central-1`
- `mtg-app-ui` until frontend migration is complete

Recreatable infrastructure:

- Lambda functions
- HTTP API
- JWT authorizer configuration
- EventBridge schedules
- Lambda/API permissions
- CloudFront frontend delivery

Known migration changes:

- Moxfield ingestion will not be carried forward.
- Scryfall ingestion must use `latest.jsonl.gz` and support the S3 CopyObject event.
- Frontend hosting will be redesigned as private S3 + CloudFront OAC rather than reproducing the existing distribution verbatim.
- The orphan `mtg-app-get-cards-name` API integration will not be recreated.
- Suspected legacy DynamoDB tables will be investigated only before any cleanup.

Further production configuration will be inspected just-in-time when required by
the resource being migrated.