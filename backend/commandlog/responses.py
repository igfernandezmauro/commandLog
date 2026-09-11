import json
from decimal import Decimal
from typing import Any

from commandlog.exceptions import CommandLogError

DEFAULT_CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "content-type,x-api-key",
    "Access-Control-Allow-Methods": "GET,POST,PUT,OPTIONS"
}

def json_safe(value: Any) -> Any:
    if isinstance(value, list):
        return [json_safe(item) for item in value]

    if isinstance(value, dict):
        return {
            key: json_safe(item) for key, item in value.items()
        }

    if isinstance(value, Decimal):
        return int(value) if value % 1 == 0 else float(value)

    return value

def json_response(status_code: int, body: Any, *, cors:bool = True) -> dict[str, Any]:
    headers = {
        "Content-Type": "application/json",
    }

    if cors:
        headers.update(DEFAULT_CORS_HEADERS)

    return {
        "statusCode": status_code,
        "headers": headers,
        "body": json.dumps(json_safe(body), default=str),
    }

def error_response(error: Exception, *, cors: bool = True) -> dict[str, Any]:
    if isinstance(error, CommandLogError):
        return json_response(
            error.status_code,
            {
                "error": error.error_code,
                "message": error.message,
            },
            cors=cors,
        )

    return json_response(
        500,
        {
            "error": "internal_error",
            "message": "An unexpected error occurred.",
        },
        cors=cors,
    )
