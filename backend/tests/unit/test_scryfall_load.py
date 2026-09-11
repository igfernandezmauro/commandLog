from functions.scryfall_load import lambda_function


def test_source_from_native_s3_event():
    event = {
        "Records": [
            {
                "eventSource": "aws:s3",
                "s3": {
                    "bucket": {
                        "name": "commandlog-test-raw",
                    },
                    "object": {
                        "key": "scryfall/oracle_cards/latest.jsonl.gz",
                    }
                }
            }
        ]
    }

    bucket, key = lambda_function.source_from_event(event)

    assert bucket == "commandlog-test-raw"
    assert key == "scryfall/oracle_cards/latest.jsonl.gz"

def test_source_from_eventbridge_s3_event():
    event = {
        "source": "aws.s3",
        "detail-type": "Object Created",
        "detail": {
            "bucket": {
                "name": "commandlog-test-raw",
            },
            "object": {
                "key": "scryfall/oracle_cards/latest.jsonl.gz",
            }
        }
    }

    bucket, key = lambda_function.source_from_event(event)

    assert bucket == "commandlog-test-raw"
    assert key == "scryfall/oracle_cards/latest.jsonl.gz"

def test_source_from_unrelated_event_returns_none():
    bucket, key = lambda_function.source_from_event(
        {
            "source": "aws.scheduler",
        }
    )

    assert bucket is None
    assert key is None

def test_handler_falls_back_to_raw_bucket_and_default_key(monkeypatch):
    captured = {}

    monkeypatch.setenv("RAW_BUCKET", "commandlog-test-raw")

    def fake_iter_oracle_cards(bucket, key):
        captured["bucket"] = bucket
        captured["key"] = key
        return iter([])

    def fake_load_cards(cards, *, write_batch_size):
        list(cards)

        captured["write_batch_size"] = write_batch_size

        return {
            "cards_written": 0,
            "missing_oracle_id": 0
        }

    monkeypatch.setattr(
        lambda_function,
        "iter_oracle_cards",
        fake_iter_oracle_cards
    )

    monkeypatch.setattr(
        lambda_function,
        "load_cards",
        fake_load_cards
    )

    result = lambda_function.lambda_handler({}, None)

    assert captured["bucket"] == "commandlog-test-raw"
    assert captured["key"] == "scryfall/oracle_cards/latest.jsonl.gz"
    assert captured["write_batch_size"] == 2000

    assert result["status"] == "ok"
    assert result["source_bucket"] == "commandlog-test-raw"
    assert result["source_key"] == "scryfall/oracle_cards/latest.jsonl.gz"
