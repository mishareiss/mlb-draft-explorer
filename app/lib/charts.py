"""Plotly figure builders, one per panel. No Streamlit calls, so each is testable.

Colors come from lib.theme: blue = selected cohort (or clearly above), grey = all draftees
(or about the same), orange = clearly below. Direct labels replace legends except for the
outcome-tier key. Every builder returns a figure with no traces and a short message when
given no data.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from lib import fmt, theme
from lib.metrics import (
    EXTREME_BARS,
    MAX_BARS,
    METRICS,
    MIN_BAND_N,
    MIN_RANGE_N,
    TREND_METRICS,
    TREND_UNITS,
    format_value,
    shown_groups,
    significance,
)
from lib.schema import (
    ALL_DRAFTEES,
    OUTCOME_YEAR_MAX,
    REACHED,
    ROUND_BANDS,
    SCHOOL_TYPES,
    TIERS,
    YEAR_MAX,
    YEAR_MIN,
)
from lib.theme import BASELINE, COHORT, INK, MUTED, layout

# How each unit is plotted: multiplier into axis units, and axis tick settings
_AXIS = {
    "pct": (100.0, {"ticksuffix": "%"}),
    "pts": (1.0, {"ticksuffix": " pts"}),
    "war": (1.0, {}),
    "years": (1.0, {"ticksuffix": " yrs"}),
    "usd": (1.0, {"tickprefix": "$", "tickformat": "~s"}),
}
PICK_TICKS = [1, 3, 10, 30, 100, 300, 1000]
VALUE_COLUMN_X = 0.92  # rankings: right edge of the value column (paper units); n sits at 1.0
TIER_LABEL_MIN = 4.0  # label a tier segment only when it is at least this many percent


def empty_figure(message: str, height: int = 220) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(
        text=message,
        showarrow=False,
        x=0.5,
        y=0.5,
        xref="paper",
        yref="paper",
        font={"size": 14, "color": MUTED},
    )
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return layout(fig, height=height)


def _tier_key(fig: go.Figure) -> None:
    """One tier key under the chart (the only legend in the app)."""
    fig.update_layout(
        showlegend=True,
        legend={
            "orientation": "h",
            "yanchor": "top",
            "y": -0.12,
            "x": 0,
            "title": None,
            "traceorder": "normal",
            "font": {"size": 13},
        },
    )


def _segment_text(pct: pd.Series | np.ndarray) -> list[str]:
    return [f"{p:.0f}%" if pd.notna(p) and p >= TIER_LABEL_MIN else "" for p in pct]


# --- overview ------------------------------------------------------------------------------


def tier_bars(dists: dict[str, pd.DataFrame]) -> go.Figure:
    """100% stacked horizontal bars, one per entry (first on top), segmented by tier."""
    dists = {k: d for k, d in dists.items() if d["n"].sum() > 0}
    if not dists:
        return empty_figure("No players with outcomes match these filters.")
    labels = list(dists)
    tiers = [t for t in TIERS if any(t in set(d["tier"]) for d in dists.values())]
    fig = go.Figure()
    for tier in tiers:
        pct = [float(d.set_index("tier")["pct"].get(tier, 0.0)) for d in dists.values()]
        n = [int(d.set_index("tier")["n"].get(tier, 0)) for d in dists.values()]
        color = theme.TIER_COLORS[tier]
        fig.add_bar(
            x=pct,
            y=labels,
            orientation="h",
            name=tier,
            marker={"color": color, "line": {"color": "white", "width": 1}},
            text=_segment_text(np.array(pct)),
            textposition="inside",
            insidetextanchor="middle",
            textfont={"color": theme.text_on(color), "size": 13},
            customdata=n,
            hovertemplate="%{y}: %{x:.1f}% " + tier + " (%{customdata:,})<extra></extra>",
        )
    fig.update_xaxes(range=[0, 100], visible=False)
    fig.update_yaxes(autorange="reversed", showgrid=False, ticksuffix="  ")
    fig = layout(
        fig, height=200, barmode="stack", bargap=0.35, margin={"l": 10, "r": 10, "t": 10, "b": 60}
    )
    _tier_key(fig)  # layout() turns legends off; the tier key is the one exception
    return fig


# --- rankings ------------------------------------------------------------------------------


def rank_dots(
    table: pd.DataFrame,
    metric: str,
    reference: float,
    reference_label: str,
    max_bars: int = MAX_BARS,
    keep: int = EXTREME_BARS,
) -> go.Figure:
    """Dot per group (highest on top), a thin line for its 90% interval, a dashed reference,
    and two right-hand columns: the value (colored like its dot) and n. Colors follow the
    significance rule against the reference. With more than max_bars groups only the `keep`
    highest and `keep` lowest are drawn, with a gap between them.
    """
    if table.empty:
        return empty_figure("No groups meet the minimum sample size.")
    m = METRICS[metric]
    mult, axis = _AXIS[m.unit]
    split = len(table) > max_bars
    t = shown_groups(table, max_bars, keep).iloc[::-1].reset_index(drop=True)
    gap = 0.8 if split else 0.0
    rows = [i + (gap if split and i >= keep else 0.0) for i in range(len(t))]
    sigs = [
        significance(lo - reference, hi - reference)
        for lo, hi in zip(t["lo"], t["hi"], strict=True)
    ]
    colors = [s.color for s in sigs]
    has_interval = t["lo"].notna().any()
    fig = go.Figure()
    if has_interval:
        for color in dict.fromkeys(colors):
            xs, ys = [], []
            for row, lo, hi, c in zip(rows, t["lo"], t["hi"], colors, strict=True):
                if c == color and pd.notna(lo):
                    xs += [lo * mult, hi * mult, None]
                    ys += [row, row, None]
            fig.add_scatter(
                x=xs,
                y=ys,
                mode="lines",
                line={"color": color, "width": 2},
                hoverinfo="skip",
                name="interval",
            )
    values = [format_value(metric, v) for v in t["value"]]
    interval = [
        f"{format_value(metric, lo)} to {format_value(metric, hi)}" if pd.notna(lo) else "—"
        for lo, hi in zip(t["lo"], t["hi"], strict=True)
    ]
    fig.add_scatter(
        x=t["value"] * mult,
        y=rows,
        mode="markers",
        name="dots",
        marker={"color": colors, "size": 11, "line": {"color": "white", "width": 1}},
        customdata=list(
            zip(t["group"], values, interval, t["n"], [s.label for s in sigs], strict=True)
        ),
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>"
            + m.label
            + ": %{customdata[1]}"
            + ("<br>90% interval: %{customdata[2]}" if has_interval else "")
            + "<br>Players: %{customdata[3]:,}<extra></extra>"
        ),
    )
    if pd.notna(reference):
        fig.add_vline(
            x=reference * mult,
            line={"dash": "dash", "color": BASELINE, "width": 1.5},
            annotation_text=reference_label,
            annotation_position="top",
            annotation_font={"color": MUTED, "size": 12},
        )
    # value and n columns, right of the plot; dots and intervals stay unlabeled
    for row, value, color, n in zip(rows, values, colors, t["n"], strict=True):
        fig.add_annotation(
            x=VALUE_COLUMN_X,
            xref="paper",
            xanchor="right",
            y=row,
            text=value,
            name="value",
            showarrow=False,
            font={"color": color, "size": 13},
        )
        fig.add_annotation(
            x=1.0,
            xref="paper",
            xanchor="right",
            y=row,
            text=f"{n:,}",
            name="n",
            showarrow=False,
            font={"color": MUTED, "size": 12},
        )
    fig.add_annotation(
        x=1.0,
        xref="paper",
        xanchor="right",
        y=rows[-1] + 0.9,
        text="n",
        name="n",
        showarrow=False,
        font={"color": MUTED, "size": 12},
    )
    if split:
        fig.add_hline(y=keep - 0.5 + gap / 2, line={"dash": "dot", "color": BASELINE, "width": 1})
    lo_x = np.nanmin(
        [*(t["lo"].fillna(t["value"]) * mult), reference * mult if pd.notna(reference) else np.nan]
    )
    hi_x = np.nanmax(
        [*(t["hi"].fillna(t["value"]) * mult), reference * mult if pd.notna(reference) else np.nan]
    )
    pad = (hi_x - lo_x) * 0.12 or 1.0
    fig.update_xaxes(
        title=m.label,
        domain=[0, VALUE_COLUMN_X - 0.09],
        range=[lo_x - pad * 0.3, hi_x + pad * 0.3],
        showgrid=False,
        **axis,
    )
    fig.update_yaxes(
        title=None,
        automargin=True,
        tickvals=rows,
        ticktext=list(t["group"]),
        showgrid=False,
        range=[-0.7, rows[-1] + 1.2],
        ticksuffix="  ",
    )
    height = 110 + 28 * (len(t) + gap)
    return layout(fig, height=round(height), margin={"l": 10, "r": 10, "t": 30, "b": 50})


# --- draft slot ----------------------------------------------------------------------------


def slot_panels(
    table: pd.DataFrame, expected: pd.Series, is_baseline: bool, min_n: int = MIN_RANGE_N
) -> go.Figure:
    """Top: chance of reaching the majors by pick (log x) with the expected curve in grey
    and the cohort's pick ranges as dots with Wilson 90% intervals (grey dots with no
    filters). Bottom: each range's mean vs. draft slot as bars colored by the significance
    rule, n under each bar; ranges with n < min_n are left out."""
    if table.empty:
        return empty_figure("No players with outcomes match these filters.")
    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.12,
        row_heights=[0.58, 0.42],
        subplot_titles=["Chance of reaching the majors by pick", "Above or below expected"],
    )
    fig.add_scatter(
        x=expected.index,
        y=expected.to_numpy() * 100,
        mode="lines",
        name="expected",
        line={"color": BASELINE, "width": 2},
        hovertemplate="Pick %{x}: expected %{y:.1f}%<extra></extra>",
        row=1,
        col=1,
    )
    dot_color = BASELINE if is_baseline else COHORT
    fig.add_scatter(
        x=table["median_pick"],
        y=table["rate"] * 100,
        mode="markers",
        name="cohort",
        marker={"color": dot_color, "size": 10, "line": {"color": "white", "width": 1}},
        error_y={
            "type": "data",
            "symmetric": False,
            "color": dot_color,
            "thickness": 1.5,
            "width": 0,
            "array": (table["hi"] - table["rate"]) * 100,
            "arrayminus": (table["rate"] - table["lo"]) * 100,
        },
        customdata=list(zip(table["range"], table["n"], strict=True)),
        hovertemplate="Picks %{customdata[0]}: %{y:.1f}% (n=%{customdata[1]:,})<extra></extra>",
        row=1,
        col=1,
    )
    x_label = float(expected.index.min()) * 1.3 if len(expected) else 1.3
    fig.add_annotation(
        x=math.log10(x_label),
        y=float(expected.iloc[0]) * 100 if len(expected) else 90,
        text="Expected for the pick",
        showarrow=False,
        xanchor="left",
        yanchor="bottom",
        font={"color": MUTED, "size": 12},
        row=1,
        col=1,
    )
    shown = table[table["n"] >= min_n]
    sigs = [significance(lo, hi) for lo, hi in zip(shown["vs_lo"], shown["vs_hi"], strict=True)]
    fig.add_bar(
        x=shown["median_pick"],
        y=shown["vs"],
        width=shown["median_pick"] * 0.25,
        name="vs slot",
        marker={"color": [s.color for s in sigs]},
        error_y={
            "type": "data",
            "symmetric": False,
            "color": INK,
            "thickness": 1,
            "width": 2,
            "array": (shown["vs_hi"] - shown["vs"]).clip(lower=0),
            "arrayminus": (shown["vs"] - shown["vs_lo"]).clip(lower=0),
        },
        customdata=list(zip(shown["range"], shown["n"], [s.label for s in sigs], strict=True)),
        hovertemplate=(
            "Picks %{customdata[0]}: %{y:+.1f} pts vs. expected, %{customdata[2]} "
            "(n=%{customdata[1]:,})<extra></extra>"
        ),
        row=2,
        col=1,
    )
    for x, n in zip(shown["median_pick"], shown["n"], strict=True):
        fig.add_annotation(
            x=math.log10(x),
            y=0,
            xref="x2",
            yref="y2 domain",
            yanchor="top",
            yshift=-2,
            text=f"n={n:,}",
            showarrow=False,
            font={"color": MUTED, "size": 11},
        )
    fig.add_hline(y=0, line={"color": MUTED, "width": 1}, row=2, col=1)
    ticks = {"tickvals": PICK_TICKS, "ticktext": [f"{t:,}" for t in PICK_TICKS]}
    fig.update_xaxes(type="log", range=[-0.05, math.log10(1300)], **ticks)
    fig.update_xaxes(title="Picked at (log scale)", row=2, col=1, ticklabelstandoff=16)
    fig.update_yaxes(title="Reached the majors", ticksuffix="%", rangemode="tozero", row=1, col=1)
    fig.update_yaxes(title="vs. draft slot", ticksuffix=" pts", row=2, col=1)
    fig.update_annotations(
        selector={"text": "Chance of reaching the majors by pick"}, font={"size": 14}
    )
    fig.update_annotations(selector={"text": "Above or below expected"}, font={"size": 14})
    return layout(fig, height=640, margin={"l": 10, "r": 20, "t": 40, "b": 60})


# --- money ---------------------------------------------------------------------------------


def money_bars(
    cohort_mix: pd.DataFrame, base_mix: pd.DataFrame, order: list[str], min_n: int = MIN_BAND_N
) -> go.Figure:
    """One 100% stacked tier bar per band (first in `order` on top) with a thin grey
    all-draftee reference bar under it and n at the right. Bars with n < min_n are faded."""
    groups = [g for g in order if cohort_mix.loc[cohort_mix["group"] == g, "group_n"].max() > 0]
    if not groups:
        return empty_figure("No signed 2012–2019 players with a known signing bonus match.")
    step = 1.0
    ys = {g: -i * step for i, g in enumerate(groups)}
    tiers = TIERS[1:]
    fig = go.Figure()
    for tier in tiers:
        rows = cohort_mix[(cohort_mix["tier"] == tier) & cohort_mix["group"].isin(groups)]
        rows = rows.set_index("group").reindex(groups)
        color = theme.TIER_COLORS[tier]
        faded = [0.3 if n < min_n else 1.0 for n in rows["group_n"]]
        fig.add_bar(
            x=rows["pct"].fillna(0),
            y=[ys[g] for g in groups],
            orientation="h",
            width=0.5,
            name=tier,
            legendgroup=tier,
            marker={"color": color, "opacity": faded, "line": {"color": "white", "width": 1}},
            text=_segment_text(rows["pct"]),
            textposition="inside",
            insidetextanchor="middle",
            textfont={"color": theme.text_on(color), "size": 12},
            customdata=list(zip(groups, rows["n"].fillna(0).astype(int), strict=True)),
            hovertemplate="%{customdata[0]}: %{x:.1f}% "
            + tier
            + " (%{customdata[1]:,})<extra></extra>",
        )
        ref = base_mix[base_mix["tier"] == tier].set_index("group").reindex(groups)
        fig.add_bar(
            x=ref["pct"].fillna(0),
            y=[ys[g] - 0.4 for g in groups],
            orientation="h",
            width=0.14,
            name=f"{ALL_DRAFTEES}: {tier}",
            legendgroup=tier,
            showlegend=False,
            marker={"color": theme.TIER_GREYS[tier], "line": {"width": 0}},
            customdata=groups,
            hovertemplate="All draftees, %{customdata}: %{x:.1f}% " + tier + "<extra></extra>",
        )
    n_by = cohort_mix.drop_duplicates("group").set_index("group")["group_n"]
    for g in groups:
        fig.add_annotation(
            x=1.0,
            xref="paper",
            xanchor="left",
            y=ys[g],
            text=f"n={int(n_by[g]):,}",
            showarrow=False,
            font={"color": MUTED, "size": 12},
        )
    fig.add_annotation(
        x=0,
        xref="paper",
        xanchor="left",
        y=ys[groups[-1]] - 0.62,
        text="Grey bar: all draftees",
        showarrow=False,
        font={"color": MUTED, "size": 11},
    )
    fig.update_xaxes(range=[0, 100], visible=False)
    fig.update_yaxes(
        tickvals=[ys[g] - 0.1 for g in groups],
        ticktext=groups,
        showgrid=False,
        ticksuffix="  ",
        range=[ys[groups[-1]] - 0.8, 0.45],
    )
    fig = layout(
        fig,
        height=150 + 62 * len(groups),
        barmode="stack",
        margin={"l": 10, "r": 60, "t": 10, "b": 60},
    )
    _tier_key(fig)
    return fig


BONUS_AXIS_MIN = 1_000  # the scatter's log axis starts here


def bonus_scatter(points: pd.DataFrame, highlight: int | None = None) -> go.Figure:
    """Signing bonus (log) vs career WAR, one dot per player; `highlight` (a person_id) is
    drawn larger in ink and labeled. Bonuses under BONUS_AXIS_MIN sit at the axis edge;
    hover shows the real amount."""
    if points.empty:
        return empty_figure("No signed 2012–2019 players with a known signing bonus match.")
    custom = pd.DataFrame(
        {
            "player": points["player_name"],
            "school": points["school"].fillna("—"),
            "year": points["draft_year"],
            "pick": points["pick_number"],
            "bonus": points["bonus_usd"].map(fmt.usd),
            "war": points["career_war"].map(fmt.war),
        }
    )
    hover = (
        "<b>%{customdata[0]}</b><br>%{customdata[1]}<br>"
        "%{customdata[2]} draft, picked at %{customdata[3]}<br>"
        "Signed for %{customdata[4]} · Career WAR %{customdata[5]}<extra></extra>"
    )
    fig = go.Figure()
    fig.add_scatter(
        x=points["bonus_usd"].clip(lower=BONUS_AXIS_MIN),
        y=points["career_war"],
        mode="markers",
        name="players",
        marker={
            "color": COHORT,
            "size": 8,
            "opacity": 0.55,
            "line": {"color": "white", "width": 1},
        },
        customdata=custom.to_numpy(),
        hovertemplate=hover,
    )
    if highlight is not None:
        mask = (points["person_id"] == highlight).to_numpy()
        if mask.any():
            row = points[mask].iloc[0]
            fig.add_scatter(
                x=[max(row["bonus_usd"], BONUS_AXIS_MIN)],
                y=[row["career_war"]],
                mode="markers+text",
                name="highlight",
                text=[row["player_name"]],
                textposition="top center",
                textfont={"color": INK, "size": 14},
                marker={"color": INK, "size": 15, "line": {"color": "white", "width": 2}},
                customdata=custom[mask].to_numpy(),
                hovertemplate=hover,
            )
    top = max(points["bonus_usd"].max(), BONUS_AXIS_MIN * 10)
    fig.update_xaxes(
        title="Signed for (log scale)",
        type="log",
        tickprefix="$",
        tickformat="~s",
        range=[math.log10(BONUS_AXIS_MIN) - 0.05, math.log10(top) + 0.05],
    )
    fig.update_yaxes(title="Career WAR")
    return layout(fig, height=420)


# --- trends --------------------------------------------------------------------------------

RULE_CHANGES = {2020: ("5-round draft", "top left"), 2021: ("20 rounds", "top right")}
REALIGNED_YEAR = 2025  # conferences use spring-2025 membership from this class on
REALIGNED = (REALIGNED_YEAR, ("Realigned conferences", "top left"))


def trend_chart(
    trend: pd.DataFrame, metric_label: str, conference_lines: bool = False
) -> go.Figure:
    """One line per selection plus a grey "All draftees" line, labeled at the line ends.
    Rule-change markers at 2020 and 2021; outcome metrics stop at 2019. With conference_lines,
    each selected line's step into 2025 is dotted and 2025 gets a "Realigned conferences"
    marker: that class uses post-2024 conference membership."""
    if trend.empty:
        return empty_figure("No draft classes match these filters.")
    unit = TREND_UNITS[TREND_METRICS[metric_label]]
    mult, axis = _AXIS[unit]
    f = {"pct": fmt.pct, "usd": fmt.usd, "pts": fmt.pts}[unit]
    outcome = (
        METRICS.get(TREND_METRICS[metric_label]) is not None
        and METRICS[TREND_METRICS[metric_label]].outcome
    )
    fig = go.Figure()
    names = list(dict.fromkeys(trend.loc[trend["role"] == "line", "line"]))
    palette = theme.SERIES_COLORS
    color = {name: palette[i % len(palette)] for i, name in enumerate(names)}
    for name, rows in trend.groupby("line", sort=False):
        rows = rows.dropna(subset=["value"]).sort_values("draft_year")
        if rows.empty:
            continue
        ref = (rows["role"] == "reference").all()
        c = BASELINE if ref else color[name]
        before = rows[rows["draft_year"] < REALIGNED_YEAR]
        dotted_tail = conference_lines and not ref and len(before) and len(before) < len(rows)
        solid = before if dotted_tail else rows
        for part, dash in [(solid, "dash" if ref else "solid")] + (
            [(rows.iloc[len(before) - 1 :], "dot")] if dotted_tail else []
        ):
            fig.add_scatter(
                x=part["draft_year"],
                y=part["value"] * mult,
                name=name,
                mode="lines+markers",
                line={"color": c, "width": 2 if ref else 2.5, "dash": dash},
                marker={"size": 6 if ref else 7},
                customdata=list(zip([f(v) for v in part["value"]], part["n"], strict=True)),
                hovertemplate=(
                    "%{x}: %{customdata[0]} (n=%{customdata[1]:,})<extra>%{fullData.name}</extra>"
                ),
            )
        last = rows.iloc[-1]
        fig.add_annotation(
            x=last["draft_year"],
            y=last["value"] * mult,
            text=f" {name}",
            xanchor="left",
            showarrow=False,
            font={"color": MUTED if ref else c, "size": 13},
            xshift=6,
        )
    markers = list(RULE_CHANGES.items()) + ([REALIGNED] if conference_lines else [])
    for year, (text, position) in markers:
        fig.add_vline(
            x=year,
            line={"dash": "dot", "color": BASELINE, "width": 1},
            annotation_text=text,
            annotation_position=position,
            annotation_font={"color": MUTED, "size": 12},
        )
    if outcome:
        fig.add_annotation(
            x=OUTCOME_YEAR_MAX + 0.5,
            xanchor="left",
            y=0.5,
            yref="paper",
            showarrow=False,
            text="Later classes<br>still developing",
            align="left",
            font={"color": MUTED, "size": 12},
        )
    if unit == "pts":
        fig.add_hline(y=0, line={"color": MUTED, "width": 1})
    fig.update_xaxes(
        title="Draft class",
        tickvals=list(range(YEAR_MIN, YEAR_MAX + 1)),
        range=[YEAR_MIN - 0.5, YEAR_MAX + 2.8],
    )
    fig.update_yaxes(title=metric_label, **axis)
    return layout(fig, height=420, margin={"l": 10, "r": 20, "t": 40, "b": 40})


# --- data quality --------------------------------------------------------------------------


def coverage_heatmap(table: list[dict]) -> go.Figure:
    """% of picks with a known signing bonus, draft class x round band."""
    if not table:
        return empty_figure("No bonus coverage table in the report.")
    t = pd.DataFrame(table)
    bands = [b for b in ROUND_BANDS if b in set(t["round_band"])]
    z = t.pivot(index="round_band", columns="draft_year", values="pct_with_bonus").loc[bands]
    picks = t.pivot(index="round_band", columns="draft_year", values="picks").loc[bands]
    ylabels = [b if b == "Supplemental" else f"Rounds {b}" for b in bands]
    fig = go.Figure(
        go.Heatmap(
            z=z.to_numpy(),
            x=list(z.columns),
            y=ylabels,
            zmin=0,
            zmax=100,
            colorscale=[[0, "#f1f5fb"], [1, COHORT]],
            xgap=2,
            ygap=2,
            showscale=False,
            customdata=picks.to_numpy(),
            hovertemplate="%{x}, %{y}: %{z:.1f}% of %{customdata:,} picks<extra></extra>",
        )
    )
    for i, label in enumerate(ylabels):
        for j, year in enumerate(z.columns):
            v = z.iat[i, j]
            if pd.notna(v):
                fig.add_annotation(
                    x=year,
                    y=label,
                    text=f"{v:.0f}%",
                    showarrow=False,
                    font={"size": 12, "color": "white" if v >= 55 else INK},
                )
    fig.update_xaxes(title="Draft class", dtick=1, showgrid=False)
    fig.update_yaxes(title=None, autorange="reversed", showgrid=False)
    return layout(fig, height=300)


def school_mix_bars(table: list[dict]) -> go.Figure:
    """Stacked % of each class by school type, labeled at the right end."""
    if not table:
        return empty_figure("No school-type table in the report.")
    t = pd.DataFrame(table).replace({"school_type": {"Unknown": SCHOOL_TYPES[-1]}})
    fig = go.Figure()
    for school_type in SCHOOL_TYPES:
        rows = t[t["school_type"] == school_type]
        if rows.empty:
            continue
        fig.add_bar(
            x=rows["draft_year"],
            y=rows["pct"],
            name=school_type,
            marker={
                "color": theme.SCHOOL_TYPE_COLORS[school_type],
                "line": {"color": "white", "width": 1},
            },
            customdata=rows["picks"],
            hovertemplate="%{x}: %{y:.1f}% (%{customdata:,} picks)<extra>%{fullData.name}</extra>",
        )
    _stack_end_labels(fig, t, "school_type", SCHOOL_TYPES)
    fig.update_xaxes(title="Draft class", dtick=1)
    fig.update_yaxes(title="Share of picks", ticksuffix="%", range=[0, 100])
    return layout(fig, barmode="stack", bargap=0.2, margin={"l": 10, "r": 140, "t": 20, "b": 40})


def _stack_end_labels(fig: go.Figure, t: pd.DataFrame, col: str, order: list[str]) -> None:
    """Direct labels at the middle of each segment of the last bar."""
    last = t[t["draft_year"] == t["draft_year"].max()].set_index(col)["pct"]
    bottom = 0.0
    for name in order:
        if name not in last.index:
            continue
        height = float(last[name])
        if height >= 3:
            fig.add_annotation(
                x=1.0,
                xref="paper",
                xanchor="left",
                y=bottom + height / 2,
                text=f" {name}",
                showarrow=False,
                font={"size": 12, "color": INK},
            )
        bottom += height


def tier_mix_bars(table: list[dict]) -> go.Figure:
    """Stacked % of each 2012-2019 class by outcome tier."""
    if not table:
        return empty_figure("No outcome tier table in the report.")
    t = pd.DataFrame(table)
    fig = go.Figure()
    for tier in TIERS:
        rows = t[t["outcome_tier"] == tier]
        if rows.empty:
            continue
        fig.add_bar(
            x=rows["draft_year"],
            y=rows["pct"],
            name=tier,
            marker={"color": theme.TIER_COLORS[tier], "line": {"color": "white", "width": 1}},
            customdata=rows["picks"],
            hovertemplate="%{x}: %{y:.1f}% (%{customdata:,} picks)<extra>%{fullData.name}</extra>",
        )
    fig.update_xaxes(title="Draft class", dtick=1)
    fig.update_yaxes(title="Share of picks", ticksuffix="%", range=[0, 100])
    fig = layout(fig, barmode="stack", bargap=0.2, margin={"l": 10, "r": 20, "t": 20, "b": 40})
    _tier_key(fig)
    fig.update_layout(legend={"y": -0.2})
    return fig


def calibration_chart(deciles: list[dict]) -> go.Figure:
    """Expected vs observed rate of reaching the majors by decile, with a y = x line."""
    if not deciles:
        return empty_figure("No calibration table in the report.")
    d = pd.DataFrame(deciles)
    top = float(max(d["expected"].max(), d["observed"].max())) * 100 * 1.08
    fig = go.Figure()
    fig.add_scatter(
        x=[0, top],
        y=[0, top],
        mode="lines",
        name="y = x",
        line={"color": BASELINE, "dash": "dash", "width": 1.5},
        hoverinfo="skip",
    )
    fig.add_scatter(
        x=d["expected"] * 100,
        y=d["observed"] * 100,
        mode="markers",
        name="deciles",
        marker={"color": COHORT, "size": 10, "line": {"color": "white", "width": 1}},
        customdata=list(zip(d["decile"], d["n"], strict=True)),
        hovertemplate=(
            "Decile %{customdata[0]}: expected %{x:.1f}%, observed %{y:.1f}% "
            "(n=%{customdata[1]:,})<extra></extra>"
        ),
    )
    fig.add_annotation(
        x=top * 0.97,
        y=top * 0.97,
        text="Perfect calibration",
        showarrow=False,
        xanchor="right",
        yanchor="bottom",
        font={"color": MUTED, "size": 12},
    )
    fig.update_xaxes(title="Expected (from the pick)", ticksuffix="%", range=[0, top])
    fig.update_yaxes(title=f"Observed: {REACHED.lower()}", ticksuffix="%", range=[0, top])
    return layout(fig, height=360, margin={"l": 10, "r": 20, "t": 20, "b": 40})
