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
    failed = [r["name"] for r in checks.run_checks(df, expected) if r["status"] == "fail"]
    assert failed == []
