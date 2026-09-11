from commandlog.logging import get_logger
from commandlog.auth import get_user_key
from commandlog.decks.recommendations import build_recommendations
from commandlog.decks.repository import get_active_source, get_user_decks
from commandlog.exceptions import CommandLogError, ValidationError
from commandlog.games.repository import get_user_games
from commandlog.responses import error_response, json_response


logger = get_logger(__name__)


def parse_int_parameter(value, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default

    return max(minimum, min(parsed, maximum))

def parse_float_parameter(value, *, default: float) -> float:
    if value is None or value == "":
        return default

    try:
        return float(value)
    except (TypeError, ValueError):
        raise ValidationError("Recommendation parameters must be numeric.")

def lambda_handler(event, context):
    try:
        user_key = get_user_key(event)
        query_parameters = (event.get("queryStringParameters") or {})

        count = parse_int_parameter(query_parameters.get("count"), default=3, minimum=1, maximum=10)

        alpha = parse_float_parameter(query_parameters.get("alpha"), default=0.7)
        beta = parse_float_parameter(query_parameters.get("beta"), default=0.8)
        gamma = parse_float_parameter(query_parameters.get("gamma"), default=1.5)

        active_source = get_active_source(user_key)

        decks = [deck for deck in get_user_decks(user_key) if deck.get("source") == active_source]

        games = get_user_games(user_key)

        recommendations = build_recommendations(decks, games, count=count, alpha=alpha, beta=beta, gamma=gamma)

        logger.info(
            "Deck recommendations generated.",
            extra={
                "data": {
                    "user_key": user_key,
                    "source": active_source,
                    "candidate_count": len(decks),
                    "picked_count": len(recommendations["picked"])
                }
            },
        )

        return json_response(200, recommendations)

    except CommandLogError as error:
        logger.warning(
            "Deck recommendation rejected.",
            extra={
                "data": {
                    "error": error.error_code
                }
            }
        )
        return error_response(error)

    except Exception as error:
        logger.exception("Failed to generate deck recommendations.")
        return error_response(error)
