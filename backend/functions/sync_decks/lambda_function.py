import os

from commandlog.auth import get_user_key
from commandlog.exceptions import CommandLogError, ValidationError
from commandlog.ingestion.sync import sync_archidekt_user
from commandlog.logging import get_logger
from commandlog.responses import error_response, json_response
from commandlog.users.repository import get_user_profile


logger = get_logger(__name__)


def is_dry_run() -> bool:
    return os.getenv("DRY_RUN", "false").strip().lower == "true"

def get_method(event: dict) -> str:
    return(
        ((event.get("requestContext") or {}).get("http") or {}).get("method")
        or event.get("httpMethod")
        or ""
    ).upper()

def lambda_handler(event, context):
    try:
        event = event or {}
        dry_run = is_dry_run()

        method = get_method(event)

        if method:
            if method == "OPTIONS":
                return json_response(200, {})
            if method != "POST":
                return json_response(
                    405,
                    {
                        "error": "method_not_allowed",
                        "message": f"Method not allowed: {method}"
                    }
                )

            user_key = get_user_key(event)
            profile = get_user_profile(user_key)

            if not profile:
                raise ValidationError("User profile is not configured.")

            username = str(profile.get("archidekt_username") or "").strip()

            if not username:
                raise ValidationError("Add an Archidekt username to your profile before importing decks.")

            result = sync_archidekt_user(user_key, username, dry_run=dry_run)

            return json_response(
                200,
                {"import": result}
            )

        if event.get("trigger") == "profile_save":
            user_key = event.get("user_key")
            source = event.get("ingestion_source")
            username = event.get("archidekt_username")

            if user_key and source == "archidekt" and username:
                return sync_archidekt_user(
                    str(user_key),
                    str(username),
                    dry_run=dry_run
                )

        raise ValidationError("Unsupported deck import invocation.")

    except CommandLogError as error:
        logger.warning(
            "Archidekt import rejected.",
            extra={
                "data": {
                    "error": error.error_code
                }
            }
        )
        return error_response(error)

    except Exception as error:
        logger.exception("Archidekt import failed.")
        return error_response(error)