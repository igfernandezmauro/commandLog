import os, json, datetime
import boto3

ddb = boto3.resource("dynamodb")
tbl_events = ddb.Table(os.environ["PLAY_EVENTS_TABLE"])
tbl_state = ddb.Table(os.environ["STATE_TABLE"])


def now_iso():
    return datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

def parse_iso_z(s):
    return datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))

def safe_duration_seconds(started_at, ended_at):
    if not started_at or not ended_at:
        return None
    try:
        start = parse_iso_z(started_at)
        end = parse_iso_z(ended_at)
        secs = int((end - start).total_seconds())
        
        if secs < 0:
            return None

        if secs > 60 * 60 * 12:
            return None
        
        return secs
    except Exception:
        return None

def update_last_played(user_key, deck_id, played_at):
    tbl_state.update_item(
        Key={"user_key": user_key, "deck_id": deck_id},
        UpdateExpression="SET last_played_at = :p",
        ConditionExpression="attribute_not_exists(last_played_at) OR last_played_at < :p",
        ExpressionAttributeValues={":p": played_at}
    )

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
    body = json.loads(event.get("body", "{}"))

    try:
        user_key = get_user_key(event)
    except PermissionError as e:
        return {"statusCode": 401, "headers": {"Content-Type": "application/json"}, "body": json.dumps({"error": str(e)})}

    deck_id = body.get("deck_id")
    result = body.get("result")
    opponents = body.get("opponents_commanders", [])
    opponents_ids = body.get("opponents_commanders_ids", [])
    notes = body.get("notes", "")
    store = body.get("store", "")
    turn_order = body.get("turn_order", 0)
    mulligans = body.get("mulligans", 0)
    metrics = body.get("metrics") or {}
    started_at = body.get("started_at")
    played_at = now_iso()
    duration_seconds = safe_duration_seconds(started_at, played_at)
    
    if not isinstance(metrics, dict):
        metrics = {}

    if not deck_id or result not in ("WIN", "LOSS", "DRAW"):
        return {"statusCode": 400, "body": "Invalid input"}

    # Read current deck state to freeze decklist
    state = tbl_state.get_item(
        Key={"user_key": user_key, "deck_id": deck_id},
        ConsistentRead=True
    ).get("Item")
    print(state)

    if not state:
        return {"statusCode": 404, "headers": {"Content-Type": "application/json"}, "body": json.dumps({"error": "Deck not found"})}

    item = {
        "user_key": user_key,
        "played_at": played_at,
        "deck_id": deck_id,
        "deck_name": state.get("name"),
        "commander": state.get("commander"),
        "result": result,
        "opponents_commanders": opponents,
        "opponents_commanders_ids": opponents_ids,
        "asof_list_hash": state.get("list_hash"),
        "turn_order": turn_order,
        "mulligans": mulligans,
        "store": store,
        "notes": notes,
        "metrics": metrics
    }

    if started_at:
        item["started_at"] = started_at[:-5] + "Z"
    if duration_seconds is not None:
        item["duration_seconds"] = duration_seconds

    tbl_events.put_item(Item=item)
    update_last_played(user_key, deck_id, played_at)

    return {
        "statusCode": 200,
        "body": json.dumps({"status": "ok", "played_at": played_at})
    }
