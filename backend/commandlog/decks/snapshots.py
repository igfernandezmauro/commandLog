import json
import os
from typing import Any

from commandlog.aws import s3_client
from commandlog.config import required_env


DEFAULT_EXCLUDED_CATEGORIES = {
    "Sideboard",
    "Maybeboard",
}

def excluded_categories() -> set[str]:
    raw_value = os.getenv("EXCLUDED_CATEGORIES", "Sideboard,Maybeboard")

    return {
        category.strip() for category in raw_value.split(",") if category.strip()
    }

def get_snapshot(key: str) -> dict[str, Any] | list[Any]:
    response = s3_client().get_object(
        Bucket=required_env("SNAPSHOT_BUCKET"),
        Key=key,
    )

    return json.loads(response["Body"].read().decode("utf-8"))

def snapshot_items(snapshot: dict[str, Any] | list[Any], source: str) -> list[dict[str, Any]]:
    if source == "archidekt":
        if isinstance(snapshot, list):
            return snapshot

        if isinstance(snapshot, dict):
            for field in ("cards", "items", "data"):
                value = snapshot.get(field)

                if isinstance(value, list):
                    return value

    if source == "moxfield" and isinstance(snapshot, dict):
        commanders = snapshot.get("commanders") or {}
        mainboard = snapshot.get("mainboard") or {}

        items: list[dict[str, Any]] = []

        if isinstance(commanders, dict):
            items.extend(commanders.values())
        elif isinstance(commanders, list):
            items.extend(commanders)

        if isinstance(mainboard, dict):
            items.extend(mainboard.values())
        elif isinstance(mainboard, list):
            items.extend(mainboard)

        return items

    return []

def stable_archidekt_card_id(item: dict[str, Any]) -> str | None:
    card = item.get("card") or {}
    oracle = card.get("oracleCard") or {}

    if oracle.get("uid"):
        return f"oracle:{oracle['uid']}"

    if card.get("uid"):
        return f"print:{card['uid']}"

    if card.get("id") is not None:
        return f"archidekt_card:{card['id']}"

    return None

def stable_moxfield_card_id(item: dict[str, Any]) -> str | None:
    card = item.get("card") or {}

    if card.get("stable_card_id"):
        return str(card["stable_card_id"])

    if card.get("oracle_id"):
        return f"oracle:{card['oracle_id']}"

    if card.get("scryfall_id"):
        return f"print:{card['scryfall_id']}"

    return None

def normalize_archidekt_snapshot(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    normalized: dict[str, dict[str, Any]] = {}
    excluded = excluded_categories()

    for item in items:
        quantity = int(item.get("quantity") or 0)

        if quantity <= 0:
            continue

        categories = set(item.get("categories") or [])

        if categories.intersection(excluded):
            continue

        card_id = stable_archidekt_card_id(item)

        if not card_id:
            continue

        card = item.get("card") or {}
        oracle = card.get("oracleCard") or {}
        name = (
            oracle.get("name") or card.get("displayName") or "Unknown Card"
        )

        current = normalized.setdefault(
            card_id,
            {
                "name": name,
                "qty": 0,
            },
        )
        current["qty"] += quantity

    return normalized

def normalize_moxfield_snapshot(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    normalized: dict[str, dict[str, Any]] = {}

    for item in items:
        quantity = int(item.get("quantity") or 0)

        if quantity <= 0:
            continue

        card_id = stable_moxfield_card_id(item)

        if not card_id:
            continue

        card = item.get("card") or {}
        name = card.get("name") or "Unknown Card"

        current = normalized.setdefault(
            card_id,
            {
                "name": name,
                "qty": 0,
            },
        )
        current["qty"] += quantity

    return normalized

def normalize_snapshot(snapshot: dict[str, Any] | list[Any], source: str) -> dict[str, dict[str, Any]]:
    if source == "text":
        if not isinstance(snapshot, dict):
            return {}

        return normalize_text_snapshot(snapshot)

    items = snapshot_items(snapshot, source)

    if source == "moxfield":
        return normalize_moxfield_snapshot(items)

    if source == "archidekt":
        return normalize_archidekt_snapshot(items)

    raise ValueError(f"Unsupported source: {source}")

def normalize_text_snapshot(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    cards = snapshot.get("cards") or {}

    if not isinstance(cards, dict):
        return {}

    normalized: dict[str, dict[str, Any]] = {}

    for card_id, card in cards.items():
        if not isinstance(card, dict):
            continue

        quantity = int(card.get("quantity") or card.get("qty") or 0)

        if quantity <= 0:
            continue

        normalized[str(card_id)] = {
            "name": card.get("name") or "Unknown Card",
            "qty": quantity
        }

    return normalized
