import copy
import math

import pytest

from ingest.pull_draft import flatten_draft, parse_bonus, parse_years, to_snake


def test_flatten_one_row_per_pick(draft_payload):
    n_picks = sum(len(r["picks"]) for r in draft_payload["drafts"]["rounds"])
    df = flatten_draft(draft_payload, 2023)
    assert len(df) == n_picks == 4
    assert (df["draft_year"] == 2023).all()
    assert df["person_id"].is_unique
    # nested fields are kept, with snake_case names
    for col in ("school_school_class", "person_primary_position_abbreviation", "signing_bonus"):
        assert col in df.columns


def test_signing_bonus_parsed(draft_payload):
    df = flatten_draft(draft_payload, 2023).set_index("person_full_name")
    assert df.loc["Paul Skenes", "signing_bonus_usd"] == 9_200_000.0
    assert math.isnan(df.loc["Caden Kendle", "signing_bonus_usd"])
    assert df["signing_bonus_usd"].dtype == "float64"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (1250000, 1_250_000.0),
        (1250000.0, 1_250_000.0),
        ("9200000", 9_200_000.0),
        ("$1,250,000", 1_250_000.0),
        (" $3,000 ", 3_000.0),
    ],
)
def test_parse_bonus_values(raw, expected):
    assert parse_bonus(raw) == expected


@pytest.mark.parametrize("raw", [None, "", "n/a"])
def test_parse_bonus_missing(raw):
    assert math.isnan(parse_bonus(raw))


def test_pick_missing_optional_nested_fields(draft_payload):
    payload = copy.deepcopy(draft_payload)
    pick = payload["drafts"]["rounds"][0]["picks"][0]
    for key in ("school", "home", "signingBonus", "pickValue", "blurb"):
        pick.pop(key, None)
    pick["person"].pop("primaryPosition")
    df = flatten_draft(payload, 2023)
    assert len(df) == 4
    assert math.isnan(df.loc[df["person_id"] == pick["person"]["id"], "signing_bonus_usd"].item())


def test_bonus_column_absent_entirely(draft_payload):
    payload = copy.deepcopy(draft_payload)
    for rnd in payload["drafts"]["rounds"]:
        for pick in rnd["picks"]:
            pick.pop("signingBonus", None)
    df = flatten_draft(payload, 2012)
    assert df["signing_bonus_usd"].isna().all()


def test_helpers():
    assert to_snake("school.schoolClass") == "school_school_class"
    assert to_snake("person.mlbDebutDate") == "person_mlb_debut_date"
    assert parse_years("2012-2014") == [2012, 2013, 2014]
    assert parse_years("2020") == [2020]
