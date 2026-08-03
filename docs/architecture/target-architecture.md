# CommandLog Target Architecture

## Goals

- Run CommandLog locally without touching production.
- Use LocalStack with seeded, persistent local data.
- Keep GitHub as the source of truth.
- Deploy production only from merged code.
- Preserve current production behaviour during migration.
- Avoid overengineering for a solo developer.

## Monorepo Structure

```text
commandlog/
├── backend/
│   ├── functions/
│   │   ├── list_decks/
│   │   ├── get_games/
│   │   ├── log_play_event/
│   │   ├── stats_summary/
│   │   ├── stats_version/
│   │   ├── get_random_decks/
│   │   ├── deck_versions/
│   │   ├── get_diff/
│   │   ├── profile/
│   │   ├── sync_decks/
│   │   ├── scryfall_batch_download/
│   │   ├── scryfall_batch_loader/
│   │   └── build_commanders_index/
│   ├── commandlog/
│   │   ├── auth.py
│   │   ├── aws.py
│   │   ├── config.py
│   │   ├── responses.py
│   │   ├── decks/
│   │   ├── games/
│   │   ├── ingestion/
│   │   └── cards/
│   └── tests/
│       ├── unit/
│       ├── integration/
│       ├── events/
│       └── fixtures/
├── frontend/
├── infrastructure/
├── local/
├── scripts/
├── docs/
└── .github/
```