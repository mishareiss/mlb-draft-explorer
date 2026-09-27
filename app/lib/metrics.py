"""Business definitions for the Explorer. Pure pandas: no Streamlit, no I/O.

Two kinds of metric:
- Draft-side (picks, signed %, median bonus) use every row in the filter.
- Outcome (MLB %, years to debut, WAR per player, hit %) use only outcome-eligible rows
  (final-draft rows from the 2012-2019 classes) and, unless unsigned picks are counted,
  only players who signed. Rates are fractions in [0, 1].
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

import numpy as np
import pandas as pd

from lib import fmt
from lib.schema import OUTCOME_YEAR_MAX, SLOT_BANDS, YEAR_MIN

if TYPE_CHECKING:
    from lib.data import Filters

Z90 = 1.645  # two-sided 90% interval
MIN_OUTCOME_ROWS = 5  # below this the Explorer shows the empty state for outcome panels


@dataclass(frozen=True)
class OutcomeRules:
    hit_war: float = 5.0  # a "hit" has at least this much career WAR
    count_unsigned: bool = False  # include unsigned final-draft picks in outcome denominators


@dataclass(frozen=True)
class Metric:
    key: str
    label: str
    kind: Literal["rate", "mean", "median"]
    outcome: bool
    unit: Literal["pct", "war", "years", "usd"]


METRICS: dict[str, Metric] = {
    m.key: m
    for m in [
        Metric("mlb_pct", "MLB %", "rate", True, "pct"),
        Metric("war_per_player", "WAR per player", "mean", True, "war"),
        Metric("hit_pct", "Hit %", "rate", True, "pct"),
        Metric("years_to_debut", "Median years to debut", "median", True, "years"),
        Metric("median_bonus", "Median bonus", "median", False, "usd"),
    ]
}

_FORMATTERS = {"pct": fmt.pct, "war": fmt.war, "years": fmt.years, "usd": fmt.usd}


def format_value(metric: str, x: float | None) -> str:
    return _FORMATTERS[METRICS[metric].unit](x)


# --- rows that count ---------------------------------------------------------------------


def outcome_rows(df: pd.DataFrame, rules: OutcomeRules) -> pd.DataFrame:
    mask = df["outcome_eligible"].astype(bool)
    if not rules.count_unsigned:
        mask &= df["signed"].astype(bool)
    return df[mask]


def metric_values(df: pd.DataFrame, metric: str, rules: OutcomeRules) -> pd.DataFrame:
    """The rows a metric is computed over, with the per-row value in column `x`."""
    if metric == "median_bonus":
        rows = df[df["bonus_usd"].notna()]
        return rows.assign(x=rows["bonus_usd"].astype(float))
    rows = outcome_rows(df, rules)
    reached = rows["reached_mlb"].fillna(False).astype(bool)
    if metric == "mlb_pct":
        return rows.assign(x=reached.astype(float))
    if metric == "hit_pct":
        return rows.assign(x=(rows["career_war"] >= rules.hit_war).astype(float))
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


def metric_stat(df: pd.DataFrame, metric: str, rules: OutcomeRules) -> Stat:
    values = metric_values(df, metric, rules)
    if values.empty:
        return Stat(math.nan, math.nan, math.nan, 0)
    row = _aggregate(_stats_by(values, None), METRICS[metric].kind).iloc[0]
    return Stat(float(row["value"]), float(row["lo"]), float(row["hi"]), int(row["n"]))


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


# --- panels ------------------------------------------------------------------------------


@dataclass(frozen=True)
class Summary:
    picks: int
    signed_pct: float
    outcome_n: int
    mlb_pct: float
    years_to_debut: float
    war_per_player: float
    hit_pct: float


def cohort_summary(df: pd.DataFrame, rules: OutcomeRules | None = None) -> Summary:
    rules = rules or OutcomeRules()
    mlb = metric_stat(df, "mlb_pct", rules)
    return Summary(
        picks=len(df),
        signed_pct=float(df["signed"].mean()) if len(df) else math.nan,
        outcome_n=mlb.n,
        mlb_pct=mlb.value,
        years_to_debut=metric_stat(df, "years_to_debut", rules).value,
        war_per_player=metric_stat(df, "war_per_player", rules).value,
        hit_pct=metric_stat(df, "hit_pct", rules).value,
    )


def slot_curve(df: pd.DataFrame, rules: OutcomeRules | None = None) -> pd.DataFrame:
    """MLB % by slot band in draft order (bands with no outcome rows are dropped)."""
    table = group_stats(df, "slot_band", "mlb_pct", min_n=1, rules=rules).table
    order = {band: i for i, band in enumerate(SLOT_BANDS)}
    return table.sort_values("group", key=lambda s: s.map(order)).reset_index(drop=True)


def bonus_points(df: pd.DataFrame) -> pd.DataFrame:
    """Outcome-eligible signed players with a positive bonus (the log axis can't show $0)."""
    rows = outcome_rows(df, OutcomeRules(count_unsigned=False))
    return rows[rows["bonus_usd"].fillna(0) > 0]


TREND_METRICS = {"Share of picks": "share", "Median bonus": "median_bonus", "MLB %": "mlb_pct"}


def trend_table(
    base: pd.DataFrame,
    cohort: pd.DataFrame,
    lines: dict[str, pd.DataFrame],
    metric: str,
    rules: OutcomeRules | None = None,
    cohort_label: str = "Selected draftees",
) -> pd.DataFrame:
    """Metric by draft year: line, draft_year, value, n, role ("line" or "reference").

    share: % of each class (all draftees in `base`) that a line's picks make up. With lines
    chosen, the whole cohort is the reference; the all-draftee share would always be 100%.
    median_bonus / mlb_pct: each line, with all draftees as the reference.
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
        # the cohort's share is a useful reference only if it is below 100% and the lines
        # don't already cover it
        covered = sum(len(f) for f in lines.values())
        if lines and covered < len(cohort) < len(base):
            series.append(("All selected picks", cohort, "reference"))
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
            series.append(("All draftees", base, "reference"))
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


# --- plain-English takeaways (one sentence each) -----------------------------------------


def describe_cohort(f: Filters) -> str:
    """'Southeastern RHP draftees', 'All draftees', or 'Selected draftees' when too complex."""
    dims = [f.schools, f.conference_groups, f.school_types, f.position_groups]
    extras = f.age_bands or f.slot_bands or f.bonus_bands
    if not any(dims) and not extras:
        return "All draftees"
    if extras or any(len(d) > 2 for d in dims):
        return "Selected draftees"
    place = f.schools or f.conference_groups or f.school_types
    words = [" / ".join(place)] if place else []
    if f.position_groups:
        words.append("/".join(f.position_groups))
    return " ".join([*words, "draftees"])


def _who(rules: OutcomeRules) -> str:
    return "draftees" if rules.count_unsigned else "signed draftees"


def takeaway_summary(
    label: str, cohort: Summary, base: Summary, rules: OutcomeRules, is_baseline: bool
) -> str:
    if cohort.outcome_n < MIN_OUTCOME_ROWS:
        return "Too few players from the 2012–2019 classes match these filters to measure outcomes."
    hit = f"{rules.hit_war:g}+ career WAR"
    if is_baseline:
        return (
            f"{fmt.pct(cohort.mlb_pct)} of {_who(rules)} from the 2012–2019 classes reached MLB, "
            f"and {fmt.pct(cohort.hit_pct)} produced {hit}."
        )
    return (
        f"{label} reached MLB at {fmt.pct(cohort.mlb_pct)} and produced {hit} at "
        f"{fmt.pct(cohort.hit_pct)}, vs {fmt.pct(base.mlb_pct)} and {fmt.pct(base.hit_pct)} "
        "for all draftees."
    )


def takeaway_compare(table: pd.DataFrame, metric: str, baseline: float) -> str:
    m = METRICS[metric]
    base = format_value(metric, baseline)
    if table.empty:
        return "No group has enough players to show; lower the minimum sample size."
    top, bottom = table.iloc[0], table.iloc[-1]
    if len(table) == 1:
        return (
            f"{top['group']}: {m.label} {format_value(metric, top['value'])} (n={top['n']:,}), "
            f"vs {base} for all draftees."
        )
    sentence = (
        f"{m.label} ranges from {format_value(metric, bottom['value'])} ({bottom['group']}) "
        f"to {format_value(metric, top['value'])} ({top['group']}); all draftees: {base}"
    )
    if m.kind != "median" and top["lo"] <= bottom["hi"]:
        sentence += " (the top and bottom intervals overlap, so the gap may be noise)"
    return sentence + "."


def takeaway_slot(
    cohort_curve: pd.DataFrame, base_curve: pd.DataFrame, label: str, is_baseline: bool
) -> str:
    if cohort_curve.empty:
        return "No players with outcomes match these filters."
    if is_baseline:
        first, last = cohort_curve.iloc[0], cohort_curve.iloc[-1]
        return (
            f"MLB % falls from {fmt.pct(first['value'])} for picks {first['group']} "
            f"to {fmt.pct(last['value'])} for picks {last['group']}."
        )
    joined = cohort_curve.merge(base_curve, on="group", suffixes=("", "_base"))
    joined = joined[joined["n"] >= 20]
    if joined.empty:
        return "Too few players in each slot band (fewer than 20) for a reliable comparison."
    row = joined.loc[(joined["value"] - joined["value_base"]).abs().idxmax()]
    return (
        f"The biggest gap vs all draftees is at picks {row['group']}: {fmt.pct(row['value'])} "
        f"of {label} reached MLB vs {fmt.pct(row['value_base'])} (n={row['n']:,})."
    )


def takeaway_bonus(points: pd.DataFrame, split: float = 1_000_000) -> str:
    if points.empty:
        return "No signed 2012–2019 players with a known bonus match these filters."
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
    lines = trend[trend["role"] == "line"]
    for name, rows in lines.groupby("line", sort=False):
        rows = rows.dropna(subset=["value"]).sort_values("draft_year")
        if len(rows) < 2:
            continue
        first, last = rows.iloc[0], rows.iloc[-1]
        unit = "pct" if metric_label in ("Share of picks", "MLB %") else "usd"
        f = fmt.pct if unit == "pct" else fmt.usd
        return (
            f"{metric_label} for {name} went from {f(first['value'])} in {first['draft_year']} "
            f"to {f(last['value'])} in {last['draft_year']}."
        )
    return "Not enough draft classes match these filters to show a trend."


def takeaway_table(df: pd.DataFrame) -> str:
    war = df[df["outcome_eligible"].astype(bool)].dropna(subset=["career_war"])
    if war.empty:
        return (
            f"{len(df):,} picks match; none are from the {YEAR_MIN}–{OUTCOME_YEAR_MAX} classes "
            "that have outcome data yet."
        )
    best = war.loc[war["career_war"].idxmax()]
    return (
        f"{len(df):,} picks match; the most career WAR belongs to {best['player_name']} "
        f"({fmt.war(best['career_war'])}, {best['draft_year']} pick {best['pick_number']})."
    )
