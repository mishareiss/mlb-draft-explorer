"""Load the processed files, filter picks, presets and shareable URLs.

The app reads only data/processed/{draft_outcomes,slot_expectation}.parquet and
quality_report.json. DRAFT_OUTCOMES_PATH / SLOT_EXPECTATION_PATH / QUALITY_REPORT_PATH
override the locations (tests use small fixtures).
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields, replace
from pathlib import Path

import pandas as pd
import streamlit as st

from lib.schema import (
    HITTER_GROUPS,
    NO_SCHOOL,
    NON_CONFERENCE_GROUPS,
    PICK_MAX,
    PICK_MIN,
    PITCHER_GROUPS,
    YEAR_MAX,
    YEAR_MIN,
)

PROCESSED = Path(__file__).resolve().parents[2] / "data" / "processed"


def outcomes_path() -> Path:
    return Path(os.environ.get("DRAFT_OUTCOMES_PATH", PROCESSED / "draft_outcomes.parquet"))


def curve_path() -> Path:
    return Path(os.environ.get("SLOT_EXPECTATION_PATH", PROCESSED / "slot_expectation.parquet"))


def quality_path() -> Path:
    return Path(os.environ.get("QUALITY_REPORT_PATH", PROCESSED / "quality_report.json"))


def read_outcomes(path: Path) -> pd.DataFrame:
    df = pd.read_parquet(path)
    # null on non-final rows; nullable bool keeps sums and masks exact
    df["reached_mlb"] = df["reached_mlb"].astype("boolean")
    df["became_regular"] = df["became_regular"].astype("boolean")
    for col in ("school_type", "conference_group"):
        df[col] = df[col].replace("Unknown", NO_SCHOOL)
    return df


@st.cache_data(show_spinner=False)
def _load_outcomes(path: str) -> pd.DataFrame:
    return read_outcomes(Path(path))


@st.cache_data(show_spinner=False)
def _load_parquet(path: str) -> pd.DataFrame:
    return pd.read_parquet(path)


@st.cache_data(show_spinner=False)
def _load_quality(path: str) -> dict:
    return json.loads(Path(path).read_text())


def load_outcomes() -> pd.DataFrame:
    return _load_outcomes(str(outcomes_path()))


def load_curve() -> pd.DataFrame:
    return _load_parquet(str(curve_path()))


def load_quality() -> dict:
    return _load_quality(str(quality_path()))


# --- filters -------------------------------------------------------------------------------


@dataclass(frozen=True)
class Filters:
    """Sidebar selections. An empty tuple means "all"."""

    years: tuple[int, int] = (YEAR_MIN, YEAR_MAX)
    school_types: tuple[str, ...] = ()
    conference_groups: tuple[str, ...] = ()
    schools: tuple[str, ...] = ()
    position_groups: tuple[str, ...] = ()
    age_bands: tuple[str, ...] = ()
    picks: tuple[int, int] = (PICK_MIN, PICK_MAX)
    bonus_bands: tuple[str, ...] = ()

    def years_only(self) -> Filters:
        """Same draft classes, nothing else: the all-draftee baseline."""
        return Filters(years=self.years)

    @property
    def is_baseline(self) -> bool:
        return self == self.years_only()


_COLUMN_FILTERS = {
    "school_types": "school_type",
    "conference_groups": "conference_group",
    "schools": "school",
    "position_groups": "position_group",
    "age_bands": "age_band",
    "bonus_bands": "bonus_band",
}


def apply_filters(df: pd.DataFrame, f: Filters) -> pd.DataFrame:
    mask = df["draft_year"].between(*f.years) & df["pick_number"].between(*f.picks)
    for field, column in _COLUMN_FILTERS.items():
        chosen = getattr(f, field)
        if chosen:
            mask &= df[column].isin(chosen)
    return df[mask]


def top_rounds(
    df: pd.DataFrame, all_picks: pd.DataFrame | None = None, last_round: int = 5
) -> pd.DataFrame:
    """Picks through the last pick of `last_round` in each class, supplemental picks included.

    Supplemental picks have no round_number, so the cut is by pick_number: everything up to
    the highest pick numbered in `last_round` that year. The cutoffs come from `all_picks`
    (every pick; defaults to df), so a filtered frame is cut at its classes' real round 5.
    """
    source = df if all_picks is None else all_picks
    last_pick = (
        source.loc[source["round_number"] == last_round].groupby("draft_year")["pick_number"].max()
    )
    return df[df["pick_number"] <= df["draft_year"].map(last_pick)]


def school_options(
    df: pd.DataFrame, conference_groups: tuple[str, ...] = (), school_types: tuple[str, ...] = ()
) -> list[str]:
    """Schools to offer, narrowed to the chosen conference groups and school types."""
    mask = pd.Series(True, index=df.index)
    if conference_groups:
        mask &= df["conference_group"].isin(conference_groups)
    if school_types:
        mask &= df["school_type"].isin(school_types)
    return sorted(df.loc[mask, "school"].dropna().unique())


def conference_group_options(df: pd.DataFrame) -> list[str]:
    """D1 conferences alphabetically, then the non-conference groups."""
    groups = set(df["conference_group"].dropna())
    tail = NON_CONFERENCE_GROUPS
    return sorted(groups - set(tail)) + [g for g in tail if g in groups]


# --- presets -------------------------------------------------------------------------------

PRESETS: dict[str, Filters] = {
    "SEC college arms": Filters(
        school_types=("4-year college",),
        conference_groups=("Southeastern",),
        position_groups=tuple(PITCHER_GROUPS),
    ),
    "Prep shortstops": Filters(school_types=("High school",), position_groups=("2B/SS",)),
    "JUCO bats": Filters(school_types=("Junior college",), position_groups=tuple(HITTER_GROUPS)),
    "Top-100 college hitters": Filters(
        school_types=("4-year college",), picks=(1, 100), position_groups=tuple(HITTER_GROUPS)
    ),
    "$1M+ high schoolers": Filters(school_types=("High school",), bonus_bands=("$1M–$3M", "$3M+")),
}


def matching_preset(f: Filters) -> str | None:
    return next((name for name, p in PRESETS.items() if p == f), None)


# --- shareable URLs ------------------------------------------------------------------------

# Filters field -> query parameter
_PARAMS = {
    "years": "class",
    "school_types": "school_type",
    "conference_groups": "conference",
    "schools": "school",
    "position_groups": "position",
    "age_bands": "age",
    "picks": "pick",
    "bonus_bands": "bonus",
}
UNSIGNED_PARAM = "unsigned"


def to_query_params(f: Filters, count_unsigned: bool = False) -> dict[str, list[str]]:
    """Only non-default values; ranges as 'lo-hi', multi-selects as repeated values."""
    default = Filters()
    out: dict[str, list[str]] = {}
    for field in fields(Filters):
        value = getattr(f, field.name)
        if value == getattr(default, field.name):
            continue
        if field.name in ("years", "picks"):
            out[_PARAMS[field.name]] = [f"{value[0]}-{value[1]}"]
        else:
            out[_PARAMS[field.name]] = list(value)
    if count_unsigned:
        out[UNSIGNED_PARAM] = ["1"]
    return out


def _range(values: Sequence[str], lo: int, hi: int) -> tuple[int, int] | None:
    try:
        a, b = (int(x) for x in values[0].split("-"))
    except (IndexError, ValueError):
        return None
    a, b = max(lo, min(a, b)), min(hi, max(a, b))
    return (a, b) if a <= b else None


def from_query_params(params: Mapping[str, Sequence[str]]) -> tuple[Filters, bool]:
    """Inverse of to_query_params. Unknown keys and malformed ranges are ignored."""
    changes: dict[str, object] = {}
    bounds = {"years": (YEAR_MIN, YEAR_MAX), "picks": (PICK_MIN, PICK_MAX)}
    for field, key in _PARAMS.items():
        values = list(params.get(key) or [])
        if not values:
            continue
        if field in bounds:
            parsed = _range(values, *bounds[field])
            if parsed:
                changes[field] = parsed
        else:
            changes[field] = tuple(values)
    count_unsigned = (list(params.get(UNSIGNED_PARAM) or ["0"])[0]) == "1"
    return replace(Filters(), **changes), count_unsigned
