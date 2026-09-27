"""Quality checks on data/processed/draft_outcomes.parquet -> data/processed/quality_report.json.

python -m quality.checks

Each check returns {name, category, status, value, threshold, detail, examples}; `examples`
lists up to 20 offending rows. Exits non-zero if any check has status "fail". The report
also carries the tables the app's Data Quality page shows.
"""

from __future__ import annotations

import json
import logging
import sys
from collections.abc import Callable
from typing import Any

import pandas as pd

from ingest import paths
from transform import slot_model

log = logging.getLogger(__name__)

OUTCOMES = paths.PROCESSED / "draft_outcomes.parquet"
REPORT = paths.PROCESSED / "quality_report.json"
CURVE = paths.PROCESSED / "slot_expectation.parquet"
YEARS = range(2012, 2026)
MAX_EXAMPLES = 20
EXAMPLE_COLS = ["draft_year", "pick_number", "player_name"]
EXP_COLS = list(slot_model.CURVES)
TIERS = ["Didn't sign", "Never reached MLB", "Cup of coffee", "Role player", "Regular", "Star"]
TIER_YEARS = (2012, 2019)


def expected_max_round(year: int) -> int:
    return 40 if year <= 2019 else 5 if year == 2020 else 20


def _result(
    name: str,
    category: str,
    status: str,
    value: Any,
    threshold: Any,
    detail: str,
    examples: pd.DataFrame | None = None,
) -> dict:
    rows = [] if examples is None else examples.head(MAX_EXAMPLES).to_dict("records")
    return {
        "name": name,
        "category": category,
        "status": status,
        "value": value,
        "threshold": threshold,
        "detail": detail,
        "examples": rows,
    }


def _pct(mask: pd.Series) -> float:
    return round(100 * float(mask.mean()), 2) if len(mask) else 100.0


def _fail_if_any(name: str, category: str, bad: pd.DataFrame, what: str) -> dict:
    status = "fail" if len(bad) else "pass"
    return _result(name, category, status, len(bad), 0, f"{len(bad)} {what}", bad)


def _warn_if_any(name: str, bad: pd.DataFrame, cols: list[str], what: str) -> dict:
    status = "warn" if len(bad) else "pass"
    return _result(name, "validity", status, len(bad), 0, f"{len(bad)} {what}", bad[cols])


# --- checks ------------------------------------------------------------------------------


def check_row_count(df: pd.DataFrame, expected_rows: int) -> dict:
    status = "pass" if len(df) == expected_rows else "fail"
    return _result(
        "row_count",
        "completeness",
        status,
        len(df),
        expected_rows,
        "draft_outcomes rows vs. draft_picks rows (no rows gained or lost in joins)",
    )


def check_unique_picks(df: pd.DataFrame) -> dict:
    dup = df[df.duplicated(["draft_year", "pick_number"], keep=False)]
    return _fail_if_any(
        "unique_pick", "uniqueness", dup[EXAMPLE_COLS], "rows share a (draft_year, pick_number)"
    )


def check_one_final_draft(df: pd.DataFrame) -> dict:
    finals = df.groupby("person_id")["is_final_draft"].sum()
    bad = finals[finals != 1].rename("final_rows").reset_index()
    return _fail_if_any(
        "one_final_draft_per_person",
        "uniqueness",
        bad,
        "people without exactly one is_final_draft row",
    )


def check_years(df: pd.DataFrame) -> dict:
    missing = sorted(set(YEARS) - set(df["draft_year"].unique()))
    status = "fail" if missing else "pass"
    return _result(
        "years_present",
        "completeness",
        status,
        len(YEARS) - len(missing),
        len(YEARS),
        f"draft years 2012-2025 present; missing: {missing or 'none'}",
    )


