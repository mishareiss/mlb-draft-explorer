"""Pull Baseball-Reference draft round pages (signed flag + bonus) for 2012-2017.

python -m ingest.pull_bbref_draft [--years 2012-2017] [--rounds 1-40] [--force]

The MLB Stats API has no signing bonus for 2012-2016; Baseball-Reference does.
2017 is pulled only to cross-check against the MLB API's 2017 bonuses.

Politeness: one page every 7 s (under 10 requests/minute), no retries on 429/403,
every page cached under data/raw/bbref_draft/. An interrupted run resumes from cache.
Supplemental / competitive-balance picks are listed on the numbered-round page of
the round they follow (e.g. 2014 CB-A picks 35-41 are on the round-1 page).
"""

from __future__ import annotations

import argparse
import io
import logging
import sys

import pandas as pd

from ingest import paths
from ingest.http import RateLimitedError, fetch_text_cached
from ingest.pull_draft import parse_bonus, parse_years

log = logging.getLogger(__name__)

BASE = "https://www.baseball-reference.com"
ROUND_URL = (
    BASE + "/draft/?year_ID={year}&draft_round={round}&draft_type=junreg&query_type=year_round"
)
MIN_INTERVAL_S = 7.0
TABLE_ID = "draft_stats"
COLUMNS = [
    "draft_year",
    "overall_pick",
    "round_label",
    "round_pick",
    "team",
    "signed",
    "bonus_usd",
    "name",
    "pos",
    "from_type",
    "drafted_out_of",
    "bbref_player_url",
]


def raw_path(year: int, rnd: int):
    return paths.RAW / "bbref_draft" / f"{year}_r{rnd:02d}.html"


def fetch_round(year: int, rnd: int, force: bool = False) -> str:
    return fetch_text_cached(
        ROUND_URL.format(year=year, round=rnd),
        raw_path(year, rnd),
        force=force,
        min_interval_s=MIN_INTERVAL_S,
        retry_429=False,
    )


def _read_table(html: str) -> pd.DataFrame | None:
    """The draft table, whether it's in the page body or hidden in an HTML comment."""
    for text in (html, html.replace("<!--", "").replace("-->", "")):
        if f'id="{TABLE_ID}"' not in text:
            continue
        try:
            return pd.read_html(
                io.StringIO(text), attrs={"id": TABLE_ID}, extract_links="body", flavor="lxml"
            )[0]
        except ValueError:
            continue
    return None


def _text(col: pd.Series) -> pd.Series:
    return col.map(lambda cell: (cell[0] if isinstance(cell, tuple) else cell) or "").map(
        lambda s: str(s).replace("\xa0", " ").strip()
    )


def _link(col: pd.Series) -> pd.Series:
    return col.map(lambda cell: cell[1] if isinstance(cell, tuple) else None)


def parse_round_page(html: str, year: int) -> pd.DataFrame:
    """One row per pick on a Baseball-Reference round page (empty frame if no table)."""
    raw = _read_table(html)
    if raw is None:
        return pd.DataFrame(columns=COLUMNS)
    ov = pd.to_numeric(_text(raw["OvPck"]), errors="coerce")
    raw = raw[ov.notna()]  # drops repeated header rows inside <tbody>
    ov = ov[ov.notna()]

    rnd = _text(raw["Rnd"])
    dt = _text(raw["DT"]) if "DT" in raw else pd.Series("", index=raw.index)
    url = _link(raw["Name"])
    signed = _text(raw["Signed"]).map({"Y": True, "N": False})
    df = pd.DataFrame(
        {
            "draft_year": year,
            "overall_pick": ov.astype(int),
            "round_label": rnd.where(dt == "", rnd + " " + dt),
            "round_pick": pd.to_numeric(_text(raw["RdPck"]), errors="coerce").astype("Int64"),
            "team": _text(raw["Tm"]),
            "signed": signed.astype("boolean"),
            "bonus_usd": _text(raw["Bonus"]).map(parse_bonus).astype("float64"),
            "name": _text(raw["Name"]).str.replace(r"^\*|\s*\(minors\)$", "", regex=True),
            "pos": _text(raw["Pos"]),
            "from_type": _text(raw["Type"]) if "Type" in raw else "",
            "drafted_out_of": _text(raw["Drafted Out of"]),
            "bbref_player_url": url.map(lambda u: BASE + u if u else None),
        }
    )
    return df[COLUMNS].reset_index(drop=True)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--years", default="2012-2017")
    ap.add_argument("--rounds", default="1-40")
    ap.add_argument("--force", action="store_true", help="re-download even if cached")
    args = ap.parse_args(argv)
    rounds = parse_years(args.rounds)

    frames = []
    for year in parse_years(args.years):
        for rnd in rounds:
            cached = raw_path(year, rnd).exists() and not args.force
            log.info("%d r%d/%d%s", year, rnd, rounds[-1], " (cached)" if cached else "")
            try:
                html = fetch_round(year, rnd, force=args.force)
            except RateLimitedError as exc:
                sys.exit(f"STOPPED: {exc}")
            frames.append(parse_round_page(html, year))

    out = pd.concat(frames, ignore_index=True)
    dupes = out.duplicated(["draft_year", "overall_pick"], keep=False)
    if dupes.any():
        log.warning("%d rows share a (year, overall_pick); keeping first", dupes.sum())
        out = out.drop_duplicates(["draft_year", "overall_pick"])
    paths.INTERIM.mkdir(parents=True, exist_ok=True)
    out.to_parquet(paths.INTERIM / "bbref_draft.parquet", index=False)
    for year, n in out.groupby("draft_year").size().items():
        log.info("%d: %d rows", year, n)
    log.info("wrote %d rows", len(out))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    main()
