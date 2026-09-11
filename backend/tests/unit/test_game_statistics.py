from commandlog.games.statistics import build_summary, build_version_stats


def test_summary_aggregates_all_games():
    games = [
        {
            "deck_id": "deck-a",
            "deck_name": "Deck A",
            "result": "WIN",
            "store": "Store A",
            "mulligans": 0,
            "turn_order": 1,
            "played_at": "2026-01-01T12:00:00Z"
        },
        {
            "deck_id": "deck-a",
            "deck_name": "Deck A",
            "result": "LOSS",
            "store": "Store A",
            "turn_order": 2,
            "played_at": "2026-01-03T12:00:00Z"
        },
        {
            "deck_id": "deck-b",
            "deck_name": "Deck B",
            "result": "DRAW",
            "store": "Store B",
            "mulligans": 2,
            "turn_order": 1,
            "played_at": "2026-01-02T12:00:00Z"
        }
    ]

    result = build_summary(
        games,
        user_key="user#test",
        since=None
    )

    assert result["total_games"] == 3
    assert result["wins"] == 1
    assert result["losses"] == 1
    assert result["draws"] == 1
    assert result["win_rate"] == 1/3

    # Only games with mulligan data count towards the average.
    assert result["avg_mulligans"] == 1.0

    decks = { row["deck_id"]: row for row in result["by_deck"] }

    assert decks["deck-a"]["games"] == 2
    assert decks["deck-a"]["wins"] == 1
    assert decks["deck-a"]["losses"] == 1
    assert decks["deck-a"]["win_rate"] == 0.5
    assert decks["deck-a"]["last_played_at"] == "2026-01-03T12:00:00Z"

    assert decks["deck-b"]["games"] == 1
    assert decks["deck-b"]["draws"] == 1

    stores = { row["store"]: row["games"] for row in result["by_store"] }

    assert stores == { "Store A": 2, "Store B": 1 }

    assert result["turn_order"]["1"] == { "games": 2, "wins": 1, "win_rate": 0.5 }
    assert result["turn_order"]["2"] == { "games": 1, "wins": 0, "win_rate": 0 }

def test_summary_mulligan_average_ignores_missing_values():
    games = [
        {
            "deck_id": "deck-a",
            "result": "WIN",
            "mulligans": 1
        },
        {
            "deck_id": "deck-a",
            "result": "LOSS"
        },
        {
            "deck_id": "deck-a",
            "result": "LOSS",
            "mulligans": 3
        }
    ]

    result = build_summary(
        games,
        user_key="user#test",
        since=None
    )

    assert result["total_games"] == 3
    assert result["avg_mulligans"] == 2.0

