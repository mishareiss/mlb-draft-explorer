import pandas as pd
import pytest
from conftest import FIXTURES

from ingest import profile
from ingest.pull_draft import flatten_draft
from ingest.pull_people import flatten_people
from ingest.pull_war import load_war

SECTIONS = [
    "# Data profile",
    "## Picks per year",
    "## Draft column completeness",
    "## Key draft fields: % non-null by year",
    "## Signing bonus coverage by round band",
    "## Categorical values",
    "### Sample school names",
    "## People: bio and debut coverage by draft year",
    "## WAR match",
    "## Repeat draftees",
    "## Bonus backfill (Baseball-Reference)",
    "## School reference",
    "## Notes for Task 2",
]


@pytest.fixture
def interim(tmp_path, draft_payload, people_payload, monkeypatch):
    flatten_draft(draft_payload, 2023).to_parquet(tmp_path / "draft_picks.parquet")
    flatten_people(people_payload["people"]).to_parquet(tmp_path / "people.parquet")
    for name in ("war_bat", "war_pitch"):
        pd.read_csv(FIXTURES / f"{name}_sample.csv").to_parquet(tmp_path / f"{name}.parquet")
    return tmp_path


def test_profile_end_to_end(interim, tmp_path):
    out = tmp_path / "DATA_PROFILE.md"
    profile.main(["--interim", str(interim), "--out", str(out), "--reference", str(tmp_path)])
    text = out.read_text()
    for header in SECTIONS:
        assert header in text, header
    assert "| 2023 | 4 | 10 | 1 |" in text  # picks, max numeric round, supplemental picks
    assert "**1 (100.0%)**" in text  # Skenes debuted and is in WAR data


def test_round_band():
    s = pd.Series(["1", "5", "6", "20", "21", "CB-A", "1C"])
    assert profile.round_band(s).tolist() == [
        "1-5",
        "1-5",
        "6-10",
        "11-20",
        "21+",
        "supplemental",
        "supplemental",
    ]


def test_load_war_uses_cache_and_validates(tmp_path, monkeypatch):
    monkeypatch.setattr("ingest.pull_war.paths.RAW", tmp_path)
    (tmp_path / "war").mkdir()
    (tmp_path / "war" / "war_bat.csv").write_text((FIXTURES / "war_bat_sample.csv").read_text())

    def boom(**_):
        raise AssertionError("loader must not run when cached")

    assert "mlb_ID" in load_war("war_bat", boom).columns

    with pytest.raises(RuntimeError, match="mlb_ID"):
        load_war("war_pitch", lambda **_: pd.DataFrame({"html": ["<p>403</p>"]}))


def test_backfill_and_school_sections(tmp_path):
    from ingest import build_school_ref as sr
    from ingest.build_bonus_backfill import build_backfill
    from ingest.pull_bbref_draft import parse_round_page

    bbref = parse_round_page((FIXTURES / "bbref_draft_2014_r01_sample.html").read_text(), 2014)
    picks = bbref.rename(columns={"overall_pick": "pick_number"})[["draft_year", "pick_number"]]
    picks = picks.assign(
        person_id=range(len(picks)),
        person_full_name=bbref["name"].str.replace("ó", "o"),
        pick_round="1",
        signing_bonus_usd=float("nan"),
        school_name=["Cathedral (CA) HS", "Shepherd (TX) HS", "NC State", "x HS", "y HS", "z HS"],
    )
    picks.loc[picks["pick_number"] == 34, "person_full_name"] = "Not Jack Flaherty At All"
    bbref.to_parquet(tmp_path / "bbref_draft.parquet")
    build_backfill(picks, bbref).to_parquet(tmp_path / "bonus_backfill.parquet")
    text = "\n".join(profile.bonus_backfill_section(tmp_path, picks))
    assert "**6 of 6 MLB picks (100.0%)**" in text
    assert "flags **1** joined rows" in text

    schools = pd.DataFrame(
        [["NC State", "North Carolina State University", "4YR", "D1", "Atlantic Coast",
          "Atlantic Coast", "NC", "bbref_type", "wikipedia", False]],
        columns=sr.COLUMNS,
    )  # fmt: skip
    sr.write_schools(schools, tmp_path / "schools.csv")
    text = "\n".join(profile.school_reference_section(tmp_path, picks))
    assert "**1** non-high-school raw names" in text
    assert "**100.0%** of 4YR picks" in text
