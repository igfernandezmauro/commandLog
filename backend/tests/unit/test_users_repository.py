from commandlog.users import repository


class FakeTable:
    def query(self, **kwargs):
        return {
            "Items": [
                {
                    "user_key": "user#archidekt",
                    "ingestion_source": "archidekt",
                    "archidekt_username": "nacho108",
                },
                {
                    "user_key": "user#moxfield",
                    "ingestion_source": "moxfield",
                    "moxfield_username": "legacy-user",
                },
                {
                    "user_key": "user#disabled-data",
                    "ingestion_source": "archidekt",
                },
            ]
        }


def test_list_enabled_profiles_returns_profiles(monkeypatch):
    monkeypatch.setattr(
        repository,
        "user_profile_table",
        lambda: FakeTable(),
    )

    profiles = repository.list_enabled_profiles()

    assert profiles == [
        {
            "user_key": "user#archidekt",
            "ingestion_source": "archidekt",
            "username": "nacho108",
        },
        {
            "user_key": "user#moxfield",
            "ingestion_source": "moxfield",
            "username": "legacy-user",
        },
    ]