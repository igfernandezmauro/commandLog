from commandlog.logging import get_logger
from commandlog.auth import get_user_key
from commandlog.exceptions import (
    CommandLogError,
    ValidationError,
)
from commandlog.games.repository import get_user_games
from commandlog.games.statistics import build_version_stats
from commandlog.responses import error_response, json_response


logger = get_logger(__name__)


def lambda_handler(event, context):
    try:
        user_key = get_user_key(event)

        query_parameters = (event.get("queryStringParameters") or {})
        deck_id = str(query_parameters.get("deck_id") or "").strip()

        if not deck_id:
            raise ValidationError("Missing required query parameter: deck_id.")

        games = get_user_games(user_key)

        statistics = build_version_stats(games, user_key=user_key, deck_id=deck_id)

        logger.info(
            "Deck version statistics calculated.",
            extra={
                "data": {
                    "user_key": user_key,
                    "deck_id": deck_id,
                    "game_count": statistics["total"]["games"],
                }
            },
        )

        return json_response(200, statistics)

    except CommandLogError as error:
        logger.warning(
            "Deck version statistics rejected.",
            extra={
                "data": {
                    "error": error.error_code
                }
            },
        )

        return error_response(error)

    except Exception as error:
        logger.exception("Failed to calculate deck version statistics.")

        return error_response(error)
    