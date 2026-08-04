from commandlog.logging import get_logger
from commandlog.auth import get_user_key
from commandlog.exceptions import CommandLogError
from commandlog.games.repository import get_user_games
from commandlog.games.statistics import build_summary
from commandlog.responses import error_response, json_response

logger = get_logger(__name__)


def lambda_handler(event, context):
    try:
        user_key = get_user_key(event)

        query_parameters = (event.get("queryStringParameters") or {})
        since = str(query_parameters.get("since") or "").strip()

        games = get_user_games(user_key, since=since or None)

        summary = build_summary(games, user_key=user_key, since=since or None)

        logger.info(
            "Game summary calculated.",
            extra={
                "data": {
                    "user_key": user_key,
                    "game_count": len(games),
                    "since": since or None,
                }
            },
        )

        return json_response(200, summary)

    except CommandLogError as error:
        logger.warning(
            "Game summary rejected.",
            extra={
                "data": {
                    "error": error.error_code
                }
            },
        )

        return error_response(error)

    except Exception as error:
        logger.exception("Failed to calculate game summary.")
        return error_response(error)
    
