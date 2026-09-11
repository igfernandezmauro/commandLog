import os
from typing import Any
from functools import lru_cache

import boto3

def dynamodb_resource() -> Any:
    options: dict[str, str] = {
        "region_name": os.getenv("AWS_REGION", "ca-central-1"),
    }

    endpoint_url = os.getenv("AWS_ENDPOINT_URL")

    if endpoint_url:
        options["endpoint_url"] = endpoint_url

    return boto3.resource("dynamodb", **options)

@lru_cache(maxsize=1)
def s3_client() -> Any:
    options: dict[str, str] = {
        "region_name": os.getenv("AWS_REGION", "ca-central-1")
    }

    endpoint_url = os.getenv("AWS_ENDPOINT_URL")

    if endpoint_url:
        options["endpoint_url"] = endpoint_url

    return boto3.client("s3", **options)
