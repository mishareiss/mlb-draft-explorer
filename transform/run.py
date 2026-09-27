"""Build data/processed/draft_outcomes.parquet by running models/*.sql in DuckDB.

python -m transform.run

Interim tables and reference CSVs are registered as `raw_*` and `ref_*` views, then the
numbered SQL files run in order. All business logic lives in the SQL files.
"""

from __future__ import annotations

import logging
from pathlib import Path

import duckdb

from ingest import paths

log = logging.getLogger(__name__)

MODELS = paths.ROOT / "models"
OUT = paths.PROCESSED / "draft_outcomes.parquet"
INTERIM_TABLES = ["draft_picks", "people", "war_bat", "war_pitch", "bbref_draft", "bonus_backfill"]


def _source(folder: Path, name: str) -> str:
    """SQL reading `name` from `folder`: parquet if present, else CSV (test fixtures)."""
    parquet, csv = folder / f"{name}.parquet", folder / f"{name}.csv"
    if parquet.exists():
        return f"read_parquet('{parquet}')"
    if csv.exists():
        return f"read_csv('{csv}', header = true)"
    raise FileNotFoundError(f"no {name}.parquet or {name}.csv in {folder}")


def register_sources(con: duckdb.DuckDBPyConnection, interim: Path, reference: Path) -> None:
    for name in INTERIM_TABLES:
        con.execute(f"create or replace view raw_{name} as select * from {_source(interim, name)}")
    con.execute(
        "create or replace view ref_schools as select * from "
        f"read_csv('{reference / 'schools.csv'}', header = true, all_varchar = true)"
    )
    con.execute(
        "create or replace view ref_draft_dates as select cast(draft_year as integer) as "
        "draft_year, cast(draft_start_date as date) as draft_start_date, source_url from "
        f"read_csv('{reference / 'draft_dates.csv'}', header = true, all_varchar = true)"
    )


def build(
    interim: Path = paths.INTERIM,
    reference: Path = paths.REFERENCE,
    models: Path = MODELS,
) -> duckdb.DuckDBPyConnection:
    """In-memory connection with every model built; `draft_outcomes` is the final table."""
    con = duckdb.connect()
    register_sources(con, interim, reference)
    for sql_file in sorted(models.glob("*.sql")):
        log.info("running %s", sql_file.name)
        con.execute(sql_file.read_text())
    return con


def main() -> None:
    con = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    con.execute(f"copy draft_outcomes to '{OUT}' (format parquet)")
    n = con.execute("select count(*) from draft_outcomes").fetchone()[0]
    log.info("wrote %d rows to %s", n, OUT)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    main()
