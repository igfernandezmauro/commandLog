import os
import urllib.parse

from commandlog.logging import get_logger
from commandlog.scryfall.bulk import iter_oracle_cards
from commandlog.scryfall.cards import load_cards


logger = get_logger(__name__)

DEFAULT_KEY = "scryfall/oracle_cards/latest.jsonl.gz"


def source_from_event(event):
    try:
        record = (event.get("Records") or [])[0]

        if record.get("eventSource") != "aws:s3":
            return None, None

        bucket = record["s3"]["bucket"]["name"]
        key = urllib.parse.unquote_plus(record["s3"]["object"]["key"])

        return bucket,key

    except (KeyError, IndexError, TypeError, AttributeError):
        return None, None

def lambda_handler(event, context):
    bucket, key = source_from_event(event or {})

    bucket = (bucket or os.environ["RAW_BUCKET"])

    key = (key or os.getenv("S3_KEY", DEFAULT_KEY))

    batch_size = int(os.getenv("WRITE_BATCH_SIZE", "2000"))

    result = load_cards(iter_oracle_cards(bucket, key), write_batch_size=batch_size)

    logger.info(
        "Scryfall Oracle Cards loaded.",
        extra={
            "data": {
                **result,
                "source_bucket": bucket,
                "source_key": key
            }
        }
    )

    return {
        "status": "ok",
        **result,
        "source_bucket": bucket,
        "source_key": key
    }