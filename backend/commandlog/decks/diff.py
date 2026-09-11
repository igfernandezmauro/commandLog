from datetime import datetime, timezone
from typing import Any

from commandlog.cards.repository import get_card_images
from commandlog.decks.repository import (
    get_cached_diff,
    get_change_at_or_before,
    get_first_change,
    get_user_deck,
    put_cached_diff_if_absent
)
from commandlog.decks.snapshots import get_snapshot, normalize_snapshot
from commandlog.exceptions import NotFoundError, ValidationError


EMPTY_BASE_HASH = "EMPTY"

def now_iso() -> str:
    return(datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"))

def parse_iso8601(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)

        return (parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"))

    except (TypeError, ValueError) as error:
        raise ValidationError(f"Invalid ISO8601 date: {value}") from error

def make_diff_key(base_hash: str, compare_hash: str) -> str:
    return f"diff#{base_hash}#{compare_hash}"

def compute_diff(base: dict[str, dict[str, Any]], compare: dict[str, dict[str, Any]]) -> dict[str, Any]:
    added: list[dict[str, Any]] = []
    removed: list[dict[str, Any]] = []

    card_ids = set(base) | set(compare)

    for card_id in card_ids:
        base_quantity = int((base.get(card_id) or {}).get("qty") or 0)
        compare_quantity = int((compare.get(card_id) or {}).get("qty") or 0)

        card = (compare.get(card_id) or base.get(card_id) or {})
        name = card.get("name") or "Unknown card"

        if compare_quantity > base_quantity:
            added.append(
                {
                    "card_id": card_id,
                    "name": name,
                    "qty": compare_quantity - base_quantity,
                }
            )

        elif base_quantity > compare_quantity:
            removed.append(
                {
                    "card_id": card_id,
                    "name": name,
                    "qty": base_quantity - compare_quantity,
                }
            )

    added.sort(
        key=lambda card: (
            card["name"],
            card["card_id"],
        )
    )
    removed.sort(
        key=lambda card: (
            card["name"],
            card["card_id"],
        )
    )

    return {
        "added": added,
        "removed": removed,
        "counts": {
            "added": len(added),
            "removed": len(removed),
        },
    }

def enrich_with_images(result: dict[str, Any]) -> dict[str, Any]:
    added = result.get("added") or []
    removed = result.get("removed") or []

    card_ids = {
        row.get("card_id")
        for row in added + removed
        if row.get("card_id")
    }

    images = get_card_images(card_ids)

    for row in added + removed:
        card = images.get(row.get("card_id"))

        if card:
            row["image_small"] = card.get("image_small")
            row["image_normal"] = card.get("image_normal")

    return result

def resolve_default_base_date(deck: dict[str, Any], deck_id: str) -> str:
    last_played_at = deck.get("last_played_at")

    if last_played_at:
        return str(last_played_at)

    first_change = get_first_change(deck_id)

    if not first_change:
        raise NotFoundError("No snapshots found for this deck.")

    return str(first_change["changed_at"])

def build_deck_diff(*, user_key: str, deck_id: str, base_date: str | None, compare_date: str | None, base_empty: bool) -> dict[str, Any]:
    deck = get_user_deck(user_key, deck_id)

    if not deck:
        raise NotFoundError("Deck not found or missing source.")

    source = deck.get("source")

    if not source:
        raise NotFoundError("Deck not found or missing source.")

    requested_compare_date = compare_date or now_iso()
    compare_iso = parse_iso8601(requested_compare_date)

    if base_empty:
        base_iso = None
        base_row = None
    else:
        requested_base_date = (base_date or resolve_default_base_date(deck, deck_id))
        base_iso = parse_iso8601(requested_base_date)

        if base_iso > compare_iso:
            raise ValidationError("baseDate must be less than or equal to compareDate.")

        base_row = get_change_at_or_before(deck_id, base_iso)

        if not base_row:
            raise NotFoundError("No snapshot exists at or before baseDate.")

    compare_row = get_change_at_or_before(deck_id, compare_iso)

    if not compare_row:
        raise NotFoundError("No snapshot exists at or before compareDate.")

    compare_hash = str(compare_row["list_hash"])
    base_hash = (EMPTY_BASE_HASH if base_empty else str(base_row["list_hash"]))

    if not base_empty and base_hash == compare_hash:
        return enrich_with_images(
            {
                "deck_id": deck_id,
                "base_date": base_iso,
                "compare_date": compare_iso,
                "base_hash": base_hash,
                "compare_hash": compare_hash,
                "added": [],
                "removed": [],
                "counts": {
                    "added": 0,
                    "removed": 0
                },
                "cache_hit": True
            }
        )

    diff_key = make_diff_key(base_hash, compare_hash)

    cached = get_cached_diff(deck_id, diff_key)

    if cached:
        result = dict(cached)
        result["cache_hit"] = True
        result["compare_date"] = compare_iso
        result["base_date"] = (None if base_empty else base_iso)
        result["base_hash"] = base_hash

        return enrich_with_images(result)

    compare_key = compare_row.get("s3_key")

    if not compare_key:
        raise NotFoundError("Compare snapshot is missing its S3 key.")

    compare_snapshot = get_snapshot(compare_key)
    compare_map = normalize_snapshot(compare_snapshot, str(source))

    if base_empty:
        base_key = None
        base_map: dict[str, dict[str, Any]] = {}
    else:
        base_key = base_row.get("s3_key")

        if not base_key:
            raise NotFoundError("Base snapshot is missing its S3 key.")

        base_snapshot = get_snapshot(base_key)
        base_map = normalize_snapshot(base_snapshot, str(source))

    calculated = compute_diff(base_map, compare_map)

    item: dict[str, Any] = {
        "deck_id": deck_id,
        "diff_key": diff_key,
        "base_date": None if base_empty else base_iso,
        "compare_date": compare_iso,
        "base_hash": base_hash,
        "compare_hash": compare_hash,
        "base_s3_key": base_key,
        "compare_s3_key": compare_key,
        "computed_at": now_iso(),
        "added": calculated["added"],
        "removed": calculated["removed"],
        "counts": calculated["counts"]
    }

    inserted = put_cached_diff_if_absent(item)

    if not inserted:
        concurrent_cache = get_cached_diff(deck_id, diff_key)

        if concurrent_cache:
            result = dict(concurrent_cache)
            result["cache_hit"] = True
            return enrich_with_images(result)

    item["cache_hit"] = False

    return enrich_with_images(item)
