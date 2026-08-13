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
from commandlog.users.repository import list_enabled_profiles


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

def build_snapshot_key(username: str, deck_id: str, run_timestamp: str) -> str:
    key_timestamp = run_timestamp.replace(":", "").replace("-", "")

    return f"archidekt/user/{username}/decks/{deck_id}/snapshot_ts={key_timestamp}.json"

def sync_archidekt_user(user_key: str, username: str, *, dry_run: bool = False) -> dict[str, Any]:
    run_timestamp = now_iso()

    decks = archidekt.list_decks(username)

    processed = 0
    changed = 0
    unchanged = 0

    for deck_summary in decks:
        deck_id = archidekt.get_deck_id(deck_summary)

        if not deck_id:
            logger.warning(
                "Skipping Archidekt deck without and ID",
                extra={
                    "data": {
                        "user_key": user_key,
                        "username": username
                    }
                }
            )
            continue

        deck_json = archidekt.fetch_deck(deck_id)

        normalized = archidekt.normalize_deck(deck_json)

        list_hash = normalized["hash"]
        main = normalized["main"]

        snapshot_key = build_snapshot_key(username, deck_id, run_timestamp)

        previous = get_current_deck(user_key, deck_id)

        previous_hash = previous.get("list_hash") if previous else None

        previous_main = previous.get("main") if previous else None

        diff = None

        if isinstance(previous_main, dict):
            diff = compute_diff(previous_main, main)

        deck_changed = previous_hash != list_hash

        if deck_changed:
            changed += 1

            if not dry_run:
                save_snapshot(snapshot_key, deck_json)

                metadata = archidekt.get_metadata(deck_json)

                save_change(
                    {
                        "deck_id": deck_id,
                        "changed_at": run_timestamp,
                        "source": "archidekt",
                        "change_type": "CREATED" if not previous else "UPDATED",
                        "deck_updated_at": metadata.get("changed_at"),
                        "list_hash": list_hash,
                        "diff_summary": diff or {"note": "no previous state"},
                        "s3_key": snapshot_key
                    }
                )

        else:
            unchanged += 1

        if not dry_run:
            metadata = archidekt.get_metadata(deck_json)

            update_deck_state(
                user_key=user_key,
                deck_id=deck_id,
                source="archidekt",
                name=metadata.get("name"),
                commander=archidekt.get_commander(deck_json),
                featured=metadata.get("featured"),
                changed_at=metadata.get("changed_at"),
                created_at=metadata.get("created_at"),
                run_ts=run_timestamp,
                list_hash=list_hash,
                main=main,
                raw_key=snapshot_key
            )

        processed += 1

        time.sleep(0.05)

    result = {
        "user_key": user_key,
        "source": "archidekt",
        "username": username,
        "processed": processed,
        "changed": changed,
        "unchanged": unchanged,
        "run_ts": run_timestamp,
        "dry_run": dry_run
    }

    logger.info(
        "Archidekt ingestion completed",
        extra = {
            "data": {
                "user_key": user_key,
                "processed": processed,
                "changed": changed,
                "unchanged": unchanged,
                "dry_run": dry_run
            }
        }
    )

    return result

def sync_enabled_profiles(*, dry_run: bool = False) -> dict[str, Any]:
    profiles = list_enabled_profiles()

    results = []

    for profile in profiles:
        if profile.get("ingestion_source") != "archidekt":
            continue

        results.append(sync_archidekt_user(profile["user_key"], profile["username"], dry_run=dry_run))

    return {
        "profiles_processed": len(results),
        "results": results,
        "dry_run": dry_run
    }