import base64
import json
import os
from datetime import datetime, timezone
from typing import Any

import boto3

from commandlog.logging import get_logger
from commandlog.auth import get_user_key
from commandlog.exceptions import CommandLogError, ValidationError
from commandlog.responses import error_response, json_response
from commandlog.users.repository import get_user_profile, save_user_profile


logger = get_logger(__name__)

lambda_client = boto3.client(
    "lambda",
    region_name=os.getenv("AWS_REGION", "ca-central-1"),
    endpoint_url=os.getenv("AWS_ENDPOINT_URL")
)

def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

def parse_body(event: dict[str, Any]) -> dict[str, Any]:
    body = event.get("body")

    if not body:
        return {}

    if event.get("isBase64Encoded"):
        body = base64.b64decode(body).decode("utf-8")

    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as error:
        raise ValidationError("Request body must contain valid JSON.")

    if not isinstance(parsed, dict):
        raise ValidationError("Request body must be a JSON object.")

    return parsed

def get_method(event: dict[str, Any]) -> str:
    return(
        ((event.get("requestContext") or {})
         .get("http") or {})
         .get("method")
         or event.get("httpMethod")
         or ""
    ).upper()

def build_profile(user_key: str, item: dict[str, Any] | None) -> dict[str, Any]:
    item = item or {}

    return {
        "user_key": user_key,
        "archidekt_username": item.get("archidekt_username") or "",
        "ingestion_enabled": bool(item.get("ingestion_enabled", False)),
        "ingestion_source": item.get("ingestion_source") or "",
        "updated_at": item.get("updated_at"),
        "created_at": item.get("created_at")
    }

def should_invoke_ingestion() -> bool:
    return (os.getenv("INVOKE_INGEST_ON_SAVE", "true").strip().lower() == "true")

def invoke_ingestion(*, user_key: str, archidekt_username: str) -> tuple[bool, str | None]:
    function_name = os.getenv("INGEST_LAMBDA_NAME")

    if not function_name:
        return False, None

    try:
        lambda_client.invoke(
            FunctionName=function_name,
            InvocationType="Event",
            Payload=json.dumps(
                {
                    "trigger": "profile_save",
                    "user_key": user_key,
                    "ingestion_source": "archidekt",
                    "archidekt_username": archidekt_username
                }
            ).encode("utf-8")
        )

        return True, None

    except Exception as error:
        logger.exception("Failed to start ingestion from profile save.")

        return False, str(error)

def lambda_handler(event, context):
    try:
        method = get_method(event)

        if method == "OPTIONS":
            return json_response(200, {})

        user_key = get_user_key(event)

        if method == "GET":
            item = get_user_profile(user_key)

            return json_response(
                200,
                {"profile": build_profile(user_key, item)}
            )

        if method == "PUT":
            data = parse_body(event)

            username = str(data.get("archidekt_username") or "").strip()

            ingestion_enabled = bool(data.get("ingestion_enabled", False))

            source = str(data.get("source") or "").strip()

            if source not in {"", "archidekt"}:
                raise ValidationError("Unsupported ingestion source.")

            if ingestion_enabled and source != "archidekt":
                raise ValidationError("Enabled ingestion requires source=archidekt.")

            if ingestion_enabled and not username:
                raise ValidationError("archidekt_username is required when ingestion is enabled.")

            existing = (get_user_profile(user_key) or {})

            timestamp = now_iso()

            item = {
                "user_key": user_key,
                "archidekt_username": username,
                "ingestion_enabled": ingestion_enabled,
                "ingestion_enabled_key": ("1" if ingestion_enabled else "0"),
                "ingestion_source": source,
                "updated_at": timestamp,
                "created_at": (existing.get("created_at") or timestamp)
            }

            save_user_profile(item)

            started = False
            ingest_error = None

            if (should_invoke_ingestion() and ingestion_enabled and source == "archidekt" and username):
                started, ingest_error = invoke_ingestion(user_key=user_key, archidekt_username=username)

            logger.info(
                "User profile saved.",
                extra={
                    "data": {
                        "user_key": user_key,
                        "ingestion_enabled": ingestion_enabled,
                        "ingestion_source": source,
                        "ingestion_started": started
                    }
                }
            )

            return json_response(
                200,
                {
                    "profile": item,
                    "ingest": {
                        "started": started,
                        "error": ingest_error
                    }
                }
            )

        return json_response(
            405,
            {
                "error": "method_not_allowed",
                "message": f"Method not allowed: {method}"
            }
        )

    except CommandLogError as error:
        logger.warning(
            "Profile request rejected.",
            extra={
                "data": {
                    "error": error.error_code
                }
            }
        )
        return error_response(error)

    except Exception as error:
        logger.exception("Failed to process profile request.")
        return error_response(error)