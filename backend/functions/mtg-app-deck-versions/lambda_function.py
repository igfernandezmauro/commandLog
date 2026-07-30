import os, json
from decimal import Decimal
import boto3
from boto3.dynamodb.conditions import Key

dynamodb = boto3.resource("dynamodb")

CHANGE_LOG_TABLE = os.environ.get("CHANGE_LOG_TABLE")

change_table = dynamodb.Table(CHANGE_LOG_TABLE)

def _json_default(o):
    if isinstance(o, Decimal):
        return int(o) if o % 1 == 0 else float(o)
    raise TypeError(f"Not JSON serializable: {type(o)}")

def _resp(status, body):
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type,Authorization",
        },
        "body": json.dumps(body, default=_json_default),
    }

def lambda_handler(event, context):
    method = event.get("httpMethod") or event.get("requestContext", {}).get("http", {}).get("method")

    if method == "OPTIONS":
        return _resp(200, {"ok": True})

    if method != "GET":
        return _resp(405, {"error": "Method not allowed"})

    deck_id = (event.get("pathParameters") or {}).get("deck_id")
    if not deck_id:
        return _resp(400, {"error": "Missing deck_id in path"})

    try:
        res = change_table.query(
            KeyConditionExpression=Key("deck_id").eq(deck_id),
            ScanIndexForward=False
        )
        items = res.get("Items", [])
    except Exception as e:
        return _resp(500, {"error": "Query failed", "detail": str(e)})

    sanitized = []
    for item in items:
        sanitized.append({
            "deck_id": item.get("deck_id"),
            "changed_at": item.get("changed_at"),
            "change_type": item.get("change_type"),
            "list_hash": item.get("list_hash")
        })

    return _resp(200, sanitized)
