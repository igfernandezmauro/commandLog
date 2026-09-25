import pytest

from commandlog.decks.text_import import parse_decklist, resolve_decklist, create_text_deck, build_list_hash, resolve_commanders, build_main
from commandlog.exceptions import ValidationError
from commandlog.decks.snapshots import normalize_snapshot


def test_parses_basic_decklist():
    result = parse_decklist(
        """
        1 Sol Ring
        1 Arcane Signet
        12 Island
        """
    )

    assert result == [
        {"name": "Sol Ring", "quantity": 1},
        {"name": "Arcane Signet", "quantity": 1},
        {"name": "Island", "quantity": 12}
    ]

def test_accepts_x_quantity():
    result = parse_decklist("2x Island")

    assert result == [
        {"name": "Island", "quantity": 2}
    ]

def test_strips_printing_information():
    result = parse_decklist("1 Swords to Plowshares (CMM) 68")

    assert result == [
        {"name": "Swords to Plowshares", "quantity": 1}
    ]

def test_combines_duplicate_cards_case_insensitively():
    result = parse_decklist(
        """
        1 Sol Ring
        2 sol ring
        """
    )

    assert result == [
        {"name": "Sol Ring", "quantity": 3}
    ]

def test_rejects_invalid_lines():
    with pytest.raises(
        ValidationError,
        match=r"Invalid decklist line\(s\): 2"
    ):
        parse_decklist(
            "1 Sol Ring\n"
            "this is invalid"
        )

def test_reject_empty_list():
    with pytest.raises(
        ValidationError,
        match="Decklist is required."
    ):
        parse_decklist("")

def test_resolves_cards_to_oracle_ids(monkeypatch):
    monkeypatch.setattr(
        "commandlog.decks.text_import.resolve_card_names",
        lambda names: (
            {
                "sol ring": {
                    "oracle_id": "oracle-id-1",
                    "name": "Sol Ring",
                    "image_art_crop": "https://example.com/sol-ring-art.jpg",
                    "image_normal": "https://example.com/sol-ring.jpg",
                },
                "island": {
                    "oracle_id": "oracle-id-2",
                    "name": "Island",
                    "image_art_crop": "https://example.com/island-art.jpg",
                    "image_normal": "https://example.com/island.jpg",
                },
            },
            [],
        ),
    )

    result = resolve_decklist(
        [
            {
                "name": "Sol Ring",
                "quantity": 1,
            },
            {
                "name": "Island",
                "quantity": 12,
            },
        ]
    )

    assert result == [
        {
            "card_id": "oracle:oracle-id-1",
            "oracle_id": "oracle-id-1",
            "name": "Sol Ring",
            "quantity": 1,
            "image_art_crop": "https://example.com/sol-ring-art.jpg",
            "image_normal": "https://example.com/sol-ring.jpg",
        },
        {
            "card_id": "oracle:oracle-id-2",
            "oracle_id": "oracle-id-2",
            "name": "Island",
            "quantity": 12,
            "image_art_crop": "https://example.com/island-art.jpg",
            "image_normal": "https://example.com/island.jpg",
        },
    ]

def test_rejects_unknown_cards(monkeypatch):
    monkeypatch.setattr(
            "commandlog.decks.text_import.resolve_card_names",
            lambda names: (
                {
                    "sol ring": {
                        "oracle_id": "oracle-id-1",
                        "name": "Sol Ring"
                    }
                },
                ["Sol Rign"],
            )
        )

    with pytest.raises(
        ValidationError,
        match="Unknown card"
    ):
        resolve_decklist(
            [
                {
                    "name": "Sol Ring",
                    "quantity": 1
                },
                {
                    "name": "Sol Rign",
                    "quantity": 1
                }
            ]
        )

