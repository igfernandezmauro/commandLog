import os, json
import urllib.request
from datetime import datetime, timezone
import boto3

s3 = boto3.client("s3")

RAW_BUCKET = os.environ.get("RAW_BUCKET")
S3_PREFIX = os.environ.get("S3_PREFIX", "scryfall/oracle_cards")
USER_AGENT = os.environ.get("UA", "mtg-deck-tracker/0.1 (persona project; contact: i.fernandezmauro@gmail.com)")
ACCEPT = "application/json;q=0.9;*/*;q=0.8"

def now_dt():
    return datetime.now(timezone.utc)

def iso_now():
    return now_dt().strftime("%y-%m-%dT%H:%M:%SZ")

def http_get_json(url, timeout=30):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": ACCEPT,
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))

def http_download_bytes(url, timeout=300):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": ACCEPT,
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()

def put_bytes(bucket, key, body, content_type="application/json"):
    s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=body,
        ContentType=content_type
    )

def lambda_handler(event, context):
    meta = http_get_json("https://api.scryfall.com/bulk-data/oracle_cards", timeout=30)
    download_uri = meta.get("download_uri")
    bulk_updated_at = meta.get("updated_at")

    raw = http_download_bytes(download_uri, timeout=300)

    dt = now_dt()
    day = dt.strftime("%Y%m%d")
    ts = dt.strftime("%Y%m%dT%H%M%SZ")

    historical_key = f"{S3_PREFIX}/dt={day}/oracle_cards_{ts}.json"
    latest_key = f"{S3_PREFIX}/latest.json"
    meta_key = f"{S3_PREFIX}/latest_meta.json"

    put_bytes(RAW_BUCKET, historical_key, raw)
    put_bytes(RAW_BUCKET, latest_key, raw)

    meta_out = {
        "fetched_at": iso_now(),
        "bulk_updated_at": bulk_updated_at,
        "download_uri": download_uri,
        "historical_key": historical_key,
        "latest_key": latest_key,
        "size_bytes": len(raw),
    }
    put_bytes(RAW_BUCKET, meta_key, json.dumps(meta_out).encode("utf-8"))

    return {"status": "ok", **meta_out}
