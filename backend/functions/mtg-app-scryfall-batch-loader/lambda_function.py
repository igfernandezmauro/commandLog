import os, json, time, gzip
import urllib.parse
from datetime import datetime, timezone
from decimal import Decimal
import boto3
import re
import unicodedata

s3 = boto3.client("s3")
ddb = boto3.resource("dynamodb")

RAW_BUCKET = os.environ["RAW_BUCKET"]
S3_KEY = os.environ.get("S3_KEY", "scryfall/oracle_cards/latest.json")
CARDS_DIM_TABLE = os.environ["CARDS_DIM_TABLE"]
WRITE_BATCH_SIZE = int(os.environ.get("WRITE_BATCH_SIZE", "2000"))

cards_dim = ddb.Table(CARDS_DIM_TABLE)

def iso_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def normalize_name(s):
    if not s:
        return ""
    
    s = s.lower()

    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    
    return s

def to_dynamodb_safe(value):
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, dict):
        return {k: to_dynamodb_safe(v) for k,v in value.items()}
    if isinstance(value, list):
        return [to_dynamodb_safe(v) for v in value]
    return value

def pick_image_uris(card_obj):
    if card_obj.get("image_uris"):
        return card_obj["image_uris"]
    faces = card_obj.get("card_faces", [])
    if faces and isinstance(faces, list):
        iu = (faces[0] or {}).get("image_uris")
        if iu:
            return iu
    return {}

def load_s3_json(bucket, key):
    obj = s3.get_object(
        Bucket=bucket,
        Key=key
    )
    raw = obj["Body"].read()

    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return json.loads(gzip.decompress(raw).decode("utf-8"))

def write_items(items):
    with cards_dim.batch_writer(overwrite_by_pkeys=["oracle_id"]) as batch:
        for item in items:
            batch.put_item(Item=item)

def get_s3_bucket_key_from_event(event):
    try:
        rec = (event.get("Records") or [])[0]
        if rec.get("eventSource") == "aws:s3":
            bucket = rec["s3"]["bucket"]["name"]
            key = rec["s3"]["object"]["key"]

            key = urllib.parse.unquote_plus(key)
            return bucket, key
    except Exception:
        pass
    return None, None

def lambda_handler(event, context):
    fetched_at = iso_now()
    bucket, key = get_s3_bucket_key_from_event(event)
    bucket = bucket or RAW_BUCKET
    key = key or S3_KEY

    data = load_s3_json(bucket, key)

    buffer = []
    count = 0
    missing_oracle_id = 0

    for c in data:
        oracle_id = c.get("oracle_id")
        if not oracle_id:
            missing_oracle_id += 1
            continue
        name = c.get("name")

        iu = pick_image_uris(c)

        item = {
            "oracle_id": oracle_id,
            "name": name,
            "image_small": iu.get("small"),
            "image_normal": iu.get("normal"),
            "image_large": iu.get("large"),
            "type_line": c.get("type_line"),
            "mana_cost": c.get("mana_cost"),
            "cmc": c.get("cmc"),
            "colors": c.get("colors") or [],
            "color_identity": c.get("color_identity") or [],
            "keywords": c.get("keywords") or [],
            "scryfall_updated_at": c.get("updated_at"),  # may be None; ok
            "last_refreshed_at": fetched_at,
        }

        buffer.append(to_dynamodb_safe(item))
        if len(buffer) >= WRITE_BATCH_SIZE:
            write_items(buffer)
            count += len(buffer)
            buffer = []

    if buffer:
        write_items(buffer)
        count += len(buffer)

    return {
        "status": "ok",
        "cards_written": count,
        "missing_oracle_id": missing_oracle_id,
        "source_bucket": bucket,
        "source_key": key,
        "refreshed_at": fetched_at,
    }