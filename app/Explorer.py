"""Explorer: the track record of MLB draftees like the ones you pick in the sidebar.

Run with `make app` (uv run streamlit run app/Explorer.py).
"""

from __future__ import annotations

import streamlit as st

from lib import fmt, metrics, tabs, ui
from lib.data import (
    PRESETS,
    Filters,
    apply_filters,
    conference_group_options,
    from_query_params,
    load_curve,
    load_outcomes,
    matching_preset,
    school_options,
    to_query_params,
)
from lib.metrics import OutcomeRules
from lib.schema import (
    AGE_BANDS,
    BONUS_BANDS,
    DRAFT_CLASS,
    PICK_MAX,
    PICK_MIN,
    PICKED_AT,
    POSITION_GROUPS,
    SCHOOL_TYPES,
)

ui.page_setup("Explorer")
df = load_outcomes()

# --- filter state: session state <-> Filters <-> URL ---------------------------------------

# Filters field -> widget key
KEYS = {
    "years": "f_years",
    "school_types": "f_school_types",
    "conference_groups": "f_conferences",
    "schools": "f_schools",
    "position_groups": "f_positions",
    "age_bands": "f_ages",
    "picks": "f_picks",
    "bonus_bands": "f_bonus",
}


def write_filters(f: Filters) -> None:
    for field, key in KEYS.items():
        value = getattr(f, field)
        st.session_state[key] = list(value)
        if field in ("years", "picks"):
            st.session_state[key] = tuple(value)


def reset_filters() -> None:
    write_filters(Filters())
    st.session_state["f_unsigned"] = False


def apply_preset() -> None:
    name = st.session_state.get("preset")
    if name:
        write_filters(PRESETS[name])


if "f_years" not in st.session_state:  # first run of this session: read the URL
    params = {k: st.query_params.get_all(k) for k in st.query_params}
    url_filters, url_unsigned = from_query_params(params)
    write_filters(url_filters)
    st.session_state["f_unsigned"] = url_unsigned
    if st.query_params.get("tab") in tabs.TABS:
        st.session_state["tab"] = st.query_params["tab"]

# --- sidebar -------------------------------------------------------------------------------

with st.sidebar:
    st.header("Player")
    school_types = st.multiselect(
        "School type", SCHOOL_TYPES, key="f_school_types", placeholder="All"
    )
    conferences = st.multiselect(
        "Conference",
        conference_group_options(df),
        key="f_conferences",
        placeholder="All",
        help="The D1 conference for 4-year D1 schools; otherwise Other 4-year, Junior "
        "college, High school or No school / unclassified.",
    )
    options = school_options(df, tuple(conferences), tuple(school_types))
    # Drop schools that the narrowed option list no longer offers
    st.session_state["f_schools"] = [s for s in st.session_state["f_schools"] if s in options]
    schools = st.multiselect("School", options, key="f_schools", placeholder="All (type to search)")
    positions = st.multiselect(
        "Position group", POSITION_GROUPS, key="f_positions", placeholder="All"
    )
    ages = st.multiselect("Age at draft", AGE_BANDS, key="f_ages", placeholder="All")

    st.header("Draft")
    years = st.slider(DRAFT_CLASS, 2012, 2025, key="f_years")
    picks = st.slider(PICKED_AT, PICK_MIN, PICK_MAX, key="f_picks", help="Overall pick number.")
    bonuses = st.multiselect("Signing bonus", BONUS_BANDS, key="f_bonus", placeholder="All")

    with st.expander("Settings"):
        count_unsigned = st.toggle(
            "Count unsigned picks",
            key="f_unsigned",
            help="Off: outcomes use signed players only. On: picks who never signed count "
            "too, as not reaching the majors, and compare with the model's all-picks curve.",
        )

filters = Filters(
    years=(int(years[0]), int(years[1])),
    school_types=tuple(school_types),
    conference_groups=tuple(conferences),
    schools=tuple(schools),
    position_groups=tuple(positions),
    age_bands=tuple(ages),
    picks=(int(picks[0]), int(picks[1])),
    bonus_bands=tuple(bonuses),
)
rules = OutcomeRules(count_unsigned=count_unsigned)
cohort = apply_filters(df, filters)

with st.sidebar:
    st.markdown(f"**{fmt.count(len(cohort))} picks match**")
    st.button("Reset filters", on_click=reset_filters, width="stretch")

# --- header --------------------------------------------------------------------------------

st.title("MLB Draft Explorer")
with st.expander("How to read this"):
    st.markdown(
        """
1. **Pick a group** in the sidebar, or start from a preset below.
2. **Read the headline** on each panel: it's the takeaway, computed from the data you picked.
3. **Compare with the grey baseline**, all draftees from the same draft classes. *vs. draft
   slot* compares a group with players taken at the same picks, so it removes the advantage
   of simply being picked early.
4. **Blue is above, orange is below, grey is about the same**: when a 90% interval includes
   zero, the difference could be noise.
"""
    )
st.session_state["preset"] = matching_preset(filters)
st.pills(
    "Presets", list(PRESETS), key="preset", on_change=apply_preset, label_visibility="collapsed"
)
ui.cohort_line(metrics.cohort_sentence(filters, cohort, rules))

st.query_params.from_dict(
    to_query_params(filters, count_unsigned)
    | (
        {"tab": st.session_state["tab"]}
        if st.session_state.get("tab", "Overview") != "Overview"
        else {}
    )
)

if cohort.empty:
    st.warning(
        "No picks match these filters. Try removing a filter or widening the draft classes, "
        "or press **Reset filters** in the sidebar."
    )
    st.stop()

view = tabs.View(
    df=df,
    cohort=cohort,
    base=apply_filters(df, filters.years_only()),
    curve=load_curve(),
    filters=filters,
    rules=rules,
    label=metrics.describe_cohort(filters),
)
for name, container in zip(
    tabs.TABS, st.tabs(tabs.TABS, key="tab", on_change="rerun"), strict=True
):
    if container.open:
        with container:
            tabs.RENDER[name](view)
