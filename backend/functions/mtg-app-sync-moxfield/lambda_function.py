import os, json, time, hashlib, datetime
import urllib.request
import urllib.parse
from urllib.error import HTTPError, URLError

import boto3
from boto3.dynamodb.conditions import Key

S3_BUCKET = os.environ["BUCKET_NAME"]

# Optional knobs
DRY_RUN = os.environ.get("DRY_RUN", "false").lower() == "true"

DDB_CURRENT = os.environ["STATE_TABLE"]
DDB_CHANGES = os.environ["CHANGE_TABLE"]
# DDB_CARDS_CURRENT = os.environ["CURRENT_CARDS_TABLE"]
# DDB_CARDS_EVENTS = os.environ["CARDS_EVENTS_TABLE"]
DDB_USERS_TABLE = os.environ["USERS_TABLE"]
DDB_PRINT_MAP_TABLE = os.environ["PRINT_MAP_TABLE"]

s3 = boto3.client("s3")
ddb = boto3.resource("dynamodb")
tbl_current = ddb.Table(DDB_CURRENT)
tbl_changes = ddb.Table(DDB_CHANGES)
# tbl_cards_current = ddb.Table(DDB_CARDS_CURRENT)
# tbl_cards_events = ddb.Table(DDB_CARDS_EVENTS)
tbl_users = ddb.Table(DDB_USERS_TABLE)
tbl_print_map = ddb.Table(DDB_PRINT_MAP_TABLE)


UA = "CommandLog/1.0 (personal project; contact: i.fernandezmauro@gmail.com)"
ACCEPT = "application/json;q=0.9;*/*;q=0.8"

# General methods

# Archidekt methods

# Moxfield methods

def get_archidekt_url(uname):
    return f"https://archidekt.com/api/decks/v3/?ownerUsername={urllib.parse.quote(uname)}&deckFormat=3"

def get_moxfield_url(uname):
    return f"https://api.moxfield.com/v2/users/{urllib.parse.quote(uname)}/decks"

def http_get_json(url: str, timeout=20, retries=4):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    last_err = None
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw)
        except HTTPError as e:
            # Back off on throttles / transient errors
            last_err = f"HTTP {e.code}"
            if e.code in (429, 500, 502, 503, 504):
                time.sleep((2 ** attempt) * 0.5)
                continue
            raise
        except URLError as e:
            last_err = str(e)
            time.sleep((2 ** attempt) * 0.5)
    raise RuntimeError(f"Failed GET after retries: {url} ({last_err})")

def stable_card_id_archidekt(card_obj: dict) -> str:
    uid =  card_obj["oracleCard"].get("uid")
    if uid:
        return f"oracle:{str(uid)}"

    # Fallback: name (less stable, but works)
    name = card_obj.get("name") or card_obj.get("card", {}).get("name")
    return f"name:{name}".lower() if name else "unknown"

def stable_card_id_moxfield(card_obj: dict):
    card = (card_obj or {}).get("card") or {}

    scryfall_id = card.get("scryfall_id")
    if scryfall_id:
        oracle_id = resolve_oracle_id_from_scryfall_id(scryfall_id)
        if oracle_id:
            return f"oracle:{oracle_id}"
        return f"print:{scryfall_id}"

    return None

def normalize_archidekt_deck(deck_json: dict) -> dict:
    main = {}
    cards = deck_json.get("cards", [])
    for entry in cards:
        # Archidekt entries usually include quantity + category/board flags
        qty = int(entry.get("quantity", 0) or 0)

        # Identify "mainboard" entries.
        # We’ll treat anything explicitly marked sideboard/maybeboard as non-main.
        cats = entry.get("categories") or []
        cats_norm = {str(c).lower() for c in cats}
        if "sideboard" in cats_norm or "maybeboard" in cats_norm:
            continue

        card = entry.get("card", entry)
        cid = stable_card_id_archidekt(card)

        if qty > 0:
            main[cid] = main.get(cid, 0) + qty

    # Create stable hash input
    items = sorted(main.items(), key=lambda x: x[0])
    payload = json.dumps(items, separators=(",", ":"), ensure_ascii=False)
    h = hashlib.sha256(payload.encode("utf-8")).hexdigest()

    return {"main": main, "hash": h}

