import os

from boto3.dynamodb.conditions import Key

from commandlog.auth import get_user_key
from commandlog.aws import dynamodb_resource
from commandlog.responses import json_response


ddb = dynamodb_resource()

tbl_state = ddb.Table(os.environ["STATE_TABLE"])
tbl_users = ddb.Table(os.environ["USERS_TABLE"])

def get_active_source(user_key: str) -> str:
    response = tbl_users.get_item(
        Key={ "user_key": user_key },
        ConsistentRead=True
    )

    item = response.get("Item") or {}

    return item.get("ingestion_source") or "moxfield"

def lambda_handler(event, context):
    try:
        user_key = get_user_key(event)
    except PermissionError as error:
        return json_response(
            401,
            {"error": str(error)},
            cors=False,
        )

    active_source = get_active_source(user_key)

    items = []

    query_kwargs = {
        "KeyConditionExpression": Key("user_key").eq(user_key),
        "ProjectionExpression": "deck_id, #n, commander, featured, changed_at, last_played_at, #s",
        "ExpressionAttributeNames": { "#n": "name", "#s": "source" },
        "ConsistentRead": True,
    }

    response = tbl_state.query(**query_kwargs)
    items.extend(response.get("Items", []))

    while "LastEvaluatedKey" in response:
        response = tbl_state.query(
            ExclusiveStartKey=response["LastEvaluatedKey"],
            **query_kwargs,
        )
        items.extend(response.get("Items", []))

    items = [item for item in items if item.get("source") == active_source]

    for item in items:
        last_played_at = item.get("last_played_at")
        item["updated_since_last_played"] = item["changed_at"] > last_played_at if last_played_at else True

    items.sort(key=lambda item: (item.get("name") or "").lower())

    return json_response(200, items, cors=False)
