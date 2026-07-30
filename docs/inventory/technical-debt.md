# Technical Debt

## Hardcoded DynamoDB table

`mtg-app-list-decks` directly references:

```python
ddb.Table("mtg_app_user_profile")
```