def normalize_moxfield_deck(deck_json: dict) -> dict:
    main = {}
    cards = list(deck_json.get("commanders").values()) or []
    cards.extend(list(deck_json.get("mainboard").values()) or [])
    for entry in cards:
        qty = int(entry.get("quantity", 0) or 0)
        cid = stable_card_id_moxfield(entry)

        if qty > 0:
            main[cid] = main.get(cid, 0) + qty

    items = sorted(main.items(), key=lambda x: x[0])
    payload = json.dumps(items, separators=(",", ":"), ensure_ascii=False)
    h = hashlib.sha256(payload.encode("utf-8")).hexdigest()

    return {"main": main, "hash": h}

        
def scryfall_get_card_by_id(scryfall_id: str):
    url = f"https://api.scryfall.com/cards/{scryfall_id}"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": ACCEPT,
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))

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

def s3_put_json(key: str, obj: dict):
    if DRY_RUN:
        return
    s3.put_object(
        Bucket=S3_BUCKET,
        Key=key,
        Body=json.dumps(obj, ensure_ascii=False).encode("utf-8"),
        ContentType="application/json"
    )

def compute_diff(old_main: dict, new_main: dict):
    added, removed, changed = [], [], []
    all_ids = set(old_main) | set(new_main)
    for cid in all_ids:
        a = old_main.get(cid, 0)
        b = new_main.get(cid, 0)
        if a == 0 and b > 0:
            added.append((cid, b))
        elif a > 0 and b == 0:
            removed.append((cid, a))
        elif a != b:
            changed.append((cid, a, b))
    return {"added": added, "removed": removed, "changed": changed}

def list_decks_archidekt(username):
    data = http_get_json(get_archidekt_url(username))
    if isinstance(data, list):
        results = data
    else:
        results = data.get("results") or data.get("data") or data.get("decks") or []
    return results

def list_decks_moxfield(username):
    commander = []
    data = http_get_json(get_moxfield_url(username))
    if isinstance(data, list):
        results = data
    else:
        results = data.get("results") or data.get("data") or data.get("decks") or []
    for r in results:
        if r.get("format") == "commander":
            commander.append(r)
    return commander

def get_archidekt_deck_id(deck_item: dict) -> str:
    return str(deck_item.get("id", ""))
    raise RuntimeError("Could not find deck id in list item")

def get_moxfield_deck_id(deck_item: dict) -> str:
    return str(deck_item.get("publicId", ""))
    raise RuntimeError("Could not find deck id in list item")

def fetch_archidekt_deck(deck_id: str):
    return http_get_json(f"https://archidekt.com/api/decks/{deck_id}/")

def fetch_moxfield_deck(deck_id: str):
    return http_get_json(f"https://api.moxfield.com/v2/decks/all/{deck_id}")

def now_iso():
    return datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

def enrich_moxfield_card_entry_with_oracle_id(item: dict):
    if not isinstance(item, dict):
        return

    card = item.get("card")
    if not isinstance(card, dict):
        return

    if card.get("oracle_id"):
        return

    scryfall_id = card.get("scryfall_id")
    if not scryfall_id:
        return

    oracle_id = resolve_oracle_id_from_scryfall_id(scryfall_id)
    if oracle_id:
        card["oracle_id"] = oracle_id
        card["stable_card_id"] = f"oracle:{oracle_id}"
    else:
        card["stable_card_id"] = f"print:{scryfall_id}"

def enrich_moxfield_snapshot_with_oracle_ids(deck_json: dict):
    if not isinstance(deck_json, dict):
        return deck_json

    commanders = deck_json.get("commanders")
    if isinstance(commanders, dict):
        for _, item in commanders.items():
            enrich_moxfield_card_entry_with_oracle_id(item)

    mainboard = deck_json.get("mainboard")
    if isinstance(mainboard, dict):
        for _, item in mainboard.items():
            enrich_moxfield_card_entry_with_oracle_id(item)

    return deck_json

