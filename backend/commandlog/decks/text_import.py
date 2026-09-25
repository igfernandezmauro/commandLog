import re
import hashlib
import json
from typing import Any
from datetime import datetime, timezone

from commandlog.exceptions import ValidationError
from commandlog.integrations.scryfall import resolve_card_names
from commandlog.decks.identity import new_deck_id
from commandlog.ingestion.repository import save_change, save_snapshot, update_deck_state


CARD_LINE = re.compile(
    r"^\s*(?P<quantity>\d+)\s*x?\s+(?P<name>.+?\s*$)",
    re.IGNORECASE
)

PRINTING_SUFFIX = re.compile(
    r"\s+\([A-Za-z0-9]{2,8}\)\s+\S+\s*$"
)

def clean_card_name(value: str) -> str:
    name = value.strip()
    name = PRINTING_SUFFIX.sub("", name)
    return name.strip()

def parse_decklist(text: str) -> list[dict[str, Any]]:
    if not isinstance(text, str) or not text.strip():
        raise ValidationError("Decklist is required.")

    cards: dict[str, dict[str, Any]] = {}
    invalid_lines: list[dict[str, Any]] = []

    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()

        if not line:
            continue

        match = CARD_LINE.match(line)

        if not match:
            invalid_lines.append(
                {
                    "line": line_number,
                    "value": raw_line
                }
            )
            continue

        quantity = int(match.group("quantity"))
        name = clean_card_name(match.group("name"))

        if quantity <= 0 or not name:
            invalid_lines.append(
                {
                    "line": line_number,
                    "value": raw_line
                }
            )
            continue

        key = name.casefold()

        current = cards.setdefault(
            key,
            {
                "name": name,
                "quantity": 0
            }
        )

        current["quantity"] += quantity

    if invalid_lines:
        lines = ", ".join(str(item["line"]) for item in invalid_lines)

        raise ValidationError(f"Invalid decklist line(s): {lines}.")

    if not cards:
        raise ValidationError("Decklist does not contain any cards.")

    return list(cards.values())

