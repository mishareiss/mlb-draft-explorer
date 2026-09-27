"""The app's color system and base chart styling. Every chart takes its colors from here.

No red or green anywhere: blue is the selected cohort (or "above"), orange is "below", and
grey is the all-draftee baseline or "about the same".
"""

from __future__ import annotations

import plotly.graph_objects as go

from lib.schema import SCHOOL_TYPES, TIERS

COHORT = "#1f5fbf"  # selected cohort; "above" a baseline
BASELINE = "#9aa0a6"  # all draftees
BELOW = "#d9822b"  # clearly below a baseline
SAME = "#9aa0a6"  # interval includes zero: "about the same"

INK = "#1f2328"
MUTED = "#5f6368"
GRIDLINE = "#e8eaed"
FONT_SIZE = 13

# Ordinal, light to dark
TIER_COLORS = dict(
    zip(TIERS, ["#e3e6ea", "#b8bec6", "#c6d9f1", "#8fb3e3", "#4a82cf", "#1f4f99"], strict=True)
)
# Grey ramp for all-draftee reference bars, same ordering
TIER_GREYS = dict(
    zip(TIERS, ["#f1f3f4", "#dadce0", "#c4c7cb", "#a9adb2", "#80868b", "#5f6368"], strict=True)
)
# School types, which have a rough order: dark to light blue, then grey
SCHOOL_TYPE_COLORS = dict(
    zip(SCHOOL_TYPES, ["#1f4f99", "#4a82cf", "#8fb3e3", "#dadce0"], strict=True)
)
# Trend lines, which have no order: blue, purple, slate, sky. Never orange (that means "below")
SERIES_COLORS = ["#1f5fbf", "#7b4fb3", "#3c4650", "#58a6d8"]

PLOTLY_CONFIG = {"displayModeBar": False}


def text_on(color: str) -> str:
    """Readable label color on a fill: white on the two darkest tier blues, ink elsewhere."""
    return "white" if color in ("#4a82cf", "#1f4f99", "#1f5fbf", "#5f6368") else INK


def layout(fig: go.Figure, height: int = 380, **kwargs) -> go.Figure:
    """White background, light horizontal gridlines only, 13px text, no legend by default."""
    fig.update_layout(
        template="plotly_white",
        plot_bgcolor="white",
        paper_bgcolor="white",
        height=height,
        margin={"l": 10, "r": 20, "t": 30, "b": 40},
        font={"family": "Source Sans Pro, sans-serif", "size": FONT_SIZE, "color": INK},
        showlegend=False,
        hoverlabel={"bgcolor": "white", "font_color": INK, "font_size": FONT_SIZE},
    )
    fig.update_layout(**kwargs)
    fig.update_xaxes(showgrid=False, zeroline=False, linecolor=GRIDLINE, ticks="")
    fig.update_yaxes(gridcolor=GRIDLINE, zeroline=False, linecolor=GRIDLINE)
    return fig
