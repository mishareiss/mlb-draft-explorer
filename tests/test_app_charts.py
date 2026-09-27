import plotly.graph_objects as go
import pytest
from app_fixture import make_outcomes

from lib import charts, metrics
from quality.checks import bonus_coverage_table, school_type_mix_table


@pytest.fixture
def df():
    return make_outcomes()


def test_compare_bars(df):
    gs = metrics.group_stats(df, "school", "mlb_pct", min_n=1)
    fig = charts.compare_bars(gs.table, "mlb_pct", 0.27)
    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 1 and len(fig.data[0].y) == 4
    assert fig.data[0].error_x.array is not None
    assert fig.data[0].y[-1].startswith("Alpha U (n=8)")  # highest value drawn on top


def test_compare_bars_caps_bar_count(df):
    gs = metrics.group_stats(df, "person_id", "mlb_pct", min_n=1)
    fig = charts.compare_bars(gs.table, "mlb_pct", 0.27, max_bars=25)
    assert len(fig.data[0].y) == 25


def test_compare_bars_median_has_no_whiskers(df):
    gs = metrics.group_stats(df, "school", "median_bonus", min_n=1)
    assert charts.compare_bars(gs.table, "median_bonus", 300_000).data[0].error_x.array is None


def test_slot_chart(df):
    curve = metrics.slot_curve(df)
    alpha = metrics.slot_curve(df[df["school"] == "Alpha U"])
    assert len(charts.slot_chart(alpha, curve, "Alpha U draftees").data) == 2


def test_bonus_scatter_one_trace_per_school_type(df):
    fig = charts.bonus_scatter(metrics.bonus_points(df))
    assert [t.name for t in fig.data] == ["4-year college", "Junior college", "High school"]
    assert fig.layout.xaxis.type == "log"


def test_trend_chart(df):
    lines = {"Alpha U": df[df["school"] == "Alpha U"], "Delta CC": df[df["school"] == "Delta CC"]}
    trend = metrics.trend_table(df, df, lines, "median_bonus")
    fig = charts.trend_chart(trend, "Median bonus")
    assert len(fig.data) == 3
    assert fig.data[-1].line.color == charts.GREY  # the all-draftee reference


def test_quality_charts(df):
    assert len(charts.coverage_heatmap(bonus_coverage_table(df)).data) == 1
    assert len(charts.school_mix_bars(school_type_mix_table(df)).data) == 3


def test_builders_handle_empty_input(df):
    empty = df.iloc[0:0]
    no_groups = metrics.group_stats(empty, "school", "mlb_pct", min_n=1).table
    figures = [
        charts.compare_bars(no_groups, "mlb_pct", float("nan")),
        charts.slot_chart(metrics.slot_curve(empty), metrics.slot_curve(empty), "x"),
        charts.bonus_scatter(metrics.bonus_points(empty)),
        charts.trend_chart(metrics.trend_table(empty, empty, {}, "mlb_pct"), "MLB %"),
        charts.coverage_heatmap([]),
        charts.school_mix_bars([]),
    ]
    for fig in figures:
        assert isinstance(fig, go.Figure) and len(fig.data) == 0
