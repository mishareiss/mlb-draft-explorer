"""Data Quality: the checks every build runs, coverage tables and known limitations."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from lib import charts, metrics, ui
from lib.data import load_quality
from lib.schema import check_label

ui.page_setup("Data Quality")
report = load_quality()
tables = report.get("tables", {})

# No red or green: pass is blue, a warning orange, a failure violet
STATUS = {"pass": ("Pass", "blue"), "warn": ("Warning", "orange"), "fail": ("Fail", "violet")}

st.title("Data quality")


def show(value: object) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:,.2f}".rstrip("0").rstrip(".")
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)


ui.heading(
    metrics.takeaway_checks(report),
    "Every build runs these checks; a failure stops the pipeline.",
)
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

deciles = tables.get("slot_model", {}).get("curves", {}).get("exp_mlb_signed", {})
deciles = deciles.get("loco_deciles", [])
ui.heading(
    metrics.takeaway_calibration(deciles),
    "Expected-by-pick model vs. what happened: signed 2012–2019 players split into ten "
    "equal-size groups by expected chance of reaching the majors. Each class is predicted by "
    "a model fit on the other classes. The dashed line is perfect calibration.",
)
left, _ = st.columns([3, 2])
with left:
    ui.chart(charts.calibration_chart(deciles), "calibration")

tier_table = tables.get("outcome_tier_mix_by_year", [])
ui.heading(
    metrics.takeaway_tier_mix(tier_table),
    "Outcome tier of every 2012–2019 pick by draft class; a non-final or unsigned pick "
    "counts as Didn't sign.",
)
ui.chart(charts.tier_mix_bars(tier_table), "tier_mix")

coverage = tables.get("bonus_coverage_by_year_round_band", [])
ui.heading(
    metrics.takeaway_coverage(coverage),
    "Share of picks with a known signing bonus, by draft class and round.",
)
ui.chart(charts.coverage_heatmap(coverage), "coverage")

school_mix = tables.get("school_type_mix_by_year", [])
ui.heading(metrics.takeaway_school_mix(school_mix), "Share of each draft class by school type.")
ui.chart(charts.school_mix_bars(school_mix), "school_mix")

st.subheader("Known limitations", anchor=False)
st.markdown(
    ui.md(
        """
- **Outcome tiers are lenient for 2018–2019.** Tiers use career WAR to date, so those
  classes have had fewer seasons to reach Regular (5+ WAR) or Star (15+ WAR).
- **The expected-by-pick model** is fit on the 2012–2019 classes and reused for later
  classes, whose outcomes aren't in yet.
- **Conferences** use the spring-2024 alignment for every draft from 2012 to 2024 (2025 uses
  the spring-2025 alignment). Realignment before 2024 isn't modeled.
- **Division** (D1 and so on) reflects a school's current membership, not its membership in
  the year of the draft.
- **Signing bonuses after round 10** are sparse for 2012–2016 (from Baseball-Reference) and
  for 2018–2019 (MLB lists $0 placeholders there, which are treated as missing).
- **"Unsigned"** in the late rounds of 2018–2019 really means unsigned or unknown.
- **Position** is the player's current listed position, which may differ from his position at
  the draft.
- **Team** shows the franchise's current name (a 2012 Indians pick is listed under the
  Cleveland Guardians).
- **"Other 4-year"** mixes D2, D3 and NAIA schools with a few D1 schools the lookup didn't
  match.
"""
    )
)
