import math
import re

import pandas as pd
import pytest
from app_fixture import make_outcomes

from lib import fmt, metrics
from lib.data import Filters, apply_filters
from lib.metrics import OutcomeRules


@pytest.fixture
def df():
    return make_outcomes()


def test_wilson_interval_known_values():
    # k=18, n=100, z=1.645: p=0.18, z²=2.706, denom=1+z²/n=1.02706,
    # center=(0.18+0.01353)/1.02706=0.18843, half=1.645*sqrt(0.001476+0.0000677)/1.02706=0.06293
    # -> (0.1255, 0.2514). statsmodels proportion_confint(18, 100, alpha=0.10, method="wilson")
    # gives (0.125507, 0.251352).
    lo, hi = metrics.wilson_interval(18, 100)
    assert lo == pytest.approx(0.12551, abs=1e-4)
    assert hi == pytest.approx(0.25135, abs=1e-4)


def test_wilson_interval_closed_forms():
    # k=0: lower bound 0, upper bound z²/(n+z²); z=1.96, n=10 -> 3.8416/13.8416 = 0.27754
    assert metrics.wilson_interval(0, 10, z=1.96) == pytest.approx((0.0, 0.27754), abs=1e-5)
    # both bounds solve the score equation (p̂-p0)² = z²·p0(1-p0)/n
    k, n, z = 7, 26, 1.645
    for p0 in metrics.wilson_interval(k, n, z):
        assert (k / n - p0) ** 2 == pytest.approx(z * z * p0 * (1 - p0) / n)


def test_wilson_interval_empty():
    assert all(math.isnan(x) for x in metrics.wilson_interval(0, 0))


def test_cohort_summary_uses_signed_eligible_rows(df):
    s = metrics.cohort_summary(df)
    assert s.picks == 40
    assert s.signed_pct == pytest.approx(36 / 40)
    assert s.outcome_n == 26
    assert s.mlb_pct == pytest.approx(7 / 26)
    assert s.hit_pct == pytest.approx(3 / 26)
    assert s.war_per_player == pytest.approx(26.8 / 26)
    assert s.years_to_debut == pytest.approx(3.1)


def test_outcomes_ignore_non_eligible_rows(df):
    # 2022 has a player who already debuted; he is in the frame but not eligible
    newer = apply_filters(df, Filters(years=(2020, 2025)))
    assert len(newer) == 10 and newer["reached_mlb"].fillna(False).any()
    s = metrics.cohort_summary(newer)
    assert s.outcome_n == 0 and math.isnan(s.mlb_pct)
    # Gamma HS non-final rows don't count even with unsigned picks included
    gamma = df[df["school"] == "Gamma HS"]
    assert metrics.metric_stat(gamma, "mlb_pct", OutcomeRules(count_unsigned=True)).n == 4


def test_count_unsigned_changes_denominator(df):
    signed_only = metrics.metric_stat(df, "mlb_pct", OutcomeRules(count_unsigned=False))
    with_unsigned = metrics.metric_stat(df, "mlb_pct", OutcomeRules(count_unsigned=True))
    assert (signed_only.n, with_unsigned.n) == (26, 28)
    assert signed_only.value == pytest.approx(7 / 26)
    assert with_unsigned.value == pytest.approx(7 / 28)


def test_hit_threshold(df):
    assert metrics.metric_stat(df, "hit_pct", OutcomeRules(hit_war=1.0)).value == pytest.approx(
        5 / 26
    )


def test_median_bonus_uses_every_row(df):
    stat = metrics.metric_stat(df, "median_bonus", OutcomeRules())
    assert stat.n == 36  # every signed pick has a bonus, 2022 included


def test_group_stats_min_n_and_hidden(df):
    gs = metrics.group_stats(df, "school", "mlb_pct", min_n=5)
    assert gs.table["group"].tolist() == ["Alpha U", "Beta State"]
    assert gs.table["n"].tolist() == [8, 10]
    assert gs.table["value"].tolist() == pytest.approx([0.5, 0.2])
    assert gs.hidden == 2  # Gamma HS and Delta CC have 4 eligible players each
    lo, hi = metrics.wilson_interval(4, 8)
    assert (gs.table.loc[0, "lo"], gs.table.loc[0, "hi"]) == pytest.approx((lo, hi))

    everyone = metrics.group_stats(df, "school", "mlb_pct", min_n=1)
    assert len(everyone.table) == 4 and everyone.hidden == 0


def test_group_stats_war_interval(df):
    gs = metrics.group_stats(df, "school", "war_per_player", min_n=8)
    alpha = gs.table.set_index("group").loc["Alpha U"]
    war = [10, 6, 1, 0.5, 0, 0, 0, 0]
    mean = sum(war) / 8
    sd = math.sqrt(sum((w - mean) ** 2 for w in war) / 7)
    assert alpha["value"] == pytest.approx(mean)
    assert alpha["lo"] == pytest.approx(mean - 1.645 * sd / math.sqrt(8))


def test_group_stats_empty_frame(df):
    gs = metrics.group_stats(df.iloc[0:0], "school", "mlb_pct", min_n=1)
    assert gs.table.empty and gs.hidden == 0


