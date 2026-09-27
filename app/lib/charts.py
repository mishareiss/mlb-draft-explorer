"""Plotly figure builders, one per panel. No Streamlit calls, so each is testable.

Colors: ACCENT is the selected cohort, GREY (dashed) the all-draftee baseline. Categorical
series take CATEGORICAL in fixed order (validated for color-vision deficiency).
Every builder returns a figure with no traces and a short message when given no data.
"""

from __future__ import annotations

import math

import pandas as pd
import plotly.graph_objects as go

from lib import fmt
from lib.metrics import EXTREME_BARS, MAX_BARS, METRICS, format_value, shown_groups
from lib.schema import ROUND_BANDS, SCHOOL_TYPES, SLOT_BANDS

ACCENT = "#1f5fbf"
GREY = "#9aa0a6"
INK = "#1f2328"
MUTED = "#5f6368"
GRIDLINE = "#e8eaed"
CATEGORICAL = [ACCENT, "#eb6834", "#1baf7a", "#4a3aa7"]
SCHOOL_TYPE_COLORS = dict(zip(SCHOOL_TYPES, [ACCENT, "#1baf7a", "#eb6834", GREY], strict=True))
PLOTLY_CONFIG = {"displayModeBar": False}

# How each unit is plotted: multiplier into axis units, and axis tick settings
_AXIS = {
    "pct": (100.0, {"ticksuffix": "%", "rangemode": "tozero"}),
    "war": (1.0, {}),
    "years": (1.0, {"ticksuffix": " yrs"}),
    "usd": (1.0, {"tickprefix": "$", "tickformat": "~s", "rangemode": "tozero"}),
}


def _layout(fig: go.Figure, height: int = 380, **kwargs) -> go.Figure:
    fig.update_layout(
        template="plotly_white",
        height=height,
        margin={"l": 10, "r": 20, "t": 40, "b": 40},
        font={"family": "Source Sans Pro, sans-serif", "size": 13, "color": INK},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "x": 0, "title": None},
        hoverlabel={"bgcolor": "white", "font_color": INK},
        **kwargs,
    )
    fig.update_xaxes(gridcolor=GRIDLINE, zeroline=False, linecolor=GRIDLINE)
    fig.update_yaxes(gridcolor=GRIDLINE, zeroline=False, linecolor=GRIDLINE)
    return fig


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
    return _layout(fig, height=height)


def compare_bars(
    table: pd.DataFrame,
    metric: str,
    baseline: float,
    max_bars: int = MAX_BARS,
    keep: int = EXTREME_BARS,
) -> go.Figure:
    """Horizontal bars, highest value on top; n in each label; dashed baseline.

    With more than max_bars groups, only the `keep` highest and `keep` lowest are drawn,
    with a gap between them.
    """
    if table.empty:
        return empty_figure("No groups meet the minimum sample size.")
    m = METRICS[metric]
    mult, axis = _AXIS[m.unit]
    split = len(table) > max_bars
    t = shown_groups(table, max_bars, keep).iloc[::-1]
    labels = [f"{g} (n={n:,})" for g, n in zip(t["group"], t["n"], strict=True)]
    # numeric rows (bottom = 0) so the split can leave a gap a categorical axis can't
    gap = 0.8 if split else 0.0
    rows = [i + (gap if split and i >= keep else 0.0) for i in range(len(t))]
    has_interval = m.kind != "median" and t["lo"].notna().any()
    interval = [
        f"{format_value(metric, lo)} to {format_value(metric, hi)}"
        for lo, hi in zip(t["lo"], t["hi"], strict=True)
    ]
    custom = list(
        zip(
            [format_value(metric, v) for v in t["value"]],
            interval,
            [f"{n:,}" for n in t["n"]],
            labels,
            strict=True,
        )
    )
    fig = go.Figure(
        go.Bar(
            x=t["value"] * mult,
            y=rows,
            orientation="h",
            marker={"color": ACCENT, "cornerradius": 4},
            error_x=(
                {
                    "type": "data",
                    "symmetric": False,
                    "array": ((t["hi"] - t["value"]) * mult).clip(lower=0),
                    "arrayminus": ((t["value"] - t["lo"]) * mult).clip(lower=0),
                    "color": INK,
                    "thickness": 1.2,
                    "width": 3,
                }
                if has_interval
                else None
            ),
            customdata=custom,
            hovertemplate=(
                "<b>%{customdata[3]}</b><br>"
                + m.label
                + ": %{customdata[0]}"
                + ("<br>90% interval: %{customdata[1]}" if has_interval else "")
                + "<br>Players: %{customdata[2]}<extra></extra>"
            ),
            name=m.label,
        )
    )
    if pd.notna(baseline):
        fig.add_vline(
            x=baseline * mult,
            line={"dash": "dash", "color": GREY, "width": 2},
            annotation_text=f"All draftees: {format_value(metric, baseline)}",
            annotation_position="top",
            annotation_font_color=MUTED,
        )
    fig.update_xaxes(title=m.label, **axis)
    if split:
        fig.add_hline(y=keep - 0.5 + gap / 2, line={"dash": "dot", "color": GREY, "width": 1})
    fig.update_yaxes(
        title=None,
        automargin=True,
        tickvals=rows,
        ticktext=labels,
        showgrid=False,
        range=[-0.6, rows[-1] + 0.6],
    )
    height = 90 + 28 * (len(t) + gap)
    return _layout(fig, height=round(height), showlegend=False, bargap=0.25)


