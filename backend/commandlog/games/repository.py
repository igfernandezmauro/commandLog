from typing import Any

from boto3.dynamodb.conditions import Key

from commandlog.tables import play_events_table


def get_user_games(user_key: str, *, since: str | None = None) -> list[dict[str, Any]]:
    table = play_events_table()

    key_condition = Key("user_key").eq(user_key)

    if since:
        key_condition &= Key("played_at").gte(f"{since}T00:00Z")

    items: list[dict[str, Any]] = []

    response = table.query(
        KeyConditionExpression=key_condition,
    )
    items.extend(response.get("Items", []))

    while "LastEvaluatedKey" in response:
        response = table.query(
            KeyConditionExpression=key_condition,
            ExclusiveStartKey=response["LastEvaluatedKey"],
        )
        items.extend(response.get("Items", []))

    return items