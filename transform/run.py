"""Build data/processed/draft_outcomes.parquet by running models/*.sql in DuckDB.

python -m transform.run

Interim tables and reference CSVs are registered as `raw_*` and `ref_*` views, then the
numbered SQL files run in order. All business logic lives in the SQL files. The
expected-by-pick model (transform/slot_model.py) then adds its exp_* columns to
draft_outcomes and builds the slot_expectation curve table.
"""

from __future__ import annotations

import logging
from pathlib import Path

import duckdb

from ingest import paths
from transform import slot_model

log = logging.getLogger(__name__)

MODELS = paths.ROOT / "models"
OUT = paths.PROCESSED / "draft_outcomes.parquet"
CURVE_OUT = paths.PROCESSED / "slot_expectation.parquet"
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
    """In-memory connection with every model built.

    Final tables: `draft_outcomes` (with the slot model's columns) and `slot_expectation`.
    """
    con = duckdb.connect()
    register_sources(con, interim, reference)
    for sql_file in sorted(models.glob("*.sql")):
        log.info("running %s", sql_file.name)
        con.execute(sql_file.read_text())
    add_slot_expectations(con)
    return con


def add_slot_expectations(con: duckdb.DuckDBPyConnection) -> None:
    """Fit the slot model on draft_outcomes and join its per-row columns back on."""
    df = con.execute("select * from draft_outcomes").df()
    curve, _ = slot_model.fit_all(df)
    extra = slot_model.row_columns(df, curve)
    con.register("slot_curve_df", curve)
    con.register("slot_rows_df", extra)
    con.execute("create or replace table slot_expectation as select * from slot_curve_df")
    con.execute(
        "create or replace table draft_outcomes as select d.*, "
        "s.* exclude (draft_year, pick_number) from draft_outcomes as d "
        "left join slot_rows_df as s using (draft_year, pick_number) "
        "order by draft_year, pick_number"
    )


def main() -> None:
    con = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    con.execute(f"copy draft_outcomes to '{OUT}' (format parquet)")
    con.execute(f"copy slot_expectation to '{CURVE_OUT}' (format parquet)")
    n = con.execute("select count(*) from draft_outcomes").fetchone()[0]
    log.info("wrote %d rows to %s", n, OUT)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    main()
