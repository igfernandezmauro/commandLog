from commandlog.ingestion import sync


def configure_archidekt(monkeypatch, normalized_results):
    normalized = iter(normalized_results)

    monkeypatch.setattr(
        sync.archidekt,
        "list_decks",
        lambda username: [{"id": "deck-a"}]
    )

    monkeypatch.setattr(
        sync.archidekt,
        "get_deck_id",
        lambda deck: deck["id"]
    )

    monkeypatch.setattr(
        sync.archidekt,
        "fetch_deck",
        lambda deck_id: {"id": deck_id}
    )

    monkeypatch.setattr(
        sync.archidekt,
        "normalize_deck",
        lambda deck: next(normalized)
    )

    monkeypatch.setattr(
        sync.archidekt,
        "get_metadata",
        lambda deck: {
            "name": "Deck A",
            "featured": None,
            "changed_at": "2026-01-01T00:00:00Z",
            "created_at": "2025-01-01T00:00:00Z"
        }
    )

    monkeypatch.setattr(
        sync.archidekt,
        "get_commander",
        lambda deck: "Commander A"
    )

    monkeypatch.setattr(
        sync.time,
        "sleep",
        lambda _: None
    )

def test_compute_diff_tracks_added_removed_and_quantity_changes():
    result = sync.compute_diff(
        {
            "kept": 1,
            "removed": 1,
            "changed": 1,
        },
        {
            "kept": 1,
            "added": 2,
            "changed": 3,
        }
    )

    assert sorted(result["added"]) == [ ("added", 2) ]
    assert sorted(result["removed"]) == [ ("removed", 1) ]
    assert sorted(result["changed"]) == [ ("changed", 1, 3) ]

def test_second_identical_sync_is_unchanged_and_keeps_existing_snapshot(monkeypatch):
    configure_archidekt(
        monkeypatch,
        [
            {
                "hash": "hash-v1",
                "main": {"card-a": 1},
            },
            {
                "hash": "hash-v1",
                "main": {"card-a": 1},
            }
        ]
    )

    timestamps = iter(["2026-01-01T10:00:00Z", "2026-01-02T10:00:00Z"])

    monkeypatch.setattr(
        sync,
        "now_iso",
        lambda: next(timestamps)
    )

    state = {}
    snapshots = []
    changes = []

    monkeypatch.setattr(
        sync,
        "get_current_deck",
        lambda user_key, deck_id: dict(state) if state else None
    )

    monkeypatch.setattr(
        sync,
        "save_snapshot",
        lambda key, snapshot: snapshots.append(key)
    )

    monkeypatch.setattr(
        sync,
        "save_change",
        lambda item: changes.append(item)
    )

    def fake_update_deck_state(**kwargs):
        state.clear()
        state.update(
            {
                "user_key": kwargs["user_key"],
                "deck_id": kwargs["deck_id"],
                "list_hash": kwargs["list_hash"],
                "main": kwargs["main"],
                "raw_s3_key": kwargs["raw_key"]
            }
        )

    monkeypatch.setattr(
        sync,
        "update_deck_state",
        fake_update_deck_state
    )

    first = sync.sync_archidekt_user(
        "user#test",
        "test-user"
    )

    first_snapshot_key = state["raw_s3_key"]

    second = sync.sync_archidekt_user(
        "user#test",
        "test-user"
    )

    assert first["changed"] == 1
    assert first["unchanged"] == 0

    assert second["changed"] == 0
    assert second["unchanged"] == 1

    # Only the first sync should create history/snapshot records.
    assert len(snapshots) == 1
    assert len(changes) == 1

    # Regression: list_hash must be persisted so the second run recognizes that nothing changed.
    assert state["list_hash"] == "hash-v1"

    # An unchanged sync must not point state at an S3 key that wasn't written
    assert state["raw_s3_key"] == first_snapshot_key

def test_changed_deck_updates_same_identity_and_records_new_hash(monkeypatch):
    configure_archidekt(
        monkeypatch,
        [
            {
                "hash": "hash-v1",
                "main": {"card-a": 1},
            },
            {
                "hash": "hash-v2",
                "main": {
                    "card-a": 1,
                    "card-b": 1,
                },
            }
        ]
    )

    timestamps = iter(["2026-01-01T10:00:00Z", "2026-01-02T10:00:00Z"])

    monkeypatch.setattr(
        sync,
        "now_iso",
        lambda: next(timestamps)
    )

    state = {}
    changes = []
    updates = []

    monkeypatch.setattr(
        sync,
        "get_current_deck",
        lambda user_key, deck_id: dict(state) if state else None
    )

    monkeypatch.setattr(
        sync,
        "save_snapshot",
        lambda key, snapshot: None
    )

    monkeypatch.setattr(
        sync,
        "save_change",
        lambda item: changes.append(item)
    )

    def fake_update_deck_state(**kwargs):
        updates.append(dict(kwargs))

        state.clear()
        state.update(
            {
                "user_key": kwargs["user_key"],
                "deck_id": kwargs["deck_id"],
                "list_hash": kwargs["list_hash"],
                "main": kwargs["main"],
                "raw_s3_key": kwargs["raw_key"]
            }
        )

    monkeypatch.setattr(
        sync,
        "update_deck_state",
        fake_update_deck_state
    )

    sync.sync_archidekt_user(
        "user#test",
        "test-user"
    )

    result = sync.sync_archidekt_user(
        "user#test",
        "test-user"
    )

    assert result["processed"] == 1
    assert result["changed"] == 1
    assert result["unchanged"] == 0

    # Reimport/update retains the same external deck identity
    assert updates[0]["deck_id"] == "deck-a"
    assert updates[1]["deck_id"] == "deck-a"

    assert state["list_hash"] == "hash-v2"

    assert len(changes) == 2
    assert changes[0]["change_type"] == "CREATED"
    assert changes[1]["change_type"] == "UPDATED"
    assert changes[1]["list_hash"] == "hash-v2"

    assert changes[1]["diff_summary"] == {
        "added": [("card-b", 1)],
        "removed": [],
        "changed": []
    }
