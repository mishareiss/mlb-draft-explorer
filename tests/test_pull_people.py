from unittest.mock import MagicMock

from ingest import http, pull_people


def test_250_ids_make_3_requests_of_at_most_100(tmp_path, monkeypatch):
    monkeypatch.setattr(http, "MIN_INTERVAL_S", 0)
    monkeypatch.setattr(pull_people.paths, "RAW", tmp_path)
    session = MagicMock()
    session.get.return_value.json.return_value = {"people": []}
    session.get.return_value.content = b'{"people": []}'
    monkeypatch.setattr(http, "_session", session)

    pull_people.fetch_people(range(1, 251))

    urls = [c.args[0] for c in session.get.call_args_list]
    assert len(urls) == 3
    sizes = [len(u.split("personIds=")[1].split(",")) for u in urls]
    assert sizes == [100, 100, 50]
    assert sorted(p.name for p in (tmp_path / "people").iterdir()) == [
        "batch_000.json",
        "batch_001.json",
        "batch_002.json",
    ]


def test_flatten_people_keeps_fields(people_payload):
    df = pull_people.flatten_people(people_payload["people"])
    assert len(df) == 3
    for col in (
        "id",
        "full_name",
        "birth_date",
        "mlb_debut_date",
        "birth_country",
        "primary_position_abbreviation",
        "bat_side_code",
        "pitch_hand_code",
    ):
        assert col in df.columns
    assert df["mlb_debut_date"].isna().sum() == 2  # two fixture people have not debuted
