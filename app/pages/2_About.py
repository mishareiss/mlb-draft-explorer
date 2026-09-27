"""About: the question, how to use the tool, definitions and sources."""

from __future__ import annotations

import streamlit as st

from lib import ui
from lib.schema import TIER_DEFINITIONS

ui.page_setup("About")

tiers = "\n".join(f"  - **{tier}:** {text}." for tier, text in TIER_DEFINITIONS.items())

st.title("About")
st.markdown(
    ui.md(
        f"""
**The question:** when a team drafts a player like this one, how have similar players
turned out? The tool covers every MLB draft pick from 2012 to 2025 and lets you slice them
by school, conference, school type, position, age at draft, where they were picked and what
they signed for.

### How to use it
- Pick a group in the Explorer sidebar, or start from a preset such as *SEC college arms*.
- Read each panel's headline: it's the takeaway for the group you picked, compared with all
  draftees from the same draft classes.
- *Rankings* ranks conferences, schools, positions or signing bonus bands; *Draft slot*
  compares the group with what their picks predict; *Money* shows what each signing bonus
  bought; *Trends* follows the group by draft class; *Players* lists everyone and downloads
  as CSV.
- Copy the page URL to share exactly what you're looking at.

### Definitions
- **Reached the majors:** played in at least one major-league game.
- **Became a regular (5+ WAR):** at least 5 career Wins Above Replacement
  (Baseball-Reference, through the latest season).
- **vs. draft slot:** how much more or less often a group reached the majors than players
  taken at the same picks, in percentage points. The expectation comes from a model fit on
  every 2012–2019 pick that predicts the chance of reaching the majors from the pick number
  alone.
- **Outcome tiers** sort every 2012–2019 pick by what it produced:
{tiers}
- **About the same:** a difference whose 90% interval includes zero is shown in grey; only
  differences clear of zero are blue (above) or orange (below).
- **Signed:** the player signed with the team that drafted him. **Signed for** is the
  signing bonus.
- **Picked at:** the overall pick number. **Draft class:** the year of the draft.
- **Final draft:** a player drafted more than once (say, out of high school and again out of
  college) counts once for outcomes, on his last draft.
- **Outcome-eligible:** final-draft picks from the 2012–2019 classes. Newer players haven't
  had time to develop, so outcomes leave them out. By default only signed players count;
  turn on *Count unsigned picks* in the sidebar's Settings to include the rest.

### Data sources
- [MLB Stats API](https://statsapi.mlb.com): draft picks, player details and debut dates.
- [Baseball-Reference](https://www.baseball-reference.com): career WAR and 2012–2016
  signing bonuses.
- [Wikipedia](https://en.wikipedia.org): college conference membership and draft dates.

### How it's built
Python ingest → DuckDB SQL models → expected-by-pick model → quality checks → Streamlit.
Code: [github.com/mishareiss/mlb-draft-explorer](https://github.com/mishareiss/mlb-draft-explorer)

Built by Misha Reiss.
"""
    )
)
