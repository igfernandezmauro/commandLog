from typing import Any

from boto3.dynamodb.conditions import Key

from commandlog.tables import user_profile_table


def get_user_profile(user_key: str) -> dict[str, Any] | None:
    response = user_profile_table().get_item(
        Key={"user_key": user_key},
        ConsistentRead=True,
    )

    return response.get("Item")

def save_user_profile(item: dict[str, Any]) -> None:
    user_profile_table().put_item(Item=item)

def list_enabled_profiles() -> list[dict[str, str]]:
    table = user_profile_table()

    response = table.query(
        IndexName="gsi_ingestion_enabled",
        KeyConditionExpression=(
            Key("ingestion_enabled_key").eq("1")
        ),
    )

    items = response.get("Items", [])

    while "LastEvaluatedKey" in response:
        response = table.query(
            IndexName="gsi_ingestion_enabled",
            KeyConditionExpression=(
                Key("ingestion_enabled_key").eq("1")
            ),
            ExclusiveStartKey=response["LastEvaluatedKey"],
        )
        items.extend(response.get("Items", []))

    profiles: list[dict[str, str]] = []

    for item in items:
        user_key = item.get("user_key")
        source = str(item.get("ingestion_source") or "").strip()

        username = ""

        if source == "archidekt":
            username = str(item.get("archidekt_username") or "").strip()

        elif source == "moxfield":
            username = str(item.get("moxfield_username") or "").strip()

        if user_key and username:
            profiles.append(
                {
                    "user_key": user_key,
                    "ingestion_source": source,
                    "username": username,
                }
            )

    return profiles
