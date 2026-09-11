# Technical Debt

## Hardcoded DynamoDB table

`mtg-app-list-decks` directly references:

```python
ddb.Table("mtg_app_user_profile")
```

`get_user_key()` in `mtg-app-get-games` raises `PermissionError`, but `lambda_handler()` does not catch it. A missing JWT claim would therefore become a Lambda failure rather than a clean HTTP `401`.

## Non-transactional game logging

`log_play_event` writes the play event and updates the deck's `last_played_at` value in separate DynamoDB operations.

If the second operation fails, the game remains recorded while the deck timestamp may be stale.

Future action:
- Consider using DynamoDB `TransacWriteItems`.