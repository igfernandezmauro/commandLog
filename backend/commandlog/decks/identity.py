from uuid import uuid4


def new_deck_id() -> str:
    return f"deck_{uuid4().hex}"