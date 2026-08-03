# Technical Debt

## Hardcoded DynamoDB table

`mtg-app-list-decks` directly references:

```python
ddb.Table("mtg_app_user_profile")
```

`get_user_key()` in `mtg-app-get-games` raises `PermissionError`, but `lambda_handler()` does not catch it. A missing JWT claim would therefore become a Lambda failure rather than a clean HTTP `401`.