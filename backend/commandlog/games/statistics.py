from decimal import Decimal
from typing import Any

RESULT_WIN = "WIN"
RESULT_LOSS = "LOSS"
RESULT_DRAW = "DRAW"


def as_int(value: Any) -> int | None:
    try:
        if value is None:
            return None

        if isinstance(value, Decimal):
            return int(value)

        return int(value)

    except (TypeError, ValueError):
        return None

def safe_rate(numerator: int, denominator: int, *, empty_value: float | None = None) -> float | None:
    if not denominator:
        return empty_value

    return numerator / denominator

def build_summary(games: list[dict[str, Any]], *, user_key: str, since: str | None) -> dict[str, Any]:
    total = len(games)
    wins = sum(1 for game in games if game.get("result") == RESULT_WIN)
    losses = sum(1 for game in games if game.get("result") == RESULT_LOSS)
    draws = sum(1 for game in games if game.get("result") == RESULT_DRAW)

    by_deck: dict[str, dict[str, Any]] = {}
    by_store: dict[str, int] = {}
    last_played: dict[str, str] = {}
    turn_order: dict[str, dict[str, Any]] = {}

    mulligan_stats: dict[str, dict[str, Any]] = {
        "0": {"games": 0, "wins": 0},
        "1": {"games": 0, "wins": 0},
        "2": {"games": 0, "wins": 0},
        "3+": {"games": 0, "wins": 0},
    }

    mulligan_sum = 0
    mulligan_count = 0

    for game in games:
        deck_id = str(game.get("deck_id") or "unknown")
        deck_name = game.get("deck_name") or deck_id
        result = game.get("result")

        deck_stats = by_deck.setdefault(
            deck_id,
            {
                "deck_id": deck_id,
                "deck_name": deck_name,
                "games": 0,
                "wins": 0,
                "losses": 0,
                "draws": 0,
            },
        )

        deck_stats["games"] += 1

        if result == RESULT_WIN:
            deck_stats["wins"] += 1
        elif result == RESULT_DRAW:
            deck_stats["draws"] += 1
        elif result == RESULT_LOSS:
            deck_stats["losses"] += 1

        store = str(game.get("store") or "").strip()

        if store:
            by_store[store] = by_store.get(store, 0) + 1

        mulligans = as_int(game.get("mulligans"))

        if mulligans is not None:
            bucket = str(mulligans) if mulligans < 3 else "3+"

            mulligan_sum += mulligans
            mulligan_count += 1
            mulligan_stats[bucket]["games"] += 1

            if result == RESULT_WIN:
                mulligan_stats[bucket]["wins"] += 1

        order = as_int(game.get("turn_order"))

        if order is not None:
            bucket = str(order)

            order_stats = turn_order.setdefault(
                bucket,
                {"games": 0, "wins": 0},
            )
            order_stats["games"] += 1

            if result == RESULT_WIN:
                order_stats["wins"] += 1

        played_at = game.get("played_at")

        if played_at and (deck_id not in last_played or played_at > last_played[deck_id]):
            last_played[deck_id] = played_at

        for bucket in mulligan_stats.values():
            bucket["win_rate"] = safe_rate(bucket["wins"], bucket["games"], empty_value=0)

        for bucket in turn_order.values():
            bucket["win_rate"] = safe_rate(bucket["wins"], bucket["games"], empty_value=0)

        deck_rows = list(by_deck.values())

        for deck in deck_rows:
            deck["win_rate"] = safe_rate(deck["wins"], deck["games"])
            deck["last_played_at"] = last_played.get(deck["deck_id"])

        deck_rows.sort(
            key=lambda deck: (
                -deck["games"],
                -(deck["win_rate"] or 0),
                deck.get("deck_name") or "",
            )
        )

        store_rows = [
            {"store": store, "games": count}
            for store, count in by_store.items()
        ]
        store_rows.sort(key=lambda row: -row["games"])

        return {
            "user_key": user_key,
            "total_games": total,
            "wins": wins,
            "losses": losses,
            "draws": draws,
            "win_rate": safe_rate(wins, total),
            "mulligans": mulligan_stats,
            "avg_mulligans": safe_rate(mulligan_sum, mulligan_count),
            "turn_order": turn_order,
            "by_deck": deck_rows,
            "by_store": store_rows,
            "since": since,
        }

