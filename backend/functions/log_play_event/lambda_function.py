import json
from datetime import datetime, timezone
from typing import Any

from botocore.exceptions import ClientError

from commandlog.logging import get_logger
from commandlog.auth import get_user_key
from commandlog.exceptions import (
    CommandLogError,
    NotFoundError,
    ValidationError
)
from commandlog.responses import error_response, json_response
from commandlog.tables import (
    deck_state_table,
    play_events_table
)


logger = get_logger(__name__)

tbl_events = play_events_table()
tbl_state = deck_state_table()

VALID_RESULTS = {"WIN", "LOSS", "DRAW"}
MAX_GAME_DURATION_SECONDS = 60 * 60 * 12

def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

def parse_iso_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))

def normalize_iso_timestamp(value: str) -> str:
    parsed = parse_iso_timestamp(value)

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return (
        parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    )

def safe_duration_seconds(started_at: str | None, ended_at: str | None) -> int | None:
    if not started_at or not ended_at:
        return None
    
    try:
        start = parse_iso_timestamp(started_at)
        end = parse_iso_timestamp(ended_at)

        seconds = int((end - start).total_seconds())
        
        if seconds < 0:
            return None

        if seconds > MAX_GAME_DURATION_SECONDS:
            return None
        
        return seconds
    
    except (TypeError, ValueError):
        return None

def parse_body(event: dict[str, Any]) -> dict[str, Any]:
    raw_body = event.get("body") or "{}"

    if isinstance(raw_body, dict):
        return raw_body

    try:
        body = json.loads(raw_body)
    except json.JSONDecodeError as error:
        raise ValidationError("Request body must contains valid JSON") from error

    if not isinstance(body, dict):
        raise ValidationError("Request body must be a JSON object")

    return body

def validate_request(body: dict[str, Any]) -> tuple[str, str]:
    deck_id = str(body.get("deck_id") or "").strip()
    result = str(body.get("result") or "").strip().upper()

    if not deck_id:
        raise ValidationError("deck_id is required.")

    if result not in VALID_RESULTS:
        raise ValidationError("result must be WIN, LOSS, or DRAW.")

    return deck_id, result

def get_deck_state(user_key: str, deck_id: str) -> dict[str, Any]:
    response = tbl_state.get_item(
        Key={
            "user_key": user_key,
            "deck_id": deck_id,
        },
        ConsistentRead=True,
    )

    state = response.get("Item")

    if not state:
        raise NotFoundError("Deck not found.")

    return state

def update_last_played(user_key: str, deck_id: str, played_at: str) -> None:
    try:
        tbl_state.update_item(
            Key={
                "user_key": user_key,
                "deck_id": deck_id,
            },
            UpdateExpression="SET last_played_at = :played_at",
            ConditionExpression=(
                "attribute_not_exists(last_played_at) OR last_played_at < :played_at"
            ),
            ExpressionAttributeValues={
                ":played_at": played_at,
            },
        )

    except ClientError as error:
        error_code = error.response["Error"]["Code"]

        if error_code == "ConditionalCheckFailedException":
            logger.info(
                "Deck last played timestamp was not updated.",
                extra={
                    "data": {
                        "user_key": user_key,
                        "deck_id": deck_id,
                        "played_at": played_at,
                    }
                },
            )
            return

        raise

def build_play_event(*, user_key: str, deck_id: str, result: str, body: dict[str, Any], state: dict[str, Any], played_at: str) -> dict[str, Any]:
    opponents = body.get("opponents_commanders") or []
    opponents_ids = body.get("opponents_commanders_ids") or []
    metrics = body.get("metrics") or {}

    if not isinstance(opponents, list):
        raise ValidationError("opponents_commanders must be a list.")

    if not isinstance(opponents_ids, list):
        raise ValidationError("opponents_commanders_ids must be a list.")

    if not isinstance(metrics, dict):
        metrics = {}

    started_at = body.get("started_at")
    normalized_started_at = None

    if started_at:
        try:
            normalized_started_at = normalize_iso_timestamp(str(started_at))
        except ValueError as error:
            raise ValidationError("started_at must be a valid ISO timestamp.") from error

    duration_seconds = safe_duration_seconds(normalized_started_at, played_at)

    item: dict[str, Any] = {
        "user_key": user_key,
        "played_at": played_at,
        "deck_id": deck_id,
        "deck_name": state.get("name"),
        "commander": state.get("commander"),
        "result": result,
        "opponents_commanders": opponents,
        "opponents_commanders_ids": opponents_ids,
        "asof_list_hash": state.get("list_hash"),
        "turn_order": body.get("turn_order", 0),
        "mulligans": body.get("mulligans", 0),
        "store": body.get("store", ""),
        "notes": body.get("notes", ""),
        "metrics": metrics
    }

    if normalized_started_at:
        item["started_at"] = normalized_started_at

    if duration_seconds is not None:
        item["duration_seconds"] = duration_seconds

    return item

def lambda_handler(event, context):
    try:
        user_key = get_user_key(event)
        body = parse_body(event)

        deck_id, result = validate_request(body)
        state = get_deck_state(user_key, deck_id)
        played_at = now_iso()

        item = build_play_event(
            user_key=user_key,
            deck_id=deck_id,
            result=result,
            body=body,
            state=state,
            played_at=played_at,
        )

        tbl_events.put_item(Item=item)

        update_last_played(user_key, deck_id, played_at,)

        logger.info(
            "Game recorded.",
            extra={
                "data": {
                    "user_key": user_key,
                    "deck_id": deck_id,
                    "result": result,
                    "played_at": played_at,
                }
            },
        )

        return json_response(
            200,
            {
                "status": "ok",
                "played_at": played_at,
            },
        )

    except CommandLogError as error:
        logger.warning(
            "Game recording rejected.",
            extra={
                "data": {
                    "error": error.error_code,
                }
            },
        )
        return error_response(error)

    except Exception as error:
        logger.exception("Failed to record game")
        return error_response(error)
