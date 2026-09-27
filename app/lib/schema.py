"""Plain-English labels and category orders for draft_outcomes columns (no Streamlit here)."""

from __future__ import annotations

YEAR_MIN, YEAR_MAX = 2012, 2025
OUTCOME_YEAR_MAX = 2019  # outcome_eligible: final-draft rows from the 2012-2019 classes
PICK_MIN, PICK_MAX = 1, 1238  # overall pick range across all classes (slot_expectation.parquet)
REGULAR_WAR = 5  # "Became a regular": at least this much career WAR (became_regular)

# --- vocabulary: the only words the app uses for these ideas --------------------------------

REACHED = "Reached the majors"
REGULAR = f"Became a regular ({REGULAR_WAR}+ WAR)"
VS_SLOT = "vs. draft slot"
SIGNED_FOR = "Signed for"
PICKED_AT = "Picked at"
DRAFT_CLASS = "Draft class"
ALL_DRAFTEES = "All draftees"

# school_type / conference_group value for picks with no usable school (renamed on load)
NO_SCHOOL = "No school / unclassified"

SCHOOL_TYPES = ["4-year college", "Junior college", "High school", NO_SCHOOL]
POSITION_GROUPS = ["RHP", "LHP", "C", "1B/3B", "2B/SS", "OF", "Other"]
PITCHER_GROUPS = ["RHP", "LHP"]
HITTER_GROUPS = [g for g in POSITION_GROUPS if g not in PITCHER_GROUPS]
AGE_BANDS = ["≤18", "19", "20", "21", "22", "23+"]
BONUS_BANDS = ["$3M+", "$1M–$3M", "$500k–$1M", "$100k–$500k", "<$100k", "Unknown", "Unsigned"]
KNOWN_BONUS_BANDS = BONUS_BANDS[:5]  # bands with a known signing bonus, highest first
ROUND_BANDS = ["1–5", "6–10", "11–20", "21+", "Supplemental"]
SLOT_VS_BANDS = ["over slot", "at slot", "under slot"]
NON_CONFERENCE_GROUPS = ["Other 4-year", "Junior college", "High school", NO_SCHOOL]

# Pick ranges for the Draft slot tab: (first, last); None = no upper end
PICK_RANGES = [
    (1, 10),
    (11, 20),
    (21, 30),
    (31, 50),
    (51, 75),
    (76, 100),
    (101, 150),
    (151, 200),
    (201, 300),
    (301, 500),
    (501, None),
]


def pick_range_label(first: int, last: int | None) -> str:
    return f"{first}+" if last is None else f"{first}–{last}"


# Outcome tiers (models/08_outcome_tiers.sql), worst to best
TIERS = ["Didn't sign", "Never reached MLB", "Cup of coffee", "Role player", "Regular", "Star"]
TIER_DEFINITIONS = {
    "Didn't sign": "a pick that never signed, or a player drafted again later",
    "Never reached MLB": "signed but never played in the majors",
    "Cup of coffee": "reached the majors with under 1 career WAR",
    "Role player": "1 to 5 career WAR",
    "Regular": "5 to 15 career WAR",
    "Star": "15+ career WAR",
}
REGULAR_TIERS = ["Regular", "Star"]  # "became a regular or better"

# Rankings: group-by label -> column
GROUP_BY = {
    "Conference (D1 only)": "conference",
    "School type": "school_type",
    "School": "school",
    "Position group": "position_group",
    "Age at draft": "age_band",
    "Round range": "round_band",
    "Signing bonus band": "bonus_band",
}
GROUP_ORDERS = {
    "school_type": SCHOOL_TYPES,
    "position_group": POSITION_GROUPS,
    "age_band": AGE_BANDS,
    "round_band": ROUND_BANDS,
    "bonus_band": BONUS_BANDS,
}

# Short names for the cohort sentence ("from SEC schools")
CONFERENCE_SHORT = {
    "Southeastern": "SEC",
    "Atlantic Coast": "ACC",
    "The American": "American",
    "Coastal Athletic": "CAA",
    "Conference USA": "C-USA",
    "Western Athletic": "WAC",
    "Mid-American": "MAC",
}
POSITION_WORDS = {
    "RHP": "right-handed pitchers",
    "LHP": "left-handed pitchers",
    "C": "catchers",
    "1B/3B": "corner infielders",
    "2B/SS": "middle infielders",
    "OF": "outfielders",
    "Other": "other position players",
}
SCHOOL_TYPE_WORDS = {
    "4-year college": "4-year colleges",
    "Junior college": "junior colleges",
    "High school": "high schools",
    NO_SCHOOL: "no listed school",
}

# Player table, in display order: column -> header. "player_url" is built in the page.
TABLE_COLUMNS = {
    "player_url": "Player",
    "draft_year": DRAFT_CLASS,
    "pick_number": PICKED_AT,
    "round_label": "Round",
    "team_name": "Team (current name)",
    "school": "School",
    "conference_group": "Conference / school type",
    "position": "Position",
    "age_at_draft": "Age at draft",
    "bonus_usd": SIGNED_FOR,
    "bonus_vs_slot_pct": "vs. slot value",
    "outcome_tier": "Outcome tier",
    "debut_year": "Debut year",
    "career_war": "Career WAR",
}
PLAYER_URL = "https://www.mlb.com/player/{person_id}"

CHECK_LABELS = {
    "row_count": "Row count matches the source picks",
    "unique_pick": "One row per pick",
    "one_final_draft_per_person": "One final draft per player",
    "years_present": "All draft classes present",
    "max_round_by_year": "Expected number of rounds each year",
    "people_join": "Birth date found for every pick",
    "war_join": "WAR found for every MLB player",
    "age_at_draft_range": "Age at draft between 16 and 26",
    "bonus_range": "Signing bonuses between $0 and $15M",
    "debut_after_draft": "MLB debut comes after the draft",
    "bonus_coverage_rounds_1_10": "Signing bonus known for rounds 1–10",
    "college_d1_conference_share": "College picks with a D1 conference",
    "unknown_school_type_share": "Picks with no school type",
    "no_signed_non_final": "Only a player's final draft can be signed",
    "debuted_players_signed": "Every MLB player signed",
    "slot_expectation_complete": "Every pick has an expected rate between 0 and 1",
    "outcome_tiers_complete": "Every 2012–2019 pick has one outcome tier",
    "slot_curve_monotone": "Expected rates never rise with pick number",
    "slot_model_calibrated": "Expected-by-pick model matches observed rates",
}


def check_label(name: str) -> str:
    return CHECK_LABELS.get(name, name.replace("_", " ").capitalize())
