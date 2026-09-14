#!/usr/bin/env python3

import argparse
import sys
from dataclasses import dataclass

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError


REGION = "ca-central-1"

SOURCE_BUCKET = "ignacio-mtg-app-raw-ca-central-1"
DESTINATION_BUCKET = "commandlog-prod-280535250460-ca-central-1-snapshots"

STATE_TABLE = "mtg_app_deck_state_v2"
CHANGE_TABLE = "mtg_app_deck_change_log"

EXCLUDED_ARCHIDEKT_USERS = { "capagmu" }


@dataclass
class MigrationStats:
    copied: int = 0
    already_exists: int = 0
    skipped: int = 0
    missing_source: int = 0
    repaired: int = 0
    unresolved: int = 0

def object_exists(s3, bucket: str, key: str) -> bool:
    try:
        s3.head_object(
            Bucket=bucket,
            Key=key
        )
        return True

    except ClientError as error:
        code = error.response.get("Error", {}).get("Code")

        if code in {"404", "NoSuchKey", "NotFound"}:
            return False

        raise

def scan_all(table) -> list[dict]:
    response = table.scan()
    items = response.get("Items", [])

    while "LastEvaluatedKey" in response:
        response = table.scan(
            ExclusiveStartKey=response["LastEvaluatedKey"]
        )
        items.extend(response.get("Items", []))

    return items

def archidekt_username_from_key(key: str | None) -> str | None:
    if not key:
        return None

    parts = key.split("/")

    # archidekt/user/<username>/decks/...
    if(len(parts) >= 4 and parts[0] == "archidekt" and parts[1] == "user"):
        return parts[2]

    return None

def should_keep_state(state: dict) -> bool:
    if state.get("source") != "archidekt":
        return False

    username = archidekt_username_from_key(state.get("raw_s3_key"))

    if username in EXCLUDED_ARCHIDEKT_USERS:
        return False

    return True

def should_keep_snapshot_key(key: str | None) -> bool:
    if not key:
        return False

    if not key.startswith("archidekt/"):
        return False

    username = archidekt_username_from_key(key)

    if username in EXCLUDED_ARCHIDEKT_USERS:
        return False

    return True

def migrate_change_snapshots(*, change_table, s3, apply: bool, stats: MigrationStats) -> None:
    print("=== CHANGE LOG SNAPSHOT AUDIT ===")

    changes = scan_all(change_table)
    seen_keys: set[str] = set()

    for change in changes:
        raw_key = change.get("s3_key")

        if not raw_key:
            continue

        key = str(raw_key)

        if not should_keep_snapshot_key(key):
            stats.skipped += 1
            continue

        if key in seen_keys:
            continue

        seen_keys.add(key)

        copy_object(
            s3=s3,
            key=key,
            apply=apply,
            stats=stats
        )

    print(f"Audited {len(seen_keys)} unique snapshot references.")
    print()

def get_changes(change_table, deck_id: str) -> list[dict]:
    response = change_table.query(
        KeyConditionExpression=Key("deck_id").eq(deck_id),
        ScanIndexForward=True
    )

    items = response.get("Items", [])

    while "LastEvaluatedKey" in response:
        response = change_table.query(
            KeyConditionExpression=Key("deck_id").eq(deck_id),
            ScanIndexForward=True,
            ExclusiveStartKey=response["LastEvaluatedKey"]
        )
        items.extend(response.get("Items", []))

    return items

def find_recovery_key(*, s3, changes: list[dict], current_hash: str | None) -> str | None:
    if not current_hash:
        return None

    matching = [change for change in changes if change.get("list_hash") == current_hash and change.get("s3_key")]

    matching.sort(key=lambda item: item.get("changed_at") or "", reverse=True)

    for change in matching:
        key = str(change["s3_key"])

        if object_exists(s3, SOURCE_BUCKET, key):
            return key

    return None

def copy_object(*, s3, key: str, apply: bool, stats: MigrationStats) -> None:
    if object_exists(s3, DESTINATION_BUCKET, key):
        print(f"EXISTS  {key}")
        stats.already_exists += 1
        return

    if not object_exists(s3, SOURCE_BUCKET, key):
        print(f"MISSING {key}")
        stats.missing_source += 1
        return

    if apply:
        s3.copy_object(
            Bucket=DESTINATION_BUCKET,
            Key=key,
            CopySource={
                "Bucket": SOURCE_BUCKET,
                "Key": key
            }
        )

    print(f"{'COPY' if apply else 'WOULD COPY':10}  {key}")
    stats.copied += 1

