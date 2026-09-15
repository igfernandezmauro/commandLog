## Status

Production cutover completed successfully.

The legacy production infrastructure was decommissioned after validation of the
CommandLog frontend, API, authentication, background jobs, deck diffs, snapshot
history, and production smoke tests.

| Component | Production resource | Action |
|---|---|---|
| Deck state | `mtg_app_deck_state_v2` | Reuse |
| Play events | `mtg_app_play_events` | Reuse |
| User profile | `mtg_app_user_profile` | Reuse |
| Change log | `mtg_app_deck_change_log` | Reuse |
| Deck diffs | `mtg_app_deck_diffs` | Reuse |
| Cards dim | `mtg_app_cards_dim` | Reuse |
| Cognito pool | Existing prod pool | Reuse |
| Cognito client | Existing prod client | Reuse |
| Snapshot bucket | new `commandlog-prod-...-snapshots` | Create + Migrate |
| Raw bucket | new `commandlog-prod-...-raw` | Create |
| Generated bucket | new `commandlog-prod-...-generated` | Create |
| Web bucket | new `commandlog-prod-...-web` | Create |
| Lambdas | `commandlog-prod-*` | Create |
| HTTP API | new prod API | Create |
| Scryfall schedules/events | new prod resources | Create |
| Moxfield sync | none | Do not migrate |
| Old infra | existing | Keep until cleanup |

### Migration exlusions:
- source=moxfield
- archidekt username=capagmu