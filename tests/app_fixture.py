"""A 40-row draft_outcomes frame for app tests, with hand-countable outcomes.

2015 class (outcome-eligible when final):
  Alpha U     (Southeastern, 4-year)  10 picks: 8 signed, 2 unsigned; 4 reached MLB,
                                      WAR 10, 6, 1, 0.5
  Beta State  (Big West, 4-year)      10 picks, all signed; 2 reached MLB, WAR 2, 0.3
  Gamma HS    (High school)            6 picks: 4 final and signed (1 reached MLB, WAR 7),
                                      2 non-final (drafted again later, so not eligible)
  Delta CC    (Junior college)         4 picks, all signed, none reached MLB
2022 class (not outcome-eligible):     5 Alpha U + 5 Delta CC, all signed; one Alpha U
                                      player already debuted (WAR 1) and must be ignored

Eligible signed players: 8 + 10 + 4 + 4 = 26, of whom 7 reached MLB and 3 have 5+ WAR.
Counting unsigned picks: 28 players, still 7 reached MLB.
"""

from __future__ import annotations

import datetime as dt

import pandas as pd

GROUPS = {
    "Alpha U": ("4-year college", "D1", "Southeastern", "Southeastern"),
    "Beta State": ("4-year college", "D1", "Big West", "Big West"),
    "Gamma HS": ("High school", None, None, "High school"),
    "Delta CC": ("Junior college", "JUCO", None, "Junior college"),
}
POSITIONS = [("P", "R", "RHP"), ("P", "L", "LHP"), ("C", "R", "C"), ("CF", "R", "OF")]
AGE_BANDS = ["21", "22", "≤18", "20"]

# (year, school, signed, final, career WAR if reached MLB else None)
SPEC = (
    [(2015, "Alpha U", True, True, w) for w in (10.0, 6.0, 1.0, 0.5)]
    + [(2015, "Alpha U", True, True, None)] * 4
    + [(2015, "Alpha U", False, True, None)] * 2
    + [(2015, "Beta State", True, True, w) for w in (2.0, 0.3)]
    + [(2015, "Beta State", True, True, None)] * 8
    + [(2015, "Gamma HS", True, True, 7.0)]
    + [(2015, "Gamma HS", True, True, None)] * 3
    + [(2015, "Gamma HS", False, False, None)] * 2
    + [(2015, "Delta CC", True, True, None)] * 4
    + [(2022, "Alpha U", True, True, 1.0)]
    + [(2022, "Alpha U", True, True, None)] * 4
    + [(2022, "Delta CC", True, True, None)] * 5
)


def _slot_band(pick: int) -> str:
    return "1–10" if pick <= 10 else "11–30" if pick <= 30 else "31–100"


def _bonus_band(signed: bool, bonus: float | None) -> str:
    if not signed:
        return "Unsigned"
    if bonus is None:
        return "Unknown"
    return "$1M–$3M" if bonus >= 1_000_000 else "$100k–$500k"


def make_outcomes() -> pd.DataFrame:
    rows = []
    picks: dict[int, int] = {}
    for i, (year, school, signed, final, war) in enumerate(SPEC):
        pick = picks[year] = picks.get(year, 0) + 1
        school_type, division, conference, conference_group = GROUPS[school]
        position, hand, position_group = POSITIONS[i % len(POSITIONS)]
        draft_date = dt.date(year, 6, 5)
        reached = war is not None
        bonus = (2_000_000.0 if pick <= 5 else 300_000.0) if signed else None
        rows.append(
            {
                "draft_year": year,
                "pick_number": pick,
                "round_label": "1" if pick <= 30 else "2",
                "round_number": 1.0 if pick <= 30 else 2.0,
                "team_name": "Test Club",
                "person_id": 1000 + i,
                "player_name": f"Player {i:02d}",
                "school_name_raw": school,
                "birth_date": dt.date(year - 21, 1, 1),
                "draft_start_date": draft_date,
                "age_at_draft": 21.4,
                "age_band": AGE_BANDS[i % len(AGE_BANDS)],
                "position": position,
                "pitch_hand": hand,
                "position_group": position_group,
                "slot_band": _slot_band(pick),
                "round_band": "1–5",
                "school_type": school_type,
                "school": school,
                "division": division,
                "conference": conference,
                "conference_group": conference_group,
                "bonus_usd": bonus,
                "bonus_source": "mlb" if bonus is not None else None,
                "bonus_band": _bonus_band(signed, bonus),
                "slot_value_usd": 500_000.0,
                "bonus_vs_slot": None if bonus is None else bonus / 500_000,
                "bonus_vs_slot_band": None,
                "is_final_draft": final,
                "signed": signed,
                "mlb_debut_date": dt.date(year + 3, 7, 1) if reached else None,
                "reached_mlb": reached if final else None,
                "years_to_debut": 3.1 if reached else None,
                "career_war": (war if reached else 0.0) if final else None,
                "outcome_eligible": final and year <= 2019,
            }
        )
    return pd.DataFrame(rows)
