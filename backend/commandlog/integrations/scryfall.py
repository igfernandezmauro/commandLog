import json
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


COLLECTION_URL = "https://api.scryfall.com/cards/collection"
COLLECTION_SIZE = 75
REQUEST_DELAY_SECONDS = 0.12

USER_AGENT = "CommandLog/1.0 (https://commandlog.app)"
ACCEPT = "application/json;q=0.9,*/*;q=0.8"


def chunks(items: list[str], size: int):
    for index in range(0, len(items), size):
        yield items[index:index + size]

def fetch_collection(names: list[str]) -> dict[str, Any]:
    request = Request(
        COLLECTION_URL,
        data=json.dumps(
            {
                "identifiers": [
                    {"name": name}
                    for name in names
                ]
            }
        ).encode("utf-8"),
        headers={
            "User-Agent": USER_AGENT,
            "Accept": ACCEPT,
            "Content-Type": "application/json"
        },
        method="POST"
    )

    try:
        with urlopen(request, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))

    except (HTTPError, URLError, TimeoutError) as error:
        raise RuntimeError("Failed to resolve cards with Scryfall.") from error

def card_lookup_names(card: dict[str, Any]) -> list[str]:
    names: list[str] = []

    canonical_name = str(card.get("name") or "").strip()

    if canonical_name:
        names.append(canonical_name)

    faces = card.get("card_faces") or []

    if faces and isinstance(faces[0], dict):
        front_name = str(faces[0].get("name") or "").strip()

        if front_name:
            names.append(front_name)

    return names

def register_resolved_cards(resolved: dict[str, dict[str, Any]], card: dict[str, Any]) -> None:
    canonical_name = str(card.get("name") or "").strip()
    oracle_id = str(card.get("oracle_id") or "").strip()

    if not canonical_name or not oracle_id:
        return

    resolved_card = {
        "oracle_id": oracle_id,
        "name": canonical_name,
        "image_art_crop": image_uri(card, "art_crop"),
        "image_normal": image_uri(card, "normal")
    }

    for name in card_lookup_names(card):
        resolved[name.casefold()] = resolved_card

def unique_names(names: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []

    for name in names:
        key = name.casefold()

        if key in seen:
            continue

        seen.add(key)
        result.append(name)

    return result

def resolve_card_names(names: list[str]) -> tuple[dict[str, dict[str, Any]], list[str]]:
    resolved: dict[str, dict[str, Any]] = {}

    requested_names = unique_names(
        [
            str(name).strip()
            for name in names
            if str(name).strip()
        ]
    )

    batches = list(chunks(requested_names, COLLECTION_SIZE))

    for index, batch in enumerate(batches):
        response = fetch_collection(batch)

        for card in response.get("data") or []:
            register_resolved_cards(resolved, card)

        if index < len(batches) - 1:
            time.sleep(REQUEST_DELAY_SECONDS)

    unresolved = [
        name
        for name in requested_names
        if name.casefold() not in resolved
    ]

    fallback_names: list[str] = []

    for name in unresolved:
        if "//" not in name:
            continue

        front_name = name.split("//", 1)[0].strip()

        if front_name:
            fallback_names.append(front_name)

    fallback_names = unique_names(fallback_names)

    fallback_batches = list(chunks(fallback_names, COLLECTION_SIZE))

    if fallback_batches and batches:
        time.sleep(REQUEST_DELAY_SECONDS)

    for index, batch in enumerate(fallback_batches):
        response = fetch_collection(batch)

        for card in response.get("data") or []:
            register_resolved_cards(resolved, card)

        if index < len(fallback_batches) - 1:
            time.sleep(REQUEST_DELAY_SECONDS)

    for requested_name in unresolved:
        if "//" not in requested_name:
            continue

        front_name = requested_name.split("//", 1)[0].strip()

        card = resolved.get(front_name.casefold())

        if card:
            resolved[requested_name.casefold()] = card

    not_found = [
        name
        for name in requested_names
        if name.casefold() not in resolved
    ]

    return resolved, not_found

def image_uri(card: dict[str, Any], size: str) -> str | None:
    image_uris = card.get("image_uris") or {}

    if image_uris.get(size):
        return str(image_uris[size])

    for face in card.get("card_faces") or []:
        if not isinstance(face, dict):
            continue

        face_images = face.get("image_uris") or {}

        if face_images.get(size):
            return str(face_images[size])

    return None