"""Explorer: the track record of MLB draftees like the ones you pick in the sidebar.

Run with `make app` (uv run streamlit run app/Explorer.py).
"""

from __future__ import annotations

import streamlit as st

from lib import charts, fmt, metrics, ui
from lib.data import (
    Filters,
    apply_filters,
    conference_group_options,
    load_outcomes,
    school_options,
)
from lib.metrics import METRICS, TREND_METRICS, OutcomeRules
from lib.schema import (
    AGE_BANDS,
    BONUS_BANDS,
    GROUP_BY,
    OUTCOME_YEAR_MAX,
    POSITION_GROUPS,
    SCHOOL_TYPES,
    SLOT_BANDS,
    TABLE_COLUMNS,
    YEAR_MAX,
    YEAR_MIN,
)

ui.page_setup("Explorer")
df = load_outcomes()

# --- sidebar filters -----------------------------------------------------------------------

DEFAULTS = {
    "f_years": (YEAR_MIN, YEAR_MAX),
    "f_school_types": [],
    "f_conferences": [],
    "f_schools": [],
    "f_positions": [],
    "f_ages": [],
    "f_slots": [],
    "f_bonus": [],
    "f_unsigned": False,
    "f_hit": 5,
}


def reset_filters() -> None:
    for key, value in DEFAULTS.items():
        st.session_state[key] = list(value) if isinstance(value, list) else value


for key, value in DEFAULTS.items():
    st.session_state.setdefault(key, list(value) if isinstance(value, list) else value)

with st.sidebar:
    st.header("Filters")
    years = st.slider("Draft years", YEAR_MIN, YEAR_MAX, key="f_years")
    school_types = st.multiselect(
        "School type", SCHOOL_TYPES, key="f_school_types", placeholder="All"
    )
    conferences = st.multiselect(
        "Conference group",
        conference_group_options(df),
        key="f_conferences",
        placeholder="All",
        help="The D1 conference for 4-year D1 schools; otherwise Other 4-year, Junior college, "
        "High school or Unknown.",
    )
    options = school_options(df, tuple(conferences), tuple(school_types))
    # Drop schools that the narrowed option list no longer offers
    st.session_state["f_schools"] = [s for s in st.session_state["f_schools"] if s in options]
    schools = st.multiselect("School", options, key="f_schools", placeholder="All (type to search)")
    positions = st.multiselect(
        "Position group", POSITION_GROUPS, key="f_positions", placeholder="All"
    )
    ages = st.multiselect("Age at draft", AGE_BANDS, key="f_ages", placeholder="All")
    slots = st.multiselect(
        "Draft slot (overall pick)", SLOT_BANDS, key="f_slots", placeholder="All"
    )
    bonuses = st.multiselect("Signing bonus", BONUS_BANDS, key="f_bonus", placeholder="All")
    st.divider()
    count_unsigned = st.toggle(
        "Count unsigned picks",
        key="f_unsigned",
        help="Off: outcome metrics use signed players only. On: players who never signed "
        "count too (as not reaching MLB).",
    )
    hit_war = st.slider("Hit = career WAR of at least", 1, 20, key="f_hit")

filters = Filters(
    years=(int(years[0]), int(years[1])),
    school_types=tuple(school_types),
    conference_groups=tuple(conferences),
    schools=tuple(schools),
    position_groups=tuple(positions),
    age_bands=tuple(ages),
    slot_bands=tuple(slots),
    bonus_bands=tuple(bonuses),
)
rules = OutcomeRules(hit_war=float(hit_war), count_unsigned=count_unsigned)
cohort = apply_filters(df, filters)
base = apply_filters(df, filters.years_only())
is_baseline = filters == filters.years_only()
label = metrics.describe_cohort(filters)

with st.sidebar:
    st.markdown(f"**{fmt.count(len(cohort))} picks match**")
    st.button("Reset filters", on_click=reset_filters, width="stretch")

# --- header --------------------------------------------------------------------------------

st.title("College Draft Explorer")
st.markdown(
    "What's the track record of MLB draftees like these? Pick a group in the sidebar and "
    "every panel updates. The grey baseline is all draftees from the same draft years."
)
if filters.years[1] > OUTCOME_YEAR_MAX:
    st.caption("Outcomes use 2012–2019 classes; newer players haven't had time to develop.")

if cohort.empty:
    st.warning(
        "No picks match these filters. Try removing a filter or widening the draft years, "
        "or press **Reset filters** in the sidebar."
    )
    st.stop()

# --- 1. summary tiles ------------------------------------------------------------------------

summary = metrics.cohort_summary(cohort, rules)
base_summary = metrics.cohort_summary(base, rules)
enough = summary.outcome_n >= metrics.MIN_OUTCOME_ROWS
who = "players" if count_unsigned else "signed players"


def outcome(value: str) -> str:
    return value if enough else fmt.DASH


tiles = [
    ("Picks", fmt.count(summary.picks), fmt.count(base_summary.picks), "Draft picks matching."),
    (
        "Signed",
        fmt.pct(summary.signed_pct),
        fmt.pct(base_summary.signed_pct),
        "Share of picks who signed with the drafting team.",
    ),
    (
        "Reached MLB",
        outcome(fmt.pct(summary.mlb_pct)),
        fmt.pct(base_summary.mlb_pct),
        f"Share of 2012–2019 {who} who played in the majors.",
    ),
    (
        "Years to debut",
        outcome(fmt.years(summary.years_to_debut)),
        fmt.years(base_summary.years_to_debut),
        "Median years from draft day to MLB debut, for players who debuted.",
    ),
    (
        "WAR per player",
        outcome(fmt.war(summary.war_per_player)),
        fmt.war(base_summary.war_per_player),
        f"Average career WAR per 2012–2019 {who.removesuffix('s')}, counting 0 for "
        "players who never debuted.",
    ),
    (
        f"Hit % ({hit_war}+ WAR)",
        outcome(fmt.pct(summary.hit_pct)),
        fmt.pct(base_summary.hit_pct),
        f"Share of 2012–2019 {who} with at least {hit_war} career WAR.",
    ),
]
for col, (name, value, baseline, help_text) in zip(st.columns(6), tiles, strict=True):
    with col:
        st.metric(name, value, help=help_text, border=True)
        st.caption(f"All draftees: {baseline}")
