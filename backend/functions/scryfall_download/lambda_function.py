from commandlog.logging import get_logger
from commandlog.scryfall.bulk import download_oracle_cards


logger = get_logger(__name__)


def lambda_handler(event, context):
    result = download_oracle_cards()

    logger.info(
        "Scryfall Oracle Cards downloaded.",
        extra={
            "data": {
                "historical_key": result["historical_key"],
                "latest_key": result["latest_key"]
            }
        }
    )

    return {
        "status": "ok",
        **result
    }