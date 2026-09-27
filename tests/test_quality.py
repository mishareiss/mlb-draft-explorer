"""Quality checks: each fails on a deliberately broken input; the committed output passes."""

import json

import pandas as pd
import pytest
from conftest import FIXTURES

from ingest import paths
from quality import checks
from transform import run

MODEL_FIXTURES = FIXTURES / "models"


@pytest.fixture(scope="module")
def good() -> pd.DataFrame:
    con = run.build(MODEL_FIXTURES / "interim", MODEL_FIXTURES / "reference")
    return con.execute("select * from draft_outcomes").df()


def by_name(results: list[dict]) -> dict[str, dict]:
    return {r["name"]: r for r in results}


def test_fixture_output_has_no_fail(good):
    results = by_name(checks.run_checks(good, expected_rows=len(good)))
    # the fixture spans only a few picks per year, so max-round completeness cannot pass
    failed = {n for n, r in results.items() if r["status"] == "fail"}
    assert failed == {"years_present", "max_round_by_year"}


def test_check_result_shape(good):
    for r in checks.run_checks(good, expected_rows=len(good)):
        assert {"name", "category", "status", "value", "threshold", "detail"} <= r.keys()
        assert r["status"] in {"pass", "warn", "fail"}


def test_duplicate_pick_fails(good):
    broken = pd.concat([good, good.iloc[[0]]], ignore_index=True)
    assert checks.check_unique_picks(broken)["status"] == "fail"
    assert checks.check_unique_picks(good)["status"] == "pass"


def test_lost_row_fails(good):
    assert checks.check_row_count(good.iloc[1:], expected_rows=len(good))["status"] == "fail"
    assert checks.check_row_count(good, expected_rows=len(good))["status"] == "pass"


def test_signed_non_final_row_fails(good):
    broken = good.copy()
    broken.loc[~broken["is_final_draft"], "signed"] = True
    result = checks.check_signed_non_final(broken)
    assert result["status"] == "fail" and result["examples"]
    assert checks.check_signed_non_final(good)["status"] == "pass"


def test_two_final_rows_for_one_person_fails(good):
    broken = good.copy()
    broken["is_final_draft"] = True
    assert checks.check_one_final_draft(broken)["status"] == "fail"
    assert checks.check_one_final_draft(good)["status"] == "pass"


def test_debuted_but_unsigned_fails(good):
    broken = good.copy()
    broken.loc[broken["reached_mlb"].fillna(False).astype(bool), "signed"] = False
    assert checks.check_debuted_signed(broken)["status"] == "fail"


def test_missing_war_match_fails(good):
    broken = good.copy()
    broken.loc[broken["reached_mlb"].fillna(False).astype(bool), "career_war"] = None
    assert checks.check_war_join(broken)["status"] == "fail"


def test_missing_birth_dates_fail(good):
    broken = good.copy()
    broken.loc[broken.index[:3], "birth_date"] = None
    assert checks.check_people_join(broken)["status"] == "fail"


def test_out_of_range_age_warns_with_examples(good):
    broken = good.copy()
    broken.loc[broken.index[0], "age_at_draft"] = 30.0
    result = checks.check_age_range(broken)
    assert result["status"] == "warn" and len(result["examples"]) == 1


def test_missing_expectation_fails(good):
    broken = good.copy()
    broken.loc[broken.index[0], "exp_mlb_all"] = None
    assert checks.check_slot_expectation_complete(broken)["status"] == "fail"
    out_of_range = good.copy()
    out_of_range.loc[out_of_range.index[0], "exp_regular_signed"] = 1.2
    assert checks.check_slot_expectation_complete(out_of_range)["status"] == "fail"
    assert checks.check_slot_expectation_complete(good)["status"] == "pass"


def test_rising_curve_fails():
    curve = pd.DataFrame({"pick_number": range(1, 6)})
    for col in checks.EXP_COLS:
        curve[col] = [0.5, 0.4, 0.3, 0.2, 0.1]
    assert checks.check_slot_curve_monotone(curve)["status"] == "pass"
    curve.loc[3, "exp_mlb_signed"] = 0.32  # a 2-point rise from pick 3 to pick 4
    result = checks.check_slot_curve_monotone(curve)
    assert result["status"] == "fail"
    assert result["examples"] == [{"curve": "exp_mlb_signed", "pick_number": 4, "rise_pts": 2.0}]


def test_miscalibrated_decile_warns():
    ok = {"decile": 1, "n": 700, "expected": 0.20, "observed": 0.21}
    off = {"decile": 2, "n": 700, "expected": 0.20, "observed": 0.30}
    assert checks.check_slot_model_calibrated([ok])["status"] == "pass"
    result = checks.check_slot_model_calibrated([ok, off])
    assert result["status"] == "warn" and result["value"] == 1


def test_missing_tier_fails(good):
    broken = good.copy()
    broken.loc[broken["draft_year"] == 2016, "outcome_tier"] = None
    assert checks.check_outcome_tiers_complete(broken)["status"] == "fail"
    late = good.copy()
    late.loc[late["draft_year"] == 2024, "outcome_tier"] = "Star"
    assert checks.check_outcome_tiers_complete(late)["status"] == "fail"
    assert checks.check_outcome_tiers_complete(good)["status"] == "pass"


def test_expected_max_round():
    assert [checks.expected_max_round(y) for y in (2012, 2019, 2020, 2021, 2025)] == [
        40,
        40,
        5,
        20,
        20,
    ]


@pytest.mark.skipif(
    not (paths.PROCESSED / "draft_outcomes.parquet").exists(), reason="no processed data"
)
def test_processed_data_has_no_fail():
    df = pd.read_parquet(paths.PROCESSED / "draft_outcomes.parquet")
    picks = paths.INTERIM / "draft_picks.parquet"
    if picks.exists():
        expected = len(pd.read_parquet(picks, columns=["draft_year"]))
    else:  # CI: interim data is not committed; use the count the committed report checked
        report = json.loads((paths.PROCESSED / "quality_report.json").read_text())
        expected = by_name(report["checks"])["row_count"]["threshold"]
    curve = pd.read_parquet(checks.CURVE)
    results = checks.run_checks(df, expected, curve)
    failed = [r["name"] for r in results if r["status"] == "fail"]
    assert failed == []
