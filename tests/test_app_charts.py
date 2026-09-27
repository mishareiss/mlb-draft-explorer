import pandas as pd
import plotly.graph_objects as go
import pytest
from app_fixture import make_outcomes

from lib import charts, metrics, theme
from lib.metrics import OutcomeRules
from quality.checks import bonus_coverage_table, school_type_mix_table, tier_mix_table
from transform import slot_model


@pytest.fixture
def df():
    return make_outcomes()


@pytest.fixture
def expected(df):
    curve, _ = slot_model.fit_all(df)
    return metrics.expected_curve(curve, OutcomeRules())


def _trace(fig: go.Figure, name: str):
    return next(t for t in fig.data if t.name == name)


def test_tier_bars(df):
    dists = {
        "This group": metrics.tier_distribution(df[df["school"] == "Alpha U"]),
        "All draftees": metrics.tier_distribution(df),
    }
    fig = charts.tier_bars(dists)
    assert [t.name for t in fig.data] == [
        "Never reached MLB",
        "Cup of coffee",
        "Role player",
        "Regular",
        "Star",
    ]
    assert list(fig.data[0].y) == ["This group", "All draftees"]
    assert fig.data[3].marker.color == theme.TIER_COLORS["Regular"]
    assert fig.layout.showlegend  # the single tier key
    # a segment under 4% gets no label; Never reached MLB (19 of 26) does
    assert fig.data[0].text[1] == "73%" and fig.data[4].text[1] == ""


def _ranked() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "group": ["Above", "Same", "Below"],
            "value": [4.0, 1.0, -3.0],
            "lo": [1.0, -1.0, -5.0],
            "hi": [7.0, 3.0, -1.0],
            "n": [100, 80, 60],
        }
    )


def test_rank_dots_colors_follow_significance():
    fig = charts.rank_dots(_ranked(), "mlb_vs_slot", 0.0, "Expected for their picks")
    dots = _trace(fig, "dots")
    color = dict(zip([c[0] for c in dots.customdata], dots.marker.color, strict=True))
    assert color == {"Above": theme.COHORT, "Same": theme.SAME, "Below": theme.BELOW}
    assert list(fig.layout.yaxis.ticktext) == ["Below", "Same", "Above"]  # highest on top
    assert [s.line.dash for s in fig.layout.shapes] == ["dash"]  # reference line at 0
    n_labels = [a.text for a in fig.layout.annotations if a.name == "n"]
    assert n_labels == ["60", "80", "100", "n"]
    # values sit in their own column left of n, colored by significance; no whisker-tip text
    values = [a for a in fig.layout.annotations if a.name == "value"]
    assert [a.text for a in values] == ["−3.0 pts", "+1.0 pts", "+4.0 pts"]
    assert [a.font.color for a in values] == [theme.BELOW, theme.SAME, theme.COHORT]
    assert all(a.xref == "paper" and a.x < 1.0 for a in values)
    assert [t.name for t in fig.data] == ["interval", "interval", "interval", "dots"]


def test_rank_dots_against_all_draftee_value():
    table = _ranked().assign(value=[0.30, 0.22, 0.12], lo=[0.25, 0.15, 0.08], hi=[0.35, 0.3, 0.19])
    fig = charts.rank_dots(table, "mlb_pct", 0.21, "All draftees: 21.0%")
    assert list(_trace(fig, "dots").marker.color) == [theme.BELOW, theme.SAME, theme.COHORT]


def test_rank_dots_top_and_bottom_with_gap():
    table = pd.DataFrame(
        {
            "group": [f"G{i:02d}" for i in range(30)],
            "value": [0.9 - 0.02 * i for i in range(30)],
            "lo": [0.8 - 0.02 * i for i in range(30)],
            "hi": [1.0 - 0.02 * i for i in range(30)],
            "n": [50] * 30,
        }
    )
    fig = charts.rank_dots(table, "mlb_pct", 0.5, "All draftees")
    assert len(_trace(fig, "dots").y) == 24
    assert [s.line.dash for s in fig.layout.shapes].count("dot") == 1  # line in the gap


def test_rank_dots_median_has_no_interval(df):
    gs = metrics.group_stats(df, "school", "median_bonus", min_n=1)
    fig = charts.rank_dots(gs.table, "median_bonus", 300_000, "All draftees")
    assert "interval" not in [t.name for t in fig.data]


def test_slot_panels(df, expected):
    table = metrics.pick_range_table(df)
    fig = charts.slot_panels(table, expected, is_baseline=False, min_n=1)
    assert [t.name for t in fig.data] == ["expected", "cohort", "vs slot"]
    assert fig.layout.xaxis.type == "log" and list(fig.layout.xaxis.tickvals) == charts.PICK_TICKS
    assert _trace(fig, "cohort").marker.color == theme.COHORT
    assert len(_trace(fig, "vs slot").x) == len(table)
    # with no filters the dots are grey; ranges under min_n leave the bottom panel
    grey = charts.slot_panels(table, expected, is_baseline=True, min_n=9)
    assert _trace(grey, "cohort").marker.color == theme.BASELINE
    assert len(_trace(grey, "vs slot").x) == int((table["n"] >= 9).sum())


def test_money_bars(df):
    order = ["$1M–$3M", "$100k–$500k"]
    rows = metrics.money_rows(df, "What each bonus bought")
    mix = metrics.tier_mix_by(rows, "bonus_band", order)
    fig = charts.money_bars(mix, mix, order, min_n=20)
    assert len(fig.data) == 2 * 5  # a cohort and a reference trace per tier
    cohort = _trace(fig, "Regular")
    # picks 1-5 signed for $1M+ (5 players, faded); the other 21 for $100k-$500k
    assert list(cohort.marker.opacity) == [0.3, 1.0]
    assert _trace(fig, "All draftees: Regular").marker.color == theme.TIER_GREYS["Regular"]


