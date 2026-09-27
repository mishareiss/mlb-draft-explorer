"""The Explorer's six tabs. Each render function draws one tab from a View of the filters.

Business logic lives in lib.metrics; this module only lays out headings, controls and charts.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import streamlit as st

from lib import charts, fmt, metrics, ui
from lib.data import Filters, top_rounds
from lib.metrics import METRICS, OutcomeRules, delta_vs
from lib.schema import (
    ALL_DRAFTEES,
    GROUP_BY,
    NO_SCHOOL,
    OUTCOME_YEAR_MAX,
    PICKED_AT,
    PLAYER_URL,
    REACHED,
    REGULAR,
    SIGNED_FOR,
    TABLE_COLUMNS,
    VS_SLOT,
    YEAR_MIN,
)
from lib.theme import MUTED

TABS = ["Overview", "Rankings", "Draft slot", "Money", "Trends", "Players"]


@dataclass(frozen=True)
class View:
    df: pd.DataFrame  # every pick
    cohort: pd.DataFrame  # picks matching the filters
    base: pd.DataFrame  # all draftees in the same draft classes
    curve: pd.DataFrame  # slot_expectation.parquet
    filters: Filters
    rules: OutcomeRules
    label: str  # short cohort name for headings

    @property
    def who(self) -> str:
        """Who outcome metrics count, for captions."""
        years = f"{YEAR_MIN}–{OUTCOME_YEAR_MAX}"
        return f"{years} {'draftees' if self.rules.count_unsigned else 'signed players'}"

    @property
    def enough(self) -> bool:
        return len(metrics.outcome_rows(self.cohort, self.rules)) >= metrics.MIN_OUTCOME_ROWS


def _too_few(v: View) -> None:
    st.info(
        f"Fewer than {metrics.MIN_OUTCOME_ROWS} {v.who} match these filters, so there are no "
        "outcomes to show here. Widen the filters or the draft classes."
    )


def _vs_baseline_tile(label: str, stat: metrics.Stat, base: float, v: View, help: str) -> ui.Tile:
    if stat.n == 0:
        return ui.Tile(label, fmt.DASH, "no players with outcomes", MUTED, help)
    if v.filters.is_baseline:
        return ui.Tile(label, fmt.pct(stat.value), "all draftees, same classes", MUTED, help)
    d, text = metrics.vs_all_draftees(stat, base)
    return ui.Tile(label, fmt.pct(stat.value), text, d.sig.color, help)


# --- Overview ------------------------------------------------------------------------------


def overview(v: View) -> None:
    mlb = metrics.metric_stat(v.cohort, "mlb_pct", v.rules)
    base_mlb = metrics.metric_stat(v.base, "mlb_pct", v.rules)
    slot = metrics.vs_slot(v.cohort, "mlb", v.rules)
    ui.heading(
        metrics.takeaway_tiles(v.label, mlb, base_mlb, slot, v.filters.is_baseline),
        f"Outcomes use {v.who}; comparisons are with all draftees from the same classes. "
        "Grey means about the same: the 90% interval includes zero.",
    )
    signed = metrics.metric_stat(v.cohort, "signed_pct", v.rules)
    base_signed = metrics.metric_stat(v.base, "signed_pct", v.rules)
    regular = metrics.metric_stat(v.cohort, "regular_pct", v.rules)
    base_regular = metrics.metric_stat(v.base, "regular_pct", v.rules)
    slot_delta = delta_vs(slot, 0.0)
    slot_words = {
        "above": "above expected for their picks",
        "below": "below expected for their picks",
        "same": "about the same as expected for their picks",
    }.get(slot_delta.sig.direction, "vs. expected for their picks")
    ui.tiles(
        [
            ui.Tile(
                "Players",
                fmt.count(len(v.cohort)),
                f"({fmt.count(mlb.n)} with outcomes)",
                MUTED,
                f"Picks matching the filters; outcomes are measured on the {v.who}.",
            ),
            _vs_baseline_tile("Signed", signed, base_signed.value, v, "Share of picks who signed."),
            _vs_baseline_tile(
                REACHED, mlb, base_mlb.value, v, "Share who played at least one MLB game."
            ),
            ui.Tile(
                VS_SLOT,
                fmt.pts(slot.value) if slot.n else fmt.DASH,
                slot_words if slot.n else "no players with outcomes",
                slot_delta.sig.color if slot.n else MUTED,
                "How much more or less often this group reached the majors than players "
                "taken at the same picks, in percentage points.",
            ),
            _vs_baseline_tile(REGULAR, regular, base_regular.value, v, "Share with 5+ career WAR."),
        ]
    )
    if not v.enough:
        _too_few(v)
        return
    st.write("")
    cohort_dist = metrics.tier_distribution(v.cohort, v.rules)
    base_dist = metrics.tier_distribution(v.base, v.rules)
    dists = (
        {ALL_DRAFTEES: base_dist}
        if v.filters.is_baseline
        else {"This group": cohort_dist, ALL_DRAFTEES: base_dist}
    )
    unsigned = (
        "unsigned picks count as Didn't sign" if v.rules.count_unsigned else "signed players only"
    )
    ui.heading(
        metrics.takeaway_tiers(regular, base_regular, v.filters.is_baseline),
        f"Outcome tier by career WAR, {YEAR_MIN}–{OUTCOME_YEAR_MAX} classes, {unsigned}.",
    )
    ui.chart(charts.tier_bars(dists), key="tiers")


# --- Rankings ------------------------------------------------------------------------------

ROUND_NOTE = (
    "vs. draft slot metrics are off for Round range: each round is compared with its own "
    "picks, so they're about zero by construction."
)


def rankings(v: View) -> None:
    by_label = st.session_state.get("rk_by", next(iter(GROUP_BY)))
    by = GROUP_BY.get(by_label, "conference")
    options = [
        m for m in metrics.RANKING_METRICS if by != "round_band" or m not in metrics.VS_SLOT_METRICS
    ]
    if st.session_state.get("rk_metric") not in options:
        st.session_state["rk_metric"] = options[0]
    c1, c2, c3 = st.columns([2, 2, 1.4])
    metric = c1.selectbox(
        "Metric", options, format_func=lambda k: METRICS[k].label, key="rk_metric"
    )
    c2.selectbox("Group by", list(GROUP_BY), key="rk_by")
    min_n = c3.slider("Minimum players per group", 5, 200, 20, step=5, key="rk_min_n")
    if by == "round_band":
        st.caption(ROUND_NOTE)
    show_unknown = st.checkbox(f"Show “{NO_SCHOOL}”", key="rk_show_unknown")
    if not v.enough and METRICS[metric].outcome:
        _too_few(v)
        return
    stats = metrics.group_stats(v.cohort, by, metric, min_n, v.rules)
    table = stats.table if show_unknown else metrics.drop_no_school(stats.table)
    slot_metric = metric in metrics.VS_SLOT_METRICS
    reference = 0.0 if slot_metric else metrics.metric_stat(v.base, metric, v.rules).value
    table = metrics.with_significance(table, reference)
    ref_label = (
        "Expected for their picks"
        if slot_metric
        else f"{ALL_DRAFTEES}: {metrics.format_value(metric, reference)}"
    )
    noun = metrics.GROUP_NOUNS[by]
    who = "picks with a known signing bonus" if metric == "median_bonus" else v.who
    notes = [f"{METRICS[metric].label} by {noun.removesuffix('s')}, {who}"]
    notes.append("medians have no interval" if metric == "median_bonus" else "90% intervals")
    shown = metrics.shown_groups(table)
    if len(shown) < len(table):
        notes.append(
            f"showing the {metrics.EXTREME_BARS} highest and {metrics.EXTREME_BARS} lowest "
            f"of {len(table)} {noun}"
        )
    groups = noun if stats.hidden != 1 else noun.removesuffix("s")
    notes.append(f"{stats.hidden} {groups} hidden (fewer than {min_n} players)")
    ui.heading(metrics.takeaway_rankings(table, metric, by, reference), "; ".join(notes) + ".")
    ui.chart(charts.rank_dots(table, metric, reference, ref_label), key="rankings")


# --- Draft slot ----------------------------------------------------------------------------


def draft_slot(v: View) -> None:
    if not v.enough:
        _too_few(v)
        return
    table = metrics.pick_range_table(v.cohort, v.rules)
    overall = metrics.vs_slot(v.cohort, "mlb", v.rules)
    hidden = int((table["n"] < metrics.MIN_RANGE_N).sum())
    dots = "grey dots: all draftees" if v.filters.is_baseline else "blue dots: this group"
    caption = (
        f"Top: share of {v.who} who reached the majors by pick range, at each range's median "
        f"pick, with 90% intervals ({dots}); grey line: expected for the pick. Bottom: "
        f"{REACHED.lower()} {VS_SLOT}, in points, with 90% intervals."
    )
    if hidden:
        caption += (
            f" {hidden} pick range{'s' if hidden > 1 else ''} with fewer than "
            f"{metrics.MIN_RANGE_N} players hidden from the bottom panel."
        )
    ui.heading(metrics.takeaway_slot(table, overall, v.label, v.filters.is_baseline), caption)
    expected = metrics.expected_curve(v.curve, v.rules)
    ui.chart(charts.slot_panels(table, expected, v.filters.is_baseline), key="slot")


# --- Money ---------------------------------------------------------------------------------


def money(v: View) -> None:
    view = st.radio(
        "Show",
        list(metrics.MONEY_VIEWS),
        horizontal=True,
        key="money_view",
        label_visibility="collapsed",
    )
    coverage = (
        f"Signing bonus known for {fmt.pct_short(metrics.bonus_known_share(v.cohort))} "
        "of this group's picks."
    )
    if not v.enough:
        _too_few(v)
        st.caption(ui.md(coverage))
        return
    col, order = metrics.MONEY_VIEWS[view]
    rows = metrics.money_rows(v.cohort, view)
    mix = metrics.tier_mix_by(rows, col, order)
    base_mix = metrics.tier_mix_by(metrics.money_rows(v.base, view), col, order)
    if view == "Over or under slot":
        caption = (
            f"Outcome tier by signing bonus vs. the pick's slot value: signed players from the "
            f"2017–2019 classes, rounds 1–10, with both values (n={len(rows):,}). A small "
            "sample: read it as a hint, not a finding."
        )
    else:
        caption = (
            f"Outcome tier by signing bonus band, signed {YEAR_MIN}–{OUTCOME_YEAR_MAX} players "
            f"with a known signing bonus (n={len(rows):,})."
        )
    caption += f" Faded bars have fewer than {metrics.MIN_BAND_N} players."
    ui.heading(metrics.takeaway_money(mix, view), caption)
    ui.chart(charts.money_bars(mix, base_mix, order), key="money")
    st.caption(ui.md(coverage))

    if st.toggle("Show individual players", key="money_players"):
        points = metrics.bonus_points(v.cohort)
        people = points.sort_values("player_name")
        labels = {
            int(r.person_id): f"{r.player_name} ({r.draft_year}, pick {r.pick_number})"
            for r in people.itertuples()
        }
        highlight = st.selectbox(
            "Find a player",
            list(labels),
            format_func=labels.get,
            index=None,
            placeholder="Type a name to highlight their dot",
            key="money_search",
        )
        ui.heading(
            metrics.takeaway_bonus(points),
            f"{SIGNED_FOR} (log scale) vs career WAR, one dot per signed "
            f"{YEAR_MIN}–{OUTCOME_YEAR_MAX} player. Signing bonuses under $1k sit at $1k.",
        )
        ui.chart(charts.bonus_scatter(points, highlight), key="bonus")


# --- Trends --------------------------------------------------------------------------------


def trends(v: View) -> None:
    c1, c2, c3, c4 = st.columns([1.1, 1.3, 1.3, 3])
    top5 = c1.toggle("Top 5 rounds only", value=True, key="tr_top5")
    metric_label = c2.selectbox("Metric", list(metrics.TREND_METRICS), key="tr_metric")
    line_dim = c3.radio("Lines for", ["Conference", "School"], horizontal=True, key="tr_dim")
    cohort = top_rounds(v.cohort, v.df) if top5 else v.cohort
    base = top_rounds(v.base, v.df) if top5 else v.base
    line_col = "conference_group" if line_dim == "Conference" else "school"
    line_options = cohort[line_col].value_counts().index.tolist()
    picked = v.filters.schools if line_col == "school" else v.filters.conference_groups
    default = [x for x in picked if x in line_options][:4] or line_options[:4]
    chosen = c4.multiselect(
        f"{line_dim}s to compare (up to 4)",
        line_options,
        default=default,
        max_selections=4,
        placeholder="This group as one line",
    )
    lines = {name: cohort[cohort[line_col] == name] for name in chosen}
    metric = metrics.TREND_METRICS[metric_label]
    trend = metrics.trend_table(base, cohort, lines, metric, v.rules, cohort_label=v.label)
    notes = {
        "share": "Share of each draft class made up of these picks, 2012–2025.",
        "median_bonus": "Median signing bonus among picks with a known bonus, 2012–2025.",
        "mlb_pct": f"Share of {v.who} who reached the majors.",
        "mlb_vs_slot": f"{REACHED} {VS_SLOT}, in points, {v.who}.",
    }
    scope = (
        " Top 5 rounds: picks through the last pick of round 5 each year, supplemental "
        "picks included."
        if top5
        else " All rounds."
    )
    conference_lines = line_col == "conference_group" and bool(lines)
    realigned = (
        " 2025 uses post-2024 conference membership (e.g. the Pac-12 lost most of its members)."
        if conference_lines
        else ""
    )
    ui.heading(metrics.takeaway_trend(trend, metric_label), notes[metric] + scope + realigned)
    ui.chart(charts.trend_chart(trend, metric_label, conference_lines), key="trend")


# --- Players -------------------------------------------------------------------------------


def _player_line(r: pd.Series) -> str:
    bonus = (
        f"{SIGNED_FOR.lower()} {fmt.usd(r['bonus_usd'])}"
        if pd.notna(r["bonus_usd"])
        else "bonus unknown"
    )
    war = fmt.war(r["career_war"])
    return (
        f"**{r['player_name']}** · {r['draft_year']}, pick {r['pick_number']} · {bonus} · {war} WAR"
    )


def player_table(cohort: pd.DataFrame) -> pd.DataFrame:
    t = cohort.assign(
        player_url=[
            PLAYER_URL.format(person_id=pid) + "#" + name
            for pid, name in zip(cohort["person_id"], cohort["player_name"], strict=True)
        ],
        bonus_vs_slot_pct=cohort["bonus_vs_slot"] * 100,
        debut_year=pd.to_datetime(cohort["mlb_debut_date"]).dt.year.astype("Int64"),
    )
    t = t.sort_values(["career_war", "draft_year", "pick_number"], ascending=[False, True, True])
    return t[list(TABLE_COLUMNS)].rename(columns=TABLE_COLUMNS)


def players(v: View) -> None:
    ui.heading(
        metrics.takeaway_players(v.cohort),
        "Top producers: most career WAR. Biggest misses: highest-bonus signed "
        f"{YEAR_MIN}–{OUTCOME_YEAR_MAX} players who never reached the majors.",
    )
    left, right = st.columns(2)
    with left:
        st.markdown("**Top producers**")
        best = metrics.top_producers(v.cohort)
        st.markdown(
            ui.md("\n".join(f"1. {_player_line(r)}" for _, r in best.iterrows()))
            if not best.empty
            else "None yet."
        )
    with right:
        st.markdown("**Biggest misses**")
        misses = metrics.biggest_misses(v.cohort)
        st.markdown(
            ui.md("\n".join(f"1. {_player_line(r)}" for _, r in misses.iterrows()))
            if not misses.empty
            else "None."
        )
    number = st.column_config.NumberColumn
    st.dataframe(
        player_table(v.cohort),
        hide_index=True,
        height=460,
        column_config={
            "Player": st.column_config.LinkColumn(display_text=r"#(.+)$", width="medium"),
            "Draft class": number(format="%d"),
            PICKED_AT: number(format="%d"),
            "Age at draft": number(format="%.1f"),
            SIGNED_FOR: number(format="$%,d"),
            "vs. slot value": number(
                format="%.0f%%", help="Signed for, as a share of the pick's slot value"
            ),
            "Debut year": number(format="%d"),
            "Career WAR": number(format="%.1f"),
        },
    )
    st.download_button(
        "Download CSV (every column)",
        v.cohort.to_csv(index=False).encode(),
        file_name="draft_picks.csv",
        mime="text/csv",
    )


RENDER = {
    "Overview": overview,
    "Rankings": rankings,
    "Draft slot": draft_slot,
    "Money": money,
    "Trends": trends,
    "Players": players,
}