def scryfall_image_urls(scryfall_id: str):
    a = scryfall_id[0]
    b = scryfall_id[1]
    base = "https://cards.scryfall.io"

    return {
        "image_small": f"{base}/small/front/{a}/{b}/{scryfall_id}.jpg",
        "image_normal": f"{base}/normal/front/{a}/{b}/{scryfall_id}.jpg",
        "image_art_crop": f"{base}/art_crop/front/{a}/{b}/{scryfall_id}.jpg",
    }

def update_deck_state(user_key, deck_id, deck_json, commander, list_hash, main, raw_key, run_ts, source):
    if DRY_RUN:
        return

    if source == "archidekt":
        changed_at = deck_json.get("updatedAt")
        created_at = deck_json.get("createdAt")
        featured = deck_json.get("featured")
    elif source == "moxfield":
        changed_at = deck_json.get("lastUpdatedAtUtc")
        created_at = deck_json.get("createdAtUtc")
        featured = scryfall_image_urls(deck_json.get("main").get("scryfall_id"))["image_art_crop"]
    tbl_current.update_item(
        Key={
            "user_key": user_key,
            "deck_id": str(deck_id),
        },
        UpdateExpression="""
            SET #source = :source,
                #name = :name,
                commander = :commander,
                featured = :featured,
                changed_at = :changed_at,
                created_at = :created_at,
                last_seen_at = :last_seen_at,
                list_hash = :list_hash,
                #main = :main,
                raw_s3_key = :raw_s3_key   
        """,
        ExpressionAttributeNames={
            "#source": "source",
            "#name": "name",
            "#main": "main"
        },
        ExpressionAttributeValues={
            ":source": source,
            ":name": deck_json.get("name"),
            ":commander": commander,
            ":featured": featured,
            ":changed_at": changed_at,
            ":created_at": created_at,
            ":last_seen_at": run_ts,
            ":list_hash": list_hash,
            ":main": main,
            ":raw_s3_key": raw_key
        }
    )

def list_enabled_profiles():
    resp = tbl_users.query(
        IndexName = "gsi_ingestion_enabled",
        KeyConditionExpression=Key("ingestion_enabled_key").eq("1"),
    )
    items = resp.get("Items", [])

    while "LastEvaluatedKey" in resp:
        resp = tbl_users.query(
            IndexName = "gsi_ingestion_enabled",
            KeyConditionExpression=Key("ingestion_enabled_key").eq("1"),
            ExclusiveStartKey=resp["LastEvaluatedKey"]
        )
        items.extend(resp.get("Items", []))

    out = []
    for it in items:
        user_key = it.get("user_key")
        source = (it.get("ingestion_source") or "").strip()
        if source == "archidekt":
            uname = (it.get("archidekt_username") or "").strip()
        elif source == "moxfield":
            uname = (it.get("moxfield_username") or "").strip()
        if user_key and uname:
            out.append({"user_key": user_key, "ingestion_source": source, "username": uname})
    return out