def check_max_round(df: pd.DataFrame) -> dict:
    got = df.groupby("draft_year")["round_number"].max()
    bad = pd.DataFrame(
        [
            {
                "draft_year": int(y),
                "max_round": None if pd.isna(r) else int(r),  # NaN: supplemental picks only
                "expected": expected_max_round(int(y)),
            }
            for y, r in got.items()
            if pd.isna(r) or int(r) != expected_max_round(int(y))
        ],
        columns=["draft_year", "max_round", "expected"],
    )
    return _result(
        "max_round_by_year",
        "completeness",
        "fail" if len(bad) else "pass",
        len(bad),
        0,
        "years whose max numeric round is not 40 (2012-2019) / 5 (2020) / 20 (2021+)",
        bad,
    )


def check_people_join(df: pd.DataFrame) -> dict:
    ok = df["birth_date"].notna()
    value = _pct(ok)
    status = "pass" if value == 100 else "warn" if value >= 99 else "fail"
    return _result(
        "people_join",
        "joins",
        status,
        value,
        99.0,
        "% of rows with birth_date (fail below 99%, warn below 100%)",
        df.loc[~ok, EXAMPLE_COLS],
    )


def check_war_join(df: pd.DataFrame) -> dict:
    debuted = df[df["is_final_draft"] & df["reached_mlb"].fillna(False).astype(bool)]
    ok = debuted["career_war"].notna()
    value = _pct(ok)
    return _result(
        "war_join",
        "joins",
        "pass" if value >= 99 else "fail",
        value,
        99.0,
        f"% of {len(debuted):,} debuted players (final-draft rows) with a WAR match",
        debuted.loc[~ok, EXAMPLE_COLS],
    )


def check_age_range(df: pd.DataFrame) -> dict:
    age = df["age_at_draft"]
    bad = df[age.notna() & ~age.between(16, 26)]
    return _warn_if_any(
        "age_at_draft_range", bad, [*EXAMPLE_COLS, "age_at_draft"], "rows outside ages 16-26"
    )


def check_bonus_range(df: pd.DataFrame) -> dict:
    bonus = df["bonus_usd"]
    bad = df[bonus.notna() & ~bonus.between(0, 15_000_000)]
    return _warn_if_any("bonus_range", bad, [*EXAMPLE_COLS, "bonus_usd"], "bonuses outside $0-$15M")


def check_debut_after_draft(df: pd.DataFrame) -> dict:
    debut = pd.to_datetime(df["mlb_debut_date"])
    bad = df[debut.notna() & (debut <= pd.to_datetime(df["draft_start_date"]))]
    return _warn_if_any(
        "debut_after_draft",
        bad,
        [*EXAMPLE_COLS, "draft_start_date", "mlb_debut_date"],
        "rows whose MLB debut is on or before the draft date",
    )


def check_bonus_coverage(df: pd.DataFrame) -> dict:
    top = df[df["round_number"].between(1, 10)]
    by_year = top.groupby("draft_year")["bonus_usd"].agg(lambda s: _pct(s.notna()))
    low = by_year[by_year < 90].rename("pct_with_bonus").reset_index()
    return _result(
        "bonus_coverage_rounds_1_10",
        "coverage",
        "warn" if len(low) else "pass",
        float(by_year.min()) if len(by_year) else None,
        90.0,
        "lowest yearly % of round 1-10 picks with a bonus; years below 90%: "
        f"{low['draft_year'].tolist() or 'none'}",
        low,
    )


def check_d1_conference_share(df: pd.DataFrame) -> dict:
    college = df[df["school_type"].isin(["4-year college", "Junior college"])]
    four_year = college[college["school_type"] == "4-year college"]
    value = _pct(college["conference"].notna())
    return _result(
        "college_d1_conference_share",
        "coverage",
        "pass",
        value,
        None,
        f"% of {len(college):,} college picks (4-year + JC) with a D1 conference; "
        f"{_pct(four_year['conference'].notna())}% of 4-year picks (informational)",
    )


