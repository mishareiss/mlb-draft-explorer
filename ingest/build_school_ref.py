"""Build reference/schools.csv: one row per non-high-school raw `school_name`.

python -m ingest.build_school_ref

School type (first rule that fires wins; recorded in `type_source`):
  0. name_regex  - an explicit HS/JC name ('(FL) HS', 'Cypress CC') wins outright: pick-level
                   evidence can describe another school the player attended
  1. mlb_class   - `school_school_class` level prefix (4YR/JC/HS) on picks with that name;
                   bare classes like `JR`/`SR`/`SO` carry no level and are ignored
  2. bbref_type  - Baseball-Reference `Type` column (HS/4Yr/JC) for those picks, or
     bbref_text    keywords in its `Drafted Out of` text
  3. name_regex  - 'University' / ' U' patterns in the raw name
  4. unknown     - school_type OTHER, needs_review
Baseball-Reference evidence for a pick is used only if its school is consistent with the raw
name (shared distinctive word or matching acronym). Evidence is pooled across spelling
variants of one name ('Arizona ' ~ 'Arizona').
High schools are dropped (Task 3 classifies them by rule).

Division and conference (D1 only) come from pinned revisions of Wikipedia's "List of
NCAA Division I baseball programs". `conference_2024` is the alignment after the July
2024 realignment (revision of 2024-09-30). `conference_pre2024` copies it, overridden by
reference/conference_moves_2024.csv, which is derived from the diff against the
2024-06-11 revision and committed for review. Schools not on the list get
division UNKNOWN, no conference and needs_review. Nothing is filled from memory.

Rows with type_source == "manual" in an existing schools.csv are kept as-is on re-runs.
"""

from __future__ import annotations

import io
import logging
import re
import unicodedata
from collections import Counter
from pathlib import Path

import pandas as pd

from ingest import paths
from ingest.http import fetch_text_cached

log = logging.getLogger(__name__)

REFERENCE = paths.ROOT / "reference"
SCHOOLS_CSV = REFERENCE / "schools.csv"
MOVES_CSV = REFERENCE / "conference_moves_2024.csv"

WIKI_URL = "https://en.wikipedia.org/w/index.php?title=List_of_NCAA_Division_I_baseball_programs&oldid={rev}"
REV_BEFORE_2024 = 1228412379  # 2024-06-11T02:59:14Z, last revision before July 2024 moves
REV_AFTER_2024 = 1248629719  # 2024-09-30T16:24:58Z, after the moves took effect

COLUMNS = [
    "school_name_raw",
    "school_canonical",
    "school_type",
    "division",
    "conference_pre2024",
    "conference_2024",
    "state",
    "type_source",
    "conf_source",
    "needs_review",
]
SCHOOL_TYPES = {"4YR", "JC", "OTHER"}
DIVISIONS = {"D1", "D2", "D3", "NAIA", "JUCO", "UNKNOWN"}

STATE_ABBR = {
    "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR", "California": "CA",
    "Colorado": "CO", "Connecticut": "CT", "Delaware": "DE", "District of Columbia": "DC",
    "Florida": "FL", "Georgia": "GA", "Hawaii": "HI", "Idaho": "ID", "Illinois": "IL",
    "Indiana": "IN", "Iowa": "IA", "Kansas": "KS", "Kentucky": "KY", "Louisiana": "LA",
    "Maine": "ME", "Maryland": "MD", "Massachusetts": "MA", "Michigan": "MI", "Minnesota": "MN",
    "Mississippi": "MS", "Missouri": "MO", "Montana": "MT", "Nebraska": "NE", "Nevada": "NV",
    "New Hampshire": "NH", "New Jersey": "NJ", "New Mexico": "NM", "New York": "NY",
    "North Carolina": "NC", "North Dakota": "ND", "Ohio": "OH", "Oklahoma": "OK", "Oregon": "OR",
    "Pennsylvania": "PA", "Rhode Island": "RI", "South Carolina": "SC", "South Dakota": "SD",
    "Tennessee": "TN", "Texas": "TX", "Utah": "UT", "Vermont": "VT", "Virginia": "VA",
    "Washington": "WA", "West Virginia": "WV", "Wisconsin": "WI", "Wyoming": "WY",
    "Puerto Rico": "PR", "Washington, D.C.": "DC",
}  # fmt: skip

