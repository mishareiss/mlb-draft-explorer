import math

import pandas as pd
import pytest
from conftest import FIXTURES

from ingest import pull_bbref_draft
from ingest.build_bonus_backfill import build_backfill, crosscheck, normalize_name
from ingest.http import RateLimitedError
from ingest.pull_bbref_draft import parse_round_page


@pytest.fixture
def page() -> str:
    return (FIXTURES / "bbref_draft_2014_r01_sample.html").read_text()


@pytest.fixture
def parsed(page) -> pd.DataFrame:
    return parse_round_page(page, 2014).set_index("overall_pick")


def test_parse_row_count_and_columns(parsed):
    assert parsed.index.tolist() == [1, 2, 3, 34, 35, 41]
    assert set(pull_bbref_draft.COLUMNS) - {"overall_pick"} <= set(parsed.columns)
    assert (parsed["draft_year"] == 2014).all()


def test_parse_bonus_and_signed(parsed):
    assert parsed.loc[3, "bonus_usd"] == 6_582_000.0
    assert parsed.loc[2, "bonus_usd"] == 6_000_000.0
    assert math.isnan(parsed.loc[1, "bonus_usd"])  # Brady Aiken: unsigned, blank bonus
    assert not parsed.loc[1, "signed"]
    assert bool(parsed.loc[3, "signed"]) is True
    assert parsed["signed"].dtype == "boolean"


def test_parse_supplemental_pick_kept(parsed):
    # 2014 CB-A picks (35-41) are listed on the round-1 page, with Rnd = 1
    assert parsed.loc[35, "name"] == "Forrest Wall"
    assert parsed.loc[41, "round_pick"] == 41


def test_parse_names_text_and_links(parsed):
    assert parsed.loc[3, "name"] == "Carlos Rodón"  # accent kept, "(minors)" stripped
    assert parsed.loc[3, "drafted_out_of"] == "North Carolina State University (Raleigh, NC)"
    assert parsed.loc[3, "from_type"] == "4Yr"
    assert parsed.loc[3, "bbref_player_url"].startswith("https://www.baseball-reference.com/")
    assert parsed.loc[1, "team"] == "Astros"


def test_parse_table_inside_html_comment(page):
    start = page.index("<table")
    end = page.index("</table>") + len("</table>")
    hidden = page[:start] + "<!--" + page[start:end] + "-->" + page[end:]
    assert len(parse_round_page(hidden, 2014)) == 6


def test_parse_page_without_table_is_empty():
    assert parse_round_page("<html><body>No results</body></html>", 2014).empty


def test_pull_stops_on_rate_limit(monkeypatch, tmp_path):
    monkeypatch.setattr(pull_bbref_draft.paths, "RAW", tmp_path)

    def limited(*_, **__):
        raise RateLimitedError("HTTP 429 ... wait an hour")

    monkeypatch.setattr(pull_bbref_draft, "fetch_text_cached", limited)
    with pytest.raises(SystemExit, match="wait an hour"):
        pull_bbref_draft.main(["--years", "2014", "--rounds", "1"])


# --- backfill join -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("José Ramírez Jr.", "jose ramirez"),
        ("A.J. Reed", "aj reed"),
        ("Ke'Bryan Hayes", "kebryan hayes"),
        ("Vladimir Guerrero III", "vladimir guerrero"),
        (None, ""),
    ],
)
def test_normalize_name(raw, expected):
    assert normalize_name(raw) == expected


def mlb_picks() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "draft_year": [2014, 2014, 2014, 2014],
            "pick_number": [1, 2, 3, 35],
            "person_id": [11, 12, 13, 14],
            "person_full_name": ["Brady Aiken", "Tyler Kolek", "Carlos Rodon", "Somebody Else"],
            "person_first_name": ["Brady", "Tyler", "Carlos", "Somebody"],
            "person_use_name": ["Brady", "Tyler", "Carlos", "Somebody"],
            "person_last_name": ["Aiken", "Kolek", "Rodon", "Else"],
            "signing_bonus_usd": [float("nan")] * 4,
        }
    )


def test_backfill_joins_on_year_and_pick(page):
    bbref = parse_round_page(page, 2014)
    bf = build_backfill(mlb_picks(), bbref).set_index("pick_number")
    assert len(bf) == 4  # one row per MLB pick
    assert bf.loc[3, "person_id"] == 13
    assert bf.loc[3, "bbref_bonus_usd"] == 6_582_000.0
    assert bf.loc[3, "name_match_score"] == 100  # accent-insensitive
    assert not bf.loc[3, "name_mismatch"]
    assert bf.loc[2, "bbref_drafted_out_of"] == "Shepherd HS (Shepherd, TX)"
    assert math.isnan(bf.loc[1, "bbref_bonus_usd"]) and not bf.loc[1, "bbref_signed"]


def test_backfill_flags_name_mismatch_and_drops_bonus(page):
    bbref = parse_round_page(page, 2014)
    bf = build_backfill(mlb_picks(), bbref).set_index("pick_number")
    assert bf.loc[35, "name_mismatch"]  # MLB "Somebody Else" vs bbref "Forrest Wall"
    assert bf.loc[35, "name_match_score"] < 85
    assert math.isnan(bf.loc[35, "bbref_bonus_usd"])
    assert pd.isna(bf.loc[35, "bbref_signed"])


def test_same_last_name_initial_is_diagnostic_only():
    from ingest.build_bonus_backfill import same_last_name_initial

    assert same_last_name_initial("Mike Mason", "Michael Mason")
    assert not same_last_name_initial("Forrest Wall", "Somebody Else")
    assert not same_last_name_initial(None, "Somebody Else")


def test_backfill_uses_nickname_variant():
    picks = (
        mlb_picks().iloc[[0]].assign(person_full_name="Bradley Aiken", person_first_name="Bradley")
    )
    bbref = pd.DataFrame(
        {
            "draft_year": [2014],
            "overall_pick": [1],
            "signed": [True],
            "bonus_usd": [1.0],
            "drafted_out_of": [""],
            "name": ["Brady Aiken"],
            "from_type": ["HS"],
            "bbref_player_url": [None],
        }
    )
    assert not build_backfill(picks, bbref)["name_mismatch"].item()  # matched via use_name


def test_crosscheck_counts():
    bf = pd.DataFrame(
        {
            "draft_year": [2017] * 3,
            "pick_number": [1, 2, 3],
            "mlb_name": ["a", "b", "c"],
            "bbref_bonus_usd": [100.0, 1005.0, 500.0],
        }
    )
    picks = pd.DataFrame(
        {
            "draft_year": [2017] * 3,
            "pick_number": [1, 2, 3],
            "signing_bonus_usd": [100.0, 1000, 900],
        }
    )
    cc = crosscheck(bf, picks)
    assert cc["n"] == 3
    assert cc["exact_pct"] == pytest.approx(33.3)
    assert cc["within_1pct_pct"] == pytest.approx(66.7)
    assert cc["top"].loc[0, "pick_number"] == 3
