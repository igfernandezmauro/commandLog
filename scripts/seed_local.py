#!/usr/bin/env python3

import os
import sys
from typing import Any

import boto3
from botocore.exceptions import ClientError

from pathlib import Path

REGION = os.getenv("AWS_REGION", "ca-central-1")
ENDPOINT_URL = os.getenv("AWS_ENDPOINT_URL", "http://localhost:4566")

STATE_TABLE = "commandlog_local_deck_state"
USERS_TABLE = "commandlog_local_user_profile"
PLAY_EVENTS_TABLE = "commandlog_local_play_events"
CHANGE_LOG_TABLE = "commandlog_local_deck_change_log"
DIFF_TABLE = "commandlog_local_deck_diffs"
CARDS_DIM_TABLE = "commandlog_local_cards_dim"
PRINT_MAP_TABLE = "commandlog_local_scryfall_print_map"

SNAPSHOT_BUCKET = "commandlog-local-snapshots"

USER_KEY = "user#local-user"

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_FIXTURES = PROJECT_ROOT / "local" / "seed" / "snapshots"

def get_dynamodb():
    return boto3.resource(
        "dynamodb",
        region_name=REGION,
        endpoint_url=ENDPOINT_URL,
        aws_access_key_id="test",
        aws_secret_access_key="test",
    )