# --- school type -------------------------------------------------------------------------

CLASS_LEVELS = {"4YR": "4YR", "JC": "JC", "HS": "HS"}
BBREF_TYPES = {"HS": "HS", "4YR": "4YR", "JC": "JC"}
SERVICE_ACADEMY = r"(?<!Military )(?<!Naval )(?<!Air Force )(?<!Coast Guard )"
BBREF_TEXT_RULES = [  # checked in order; bare "College" is not decisive (many JCs use it)
    (rf"High School|\bHS\b|{SERVICE_ACADEMY}Academy", "HS"),
    (r"Community College|Junior College|\bCC\b|\bJC\b", "JC"),
    (r"University", "4YR"),
]
# HS and JC patterns are also "explicit": when the raw name says it is a high school or a
# JC, that wins over pick-level evidence, which can describe another school the player attended
# (e.g. 'Blythewood (SC) HS' with class '4YR JR', 'Tyler Junior College' with bbref type 4Yr).
NAME_RULES = [
    (
        rf"\bHS\b|High School|{SERVICE_ACADEMY}Academy|\bPrep\b|Secondary|\bSS\b|Colegio"
        r"|\bSchool\b(?! of)",
        "HS",
    ),
    (r"\bCC\b|\bJC\b|Community College|Junior College|Comm Col", "JC"),
    (r"University|\bUniv\b|\bU\b|Institute of Technology", "4YR"),
]


def _majority(values: list[str]) -> str | None:
    """Most common value, or None if empty or tied."""
    counts = Counter(v for v in values if v).most_common(2)
    if not counts or (len(counts) == 2 and counts[0][1] == counts[1][1]):
        return None
    return counts[0][0]


def class_level(school_class: object) -> str | None:
    """'4YR JR' -> '4YR'; bare 'JR'/'SR'/'NS'/None -> None."""
    if not isinstance(school_class, str) or not school_class.strip():
        return None
    return CLASS_LEVELS.get(school_class.split()[0].upper())


def bbref_text_level(text: object) -> str | None:
    if not isinstance(text, str):
        return None
    name = strip_location(text)
    for pattern, level in BBREF_TEXT_RULES:
        if re.search(pattern, name):
            return level
    return None


def name_level(name: str) -> str | None:
    for pattern, level in NAME_RULES:
        if re.search(pattern, name):
            return level
    return None


def classify_type(
    name: str, classes: list[object], bbref_types: list[object], bbref_texts: list[object]
) -> tuple[str, str]:
    """(level, rule) where level is HS/4YR/JC/UNKNOWN; see module docstring for the order."""
    level = name_level(name)
    if level in ("HS", "JC"):
        return level, "name_regex"
    level = _majority([class_level(c) for c in classes])
    if level:
        return level, "mlb_class"
    level = _majority([BBREF_TYPES.get(str(t).upper()) for t in bbref_types if isinstance(t, str)])
    if level:
        return level, "bbref_type"
    level = _majority([bbref_text_level(t) for t in bbref_texts])
    if level:
        return level, "bbref_text"
    level = name_level(name)
    if level:
        return level, "name_regex"
    return "UNKNOWN", "unknown"


# --- names -------------------------------------------------------------------------------


def strip_location(text: str) -> str:
    """'Louisiana State University (Baton Rouge, LA)' -> 'Louisiana State University'."""
    return re.sub(r"\s*\([^()]*,\s*[A-Z]{2}\)\s*$", "", text).strip()


STATE_TAG = re.compile(r"\s*\(([A-Z]{2})\)\s*$")  # 'Abilene Christian (TX)'


def pool_key(raw: str) -> str:
    """Spelling variants of one raw name share evidence: 'Arizona ' ~ 'Arizona',
    'Cal State-Long Beach' ~ 'Cal State Long Beach'. A trailing state tag stays distinct."""
    m = STATE_TAG.search(raw)
    return f"{school_key(STATE_TAG.sub('', raw))}|{m.group(1) if m else ''}"


