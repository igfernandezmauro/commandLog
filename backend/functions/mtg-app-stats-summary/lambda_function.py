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
    qs = event.get("queryStringParameters") or {}
    since = (qs.get("since") or "").strip()  # YYYY-MM-DD
    user_key = get_user_key(event)

    # played_at is ISO string, so lexical order matches time order
    if since:
        start = since + "T00:00:00Z"
        key_cond = Key("user_key").eq(user_key) & Key("played_at").gte(start)
    else:
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

    total = len(items)
    wins = sum(1 for x in items if x.get("result") == "WIN")
    losses = sum(1 for x in items if x.get("result") == "LOSS")
    draws = sum(1 for x in items if x.get("result") == "DRAW")
    win_rate = (wins / total) if total else None

    by_deck = {}
    by_store = {}
    mull_sum = 0
    mull_n = 0
    last_played = {}
    turn_order = {}
    mulligans = {"0": {"games": 0, "wins": 0}, "1": {"games": 0, "wins": 0}, "2": {"games": 0, "wins": 0}, "3+": {"games": 0, "wins": 0}}

    for x in items:
        deck_id = str(x.get("deck_id") or "unknown")
        deck_name = x.get("deck_name") or deck_id

        d = by_deck.get(deck_id)
        if not d:
            d = {"deck_id": deck_id, "deck_name": deck_name, "games": 0, "wins": 0, "losses": 0, "draws": 0}
            by_deck[deck_id] = d

        d["games"] += 1
        r = x.get("result")
        if r == "WIN":
            d["wins"] += 1
        elif r == "LOSS":
            d["losses"] += 1
        elif r == "DRAW":
            d["draws"] += 1

        store = (x.get("store") or "").strip()
        if store:
            by_store[store] = by_store.get(store, 0) + 1

        m = as_int(x.get("mulligans"))
        if m is not None:
            k = str(m) if m < 3 else "3+"
            mull_sum += m
            mull_n += 1
            if k not in mulligans:
                mulligans[k] = {"games": 0, "wins": 0}
            mulligans[k]["games"] += 1
            if r == "WIN":
                mulligans[k]["wins"] += 1

        t = as_int(x.get("turn_order"))
        if t is not None:
            k = str(t)
            if not k in turn_order:
                turn_order[k] = {"games": 0, "wins": 0}
            turn_order[k]["games"] += 1
            if r == "WIN":
                turn_order[k]["wins"] += 1

        ts = x.get("played_at")
        if deck_id not in last_played or ts > last_played[deck_id]:
            last_played[deck_id] = ts

    for m in mulligans:
        mulligans[m]["win_rate"] = mulligans[m]["wins"] / mulligans[m]["games"] if mulligans[m]["games"] > 0 else 0

    for t in turn_order:
        turn_order[t]["win_rate"] = turn_order[t]["wins"] / turn_order[t]["games"]

    deck_rows = list(by_deck.values())
    for d in deck_rows:
        d["win_rate"] = (d["wins"] / d["games"]) if d["games"] else None
        d["last_played_at"] = last_played.get(d["deck_id"])

    deck_rows.sort(key=lambda d: (-d["games"], -(d["win_rate"] or 0), d.get("deck_name") or ""))

    store_rows = [{"store": k, "games": v} for k, v in by_store.items()]
    store_rows.sort(key=lambda x: -x["games"])

    out = {
        "user_key": user_key,
        "total_games": total,
        "wins": wins,
        "losses": losses,
        "draws": draws,
        "win_rate": win_rate,
        "mulligans": mulligans,
        "avg_mulligans": (mull_sum / mull_n) if mull_n else None,
        "turn_order": turn_order,
        "by_deck": deck_rows,
        "by_store": store_rows,
        "since": since or None,
    }

    return resp(200, out)
