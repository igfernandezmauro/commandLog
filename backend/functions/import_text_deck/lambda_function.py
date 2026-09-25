import json

from commandlog.auth import get_user_key
from commandlog.decks.text_import import create_text_deck
from commandlog.exceptions import CommandLogError, ValidationError
from commandlog.logging import get_logger
from commandlog.responses import error_response, json_response


logger = get_logger(__name__)


def parse_body(event: dict) -> dict:
    raw_body = event.get("body")

    if not raw_body:
        raise ValidationError("Request body is required.")

    try:
        body = json.loads(raw_body)
    except (TypeError, json.JSONDecodeError) as error:
        raise ValidationError("Request body must be valid JSON.") from error

    if not isinstance(body, dict):
        raise ValidationError("Request body must be a JSON object.")

    return body

def lambda_handler(event, context):
    try:
        user_key = get_user_key(event)
        body = parse_body(event)

        name = str(body.get("name") or "").strip()
        decklist = str(body.get("decklist") or "")

        commanders = body.get("commanders") or []
        featured_commander_id = body.get("featured_commander_id")

        if not isinstance(commanders, list):
            raise ValidationError("Commanders must be a list.")

        if featured_commander_id is not None:
            featured_commander_id = str(featured_commander_id).strip() or None

        result = create_text_deck(user_key=user_key, name=name, commanders=commanders, featured_commander_id=featured_commander_id, decklist=decklist)

        logger.info(
            "Text deck imported.",
            extra={
                "data": {
                    "user_key": user_key,
                    "deck_id": result["deck_id"],
                    "card_count": result["card_count"],
                    "unique_cards": result["unique_cards"]
                }
            }
        )

        return json_response(
            201,
            {
                "ok": True,
                **result
            }
        )
    
    except CommandLogError as error:
        logger.warning(
            "Text deck import rejected.",\
            extra={
                "data": {
                    "error": error.error_code
                }
            }
        )

        return error_response(error)

    except Exception as error:
        logger.exception("Text deck import failed.")
        return error_response(error)