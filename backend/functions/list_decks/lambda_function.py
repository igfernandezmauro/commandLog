from boto3.dynamodb.conditions import Key

from commandlog.logging import get_logger
from commandlog.auth import get_user_key
from commandlog.exceptions import CommandLogError
from commandlog.responses import error_response, json_response
from commandlog.tables import deck_state_table


logger = get_logger(__name__)

tbl_state = deck_state_table()


def lambda_handler(event, context):
    try:
        user_key = get_user_key(event)
        
        items = []
        
        query_kwargs = {
            "KeyConditionExpression": Key("user_key").eq(user_key),
            "ProjectionExpression": "deck_id, #n, commander, featured, changed_at, last_played_at, #s",
            "ExpressionAttributeNames": { "#n": "name", "#s": "source" },
            "ConsistentRead": True,
        }
        
        response = tbl_state.query(**query_kwargs)
        items.extend(response.get("Items", []))
        
        while "LastEvaluatedKey" in response:
            response = tbl_state.query(
                ExclusiveStartKey=response["LastEvaluatedKey"],
                **query_kwargs,
            )
            items.extend(response.get("Items", []))
        
        
        for item in items:
            last_played_at = item.get("last_played_at")
            item["updated_since_last_played"] = item["changed_at"] > last_played_at if last_played_at else True
        
        items.sort(key=lambda item: (item.get("name") or "").lower())

        logger.info(
            "Decks listed",
            extra={
                "data": {
                    "user_key": user_key,
                    "deck_count": len(items)
                }
            },
        )
        
        return json_response(200, items, cors=False)
    
    except CommandLogError as error:
        logger.warning(
            "Decks listing rejected",
            extra={"data": {"error": error.error_code}},
        )
        return error_response(error, cors=False)

    except Exception as error:
        logger.exception("Failed to list decks")
        return error_response(error, cors=False)

   
