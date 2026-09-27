"""Numbers behind the README's findings, from data/processed/draft_outcomes.parquet.

Run: uv run python scripts/readme_findings.py

Uses the app's own metric definitions (app/lib/metrics.py) with the app defaults:
outcome-eligible (final-draft, 2012-2019 classes) signed players. Also prints each group's
slot-adjusted MLB rate (mean mlb_minus_exp: how much more often the group reached MLB than
players picked in the same slots) and its outcome-tier mix.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from lib import fmt  # noqa: E402
from lib.metrics import Z90, OutcomeRules, metric_stat  # noqa: E402

RULES = OutcomeRules()  # signed players only, hit = 5+ WAR
TIERS = ["Didn't sign", "Never reached MLB", "Cup of coffee", "Role player", "Regular", "Star"]


def row(df: pd.DataFrame, label: str) -> dict:
    mlb = metric_stat(df, "mlb_pct", RULES)
    return {
        "group": label,
        "players": mlb.n,
        "mlb_pct": fmt.pct(mlb.value),
        "war_per_player": fmt.war(metric_stat(df, "war_per_player", RULES).value),
        "median_years_to_debut": fmt.years(metric_stat(df, "years_to_debut", RULES).value),
    }


def slot_adjusted(df: pd.DataFrame, label: str) -> dict:
    """Mean observed-minus-expected MLB rate in points, with a 90% interval."""
    diff = 100 * df["mlb_minus_exp"].dropna()  # set on signed outcome-eligible rows only
    half = Z90 * diff.std() / len(diff) ** 0.5
    return {
        "group": label,
        "players": len(diff),
        "mlb_vs_slot_pts": f"{diff.mean():+.1f}",
        "90% interval": f"{diff.mean() - half:+.1f} to {diff.mean() + half:+.1f}",
    }


def tier_mix(df: pd.DataFrame, label: str) -> dict:
    """Share of each outcome tier among 2012-2019 picks (all picks, signed or not)."""
    tiers = df.loc[df["draft_year"] <= 2019, "outcome_tier"]
    shares = tiers.value_counts(normalize=True).reindex(TIERS, fill_value=0)
    return {"group": label, "picks": len(tiers), **{t: fmt.pct(v) for t, v in shares.items()}}


def main() -> None:
    df = pd.read_parquet(ROOT / "data" / "processed" / "draft_outcomes.parquet")
    groups = {
        "All draftees": df,
        "Picks 1-10": df[df["slot_band"] == "1–10"],
        "Picks 301+": df[df["slot_band"] == "301+"],
        "Southeastern (SEC)": df[df["conference_group"] == "Southeastern"],
        "High school": df[df["school_type"] == "High school"],
        "4-year college": df[df["school_type"] == "4-year college"],
    }
    sections = {
        "1. MLB rate by draft slot": ["All draftees", "Picks 1-10", "Picks 301+"],
        "2. SEC vs all draftees": ["All draftees", "Southeastern (SEC)"],
        "3. High school vs 4-year college": ["High school", "4-year college"],
    }
    print("Outcome-eligible signed players, 2012-2019 draft classes")
    for title, labels in sections.items():
        print(f"\n{title}")
        print(pd.DataFrame([row(groups[g], g) for g in labels]).to_string(index=False))

    print("\nSlot-adjusted MLB rate: points above players picked in the same slots (signed)")
    print(pd.DataFrame([slot_adjusted(d, g) for g, d in groups.items()]).to_string(index=False))

    print("\nOutcome tiers, all 2012-2019 picks (a non-final or unsigned pick is Didn't sign)")
    print(pd.DataFrame([tier_mix(d, g) for g, d in groups.items()]).to_string(index=False))


if __name__ == "__main__":
    main()