def test_creates_commandlog_text_deck(monkeypatch):
    monkeypatch.setattr(
        "commandlog.decks.text_import.new_deck_id",
        lambda: "deck-internal",
    )

    monkeypatch.setattr(
        "commandlog.decks.text_import.resolve_decklist",
        lambda parsed: [
            {
                "card_id": "oracle:commander",
                "oracle_id": "commander",
                "name": "Test Commander",
                "quantity": 1,
                "image_art_crop": "https://example.com/commander-art.jpg",
                "image_normal": "https://example.com/commander.jpg",
            },
            {
                "card_id": "oracle:island",
                "oracle_id": "island",
                "name": "Island",
                "quantity": 12,
                "image_art_crop": None,
                "image_normal": None,
            },
        ],
    )

    snapshots = []
    changes = []
    updates = []

    monkeypatch.setattr(
        "commandlog.decks.text_import.save_snapshot",
        lambda key, snapshot: snapshots.append((key, snapshot)),
    )

    monkeypatch.setattr(
        "commandlog.decks.text_import.save_change",
        lambda item: changes.append(item),
    )

    monkeypatch.setattr(
        "commandlog.decks.text_import.update_deck_state",
        lambda **kwargs: updates.append(kwargs),
    )

    result = create_text_deck(
        user_key="user#test",
        name="Test Deck",
        commanders=[
            {
                "oracle_id": "oracle:commander",
                "name": "Test Commander"
            }
        ],
        featured_commander_id=None,
        decklist="1 Test Commander\n12 Island",
        run_timestamp="2026-09-23T20:00:00Z",
    )

    assert result["deck_id"] == "deck-internal"
    assert result["source"] == "text"
    assert result["card_count"] == 13
    assert result["unique_cards"] == 2

    assert len(snapshots) == 1
    assert snapshots[0][0] == (
        "text/decks/deck-internal/"
        "snapshot_ts=20260923T200000Z.json"
    )

    assert changes[0]["deck_id"] == "deck-internal"
    assert changes[0]["change_type"] == "CREATED"
    assert changes[0]["source"] == "text"

    assert updates[0]["deck_id"] == "deck-internal"
    assert updates[0]["source"] == "text"
    assert updates[0]["external_id"] is None
    assert updates[0]["main"] == {
        "oracle:commander": 1,
        "oracle:island": 12,
    }
    assert updates[0]["commander"] == "Test Commander"
    assert updates[0]["featured"] == "https://example.com/commander-art.jpg"

def test_list_hash_is_independent_of_card_order():
    first = build_list_hash(
        {
            "oracle:a": 1,
            "oracle:b": 2,
        }
    )

    second = build_list_hash(
        {
            "oracle:b": 2,
            "oracle:a": 1,
        }
    )

    assert first == second

def test_normalizes_text_snapshot():
    snapshot = {
        "schema_version": 1,
        "source": "text",
        "cards": {
            "oracle:a": {
                "name": "Sol Ring",
                "quantity": 1,
            },
            "oracle:b": {
                "name": "Island",
                "quantity": 12,
            },
        },
    }

    assert normalize_snapshot(snapshot, "text") == {
        "oracle:a": {
            "name": "Sol Ring",
            "qty": 1,
        },
        "oracle:b": {
            "name": "Island",
            "qty": 12,
        },
    }

def test_single_commander_is_automatically_featured():
    commanders, commander_text, featured = resolve_commanders(
        [
            {
                "oracle_id": "oracle:amalia",
                "name": "Amalia Benavides Aguirre",
            }
        ],
        None,
        [
            {
                "card_id": "oracle:amalia",
                "oracle_id": "amalia",
                "name": "Amalia Benavides Aguirre",
                "quantity": 1,
                "image_art_crop": "https://example.com/amalia-art.jpg",
                "image_normal": "https://example.com/amalia.jpg",
            }
        ],
    )

    assert commander_text == "Amalia Benavides Aguirre"
    assert featured == "https://example.com/amalia-art.jpg"

def test_resolves_card_aliases_to_same_oracle_card(monkeypatch):
    canonical_card = {
        "oracle_id": "aang-oracle-id",
        "name": "Avatar Aang // Aang, Master of Elements",
        "image_art_crop": None,
        "image_normal": None,
    }

    monkeypatch.setattr(
        "commandlog.decks.text_import.resolve_card_names",
        lambda names: (
            {
                "avatar aang": canonical_card,
                "avatar aang // aang, master of elements": canonical_card,
            },
            [],
        ),
    )

    parsed = parse_decklist(
        """
        1 Avatar Aang
        1 Avatar Aang // Aang, Master of Elements
        """
    )

    resolved = resolve_decklist(parsed)

    assert resolved == [
        {
            "card_id": "oracle:aang-oracle-id",
            "oracle_id": "aang-oracle-id",
            "name": "Avatar Aang // Aang, Master of Elements",
            "quantity": 1,
            "image_art_crop": None,
            "image_normal": None,
        },
        {
            "card_id": "oracle:aang-oracle-id",
            "oracle_id": "aang-oracle-id",
            "name": "Avatar Aang // Aang, Master of Elements",
            "quantity": 1,
            "image_art_crop": None,
            "image_normal": None,
        },
    ]

    assert build_main(resolved) == {
        "oracle:aang-oracle-id": 2
    }