from datetime import date

import pytest

from ingest.build_draft_dates import parse_start_date


def infobox(cell: str, label: str = "Date") -> str:
    return (
        '<table class="infobox"><tr><th scope="row" class="infobox-label">'
        f'{label}</th><td class="infobox-data">{cell}</td></tr>'
        '<tr><th scope="row" class="infobox-label">Location</th>'
        '<td class="infobox-data">Secaucus, New Jersey</td></tr></table>'
    )


def test_parses_first_day_of_range():
    assert parse_start_date(infobox("June 10–11, 2020")) == date(2020, 6, 10)
    assert parse_start_date(infobox("July 13–14, 2025")) == date(2025, 7, 13)


def test_parses_linked_and_plural_label():
    html = infobox('<a href="/wiki/June_4">June 4</a>&#8211;6, 2012', label="Date(s)")
    assert parse_start_date(html) == date(2012, 6, 4)


def test_missing_date_row_raises():
    with pytest.raises(ValueError):
        parse_start_date("<table><tr><th>Location</th><td>Omaha</td></tr></table>")
