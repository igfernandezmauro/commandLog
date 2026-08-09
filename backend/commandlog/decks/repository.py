from typing import Any

from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from commandlog.tables import (
    deck_change_log_table,
    deck_diff_table,
    deck_state_table,
    user_profile_table
)

def get_active_source(user_key: str) -> str:
    response = user_profile_table().get_item(
        Key={"user_key": user_key},
        ConsistentRead=True,
    )

    item = response.get("Item") or {}

    return item.get("ingestion_source") or "moxfield"

def get_user_decks(user_key: str) -> list[dict[str, Any]]:
    table = deck_state_table()
    items: list[dict[str, Any]] = []

    response = table.query(
        KeyConditionExpression=Key("user_key").eq(user_key),
    )
    items.extend(response.get("Items", []))

    while "LastEvaluatedKey" in response:
        response = table.query(
            KeyConditionExpression=Key("user_key").eq(user_key),
            ExclusiveStartKey=response["LastEvaluatedKey"],
        )
        items.extend(response.get("Items", []))

    return items

def get_user_deck(user_key: str, deck_id: str) -> dict[str, Any] | None:
    response = deck_state_table().get_item(
        Key={
            "user_key": user_key,
            "deck_id": deck_id,
        },
        ConsistentRead=True,
    )

    return response.get("Item")

def get_deck_change_history(deck_id: str) -> list[dict[str, Any]]:
    table = deck_change_log_table()
    items: list[dict[str, Any]] = []

    response = table.query(
        KeyConditionExpression=Key("deck_id").eq(deck_id),
        ScanIndexForward=False,
    )
    items.extend(response.get("Items", []))

    while "LastEvaluatedKey" in response:
        response = table.query(
            KeyConditionExpression=Key("deck_id"),
            ScanIndexForward=False,
            ExclusiveStartKey=response["LastEvaluatedKey"]
        )
        items.extend(response.get("Items", []))

    return items

def get_change_at_or_before(deck_id: str, target_iso: str) -> dict[str, Any] | None:
    response = deck_change_log_table().query(
        KeyConditionExpression=(
            Key("deck_id").eq(deck_id) & Key("changed_at").lte(target_iso)
        ),
        ScanIndexForward=False,
        Limit=1,
    )

    items = response.get("Items", [])

    return items[0] if items else None

def get_first_change(deck_id: str) -> dict[str, Any] | None:
    response = deck_change_log_table().query(
        KeyConditionExpression=Key("deck_id").eq(deck_id),
        ScanIndexForward=True,
        Limit=1,
    )

    items = response.get("Items", [])

    return items[0] if items else None

def get_cached_diff(deck_id: str, diff_key: str) -> dict[str, Any] | None:
    response = deck_diff_table().get_item(
        Key={
            "deck_id": deck_id,
            "diff_key": diff_key,
        }
    )

    return response.get("Item")

def put_cached_diff_if_absent(item: dict[str, Any]) -> bool:
    try:
        deck_diff_table().put_item(
            Item=item,
            ConditionExpression=(
                "attribute_not_exists(deck_id) AND attribute_not_exists(diff_key)"
            ),
        )
        return True

    except ClientError as error:
        code = error.response["Error"]["Code"]

        if code == "ConditionalCheckFailedException":
            return False

        raise
