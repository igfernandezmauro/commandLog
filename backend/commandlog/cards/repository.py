from typing import Any

from commandlog.aws import dynamodb_resource
from commandlog.config import required_env


def oracle_id_from_card_id(card_id: str | None) -> str | None:
    if not card_id:
        return None

    if not card_id.startswith("oracle:"):
        return None

    return card_id.split("oracle:", 1)[1]

def chunks(items: list[str], size: int):
    for index in range(0, len(items), size):
        yield items[index:index + size]

def get_card_images(card_ids: set[str]) -> dict[str, dict[str, Any]]:
    table_name = required_env("CARDS_DIM_TABLE")

    oracle_ids = [
        oracle_id
        for card_id in card_ids
        if (oracle_id := oracle_id_from_card_id(card_id))
    ]

    if not oracle_ids:
        return {}

    client = dynamodb_resource().meta.client
    results: dict[str, dict[str, Any]] = {}

    for batch in chunks(oracle_ids, 100):
        request_items = {
            table_name: {
                "Keys": [
                    {"oracle_id": oracle_id}
                    for oracle_id in batch
                ],
                "ProjectionExpression": (
                    "oracle_id, image_small, image_normal, #name"
                ),
                "ExpressionAttributeNames": {
                    "#name": "name",
                },
            }
        }

        while request_items:
            response = client.batch_get_item(
                RequestItems=request_items
            )

            for item in (response.get("Responses", {}).get(table_name, [])):
                results[f"oracle:{item['oracle_id']}"] = item

            request_items = response.get("UnprocessedKeys", {})

            if not request_items.get(table_name, {}).get("Keys"):
                break

    return results
