import time
from datetime import datetime, timezone
from typing import Any

from commandlog.logging import get_logger
from commandlog.ingestion.repository import (
    get_current_deck,
    save_change,
    save_snapshot,
    update_deck_state
)
from commandlog.integrations import archidekt
from commandlog.decks.identity import new_deck_id
from commandlog.decks.repository import find_user_deck_by_external_id


logger = get_logger(__name__)


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

def compute_diff(old_main: dict[str, int], new_main: dict[str, int]) -> dict[str, Any]:
    added = []
    removed = []
    changed = []

    card_ids = set(old_main) | set(new_main)

    for card_id in card_ids:
        old_quantity = old_main.get(card_id, 0)
        new_quantity = new_main.get(card_id, 0)

        if old_quantity == 0 and new_quantity > 0:
            added.append((card_id, new_quantity))

        elif old_quantity > 0 and new_quantity == 0:
            removed.append((card_id, old_quantity))

        elif old_quantity != new_quantity:
            changed.append(
                (
                    card_id,
                    old_quantity,
                    new_quantity
                )
            )

    return {
        "added": added,
        "removed": removed,
        "changed": changed
    }

def build_snapshot_key(username: str, external_id: str, run_timestamp: str) -> str:
    key_timestamp = run_timestamp.replace(":", "").replace("-", "")

    return f"archidekt/user/{username}/decks/{external_id}/snapshot_ts={key_timestamp}.json"

def sync_archidekt_deck(user_key: str, username: str, external_id: str, *, run_timestamp: str | None = None, dry_run: bool = False):
    external_id = str(external_id).strip()
    run_timestamp = run_timestamp or now_iso()

    matched_deck = find_user_deck_by_external_id(user_key, source="archidekt", external_id=external_id)

    if matched_deck:
        deck_id = str(matched_deck["deck_id"])
    else:
        deck_id = new_deck_id()

    deck_json = archidekt.fetch_deck(external_id)
    normalized = archidekt.normalize_deck(deck_json)

    list_hash = normalized["hash"]
    main = normalized["main"]

    previous = get_current_deck(user_key, deck_id)

    raw_key = previous.get("raw_s3_key") if previous else None
    previous_hash = previous.get("list_hash") if previous else None
    previous_main = previous.get("main") if previous else None
    metadata = archidekt.get_metadata(deck_json)

    if not previous:
        status = "CREATED"
    elif previous_hash != list_hash:
        status = "UPDATED"
    else:
        status = "UNCHANGED"

    if status != "UNCHANGED":
        snapshot_key = build_snapshot_key(username, external_id, run_timestamp)

        diff = compute_diff(previous_main, main) if isinstance(previous_main, dict) else None

        if not dry_run:
            save_snapshot(snapshot_key, deck_json)
            raw_key = snapshot_key

            save_change(
                {
                    "deck_id": deck_id,
                    "changed_at": run_timestamp,
                    "source": "archidekt",
                    "change_type": status,
                    "deck_updated_at": metadata.get("changed_at"),
                    "list_hash": list_hash,
                    "diff_summary": diff or {"note": "no previous state"},
                    "s3_key": snapshot_key
                }
            )

    if not dry_run:
        update_deck_state(
            user_key=user_key,
            deck_id=deck_id,
            source="archidekt",
            external_id=external_id,
            name=metadata.get("name"),
            commander=archidekt.get_commander(deck_json),
            featured=metadata.get("featured"),
            changed_at=metadata.get("changed_at"),
            created_at=metadata.get("created_at"),
            run_ts=run_timestamp,
            list_hash=list_hash,
            main=main,
            raw_key=raw_key
        )

    return {
        "deck_id": deck_id,
        "external_id": external_id,
        "name": metadata.get("name"),
        "status": status
    }

def sync_archidekt_user(user_key: str, username: str, *, dry_run: bool = False) -> dict[str, Any]:
    run_timestamp = now_iso()
    decks = archidekt.list_decks(username)

    results = []

    for deck_summary in decks:
        external_id = archidekt.get_deck_id(deck_summary)

        if not external_id:
            logger.warning(
                "Skipping Archidekt deck without an ID",
                extra={
                    "data": {
                        "user_key": user_key,
                        "username": username
                    }
                }
            )
            continue

        results.append(sync_archidekt_deck(user_key, username, external_id, run_timestamp=run_timestamp, dry_run=dry_run))

        time.sleep(0.05)

    return {
        "source": "archidekt",
        "processed": len(results),
        "created": sum(r["status"] == "CREATED" for r in results),
        "updated": sum(r["status"] == "UPDATED" for r in results),
        "unchanged": sum(r["status"] == "UNCHANGED" for r in results),
        "decks": results,
        "run_ts": run_timestamp,
        "dry_run": dry_run
    }
