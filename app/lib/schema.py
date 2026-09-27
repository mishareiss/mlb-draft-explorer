"""Plain-English labels and category orders for draft_outcomes columns (no Streamlit here)."""

from __future__ import annotations

YEAR_MIN, YEAR_MAX = 2012, 2025
OUTCOME_YEAR_MAX = 2019  # outcome_eligible: final-draft rows from the 2012-2019 classes

SCHOOL_TYPES = ["4-year college", "Junior college", "High school", "Unknown"]
POSITION_GROUPS = ["RHP", "LHP", "C", "1B/3B", "2B/SS", "OF", "Other"]
AGE_BANDS = ["≤18", "19", "20", "21", "22", "23+"]
SLOT_BANDS = ["1–10", "11–30", "31–100", "101–300", "301+"]
BONUS_BANDS = ["$3M+", "$1M–$3M", "$500k–$1M", "$100k–$500k", "<$100k", "Unknown", "Unsigned"]
ROUND_BANDS = ["1–5", "6–10", "11–20", "21+", "Supplemental"]

# Group-by choices for the compare panel: label -> column
GROUP_BY = {
    "Conference group": "conference_group",
    "School": "school",
    "School type": "school_type",
    "Position group": "position_group",
    "Age at draft": "age_band",
    "Draft slot": "slot_band",
    "Bonus band": "bonus_band",
}

# Player table / CSV: column -> readable name, in display order
TABLE_COLUMNS = {
    "draft_year": "Year",
    "pick_number": "Pick",
    "round_label": "Round",
    "player_name": "Player",
    "team_name": "Team",
    "school": "School",
    "school_type": "School type",
    "conference_group": "Conference group",
    "division": "Division",
    "position": "Position",
    "position_group": "Position group",
    "age_at_draft": "Age at draft",
    "bonus_usd": "Bonus",
    "slot_value_usd": "Slot value",
    "signed": "Signed",
    "is_final_draft": "Final draft",
    "reached_mlb": "Reached MLB",
    "mlb_debut_date": "MLB debut",
    "years_to_debut": "Years to debut",
    "career_war": "Career WAR",
}

CHECK_LABELS = {
    "row_count": "Row count matches the source picks",
    "unique_pick": "One row per pick",
    "one_final_draft_per_person": "One final draft per player",
    "years_present": "All draft years present",
    "max_round_by_year": "Expected number of rounds each year",
    "people_join": "Birth date found for every pick",
    "war_join": "WAR found for every MLB player",
    "age_at_draft_range": "Age at draft between 16 and 26",
    "bonus_range": "Bonuses between $0 and $15M",
    "debut_after_draft": "MLB debut comes after the draft",
    "bonus_coverage_rounds_1_10": "Bonus known for rounds 1–10",
    "college_d1_conference_share": "College picks with a D1 conference",
    "unknown_school_type_share": "Picks with an unknown school type",
    "no_signed_non_final": "Only a player's final draft can be signed",
    "debuted_players_signed": "Every MLB player signed",
}


def check_label(name: str) -> str:
    return CHECK_LABELS.get(name, name.replace("_", " ").capitalize())
