"""Pull bios and debut dates for every drafted person.

python -m ingest.pull_people [--force]
"""

from __future__ import annotations

import argparse
import hashlib
import logging
from collections.abc import Callable, Iterable, Sequence

import pandas as pd

from ingest import paths
from ingest.http import fetch_json_cached
from ingest.pull_draft import to_snake

log = logging.getLogger(__name__)

PEOPLE_URL = "https://statsapi.mlb.com/api/v1/people?personIds={ids}"
BATCH_SIZE = 100


def batched(ids: Sequence[int], size: int = BATCH_SIZE) -> list[list[int]]:
    return [list(ids[i : i + size]) for i in range(0, len(ids), size)]


def batch_filename(batch: Sequence[int]) -> str:
    """Cache name keyed by the batch's contents, so a changed id set never reads a stale file."""
    digest = hashlib.sha1(",".join(map(str, sorted(batch))).encode()).hexdigest()
    return f"batch_{digest[:12]}.json"


def fetch_people(
    ids: Iterable[int],
    force: bool = False,
    fetch: Callable[..., dict] = fetch_json_cached,
) -> list[dict]:
    """Fetch /people in batches of 100, caching each batch as batch_<sha1 of its ids>.json."""
    people: list[dict] = []
    for batch in batched(sorted(set(ids))):
        url = PEOPLE_URL.format(ids=",".join(map(str, batch)))
        payload = fetch(url, paths.RAW / "people" / batch_filename(batch), force=force)
        people.extend(payload.get("people", []))
    return people


def flatten_people(people: list[dict]) -> pd.DataFrame:
    df = pd.json_normalize(people)
    df.columns = [to_snake(c) for c in df.columns]
    return df


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true", help="re-download even if cached")
    args = ap.parse_args(argv)

    picks = pd.read_parquet(paths.INTERIM / "draft_picks.parquet", columns=["person_id"])
    ids = picks["person_id"].dropna().astype(int).unique().tolist()
    log.info("%d unique person ids", len(ids))

    df = flatten_people(fetch_people(ids, force=args.force))
    df.to_parquet(paths.INTERIM / "people.parquet", index=False)
    log.info("wrote %d people x %d columns", *df.shape)

    for col in ("id", "full_name", "birth_date", "mlb_debut_date", "birth_country"):
        if col not in df:
            log.warning("expected column %r not present", col)
    for prefix in ("primary_position", "bat_side", "pitch_hand"):
        if not any(c.startswith(prefix) for c in df.columns):
            log.warning("expected %s_* columns not present", prefix)

    missing = sorted(set(ids) - set(df["id"].astype(int)))
    pd.DataFrame({"person_id": missing}).to_csv(
        paths.INTERIM / "people_missing_ids.csv", index=False
    )
    if missing:
        log.warning("%d ids not returned by /people (see people_missing_ids.csv)", len(missing))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    main()
