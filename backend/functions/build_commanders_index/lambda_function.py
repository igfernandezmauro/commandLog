from commandlog.logging import get_logger
from commandlog.scryfall.commanders import build_commanders_index
from commandlog.responses import json_response


logger = get_logger(__name__)


def lambda_handler(event, context):
    result = build_commanders_index()

    logger.info(
        "Commander index built.",
        extra={
            "data": {
                "count": result["count"],
                "key": result["key"]
            }
        }
    )

    return json_response(
        200,
        {
            "ok": True,
            **result
        }
    )