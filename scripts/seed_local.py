#!/usr/bin/env python3

import os
import sys
from typing import Any

import boto3
from botocore.exceptions import ClientError

REGION = os.getenv("AWS_REGION", "ca-central-1")
ENDPOINT_URL = os.getenv("AWS_ENDPOINT_URL", "http://localhost:4566")

STATE_TABLE = "commandlog_local_deck_state"
USERS_TABLE = "commandlog_local_user_profile"
PLAY_EVENTS_TABLE = "commandlog_local_play_events"

USER_KEY = "user#local-user"

def get_dynamodb():
    return boto3.resource(
        "dynamodb",
        region_name=REGION,
        endpoint_url=ENDPOINT_URL,
        aws_access_key_id="test",
        aws_secret_access_key="test",
    )

def table_exists(dynamodb: Any, table_name: str) -> bool:
    try:
        dynamodb.meta.client.describe_table(TableName=table_name)
        return True
    except ClientError as error:
        code = error.response["Error"]["Code"]

        if code == "ResourceNotFoundException":
            return False

        raise

def create_state_table(dynamodb: Any) -> None:
    if table_exists(dynamodb, STATE_TABLE):
        print(f"Table already exists: {STATE_TABLE}")
        return

    table = dynamodb.create_table(
        TableName=STATE_TABLE,
        KeySchema=[
            {"AttributeName": "user_key", "KeyType": "HASH"},
            {"AttributeName": "deck_id", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "deck_id", "AttributeType": "S"},
            {"AttributeName": "user_key", "AttributeType": "S"}
        ],
        BillingMode="PAY_PER_REQUEST",
    )

    table.wait_until_exists()
    print(f"Created table: {STATE_TABLE}")

def create_users_table(dynamodb: Any) -> None:
    if table_exists(dynamodb, USERS_TABLE):
        print(f"Table already exists: {USERS_TABLE}")
        return

    table = dynamodb.create_table(
        TableName=USERS_TABLE,
        KeySchema=[
            {"AttributeName": "user_key", "KeyType": "HASH"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "user_key", "AttributeType": "S"},
            {"AttributeName": "ingestion_enabled_key", "AttributeType": "S"},
        ],
        GlobalSecondaryIndexes=[
            {
                "IndexName": "gsi_ingestion_enabled",
                "KeySchema": [
                    {"AttributeName": "ingestion_enabled_key", "KeyType": "HASH"},
                    {"AttributeName": "user_key", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            }
        ],
        BillingMode="PAY_PER_REQUEST",
    )

    table.wait_until_exists()
    print(f"Created table: {USERS_TABLE}")

def create_play_events_table(dynamodb: Any) -> None:
    if table_exists(dynamodb, PLAY_EVENTS_TABLE):
        print(f"Table already exists: {PLAY_EVENTS_TABLE}")
        return

    table = dynamodb.create_table(
        TableName=PLAY_EVENTS_TABLE,
        KeySchema=[
            {"AttributeName": "user_key", "KeyType": "HASH"},
            {"AttributeName": "played_at", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "user_key", "AttributeType": "S"},
            {"AttributeName": "played_at", "AttributeType": "S"},
            {"AttributeName": "deck_id", "AttributeType": "S"},
        ],
        GlobalSecondaryIndexes=[
            {
                "IndexName": "gsi1.deck_id_played_at",
                "KeySchema": [
                    {"AttributeName": "deck_id", "KeyType": "HASH"},
                    {"AttributeName": "played_at", "KeyType": "RANGE"},
                ],
                "Projection": {
                    "ProjectionType": "ALL"
                },
            }
        ],
        BillingMode="PAY_PER_REQUEST",
    )

    table.wait_until_exists()
    print(f"Created table: {PLAY_EVENTS_TABLE}")

def seed_profile(dynamodb: Any) -> None:
    table = dynamodb.Table(USERS_TABLE)

    table.put_item(
        Item={
            "user_key": USER_KEY,
            "ingestion_source": "moxfield",
            "ingestion_enabled": True,
            "ingestion_enabled_key": "enabled",
            "moxfield_username": "local-commandlog-user",
        }
    )

    print("Seeded local user profile")

def seed_decks(dynamodb: Any) -> None:
    table = dynamodb.Table(STATE_TABLE)

    decks = [
        {
            "user_key": USER_KEY,
            "deck_id": "deck-alora",
            "name": "Alora, Merry Thief",
            "commander": "Alora, Merry Thief",
            "featured": "https://example.com/alora.jpg",
            "source": "moxfield",
            "changed_at": "2026-08-01T15:00:00+00:00",
            "last_played_at": "2026-07-20T19:00:00+00:00",
            "list_hash": "local-alora-v2",
        },
        {
            "user_key": USER_KEY,
            "deck_id": "deck-kadena",
            "name": "Kadena Morph",
            "commander": "Kadena, Slinking Sorcerer",
            "featured": "https://example.com/kadena.jpg",
            "source": "moxfield",
            "changed_at": "2026-06-15T12:00:00+00:00",
            "last_played_at": "2026-07-25T18:30:00+00:00",
            "list_hash": "local-kadena-v1",
        },
        {
            "user_key": USER_KEY,
            "deck_id": "deck-archidekt-example",
            "name": "Archidekt Test Deck",
            "commander": "Test Commander",
            "featured": "https://example.com/test.jpg",
            "source": "archidekt",
            "changed_at": "2026-08-01T10:00:00+00:00",
            "list_hash": "local-archidekt-v1",
        }
    ]

    with table.batch_writer() as batch:
        for deck in decks:
            batch.put_item(Item=deck)

    print(f"Seeded {len(decks)} local decks")

def seed_games(dynamodb: Any) -> None:
    table = dynamodb.Table(PLAY_EVENTS_TABLE)

    games = [
        {
            "user_key": USER_KEY,
            "played_at": "2026-08-01T22:00:00Z",
            "deck_id": "deck-alora",
            "deck_name": "Alora, Merry Thief",
            "commander": "Alora, Merry Thief",
            "result": "win",
            "store": "Local Game Store",
            "turn_order": 2,
            "mulligans": 1,
            "asof_list_hash": "local-alora-v2",
        },
        {
            "user_key": USER_KEY,
            "played_at": "2026-07-25T18:30:00Z",
            "deck_id": "deck-kadena",
            "deck_name": "Kadena Morph",
            "commander": "Kadena, Slinking Sorcerer",
            "result": "loss",
            "store": "Home",
            "turn_order": 4,
            "mulligans": 0,
            "asof_list_hash": "local-kadena-v1",
        },
        {
            "user_key": USER_KEY,
            "played_at": "2026-07-20T19:00:00Z",
            "deck_id": "deck-alora",
            "deck_name": "Alora, Merry Thief",
            "commander": "Alora, Merry Thief",
            "result": "loss",
            "store": "Local Game Store",
            "turn_order": 1,
            "mulligans": 2,
            "asof_list_hash": "local-alora-v1",
        },
    ]

    with table.batch_writer() as batch:
        for game in games:
            batch.put_item(Item=game)

    print(f"Seeded {len(games)} local games")

def main() -> int:
    try:
        dynamodb = get_dynamodb()

        create_state_table(dynamodb)
        create_users_table(dynamodb)
        create_play_events_table(dynamodb)

        seed_profile(dynamodb)
        seed_decks(dynamodb)
        seed_games(dynamodb)

        print("Local CommandLog data is ready")
        return 0

    except Exception as error:
        print(f"Failed to seed LocalStack: {error}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())