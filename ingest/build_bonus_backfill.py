"""Join Baseball-Reference draft rows to MLB picks to backfill 2012-2016 bonuses.

python -m ingest.build_bonus_backfill

Join key: (draft_year, overall_pick) = (draft_year, pick_number). Every join is checked
by comparing names; rows scoring below NAME_MATCH_MIN are flagged `name_mismatch` and
their Baseball-Reference signed/bonus values are withheld. draft_picks.parquet is not
modified: Task 3 coalesces MLB and Baseball-Reference bonuses.
"""

from __future__ import annotations

import logging
import re
import unicodedata

import pandas as pd
from rapidfuzz import fuzz

from ingest import paths

log = logging.getLogger(__name__)

NAME_MATCH_MIN = 85
SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}
OUT_COLUMNS = [
    "draft_year",
    "pick_number",
    "person_id",
    "bbref_signed",
    "bbref_bonus_usd",
    "bbref_drafted_out_of",
    "name_match_score",
    "name_mismatch",
    # extra context, for reviewing mismatches (most are nicknames: Mike/Michael, Jake/Jacob)
    # and for build_school_ref
    "same_last_name_initial",
    "bbref_matched",
    "bbref_name",
    "mlb_name",
    "bbref_from_type",
    "bbref_player_url",
]


def normalize_name(name: object) -> str:
    """'José Ramírez Jr.' -> 'jose ramirez'; 'A.J. Reed' -> 'aj reed'."""
    if not isinstance(name, str):
        return ""
    s = unicodedata.normalize("NFKD", name)
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = re.sub(r"[.'’]", "", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(t for t in s.split() if t not in SUFFIXES)


def name_score(bbref_name: object, mlb_names: list[object]) -> float:
    """Best token_sort_ratio between the Baseball-Reference name and any MLB name variant."""
    b = normalize_name(bbref_name)
    if not b:
        return float("nan")
    scores = [fuzz.token_sort_ratio(b, normalize_name(m)) for m in mlb_names if normalize_name(m)]
    return max(scores, default=float("nan"))


def same_last_name_initial(bbref_name: object, mlb_name: object) -> bool:
    """True if the last token and first initial agree ('Mike Mason' ~ 'Michael Mason').
    Diagnostic only: it does not clear name_mismatch."""
    b, m = normalize_name(bbref_name).split(), normalize_name(mlb_name).split()
    return bool(b and m) and b[-1] == m[-1] and b[0][0] == m[0][0]


def _mlb_name_variants(picks: pd.DataFrame) -> pd.Series:
    """Full name plus 'use name + last' and 'first + last' (covers Mike/Michael, AJ/Alan)."""

    def col(c: str) -> pd.Series:
        return picks[c] if c in picks else pd.Series(None, index=picks.index, dtype="object")

    last = col("person_last_name").fillna("")
    use = col("person_use_name").fillna("") + " " + last
    first = col("person_first_name").fillna("") + " " + last
    return pd.Series(list(zip(col("person_full_name"), use, first, strict=True)), index=picks.index)


def build_backfill(picks: pd.DataFrame, bbref: pd.DataFrame) -> pd.DataFrame:
    """One row per MLB pick in the Baseball-Reference years, with the joined bbref values."""
    years = bbref["draft_year"].unique()
    mlb = picks[picks["draft_year"].isin(years)].copy()
    mlb["_names"] = _mlb_name_variants(mlb)
    bb = bbref.rename(
        columns={
            "overall_pick": "pick_number",
            "signed": "bbref_signed",
            "bonus_usd": "bbref_bonus_usd",
            "drafted_out_of": "bbref_drafted_out_of",
            "name": "bbref_name",
            "from_type": "bbref_from_type",
        }
    )
    df = mlb.merge(bb, on=["draft_year", "pick_number"], how="left", indicator=True)
    df["bbref_matched"] = df["_merge"] == "both"
    df["mlb_name"] = df["person_full_name"]
    df["name_match_score"] = [
        name_score(b, list(m)) if ok else float("nan")
        for b, m, ok in zip(df["bbref_name"], df["_names"], df["bbref_matched"], strict=True)
    ]
    df["name_mismatch"] = df["bbref_matched"] & ~(df["name_match_score"] >= NAME_MATCH_MIN)
    df["same_last_name_initial"] = [
        same_last_name_initial(b, m) for b, m in zip(df["bbref_name"], df["mlb_name"], strict=True)
    ]
    df["bbref_signed"] = df["bbref_signed"].astype("boolean").mask(df["name_mismatch"])
    df["bbref_bonus_usd"] = df["bbref_bonus_usd"].astype("float64").mask(df["name_mismatch"])
    return df[OUT_COLUMNS].sort_values(["draft_year", "pick_number"], ignore_index=True)


def crosscheck(backfill: pd.DataFrame, picks: pd.DataFrame, year: int = 2017) -> dict:
    """Compare Baseball-Reference and MLB bonuses for `year` picks that have both."""
    mlb = picks.loc[picks["draft_year"] == year, ["draft_year", "pick_number", "signing_bonus_usd"]]
    both = backfill.merge(mlb, on=["draft_year", "pick_number"])
    both = both[both["bbref_bonus_usd"].notna() & both["signing_bonus_usd"].notna()].copy()
    both["diff"] = both["bbref_bonus_usd"] - both["signing_bonus_usd"]
    rel = both["diff"].abs() / both["signing_bonus_usd"].where(both["signing_bonus_usd"] > 0)
    exact = both["diff"] == 0
    within = exact | (rel <= 0.01)
    disagree = both[both["diff"] != 0]
    top = disagree.reindex(disagree["diff"].abs().sort_values(ascending=False).index).head(10)
    return {
        "n": len(both),
        "exact_pct": round(100 * exact.mean(), 1) if len(both) else float("nan"),
        "within_1pct_pct": round(100 * within.mean(), 1) if len(both) else float("nan"),
        "top": top[
            ["pick_number", "mlb_name", "signing_bonus_usd", "bbref_bonus_usd", "diff"]
        ].reset_index(drop=True),
    }


def main() -> None:
    picks = pd.read_parquet(paths.INTERIM / "draft_picks.parquet")
    bbref = pd.read_parquet(paths.INTERIM / "bbref_draft.parquet")
    out = build_backfill(picks, bbref)
    out.to_parquet(paths.INTERIM / "bonus_backfill.parquet", index=False)

    matched = out["bbref_matched"]
    log.info(
        "wrote %d rows; joined %d (%.1f%%); name mismatches %d",
        len(out),
        matched.sum(),
        100 * matched.mean(),
        out["name_mismatch"].sum(),
    )
    orphans = len(bbref) - matched.sum()
    if orphans:
        log.warning("%d Baseball-Reference rows have no MLB pick at that (year, pick)", orphans)
    cc = crosscheck(out, picks)
    log.info(
        "2017 cross-check on %d picks: exact %.1f%%, within 1%% %.1f%%",
        cc["n"],
        cc["exact_pct"],
        cc["within_1pct_pct"],
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    main()
