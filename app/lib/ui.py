"""Small Streamlit helpers shared by the pages."""

from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from lib.charts import PLOTLY_CONFIG

_CSS = """
<style>
.block-container { padding-top: 2.2rem; }
[data-testid="stMetricValue"] { font-size: 1.7rem; }
</style>
"""


def page_setup(title: str) -> None:
    st.set_page_config(page_title=f"{title} · MLB Draft Explorer", layout="wide")
    st.markdown(_CSS, unsafe_allow_html=True)


def md(text: str) -> str:
    """Escape '$' so Streamlit markdown doesn't read dollar amounts as LaTeX."""
    return text.replace("$", r"\$")


def takeaway(text: str) -> None:
    st.markdown(f"**Takeaway:** {md(text)}")


def chart(fig: go.Figure, key: str) -> None:
    st.plotly_chart(fig, config=PLOTLY_CONFIG, theme=None, key=key)