def test_takeaway_summary(df):
    alpha = df[df["school"] == "Alpha U"]
    rules = OutcomeRules()
    text = metrics.takeaway_summary(
        "Southeastern draftees",
        metrics.cohort_summary(alpha, rules),
        metrics.cohort_summary(df, rules),
        rules,
        is_baseline=False,
    )
    assert text == (
        "Southeastern draftees reached MLB at 50.0% and produced 5+ career WAR at 25.0%, "
        "vs 26.9% and 11.5% for all draftees."
    )


def test_takeaway_compare(df):
    gs = metrics.group_stats(df, "school", "mlb_pct", min_n=5)
    text = metrics.takeaway_compare(gs.table, "mlb_pct", 7 / 26)
    assert text.startswith("MLB % ranges from 20.0% (Beta State) to 50.0% (Alpha U)")
    assert "all draftees: 26.9%" in text and "overlap" in text


def test_shown_groups_keeps_extremes_and_takeaway_names_only_them():
    table = pd.DataFrame(
        {
            "group": [f"G{i:02d}" for i in range(30)],
            "value": [0.9 - 0.02 * i for i in range(30)],
            "lo": [0.8 - 0.02 * i for i in range(30)],
            "hi": [1.0 - 0.02 * i for i in range(30)],
            "n": [50] * 30,
        }
    )
    shown = metrics.shown_groups(table)
    assert len(shown) == 24
    assert shown["group"].tolist() == [f"G{i:02d}" for i in [*range(12), *range(18, 30)]]
    text = metrics.takeaway_compare(shown, "mlb_pct", 0.5)
    named = set(re.findall(r"\((G\d\d)\)", text))
    assert named == {"G00", "G29"} and named <= set(shown["group"])
    assert metrics.shown_groups(table.head(25)).equals(table.head(25))


def test_takeaway_empty_states(df):
    none = df.iloc[0:0]
    assert "Too few" in metrics.takeaway_summary(
        "X", metrics.cohort_summary(none), metrics.cohort_summary(df), OutcomeRules(), False
    )
    assert "No group" in metrics.takeaway_compare(none, "mlb_pct", 0.2)
    assert "No signed" in metrics.takeaway_bonus(metrics.bonus_points(none))


def test_takeaway_bonus(df):
    # signed eligible players: picks 1-5 got $2M, the rest $300k
    text = metrics.takeaway_bonus(metrics.bonus_points(df))
    assert text.startswith("Players who signed for $1M+ averaged")


def test_describe_cohort():
    assert metrics.describe_cohort(Filters()) == "All draftees"
    f = Filters(conference_groups=("Southeastern",), position_groups=("RHP",))
    assert metrics.describe_cohort(f) == "Southeastern RHP draftees"
    assert metrics.describe_cohort(Filters(slot_bands=("1–10",))) == "Selected draftees"


def test_slot_curve_in_draft_order(df):
    curve = metrics.slot_curve(df)
    assert curve["group"].tolist() == ["1–10", "11–30"]


def test_trend_share_of_picks(df):
    base = apply_filters(df, Filters())
    cohort = df[df["school_type"] != "High school"]
    lines = {"Alpha U": df[df["school"] == "Alpha U"]}
    trend = metrics.trend_table(base, cohort, lines, "share")
    alpha = trend[trend["line"] == "Alpha U"].set_index("draft_year")["value"]
    assert alpha.loc[2015] == pytest.approx(10 / 30)
    assert alpha.loc[2022] == pytest.approx(5 / 10)
    assert set(trend.loc[trend["role"] == "reference", "line"]) == {"All selected picks"}


def test_trend_mlb_only_eligible_years(df):
    alpha = df[df["school"] == "Alpha U"]
    trend = metrics.trend_table(df, alpha, {}, "mlb_pct")
    assert trend["draft_year"].unique().tolist() == [2015]
    assert set(trend["role"]) == {"line", "reference"}


def test_trend_skips_reference_that_repeats_a_line(df):
    # no filters: the cohort is all draftees, so there is no separate reference line
    assert set(metrics.trend_table(df, df, {}, "mlb_pct")["role"]) == {"line"}
    # one line covering the whole cohort: its share equals the cohort's share
    alpha = df[df["school"] == "Alpha U"]
    trend = metrics.trend_table(df, alpha, {"Alpha U": alpha}, "share")
    assert set(trend["line"]) == {"Alpha U"}
    # no filters: the cohort's share is 100% every year
    trend = metrics.trend_table(df, df, {"Alpha U": alpha}, "share")
    assert set(trend["line"]) == {"Alpha U"}


@pytest.mark.parametrize(
    ("value", "text"),
    [(1_234_567, "$1.2M"), (1_000_000, "$1M"), (350_000, "$350k"), (999_600, "$1M"), (800, "$800")],
)
def test_fmt_usd(value, text):
    assert fmt.usd(value) == text


def test_fmt_pct():
    assert fmt.pct(0.2918) == "29.2%"
    assert fmt.pct(None) == fmt.DASH
