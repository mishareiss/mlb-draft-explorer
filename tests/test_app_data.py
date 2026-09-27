import pytest
from app_fixture import make_outcomes

from lib.data import Filters, apply_filters, conference_group_options, school_options


@pytest.fixture
def df():
    return make_outcomes()


def test_empty_selection_means_all(df):
    assert len(apply_filters(df, Filters())) == 40


@pytest.mark.parametrize(
    ("filters", "expected"),
    [
        (Filters(years=(2022, 2025)), 10),
        (Filters(years=(2012, 2019)), 30),
        (Filters(school_types=("High school",)), 6),
        (Filters(conference_groups=("Southeastern",)), 15),
        (Filters(schools=("Delta CC",)), 9),
        (Filters(schools=("Delta CC", "Gamma HS")), 15),
        (Filters(position_groups=("RHP",)), 10),
        (Filters(age_bands=("21",)), 10),
        (Filters(slot_bands=("1–10",)), 20),
        (Filters(bonus_bands=("Unsigned",)), 4),
    ],
)
def test_each_filter_narrows(df, filters, expected):
    assert len(apply_filters(df, filters)) == expected


def test_filters_combine(df):
    f = Filters(years=(2015, 2015), conference_groups=("Southeastern",), position_groups=("RHP",))
    out = apply_filters(df, f)
    assert len(out) == 3
    assert set(out["school"]) == {"Alpha U"} and set(out["position_group"]) == {"RHP"}


def test_no_match_is_empty(df):
    f = Filters(school_types=("High school",), conference_groups=("Southeastern",))
    assert apply_filters(df, f).empty


def test_school_options_narrow_by_conference(df):
    assert school_options(df) == ["Alpha U", "Beta State", "Delta CC", "Gamma HS"]
    assert school_options(df, ("Southeastern",)) == ["Alpha U"]
    assert school_options(df, ("Southeastern", "Junior college")) == ["Alpha U", "Delta CC"]
    assert school_options(df, school_types=("High school",)) == ["Gamma HS"]


def test_conference_group_options_put_d1_first(df):
    assert conference_group_options(df) == [
        "Big West",
        "Southeastern",
        "Junior college",
        "High school",
    ]


def test_years_only_is_the_baseline():
    f = Filters(years=(2014, 2016), schools=("Alpha U",))
    assert f.years_only() == Filters(years=(2014, 2016))
