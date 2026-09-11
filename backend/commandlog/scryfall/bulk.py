import gzip
import json
from datetime import datetime, timezone
from typing import Any, Iterator

from commandlog.aws import s3_client
from commandlog.config import required_env
from commandlog.integrations.http import get_json, open_stream


ORACLE_CARDS_METADATA_URL = "https://api.scryfall.com/bulk-data/oracle_cards"

DEFAULT_PREFIX = "scryfall/oracle_cards"


def now_utc() -> datetime:
    return datetime.now(timezone.utc)

def now_iso() -> str:
    return now_utc().replace(microsecond=0).isoformat().replace("+00:00", "Z")

def get_oracle_cards_metadata() -> dict[str, Any]:
    return get_json(ORACLE_CARDS_METADATA_URL, timeout=30)

def download_oracle_cards() -> dict[str, Any]:
    bucket = required_env("RAW_BUCKET")

    metadata = get_oracle_cards_metadata()

    download_uri = metadata.get("jsonl_download_uri")

    if not download_uri:
        raise RuntimeError("Scryfall metadata did not provide jsonl_download_uri.")

    now = now_utc()

    day = now.strftime("%Y%m%d")
    timestamp = now.strftime("%Y%m%dT%H%M%SZ")

    prefix = DEFAULT_PREFIX

    historical_key = f"{prefix}/dt={day}/oracle_cards_{timestamp}.jsonl.gz"

    latest_key = f"{prefix}/latest.jsonl.gz"

    meta_key = f"{prefix}/latest_meta.json"

    s3 = s3_client()

    with open_stream(download_uri, timeout=300) as response:
        s3.upload_fileobj(
            response,
            bucket,
            historical_key,
            ExtraArgs={
                "ContentType": "application/gzip"
            }
        )

    s3.copy_object(
        Bucket=bucket,
        CopySource={
            "Bucket": bucket,
            "Key": historical_key
        },
        Key=latest_key,
        ContentType="application/gzip",
        MetadataDirective="REPLACE"
    )

    metadata_output = {
        "fetched_at": now_iso(),
        "bulk_updated_at": metadata.get("updated_at"),
        "jsonl_download_uri": download_uri,
        "historical_key": historical_key,
        "latest_key": latest_key
    }

    s3.put_object(
        Bucket=bucket,
        Key=meta_key,
        Body=json.dumps(metadata_output).encode("utf-8"),
        ContentType="application/json"
    )

    return metadata_output

def iter_oracle_cards(bucket: str, key: str) -> Iterator[dict[str, Any]]:
    response = s3_client().get_object(
        Bucket=bucket,
        Key=key
    )

    body = response["Body"]

    with gzip.GzipFile(fileobj=body, mode="rb") as compressed:
        for raw_line in compressed:
            line = raw_line.strip()

            if not line:
                continue

            yield json.loads(line.decode("utf-8"))