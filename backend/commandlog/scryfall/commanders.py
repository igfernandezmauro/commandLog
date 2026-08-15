import json
import re
import time
import unicodedata
import urllib.parse
from typing import Any

from commandlog.aws import s3_client
from commandlog.config import required_env
from commandlog.integrations.http import get_json


SCRYFALL_SEARCH_URL = "https://api.scryfall.com/cards/search"

_non_alnum_re = re.compile(r"[^a-z0-9\s]+")
_ws_re = re.compile(r"\s+")


def normalize_name(value: str | None) -> str:
    if not value:
        return ""

    value = value.lower()
    value = unicodedata.normalize("NFKD", value)
    value = "".join(char for char in value if not unicodedata.combining(char))

    value = _non_alnum_re.sub("", value)
    value = _ws_re.sub(" ", value).strip()

    return value

def add_names(card: dict[str, Any], output: list[dict[str, str]], seen: set[tuple[str, str]]) -> None:
    if card.get("lang") != "en":
        return

    oracle_id = card.get("oracle_id")

    if not oracle_id:
        return

    names: list[str] = []

    if card.get("name"):
        names.append(card["name"])

    if card.get("printed_name"):
        names.append(card["printed_name"])

    for face in card.get("card_faces") or []:
        if not isinstance(face, dict):
            continue

        if face.get("name"):
            names.append(face["name"])

        if face.get("printed_name"):
            names.append(face["printed_name"])

    for name in names:
        normalized = normalize_name(name)

        if not normalized:
            continue

        key = (str(oracle_id), normalized)

        if key in seen:
            continue

        seen.add(key)

        output.append(
            {
                "oracle_id": f"oracle:{oracle_id}",
                "name": name,
                "n": normalized
            }
        )

def fetch_commanders() -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    query = urllib.parse.urlencode(
        {
            "q": "is:commander f:commander",
            "unique": "prints",
            "order": "name"
        }
    )

    url = f"{SCRYFALL_SEARCH_URL}?{query}"

    while True:
        data = get_json(
            url,
            timeout=60
        )

        for card in data.get("data", []):
            add_names(card, output, seen)

        if (data.get("has_more") and data.get("next_page")):
            url = data["next_page"]
            time.sleep(1)
            continue

        break

    output.sort(key=lambda item: item["name"].lower())

    return output

def write_commanders_index(commanders: list[dict[str, str]]) -> dict[str, Any]:
    bucket = required_env("FRONTEND_BUCKET")
    key = required_env("COMMANDERS_INDEX_KEY")

    body = json.dumps(
        commanders,
        separators=(",", ":")
    ).encode("utf-8")

    s3_client().put_object(
        Bucket=bucket,
        Key=key,
        Body=body,
        ContentType="application/json",
        CacheControl="max-age=86400"
    )

    return {
        "count": len(commanders),
        "key": key
    }

def build_commanders_index() -> dict[str, Any]:
    commanders = fetch_commanders()
    return write_commanders_index(commanders)