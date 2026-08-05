from typing import Any

from commandlog.decks.repository import (
    get_deck_change_history,
    get_user_deck
)
from commandlog.exceptions import NotFoundError


def build_deck_history(user_key: str, deck_id: str) -> list[dict[str, Any]]:
    deck = get_user_deck(user_key, deck_id)

    if not deck:
        raise NotFoundError("Deck not found.")

    history = get_deck_change_history(deck_id)

    return [
        {
            "deck_id": item.get("deck_id"),
            "changed_at": item.get("changed_at"),
            "change_type": item.get("change_type"),
            "list_hash": item.get("list_hash")
        } for item in history
    ]