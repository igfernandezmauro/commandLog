from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from commandlog.tables import cards_dimension_table


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

def dynamodb_safe(value: Any) -> Any:
    if isinstance(value, float):
        return Decimal(str(value))

    if isinstance(value, int):
        return Decimal(value)

    if isinstance(value, dict):
        return { key: dynamodb_safe(item) for key, item in value.items() }

    if isinstance(value, list):
        return [ dynamodb_safe(item) for item in value ]

    return value

def image_uris(card: dict[str, Any]) -> dict[str, Any]:
    if card.get("image_uris"):
        return card["image_uris"]

    faces = card.get("card_faces") or []

    if faces and isinstance(faces, list):
        images = ((faces[0] or {}).get("images_uris"))

        if images:
            return images

    return {}

def transform_card(card: dict[str, Any], *, refreshed_at: str) -> dict[str, Any] | None:
    oracle_id = card.get("oracle_id")

    if not oracle_id:
        return None

    images = image_uris(card)

    return dynamodb_safe(
        {
            "oracle_id": oracle_id,
            "name": card.get("name"),
            "image_small": images.get("small"),
            "image_normal": images.get("normal"),
            "image_large": images.get("large"),
            "type_line": card.get("type_line"),
            "mana_cost": card.get("mana_cost"),
            "cmc": card.get("cmc"),
            "colors": card.get("colors") or [],
            "color_identity": card.get("color_identity") or [],
            "keywords": card.get("keywords") or [],
            "scryfall_updated_at": card.get("updated_at"),
            "last_refreshed_at": refreshed_at
        }
    )

def load_cards(cards, *, write_batch_size: int = 2000) -> dict[str, int]:
    table = cards_dimension_table()

    refreshed_at = now_iso()

    written = 0
    missing_oracle_id = 0
    buffer = []

    for card in cards:
        item = transform_card(card, refreshed_at=refreshed_at)

        if item is None:
            missing_oracle_id += 1
            continue

        buffer.append(item)

        if len(buffer) >= write_batch_size:
            with table.batch_writer(overwrite_by_pkeys=["oracle_id"]) as batch:
                for row in buffer:
                    batch.put_item(Item=row)

            written += len(buffer)
            buffer = []

    if buffer:
        with table.batch_writer(overwrite_by_pkeys=["oracle_id"]) as batch:
            for row in buffer:
                batch.put_item(Item=row)

        written += len(buffer)

    return {
        "cards_written": written,
        "missing_oracle_id": missing_oracle_id
    }