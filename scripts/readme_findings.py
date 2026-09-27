"""Numbers behind the README's findings, from data/processed/draft_outcomes.parquet.

Run: uv run python scripts/readme_findings.py

Uses the app's own metric definitions (app/lib/metrics.py) with the app defaults:
outcome-eligible (final-draft, 2012-2019 classes) signed players.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from lib import fmt  # noqa: E402
from lib.metrics import OutcomeRules, metric_stat  # noqa: E402

RULES = OutcomeRules()  # signed players only, hit = 5+ WAR


def row(df: pd.DataFrame, label: str) -> dict:
    mlb = metric_stat(df, "mlb_pct", RULES)
    return {
        "group": label,
        "players": mlb.n,
        "mlb_pct": fmt.pct(mlb.value),
        "war_per_player": fmt.war(metric_stat(df, "war_per_player", RULES).value),
        "median_years_to_debut": fmt.years(metric_stat(df, "years_to_debut", RULES).value),
    }


def main() -> None:
    df = pd.read_parquet(ROOT / "data" / "processed" / "draft_outcomes.parquet")
    sections = {
        "1. MLB rate by draft slot": [
            row(df, "All draftees"),
            row(df[df["slot_band"] == "1–10"], "Picks 1-10"),
            row(df[df["slot_band"] == "301+"], "Picks 301+"),
        ],
        "2. SEC vs all draftees": [
            row(df, "All draftees"),
            row(df[df["conference_group"] == "Southeastern"], "Southeastern (SEC)"),
        ],
        "3. High school vs 4-year college": [
            row(df[df["school_type"] == "High school"], "High school"),
            row(df[df["school_type"] == "4-year college"], "4-year college"),
        ],
    }
    print("Outcome-eligible signed players, 2012-2019 draft classes")
    for title, rows in sections.items():
        print(f"\n{title}")
        print(pd.DataFrame(rows).to_string(index=False))


if __name__ == "__main__":
    main()
