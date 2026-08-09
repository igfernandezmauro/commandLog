from commandlog.logging import get_logger
from commandlog.auth import get_user_key
from commandlog.decks.diff import build_deck_diff
from commandlog.exceptions import CommandLogError, ValidationError
from commandlog.responses import error_response, json_response


logger = get_logger(__name__)


def parse_boolean(value) -> bool:
    return str(value or "").lower() in {"true", "1", "yes", "on"}

def lambda_handler(event, context):
    try:
        user_key = get_user_key(event)

        path_parameters = event.get("pathParameters") or {}
        deck_id = str(path_parameters.get("deck_id") or "").strip()

        if not deck_id:
            raise ValidationError("Missing deck_id in path.")

        query_parameters = event.get("queryStringParameters") or {}

        result = build_deck_diff(
            user_key=user_key,
            deck_id=deck_id,
            base_date=query_parameters.get("baseDate"),
            compare_date=query_parameters.get("compareDate"),
            base_empty=parse_boolean(query_parameters.get("baseEmpty"))
        )

        logger.info(
            "Deck diff generated.",
            extra={
                "data": {
                    "user_key": user_key,
                    "deck_id": deck_id,
                    "cache_hit": result.get("cache_hit"),
                    "added": result["counts"]["added"],
                    "removed": result["counts"]["removed"]
                }
            }
        )

        return json_response(200, result)

    except CommandLogError as error:
        logger.warning(
            "Deck diff request rejected.",
            extra={
                "data": {
                    "error": error.error_code
                }
            }
        )
        return error_response(error)

    except Exception as error:
        logger.exception("Failed to generate deck diff.")
        return error_response(error)
