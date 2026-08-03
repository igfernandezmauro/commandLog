import os, json

from boto3.dynamodb.conditions import Key

from commandlog.auth import get_user_key
from commandlog.aws import dynamodb_resource
from commandlog.responses import json_response


ddb = dynamodb_resource()
tbl = ddb.Table(os.environ["PLAY_EVENTS_TABLE"])

def clamp_int(value, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
        if number < minimum:
            return minimum
        
        if number > maximum:
            return maximum
        
        return number
    
    except (TypeError, ValueError):
        return default

def lambda_handler(event, context):
    try:
        user_key = get_user_key(event)
    except PermissionError as error:
        return json_response(
            401,
            {"error": str(error)},
        )

    query_parameters = event.get("queryStringParameters") or {}

    limit = clamp_int(
        query_parameters.get("limit"),
        default=20,
        minimum=1,
        maximum=200,
    )

    deck_id = (
        query_parameters.get("deck_id") or ""
    ).strip()

    since = (
        query_parameters.get("since") or ""
    ).strip()

    if since:
        start = f"{since}T00:00:00Z"

        key_condition = (
            Key("user_key").eq(user_key)
            & Key("played_at").gte(start)
        )
    else:
        key_condition = Key("user_key").eq(user_key)

    response = tbl.query(
        KeyConditionExpression=key_condition,
        ScanIndexForward=False,
        Limit=limit * 3 if deck_id else limit,
    )

    items = response.get("Items", [])

    if deck_id:
        items = [item for item in items if str(item.get("deck_id")) == deck_id][:limit]

    return json_response(
        200,
        {
            "user_key": user_key,
            "count": len(items),
            "limit": limit,
            "deck_id": deck_id or None,
            "since": since or None,
            "games": items,
        },
    )
