import os
import json
from datetime import datetime, timezone
import boto3
import botocore
from boto3.dynamodb.conditions import Key
from decimal import Decimal
import urllib

dynamodb = boto3.resource("dynamodb")
s3 = boto3.client("s3")

CHANGE_LOG_TABLE = os.environ["CHANGE_LOG_TABLE"]
DECK_DIFF_TABLE = os.environ["DECK_DIFF_TABLE"]
STATE_TABLE = os.environ["STATE_TABLE"]
CARDS_DIM_TABLE = os.environ["CARDS_DIM_TABLE"]
SNAPSHOT_BUCKET = os.environ["SNAPSHOT_BUCKET"]
PRINT_MAP_TABLE = os.environ["PRINT_MAP_TABLE"]

EXCLUDED_CATEGORIES = set(
    c.strip() for c in os.environ.get("EXCLUDED_CATEGORIES", "Sideboard,Maybeboard").split(",") if c.strip()
)
EMPTY_BASE_HASH = "EMPTY"
UA = "CommandLog/1.0 (personal project; contact: i.fernandezmauro@gmail.com)"
ACCEPT = "application/json;q=0.9;*/*;q=0.8"

change_log_table = dynamodb.Table(CHANGE_LOG_TABLE)
deck_diff_table = dynamodb.Table(DECK_DIFF_TABLE)
state_table = dynamodb.Table(STATE_TABLE)
tbl_print_map = dynamodb.Table(PRINT_MAP_TABLE)

