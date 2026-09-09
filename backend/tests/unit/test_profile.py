import json

from functions.profile import lambda_function


def jwt_event(*, method, body=None):
    event = {
        "version": "2.0",
        "requestContext": {
            "authorizer": {
                "jwt": {
                    "claims": {
                        "sub": "test-user-123",
                        "email": "test@example.com",
                    }
                }
            },
            "http": {
                "method": method,
            }
        }
    }
    if body is not None:
        event["body"] = json.dumps(body)

    return event

def response_body(response):
    return json.loads(response["body"])

def test_get_empty_profile(monkeypatch):
    monkeypatch.setattr(
        lambda_function,
        "get_user_profile",
        lambda user_key: None,
    )

    response = lambda_function.lambda_handler(
        jwt_event(method="GET"),
        None,
    )

    assert response["statusCode"] == 200

    profile = response_body(response)["profile"]

    assert profile["user_key"] == "user#test-user-123"
    assert profile["archidekt_username"] == ""
    assert profile["ingestion_enabled"] is False
    assert profile["ingestion_source"] == ""
    assert profile["created_at"] is None
    assert profile["updated_at"] is None

def test_put_rejects_unsupported_source():
    response = lambda_function.lambda_handler(
        jwt_event(
            method="PUT",
            body={
                "source": "moxfield",
                "ingestion_enabled": False,
            },
        ),
        None,
    )

    assert response["statusCode"] == 400

def test_put_requires_username_when_ingestion_enabled():
    response = lambda_function.lambda_handler(
        jwt_event(
            method="PUT",
            body={
                "source": "archidekt",
                "archidekt_username": "",
                "ingestion_enabled": True,
            },
        ),
        None,
    )

    assert response["statusCode"] == 400

def test_put_saves_profile_without_starting_ingestion(monkeypatch):
    saved = {}

    monkeypatch.setattr(
        lambda_function,
        "get_user_profile",
        lambda user_key: None,
    )

    def fake_save_user_profile(item):
        saved.update(item)

    monkeypatch.setattr(
        lambda_function,
        "save_user_profile",
        fake_save_user_profile,
    )

    def fail_if_invoked(**kwargs):
        raise AssertionError(
            "Ingestion must not start when ingestion_enabled=false"
        )

    monkeypatch.setattr(
        lambda_function,
        "invoke_ingestion",
        fail_if_invoked,
    )

    response = lambda_function.lambda_handler(
        jwt_event(
            method="PUT",
            body={
                "source": "archidekt",
                "archidekt_username": "commandlog-dev",
                "ingestion_enabled": False,
            },
        ),
        None,
    )

    assert response["statusCode"] == 200

    assert saved["user_key"] == "user#test-user-123"
    assert saved["archidekt_username"] == "commandlog-dev"
    assert saved["ingestion_enabled"] is False
    assert saved["ingestion_enabled_key"] == "0"
    assert saved["ingestion_source"] == "archidekt"

    body = response_body(response)

    assert body["ingest"]["started"] is False
    assert body["ingest"]["error"] is None
