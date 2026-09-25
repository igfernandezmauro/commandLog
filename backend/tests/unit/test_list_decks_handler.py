import json
import os

os.environ.setdefault("STATE_TABLE", "test-deck-state")
os.environ.setdefault("AWS_DEFAULT_REGION", "ca-central-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")

from functions.list_decks import lambda_function as handler

class FakeStateTable:
    def query(self, **kwargs):
        return {
            "Items": [
                {
                    "deck_id": "123",
                    "name": "Archidekt Deck",
                    "commander": "Commander A",
                    "featured": None,
                    "changed_at": "2026-09-20T12:00:00Z",
                    "source": "archidekt",
                },
                {
                    "deck_id": "deck_text",
                    "name": "Text Deck",
                    "commander": "Commander B",
                    "featured": None,
                    "changed_at": "2026-09-24T01:00:00Z",
                    "source": "text",
                },
            ]
        }


def test_lists_decks_from_multiple_sources(monkeypatch):
    monkeypatch.setattr(
        handler,
        "get_user_key",
        lambda event: "user#test",
    )

    monkeypatch.setattr(
        handler,
        "tbl_state",
        FakeStateTable(),
    )

    response = handler.lambda_handler({}, None)

    assert response["statusCode"] == 200

    decks = json.loads(response["body"])

    assert {
        deck["deck_id"]
        for deck in decks
    } == {
        "123",
        "deck_text",
    }

    assert {
        deck["source"]
        for deck in decks
    } == {
        "archidekt",
        "text",
    }