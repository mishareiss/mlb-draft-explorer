"""About: the question, how to use the tool, definitions and sources."""

from __future__ import annotations

import streamlit as st

from lib import ui

ui.page_setup("About")

st.title("About")
st.markdown(
    ui.md(
        """
**The question:** when a team drafts a player like this one, how have similar players
turned out? The tool covers every MLB draft pick from 2012 to 2025 and lets you slice them
by school, conference, school type, position, age at draft, draft slot and signing bonus.

### How to use it
- Pick a group in the Explorer sidebar, such as SEC right-handed pitchers from 4-year colleges.
- Read the tiles and takeaways: each compares your group with all draftees from the same years.
- Use *Compare groups* to rank schools or conferences, and download the matching players as CSV.

### Definitions
- **Signed:** the player signed with the team that drafted him.
- **Final draft:** a player drafted more than once (say, out of high school and again out of
  college) counts once for outcomes, on his last draft.
- **MLB %:** the share of players who appeared in at least one major-league game.
- **WAR:** career Wins Above Replacement through the latest season (Baseball-Reference);
  0 for players who never reached MLB.
- **Hit:** a player with at least the chosen career WAR (5 by default).
- **Outcome-eligible:** final-draft picks from the 2012–2019 classes. Newer players haven't had
  time to develop, so outcome metrics leave them out. By default only signed players count.

### Data sources
- [MLB Stats API](https://statsapi.mlb.com): draft picks, player details and debut dates.
- [Baseball-Reference](https://www.baseball-reference.com): career WAR and 2012–2016 bonuses.
- [Wikipedia](https://en.wikipedia.org): college conference membership and draft dates.

### How it's built
Python ingest → DuckDB SQL models → quality checks → Streamlit.
Code: [github.com/mishareiss/mlb-draft-explorer](https://github.com/mishareiss/mlb-draft-explorer)

Built by Misha Reiss.
"""
    )
)
