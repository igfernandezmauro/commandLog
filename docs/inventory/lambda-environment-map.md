# CommandLog Lambda Environment Map

> Historical inventory captured before the CommandLog infrastructure migration.
> Resources, Lambda functions, environment variables, and bucket names documented
> here may have since been decommissioned. This file is retained as a record of
> the pre-migration production architecture.

## log_play_event

- `PLAY_EVENTS_TABLE`: `mtg_app_play_events`
- `STATE_TABLE`: `mtg_app_deck_state_v2`

## mtg-app-stats-version

- `PLAY_EVENTS_TABLE`: `mtg_app_play_events`

## mtg-app-scryfall-batch-loader

- `CARDS_DIM_TABLE`: `mtg_app_cards_dim`
- `RAW_BUCKET`: `ignacio-mtg-app-raw-ca-central-1`

## mtg-app-stats-summary

- `PLAY_EVENTS_TABLE`: `mtg_app_play_events`

## mtg-app-sync-moxfield

- `BUCKET_NAME`: `ignacio-mtg-app-raw-ca-central-1`
- `CHANGE_TABLE`: `mtg_app_deck_change_log`
- `DEBUG_SAVE_SEARCH`: `true`
- `DRY_RUN`: `false`
- `STATE_TABLE`: `mtg_app_deck_state_v2`
- `USERS_TABLE`: `mtg_app_user_profile`

## mtgAppProfile

- `CORS_ORIGIN`: `https://d2cux7a98zqlb4.cloudfront.net/`
- `INGEST_LAMBDA_NAME`: `mtg-app-sync-moxfield`
- `USER_PROFILE_TABLE`: `mtg_app_user_profile`

## mtg-app-get-random-decks

- `PLAY_EVENTS_TABLE`: `mtg_app_play_events`
- `STATE_TABLE`: `mtg_app_deck_state_v2`
- `USERS_TABLE`: `mtg_app_user_profile`

## mtg-app-list-decks

- `STATE_TABLE`: `mtg_app_deck_state_v2`

## mtg-app-get-diff

- `CARDS_DIM_TABLE`: `mtg_app_cards_dim`
- `CHANGE_LOG_TABLE`: `mtg_app_deck_change_log`
- `DECK_DIFF_TABLE`: `mtg_app_deck_diffs`
- `SNAPSHOT_BUCKET`: `ignacio-mtg-app-raw-ca-central-1`
- `STATE_TABLE`: `mtg_app_deck_state_v2`

## mtg-app-get-games

- `PLAY_EVENTS_TABLE`: `mtg_app_play_events`

## mtg-app-build-commanders-index

- `COMMANDERS_INDEX_KEY`: `data/commanders_index.json`
- `FRONTEND_BUCKET`: `mtg-app-ui`

## mtg-app-scryfall-batch-download

- `RAW_BUCKET`: `ignacio-mtg-app-raw-ca-central-1`

## mtg-app-deck-versions

- `CHANGE_LOG_TABLE`: `mtg_app_deck_change_log`