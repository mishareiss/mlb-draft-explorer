"""Small Streamlit helpers shared by the pages."""

from __future__ import annotations

import html
from dataclasses import dataclass

import plotly.graph_objects as go
import streamlit as st

from lib.theme import INK, MUTED, PLOTLY_CONFIG, SAME

_CSS = f"""
<style>
.block-container {{ padding-top: 2.2rem; }}
[data-testid="stHeading"] h3 {{ font-size: 1.3rem; line-height: 1.35; }}
.tile {{ border: 1px solid #e3e6ea; border-radius: 0.5rem; padding: 0.7rem 0.9rem;
         min-height: 8.2rem; background: white; }}
.tile-label {{ font-size: 0.9rem; color: {MUTED}; }}
.tile-value {{ font-size: 1.8rem; font-weight: 600; color: {INK}; line-height: 1.3; }}
.tile-delta {{ font-size: 0.88rem; font-weight: 600; }}
.cohort {{ font-size: 1.05rem; color: {INK}; margin: 0.2rem 0 0.4rem; }}
</style>
"""


def page_setup(title: str) -> None:
    st.set_page_config(page_title=f"{title} · MLB Draft Explorer", layout="wide")
    st.markdown(_CSS, unsafe_allow_html=True)


def md(text: str) -> str:
    """Escape '$' so Streamlit markdown doesn't read dollar amounts as LaTeX."""
    return text.replace("$", r"\$")


def heading(takeaway: str, caption: str) -> None:
    """A panel heading: the data-generated takeaway, with what the chart shows underneath."""
    st.subheader(md(takeaway), anchor=False)
    st.caption(md(caption))


def chart(fig: go.Figure, key: str) -> None:
    st.plotly_chart(fig, config=PLOTLY_CONFIG, theme=None, key=key)


@dataclass(frozen=True)
class Tile:
    label: str
    value: str
    delta: str
    color: str = MUTED
    help: str = ""


def text_color(mark_color: str) -> str:
    """Delta text color: the significance color, with a darker grey for readable grey text."""
    return MUTED if mark_color == SAME else mark_color


def tiles(items: list[Tile]) -> None:
    for col, t in zip(st.columns(len(items)), items, strict=True):
        col.markdown(
            f"<div class='tile' title='{html.escape(t.help, quote=True)}'>"
            f"<div class='tile-label'>{html.escape(t.label)}</div>"
            f"<div class='tile-value'>{html.escape(t.value)}</div>"
            f"<div class='tile-delta' style='color:{text_color(t.color)}'>"
            f"{html.escape(t.delta)}</div></div>",
            unsafe_allow_html=True,
        )


def cohort_line(text: str) -> None:
    st.markdown(f"<div class='cohort'>{md(html.escape(text))}</div>", unsafe_allow_html=True)
