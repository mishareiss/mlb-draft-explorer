"""Run the real models/*.sql on the handcrafted fixtures in tests/fixtures/models/."""

import duckdb
import pandas as pd
import pytest
from conftest import FIXTURES

from transform import run

MODEL_FIXTURES = FIXTURES / "models"


@pytest.fixture(scope="module")
def out() -> pd.DataFrame:
    con = run.build(MODEL_FIXTURES / "interim", MODEL_FIXTURES / "reference")
    return con.execute("select * from draft_outcomes").df()


def row(out: pd.DataFrame, year: int, pick: int) -> pd.Series:
    got = out[(out["draft_year"] == year) & (out["pick_number"] == pick)]
    assert len(got) == 1
    return got.iloc[0]


def test_one_row_per_pick(out):
    assert len(out) == 15
    assert not out.duplicated(["draft_year", "pick_number"]).any()


# --- final draft and signing ------------------------------------------------------------


def test_redrafted_player_outcomes_only_on_final_row(out):
    first, final = row(out, 2014, 400), row(out, 2017, 150)
    assert not first["is_final_draft"] and final["is_final_draft"]
    assert not first["signed"] and first["bonus_band"] == "Unsigned"
    assert pd.isna(first["reached_mlb"])
    assert pd.isna(first["career_war"]) and pd.isna(first["years_to_debut"])
    assert final["signed"] and final["reached_mlb"]
    assert final["years_to_debut"] == 2.1  # 2017-06-12 -> 2019-07-01
    assert out.loc[out["person_id"] == 1001, "career_war"].notna().sum() == 1


def test_outcome_eligible(out):
    assert row(out, 2017, 150)["outcome_eligible"]
    assert not row(out, 2014, 400)["outcome_eligible"]  # not the final draft
    assert not row(out, 2024, 20)["outcome_eligible"]  # class too young


# --- bonus ----------------------------------------------------------------------------------


def test_mlb_zero_bonus_and_slot_are_missing(out):
    r = row(out, 2018, 1100)
    assert pd.isna(r["bonus_usd"]) and pd.isna(r["bonus_source"])
    assert pd.isna(r["slot_value_usd"]) and pd.isna(r["bonus_vs_slot"])


def test_2017_missing_mlb_bonus_falls_back_to_bbref(out):
    r = row(out, 2017, 700)
    assert r["bonus_usd"] == 150000 and r["bonus_source"] == "bbref"


def test_2017_mlb_bonus_wins(out):
    r = row(out, 2017, 150)
    assert r["bonus_usd"] == 300000 and r["bonus_source"] == "mlb"
    assert r["bonus_vs_slot"] == pytest.approx(300000 / 310000)
    assert r["bonus_vs_slot_band"] == "at slot"  # 0.968 is within 0.95-1.05


def test_nickname_mismatch_is_accepted(out):
    r = row(out, 2013, 738)  # Michael Mason ~ Mike Mason
    assert r["bonus_usd"] == 50000 and r["bonus_source"] == "bbref" and r["signed"]


def test_real_name_mismatch_is_rejected(out):
    r = row(out, 2013, 900)  # John Smith vs Pedro Alvarez
    assert pd.isna(r["bonus_usd"]) and not r["signed"]
    assert r["school_type"] == "4-year college"  # the rejected row's from_type HS is ignored


def test_125k_bonus_is_kept(out):
    r = row(out, 2019, 330)
    assert r["bonus_usd"] == 125000 and r["bonus_source"] == "mlb"
    assert r["bonus_band"] == "$100k–$500k"


def test_bonus_band_edges(out):
    assert row(out, 2015, 60)["bonus_band"] == "$100k–$500k"  # exactly $100k
    assert row(out, 2024, 20)["bonus_band"] == "$3M+"  # exactly $3M
    assert row(out, 2016, 500)["bonus_band"] == "Unsigned"
    assert row(out, 2025, 11)["bonus_vs_slot_band"] == "under slot"
    assert row(out, 2018, 50)["bonus_vs_slot_band"] == "over slot"


# --- school ---------------------------------------------------------------------------------


def test_conference_switch_by_draft_year(out):
    early, late = row(out, 2024, 20), row(out, 2025, 11)
    assert early["school"] == late["school"] == "University of Oregon"
    assert early["conference"] == "Pac-12" and late["conference"] == "Big Ten"
    assert late["conference_group"] == "Big Ten"


def test_high_school_detection(out):
    for year, pick in [(2025, 10), (2018, 50), (2015, 60), (2014, 400)]:  # name, class, bbref
        r = row(out, year, pick)
        assert r["school_type"] == "High school" and r["conference_group"] == "High school"
        assert r["school"] == r["school_name_raw"] and pd.isna(r["conference"])


def test_conference_groups(out):
    assert row(out, 2016, 500)["conference_group"] == "Junior college"
    assert row(out, 2016, 500)["school"] == "Cypress College"
    assert row(out, 2019, 330)["conference_group"] == "Other 4-year"
    assert row(out, 2013, 738)["conference_group"] == "The American"
    for year, pick in [(2021, 400), (2012, 40)]:  # 'No School', a name not in schools.csv
        r = row(out, year, pick)
        assert r["school_type"] == "Unknown" and r["conference_group"] == "Unknown"