def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def parse_iso8601(date_str):
    try:
        if date_str.endswith("Z"):
            ds = date_str.replace("Z", "+00:00")
        else:
            ds = date_str
        dt = datetime.fromisoformat(ds)
        dt = dt.astimezone(timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        raise ValueError(f"Invalid ISO8601 date: {date_str}")

def resolve_change_at_or_before(deck_id, target_iso):
    resp = change_log_table.query(
        KeyConditionExpression=Key("deck_id").eq(deck_id) & Key("changed_at").lte(target_iso),
        ScanIndexForward=False,
        Limit=1
    )
    items = resp.get("Items", [])
    return items[0] if items else None

def resolve_last_played_at(user_key, deck_id):
    resp = state_table.get_item(
        Key={
            "user_key": user_key,
            "deck_id": deck_id
        },
        ConsistentRead=True
    )
    item = resp.get("Item") or {}
    return item.get("last_played_at")

def resolve_first_change_at(deck_id):
    resp = change_log_table.query(
        KeyConditionExpression=Key("deck_id").eq(deck_id),
        ScanIndexForward=True,
        Limit=1
    )
    items = resp.get("Items", [])
    return items[0].get("changed_at") if items else None

def make_diff_key(base_hash, compare_hash):
    return f"diff#{base_hash}#{compare_hash}"

def get_cached_diff(deck_id, diff_key):
    resp = deck_diff_table.get_item(Key={
        "deck_id": deck_id,
        "diff_key": diff_key
    })
    return resp.get("Item")

def put_diff_if_absent(item):
    try:
        deck_diff_table.put_item(
            Item=item,
            ConditionExpression="attribute_not_exists(deck_id) AND attribute_not_exists(diff_key)",
        )
        return True
    except botocore.exceptions.ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return False
        raise

def s3_get_json(bucket, key):
    obj = s3.get_object(Bucket=bucket, Key=key)
    return json.loads(obj["Body"].read().decode("utf-8"))

def snapshot_items(snapshot_json, source):
    if source == "archidekt":
        if isinstance(snapshot_json, list):
            return snapshot_json
        if isinstance(snapshot_json, dict):
            for k in ("cards", "items", "data"):
                v = snapshot_json.get(k)
                if isinstance(v, list):
                    return v
    elif source == "moxfield":
        cards = snapshot_json.get("commanders") | (snapshot_json.get("mainboard"))
        return list(cards.values())
    return []

def stable_card_id_archidekt(item):
    card = (item or {}).get("card") or {}
    oracle = card.get("oracleCard") or {}

    if oracle.get("uid"):
        return f"oracle:{oracle['uid']}"
    if card.get("uid"):
        return f"print:{card['uid']}"
    if card.get("id") is not None:
        return f"archidekt_card:{card['id']}"
    return None

def display_name_archidekt(item):
    card = (item or {}).get("card") or {}
    oracle = card.get("oracleCard") or {}
    return oracle.get("name") or card.get("displayName") or "Unknown Card"

def normalize_archidekt_snapshot(raw_items):
    out = {}

    for item in raw_items or []:
        qty = int(item.get("quantity") or 0)
        if qty <= 0:
            continue

        cats = set(item.get("categories") or [])
        if cats.intersection(EXCLUDED_CATEGORIES):
            continue

        cid = stable_card_id_archidekt(item)
        if not cid:
            continue

        name = display_name_archidekt(item)

        if cid not in out:
            out[cid] = {"name": name, "qty": qty}
        else:
            out[cid]["qty"] += qty
            if out[cid]["name"] == "Unknown card" and name != "Unknown card":
                out[cid]["name"] = name

    return out

def normalize_moxfield_snapshot(raw_items):
    out = {}
    
    for item in raw_items or []:
        qty = int(item.get("quantity") or 0)
        if qty <= 0:
            continue

        cid = stable_card_id_moxfield(item)
        if not cid:
            continue

        name = display_name_moxfield(item)
        if cid not in out:
            out[cid] = {"name": name, "qty": qty}
        else:
            out[cid]["qty"] += qty
            if out[cid]["name"] == "Unknown card" and name != "Unknown card":
                out[cid]["name"] = name
    
    return out

def compute_diff(base_map, compare_map):
    added = []
    removed = []

    for cid in set(base_map.keys()) | set(compare_map.keys()):
        b = int((base_map.get(cid) or {}).get("qty") or 0)
        c = int((compare_map.get(cid) or {}).get("qty") or 0)

        if c > b:
            added.append({
                "card_id": cid,
                "name": (compare_map.get(cid) or base_map.get(cid) or {}).get("name") or "Unknown card",
                "qty": c - b,
            })
        elif b > c:
            removed.append({
                "card_id": cid,
                "name": (base_map.get(cid) or compare_map.get(cid) or {}).get("name") or "Unknown card",
                "qty": b - c,
            })

    added.sort(key=lambda x: (x["name"], x["card_id"]))
    removed.sort(key=lambda x: (x["name"], x["card_id"]))

    return {
        "added": added,
        "removed": removed,
        "counts": {"added": len(added), "removed": len(removed)}
    }

def normalize_snapshot(snapshot_json, source):
    if source == "moxfield":
        return normalize_moxfield_snapshot(snapshot_items(snapshot_json, source))

    if source == "archidekt":
        return normalize_archidekt_snapshot(snapshot_items(snapshot_json, source))

    raise ValueError(f"Unsupported source: {source}")

def resolve_deck_source(user_key, deck_id):
    resp = state_table.get_item(
        Key={
            "user_key": user_key,
            "deck_id": deck_id
        },
        ConsistentRead=True
    )
    item = resp.get("Item") or {}
    return item.get("source")

# def stable_card_id_moxfield(card_obj: dict):
#     card = (card_obj or {}).get("card") or {}

#     scryfall_id = card.get("scryfall_id")
#     if scryfall_id:
#         oracle_id = resolve_oracle_id_from_scryfall_id(scryfall_id)
#         if oracle_id:
#             return f"oracle:{oracle_id}"
#         return f"print:{scryfall_id}"

#     return None

def stable_card_id_moxfield(card_obj: dict):
    card = (card_obj or {}).get("card") or {}

    if card.get("stable_card_id"):
        return card["stable_card_id"]

    if card.get("oracle_id"):
        return f"oracle:{card['oracle_id']}"

    if card.get("scryfall_id"):
        return f"print:{card['scryfall_id']}"

    return None

def display_name_moxfield(card_obj: dict):
    card = (card_obj or {}).get("card") or {}
    return card.get("name") or "Unknown card"

def resolve_oracle_id_from_scryfall_id(scryfall_id: str):
    resp = tbl_print_map.get_item(Key={"scryfall_id": scryfall_id}, ConsistentRead=True)
    item = resp.get("Item")
    if item and item.get("oracle_id"):
        return item["oracle_id"]

    card = scryfall_get_card_by_id(scryfall_id)
    oracle_id = card.get("oracle_id")
    if not oracle_id:
        return None

    tbl_print_map.put_item(Item={
        "scryfall_id": scryfall_id,
        "oracle_id": oracle_id,
        "name": card.get("name"),
        "fetched_at": now_iso(),
    })

    return oracle_id

def scryfall_get_card_by_id(scryfall_id: str):
    url = f"https://api.scryfall.com/cards/{scryfall_id}"
    req = urllib.request.urlopen(
        url,
        headers={
            "User-Agent": UA,
            "Accept": ACCEPT,
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))

def get_or_compute_diff(deck_id, source, base_date, compare_date, base_empty=False):
    compare_iso = parse_iso8601(compare_date)

    base_row = None
    base_iso = None

    if not base_empty:
        base_iso = parse_iso8601(base_date)
        if base_iso > compare_iso:
            raise ValueError("baseDate must be <= compareDate")

        base_row = resolve_change_at_or_before(deck_id, base_iso)
        if not base_row:
            raise LookupError(f"No snapshot exists at or before baseDate for deck_id={deck_id}")
    
    compare_row = resolve_change_at_or_before(deck_id, compare_iso)   
    if not compare_row:
        raise LookupError(f"No snapshot exists at or before compareDate for deck_id={deck_id}")

    compare_hash = compare_row["list_hash"]
    base_hash = EMPTY_BASE_HASH if base_empty else base_row["list_hash"]
    diff_key = make_diff_key(base_hash, compare_hash)

    if (not base_empty) and (base_hash == compare_hash):
        return {
            "deck_id": deck_id,
            "base_date": base_iso,
            "compare_date": compare_iso,
            "base_hash": base_hash,
            "compare_hash": compare_hash,
            "added": [],
            "removed": [],
            "counts": {"added": 0, "removed": 0},
            "cache_hit": True,
        }

    cached = get_cached_diff(deck_id, diff_key)
    if cached:
        cached["cache_hit"] = True
        cached["compare_date"] = compare_iso

        if base_empty:
            cached["base_date"] = None
            cached["base_hash"] = EMPTY_BASE_HASH
        else:
            cached["base_date"] = base_iso

        return cached

    compare_s3_key = compare_row["s3_key"]
    compare_json = s3_get_json(SNAPSHOT_BUCKET, compare_s3_key)
    compare_map = normalize_snapshot(compare_json, source)

    if base_empty:
        base_s3_key = None
        base_map = {}
    else:
        base_s3_key = base_row["s3_key"]
        base_json = s3_get_json(SNAPSHOT_BUCKET, base_s3_key)
        base_map = normalize_snapshot(base_json, source)

    diff = compute_diff(base_map, compare_map)

    item = {
        "deck_id": deck_id,
        "diff_key": diff_key,
        "base_date": None if base_empty else base_iso,
        "compare_date": compare_iso,
        "base_hash": base_hash,
        "compare_hash": compare_hash,
        "base_s3_key": None if base_empty else base_s3_key,
        "compare_s3_key": compare_s3_key,
        "computed_at": now_iso(),
        "added": diff["added"],
        "removed": diff["removed"],
        "counts": diff["counts"],
    }

    inserted = put_diff_if_absent(item)
    if not inserted:
        cached2 = get_cached_diff(deck_id, diff_key)
        if cached2:
            cached2["cache_hit"] = True
            return cached2

    item["cache_hit"] = False
    return item

def json_safe(obj):
    if isinstance(obj, list):
        return [json_safe(x) for x in obj]
    if isinstance(obj, dict):
        return {k: json_safe(v) for k, v in obj.items()}
    if isinstance(obj, Decimal):
        if obj % 1 == 0:
            return int(obj)
        return float(obj)
    return obj

def chunked(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]

def batch_get_cards_dim(card_ids):
    out = {}

    for batch in chunked(list(card_ids), 100):
        keys = [{"oracle_id": extract_oracle_id(cid)} for cid in batch]

        resp = dynamodb.batch_get_item(
            RequestItems={
                CARDS_DIM_TABLE: {
                    "Keys": keys,
                    "ProjectionExpression": "oracle_id, image_small, image_normal, #n",
                    "ExpressionAttributeNames": {"#n": "name"}
                }
            }
        )

        items = resp.get("Responses", {}).get(CARDS_DIM_TABLE, [])
        for item in items:
            out[f"oracle:{item['oracle_id']}"] = item

        unprocessed = resp.get("UnprocessedKeys", {})
        while unprocessed and unprocessed.get(CARDS_DIM_TABLE, {}).get("Keys"):
            resp = dynamodb.batch_get_item(RequestItems=unprocessed)
            items = resp.get("Responses", {}).get(CARDS_DIM_TABLE, [])
            for item in items:
                out[f"oracle:{item['oracle_id']}"] = item
            unprocessed = resp.get("UnprocessedKeys", {})
    return out

def enrich_diff_with_images(result):
    added = result.get("added") or []
    removed = result.get("removed") or []

    card_ids = {x.get("card_id") for x in added + removed if x.get("card_id")}
    if not card_ids:
        return result

    dim_by_id = batch_get_cards_dim(card_ids)

    for row in added:
        dim = dim_by_id.get(row.get("card_id"))
        if dim:
            row["image_small"] = dim.get("image_small")
            row["image_normal"] = dim.get("image_normal")
    for row in removed:
        dim = dim_by_id.get(row.get("card_id"))
        if dim:
            row["image_small"] = dim.get("image_small")
            row["image_normal"] = dim.get("image_normal")
    return result

def extract_oracle_id(card_id):
    if not card_id:
        return None
    if card_id.startswith("oracle:"):
        return card_id.split("oracle:", 1)[1]
    return card_id

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

def lambda_handler(event, context):
    user_key = get_user_key(event)
    deck_id = event.get("pathParameters")["deck_id"]
    source = resolve_deck_source(user_key, deck_id)
    if not source:
        return {
            "statusCode": 404,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": "Deck not found or missing source"})
        }
    qs = event.get("queryStringParameters") or {}

    base_date = qs.get("baseDate")
    compare_date = qs.get("compareDate")
    base_empty = (qs.get("baseEmpty") or "").lower() in ("true", "1", "yes", "on")

    if not compare_date:
        compare_date = now_iso()

    if not base_empty:
        if not base_date:
            last_played = resolve_last_played_at(user_key, deck_id)
            if last_played:
                base_date = last_played
            else:
                first_change = resolve_first_change_at(deck_id)
                if not first_change:
                    return {
                        "statusCode": 404,
                        "headers": {"Content-Type": "application/json"},
                        "body": json.dumps({"error": "No snapshots found for this deck"})
                    }
                base_date = first_change
    else:
        base_date = base_date

    try:
        if not base_empty and not base_date:
            return {
                "statusCode": 400,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({"error": "baseDate is required unless baseEmpty=true"})
            }

        result = get_or_compute_diff(deck_id, source, base_date, compare_date, base_empty=base_empty)
        result = enrich_diff_with_images(result)
        result["defaults_applied"] = {
            "baseDate": qs.get("baseDate") is None,
            "compareDate": qs.get("compareDate") is None,
            "baseEmpty": base_empty,
        }
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps(json_safe(result))}

    except ValueError as e:
        return {"statusCode": 400, "headers": {"Content-Type": "application/json"}, "body": json.dumps({"error": str(e)})}
    except LookupError as e:
        return {"statusCode": 404, "headers": {"Content-Type": "application/json"}, "body": json.dumps({"error": str(e)})}
