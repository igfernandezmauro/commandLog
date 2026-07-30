import os, json, random
import boto3
from datetime import datetime, timezone
from boto3.dynamodb.conditions import Key

ddb = boto3.resource("dynamodb")
tbl_state = ddb.Table(os.environ["STATE_TABLE"])
tbl_events = ddb.Table(os.environ["PLAY_EVENTS_TABLE"])
tbl_users = ddb.Table(os.environ["USERS_TABLE"])

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

def parse_iso_z(s: str):
    # "2026-02-02T06:01:00Z"
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)

def days_since(iso_z: str, now_utc: datetime):
    if not iso_z:
        return 10_000  # never played -> huge "days since"
    dt = parse_iso_z(iso_z)
    delta = now_utc - dt
    return max(0, int(delta.total_seconds() // 86400))

def updated_since_last_played(deck_updated_at, last_played_at):
    if not deck_updated_at or not last_played_at:
        return False
    return str(deck_updated_at) > str(last_played_at)
    
def weighted_sample_without_replacement(items, weights, k):
    # Simple approach: repeatedly draw one by normalized weights and remove it.
    chosen = []
    pool = list(items)
    w = list(weights)

    for _ in range(min(k, len(pool))):
        total = sum(w)
        if total <= 0:
            # fallback uniform
            idx = random.randrange(len(pool))
        else:
            r = random.random() * total
            acc = 0.0
            idx = 0
            for i, wi in enumerate(w):
                acc += wi
                if r <= acc:
                    idx = i
                    break
        chosen.append(pool.pop(idx))
        w.pop(idx)

    return chosen

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

def get_active_source(user_key: str) -> str:
    resp =  tbl_users.get_item(
        Key={"user_key": user_key},
        ConsistentRead=True
    )
    item = resp.get("Item") or {}
    return item.get("ingestion_source") or "moxfield"

def lambda_handler(event, context):
    user_key = get_user_key(event)
    source = get_active_source(user_key)
    qs = event.get("queryStringParameters") or {}
    count =  int(qs.get("count", "3"))
    count = max(1, min(count, 10))  # keep it sane

    # knobs
    alpha = float(qs.get("alpha", "0.7"))   # games effect
    beta  = float(qs.get("beta", "0.8"))    # recency effect
    gamma = float(qs.get("gamma", "1.5"))   # updated deck effect
    delta = float(qs.get("delta", "2.0"))   # new deck effect

    # 1) Load decks
    decks = []
    r = tbl_state.query(
        KeyConditionExpression=Key("user_key").eq(user_key)
    )

    decks.extend(r.get("Items", []))
    while "LastEvaluatedKey" in r:
        r = tbl_state.query(
            KeyConditionExpression=Key("user_key").eq(user_key)
        )
        decks.extend(r.get("Items", []))

    decks = [x for x in decks if x.get("source") == source]

    # 2) Load all play events for user (paginate)
    events = []
    q = tbl_events.query(KeyConditionExpression=Key("user_key").eq(user_key))
    events.extend(q.get("Items", []))
    while "LastEvaluatedKey" in q:
        q = tbl_events.query(
            KeyConditionExpression=Key("user_key").eq(user_key),
            ExclusiveStartKey=q["LastEvaluatedKey"]
        )
        events.extend(q.get("Items", []))

    # 3) Aggregate per deck
    games_played = {}
    for e in events:
        deck_id = str(e.get("deck_id") or "")
        if not deck_id:
            continue
        games_played[deck_id] = games_played.get(deck_id, 0) + 1

    now_utc = datetime.now(timezone.utc)

    # 4) Compute weights
    candidates = []
    weights = []
    for d in decks:
        deck_id = str(d.get("deck_id") or d.get("id") or "")
        if not deck_id:
            continue

        gp = games_played.get(deck_id, 0)
        last_played_at = d.get("last_played_at", None)
        ds = days_since(last_played_at, now_utc)

        games_factor = 1.0 / ((gp + 1) ** alpha)
        recency_factor = (ds + 1) ** beta

        w = games_factor * recency_factor

        deck_updated_at = d.get("changed_at")
        is_updated = updated_since_last_played(deck_updated_at, last_played_at)
        if is_updated:
            w *= gamma

        # keep randomness alive
        w = max(w, 0.05)

        candidates.append({
            "deck_id": deck_id,
            "name": d.get("name"),
            "commander": d.get("commander"),
            "featured": d.get("featured"),
            "deck_updated_at": deck_updated_at,
            "last_played_at": last_played_at,
            "updated_since_last_played": is_updated,
            "is_new_deck": last_played_at is None,
            "games_played": gp,
            "days_since_last_played": ds,
            "weight": round(w, 6),
        })
        weights.append(w)

    if not candidates:
        return resp(200, {"count": count, "picked": []})

    picked = weighted_sample_without_replacement(candidates, weights, count)

    return resp(200, {
        "count": count,
        "alpha": alpha,
        "beta": beta,
        "gamma": gamma,
        "delta": delta,
        "picked": picked
    })