def migrate(*, apply: bool, repair_state: bool) -> int:
    dynamodb = boto3.resource("dynamodb", region_name=REGION)
    s3 = boto3.client("s3",region_name=REGION)

    state_table = dynamodb.Table(STATE_TABLE)
    change_table = dynamodb.Table(CHANGE_TABLE)

    states = scan_all(state_table)

    retained_states = [ state for state in states if should_keep_state(state) ]

    stats = MigrationStats()

    migrate_change_snapshots(change_table=change_table, s3=s3, apply=apply, stats=stats)

    print("=== COMMANDLOG PRODUCTION SNAPSHOT MIGRATION ===")
    print(f"mode={'APPLY' if apply else 'DRY RUN'}")
    print(f"source={SOURCE_BUCKET}")
    print(f"destination={DESTINATION_BUCKET}")
    print()

    if repair_state:
        for state in retained_states:
            deck_id = str(state["deck_id"])
            current_hash = state.get("list_hash")
            current_key = state.get("raw_s3_key")

            username = archidekt_username_from_key(current_key)

            print(f"=== deck={deck_id}    user={username} ===")

            changes = get_changes(change_table, deck_id)

            retained_changes = []

            for change in changes:
                key = change.get("s3_key")

                if not key:
                    continue

                key = str(key)

                if not should_keep_snapshot_key(key):
                    continue

                retained_changes.append(change)

            # Prefer preserving the stat;s existing raw_s3_key.
            if current_key and should_keep_snapshot_key(str(current_key)):
                current_key = str(current_key)

                if object_exists(s3, DESTINATION_BUCKET, current_key):
                    print(f"CURRENT EXISTS {current_key}")
                    print()
                    continue

                if object_exists(s3, SOURCE_BUCKET, current_key):
                    copy_object(
                        s3=s3,
                        key=current_key,
                        apply=apply,
                        stats=stats
                    )

                    print()
                    continue

            if current_key:
                print(f"CURRENT MISSING {current_key}")
            else:
                print("CURRENT MISSING  <no raw_s3_key>")

            recovery_key = find_recovery_key(
                s3=s3,
                changes=retained_changes,
                current_hash=current_hash
            )

            if not recovery_key:
                print(f"UNRESOLVED  deck={deck_id}  hash={current_hash}")
                stats.unresolved += 1
                print()
                continue

            copy_object(
                s3=s3,
                key=recovery_key,
                apply=apply,
                stats=stats
            )

            if apply:
                state_table.update_item(
                    Key={
                        "user_key": state["user_key"],
                        "deck_id": state["deck_id"]
                    },
                    UpdateExpression="SET raw_s3_key = :key",
                    ExpressionAttributeValues={
                        ":key": recovery_key
                    }
                )

            print(
                f"{'REPAIRED' if apply else 'WOULD REPAIR'}"
                f"raw_s3_key -> {recovery_key}"
            )
            stats.repaired += 1
            print()

    print("=== SUMMARY ===")
    print(f"copied={stats.copied}")
    print(f"already_exists={stats.already_exists}")
    print(f"skipped={stats.skipped}")
    print(f"missing_source={stats.missing_source}")
    print(f"repaired={stats.repaired}")
    print(f"unresolved={stats.unresolved}")

    if stats.unresolved or stats.missing_source:
        return 1

    return 0

def parse_args():
    parser = argparse.ArgumentParser(
        description="Migrate retained production Archidekt snapshots intro CommandLog production storage."
    )

    parser.add_argument(
        "--apply",
        action="store_true",
        help=(
            "Perform S3 copies and DynamoDB pointer repairs. "
            "Without this flag the script is read-only."
        )
    )

    parser.add_argument(
        "--repair-state",
        action="store_true",
        help="Also repair deck_state raw_s3_key pointers."
    )

    return parser.parse_args()

def main():
    args = parse_args()

    if args.apply:
        confirmation = input(
            "This will modify production S3/DynamoDB. "
            "Type APPLY to continue: "
        )

        if confirmation != "APPLY":
            print("Aborted.")
            return 2

    return migrate(
        apply=args.apply,
        repair_state=args.repair_state
    )

if __name__ == "__main__":
    sys.exit(main())