def resolve_decklist(parsed_cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    names = [card["name"] for card in parsed_cards]

    resolved_by_name, not_found = resolve_card_names(names)

    if not_found:
        names_text = ", ".join(sorted(not_found))

        raise ValidationError(f"Unknown card(s): {names_text}.")

    resolved_cards: list[dict[str, Any]] = []

    for parsed in parsed_cards:
        requested_name = parsed["name"]
        card = resolved_by_name.get(requested_name.casefold())

        if not card:
            raise ValidationError(f"Unknown card: {requested_name}.")

        oracle_id = card["oracle_id"]

        resolved_cards.append(
            {
                "card_id": f"oracle:{oracle_id}",
                "oracle_id": oracle_id,
                "name": card["name"],
                "quantity": parsed["quantity"],
                "image_art_crop": card.get("image_art_crop"),
                "image_normal": card.get("image_normal")
            }
        )

    return resolved_cards

# Persistence layer

def now_iso() -> str:
    return (datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"))

def build_main(cards: list[dict[str, Any]]) -> dict[str, int]:
    main: dict[str, int] = {}

    for card in cards:
        card_id = str(card["card_id"])
        quantity = int(card["quantity"])

        main[card_id] = main.get(card_id, 0) + quantity

    return main

def build_list_hash(main: dict[str, int]) -> str:
    canonical = json.dumps(main, sort_keys=True,separators=(",", ":"))

    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

def build_text_snapshot(*, name: str, commanders: list[dict[str, str]], featured_commander_id: str, cards: list[dict[str, Any]]) -> dict[str, Any]:
    snapshot_cards: dict[str, dict[str, Any]] = {}

    for card in cards:
        card_id = str(card["card_id"])
        quantity = int(card["quantity"])

        current = snapshot_cards.setdefault(
            card_id,
            {
                "name": card["name"],
                "quantity": 0
            }
        )

        current["quantity"] += quantity

    return {
        "schema_version": 1,
        "source": "text",
        "name": name,
        "commanders": commanders,
        "featured_commander_id": featured_commander_id,
        "cards": snapshot_cards
    }

def build_text_snapshot_key(deck_id: str, timestamp: str) -> str:
    key_timestamp = timestamp.replace(":", "").replace("-", "")

    return (f"text/decks/{deck_id}/snapshot_ts={key_timestamp}.json")

def create_text_deck(*, user_key: str, name: str, commanders: list[dict[str, str]], featured_commander_id: str | None = None, decklist: str, run_timestamp: str | None = None) -> dict[str, Any]:
    name = str(name or "").strip()

    if not name:
        raise ValidationError("Deck name is required.")

    parsed_cards = parse_decklist(decklist)
    resolved_cards = resolve_decklist(parsed_cards)

    (normalized_commanders, commander, featured) = resolve_commanders(commanders, featured_commander_id, resolved_cards)

    if len(normalized_commanders) == 1:
        resolved_featured_commander_id = normalized_commanders[0]["oracle_id"]
    else:
        resolved_featured_commander_id = featured_commander_id

    deck_id = new_deck_id()
    timestamp = run_timestamp or now_iso()

    main = build_main(resolved_cards)
    list_hash = build_list_hash(main)

    snapshot = build_text_snapshot(name=name, commanders=normalized_commanders, featured_commander_id=resolved_featured_commander_id, cards=resolved_cards)

    snapshot_key = build_text_snapshot_key(deck_id, timestamp)

    save_snapshot(snapshot_key, snapshot)

    save_change(
        {
            "deck_id": deck_id,
            "changed_at": timestamp,
            "source": "text",
            "change_type": "CREATED",
            "deck_updated_at": timestamp,
            "list_hash": list_hash,
            "diff_summary": {
                "note": "initial text import"
            },
            "s3_key": snapshot_key
        }
    )

    update_deck_state(
        user_key=user_key,
        deck_id=deck_id,
        source="text",
        external_id=None,
        name=name,
        commander=commander,
        featured=featured,
        changed_at=timestamp,
        created_at=timestamp,
        run_ts=timestamp,
        list_hash=list_hash,
        main=main,
        raw_key=snapshot_key
    )

    return {
        "deck_id": deck_id,
        "source": "text",
        "name": name,
        "commander": commander,
        "card_count": sum(main.values()),
        "unique_cards": len(main),
        "list_hash": list_hash
    }

def resolve_commanders(commanders: list[dict[ str, str]], featured_commander_id: str | None, resolved_cards: list[dict[str, Any]]) -> tuple[list[dict[str, str]], str, str | None]:
    if not commanders:
        raise ValidationError("At least one commander is required.")

    cards_by_id = {
        card["card_id"]: card
        for card in resolved_cards
    }

    normalized_commanders: list[dict[str, str]] = []
    seen: set[str] = set()

    for commander in commanders:
        card_id = str(commander.get("oracle_id") or "").strip()
        name = str(commander.get("name") or "").strip()

        if not card_id or not name:
            raise ValidationError("Invalid commander selection.")

        if card_id in seen:
            continue

        if card_id not in cards_by_id:
            raise ValidationError(f"Commander is not present in decklist: {name}.")

        seen.add(card_id)

        normalized_commanders.append(
            {
                "oracle_id": card_id,
                "name": name
            }
        )

    if not normalized_commanders:
        raise ValidationError("At least one commander is required.")

    if len(normalized_commanders) == 1:
        featured_commander_id = normalized_commanders[0]["oracle_id"]

    select_ids = {
        commander["oracle_id"]
        for commander in normalized_commanders
    }

    if not featured_commander_id:
        raise ValidationError("Featured commander is required when multiple commanders are selected.")

    if featured_commander_id not in select_ids:
        raise ValidationError("Featured commander must be one of the selected commanders.")

    commander_text = " // ".join(commander["name"] for commander in normalized_commanders)

    featured_card = cards_by_id[featured_commander_id]

    featured = (featured_card.get("image_art_crop") or featured_card.get("image_normal"))

    return normalized_commanders, commander_text, featured