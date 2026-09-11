import random
from datetime import datetime, timezone
from typing import Any


def parse_iso_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)

def days_since(timestamp: str | None, now_utc: datetime) -> int:
    if not timestamp:
        return 10_000

    parsed = parse_iso_timestamp(timestamp)
    delta = now_utc - parsed

    return max(0, int(delta.total_seconds() // 86_400))

def updated_since_last_played(deck_updated_at: str | None, last_played_at: str | None) -> bool:
    if not deck_updated_at or not last_played_at:
        return False

    return str(deck_updated_at) > str(last_played_at)

def weighted_sample_without_replacement(items: list[dict[str, Any]], weights: list[float], count: int) -> list[dict[str, Any]]:
    chosen: list[dict[str, Any]] = []
    pool = list(items)
    remaining_weights = list(weights)

    for _ in range(min(count, len(pool))):
        total = sum(remaining_weights)

        if total <= 0:
            index = random.randrange(len(pool))
        else:
            threshold = random.random() * total
            accumulated = 0.0
            index = 0

            for position, weight in enumerate(remaining_weights):
                accumulated += weight

                if threshold <= accumulated:
                    index = position
                    break

        chosen.append(pool.pop(index))
        remaining_weights.pop(index)

    return chosen

def build_recommendations(decks: list[dict[str, Any]], games: list[dict[str, Any]], *, count: int, alpha: float, beta: float, gamma: float, now_utc: datetime | None = None) -> dict[str, Any]:
    games_played: dict[str, int] = {}

    for game in games:
        deck_id = str(game.get("deck_id") or "")

        if not deck_id:
            continue

        games_played[deck_id] = (games_played.get(deck_id, 0) + 1)

    now = now_utc or datetime.now(timezone.utc)

    candidates: list[dict[str, Any]] = []
    weights: list[float] = []

    for deck in decks:
        deck_id = str(deck.get("deck_id") or deck.get("id") or "")

        if not deck_id:
            continue

        games_count = games_played.get(deck_id, 0)
        last_played_at = deck.get("last_played_at")
        days_since_played = days_since(last_played_at, now)

        games_factor = 1.0 / ((games_count + 1) ** alpha)
        recency_factor = (days_since_played + 1) ** beta

        weight = games_factor * recency_factor

        deck_updated_at = deck.get("changed_at")
        is_updated = updated_since_last_played(deck_updated_at, last_played_at)

        if is_updated:
            weight *= gamma

        weight = max(weight, 0.05)

        candidates.append(
            {
                "deck_id": deck_id,
                "name": deck.get("name"),
                "commander": deck.get("commander"),
                "featured": deck.get("featured"),
                "deck_updated_at": deck_updated_at,
                "last_played_at": last_played_at,
                "updated_since_last_played": is_updated,
                "is_new_deck": last_played_at is None,
                "games_played": games_count,
                "days_since_last_played": days_since_played,
                "weight": round(weight, 6)
            }
        )
        weights.append(weight)

    picked = weighted_sample_without_replacement(candidates, weights, count)

    return {
        "count": count,
        "alpha": alpha,
        "beta": beta,
        "gamma": gamma,
        "picked": picked
    }
