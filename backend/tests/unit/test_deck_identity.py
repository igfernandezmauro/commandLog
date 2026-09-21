import pytest

from commandlog.decks.repository import find_user_deck_by_external_id


def test_finds_deck_by_external_id(monkeypatch):
    monkeypatch.setattr(
        "commandlog.decks.repository.get_user_decks",
        lambda user_key: [
            {
                "deck_id": "deck-internal",
                "source": "archidekt",
                "external_id": "12345"
            }
        ]
    )

    deck = find_user_deck_by_external_id("user#test", "archidekt", "12345")

    assert deck["deck_id"] == "deck-internal"

def test_finds_legacy_deck_by_deck_id(monkeypatch):
    monkeypatch.setattr(
        "commandlog.decks.repository.get_user_decks",
        lambda user_key: [
            {
                "deck_id": "12345",
                "source": "archidekt"
            }
        ]
    )

    deck = find_user_deck_by_external_id("user#test", "archidekt", "12345")

    assert deck["deck_id"] == "12345"

def test_does_not_match_other_source(monkeypatch):
    monkeypatch.setattr(
        "commandlog.decks.repository.get_user_decks",
        lambda user_key: [
            {
                "deck_id": "12345",
                "source": "something-else"
            }
        ]
    )

    deck = find_user_deck_by_external_id("user#test", "archidekt", "12345")

    assert deck is None