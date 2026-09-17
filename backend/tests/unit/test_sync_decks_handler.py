import json

from functions.sync_decks import lambda_function


def http_event(method="POST"):
    return {
        "requestContext": {
            "http": {
                "method": method
            }
        }
    }

def test_explicit_archidekt_import_uses_authenticated_user(monkeypatch):
    calls = []

    monkeypatch.setattr(
        lambda_function,
        "get_user_key",
        lambda event: "user#alice"
    )

    monkeypatch.setattr(
        lambda_function,
        "get_user_profile",
        lambda user_key: {
            "user_key":user_key,
            "archidekt_username": "alice-archidekt"
        }
    )

    def fake_sync(user_key, username, *, dry_run=False):
        calls.append(
            {
                "user_key": user_key,
                "username": username,
                "dry_run": dry_run
            }
        )

        return {
            "processed": 1,
            "created": 1,
            "updated": 0,
            "unchanged": 0,
            "decks": [
                {
                    "deck_id": "deck-a",
                    "name": "Deck A",
                    "status": "CREATED"
                }
            ]
        }

    monkeypatch.setattr(
        lambda_function,
        "sync_archidekt_user",
        fake_sync
    )

    event = http_event()

    # This should not override the authenticated user
    event["user_key"] = "user#bob"
    event["archidekt_username"] = "bob-archidekt"

    response = lambda_function.lambda_handler(event, None)

    assert response["statusCode"] == 200

    body = json.loads(response["body"])

    assert body["import"]["created"] == 1

    assert calls == [
        {
            "user_key": "user#alice",
            "username": "alice-archidekt",
            "dry_run": False
        }
    ]

def test_explicit_import_rejects_missing_profile(monkeypatch):
    monkeypatch.setattr(
        lambda_function,
        "get_user_key",
        lambda event: "user#alice"
    )

    monkeypatch.setattr(
        lambda_function,
        "get_user_profile",
        lambda user_key: None
    )

    response = lambda_function.lambda_handler(http_event(), None)

    assert response["statusCode"] == 400

    body = json.loads(response["body"])

    assert "profile" in body["message"].lower()

def test_explicit_import_rejects_missing_archidekt_username(monkeypatch):
    monkeypatch.setattr(
        lambda_function,
        "get_user_key",
        lambda event: "user#alice"
    )

    monkeypatch.setattr(
        lambda_function,
        "get_user_profile",
        lambda user_key: {
            "user_key": user_key,
            "archidekt_username": ""
        }
    )

    response = lambda_function.lambda_handler(http_event(), None)

    assert response["statusCode"] == 400

    body = json.loads(response["body"])

    assert "archidekt" in body["message"].lower()

def test_explicit_import_rejects_non_post_method():
    response = lambda_function.lambda_handler(http_event("GET"), None)

    assert response["statusCode"] == 405

def test_profile_save_invocation_still_supported_temporarily(monkeypatch):
    calls = []

    def fake_sync(user_key, username, *, dry_run=False):
        calls.append(
            {
                "user_key": user_key,
                "username": username,
                "dry_run": dry_run
            }
        )

        return {
            "processed": 1,
            "created": 0,
            "updated": 1,
            "unchanged": 0
        }

    monkeypatch.setattr(
        lambda_function,
        "sync_archidekt_user",
        fake_sync
    )

    response = lambda_function.lambda_handler(
        {
            "trigger": "profile_save",
            "user_key": "user#alice",
            "ingestion_source": "archidekt",
            "archidekt_username": "alice-archidekt"
        },
        None
    )

    assert response["processed"] == 1

    assert calls == [
        {
            "user_key": "user#alice",
            "username": "alice-archidekt",
            "dry_run": False
        }
    ]