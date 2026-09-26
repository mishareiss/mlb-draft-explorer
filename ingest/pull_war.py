"""Pull Baseball-Reference WAR (batting + pitching) via pybaseball.

    python -m ingest.pull_war [--force]

pybaseball does its own HTTP (its own session, not ingest.http). This script
caches the result as CSV so that happens at most once per table.
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Callable

import pandas as pd

from ingest import paths

log = logging.getLogger(__name__)

ID_COLUMN = "mlb_ID"


def load_war(name: str, loader: Callable[..., pd.DataFrame], force: bool = False) -> pd.DataFrame:
    """Return the `name` WAR table, from data/raw/war/{name}.csv if cached."""
    raw = paths.RAW / "war" / f"{name}.csv"
    if raw.exists() and not force:
        return pd.read_csv(raw, low_memory=False)
    df = loader(return_all=True)
    if ID_COLUMN not in df.columns:
        raise RuntimeError(
            f"{name}: expected column {ID_COLUMN!r} missing; got {list(df.columns)[:10]}... "
            "(the download may have returned an error page)"
        )
    raw.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(raw, index=False)
    return df


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true", help="re-download even if cached")
    args = ap.parse_args(argv)

    from pybaseball import bwar_bat, bwar_pitch  # slow import; only needed here

    for name, loader in (("war_bat", bwar_bat), ("war_pitch", bwar_pitch)):
        try:
            df = load_war(name, loader, force=args.force)
        except Exception as exc:  # network / 403 / parse failure: stop loudly
            sys.exit(f"ERROR pulling {name} from Baseball-Reference: {exc!r}")
        df.to_parquet(paths.INTERIM / f"{name}.parquet", index=False)
        log.info("%s: %d rows, %s present=%s", name, len(df), ID_COLUMN, ID_COLUMN in df)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    main()
