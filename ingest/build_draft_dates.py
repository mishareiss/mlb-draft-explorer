"""Build reference/draft_dates.csv: the first day of each draft, from Wikipedia.

python -m ingest.build_draft_dates

Each date is parsed from the infobox `Date` row of the page "{year} Major League Baseball
draft" ('June 10–11, 2020' -> 2020-06-10). Pages are cached under data/raw/wikipedia/.
A year whose infobox cannot be parsed stops the run: nothing is filled from memory.
"""

from __future__ import annotations

import csv
import html as htmllib
import logging
import re
from datetime import date, datetime

from ingest import paths
from ingest.http import fetch_text_cached

log = logging.getLogger(__name__)

YEARS = range(2012, 2026)
URL = "https://en.wikipedia.org/wiki/{year}_Major_League_Baseball_draft"
OUT_CSV = paths.REFERENCE / "draft_dates.csv"

INFOBOX_DATE = re.compile(
    r'class="infobox-label"[^>]*>\s*Dates?(?:\(s\))?\s*</th>\s*<td[^>]*>(.*?)</td>', re.S
)
FIRST_DAY = re.compile(r"([A-Z][a-z]+)\s+(\d{1,2})\b.*?(\d{4})", re.S)


def parse_start_date(html: str) -> date:
    """First day in the infobox Date row: 'July 13–14, 2025' -> date(2025, 7, 13)."""
    row = INFOBOX_DATE.search(html)
    if not row:
        raise ValueError("no infobox Date row")
    text = htmllib.unescape(re.sub(r"<[^>]+>", " ", row.group(1))).replace("\xa0", " ")
    m = FIRST_DAY.search(text)
    if not m:
        raise ValueError(f"unparseable infobox date: {text.strip()!r}")
    month, day, year = m.groups()
    return datetime.strptime(f"{month} {day} {year}", "%B %d %Y").date()


def fetch_page(year: int, force: bool = False) -> str:
    return fetch_text_cached(
        URL.format(year=year),
        paths.RAW / "wikipedia" / f"mlb_draft_{year}.html",
        force=force,
        min_interval_s=1.0,
        retry_429=False,
    )


def main() -> None:
    rows = []
    for year in YEARS:
        start = parse_start_date(fetch_page(year))
        if start.year != year:
            raise ValueError(f"{year}: infobox date {start} is in another year")
        rows.append(
            {
                "draft_year": year,
                "draft_start_date": start.isoformat(),
                "source_url": URL.format(year=year),
            }
        )
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["draft_year", "draft_start_date", "source_url"])
        w.writeheader()
        w.writerows(rows)
    log.info("wrote %d draft dates to %s", len(rows), OUT_CSV)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    main()