def location_state(text: object) -> str | None:
    if not isinstance(text, str):
        return None
    m = re.search(r"\([^()]*,\s*([A-Z]{2})\)\s*$", text)
    return m.group(1) if m else None


GENERIC_WORDS = {
    "university", "college", "state", "of", "and", "community", "junior", "cc", "jc", "hs",
    "high", "school", "saint", "north", "south", "east", "west", "northern", "southern",
    "eastern", "western", "central", "christian", "baptist", "tech", "a", "m", "campus",
}  # fmt: skip


def names_consistent(raw: str, bbref_school: str) -> bool:
    """Could `raw` (MLB) and `bbref_school` (Baseball-Reference) name the same school?
    'TCU' ~ 'Texas Christian University' (acronym); 'Virginia' ~ 'University of Virginia';
    not 'Blythewood (SC) HS' ~ 'University of South Carolina'."""
    r = school_key(STATE_TAG.sub("", raw)).split()
    b = school_key(bbref_school).split()
    if set(r) - GENERIC_WORDS & set(b):
        return True
    initials = "".join(t[0] for t in b if t not in ("of", "and"))
    return len(r) == 1 and len(r[0]) >= 2 and r[0] in (initials, initials.replace("s", "", 1))


def school_key(name: str) -> str:
    """Loose comparison key: case/accents/punctuation folded, common abbreviations expanded."""
    s = unicodedata.normalize("NFKD", name)
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = re.sub(r"\[[^\]]*\]", " ", s).replace("&", " and ")
    s = re.sub(r"[.'’ʻ]", "", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    s = re.sub(r"\bstate university of new york\b|\bsuny\b", " ", s)  # SUNY Stony Brook
    s = re.sub(r"\bunc\b", "north carolina", s)  # UNC Charlotte
    toks = [t for t in s.split() if t not in ("at", "the")]
    out = []
    for i, t in enumerate(toks):
        if t == "st":
            t = "saint" if i == 0 or toks[i - 1] in ("mount", "mt") else "state"
        t = {"u": "university", "univ": "university", "col": "college", "mt": "mount"}.get(t, t)
        out.append(t)
    return " ".join(out)


def key_variants(name: str) -> set[str]:
    """Keys a school may be written as: full, and without 'University of' / 'College'."""
    k = school_key(name)
    out = {k}
    for pat in (r"^university of ", r"^college of ", r" university$", r" college$"):
        stripped = re.sub(pat, "", k).strip()
        if stripped:
            out.add(stripped)
    return out


# --- Wikipedia D1 list -------------------------------------------------------------------


def fetch_wikipedia(rev: int, force: bool = False) -> str:
    return fetch_text_cached(
        WIKI_URL.format(rev=rev),
        paths.RAW / "wikipedia" / f"ncaa_d1_baseball_{rev}.html",
        force=force,
        min_interval_s=1.0,
        retry_429=False,
    )


def clean_cell(s: object) -> str:
    return re.sub(r"\[[^\]]*\]", "", str(s)).replace("\xa0", " ").strip() if pd.notna(s) else ""


def parse_d1_list(html: str) -> pd.DataFrame:
    """School/state/conference for every current D1 member, incl. those transitioning in.

    Columns: wiki_name (as listed), wiki_school (name without aliases), aliases (list),
    state (2-letter), conference. Programs not yet playing ('Future conference') are skipped.
    """
    rows = []
    for t in pd.read_html(io.StringIO(html), flavor="lxml"):
        school_col = next((c for c in t.columns if str(c).startswith("School")), None)
        if school_col is None or "Conference" not in t.columns or "State" not in t.columns:
            continue
        if "First playing" in t.columns:  # announced programs that have not started play
            continue
        for _, r in t.iterrows():
            listed = clean_cell(r[school_col])
            m = re.match(r"^(.*?)\s*\(([^()]*)\)\s*$", listed)
            base, aliases = (m.group(1), m.group(2).split("/")) if m else (listed, [])
            rows.append(
                {
                    "wiki_name": listed,
                    "wiki_school": re.sub(r"\s+", " ", base).strip(),
                    "aliases": [a.strip() for a in aliases if a.strip()],
                    "state": STATE_ABBR.get(clean_cell(r["State"])) or None,
                    "conference": clean_cell(r["Conference"]),
                }
            )
    return pd.DataFrame(rows).drop_duplicates("wiki_school", ignore_index=True)


def build_key_index(d1: pd.DataFrame) -> dict[str, list[int]]:
    """key -> row indexes in d1 (more than one when a short key is shared, e.g. 'miami')."""
    index: dict[str, list[int]] = {}
    for i, r in d1.iterrows():
        keys = key_variants(r["wiki_school"]) | {school_key(a) for a in r["aliases"]}
        for k in keys:
            index.setdefault(k, []).append(i)
    return index


def derive_moves(before: pd.DataFrame, after: pd.DataFrame) -> pd.DataFrame:
    """Schools whose conference differs between the two revisions (renames excluded)."""
    m = before.merge(after, on="wiki_school", suffixes=("_pre2024", "_2024"))
    moved = m[m["conference_pre2024"] != m["conference_2024"]]
    return moved[["wiki_school", "conference_pre2024", "conference_2024"]].reset_index(drop=True)


def load_or_write_moves(before: pd.DataFrame, after: pd.DataFrame, path: Path) -> pd.DataFrame:
    if path.exists():
        return pd.read_csv(path, comment="#", dtype=str)
    moves = derive_moves(before, after)
    header = (
        "# Conference moves effective July 2024 (2024-25 season), D1 baseball.\n"
        "# Derived by ingest/build_school_ref.py from Wikipedia 'List of NCAA Division I\n"
        f"# baseball programs': revision {REV_BEFORE_2024} (2024-06-11) vs "
        f"{REV_AFTER_2024} (2024-09-30).\n"
        "# conference_pre2024 overrides conference_2024 for these schools. Delete this file\n"
        "# to regenerate; edit rows by hand if a move is wrong.\n"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(header + moves.to_csv(index=False))
    return moves


# --- build -------------------------------------------------------------------------------


def evidence_by_school(picks: pd.DataFrame, backfill: pd.DataFrame | None) -> pd.DataFrame:
    """Per raw school name: MLB classes and states, Baseball-Reference type and text."""
    df = picks[["draft_year", "pick_number", "school_name", "school_school_class", "school_state"]]
    df = df[df["school_name"].notna()]
    if backfill is not None:
        bb = backfill.loc[
            backfill["bbref_matched"] & ~backfill["name_mismatch"],
            ["draft_year", "pick_number", "bbref_from_type", "bbref_drafted_out_of"],
        ]
        df = df.merge(bb, on=["draft_year", "pick_number"], how="left")
        ok = [
            isinstance(t, str) and names_consistent(n, strip_location(t))
            for n, t in zip(df["school_name"], df["bbref_drafted_out_of"], strict=True)
        ]
        df.loc[~pd.Series(ok, index=df.index), ["bbref_from_type", "bbref_drafted_out_of"]] = None
    else:
        df = df.assign(bbref_from_type=None, bbref_drafted_out_of=None)
    return df.groupby("school_name", sort=True).agg(
        n=("school_name", "size"),
        classes=("school_school_class", list),
        mlb_states=("school_state", list),
        bbref_types=("bbref_from_type", list),
        bbref_texts=("bbref_drafted_out_of", list),
    )


def _state_ok(known: str | None, listed: object) -> bool:
    return not known or pd.isna(listed) or listed == known


def match_d1(
    raw: str, bbref_name: str | None, state: str | None, d1: pd.DataFrame, index: dict
) -> tuple[int | None, bool, str]:
    """(d1 row, ambiguous, via). Tries the raw name, then the Baseball-Reference full name,
    longest key first. Candidates in a different state than the one we know are dropped; a key
    that still points to more than one school is ambiguous and not used. `via` says which
    name matched ('raw' or 'bbref')."""
    ambiguous = False
    for via, name in (("raw", raw), ("bbref", bbref_name)):
        if not name:
            continue
        for k in sorted(key_variants(name), key=len, reverse=True):
            cands = [i for i in index.get(k, []) if _state_ok(state, d1.at[i, "state"])]
            if len(cands) == 1:
                return cands[0], False, via
            ambiguous |= len(cands) > 1
    return None, ambiguous, ""


def build_schools(
    picks: pd.DataFrame,
    backfill: pd.DataFrame | None,
    d1: pd.DataFrame,
    moves: pd.DataFrame,
) -> pd.DataFrame:
    ev = evidence_by_school(picks, backfill)
    lists = ["classes", "mlb_states", "bbref_types", "bbref_texts"]
    pooled = ev[lists].groupby([pool_key(r) for r in ev.index]).agg(lambda s: sum(s, []))
    index = build_key_index(d1)
    pre = dict(zip(moves["wiki_school"], moves["conference_pre2024"], strict=True))
    rows = []
    for raw in ev.index:
        e = pooled.loc[pool_key(raw)]
        level, rule = classify_type(raw, e["classes"], e["bbref_types"], e["bbref_texts"])
        if level == "HS":
            continue
        texts = [t for t in e["bbref_texts"] if isinstance(t, str) and t]
        bbref_name = _majority([strip_location(t) for t in texts])
        tag = STATE_TAG.search(raw)
        state = (
            (tag.group(1) if tag else None)
            or _majority([s for s in e["mlb_states"] if isinstance(s, str)])
            or _majority([location_state(t) for t in texts])
        )
        row = {
            "school_name_raw": raw,
            "school_type": "OTHER" if level == "UNKNOWN" else level,
            "division": "UNKNOWN",
            "conference_pre2024": "",
            "conference_2024": "",
            "state": state or "",
            "type_source": rule,
            "conf_source": "",
            "needs_review": level == "UNKNOWN",
        }
        canonical = bbref_name or re.sub(r"\s+", " ", raw).strip()
        if level == "JC":
            row["division"] = "JUCO"
        elif level == "4YR":
            i, ambiguous, via = match_d1(STATE_TAG.sub("", raw), bbref_name, state, d1, index)
            if i is None:
                row["needs_review"] = True
                row["conf_source"] = "ambiguous" if ambiguous else ""
            else:
                w = d1.loc[i]
                canonical = w["wiki_school"]
                row.update(
                    division="D1",
                    conference_2024=w["conference"],
                    conference_pre2024=pre.get(w["wiki_school"], w["conference"]),
                    state=row["state"] or ("" if pd.isna(w["state"]) else w["state"]),
                    conf_source="wikipedia",
                    # matched only through the Baseball-Reference name: worth a look
                    needs_review=via == "bbref",
                )
        row["school_canonical"] = canonical
        rows.append(row)
    return pd.DataFrame(rows, columns=COLUMNS)


def merge_manual(generated: pd.DataFrame, existing_path: Path) -> pd.DataFrame:
    """Keep rows marked type_source == 'manual' in the existing CSV; replace the rest."""
    if not existing_path.exists():
        return generated
    existing = read_schools(existing_path)
    manual = existing[existing["type_source"] == "manual"]
    if manual.empty:
        return generated
    log.info("keeping %d manual rows", len(manual))
    rest = generated[~generated["school_name_raw"].isin(manual["school_name_raw"])]
    return pd.concat([rest, manual[COLUMNS]], ignore_index=True)


def read_schools(path: Path = SCHOOLS_CSV) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    df["needs_review"] = df["needs_review"].str.lower().eq("true")
    return df


def write_schools(df: pd.DataFrame, path: Path = SCHOOLS_CSV) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.sort_values("school_name_raw").to_csv(path, index=False)


def main() -> None:
    picks = pd.read_parquet(paths.INTERIM / "draft_picks.parquet")
    bf_path = paths.INTERIM / "bonus_backfill.parquet"
    backfill = pd.read_parquet(bf_path) if bf_path.exists() else None
    if backfill is None:
        log.warning("no bonus_backfill.parquet; building without Baseball-Reference evidence")
    before = parse_d1_list(fetch_wikipedia(REV_BEFORE_2024))
    after = parse_d1_list(fetch_wikipedia(REV_AFTER_2024))
    moves = load_or_write_moves(before, after, MOVES_CSV)

    schools = merge_manual(build_schools(picks, backfill, after, moves), SCHOOLS_CSV)
    write_schools(schools)
    log.info(
        "wrote %d schools: %s; needs_review=%d",
        len(schools),
        schools["division"].value_counts().to_dict(),
        schools["needs_review"].sum(),
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    main()
