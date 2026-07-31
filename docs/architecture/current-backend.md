# Current Backend Architecture

## User and ingestion

# mtgAppProfile
Manages the current user’s ingestion profile. `GET` returns saved Archidekt/Moxfield usernames, ingestion source, and whether syncing is enabled. `PUT` saves those settings to `mtg_app_user_profile`; if ingestion is enabled and a username/source is present, it asynchronously invokes `mtg-app-sync-moxfield` to start a sync.

# mtg-app-sync-moxfield
Despite the name, it syncs both Archidekt and Moxfield. It can run for one user from an event payload or scan all enabled profiles. For each deck, it fetches the external deck JSON, normalizes the mainboard, computes a list hash, compares it to current state, writes changed snapshots to S3, records change events in `mtg_app_deck_change_log`, and updates `mtg_app_deck_state_v2`.

## Deck state and history

# mtg-app-list-decks
Returns the authenticated user’s decks from `mtg_app_deck_state_v2`, filtered to the user’s active ingestion source. It includes deck name, commander, featured image, changed time, last played time, source, and an `updated_since_last_played` flag.

# mtg-app-deck-versions
Returns the change/version history for a deck from `mtg_app_deck_change_log`. It expects `deck_id` in the path and returns sanitized records containing `deck_id`, `changed_at`, `change_type`, and `list_hash`, newest first.

# mtg-app-get-diff
Computes or retrieves a decklist diff between two deck snapshots. It resolves the deck’s source, chooses default dates when needed, finds matching change-log snapshots, loads raw snapshots from S3, normalizes Archidekt/Moxfield formats, computes added/removed cards, caches the diff in `mtg_app_deck_diffs`, and enriches diff rows with card images from `mtg_app_cards_dim`.

## Gameplay and analytics

# log_play_event
Records a game result for the authenticated user. It validates `deck_id` and result, reads current deck state so the game is tied to the deck name/commander/list hash at play time, writes a row to `mtg_app_play_events`, and updates `last_played_at` on the deck state table.

# mtg-app-get-games
Returns recent play events for the authenticated user from `mtg_app_play_events`. Supports limit, optional `deck_id`, and optional `since=YYYY-MM-DD`. Results are newest first.

# mtg-app-stats-summary
Builds aggregate stats over the authenticated user’s play events. It computes total games, wins/losses/draws, win rate, per-deck stats, games by store, mulligan stats, turn-order stats, average mulligans, and last-played timestamps. Optional `since=YYYY-MM-DD`.

# mtg-app-stats-version
Builds stats for one deck broken down by deck version/list hash. It requires `deck_id`, scans that user’s play events, groups matching games by `asof_list_hash`, and reports games, wins/losses/draws, win rate, averages for turns/mulligans/missed land drops/feeling, plus first and last played dates.

# mtg-app-get-random-decks
Suggests random decks to play, weighted by heuristics. It loads the user’s active-source decks and play history, then gives more weight to decks played less often, decks not played recently, and decks updated since their last play. Supports count plus tuning parameters alpha, beta, gamma, and delta; delta is returned but currently not applied in the weighting logic.

## Card data enrichment

# mtg-app-scryfall-batch-download
Downloads Scryfall’s `oracle_cards` bulk JSON and stores it in the raw S3 bucket. It writes both a dated historical copy and scryfall/oracle_cards/latest.json, plus metadata about the fetch.

# mtg-app-scryfall-batch-loader
Loads the downloaded Scryfall bulk JSON from S3 into DynamoDB table `mtg_app_cards_dim`. Each card is keyed by `oracle_id` and stores name, image URLs, type line, mana cost, CMC, colors, keywords, Scryfall updated time, and refresh time. This supports image enrichment for diffs.

# mtg-app-build-commanders-index
Builds a frontend commander search index. It queries Scryfall for cards legal as commanders in Commander format, extracts normalized English names and face names, then uploads data/commanders_index.json to the frontend bucket.

## Current data flow

User Profile
    
    ↓
    
External Deck Source
    
    ↓

Current Deck State
    
    ↓

Deck Change History
    
    ↓

Play Events
    
    ↓
    
Statistics and Recommendations

## Known technical debt

1. Rename or generalize mtg-app-sync-moxfield.
1. Stop triggering import automatically from profile updates.
1. Add an explicit manual import endpoint.
1. Move the hardcoded user-profile table name into configuration.
1. Apply or remove the unused delta recommendation parameter.
1. Separate provider-specific parsing from sync orchestration.
1. Extract shared authentication and response handling.
1. Replace expensive DynamoDB scans where practical.
1. Review whether mtg_app_deck_diffs should remain a cache.
1. Investigate the three apparently unused tables.
1. Review why the commander-index function needs 3008 MB and 15 minutes.
1. Rename the misleading mtg-app-sync-daily schedule, which runs every 30 minutes.