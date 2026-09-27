"""Data Quality: the checks every build runs, coverage tables and known limitations."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from lib import charts, ui
from lib.data import load_quality
from lib.schema import check_label

ui.page_setup("Data Quality")
report = load_quality()

STATUS = {"pass": ("Pass", "green"), "warn": ("Warning", "orange"), "fail": ("Fail", "red")}

st.title("Data quality")
st.markdown(
    "Every build runs these checks; a failure stops the pipeline. "
    f"This build has {report['rows']:,} picks: "
    f"{report['summary']['pass']} checks pass, {report['summary']['warn']} warn and "
    f"{report['summary']['fail']} fail."
)


def show(value: object) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:,.2f}".rstrip("0").rstrip(".")
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)


st.subheader("Checks")
widths = [3, 1, 1, 1, 4]
headers = ["Check", "Status", "Value", "Threshold", "Details"]
for col, head in zip(st.columns(widths), headers, strict=True):
    col.markdown(f"**{head}**")
for check in report["checks"]:
    name, status, value, threshold, details = st.columns(widths, vertical_alignment="center")
    name.markdown(ui.md(check_label(check["name"])))
    text, color = STATUS.get(check["status"], (check["status"], "gray"))
    with status:
        st.badge(text, color=color)
    value.markdown(show(check["value"]))
    threshold.markdown(show(check["threshold"]))
    examples = check.get("examples") or []
    with details.expander(f"Details{f' ({len(examples)} examples)' if examples else ''}"):
        st.markdown(ui.md(check["detail"]))
        if examples:
            st.dataframe(pd.DataFrame(examples), hide_index=True)

tables = report.get("tables", {})
st.subheader("Bonus coverage")
st.caption("Share of picks with a known signing bonus, by draft class and round.")
ui.chart(charts.coverage_heatmap(tables.get("bonus_coverage_by_year_round_band", [])), "coverage")

st.subheader("School type by draft class")
ui.chart(charts.school_mix_bars(tables.get("school_type_mix_by_year", [])), "school_mix")

st.subheader("Known limitations")
st.markdown(
    ui.md(
        """
- **Conferences** use the spring-2024 alignment for every draft from 2012 to 2024 (2025 uses
  the spring-2025 alignment). Realignment before 2024 isn't modeled.
- **Division** (D1 and so on) reflects a school's current membership, not its membership in
  the draft year.
- **Bonuses after round 10** are sparse for 2012–2016 (from Baseball-Reference) and for
  2018–2019 (MLB lists $0 placeholders there, which are treated as missing).
- **"Unsigned"** in the late rounds of 2018–2019 really means unsigned or unknown.
- **Position** is the player's current listed position, which may differ from his position at
  the draft.
- **"Other 4-year"** mixes D2, D3 and NAIA schools with a few D1 schools the lookup didn't
  match.
"""
    )
)