# --- player dimensions ----------------------------------------------------------------------


def test_position_groups(out):
    assert row(out, 2024, 20)["position_group"] == "LHP"
    assert row(out, 2017, 150)["position_group"] == "RHP"
    assert row(out, 2025, 10)["position_group"] == "OF"  # CF
    assert row(out, 2025, 10)["position"] == "CF"
    assert row(out, 2018, 50)["position_group"] == "1B/3B"
    assert row(out, 2025, 11)["position_group"] == "2B/SS"
    assert row(out, 2019, 330)["position_group"] == "Other"  # DH


def test_age_at_draft_uses_draft_dates(out):
    day_before = row(out, 2024, 20)  # born 2003-07-15, draft 2024-07-14
    assert day_before["draft_start_date"] == pd.Timestamp("2024-07-14")
    assert day_before["age_at_draft"] == 20.9 and day_before["age_band"] == "20"
    birthday = row(out, 2025, 11)  # born 2004-07-13, draft 2025-07-13
    assert birthday["age_at_draft"] == 21.0 and birthday["age_band"] == "21"
    assert row(out, 2025, 10)["age_band"] == "≤18"
    assert row(out, 2013, 738)["age_band"] == "21"


def test_slot_and_round_band_edges(out):
    assert row(out, 2025, 10)["slot_band"] == "1–10"
    assert row(out, 2025, 11)["slot_band"] == "11–30"
    assert row(out, 2012, 40)["round_band"] == "Supplemental"
    assert row(out, 2019, 330)["round_band"] == "11–20"
    assert row(out, 2017, 150)["round_band"] == "1–5"


# --- outcomes -------------------------------------------------------------------------------


def test_career_war_sums_bat_and_pitch(out):
    assert row(out, 2017, 150)["career_war"] == pytest.approx(0.5 + 1.3 + 1.0)
    assert row(out, 2024, 20)["career_war"] == pytest.approx(0.75)  # pitching only


def test_career_war_excludes_seasons_after_2026(out):
    assert row(out, 2012, 40)["career_war"] == pytest.approx(1.5)


def test_non_debuted_player_gets_zero_war(out):
    r = row(out, 2025, 11)
    assert not r["reached_mlb"] and r["career_war"] == 0.0 and pd.isna(r["years_to_debut"])


# --- outcome tiers (models/08 on a synthetic draft_outcomes) --------------------------------


@pytest.fixture(scope="module")
def tiers() -> pd.DataFrame:
    rows = [  # draft_year, pick, is_final_draft, signed, reached_mlb, career_war
        (2015, 1, True, True, True, 0.99),
        (2015, 2, True, True, True, 1.0),
        (2015, 3, True, True, True, 4.99),
        (2015, 4, True, True, True, 5.0),
        (2015, 5, True, True, True, 15.0),
        (2015, 6, False, False, None, None),  # drafted again later
        (2016, 7, True, True, False, 0.0),
        (2017, 8, True, False, False, 0.0),
        (2021, 9, True, True, True, 20.0),
    ]
    con = duckdb.connect()
    con.execute(
        "create table draft_outcomes (draft_year int, pick_number int, is_final_draft bool, "
        "signed bool, reached_mlb bool, career_war double, outcome_eligible bool)"
    )
    for r in rows:
        eligible = r[2] and 2012 <= r[0] <= 2019
        con.execute("insert into draft_outcomes values (?, ?, ?, ?, ?, ?, ?)", [*r, eligible])
    con.execute((run.MODELS / "08_outcome_tiers.sql").read_text())
    return con.execute("select * from draft_outcomes").df().set_index("pick_number")


@pytest.mark.parametrize(
    ("pick", "tier", "order"),
    [
        (1, "Cup of coffee", 2),
        (2, "Role player", 3),
        (3, "Role player", 3),
        (4, "Regular", 4),
        (5, "Star", 5),
        (6, "Didn't sign", 0),
        (7, "Never reached MLB", 1),
        (8, "Didn't sign", 0),
    ],
)
def test_outcome_tier_boundaries(tiers, pick, tier, order):
    assert tiers.loc[pick, "outcome_tier"] == tier
    assert tiers.loc[pick, "outcome_tier_order"] == order


def test_2020_plus_has_no_tier(tiers):
    assert pd.isna(tiers.loc[9, "outcome_tier"]) and pd.isna(tiers.loc[9, "outcome_tier_order"])
    assert pd.isna(tiers.loc[9, "became_regular"])


def test_became_regular_only_on_eligible_rows(tiers):
    assert tiers.loc[4, "became_regular"] and not tiers.loc[3, "became_regular"]
    assert not tiers.loc[8, "became_regular"]  # eligible but unsigned: False, not null
    assert pd.isna(tiers.loc[6, "became_regular"])  # non-final


def test_fixture_has_slot_columns(out):
    for col in ["exp_mlb_signed", "exp_mlb_all", "exp_regular_signed", "exp_regular_all"]:
        assert out[col].between(0, 1).all()
    assert pd.isna(row(out, 2014, 400)["mlb_minus_exp"])  # non-final
    assert pd.isna(row(out, 2024, 20)["mlb_minus_exp"])  # 2020+