def check_unknown_school_type(df: pd.DataFrame) -> dict:
    unknown = df["school_type"] == "Unknown"
    value = _pct(unknown)
    top = (
        df.loc[unknown, "school_name_raw"]
        .fillna("(null)")
        .value_counts()
        .rename_axis("school_name_raw")
        .rename("picks")
        .reset_index()
    )
    return _result(
        "unknown_school_type_share",
        "coverage",
        "warn" if value > 5 else "pass",
        value,
        5.0,
        "% of all picks with school_type Unknown (warn above 5%); examples are the most common",
        top,
    )


def check_signed_non_final(df: pd.DataFrame) -> dict:
    bad = df[~df["is_final_draft"] & df["signed"]]
    return _fail_if_any(
        "no_signed_non_final", "business_logic", bad[EXAMPLE_COLS], "non-final rows marked signed"
    )


def check_debuted_signed(df: pd.DataFrame) -> dict:
    bad = df[df["reached_mlb"].fillna(False).astype(bool) & ~df["signed"]]
    return _fail_if_any(
        "debuted_players_signed",
        "business_logic",
        bad[EXAMPLE_COLS],
        "debuted players (final-draft rows) not marked signed",
    )


def check_slot_expectation_complete(df: pd.DataFrame) -> dict:
    exp = df[EXP_COLS]
    bad = df[(exp.isna() | (exp < 0) | (exp > 1)).any(axis=1)]
    return _fail_if_any(
        "slot_expectation_complete",
        "model",
        bad[[*EXAMPLE_COLS, *EXP_COLS]],
        "rows missing an exp_* value or with one outside [0, 1]",
    )


def check_slot_curve_monotone(curve: pd.DataFrame) -> dict:
    curve = curve.sort_values("pick_number")
    rises = [  # rise above the lowest value at any earlier pick
        {"curve": col, "pick_number": int(pick), "rise_pts": round(100 * float(rise), 2)}
        for col in EXP_COLS
        for pick, rise in zip(curve["pick_number"], curve[col] - curve[col].cummin(), strict=True)
        if rise > slot_model.MAX_RISE
    ]
    return _fail_if_any(
        "slot_curve_monotone",
        "model",
        pd.DataFrame(rises, columns=["curve", "pick_number", "rise_pts"]),
        f"picks where an expected-by-pick curve is more than {100 * slot_model.MAX_RISE}"
        " points above its value at an earlier pick",
    )


def check_slot_model_calibrated(deciles: list[dict]) -> dict:
    """Leave-one-class-out deciles of exp_mlb_signed whose observed rate is outside the 90%
    Wilson interval around the expected rate."""
    bad = []
    for d in deciles:
        lo, hi = slot_model.wilson_interval(d["expected"], d["n"])
        if not lo <= d["observed"] <= hi:
            bad.append({**d, "interval_low": round(lo, 4), "interval_high": round(hi, 4)})
    return _result(
        "slot_model_calibrated",
        "model",
        "warn" if bad else "pass",
        len(bad),
        0,
        f"of {len(deciles)} leave-one-class-out deciles of exp_mlb_signed, those whose observed"
        " MLB rate is outside the 90% Wilson interval around the expected rate",
        pd.DataFrame(bad),
    )


def check_outcome_tiers_complete(df: pd.DataFrame) -> dict:
    in_years = df["draft_year"].between(*TIER_YEARS)
    tier = df["outcome_tier"]
    bad = df[(in_years & ~tier.isin(TIERS)) | (~in_years & tier.notna())]
    counts = tier[in_years].value_counts()
    return _fail_if_any(
        "outcome_tiers_complete",
        "business_logic",
        bad[[*EXAMPLE_COLS, "outcome_tier"]],
        f"rows with a missing 2012-2019 tier or a 2020+ tier; tier counts sum to "
        f"{int(counts.sum()):,} of {int(in_years.sum()):,} 2012-2019 rows",
    )


