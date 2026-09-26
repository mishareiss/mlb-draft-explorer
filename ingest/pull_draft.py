"""Pull MLB draft results (2012-2025) and flatten to one row per pick.

python -m ingest.pull_draft [--years 2012-2025] [--force]
"""

from __future__ import annotations

import argparse
import logging
import re

import pandas as pd

from ingest import paths
from ingest.http import fetch_json_cached

log = logging.getLogger(__name__)

DRAFT_URL = "https://statsapi.mlb.com/api/v1/draft/{year}"


def to_snake(name: str) -> str:
    """'school.schoolClass' -> 'school_school_class'."""
    name = name.replace(".", "_")
    name = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name)
    return name.lower()


def parse_bonus(value: object) -> float:
    """Parse a bonus given as a number or a string like '$1,250,000'; NaN if missing."""
    if value is None:
        return float("nan")
    if isinstance(value, int | float):
        return float(value)
    cleaned = re.sub(r"[$,\s]", "", str(value))
    try:
        return float(cleaned)
    except ValueError:
        return float("nan")


def flatten_draft(payload: dict, year: int) -> pd.DataFrame:
    """One row per pick from a /draft/{year} response, keeping every field."""
    picks = [pick for rnd in payload["drafts"]["rounds"] for pick in rnd.get("picks", [])]
    df = pd.json_normalize(picks)
    df.columns = [to_snake(c) for c in df.columns]
    df.insert(0, "draft_year", year)
    raw_bonus = df["signing_bonus"] if "signing_bonus" in df else pd.Series(None, index=df.index)
    df["signing_bonus_usd"] = raw_bonus.map(parse_bonus).astype("float64")
    return df


def parse_years(spec: str) -> list[int]:
    start, _, end = spec.partition("-")
    return list(range(int(start), int(end or start) + 1))


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--years", default="2012-2025")
    ap.add_argument("--force", action="store_true", help="re-download even if cached")
    args = ap.parse_args(argv)

    frames = []
    for year in parse_years(args.years):
        raw = fetch_json_cached(
            DRAFT_URL.format(year=year), paths.RAW / "draft" / f"{year}.json", force=args.force
        )
        df = flatten_draft(raw, year)
        log.info("%d: %d picks", year, len(df))
        frames.append(df)

    out = pd.concat(frames, ignore_index=True)
    paths.INTERIM.mkdir(parents=True, exist_ok=True)
    out.to_parquet(paths.INTERIM / "draft_picks.parquet", index=False)
    log.info("wrote %d picks x %d columns", *out.shape)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    main()
