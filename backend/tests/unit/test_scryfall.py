from commandlog.integrations import scryfall

def test_resolve_front_face_name(monkeypatch):
    def fake_fetch_collection(names):
        assert names == ["Avatar Aang"]

        return {
            "data": [
                {
                    "name": "Avatar Aang // Aang, Master of Elements",
                    "oracle_id": "aang-oracle-id",
                    "card_faces": [
                        {"name": "Avatar Aang"},
                        {"name": "Aang, Master of Elements"}
                    ]
                }
            ],
            "not_found": []
        }

    monkeypatch.setattr(
        scryfall,
        "fetch_collection",
        fake_fetch_collection
    )

    resolved, not_found = scryfall.resolve_card_names(
        ["Avatar Aang"]
    )

    assert not_found == []

    card = resolved["avatar aang"]

    assert card["oracle_id"] == "aang-oracle-id"
    assert card["name"] == (
        "Avatar Aang // Aang, Master of Elements"
    )

def test_resolve_full_double_faced_name_via_front_face_fallback(
    monkeypatch
):
    calls = []

    def fake_fetch_collection(names):
        calls.append(names)

        if names == [
            "Avatar Aang // Aang, Master of Elements"
        ]:
            return {
                "data": [],
                "not_found": [
                    {
                        "name":
                        "Avatar Aang // Aang, Master of Elements"
                    }
                ]
            }

        if names == ["Avatar Aang"]:
            return {
                "data": [
                    {
                        "name":
                        "Avatar Aang // Aang, Master of Elements",
                        "oracle_id": "aang-oracle-id",
                        "card_faces": [
                            {"name": "Avatar Aang"},
                            {"name": "Aang, Master of Elements"}
                        ]
                    }
                ],
                "not_found": []
            }

        raise AssertionError(
            f"Unexpected lookup: {names}"
        )

    monkeypatch.setattr(
        scryfall,
        "fetch_collection",
        fake_fetch_collection
    )

    resolved, not_found = scryfall.resolve_card_names(
        [
            "Avatar Aang // Aang, Master of Elements"
        ]
    )

    assert not_found == []

    card = resolved[
        "avatar aang // aang, master of elements"
    ]

    assert card["oracle_id"] == "aang-oracle-id"
    assert card["name"] == (
        "Avatar Aang // Aang, Master of Elements"
    )

    assert calls == [
        ["Avatar Aang // Aang, Master of Elements"],
        ["Avatar Aang"]
    ]