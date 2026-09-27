import pandas as pd
import pytest
from app_fixture import make_outcomes

from lib.data import (
    PRESETS,
    Filters,
    apply_filters,
    conference_group_options,
    from_query_params,
    matching_preset,
    school_options,
    to_query_params,
    top_rounds,
)
from lib.schema import HITTER_GROUPS, NO_SCHOOL


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
        (Filters(bonus_bands=("Unsigned",)), 4),
    ],
)
def test_each_filter_narrows(df, filters, expected):
    assert len(apply_filters(df, filters)) == expected


@pytest.mark.parametrize(
    ("picks", "expected"),
    [
        ((1, 1238), 40),
        ((1, 10), 20),  # picks 1-10 in both classes
        ((1, 1), 2),
        ((10, 10), 2),
        ((11, 11), 1),  # 2022 stops at pick 10
        ((30, 30), 1),
        ((31, 1238), 0),
    ],
)
def test_pick_range_filter_edges(df, picks, expected):
    assert len(apply_filters(df, Filters(picks=picks))) == expected


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
    assert not f.is_baseline and f.years_only().is_baseline
    assert not Filters(picks=(1, 100)).is_baseline


# --- top 5 rounds --------------------------------------------------------------------------


def _rounds_frame() -> pd.DataFrame:
    # one class: round 1 (picks 1-2), a supplemental pick (3), round 5 (4 and 6) with a
    # supplemental pick inside it (5), then round 6 (7) and a later supplemental pick (8)
    return pd.DataFrame(
        {
            "draft_year": [2020] * 8,
            "pick_number": [1, 2, 3, 4, 5, 6, 7, 8],
            "round_number": [1, 1, None, 5, None, 5, 6, None],
        }
    )


def test_top_rounds_keeps_supplemental_picks_inside_round_5():
    kept = top_rounds(_rounds_frame())["pick_number"].tolist()
    assert kept == [1, 2, 3, 4, 5, 6]  # first pick of round 6 (7) and pick 8 dropped


def test_top_rounds_cuts_a_filtered_frame_at_the_real_round_5():
    all_picks = _rounds_frame()
    subset = all_picks[all_picks["pick_number"].isin([1, 5, 7])]  # no round-5 pick of its own
    assert top_rounds(subset, all_picks)["pick_number"].tolist() == [1, 5]


def test_top_rounds_per_class():
    frame = pd.concat(
        [
            _rounds_frame(),
            _rounds_frame().assign(draft_year=2021, pick_number=lambda d: d.pick_number * 2),
        ]
    )
    kept = top_rounds(frame)
    assert kept.groupby("draft_year")["pick_number"].max().to_dict() == {2020: 6, 2021: 12}


# --- presets -------------------------------------------------------------------------------


def test_presets_map_to_exact_filters():
    assert PRESETS == {
        "SEC college arms": Filters(
            school_types=("4-year college",),
            conference_groups=("Southeastern",),
            position_groups=("RHP", "LHP"),
        ),
        "Prep shortstops": Filters(school_types=("High school",), position_groups=("2B/SS",)),
        "JUCO bats": Filters(
            school_types=("Junior college",), position_groups=("C", "1B/3B", "2B/SS", "OF", "Other")
        ),
        "Top-100 college hitters": Filters(
            school_types=("4-year college",), picks=(1, 100), position_groups=tuple(HITTER_GROUPS)
        ),
        "$1M+ high schoolers": Filters(
            school_types=("High school",), bonus_bands=("$1M–$3M", "$3M+")
        ),
    }
    for name, f in PRESETS.items():
        assert f.years == (2012, 2025)  # presets clear everything they don't set
        assert matching_preset(f) == name
    assert matching_preset(Filters()) is None


# --- shareable URLs ------------------------------------------------------------------------

EVERY_FILTER = Filters(
    years=(2014, 2019),
    school_types=("4-year college", NO_SCHOOL),
    conference_groups=("Southeastern", "Big West"),
    schools=("Alpha U",),
    position_groups=("RHP", "2B/SS"),
    age_bands=("≤18", "23+"),
    picks=(5, 250),
    bonus_bands=("$1M–$3M", "<$100k"),
)


@pytest.mark.parametrize("f", [Filters(), EVERY_FILTER, *PRESETS.values()])
@pytest.mark.parametrize("count_unsigned", [False, True])
def test_query_params_round_trip(f, count_unsigned):
    assert from_query_params(to_query_params(f, count_unsigned)) == (f, count_unsigned)


def test_query_params_only_carry_changes():
    assert to_query_params(Filters()) == {}
    assert to_query_params(Filters(picks=(1, 100)), count_unsigned=True) == {
        "pick": ["1-100"],
        "unsigned": ["1"],
    }


def test_query_params_ignore_junk():
    f, unsigned = from_query_params({"class": ["abc"], "pick": ["0-99999"], "other": ["x"]})
    assert f == Filters(picks=(1, 1238)) and not unsigned