ui.takeaway(metrics.takeaway_summary(label, summary, base_summary, rules, is_baseline))

if not enough:
    st.info(
        f"Fewer than {metrics.MIN_OUTCOME_ROWS} {who} from the 2012–2019 classes match these "
        "filters, so the outcome panels are hidden. Widen the filters to see them."
    )
else:
    # --- 2. compare groups -------------------------------------------------------------------
    st.subheader("Compare groups")
    c1, c2, c3 = st.columns(3)
    group_label = c1.selectbox("Group by", list(GROUP_BY), key="cmp_by")
    metric_key = c2.selectbox(
        "Metric", list(METRICS), format_func=lambda k: METRICS[k].label, key="cmp_metric"
    )
    min_n = c3.slider("Minimum players per group", 5, 200, 20, step=5, key="cmp_min_n")
    stats = metrics.group_stats(cohort, GROUP_BY[group_label], metric_key, min_n, rules)
    baseline_value = metrics.metric_stat(base, metric_key, rules).value
    ui.chart(charts.compare_bars(stats.table, metric_key, baseline_value), key="compare")
    n_means = {
        "median_bonus": "picks with a known bonus",
        "years_to_debut": "players who reached MLB",
    }.get(metric_key, f"2012–2019 {who}")
    notes = [f"n = {n_means}."]
    if METRICS[metric_key].kind == "rate":
        notes.append("Whiskers show 90% Wilson intervals.")
    elif METRICS[metric_key].kind == "mean":
        notes.append("Whiskers show the mean ± 1.645 standard errors (90%).")
    if len(stats.table) > 25:
        notes.append(f"Showing the top 25 of {len(stats.table)} groups.")
    groups = "group" if stats.hidden == 1 else "groups"
    notes.append(f"{stats.hidden} {groups} hidden (fewer than {min_n} players).")
    st.caption(ui.md(" ".join(notes)))
    ui.takeaway(metrics.takeaway_compare(stats.table, metric_key, baseline_value))

    # --- 3. draft slot curve -----------------------------------------------------------------
    st.subheader("Draft slot curve")
    cohort_curve = metrics.slot_curve(cohort, rules)
    # with no filters the cohort is the baseline; draw it once
    base_curve = cohort_curve.iloc[0:0] if is_baseline else metrics.slot_curve(base, rules)
    ui.chart(charts.slot_chart(cohort_curve, base_curve, label), key="slot")
    st.caption(f"Share of 2012–2019 {who} who reached MLB, by overall pick (90% intervals).")
    ui.takeaway(metrics.takeaway_slot(cohort_curve, base_curve, label, is_baseline))

    # --- 4. bonus vs outcome -----------------------------------------------------------------
    st.subheader("Bonus vs. outcome")
    points = metrics.bonus_points(cohort)
    ui.chart(charts.bonus_scatter(points), key="bonus")
    st.caption("Bonus data is thin after round 10 for 2012–2016 and 2018–2019.")
    ui.takeaway(metrics.takeaway_bonus(points))

# --- 5. trend by draft class -------------------------------------------------------------------

st.subheader("Trend by draft class")
t1, t2, t3 = st.columns([1, 1, 2])
trend_label = t1.selectbox("Metric", list(TREND_METRICS), key="trend_metric")
line_dim = t2.radio("Lines for", ["Conference group", "School"], horizontal=True, key="trend_dim")
line_col = "conference_group" if line_dim == "Conference group" else "school"
line_options = cohort[line_col].value_counts().index.tolist()
picked = schools if line_col == "school" else conferences
default_lines = [x for x in picked if x in line_options][:4] or line_options[:4]
chosen = t3.multiselect(
    f"{line_dim}s to compare (up to 4)", line_options, default=default_lines, max_selections=4
)
lines = {name: cohort[cohort[line_col] == name] for name in chosen}
trend = metrics.trend_table(
    base, cohort, lines, TREND_METRICS[trend_label], rules, cohort_label=label
)
ui.chart(charts.trend_chart(trend, trend_label), key="trend")
trend_notes = {
    "Share of picks": "Share of each draft class made up of these picks.",
    "Median bonus": "Median signing bonus among picks with a known bonus.",
    "MLB %": f"Share of {who} who reached MLB; 2012–2019 classes only.",
}
st.caption(trend_notes[trend_label])
ui.takeaway(metrics.takeaway_trend(trend, trend_label))

# --- 6. player table ---------------------------------------------------------------------------

st.subheader("Players")
table = cohort[list(TABLE_COLUMNS)].rename(columns=TABLE_COLUMNS)
number = st.column_config.NumberColumn
st.dataframe(
    table,
    hide_index=True,
    height=420,
    column_config={
        "Year": number(format="%d"),
        "Pick": number(format="%d"),
        "Age at draft": number(format="%.1f"),
        "Bonus": number(format="$%,d"),
        "Slot value": number(format="$%,d"),
        "Years to debut": number(format="%.1f"),
        "Career WAR": number(format="%.1f"),
    },
)
st.download_button(
    "Download CSV",
    table.to_csv(index=False).encode(),
    file_name="draft_picks.csv",
    mime="text/csv",
)
ui.takeaway(metrics.takeaway_table(cohort))