def build_version_stats(games: list[dict[str, Any]], *, user_key: str, deck_id: str) -> dict[str, Any]:
    by_version: dict[str, dict[str, Any]] = {}
    deck_name = deck_id

    total: dict[str, Any] = {
        "games": 0,
        "wins": 0,
        "losses": 0,
        "draws": 0,
        "turns": 0,
        "mulls": 0,
        "mld": 0,
        "feel": 0,
        "first_played": None,
        "last_played": None,
    }

    for game in games:
        current_deck_id = str(game.get("deck_id") or "unknown")

        if current_deck_id != deck_id:
            continue

        if deck_name == deck_id:
            deck_name = game.get("deck_name") or deck_id

        version = str(game.get("asof_list_hash") or "")

        stats = by_version.setdefault(
            version,
            {
                "list_hash": version,
                "games": 0,
                "wins": 0,
                "losses": 0,
                "draws": 0,
                "turns": 0,
                "mulligans": 0,
                "mld": 0,
                "feeling": 0,
                "first_played_at": None,
                "last_played_at": None,
            },
        )

        total["games"] += 1
        stats["games"] += 1

        result = game.get("result")

        if result == RESULT_WIN:
            stats["wins"] += 1
            total["wins"] += 1
        elif result == RESULT_LOSS:
            stats["losses"] += 1
            total["losses"] += 1
        elif result == RESULT_DRAW:
            stats["draws"] += 1
            total["draws"] += 1

        mulligans = as_int(game.get("mulligans"))

        if mulligans is not None:
            stats["mulligans"] += mulligans
            total["mulls"] += mulligans

        played_at = game.get("played_at")

        if played_at:
            if(not stats["first_played_at"] or played_at < stats["first_played_at"]):
                stats["first_played_at"] = played_at
            if(not stats["last_played_at"] or played_at > stats["last_played_at"]):
                stats["last_played_at"] = played_at
            if(not total["first_played"] or played_at < total["first_played"]):
                total["first_played"] = played_at
            if(not total["last_played"] or played_at > total["last_played"]):
                total["last_played"] = played_at

        metrics = game.get("metrics")

        if isinstance(metrics, dict):
            turns = as_int(metrics.get("turns")) or 0
            missed_land_drops = as_int(metrics.get("missed_land_drops")) or 0
            feeling = as_int(metrics.get("feeling")) or 0

            stats["turns"] += turns
            stats["mld"] += missed_land_drops
            stats["feeling"] += feeling

            total["turns"] += turns
            total["mld"] += missed_land_drops
            total["feeling"] += feeling

    version_rows = list(by_version.values())

    for stats in version_rows:
        games_count = stats["games"]

        stats["win_rate"] = safe_rate(stats["wins"], games_count)
        stats["avg_turns"] = safe_rate(stats["turns"], games_count)
        stats["avg_mulligans"] = safe_rate(stats["mulligans"], games_count)
        stats["avg_mld"] = safe_rate(stats["mld"], games_count)
        stats["avg_feeling"] = safe_rate(stats["feeling"], games_count)

    total_games = total["games"]

    total["win_rate"] = safe_rate(total["wins"], total_games)
    total["avg_turns"] = safe_rate(total["turns"], total_games)
    total["avg_mulligans"] = safe_rate(total["mulls"], total_games)
    total["avg_mld"] = safe_rate(total["mld"], total_games)
    total["avg_feeling"] = safe_rate(total["feel"], total_games)

    version_rows.sort(key=lambda row: row.get("last_played_at") or "", reverse=True)

    return {
        "user_key": user_key,
        "deck_id": deck_id,
        "deck_name": deck_name,
        "total": total,
        "versions": version_rows
    }