def slot_chart(
    cohort_curve: pd.DataFrame, base_curve: pd.DataFrame, cohort_label: str
) -> go.Figure:
    """MLB % by draft slot: cohort (accent, 90% intervals) vs all draftees (grey)."""
    if cohort_curve.empty and base_curve.empty:
        return empty_figure("No players with outcomes match these filters.")
    fig = go.Figure()
    if not base_curve.empty:
        fig.add_scatter(
            x=base_curve["group"],
            y=base_curve["value"] * 100,
            name="All draftees",
            mode="lines+markers",
            line={"color": GREY, "dash": "dash", "width": 2},
            marker={"size": 8},
            customdata=base_curve["n"],
            hovertemplate="Picks %{x}: %{y:.1f}% (n=%{customdata:,})<extra>All draftees</extra>",
        )
    if not cohort_curve.empty:
        fig.add_scatter(
            x=cohort_curve["group"],
            y=cohort_curve["value"] * 100,
            name=cohort_label,
            mode="lines+markers",
            line={"color": ACCENT, "width": 2},
            marker={"size": 9},
            error_y={
                "type": "data",
                "symmetric": False,
                "color": ACCENT,
                "thickness": 1.2,
                "array": (cohort_curve["hi"] - cohort_curve["value"]) * 100,
                "arrayminus": (cohort_curve["value"] - cohort_curve["lo"]) * 100,
            },
            customdata=cohort_curve["n"],
            hovertemplate=(
                "Picks %{x}: %{y:.1f}% (n=%{customdata:,})<extra>%{fullData.name}</extra>"
            ),
        )
    fig.update_xaxes(title="Overall pick number", categoryorder="array", categoryarray=SLOT_BANDS)
    fig.update_yaxes(title="Reached MLB", ticksuffix="%", rangemode="tozero")
    return _layout(fig)


BONUS_AXIS_MIN = 1_000  # the scatter's log axis starts here


