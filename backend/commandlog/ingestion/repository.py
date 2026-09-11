import json
from typing import Any

from commandlog.aws import s3_client
from commandlog.config import required_env
from commandlog.tables import deck_change_log_table, deck_state_table


def get_current_deck(user_key: str, deck_id: str) -> dict[str, Any] | None:
    response = deck_state_table().get_item(
        Key={
            "user_key": user_key,
            "deck_id": deck_id
        },
        ConsistentRead=True
    )

    return response.get("Item")

def save_snapshot(key: str, snapshot: dict[str, Any]) -> None:
    s3_client().put_object(
        Bucket=required_env("BUCKET_NAME"),
        Key=key,
        Body=json.dumps(
            snapshot,
            ensure_ascii=False
        ).encode("utf-8"),
        ContentType="application/json"
    )

def save_change(item: dict[str, Any]) -> None:
    deck_change_log_table().put_item(
        Item=item
    )

def update_deck_state(
    *,
    user_key: str,
    deck_id: str,
    source: str,
    name: str | None,
    commander: str,
    featured: str | None,
    changed_at: str | None,
    created_at: str | None,
    run_ts: str,
    list_hash: str,
    main: dict[str, int],
    raw_key: str
) -> None:
    deck_state_table().update_item(
        Key={
            "user_key": user_key,
            "deck_id": deck_id
        },
        UpdateExpression="""
            SET #source = :source,
                #name = :name,
                commander = :commander,
                featured = :featured,
                changed_at = :changed_at,
                created_at = :created_at,
                last_seen_at = :last_seen_at,
                list_hash = :list_hash,
                #main = :main,
                raw_s3_key = :raw_s3_key
        """,
        ExpressionAttributeNames={
            "#source": "source",
            "#name": "name",
            "#main": "main"
        },
        ExpressionAttributeValues={
            ":source": source,
            ":name": name,
            ":commander": commander,
            ":featured": featured,
            ":changed_at": changed_at,
            ":created_at": created_at,
            ":last_seen_at": run_ts,
            ":list_hash": list_hash,
            ":main": main,
            ":raw_s3_key": raw_key
        }
    )