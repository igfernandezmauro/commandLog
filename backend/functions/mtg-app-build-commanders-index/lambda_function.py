import os
import json
import re
import unicodedata
import urllib.parse
import urllib.request
import time
from urllib.error import HTTPError, URLError

import boto3


s3 = boto3.client("s3")

FRONTEND_BUCKET = os.environ["FRONTEND_BUCKET"]
COMMANDERS_INDEX_KEY = os.environ.get("COMMANDERS_INDEX_KEY", "data/commanders_index.json")

SCRYFALL_SEARCH_URL = "https://api.scryfall.com/cards/search"
USER_AGENT = "mtg-app/commanders-index (contact: i.fernandezmauro@gmail.com)"

_non_alnum_re = re.compile(r"[^a-z0-9\s]+")
_ws_re = re.compile(r"\s+")

def normalize_name(s):
    if not s:
        return ""
    s = s.lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = _non_alnum_re.sub("", s)
    s = _ws_re.sub(" ", s).strip()
    return s

def http_get_json(url):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",    
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print("Scryfall HTTPError:", e.code)
        print("URL:", url)
        print("Body:", body[:2000])
        raise
    except URLError as e:
        print("Scryfall URLError:", str(e))
        print("URL:", url)
        raise

def add_names(card, out, seen):
    if card.get("lang") != "en":
        return
    oracle_id = card.get("oracle_id")
    if not oracle_id:
        return
    
    names = []
    if card.get("name"):
        names.append(card["name"])
    if card.get("printed_name"):
        names.append(card["printed_name"])

    for f in (card.get("card_faces") or []):
        if isinstance(f, dict):
            if f.get("name"):
                names.append(f["name"])
            if f.get("printed_name"):
                names.append(f["printed_name"])

    for nm in names:
        n = normalize_name(nm)
        if not n:
            continue
        key = (oracle_id, n)
        if key in seen:
            continue
        seen.add(key)
        out.append({"oracle_id": f"oracle:{oracle_id}", "name": nm, "n":n})

def fetch_query(out, seen):
    url = SCRYFALL_SEARCH_URL + "?q=is:commander%20f:commander&unique=prints&order=name"
    print(url)
    while True:
        data = http_get_json(url)

        for card in data.get("data", []):
            add_names(card, out, seen)

        if data.get("has_more") and data.get("next_page"):
            url = data["next_page"]
            time.sleep(1)
        else:
            break

def lambda_handler(event, context):
    out = []
    seen = set()

    fetch_query(out, seen)

    out.sort(key=lambda x: x["name"].lower())

    body = json.dumps(out, separators=(",", ":")).encode("utf-8")

    s3.put_object(
        Bucket=FRONTEND_BUCKET,
        Key=COMMANDERS_INDEX_KEY,
        Body=body,
        ContentType="application/json",
        CacheControl="max-age=86400",
    )

    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({
            "ok": True,
            "count": len(out),
            "key": COMMANDERS_INDEX_KEY,
        }),
    }
