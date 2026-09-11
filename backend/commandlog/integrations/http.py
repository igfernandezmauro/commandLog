import json
import time
import urllib.request
from urllib.error import HTTPError, URLError
from typing import Any


USER_AGENT = (
    "CommandLog/1.0 (personal project; contact: i.fernandezmauro@gmail.com)"
)

DEFAULT_ACCEPT = "application/json"


def get_json(url: str, *, timeout: int = 20, retries: int = 4) -> Any:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": DEFAULT_ACCEPT
        },
        method="GET"
    )

    last_error = None

    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(
                request,
                timeout=timeout,
            ) as response:
                return json.loads(
                    response.read().decode("utf-8")
                )

        except HTTPError as error:
            last_error = f"HTTP {error.code}"

            if error.code in {429, 500, 502, 503, 504}:
                time.sleep((2 ** attempt) * 0.5)
                continue

            raise

        except URLError as error:
            last_error = str(error)
            time.sleep((2 ** attempt) * 0.5)

    raise RuntimeError(
        f"GET failed after retries: {url} ({last_error})"
    )

def open_stream(url: str, *, timeout: int = 300, accept: str = "application/json;q=0.9;*/*;q=0.8"):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": accept
        }
    )

    return urllib.request.urlopen(
        request,
        timeout=timeout
    )