def ingest_archidekt_user(user_key, username):
    run_ts = now_iso()
    key_ts = run_ts.replace(':', '').replace('-', '')

    decks = list_decks_archidekt(username)

    processed = 0
    changed = 0

    for d in decks:
        deck_id = get_archidekt_deck_id(d)
        deck_json = fetch_archidekt_deck(deck_id)

        norm = normalize_archidekt_deck(deck_json)
        list_hash = norm["hash"]

        raw_key = f"archidekt/user/{username}/decks/{deck_id}/snapshot_ts={key_ts}.json"

        # Load previous state
        prev = tbl_current.get_item(Key={
            "user_key": user_key,
            "deck_id": str(deck_id)
        }).get("Item")
        prev_hash = prev.get("list_hash") if prev else None
        prev_main = prev.get("main") if prev else None

        # Compute diff
        diff = None
        if prev_main:
            diff = compute_diff(prev_main, norm["main"])

        if prev_hash != list_hash:
            s3_put_json(raw_key, deck_json)
            # upsert_cards(deck_json, diff)

            if not DRY_RUN:
                # write change event
                tbl_changes.put_item(Item={
                    "deck_id": deck_id,
                    "changed_at": run_ts,
                    "source": "archidekt",
                    "change_type": "CREATED" if not prev else "UPDATED",
                    "deck_updated_at": deck_json.get("updatedAt") or deck_json.get("updated_at"),
                    "list_hash": list_hash,
                    "diff_summary": diff or {"note": "no previous state"},
                    "s3_key": raw_key
                })

            changed += 1

        # update current
        if not DRY_RUN:
            commanders = []
            for card in (deck_json.get("cards") or []):
                if card.get("categories") is None:
                    continue
                if "Commander" in card.get("categories", []):
                    commanders.append(card["card"]["oracleCard"].get("name", ""))
            commanders.sort()
            commander = " // ".join(commanders)
            update_deck_state(
                user_key=user_key,
                deck_id=deck_id,
                deck_json=deck_json,
                commander=commander,
                list_hash=list_hash,
                main=norm["main"],
                raw_key=raw_key,
                run_ts=run_ts,
                source="archidekt"
            )

        processed += 1

        time.sleep(0.05)

def ingest_moxfield_user(user_key, username):
    run_ts = now_iso()
    key_ts = run_ts.replace(":", "").replace("-", "")

    decks = list_decks_moxfield(username)

    processed = 0
    changed = 0

    for d in decks:
        deck_id = get_moxfield_deck_id(d)
        deck_json = fetch_moxfield_deck(deck_id)

        norm = normalize_moxfield_deck(deck_json)
        list_hash = norm["hash"]

        raw_key = f"moxfield/user/{username}/decks/{deck_id}/snapshot_ts={key_ts}.json"

        prev = tbl_current.get_item(Key={
            "user_key": user_key,
            "deck_id": str(deck_id)
        }).get("Item")
        prev_hash = prev.get("list_hash") if prev else None
        prev_main = prev.get("main") if prev else None

        diff = None
        if prev_main:
            diff = compute_diff(prev_main, norm["main"])

        if prev_hash != list_hash:
            full_deck = enrich_moxfield_snapshot_with_oracle_ids(deck_json)
            s3_put_json(raw_key, full_deck)

            if not DRY_RUN:
                tbl_changes.put_item(Item={
                    "deck_id": deck_id,
                    "changed_at": run_ts,
                    "source": "moxfield",
                    "change_type": "CREATED" if not prev else "UPDATED",
                    "deck_updated_at": deck_json.get("lastUpdatedAtUtc"),
                    "list_hash": list_hash,
                    "diff_summary": diff or {"note": "no previous state"},
                    "s3_key": raw_key
                })

            changed += 1

        if not DRY_RUN:
            commanders = []
            for card in (deck_json.get("commanders") or {}):
                commanders.append((card or "").strip())
            commanders.sort()
            commander = " // ".join(commanders)
            update_deck_state(
                user_key=user_key,
                deck_id=deck_id,
                deck_json=deck_json,
                commander=commander,
                list_hash=list_hash,
                main=norm["main"],
                raw_key=raw_key,
                run_ts=run_ts,
                source="moxfield"
            )

def lambda_handler(event, context):
    run_ts = now_iso()

    if event.get("user_key") and event.get("archidekt_username") and event.get("ingestion_source") == "archidekt":
        ingest_archidekt_user(event["user_key"], event["archidekt_username"])
    elif event.get("user_key") and event.get("moxfield_username") and event.get("ingestion_source") == "moxfield":
        ingest_moxfield_user(event["user_key"], event["moxfield_username"])
    else:
        profiles = list_enabled_profiles()

        for p in profiles:
            if p["ingestion_source"] == "archidekt":
                ingest_archidekt_user(p["user_key"], p["username"])
            elif p["ingestion_source"] == "moxfield":
                ingest_moxfield_user(p["user_key"], p["username"])

    return {"run_ts": run_ts, "dry_run": DRY_RUN}