def test_bonus_scatter_highlight(df):
    points = metrics.bonus_points(df)
    assert len(charts.bonus_scatter(points).data) == 1
    fig = charts.bonus_scatter(points, highlight=int(points["person_id"].iloc[0]))
    assert [t.name for t in fig.data] == ["players", "highlight"]
    assert fig.data[1].text[0] == points["player_name"].iloc[0]
    assert fig.layout.xaxis.type == "log"


def test_trend_chart(df):
    lines = {"Alpha U": df[df["school"] == "Alpha U"], "Delta CC": df[df["school"] == "Delta CC"]}
    trend = metrics.trend_table(df, df, lines, "median_bonus")
    fig = charts.trend_chart(trend, "Median signing bonus")
    assert len(fig.data) == 3
    assert fig.data[-1].line.color == theme.BASELINE  # the all-draftee reference
    assert not fig.layout.showlegend
    labels = {a.text.strip() for a in fig.layout.annotations}
    assert {"Alpha U", "Delta CC", "All draftees", "5-round draft", "20 rounds"} <= labels
    outcome = charts.trend_chart(
        metrics.trend_table(df, df, lines, "mlb_pct"), "Reached the majors %"
    )
    assert any("still developing" in a.text for a in outcome.layout.annotations)
    assert "Realigned conferences" not in labels
    assert all(t.line.dash == "solid" for t in fig.data[:-1])  # school lines: no dotted tail
    assert fig.data[-1].line.dash == "dash"


def _trend(lines: list[str], years=range(2022, 2026)) -> pd.DataFrame:
    rows = [
        {"line": name, "draft_year": y, "value": 0.1 + 0.01 * i, "n": 20, "role": role}
        for name, role in [(n, "line") for n in lines] + [("All draftees", "reference")]
        for i, y in enumerate(years)
    ]
    return pd.DataFrame(rows)


def test_trend_chart_conference_realignment():
    trend = _trend(["Pac-12", "Southeastern"])
    fig = charts.trend_chart(trend, "Share of picks", conference_lines=True)
    labels = {a.text.strip() for a in fig.layout.annotations}
    assert "Realigned conferences" in labels
    assert 2025 in [s.x0 for s in fig.layout.shapes]
    for name in ["Pac-12", "Southeastern"]:
        solid, tail = [t for t in fig.data if t.name == name]
        # solid through 2024, then a dotted 2024->2025 step in the same color
        assert (solid.line.dash, tail.line.dash) == ("solid", "dot")
        assert list(solid.x) == [2022, 2023, 2024] and list(tail.x) == [2024, 2025]
        assert solid.line.color == tail.line.color
    (reference,) = [t for t in fig.data if t.name == "All draftees"]
    assert reference.line.dash == "dash" and reference.line.color == theme.BASELINE
    assert list(reference.x) == [2022, 2023, 2024, 2025]

    schools = charts.trend_chart(_trend(["Alpha U"]), "Share of picks")
    assert "Realigned conferences" not in {a.text.strip() for a in schools.layout.annotations}
    assert [t.line.dash for t in schools.data] == ["solid", "dash"]


def test_trend_lines_never_use_the_below_orange(df):
    schools = df["school"].dropna().unique()[:4]
    lines = {s: df[df["school"] == s] for s in schools}
    for metric, label in [
        ("median_bonus", "Median signing bonus"),
        ("mlb_pct", "Reached the majors %"),
    ]:
        for conference_lines in (False, True):
            fig = charts.trend_chart(
                metrics.trend_table(df, df, lines, metric), label, conference_lines
            )
            assert fig.data
            for t in fig.data:
                assert t.line.color.lower() != theme.BELOW == "#d9822b"
                assert t.line.color in [*theme.SERIES_COLORS, theme.BASELINE]


def test_quality_charts(df):
    assert len(charts.coverage_heatmap(bonus_coverage_table(df)).data) == 1
    assert len(charts.school_mix_bars(school_type_mix_table(df)).data) == 3
    assert len(charts.tier_mix_bars(tier_mix_table(df)).data) >= 4
    deciles = slot_model.evaluate(df)["curves"]["exp_mlb_signed"]["loco_deciles"]
    fig = charts.calibration_chart(deciles)
    assert [t.name for t in fig.data] == ["y = x", "deciles"]


def test_builders_handle_empty_input(df, expected):
    empty = df.iloc[0:0]
    rules = OutcomeRules()
    no_groups = metrics.group_stats(empty, "school", "mlb_pct", min_n=1).table
    empty_mix = metrics.tier_mix_by(
        metrics.money_rows(empty, "What each bonus bought"), "bonus_band", ["$3M+"]
    )
    figures = [
        charts.tier_bars({"This group": metrics.tier_distribution(empty, rules)}),
        charts.rank_dots(no_groups, "mlb_pct", float("nan"), "All draftees"),
        charts.slot_panels(metrics.pick_range_table(empty), expected, is_baseline=False),
        charts.money_bars(empty_mix, empty_mix, ["$3M+"]),
        charts.bonus_scatter(metrics.bonus_points(empty)),
        charts.trend_chart(
            metrics.trend_table(empty, empty, {}, "mlb_pct"), "Reached the majors %"
        ),
        charts.coverage_heatmap([]),
        charts.school_mix_bars([]),
        charts.tier_mix_bars([]),
        charts.calibration_chart([]),
    ]
    for fig in figures:
        assert isinstance(fig, go.Figure) and len(fig.data) == 0