def test_version_stats_optional_metrics_ignore_missing_values():
    games = [
        {
            "deck_id": "deck-a",
            "deck_name": "Deck A",
            "asof_list_hash": "version-1",
            "result": "WIN",
            "mulligans": 1,
            "played_at": "2026-01-01T12:00:00Z",
            "metrics": {
                "turns": 8,
                "missed_land_drops": 2,
                "feeling": 4,
            },
        },
        {
            "deck_id": "deck-a",
            "deck_name": "Deck A",
            "asof_list_hash": "version-1",
            "result": "LOSS",
            "played_at": "2026-01-02T12:00:00Z",
            "metrics": {
                "turns": 10,
            },
        },
        {
            "deck_id": "deck-a",
            "deck_name": "Deck A",
            "asof_list_hash": "version-2",
            "result": "DRAW",
            "mulligans": 0,
            "played_at": "2026-01-03T12:00:00Z",
            "metrics": {
                "missed_land_drops": 0,
                "feeling": 5,
            },
        },

        # Must not contribute because this is another deck.
        {
            "deck_id": "deck-b",
            "deck_name": "Deck B",
            "asof_list_hash": "other-version",
            "result": "WIN",
            "mulligans": 3,
            "played_at": "2026-01-04T12:00:00Z",
            "metrics": {
                "turns": 20,
                "missed_land_drops": 7,
                "feeling": 1,
            },
        },
    ]

    result = build_version_stats(
        games,
        user_key="user#test",
        deck_id="deck-a"
    )

    total = result["total"]

    assert total["games"] == 3
    assert total["wins"] == 1
    assert total["losses"] == 1
    assert total["draws"] == 1

    # turns exists only in two games (8 + 10) / 2
    assert total["avg_turns"] == 9.0

    # mulligans exists only in two games (1 + 0) / 2
    assert total["avg_mulligans"] == 0.5

    # MLD exists only in two games (2 + 0) / 2
    assert total["avg_mld"] == 1.0

    # feeling exists only in two games (4 + 5) / 2
    assert total["avg_feeling"] == 4.5

    assert total["first_played"] == "2026-01-01T12:00:00Z"
    assert total["last_played"] == "2026-01-03T12:00:00Z"

    versions = { row["list_hash"]: row for row in result["versions"] }

    version_1 = versions["version-1"]

    assert version_1["games"] == 2
    assert version_1["wins"] == 1
    assert version_1["losses"] == 1
    assert version_1["win_rate"] == 0.5

    assert version_1["avg_turns"] == 9.0
    assert version_1["avg_mulligans"] == 1.0
    assert version_1["avg_mld"] == 2.0
    assert version_1["avg_feeling"] == 4.0

    version_2 = versions["version-2"]

    assert version_2["games"] == 1
    assert version_2["draws"] == 1

    assert version_2["avg_turns"] is None
    assert version_2["avg_mulligans"] == 0
    assert version_2["avg_mld"] == 0
    assert version_2["avg_feeling"] == 5

def test_version_stats_with_no_optional_metrics_returns_none_averages():
    games = [
        {
            "deck_id": "deck-a",
            "deck_name": "Deck A",
            "asof_list_hash": "version-1",
            "result": "WIN",
            "played_at": "2026-01-01T12:00:00Z",
        }
    ]

    result = build_version_stats(
        games,
        user_key="user#test",
        deck_id="deck-a"
    )

    total = result["total"]
    version = result["versions"][0]

    assert total["avg_turns"] is None
    assert total["avg_mulligans"] is None
    assert total["avg_mld"] is None
    assert total["avg_feeling"] is None

    assert version["avg_turns"] is None
    assert version["avg_mulligans"] is None
    assert version["avg_mld"] is None
    assert version["avg_feeling"] is None

def test_version_stats_ignores_other_decks():
    games = [
        {
            "deck_id": "deck-a",
            "deck_name": "Deck A",
            "asof_list_hash": "version-a",
            "result": "WIN",
            "mulligans": 1,
            "played_at": "2026-01-01T12:00:00Z",
            "metrics": {
                "turns": 8,
                "missed_land_drops": 1,
                "feeling": 4,
            },
        },
        {
            "deck_id": "deck-b",
            "deck_name": "Deck B",
            "asof_list_hash": "version-b",
            "result": "LOSS",
            "mulligans": 3,
            "played_at": "2026-01-02T12:00:00Z",
            "metrics": {
                "turns": 20,
                "missed_land_drops": 5,
                "feeling": 1,
            },
        }
    ]

    result = build_version_stats(
        games,
        user_key="user#test",
        deck_id="deck-a"
    )

    assert result["deck_id"] == "deck-a"
    assert result["deck_name"] == "Deck A"

    assert result["total"]["games"] == 1
    assert result["total"]["wins"] == 1
    assert result["total"]["losses"] == 0
    assert result["total"]["draws"] == 0

    assert result["total"]["avg_turns"] == 8
    assert result["total"]["avg_mulligans"] == 1
    assert result["total"]["avg_mld"] == 1
    assert result["total"]["avg_feeling"] == 4

    assert len(result["versions"]) == 1
    assert result["versions"][0]["list_hash"] == "version-a"
