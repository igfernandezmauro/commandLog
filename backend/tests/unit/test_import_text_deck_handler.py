import json

from functions.import_text_deck import lambda_function as handler


def event(body):
    return {
        "body": json.dumps(body),
        "requestContext": {
            "authorizer": {
                "jwt": {
                    "claims": {
                        "sub": "test-user",
                    }
                }
            }
        },
    }


def test_imports_text_deck(monkeypatch):
    calls = []

    monkeypatch.setattr(
        handler,
        "create_text_deck",
        lambda **kwargs: (
            calls.append(kwargs)
            or {
                "deck_id": "deck-internal",
                "source": "text",
                "name": "Test Deck",
                "commander": "Test Commander",
                "card_count": 100,
                "unique_cards": 75,
                "list_hash": "hash-1",
            }
        ),
    )

    response = handler.lambda_handler(
        event(
            {
                "name": "Test Deck",
                "commanders": [
                    {
                        "oracle_id": "oracle:commander",
                        "name": "Test Commander",
                    }
                ],
                "featured_commander_id": None,
                "decklist": (
                    "1 Test Commander\n"
                    "1 Sol Ring"
                ),
            }
        ),
        None,
    )

    assert response["statusCode"] == 201

    body = json.loads(response["body"])

    assert body["ok"] is True
    assert body["deck_id"] == "deck-internal"

    assert calls == [
        {
            "user_key": "user#test-user",
            "name": "Test Deck",
            "commanders": [
                {
                    "oracle_id": "oracle:commander",
                    "name": "Test Commander",
                }
            ],
            "featured_commander_id": None,
            "decklist": (
                "1 Test Commander\n"
                "1 Sol Ring"
            ),
        }
    ]


def test_rejects_missing_body():
    response = handler.lambda_handler(
        {
            "requestContext": {
                "authorizer": {
                    "jwt": {
                        "claims": {
                            "sub": "test-user",
                        }
                    }
                }
            }
        },
        None,
    )

    assert response["statusCode"] == 400


def test_rejects_invalid_json():
    response = handler.lambda_handler(
        {
            "body": "{not-json}",
            "requestContext": {
                "authorizer": {
                    "jwt": {
                        "claims": {
                            "sub": "test-user",
                        }
                    }
                }
            },
        },
        None,
    )

    assert response["statusCode"] == 400


def test_rejects_non_list_commanders():
    response = handler.lambda_handler(
        event(
            {
                "name": "Test Deck",
                "commanders": "Test Commander",
                "decklist": "1 Test Commander",
            }
        ),
        None,
    )

    assert response["statusCode"] == 400