def get_s3_client():
    return boto3.client(
        "s3",
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

def create_change_log_table(dynamodb: Any) -> None:
    if table_exists(dynamodb, CHANGE_LOG_TABLE):
        print(f"Table already exists: {CHANGE_LOG_TABLE}")
        return

    table = dynamodb.create_table(
        TableName=CHANGE_LOG_TABLE,
        KeySchema=[
            {"AttributeName": "deck_id", "KeyType": "HASH"},
            {"AttributeName": "changed_at", "KeyType": "RANGE"}
        ],
        AttributeDefinitions=[
            {"AttributeName": "deck_id", "AttributeType": "S"},
            {"AttributeName": "changed_at", "AttributeType": "S"}
        ],
        BillingMode="PAY_PER_REQUEST",
    )

    table.wait_until_exists()
    print(f"Created table: {CHANGE_LOG_TABLE}")

def create_diff_table(dynamodb: Any) -> None:
    if table_exists(dynamodb, DIFF_TABLE):
        print(f"Table already existst: {DIFF_TABLE}")
        return

    table = dynamodb.create_table(
        TableName=DIFF_TABLE,
        KeySchema=[
            {"AttributeName": "deck_id", "KeyType": "HASH"},
            {"AttributeName": "diff_key", "KeyType": "RANGE"}
        ],
        AttributeDefinitions=[
            {"AttributeName": "deck_id", "AttributeType": "S"},
            {"AttributeName": "diff_key", "AttributeType": "S"}
        ],
        BillingMode="PAY_PER_REQUEST",
    )

    table.wait_until_exists()
    print(f"Created table: {DIFF_TABLE}")

def create_cards_dimension_table(dynamodb: Any) -> None:
    if table_exists(dynamodb, CARDS_DIM_TABLE):
        print(f"Table already exists: {CARDS_DIM_TABLE}")
        return

    table = dynamodb.create_table(
        TableName=CARDS_DIM_TABLE,
        KeySchema=[
            {"AttributeName": "oracle_id", "KeyType": "HASH"}
        ],
        AttributeDefinitions=[
            {"AttributeName": "oracle_id", "AttributeType": "S"}
        ],
        BillingMode="PAY_PER_REQUEST",
    )

    table.wait_until_exists()
    print(f"Created table: {CARDS_DIM_TABLE}")

def create_print_map_table(dynamodb: Any) -> None:
    if table_exists(dynamodb, PRINT_MAP_TABLE):
        print(f"Table already exists: {PRINT_MAP_TABLE}")
        return

    table = dynamodb.create_table(
        TableName=PRINT_MAP_TABLE,
        KeySchema=[
            {"AttributeName": "scryfall_id", "KeyType": "HASH"}
        ],
        AttributeDefinitions=[
            {"AttributeName": "scryfall_id", "AttributeType": "S"}
        ],
        BillingMode="PAY_PER_REQUEST",
    )

    table.wait_until_exists()
    print(f"Created table: {PRINT_MAP_TABLE}")

def create_snapshot_bucket(s3_client: Any) -> None:
    try:
        s3_client.head_bucket(Bucket=SNAPSHOT_BUCKET)
        print(f"Bucket already exists: {SNAPSHOT_BUCKET}")
    except ClientError:
        s3_client.create_bucket(
            Bucket=SNAPSHOT_BUCKET,
            CreateBucketConfiguration={
                "LocationConstraint": REGION,
            },
        )
        print(f"Created bucket: {SNAPSHOT_BUCKET}")

def seed_profile(dynamodb: Any) -> None:
    table = dynamodb.Table(USERS_TABLE)

    table.put_item(
        Item={
            "user_key": USER_KEY,
            "ingestion_source": "archidekt",
            "ingestion_enabled": True,
            "ingestion_enabled_key": "1",
            "archidekt_username": "local-archidekt-user-outdated",
            "moxfield_username": "",
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
            "result": "WIN",
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
            "result": "LOSS",
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
            "result": "LOSS",
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

def seed_deck_history(dynamodb: Any) -> None:
    table = dynamodb.Table(CHANGE_LOG_TABLE)

    records = [
        {
            "deck_id": "deck-alora",
            "changed_at": "2026-06-01T12:00:00Z",
            "change_type": "CREATED",
            "source": "moxfield",
            "list_hash": "local-alora-v1",
            "s3_key": "moxfield/local/decks/deck-alora/snapshot-v1.json",
        },
        {
            "deck_id": "deck-alora",
            "changed_at": "2026-08-01T15:00:00Z",
            "change_type": "UPDATED",
            "source": "moxfield",
            "list_hash": "local-alora-v2",
            "s3_key": "moxfield/local/decks/deck-alora/snapshot-v2.json",
        },
        {
            "deck_id": "deck-kadena",
            "changed_at": "2026-06-15T12:00:00Z",
            "change_type": "CREATED",
            "list_hash": "local-kadena-v1"
        }
    ]

    with table.batch_writer() as batch:
        for record in records:
            batch.put_item(Item=record)

    print(f"Seeded {len(records)} deck history records")

def seed_cards_dimension(dynamodb: Any) -> None:
    table = dynamodb.Table(CARDS_DIM_TABLE)

    cards = [
        {
            "oracle_id": "cccccccc-cccc-cccc-cccc-cccccccccccc",
            "name": "Mulldrifter",
            "image_small": "https://example.com/mulldrifter-small.jpg",
            "image_normal": "https://example.com/mulldrifter-normal.jpg",
        },
        {
            "oracle_id": "dddddddd-dddd-dddd-dddd-dddddddddddd",
            "name": "Ninja of the Deep Hours",
            "image_small": "https://example.com/ninja-small.jpg",
            "image_normal": "https://example.com/ninja-normal.jpg",
        },
    ]

    with table.batch_writer() as batch:
        for card in cards:
            batch.put_item(Item=card)

    print(f"Seeded {len(cards)} card dimension records")

def seed_snapshots(s3_client: Any) -> None:
    snapshots = {
        "moxfield/local/decks/deck-alora/snapshot-v1.json": SNAPSHOT_FIXTURES / "moxfield-alora-v1.json",
        "moxfield/local/decks/deck-alora/snapshot-v2.json": SNAPSHOT_FIXTURES / "moxfield-alora-v2.json",
        "archidekt/local/decks/deck-archidekt-example/snapshot-v1.json": SNAPSHOT_FIXTURES / "archidekt-test-v1.json",
    }

    for key, fixture_path in snapshots.items():
        s3_client.put_object(
            Bucket=SNAPSHOT_BUCKET,
            Key=key,
            Body=fixture_path.read_bytes(),
            ContentType="application/json",
        )

    print(f"Seeded {len(snapshots)} snapshot objects")

def main() -> int:
    try:
        dynamodb = get_dynamodb()
        s3_client = get_s3_client()

        create_state_table(dynamodb)
        create_users_table(dynamodb)
        create_play_events_table(dynamodb)
        create_change_log_table(dynamodb)
        create_diff_table(dynamodb)
        create_cards_dimension_table(dynamodb)
        create_print_map_table(dynamodb)

        create_snapshot_bucket(s3_client)

        seed_profile(dynamodb)
        seed_decks(dynamodb)
        seed_games(dynamodb)
        seed_deck_history(dynamodb)
        seed_cards_dimension(dynamodb)

        seed_snapshots(s3_client)

        print("Local CommandLog data is ready")
        return 0

    except Exception as error:
        print(f"Failed to seed LocalStack: {error}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())