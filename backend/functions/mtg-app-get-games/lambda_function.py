import os, json
import boto3
from boto3.dynamodb.conditions import Key

ddb = boto3.resource("dynamodb")
tbl = ddb.Table(os.environ["PLAY_EVENTS_TABLE"])

def resp(status, obj):
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "content-type,x-api-key",
            "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
        },
        "body": json.dumps(obj, default=str),
    }

def clamp_int(v, default, lo, hi):
    try:
        n = int(v)
        if n < lo: return lo
        if n > hi: return hi
        return n
    except Exception:
        return default

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
    sub = (_claims_from_event(event) or {}).get("sub")
    if not sub:
        raise PermissionError("Unauthorized: missing sub claim")
    return f"user#{sub}"

def lambda_handler(event, context):
    user_key = get_user_key(event)
    qs = event.get("queryStringParameters") or {}

    # limit=20 (default), clamp to keep it safe/cheap
    limit = clamp_int(qs.get("limit"), default=20, lo=1, hi=200)

    # optional: deck_id filter
    deck_id = (qs.get("deck_id") or "").strip()

    # optional: since=YYYY-MM-DD
    since = (qs.get("since") or "").strip()

    # Sort key is played_at (ISO string); Query can return newest first.
    if since:
        start = since + "T00:00:00Z"
        key_cond = Key("user_key").eq(user_key) & Key("played_at").gte(start)
    else:
        key_cond = Key("user_key").eq(user_key)

    q = tbl.query(
        KeyConditionExpression=key_cond,
        ScanIndexForward=False,  # newest first
        Limit=limit * 3 if deck_id else limit  # overfetch a bit if filtering client-side
    )

    items = q.get("Items", [])

    # If deck_id filter, apply after query (simple, no GSI needed)
    if deck_id:
        items = [x for x in items if str(x.get("deck_id")) == deck_id][:limit]

    # Return items (already newest first)
    return resp(200, {
        "user_key": user_key,
        "count": len(items),
        "limit": limit,
        "deck_id": deck_id or None,
        "since": since or None,
        "games": items
    })