def bonus_scatter(points: pd.DataFrame) -> go.Figure:
    """Signing bonus (log) vs career WAR, one trace per school type.

    Bonuses under BONUS_AXIS_MIN are drawn at the axis edge; hover shows the real amount.
    """
    if points.empty:
        return empty_figure("No signed 2012–2019 players with a known bonus match these filters.")
    fig = go.Figure()
    for school_type in SCHOOL_TYPES:
        rows = points[points["school_type"] == school_type]
        if rows.empty:
            continue
        custom = pd.DataFrame(
            {
                "player": rows["player_name"],
                "school": rows["school"].fillna("—"),
                "year": rows["draft_year"],
                "pick": rows["pick_number"],
                "bonus": rows["bonus_usd"].map(fmt.usd),
                "war": rows["career_war"].map(fmt.war),
            }
        )
        fig.add_scatter(
            x=rows["bonus_usd"].clip(lower=BONUS_AXIS_MIN),
            y=rows["career_war"],
            mode="markers",
            name=school_type,
            marker={
                "color": SCHOOL_TYPE_COLORS[school_type],
                "size": 8,
                "opacity": 0.7,
                "line": {"color": "white", "width": 1},
            },
            customdata=custom.to_numpy(),
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>%{customdata[1]}<br>"
                "%{customdata[2]} draft, pick %{customdata[3]}<br>"
                "Bonus %{customdata[4]} · Career WAR %{customdata[5]}<extra></extra>"
            ),
        )
    top = max(points["bonus_usd"].max(), BONUS_AXIS_MIN * 10)
    fig.update_xaxes(
        title="Signing bonus (log scale)",
        type="log",
        tickprefix="$",
        tickformat="~s",
        range=[math.log10(BONUS_AXIS_MIN) - 0.05, math.log10(top) + 0.05],
    )
    fig.update_yaxes(title="Career WAR")
    return _layout(fig, height=420, showlegend=True)


def trend_chart(trend: pd.DataFrame, metric_label: str) -> go.Figure:
    """One line per selection (categorical order) plus the grey dashed reference line."""
    if trend.empty:
        return empty_figure("No draft classes match these filters.")
    is_usd = metric_label == "Median bonus"
    mult = 1.0 if is_usd else 100.0
    fig = go.Figure()
    names = list(dict.fromkeys(trend.loc[trend["role"] == "line", "line"]))
    color = {name: CATEGORICAL[i % len(CATEGORICAL)] for i, name in enumerate(names)}
    for name, rows in trend.groupby("line", sort=False):
        ref = (rows["role"] == "reference").all()
        values = [fmt.usd(v) if is_usd else fmt.pct(v) for v in rows["value"]]
        fig.add_scatter(
            x=rows["draft_year"],
            y=rows["value"] * mult,
            name=name,
            mode="lines+markers",
            line={
                "color": GREY if ref else color[name],
                "width": 2,
                "dash": "dash" if ref else None,
            },
            marker={"size": 7 if ref else 8},
            customdata=list(zip(values, rows["n"], strict=True)),
            hovertemplate=(
                "%{x}: %{customdata[0]} (n=%{customdata[1]:,})<extra>%{fullData.name}</extra>"
            ),
        )
    fig.update_xaxes(title="Draft class", dtick=1)
    axis = _AXIS["usd"][1] if is_usd else _AXIS["pct"][1]
    fig.update_yaxes(title=metric_label, **axis)
    return _layout(fig)


def coverage_heatmap(table: list[dict]) -> go.Figure:
    """% of picks with a known bonus, draft year x round band."""
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
            colorscale=[[0, "#f1f5fb"], [1, ACCENT]],
            xgap=2,
            ygap=2,
            customdata=picks.to_numpy(),
            colorbar={"title": "% with bonus", "ticksuffix": "%", "thickness": 12},
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
                    text=f"{v:.0f}",
                    showarrow=False,
                    font={"size": 11, "color": "white" if v >= 55 else INK},
                )
    fig.update_xaxes(title="Draft class", dtick=1, showgrid=False)
    fig.update_yaxes(title=None, autorange="reversed", showgrid=False)
    return _layout(fig, height=300)


def school_mix_bars(table: list[dict]) -> go.Figure:
    """Stacked % of each class by school type."""
    if not table:
        return empty_figure("No school-type table in the report.")
    t = pd.DataFrame(table)
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
                "color": SCHOOL_TYPE_COLORS[school_type],
                "line": {"color": "white", "width": 1},
            },
            customdata=rows["picks"],
            hovertemplate="%{x}: %{y:.1f}% (%{customdata:,} picks)<extra>%{fullData.name}</extra>",
        )
    fig.update_xaxes(title="Draft class", dtick=1)
    fig.update_yaxes(title="Share of picks", ticksuffix="%", range=[0, 100])
    fig.update_layout(legend_traceorder="normal")
    return _layout(fig, barmode="stack", bargap=0.2)
