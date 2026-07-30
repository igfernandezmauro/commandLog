import os, json, decimal
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

def as_int(x):
    try:
        if x is None:
            return None
        if isinstance(x, decimal.Decimal):
            return int(x)
        return int(x)
    except Exception:
        return None

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

    if event.get("httpMethod") == "OPTIONS":
        return {"statusCode": 200, "headers": CORS_HEADERS, "body": ""}

    qs = event.get("queryStringParameters") or {}
    deck = (qs.get("deck_id") or "").strip()
    if not deck:
        return resp(400, {"error": "Missing required query param: deck_id"})

    key_cond = Key("user_key").eq(user_key)

    items = []
    q = tbl.query(KeyConditionExpression=key_cond)
    items.extend(q.get("Items", []))

    while "LastEvaluatedKey" in q:
        q = tbl.query(
            KeyConditionExpression=key_cond,
            ExclusiveStartKey=q["LastEvaluatedKey"]
        )
        items.extend(q.get("Items", []))

    by_version = {}
    deck_name = deck
    total = {
        "games": 0,
        "wins": 0,
        "losses": 0,
        "draws": 0,
        "turns": 0,
        "mulls": 0,
        "mld": 0,
        "feel": 0,
        "first_played": None,
        "last_played": None,
    }

    for x in items:
        version = str(x.get("asof_list_hash") or "")
        deck_id = str(x.get("deck_id") or "unknown")
        
        if deck_id != deck:
            continue

        if deck_name == deck:
            deck_name = x.get("deck_name") or deck

        h = by_version.get(version)
        if not h:
            h = {"list_hash": version, "games": 0, "wins": 0, "losses": 0, "draws": 0, "turns": 0, "mulligans": 0, "mld": 0, "feeling": 0, "first_played_at": None, "last_played_at": None}
            by_version[version] = h

        total["games"] += 1
        h["games"] += 1
        r = x.get("result")
        if r == "WIN":
            h["wins"] += 1
            total["wins"] += 1
        elif r == "LOSS":
            h["losses"] += 1
            total["losses"] += 1
        elif r == "DRAW":
            h["draws"] += 1
            total["draws"] += 1

        m = as_int(x.get("mulligans"))
        if m is not None:
            h["mulligans"] += m
            total["mulls"] += m

        played_at = x.get("played_at")
        if played_at:
            if not h["first_played_at"] or played_at < h["first_played_at"]:
                h["first_played_at"] = played_at
            if not total["first_played"] or played_at < total["first_played"]:
                total["first_played"] = played_at
            if not h["last_played_at"] or played_at > h["last_played_at"]:
                h["last_played_at"] = played_at
            if not total["last_played"] or played_at > total["last_played"]:
                total["last_played"] = played_at
        
        metrics = x.get("metrics")
        if metrics is not None:
            h["turns"] += as_int(metrics.get("turns")) or 0
            total["turns"] += as_int(metrics.get("turns")) or 0
            h["mld"] += as_int(metrics.get("missed_land_drops")) or 0
            total["mld"] += as_int(metrics.get("missed_land_drops")) or 0
            h["feeling"] += as_int(metrics.get("feeling")) or 0
            total["feel"] += as_int(metrics.get("feeling")) or 0

    version_rows = list(by_version.values())
    for h in version_rows:
        h["win_rate"] = (h["wins"] / h["games"]) if h["games"] else None
        h["avg_turns"] = (h["turns"] / h["games"]) if h["games"] else None
        h["avg_mulligans"] = (h["mulligans"] / h["games"]) if h["games"] else None
        h["avg_mld"] = (h["mld"] / h["games"]) if h["games"] else None
        h["avg_feeling"] = (h["feeling"] / h["games"]) if h["games"] else None
    total["win_rate"] = (total["wins"] / total["games"]) if total["games"] else None
    total["avg_turns"] = (total["turns"] / total["games"]) if total["games"] else None
    total["avg_mulligans"] = (total["mulls"] / total["games"]) if total["games"] else None
    total["avg_mld"] = (total["mld"] / total["games"]) if total["games"] else None
    total["avg_feeling"] = (total["feel"] / total["games"]) if total["games"] else None

    version_rows.sort(key=lambda x: x["last_played_at"], reverse=True)

    out = {
        "user_key": user_key,
        "deck_id": deck,
        "deck_name": deck_name,
        "total": total,
        "versions": version_rows
    }

    return resp(200, out)
