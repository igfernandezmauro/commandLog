import pytest

from commandlog.auth import claims_from_event, get_user_key
from commandlog.exceptions import UnauthorizedError


def test_claims_from_http_api_v2_jwt():
    event = {
        "requestContext": {
            "authorizer": {
                "jwt": {
                    "claims": {
                        "sub": "abc-123",
                        "email": "test@example.com"
                    }
                }
            }
        }
    }

    claims = claims_from_event(event)

    assert claims["sub"] == "abc-123"
    assert claims["email"] == "test@example.com"

def test_get_user_key_uses_sub():
    event = {
        "requestContext": {
            "authorizer": {
                "jwt": {
                    "claims": {
                        "sub": "abc-123",
                    }
                }
            }
        }
    }

    assert get_user_key(event) == "user#abc-123"

def test_get_user_key_rejects_missing_sub():
    event = {
        "requestContext": {
            "authorizer": {
                "jwt": {
                    "claims": {}
                }
            }
        }
    }

    with pytest.raises(UnauthorizedError):
        get_user_key(event)
    