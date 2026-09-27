"""Business definitions for the Explorer. Pure pandas: no Streamlit, no I/O.

Two kinds of metric:
- Draft-side (picks, signed %, median signing bonus) use every row in the filter.
- Outcome (reached the majors, became a regular, vs. draft slot, outcome tiers) use only
  outcome-eligible rows (final-draft rows from the 2012-2019 classes) and, unless unsigned
  picks are counted, only players who signed. Rates are fractions in [0, 1]; vs. draft slot
  values are percentage points.

"vs. draft slot" is observed minus expected, where expected comes from the expected-by-pick
model (transform/slot_model.py): how much more or less often a group reached the majors (or
became a regular) than players taken at the same picks.

Significance rule (significance()): a difference whose 90% interval includes zero is "about
the same" (grey); only intervals clear of zero are "above" (blue) or "below" (orange).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

import numpy as np
import pandas as pd

from lib import fmt, theme
from lib.schema import (
    ALL_DRAFTEES,
    CONFERENCE_SHORT,
    HITTER_GROUPS,
    KNOWN_BONUS_BANDS,
    NO_SCHOOL,
    OUTCOME_YEAR_MAX,
    PICK_MAX,
    PICK_MIN,
    PICK_RANGES,
    PITCHER_GROUPS,
    POSITION_WORDS,
    REGULAR_TIERS,
    SCHOOL_TYPE_WORDS,
    SLOT_VS_BANDS,
    TIERS,
    YEAR_MIN,
    pick_range_label,
)

if TYPE_CHECKING:
    from lib.data import Filters

Z90 = 1.645  # two-sided 90% interval
MIN_OUTCOME_ROWS = 5  # below this the outcome panels show an empty state
MIN_RANGE_N = 10  # Draft slot tab: pick ranges with fewer players are hidden from the bars
MIN_BAND_N = 20  # Money tab: bars with fewer players are greyed out


@dataclass(frozen=True)
class OutcomeRules:
    count_unsigned: bool = False  # include unsigned final-draft picks in outcome denominators


@dataclass(frozen=True)
class Metric:
    key: str
    label: str
    kind: Literal["rate", "mean", "median"]
    outcome: bool
    unit: Literal["pct", "pts", "war", "years", "usd"]


METRICS: dict[str, Metric] = {
    m.key: m
    for m in [
        Metric("mlb_vs_slot", "Reached the majors vs. draft slot", "mean", True, "pts"),
        Metric("regular_vs_slot", "Became a regular vs. draft slot", "mean", True, "pts"),
        Metric("mlb_pct", "Reached the majors %", "rate", True, "pct"),
        Metric("regular_pct", "Became a regular %", "rate", True, "pct"),
        Metric("median_bonus", "Median signing bonus", "median", False, "usd"),
        Metric("signed_pct", "Signed %", "rate", False, "pct"),
        Metric("war_per_player", "WAR per player", "mean", True, "war"),
        Metric("years_to_debut", "Median years to debut", "median", True, "years"),
    ]
}
VS_SLOT_METRICS = ("mlb_vs_slot", "regular_vs_slot")
RANKING_METRICS = ["mlb_vs_slot", "regular_vs_slot", "mlb_pct", "regular_pct", "median_bonus"]

_FORMATTERS = {"pct": fmt.pct, "pts": fmt.pts, "war": fmt.war, "years": fmt.years, "usd": fmt.usd}


def format_value(metric: str, x: float | None) -> str:
    return _FORMATTERS[METRICS[metric].unit](x)


# --- significance ------------------------------------------------------------------------


@dataclass(frozen=True)
class Significance:
    direction: Literal["above", "below", "same", "none"]
    color: str
    label: str


def significance(lo: float, hi: float) -> Significance:
    """Color and words for a difference with 90% interval [lo, hi].

    The interval includes zero (an end exactly at zero counts) -> "about the same", grey.
    Clear of zero -> "above" (blue) or "below" (orange). No interval (a median, or a single
    player) -> "none", drawn in the plain cohort blue with no claim either way.
    """
    if lo is None or hi is None or math.isnan(lo) or math.isnan(hi):
        return Significance("none", theme.COHORT, "")
    if lo > 0:
        return Significance("above", theme.COHORT, "above")
    if hi < 0:
        return Significance("below", theme.BELOW, "below")
    return Significance("same", theme.SAME, "about the same")


# --- rows that count ---------------------------------------------------------------------


def outcome_rows(df: pd.DataFrame, rules: OutcomeRules) -> pd.DataFrame:
    mask = df["outcome_eligible"].astype(bool)
    if not rules.count_unsigned:
        mask &= df["signed"].astype(bool)
    return df[mask]


# target -> (observed column, expected column when unsigned count, signed-only difference)
_VS_SLOT = {
    "mlb_vs_slot": ("reached_mlb", "exp_mlb_all", "mlb_minus_exp"),
    "regular_vs_slot": ("became_regular", "exp_regular_all", "regular_minus_exp"),
}


def metric_values(df: pd.DataFrame, metric: str, rules: OutcomeRules) -> pd.DataFrame:
    """The rows a metric is computed over, with the per-row value in column `x`."""
    if metric == "median_bonus":
        rows = df[df["bonus_usd"].notna()]
        return rows.assign(x=rows["bonus_usd"].astype(float))
    if metric == "signed_pct":
        return df.assign(x=df["signed"].astype(float))
    rows = outcome_rows(df, rules)
    reached = rows["reached_mlb"].fillna(False).astype(bool)
    if metric in _VS_SLOT:
        observed, exp_all, signed_diff = _VS_SLOT[metric]
        if rules.count_unsigned:
            diff = rows[observed].fillna(False).astype(float) - rows[exp_all]
        else:
            diff = rows[signed_diff]
        rows = rows.assign(x=100 * diff.astype(float))
        return rows[rows["x"].notna()]
    if metric == "mlb_pct":
        return rows.assign(x=reached.astype(float))
    if metric == "regular_pct":
        return rows.assign(x=rows["became_regular"].fillna(False).astype(float))
    if metric == "war_per_player":
        rows = rows[rows["career_war"].notna()]
        return rows.assign(x=rows["career_war"].astype(float))
    if metric == "years_to_debut":
        rows = rows[reached & rows["years_to_debut"].notna()]
        return rows.assign(x=rows["years_to_debut"].astype(float))
    raise ValueError(f"unknown metric {metric!r}")


# --- intervals and aggregation -----------------------------------------------------------


def wilson_interval(k: float, n: float, z: float = Z90) -> tuple[float, float]:
    """Wilson score interval for k successes in n trials. (nan, nan) when n == 0."""
    if n == 0:
        return (math.nan, math.nan)
    lo, hi = _wilson(np.asarray(k, dtype=float), np.asarray(n, dtype=float), z)
    return (float(lo), float(hi))


def _wilson(k: np.ndarray, n: np.ndarray, z: float) -> tuple[np.ndarray, np.ndarray]:
    p = k / n
    z2 = z * z
    denom = 1 + z2 / n
    center = (p + z2 / (2 * n)) / denom
    half = z * np.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / denom
    return np.clip(center - half, 0, 1), np.clip(center + half, 0, 1)


def _aggregate(g: pd.DataFrame, kind: str) -> pd.DataFrame:
    """g has columns n, total, mean, std, median (one row per group) -> value, lo, hi, n."""
    out = pd.DataFrame({"n": g["n"].astype(int)}, index=g.index)
    with np.errstate(divide="ignore", invalid="ignore"):
        if kind == "rate":
            out["value"] = g["total"] / g["n"]
            out["lo"], out["hi"] = _wilson(g["total"].to_numpy(), g["n"].to_numpy(), Z90)
        elif kind == "mean":
            se = g["std"] / np.sqrt(g["n"])
            out["value"] = g["mean"]
            out["lo"], out["hi"] = g["mean"] - Z90 * se, g["mean"] + Z90 * se
        else:
            out["value"] = g["median"]
            out["lo"] = out["hi"] = np.nan
    return out[["value", "lo", "hi", "n"]]


def _stats_by(values: pd.DataFrame, by: str | None) -> pd.DataFrame:
    x = values["x"]
    grouped = x.groupby(values[by]) if by else x.groupby(np.zeros(len(x), dtype=int))
    return grouped.agg(n="count", total="sum", mean="mean", std="std", median="median")


@dataclass(frozen=True)
class Stat:
    value: float
    lo: float
    hi: float
    n: int


EMPTY_STAT = Stat(math.nan, math.nan, math.nan, 0)


def metric_stat(df: pd.DataFrame, metric: str, rules: OutcomeRules) -> Stat:
    values = metric_values(df, metric, rules)
    if values.empty:
        return EMPTY_STAT
    row = _aggregate(_stats_by(values, None), METRICS[metric].kind).iloc[0]
    return Stat(float(row["value"]), float(row["lo"]), float(row["hi"]), int(row["n"]))


def vs_slot(
    df: pd.DataFrame, target: Literal["mlb", "regular"], rules: OutcomeRules | None = None
) -> Stat:
    """A group's rate vs. draft slot, in percentage points, with a 90% interval.

    Signed players (default): mean of mlb_minus_exp (regular_minus_exp) over outcome-eligible
    signed rows. Counting unsigned picks: mean of reached_mlb.fillna(False) - exp_mlb_all
    (became_regular / exp_regular_all) over every outcome-eligible row.
    Interval: mean ± 1.645·sd/√n.
    """
    return metric_stat(df, f"{target}_vs_slot", rules or OutcomeRules())


@dataclass(frozen=True)
class Delta:
    """A cohort value minus a reference, with the 90% interval of the difference."""

    value: float
    lo: float
    hi: float
    sig: Significance


def delta_vs(stat: Stat, reference: float) -> Delta:
    """Treats the reference (all draftees, or 0 for vs. draft slot) as fixed."""
    lo, hi = stat.lo - reference, stat.hi - reference
    return Delta(stat.value - reference, lo, hi, significance(lo, hi))


@dataclass(frozen=True)
class GroupStats:
    table: pd.DataFrame  # group, value, lo, hi, n; groups with n >= min_n, highest value first
    hidden: int  # groups present in the frame but below min_n


def group_stats(
    df: pd.DataFrame, by: str, metric: str, min_n: int, rules: OutcomeRules | None = None
) -> GroupStats:
    rules = rules or OutcomeRules()
    values = metric_values(df, metric, rules)
    cols = ["group", "value", "lo", "hi", "n"]
    if values.empty:
        table = pd.DataFrame(columns=cols)
    else:
        table = _aggregate(_stats_by(values, by), METRICS[metric].kind)
        table = table.rename_axis("group").reset_index()[cols]
    visible = table[table["n"] >= min_n].sort_values(["value", "n"], ascending=[False, False])
    all_groups = df[by].dropna().nunique()
    return GroupStats(visible.reset_index(drop=True), int(all_groups - len(visible)))


def drop_no_school(table: pd.DataFrame) -> pd.DataFrame:
    return table[table["group"] != NO_SCHOOL].reset_index(drop=True)


def with_significance(table: pd.DataFrame, reference: float) -> pd.DataFrame:
    """Adds color and sig (the significance rule applied to each group's interval vs reference)."""
    sigs = [
        significance(lo - reference, hi - reference)
        for lo, hi in zip(table["lo"], table["hi"], strict=True)
    ]
    return table.assign(color=[s.color for s in sigs], sig=[s.direction for s in sigs])


MAX_BARS = 25  # above this, the rankings chart shows only the extremes
EXTREME_BARS = 12  # how many of the highest and of the lowest groups it shows


def shown_groups(
    table: pd.DataFrame, max_bars: int = MAX_BARS, keep: int = EXTREME_BARS
) -> pd.DataFrame:
    """Every group when there are at most max_bars, else the `keep` highest and `keep` lowest."""
    if len(table) <= max_bars:
        return table
    return pd.concat([table.head(keep), table.tail(keep)], ignore_index=True)


# --- outcome tiers -----------------------------------------------------------------------


def shown_tiers(rules: OutcomeRules) -> list[str]:
    return TIERS if rules.count_unsigned else TIERS[1:]


def tier_distribution(df: pd.DataFrame, rules: OutcomeRules | None = None) -> pd.DataFrame:
    """tier, n, pct (0-100) over outcome rows, in tier order. Without unsigned picks,
    "Didn't sign" is left out and the rest renormalized to 100."""
    rules = rules or OutcomeRules()
    tiers = shown_tiers(rules)
    rows = outcome_rows(df, rules)
    counts = rows["outcome_tier"].value_counts().reindex(tiers, fill_value=0)
    total = counts.sum()
    pct = 100 * counts / total if total else counts.astype(float) * np.nan
    return pd.DataFrame({"tier": tiers, "n": counts.to_numpy(), "pct": pct.to_numpy()})


def regular_or_better(dist: pd.DataFrame) -> float:
    """Share (fraction) of a tier distribution that is Regular or Star."""
    if dist["n"].sum() == 0:
        return math.nan
    return float(dist.loc[dist["tier"].isin(REGULAR_TIERS), "pct"].sum() / 100)


def tier_mix_by(rows: pd.DataFrame, by: str, order: list[str]) -> pd.DataFrame:
    """Long table group, tier, n, pct, group_n: each group's tier mix (signed tiers only)."""
    tiers = TIERS[1:]
    counts = (
        rows.groupby([by, "outcome_tier"])
        .size()
        .unstack(fill_value=0)
        .reindex(index=order, columns=tiers, fill_value=0)
    )
    group_n = counts.sum(axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        pct = counts.div(group_n.replace(0, np.nan), axis=0) * 100
    out = counts.stack().rename("n").to_frame().join(pct.stack().rename("pct"))
    out = out.rename_axis(["group", "tier"]).reset_index()
    return out.assign(group_n=out["group"].map(group_n).astype(int))


MONEY_VIEWS = {
    "What each bonus bought": ("bonus_band", KNOWN_BONUS_BANDS),
    "Over or under slot": ("bonus_vs_slot_band", SLOT_VS_BANDS),
}
SLOT_COMPARE_YEARS = (2017, 2019)  # classes with both a signing bonus and a slot value


def money_rows(df: pd.DataFrame, view: str) -> pd.DataFrame:
    """Outcome-eligible signed rows with a known signing bonus; for "Over or under slot",
    only 2017-2019 rounds 1-10 with both a bonus and a slot value."""
    rows = outcome_rows(df, OutcomeRules())
    rows = rows[rows["bonus_usd"].notna() & rows["outcome_tier"].notna()]
    if view == "Over or under slot":
        rows = rows[
            rows["draft_year"].between(*SLOT_COMPARE_YEARS)
            & (rows["round_number"] <= 10)
            & rows["slot_value_usd"].notna()
            & rows["bonus_vs_slot_band"].notna()
        ]
    return rows


def bonus_points(df: pd.DataFrame) -> pd.DataFrame:
    """Outcome-eligible signed players with a positive bonus (the log axis can't show $0)."""
    rows = outcome_rows(df, OutcomeRules())
    return rows[rows["bonus_usd"].fillna(0) > 0]


def bonus_known_share(df: pd.DataFrame) -> float:
    return float(df["bonus_usd"].notna().mean()) if len(df) else math.nan


# --- draft slot tab ----------------------------------------------------------------------


def pick_range_table(df: pd.DataFrame, rules: OutcomeRules | None = None) -> pd.DataFrame:
    """One row per pick range with outcome rows: range, median_pick, n, rate, lo, hi (Wilson
    90%), and the range's vs. draft slot mean with its interval (vs, vs_lo, vs_hi)."""
    rules = rules or OutcomeRules()
    rows = outcome_rows(df, rules)
    vs = metric_values(df, "mlb_vs_slot", rules)
    out = []
    for first, last in PICK_RANGES:
        hi = PICK_MAX if last is None else last
        in_range = rows[rows["pick_number"].between(first, hi)]
        if in_range.empty:
            continue
        k = int(in_range["reached_mlb"].fillna(False).astype(bool).sum())
        n = len(in_range)
        lo_w, hi_w = wilson_interval(k, n)
        diff = vs.loc[vs["pick_number"].between(first, hi), "x"]
        se = diff.std() / math.sqrt(len(diff)) if len(diff) > 1 else math.nan
        out.append(
            {
                "range": pick_range_label(first, last),
                "median_pick": float(in_range["pick_number"].median()),
                "n": n,
                "rate": k / n,
                "lo": lo_w,
                "hi": hi_w,
                "vs": float(diff.mean()) if len(diff) else math.nan,
                "vs_lo": float(diff.mean() - Z90 * se),
                "vs_hi": float(diff.mean() + Z90 * se),
            }
        )
    cols = ["range", "median_pick", "n", "rate", "lo", "hi", "vs", "vs_lo", "vs_hi"]
    return pd.DataFrame(out, columns=cols)


def expected_curve(curve: pd.DataFrame, rules: OutcomeRules) -> pd.Series:
    """Expected chance of reaching the majors at each pick (index = pick_number)."""
    col = "exp_mlb_all" if rules.count_unsigned else "exp_mlb_signed"
    return curve.set_index("pick_number")[col]


# --- players tab -------------------------------------------------------------------------


def top_producers(df: pd.DataFrame, n: int = 5) -> pd.DataFrame:
    """The n picks with the most career WAR (ties: earlier pick first)."""
    rows = df[df["career_war"].notna()]
    return rows.sort_values(
        ["career_war", "draft_year", "pick_number"], ascending=[False, True, True]
    ).head(n)


def biggest_misses(df: pd.DataFrame, n: int = 5) -> pd.DataFrame:
    """The n highest-bonus signed, outcome-eligible players who never reached MLB."""
    rows = df[
        df["signed"].astype(bool)
        & df["outcome_eligible"].astype(bool)
        & ~df["reached_mlb"].fillna(False).astype(bool)
        & df["bonus_usd"].notna()
    ]
    return rows.sort_values(
        ["bonus_usd", "draft_year", "pick_number"], ascending=[False, True, True]
    ).head(n)


# --- trends ------------------------------------------------------------------------------

TREND_METRICS = {
    "Share of picks": "share",
    "Median signing bonus": "median_bonus",
    "Reached the majors %": "mlb_pct",
    "vs. draft slot": "mlb_vs_slot",
}
TREND_UNITS = {"share": "pct", "median_bonus": "usd", "mlb_pct": "pct", "mlb_vs_slot": "pts"}
COHORT_LINE = "This group"


def trend_table(
    base: pd.DataFrame,
    cohort: pd.DataFrame,
    lines: dict[str, pd.DataFrame],
    metric: str,
    rules: OutcomeRules | None = None,
    cohort_label: str = COHORT_LINE,
) -> pd.DataFrame:
    """Metric by draft class: line, draft_year, value, n, role ("line" or "reference").

    share: % of each class (all draftees in `base`) that a line's picks make up. With lines
    chosen, the whole cohort is the reference; the all-draftee share would always be 100%.
    Other metrics: each line, with all draftees as the reference.
    A reference that would repeat a drawn line (the cohort is all draftees, or the lines
    cover the whole cohort) is left out.
    """
    rules = rules or OutcomeRules()
    cols = ["line", "draft_year", "value", "n", "role"]
    series = [(name, frame, "line") for name, frame in lines.items()] or [
        (cohort_label, cohort, "line")
    ]
    frames = []
    if metric == "share":
        covered = sum(len(f) for f in lines.values())
        if lines and covered < len(cohort) < len(base):
            series.append((COHORT_LINE, cohort, "reference"))
        class_size = base.groupby("draft_year").size()
        for name, frame, role in series:
            n = frame.groupby("draft_year").size().reindex(class_size.index, fill_value=0)
            frames.append(
                pd.DataFrame(
                    {"line": name, "draft_year": class_size.index, "value": n / class_size}
                ).assign(n=n.to_numpy(), role=role)
            )
    else:
        if lines or len(cohort) < len(base):
            series.append((ALL_DRAFTEES, base, "reference"))
        for name, frame, role in series:
            values = metric_values(frame, metric, rules)
            if values.empty:
                continue
            by_year = _aggregate(_stats_by(values, "draft_year"), METRICS[metric].kind)
            by_year = by_year.rename_axis("draft_year").reset_index()
            frames.append(by_year.assign(line=name, role=role))
    if not frames:
        return pd.DataFrame(columns=cols)
    out = pd.concat(frames, ignore_index=True)
    return out[cols].astype({"draft_year": int, "n": int})


# --- the cohort in words -----------------------------------------------------------------


def _join(words: list[str], conj: str = "and") -> str:
    if len(words) <= 2:
        return f" {conj} ".join(words)
    return ", ".join(words[:-1]) + f" {conj} " + words[-1]


def _conference(name: str) -> str:
    return CONFERENCE_SHORT.get(name, name)


def _position_phrase(groups: tuple[str, ...], short: bool = False) -> str:
    chosen = set(groups)
    if not chosen or chosen == set(PITCHER_GROUPS + HITTER_GROUPS):
        return "players"
    if chosen == set(PITCHER_GROUPS):
        return "pitchers"
    if chosen == set(HITTER_GROUPS):
        return "hitters" if short else "position players"
    if short and chosen == {"RHP"}:
        return "right-handers"
    if short and chosen == {"LHP"}:
        return "left-handers"
    return _join([POSITION_WORDS[g] for g in groups])


def _place_phrase(f: Filters) -> str:
    if f.schools:
        return (
            f"from {_join(list(f.schools), 'or')}"
            if len(f.schools) <= 3
            else f"from {len(f.schools)} schools"
        )
    if f.conference_groups:
        d1 = [c for c in f.conference_groups if c not in SCHOOL_TYPE_WORDS and c != "Other 4-year"]
        other = [c for c in f.conference_groups if c not in d1]
        parts = []
        if d1:
            parts.append(
                f"{_join([_conference(c) for c in d1], 'or')} schools"
                if len(d1) <= 3
                else f"{len(d1)} conferences"
            )
        parts += [SCHOOL_TYPE_WORDS.get(c, "other 4-year colleges") for c in other]
        return "from " + _join(parts, "or")
    if f.school_types:
        return "from " + _join([SCHOOL_TYPE_WORDS[t] for t in f.school_types], "or")
    return ""


def _age_word(band: str) -> str:
    return {"≤18": "18 or younger", "23+": "23 or older"}.get(band, band)


def cohort_sentence(f: Filters, cohort: pd.DataFrame, rules: OutcomeRules) -> str:
    """'207 signed right-handed pitchers from SEC schools, drafted 2012–2019 (439 picks,
    2012–2025).' The first number counts the players outcomes are measured on."""
    words = [_position_phrase(f.position_groups)]
    place = _place_phrase(f)
    if place:
        words.append(place)
    extras = []
    if f.picks != (PICK_MIN, PICK_MAX):
        extras.append(f"picked {f.picks[0]:,}–{f.picks[1]:,}")
    if f.bonus_bands:
        extras.append(f"with signing bonus {_join(list(f.bonus_bands), 'or')}")
    if f.age_bands:
        extras.append(f"aged {_join([_age_word(a) for a in f.age_bands], 'or')} at the draft")
    who = " ".join(words) + ("" if not extras else ", " + ", ".join(extras))
    y0, y1 = f.years
    picks = f"{len(cohort):,} picks, {y0}–{y1}"
    if y0 > OUTCOME_YEAR_MAX:
        return (
            f"{len(cohort):,} {who}, drafted {y0}–{y1}. None are from the "
            f"{YEAR_MIN}–{OUTCOME_YEAR_MAX} classes that have outcomes yet."
        )
    n = len(outcome_rows(cohort, rules))
    signed = "" if rules.count_unsigned else "signed "
    return f"{n:,} {signed}{who}, drafted {y0}–{min(y1, OUTCOME_YEAR_MAX)} ({picks})."


def describe_cohort(f: Filters) -> str:
    """Short name for headings: 'SEC pitchers', 'High school middle infielders',
    'All draftees', or 'This group' when the filters are too many to name."""
    if f.is_baseline:
        return ALL_DRAFTEES
    extras = f.age_bands or f.bonus_bands or f.picks != (PICK_MIN, PICK_MAX)
    place_dims = [d for d in (f.schools, f.conference_groups) if d]
    if extras or any(len(d) > 1 for d in place_dims) or len(f.school_types) > 1:
        return "This group"
    who = _position_phrase(f.position_groups, short=True)
    if who.count(",") or " and " in who:
        return "This group"
    if f.schools:
        place = f.schools[0]
    elif f.conference_groups:
        place = _conference(f.conference_groups[0])
    elif f.school_types:
        place = f.school_types[0]
    else:
        return who.capitalize()
    if who == "players":
        return f"{place} players" if place not in SCHOOL_TYPE_WORDS else f"{place} draftees"
    return f"{place} {who}"


# --- takeaway headings (one data-driven sentence each) -----------------------------------


def _more_or_less(delta: Delta, verb: str, what: str) -> str:
    """'reached the majors 3.1 points more often than their draft slots predict'."""
    if delta.sig.direction == "same":
        return f"{verb} about as often as {what}"
    if math.isnan(delta.value):
        return f"{verb} at a rate we can't measure yet"
    side = "more" if delta.value > 0 else "less"
    return f"{verb} {abs(delta.value):.1f} points {side} often than {what}"


def takeaway_tiles(label: str, mlb: Stat, base_mlb: Stat, slot: Stat, is_baseline: bool) -> str:
    if mlb.n < MIN_OUTCOME_ROWS:
        return (
            f"Too few players from the {YEAR_MIN}–{OUTCOME_YEAR_MAX} classes match these "
            "filters to measure outcomes."
        )
    slot_phrase = _more_or_less(
        delta_vs(slot, 0.0), "reached the majors", "their draft slots predict"
    )
    if is_baseline:
        return f"{fmt.pct_short(mlb.value)} of all draftees with outcomes reached the majors."
    rates = f"{fmt.pct_short(mlb.value)} vs {fmt.pct_short(base_mlb.value)} for all draftees"
    return f"{label} {slot_phrase} ({rates})."


def vs_all_draftees(stat: Stat, base: float, pct=fmt.pct) -> tuple[Delta, str]:
    """A rate against the all-draftee rate, in words, following the significance rule:
    'about the same as all draftees (3.3%)' or '+2.8 pts vs. all draftees (3.3%)'."""
    d = delta_vs(stat, base)
    if d.sig.direction == "same":
        return d, f"about the same as all draftees ({pct(base)})"
    return d, f"{fmt.pts(100 * d.value)} vs. all draftees ({pct(base)})"


def takeaway_tiers(regular: Stat, base_regular: Stat, is_baseline: bool) -> str:
    """Regular-or-better share (the Became a regular tile), compared the same way as the tile."""
    if regular.n == 0 or math.isnan(regular.value):
        return "No players with outcomes match these filters."
    share = fmt.pct_short(regular.value)
    if is_baseline:
        return f"{share} of all draftees with outcomes became regulars or better."
    d, phrase = vs_all_draftees(regular, base_regular.value, fmt.pct_short)
    if d.sig.direction == "same":
        return f"{share} of this group became regulars or better, {phrase}."
    return (
        f"{share} of this group became regulars or better, "
        f"vs {fmt.pct_short(base_regular.value)} of all draftees."
    )


GROUP_NOUNS = {
    "conference": "conferences",
    "school_type": "school types",
    "school": "schools",
    "position_group": "position groups",
    "age_band": "ages",
    "round_band": "round ranges",
    "bonus_band": "signing bonus bands",
}


def _count(k: int, noun: str) -> str:
    return f"{k} {noun if k != 1 else noun.removesuffix('s')}"


def takeaway_rankings(table: pd.DataFrame, metric: str, by: str, reference: float) -> str:
    """table: groups with a sig column (with_significance), highest value first."""
    noun = GROUP_NOUNS.get(by, "groups")
    if table.empty:
        return (
            f"No {noun.removesuffix('s')} in this group has enough players to rank; "
            "try another grouping or a lower minimum."
        )
    top = table.iloc[0]
    ref = format_value(metric, reference)
    if metric == "median_bonus":
        return (
            f"{top['group']} had the highest median signing bonus ({fmt.usd(top['value'])}), "
            f"vs {ref} for all draftees."
        )
    k = len(table)
    above = table[table["sig"] == "above"]
    below = table[table["sig"] == "below"]
    short = f"; {_count(len(below), noun)} clearly below" if len(below) else ""
    if metric in VS_SLOT_METRICS:
        verb = "reached the majors" if metric == "mlb_vs_slot" else "became regulars"
        if k == 1:
            d = Delta(top["value"], top["lo"], top["hi"], significance(top["lo"], top["hi"]))
            return f"{top['group']} {_more_or_less(d, verb, 'their draft slots predict')}."
        if len(above):
            best = above.iloc[0]
            return (
                f"{len(above)} of {_count(k, noun)} clearly beat their draft slots, led by "
                f"{best['group']} ({fmt.pts(best['value'])}){short}."
            )
        return (
            f"No {noun.removesuffix('s')} clearly beat its draft slots; {top['group']} came "
            f"closest ({fmt.pts(top['value'])}){short}."
        )
    verb = "reached the majors" if metric == "mlb_pct" else "became regulars"
    lead = f"{top['group']} {verb} most often ({fmt.pct(top['value'])}), vs {ref} for all draftees"
    if k == 1:
        return lead + "."
    return f"{lead}; {len(above)} of {_count(k, noun)} clearly above{short}."


def takeaway_slot(table: pd.DataFrame, overall: Stat, label: str, is_baseline: bool) -> str:
    shown = table[table["n"] >= MIN_RANGE_N]
    if overall.n < MIN_OUTCOME_ROWS or shown.empty:
        return (
            "Too few players with outcomes match these filters to compare with their draft slots."
        )
    sigs = [
        significance(lo, hi).direction
        for lo, hi in zip(shown["vs_lo"], shown["vs_hi"], strict=True)
    ]
    off = sum(s in ("above", "below") for s in sigs)
    if is_baseline:
        worst = shown["vs"].abs().max()
        if off == 0:
            return (
                "The expected-by-pick model tracks all draftees: every pick range is within "
                f"{worst:.1f} points of expected."
            )
        return (
            f"The expected-by-pick model tracks all draftees within {worst:.1f} points; "
            f"{off} of {len(shown)} pick ranges differ by more than chance."
        )
    sentence = f"{label} " + _more_or_less(
        delta_vs(overall, 0.0), "reached the majors", "their draft slots predict"
    )
    clear = shown[[s in ("above", "below") for s in sigs]]
    if not clear.empty:
        row = clear.iloc[clear["vs"].abs().to_numpy().argmax()]
        sentence += f", biggest at picks {row['range']} ({fmt.pts(row['vs'])})"
    return sentence + "."


def takeaway_money(mix: pd.DataFrame, view: str) -> str:
    groups = mix.drop_duplicates("group")
    groups = groups[groups["group_n"] >= MIN_BAND_N]
    if len(groups) < 2:
        return (
            f"Too few signed {YEAR_MIN}–{OUTCOME_YEAR_MAX} players in each band "
            f"(fewer than {MIN_BAND_N}) to compare."
        )
    share = mix[mix["tier"].isin(REGULAR_TIERS)].groupby("group", sort=False)["n"].sum()
    rate = (share / mix.drop_duplicates("group").set_index("group")["group_n"]).reindex(
        groups["group"]
    )
    first, last = rate.index[0], rate.index[-1]
    if view == "Over or under slot":
        return (
            f"Players signed {first} became regulars or better "
            f"{fmt.pct_short(rate[first])} of the time, "
            f"vs {fmt.pct_short(rate[last])} for those signed {last}."
        )
    return (
        f"{fmt.pct_short(rate[first])} of players signed for {first} became regulars or better, "
        f"vs {fmt.pct_short(rate[last])} of those signed for {last}."
    )


def takeaway_bonus(points: pd.DataFrame, split: float = 1_000_000) -> str:
    if points.empty:
        return "No signed 2012–2019 players with a known signing bonus match these filters."
    high = points[points["bonus_usd"] >= split]["career_war"]
    low = points[points["bonus_usd"] < split]["career_war"]
    cut = fmt.usd(split)
    if high.empty or low.empty:
        side, war = ("under", low) if high.empty else ("at least", high)
        return (
            f"All {len(points):,} players shown signed for {side} {cut} "
            f"and averaged {fmt.war(war.mean())} career WAR."
        )
    return (
        f"Players who signed for {cut}+ averaged {fmt.war(high.mean())} career WAR "
        f"(n={len(high):,}), vs {fmt.war(low.mean())} for those under {cut} (n={len(low):,})."
    )


def takeaway_trend(trend: pd.DataFrame, metric_label: str) -> str:
    unit = TREND_UNITS[TREND_METRICS[metric_label]]
    f = {"pct": fmt.pct, "usd": fmt.usd, "pts": fmt.pts}[unit]
    lines = trend[trend["role"] == "line"]
    for name, rows in lines.groupby("line", sort=False):
        rows = rows.dropna(subset=["value"]).sort_values("draft_year")
        if len(rows) < 2:
            continue
        first, last = rows.iloc[0], rows.iloc[-1]
        return (
            f"{metric_label} for {name} went from {f(first['value'])} in {first['draft_year']} "
            f"to {f(last['value'])} in {last['draft_year']}."
        )
    return "Not enough draft classes match these filters to show a trend."


def takeaway_players(df: pd.DataFrame) -> str:
    best = top_producers(df, 1)
    if best.empty or best["career_war"].iloc[0] <= 0:
        return f"{len(df):,} picks match; none has produced career WAR yet."
    b = best.iloc[0]
    sentence = (
        f"{b['player_name']} leads this group with {fmt.war(b['career_war'])} career WAR "
        f"({b['draft_year']}, pick {b['pick_number']})"
    )
    miss = biggest_misses(df, 1)
    if not miss.empty:
        m = miss.iloc[0]
        sentence += (
            f"; the priciest miss is {m['player_name']}, signed for {fmt.usd(m['bonus_usd'])}"
        )
    return sentence + "."


# --- data quality page takeaways (from quality_report.json tables) -------------------------


def takeaway_checks(report: dict) -> str:
    s = report["summary"]
    n = s["pass"] + s["warn"] + s["fail"]
    fail = "none fail" if s["fail"] == 0 else f"{s['fail']} fail"
    return (
        f"{s['pass']} of {n} checks pass on this build of {report['rows']:,} picks; "
        f"{s['warn']} warn and {fail}."
    )


def takeaway_coverage(table: list[dict]) -> str:
    if not table:
        return "No signing bonus coverage table in this build."
    t = pd.DataFrame(table)
    known = t["picks"] * t["pct_with_bonus"] / 100
    early = t["round_band"].isin(["1–5", "6–10"])
    top = known[early].sum() / t.loc[early, "picks"].sum()
    if early.all():
        return f"Signing bonus is known for {fmt.pct_short(top)} of round 1–10 picks."
    rest = known[~early].sum() / t.loc[~early, "picks"].sum()
    return (
        f"Signing bonus is known for {fmt.pct_short(top)} of round 1–10 picks, "
        f"but only {fmt.pct_short(rest)} of later and supplemental picks."
    )


def takeaway_school_mix(table: list[dict]) -> str:
    if not table:
        return "No school-type table in this build."
    t = pd.DataFrame(table)
    hs = t[t["school_type"] == "High school"].set_index("draft_year")["pct"]
    if hs.empty:
        return "No high school picks in this build."
    first, last = hs.index.min(), hs.index.max()
    return (
        f"High schoolers made up {hs[first]:.0f}% of the {first} draft class "
        f"and {hs[last]:.0f}% of {last}."
    )


def takeaway_tier_mix(table: list[dict]) -> str:
    if not table:
        return "No outcome tier table in this build."
    t = pd.DataFrame(table)
    t["regular"] = t["outcome_tier"].isin(REGULAR_TIERS)

    def share(rows: pd.DataFrame) -> float:
        return rows.loc[rows["regular"], "picks"].sum() / rows["picks"].sum()

    early, late = t[t["draft_year"] <= 2017], t[t["draft_year"] >= 2018]
    if early.empty or late.empty:
        return f"{fmt.pct_short(share(t))} of 2012–2019 picks became regulars or better."
    return (
        f"{fmt.pct_short(share(early))} of 2012–2017 picks became regulars or better, vs "
        f"{fmt.pct_short(share(late))} of 2018–2019 picks, who have had less time."
    )


def takeaway_calibration(deciles: list[dict]) -> str:
    if not deciles:
        return "No calibration table in this build."
    worst = max(abs(d["observed"] - d["expected"]) for d in deciles)
    return (
        f"Expected and observed rates of reaching the majors agree within "
        f"{100 * worst:.1f} points in every decile."
    )
