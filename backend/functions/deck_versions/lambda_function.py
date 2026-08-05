from commandlog.logging import get_logger
from commandlog.auth import get_user_key
from commandlog.decks.history import build_deck_history
from commandlog.exceptions import CommandLogError, ValidationError
from commandlog.responses import error_response, json_response


logger = get_logger(__name__)


def lambda_handler(event, context):
    try:
        user_key = get_user_key(event)

        path_parameters = event.get("pathParameters") or {}
        deck_id = str(path_parameters.get("deck_id") or "").strip()

        if not deck_id:
            raise ValidationError("Missing deck_id in path.")

        history = build_deck_history(user_key, deck_id)

        logger.info(
            "Deck history listed.",
            extra={
                "data": {
                    "user_key": user_key,
                    "deck_id": deck_id,
                    "version_count": len(history)
                }
            },
        )

        return json_response(200, history)

    except CommandLogError as error:
        logger.warning(
            "Deck history request rejected.",
            extra={
                "data": {
                    "error": error.error_code
                }
            },
        )

        return error_response(error)

    except Exception as error:
        logger.exception("Failed to list deck history")
        return error_response(error)