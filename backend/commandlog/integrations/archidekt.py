import hashlib
import json
import urllib.parse
from typing import Any

from commandlog.integrations.http import get_json

SOURCE = "archidekt"


def list_deck(username: str) -> list[dict[str, Any]]:
    encoded = urllib.parse.quote(username)

    data = get_json(
        f"https://archidekt.com/api/decks/v3/?ownerUsername={encoded}&deckFormat=3"
    )

    if isinstance(data, list):
        return data

    return (
        data.get("results")
        or data.get("data")
        or data.get("decks")
        or []
    )

def get_deck_id(deck: dict[str, Any]) -> str:
    return str(deck.get("id") or "")

def fetch_deck(deck_id: str) -> dict[str, Any]:
    return get_json(
        f"https://archidekt.com/api/decks/{deck_id}/"
    )

def stable_card_id(card: dict[str, Any]) -> str:
    oracle = card.get("oracleCard") or {}

    uid = oracle.get("uid")

    if uid:
        return f"oracle:{uid}"

    name = (
        card.get("name")
        or card.get("card", {}).get("name")
    )

    return (
        f"name:{name}".lower()
        if name
        else "unknown"
    )

def normalize_deck(deck_json: dict[str, Any]) -> dict[str, Any]:
    main: dict[str, int] = {}

    for entry in deck_json.get("cards") or []:
        quantity = int(entry.get("quantity") or 0)

        categories = {
            str(value).lower()
            for value in (entry.get("categories") or [])
        }

        if {"sideboard", "maybeboard"}.intersection(categories):
            continue

        card = entry.get("card") or entry
        card_id = stable_card_id(card)

        if quantity > 0:
            main[card_id] = (main.get(card_id, 0) + quantity)

    payload = json.dumps(
        sorted(main.items()),
        separators=(",", ":"),
        ensure_ascii=False,
    )

    return {
        "main": main,
        "hash": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
    }

def get_commander(deck_json: dict[str, Any]) -> str:
    commanders = []

    for entry in deck_json.get("cards") or []:
        categories = entry.get("categories") or []

        if "Commander" not in categories:
            continue

        card = entry.get("card") or {}
        oracle = card.get("oracleCard") or {}

        commanders.append(oracle.get("name") or "")

    commanders = [name for name in commanders if name]
    commanders.sort()

    return " // ".join(commanders)

def get_metadata(deck_json: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": deck_json.get("name"),
        "changed_at": deck_json.get("updatedAt"),
        "created_at": deck_json.get("createdAt"),
        "featured": deck_json.get("featured"),
    }