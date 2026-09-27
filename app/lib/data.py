"""Load the processed files and filter picks.

The app reads only data/processed/draft_outcomes.parquet and quality_report.json.
DRAFT_OUTCOMES_PATH / QUALITY_REPORT_PATH override the locations (tests use small fixtures).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import streamlit as st

from lib.schema import YEAR_MAX, YEAR_MIN

PROCESSED = Path(__file__).resolve().parents[2] / "data" / "processed"


def outcomes_path() -> Path:
    return Path(os.environ.get("DRAFT_OUTCOMES_PATH", PROCESSED / "draft_outcomes.parquet"))


def quality_path() -> Path:
    return Path(os.environ.get("QUALITY_REPORT_PATH", PROCESSED / "quality_report.json"))


def read_outcomes(path: Path) -> pd.DataFrame:
    df = pd.read_parquet(path)
    # null on non-final rows; nullable bool keeps sums and masks exact
    df["reached_mlb"] = df["reached_mlb"].astype("boolean")
    return df


@st.cache_data(show_spinner=False)
def _load_outcomes(path: str) -> pd.DataFrame:
    return read_outcomes(Path(path))


@st.cache_data(show_spinner=False)
def _load_quality(path: str) -> dict:
    return json.loads(Path(path).read_text())


def load_outcomes() -> pd.DataFrame:
    return _load_outcomes(str(outcomes_path()))


def load_quality() -> dict:
    return _load_quality(str(quality_path()))


@dataclass(frozen=True)
class Filters:
    """Sidebar selections. An empty tuple means "all"."""

    years: tuple[int, int] = (YEAR_MIN, YEAR_MAX)
    school_types: tuple[str, ...] = ()
    conference_groups: tuple[str, ...] = ()
    schools: tuple[str, ...] = ()
    position_groups: tuple[str, ...] = ()
    age_bands: tuple[str, ...] = ()
    slot_bands: tuple[str, ...] = ()
    bonus_bands: tuple[str, ...] = ()

    def years_only(self) -> Filters:
        """Same year range, nothing else: the all-draftee baseline."""
        return Filters(years=self.years)


_COLUMN_FILTERS = {
    "school_types": "school_type",
    "conference_groups": "conference_group",
    "schools": "school",
    "position_groups": "position_group",
    "age_bands": "age_band",
    "slot_bands": "slot_band",
    "bonus_bands": "bonus_band",
}


def apply_filters(df: pd.DataFrame, f: Filters) -> pd.DataFrame:
    lo, hi = f.years
    mask = df["draft_year"].between(lo, hi)
    for field, column in _COLUMN_FILTERS.items():
        chosen = getattr(f, field)
        if chosen:
            mask &= df[column].isin(chosen)
    return df[mask]


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
    tail = ["Other 4-year", "Junior college", "High school", "Unknown"]
    groups = set(df["conference_group"].dropna())
    return sorted(groups - set(tail)) + [g for g in tail if g in groups]
