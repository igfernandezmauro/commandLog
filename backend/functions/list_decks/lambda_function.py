import os, json, boto3
from boto3.dynamodb.conditions import Key
from decimal import Decimal

aws_endpoint_url = os.getenv("AWS_ENDPOINT_URL")

dynamodb_options = {
    "region_name": os.getenv("AWS_REGION", "ca-central-1"),
}

if aws_endpoint_url:
    dynamodb_options["endpoint_url"] = aws_endpoint_url

ddb = boto3.resource("dynamodb", **dynamodb_options)

tbl_state = ddb.Table(os.environ["STATE_TABLE"])
tbl_users = ddb.Table(os.environ["USERS_TABLE"])

def _claims_from_event(event: dict) -> dict:
    rc = (event or {}).get("requestContext") or {}

    jwt = (rc.get("authorizer") or {}).get("jwt") or {}
    claims = jwt.get("claims")
    if isinstance(claims, dict) and claims:
        return claims

    claims = (rc.get("authorizer") or {}).get("claims")
    if isinstance(claims, dict) and claims:
        return claims

    return {}

def get_user_key(event: dict) -> str:
    claims = _claims_from_event(event)
    sub = claims.get("sub")
    if not sub:
        raise PermissionError("Unauthorized: missing sub claim")
    return f"user#{sub}"

def get_active_source(user_key: str) -> str:
    resp = tbl_users.get_item(
        Key={ "user_key": user_key },
        ConsistentRead=True
    )
    item = resp.get("Item") or {}
    return item.get("ingestion_source") or "moxfield"

def json_safe(obj):
    if isinstance(obj, list):
        return [json_safe(x) for x in obj]
    if isinstance(obj, dict):
        return {k: json_safe(v) for k, v in obj.items()}
    if isinstance(obj, Decimal):
        return int(obj) if obj % 1 == 0 else float(obj)
    return obj

def lambda_handler(event, context):
    try:
        user_key = get_user_key(event)
    except PermissionError as e:
        return {
            "statusCode": 401,
            "headers": { "Content-Type": "application/json" },
            "body": json.dumps({ "error": str(e) })
        }

    active_source = get_active_source(user_key)

    items = []
    query_kwargs = {
        "KeyConditionExpression": Key("user_key").eq(user_key),
        "ProjectionExpression": "deck_id, #n, commander, featured, changed_at, last_played_at, #s",
        "ExpressionAttributeNames": { "#n": "name", "#s": "source" },
        "ConsistentRead": True,
    }

    resp = tbl_state.query(**query_kwargs)
    items.extend(resp.get("Items", []))

    while "LastEvaluatedKey" in resp:
        resp = tbl_state.query(ExclusiveStartKey=resp["LastEvaluatedKey"], **query_kwargs)
        items.extend(resp.get("Items", []))

    items = [x for x in items if x.get("source") == active_source]

    for it in items:
        it["updated_since_last_played"] = it["changed_at"] > it.get("last_played_at") if it.get("last_played_at") else True

    items.sort(key=lambda x: (x.get("name") or "").lower())

    return {
        "statusCode": 200,
        "headers": { "Content-Type": "application/json" },
        "body": json.dumps(json_safe(items)),
    }