CHECKS: list[Callable[[pd.DataFrame], dict]] = [
    check_unique_picks,
    check_one_final_draft,
    check_years,
    check_max_round,
    check_people_join,
    check_war_join,
    check_age_range,
    check_bonus_range,
    check_debut_after_draft,
    check_bonus_coverage,
    check_d1_conference_share,
    check_unknown_school_type,
    check_signed_non_final,
    check_debuted_signed,
    check_slot_expectation_complete,
    check_outcome_tiers_complete,
]


def run_checks(
    df: pd.DataFrame,
    expected_rows: int,
    curve: pd.DataFrame | None = None,
    slot_eval: dict | None = None,
) -> list[dict]:
    """All checks. `curve` defaults to the exp_* values on the rows themselves and
    `slot_eval` to a fresh slot_model.evaluate(df)."""
    if curve is None:
        curve = df.drop_duplicates("pick_number")[["pick_number", *EXP_COLS]]
    if slot_eval is None:
        slot_eval = slot_model.evaluate(df)
    deciles = slot_eval["curves"]["exp_mlb_signed"]["loco_deciles"]
    return [
        check_row_count(df, expected_rows),
        *(check(df) for check in CHECKS),
        check_slot_curve_monotone(curve),
        check_slot_model_calibrated(deciles),
    ]


# --- tables for the Data Quality page ------------------------------------------------------


def bonus_coverage_table(df: pd.DataFrame) -> list[dict]:
    t = (
        df.groupby(["draft_year", "round_band"])
        .agg(picks=("pick_number", "size"), with_bonus=("bonus_usd", "count"))
        .reset_index()
    )
    t["pct_with_bonus"] = (100 * t["with_bonus"] / t["picks"]).round(1)
    return t.to_dict("records")


def school_type_mix_table(df: pd.DataFrame) -> list[dict]:
    t = df.groupby(["draft_year", "school_type"]).size().rename("picks").reset_index()
    t["pct"] = (100 * t["picks"] / t.groupby("draft_year")["picks"].transform("sum")).round(1)
    return t.to_dict("records")


def tier_mix_table(df: pd.DataFrame) -> list[dict]:
    rows = df[df["draft_year"].between(*TIER_YEARS)]
    t = (
        rows.groupby(["draft_year", "outcome_tier_order", "outcome_tier"])
        .size()
        .rename("picks")
        .reset_index()
    )
    t["pct"] = (100 * t["picks"] / t.groupby("draft_year")["picks"].transform("sum")).round(1)
    return t.to_dict("records")


def build_report(df: pd.DataFrame, expected_rows: int, curve: pd.DataFrame | None = None) -> dict:
    slot_eval = slot_model.evaluate(df)
    checks = run_checks(df, expected_rows, curve, slot_eval)
    return {
        "rows": len(df),
        "summary": {s: sum(c["status"] == s for c in checks) for s in ("pass", "warn", "fail")},
        "checks": checks,
        "tables": {
            "bonus_coverage_by_year_round_band": bonus_coverage_table(df),
            "school_type_mix_by_year": school_type_mix_table(df),
            "outcome_tier_mix_by_year": tier_mix_table(df),
            "slot_model": slot_eval,
        },
    }


def _jsonable(obj: Any) -> Any:
    """numpy scalars and dates -> plain JSON values."""
    if hasattr(obj, "item"):
        return obj.item()
    if pd.isna(obj):
        return None
    return str(obj)


def main() -> int:
    df = pd.read_parquet(OUTCOMES)
    expected = len(pd.read_parquet(paths.INTERIM / "draft_picks.parquet", columns=["draft_year"]))
    report = build_report(df, expected, pd.read_parquet(CURVE))
    REPORT.write_text(json.dumps(report, indent=2, default=_jsonable) + "\n")
    for c in report["checks"]:
        log.info(
            "%-5s %-28s value=%s threshold=%s", c["status"], c["name"], c["value"], c["threshold"]
        )
    log.info("wrote %s: %s", REPORT, report["summary"])
    return 1 if report["summary"]["fail"] else 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    sys.exit(main())
