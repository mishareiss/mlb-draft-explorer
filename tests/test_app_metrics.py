import math
import re
import statistics

import pandas as pd
import pytest
from app_fixture import make_outcomes

from lib import fmt, metrics, theme
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


# --- vs. draft slot ----------------------------------------------------------------------


def _slot_frame() -> pd.DataFrame:
    """Four signed eligible players, one unsigned eligible pick, one 2022 pick (ignored)."""
    return pd.DataFrame(
        {
            "outcome_eligible": [True, True, True, True, True, False],
            "signed": [True, True, True, True, False, True],
            "reached_mlb": pd.array([True, False, False, True, None, True], dtype="boolean"),
            "became_regular": pd.array([True, False, False, False, None, None], dtype="boolean"),
            "mlb_minus_exp": [0.6, -0.2, -0.1, 0.5, None, None],
            "regular_minus_exp": [0.9, -0.05, -0.05, -0.2, None, None],
            "exp_mlb_all": [0.35, 0.15, 0.08, 0.45, 0.30, 0.50],
            "exp_regular_all": [0.08, 0.04, 0.04, 0.18, 0.02, 0.10],
        }
    )


def _mean_and_half(values: list[float]) -> tuple[float, float]:
    return statistics.mean(values), 1.645 * statistics.stdev(values) / math.sqrt(len(values))


def test_vs_slot_signed_players():
    # mean of mlb_minus_exp over the 4 signed eligible rows: (0.6-0.2-0.1+0.5)/4 = 0.2
    # sd = sqrt(((.4)²+(.4)²+(.3)²+(.3)²)/3) = 0.40825; half = 1.645*0.40825/2 = 0.33578
    s = metrics.vs_slot(_slot_frame(), "mlb")
    assert s.n == 4
    assert s.value == pytest.approx(20.0)
    assert (s.lo, s.hi) == pytest.approx((20.0 - 33.578, 20.0 + 33.578), abs=1e-3)
    regular = metrics.vs_slot(_slot_frame(), "regular")
    mean, half = _mean_and_half([90, -5, -5, -20])
    assert (regular.value, regular.lo, regular.hi) == pytest.approx(
        (mean, mean - half, mean + half)
    )


def test_vs_slot_counting_unsigned_picks():
    # reached_mlb.fillna(False) - exp_mlb_all over the 5 eligible rows
    rules = OutcomeRules(count_unsigned=True)
    s = metrics.vs_slot(_slot_frame(), "mlb", rules)
    mean, half = _mean_and_half([65, -15, -8, 55, -30])
    assert s.n == 5
    assert (s.value, s.lo, s.hi) == pytest.approx((mean, mean - half, mean + half))
    assert s.value == pytest.approx(13.4)
    regular = metrics.vs_slot(_slot_frame(), "regular", rules)
    mean, half = _mean_and_half([92, -4, -4, -18, -2])
    assert (regular.value, regular.lo, regular.hi) == pytest.approx(
        (mean, mean - half, mean + half)
    )


def test_vs_slot_empty():
    s = metrics.vs_slot(_slot_frame().iloc[0:0], "mlb")
    assert s.n == 0 and math.isnan(s.value)


# --- significance ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("lo", "hi", "direction", "color", "label"),
    [
        (0.0, 2.0, "same", theme.SAME, "about the same"),  # an end at zero includes zero
        (-2.0, 0.0, "same", theme.SAME, "about the same"),
        (-1.0, 1.0, "same", theme.SAME, "about the same"),
        (1e-9, 2.0, "above", theme.COHORT, "above"),
        (-2.0, -1e-9, "below", theme.BELOW, "below"),
        (math.nan, math.nan, "none", theme.COHORT, ""),
    ],
)
def test_significance_edges(lo, hi, direction, color, label):
    sig = metrics.significance(lo, hi)
    assert (sig.direction, sig.color, sig.label) == (direction, color, label)


def test_no_red_or_green_in_the_theme():
    colors = [theme.COHORT, theme.BASELINE, theme.BELOW, theme.SAME, *theme.SERIES_COLORS]
    colors += [*theme.TIER_COLORS.values(), *theme.SCHOOL_TYPE_COLORS.values()]
    for c in colors:
        r, g, b = (int(c[i : i + 2], 16) for i in (1, 3, 5))
        assert not (r > 150 and g < 110 and b < 110), c  # red
        assert not (g > 150 and r < 110 and b < 140), c  # green


def test_delta_vs_reference():
    d = metrics.delta_vs(metrics.Stat(0.30, 0.25, 0.35, 100), 0.20)
    assert d.value == pytest.approx(0.10) and d.sig.direction == "above"
    assert metrics.delta_vs(metrics.Stat(0.30, 0.15, 0.35, 100), 0.20).sig.direction == "same"


# --- summary metrics ---------------------------------------------------------------------


def test_outcome_metrics_use_signed_eligible_rows(df):
    rules = OutcomeRules()
    mlb = metrics.metric_stat(df, "mlb_pct", rules)
    assert (mlb.n, mlb.value) == (26, pytest.approx(7 / 26))
    assert metrics.metric_stat(df, "regular_pct", rules).value == pytest.approx(3 / 26)
    assert metrics.metric_stat(df, "signed_pct", rules).value == pytest.approx(36 / 40)
    assert metrics.metric_stat(df, "war_per_player", rules).value == pytest.approx(26.8 / 26)


def test_outcomes_ignore_non_eligible_rows(df):
    # 2022 has a player who already debuted; he is in the frame but not eligible
    newer = apply_filters(df, Filters(years=(2020, 2025)))
    assert len(newer) == 10 and newer["reached_mlb"].fillna(False).any()
    assert metrics.metric_stat(newer, "mlb_pct", OutcomeRules()).n == 0
    # Gamma HS non-final rows don't count even with unsigned picks included
    gamma = df[df["school"] == "Gamma HS"]
    assert metrics.metric_stat(gamma, "mlb_pct", OutcomeRules(count_unsigned=True)).n == 4


def test_count_unsigned_changes_denominator(df):
    signed_only = metrics.metric_stat(df, "mlb_pct", OutcomeRules(count_unsigned=False))
    with_unsigned = metrics.metric_stat(df, "mlb_pct", OutcomeRules(count_unsigned=True))
    assert (signed_only.n, with_unsigned.n) == (26, 28)
    assert with_unsigned.value == pytest.approx(7 / 28)


def test_median_bonus_uses_every_row(df):
    assert metrics.metric_stat(df, "median_bonus", OutcomeRules()).n == 36


# --- outcome tiers -----------------------------------------------------------------------


def test_tier_distribution_signed_players(df):
    # 26 signed eligible: 19 never reached; WAR 0.5, 0.3 cup of coffee; 1, 2 role player;
    # 10, 6, 7 regular; no star
    dist = metrics.tier_distribution(df).set_index("tier")
    assert "Didn't sign" not in dist.index
    assert dist["n"].to_dict() == {
        "Never reached MLB": 19,
        "Cup of coffee": 2,
        "Role player": 2,
        "Regular": 3,
        "Star": 0,
    }
    assert dist["pct"].sum() == pytest.approx(100)
    assert dist.loc["Regular", "pct"] == pytest.approx(300 / 26)


def test_tier_distribution_counting_unsigned_adds_didnt_sign(df):
    dist = metrics.tier_distribution(df, OutcomeRules(count_unsigned=True)).set_index("tier")
    assert dist.loc["Didn't sign", "n"] == 2
    assert dist["n"].sum() == 28
    assert dist["pct"].sum() == pytest.approx(100)


def test_tier_distribution_renormalizes_without_didnt_sign():
    frame = pd.DataFrame(
        {
            "outcome_eligible": [True] * 4,
            "signed": [True, True, True, False],
            "outcome_tier": ["Never reached MLB", "Regular", "Regular", "Didn't sign"],
        }
    )
    dist = metrics.tier_distribution(frame).set_index("tier")["pct"]
    assert dist["Regular"] == pytest.approx(200 / 3) and dist.sum() == pytest.approx(100)
    with_unsigned = metrics.tier_distribution(frame, OutcomeRules(count_unsigned=True))
    assert with_unsigned.set_index("tier")["pct"]["Regular"] == pytest.approx(50)


def test_regular_or_better(df):
    assert metrics.regular_or_better(metrics.tier_distribution(df)) == pytest.approx(3 / 26)
    assert math.isnan(metrics.regular_or_better(metrics.tier_distribution(df.iloc[0:0])))


def test_tier_mix_by_bonus_band(df):
    rows = metrics.money_rows(df, "What each bonus bought")
    mix = metrics.tier_mix_by(rows, "bonus_band", ["$1M–$3M", "$100k–$500k"])
    by_group = mix.groupby("group")["pct"].sum()
    assert by_group.to_dict() == pytest.approx({"$1M–$3M": 100, "$100k–$500k": 100})
    assert mix.drop_duplicates("group").set_index("group")["group_n"].sum() == 26


# --- players tab -------------------------------------------------------------------------


def test_top_producers(df):
    # WAR 10 (Player 00), 7 (Player 20), 6 (01), 2 (10), then a tie at 1.0 between the 2015
    # pick (Player 02) and a 2022 pick: the earlier class wins
    top = metrics.top_producers(df)
    assert top["player_name"].tolist() == [
        "Player 00",
        "Player 20",
        "Player 01",
        "Player 10",
        "Player 02",
    ]


def test_biggest_misses(df):
    # signed, eligible, never reached MLB, highest bonus first: Player 04 got $2M (pick 5);
    # the rest $300k, earliest pick first. Unsigned and non-final picks never count.
    misses = metrics.biggest_misses(df)
    assert misses["player_name"].tolist() == [
        "Player 04",
        "Player 05",
        "Player 06",
        "Player 07",
        "Player 12",
    ]
    assert misses["signed"].all() and misses["outcome_eligible"].all()


# --- groups ------------------------------------------------------------------------------


def test_group_stats_min_n_and_hidden(df):
    gs = metrics.group_stats(df, "school", "mlb_pct", min_n=5)
    assert gs.table["group"].tolist() == ["Alpha U", "Beta State"]
    assert gs.table["n"].tolist() == [8, 10]
    assert gs.table["value"].tolist() == pytest.approx([0.5, 0.2])
    assert gs.hidden == 2  # Gamma HS and Delta CC have 4 eligible players each
    lo, hi = metrics.wilson_interval(4, 8)
    assert (gs.table.loc[0, "lo"], gs.table.loc[0, "hi"]) == pytest.approx((lo, hi))


def test_group_stats_vs_slot_is_a_mean_in_points(df):
    gs = metrics.group_stats(df, "school", "mlb_vs_slot", min_n=1)
    alpha = gs.table.set_index("group").loc["Alpha U"]
    rows = df[(df["school"] == "Alpha U") & df["outcome_eligible"] & df["signed"]]
    assert alpha["value"] == pytest.approx(100 * rows["mlb_minus_exp"].mean())


def test_group_stats_empty_frame(df):
    gs = metrics.group_stats(df.iloc[0:0], "school", "mlb_pct", min_n=1)
    assert gs.table.empty and gs.hidden == 0


def test_drop_no_school():
    table = pd.DataFrame({"group": ["A", "No school / unclassified"], "value": [1, 2]})
    assert metrics.drop_no_school(table)["group"].tolist() == ["A"]


def test_shown_groups_keeps_extremes():
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
    assert shown["group"].tolist() == [f"G{i:02d}" for i in [*range(12), *range(18, 30)]]
    assert metrics.shown_groups(table.head(25)).equals(table.head(25))


def test_takeaway_rankings_counts_clear_groups():
    table = metrics.with_significance(
        pd.DataFrame(
            {
                "group": ["A", "B", "C"],
                "value": [4.0, 1.0, -3.0],
                "lo": [1.0, -1.0, -5.0],
                "hi": [7.0, 3.0, -1.0],
                "n": [100, 100, 100],
            }
        ),
        0.0,
    )
    assert table["sig"].tolist() == ["above", "same", "below"]
    text = metrics.takeaway_rankings(table, "mlb_vs_slot", "conference", 0.0)
    assert text == (
        "1 of 3 conferences clearly beat their draft slots, led by A (+4.0 pts); "
        "1 conference clearly below."
    )


# --- draft slot tab ----------------------------------------------------------------------


def test_pick_range_table(df):
    table = metrics.pick_range_table(df).set_index("range")
    # 2015 signed eligible picks 1-10: Alpha U picks 1-8 (4 reached), Beta State 11-20...
    assert table.index.tolist() == ["1–10", "11–20", "21–30"]
    assert table.loc["1–10", "n"] == 8  # picks 9 and 10 never signed
    assert table.loc["1–10", "rate"] == pytest.approx(4 / 8)
    assert table.loc["1–10", "median_pick"] == pytest.approx(4.5)
    lo, hi = metrics.wilson_interval(4, 8)
    assert (table.loc["1–10", "lo"], table.loc["1–10", "hi"]) == pytest.approx((lo, hi))


# --- words -------------------------------------------------------------------------------


def test_cohort_sentence(df):
    f = Filters(
        school_types=("4-year college",),
        conference_groups=("Southeastern",),
        position_groups=("RHP",),
    )
    cohort = apply_filters(df, f)
    assert metrics.cohort_sentence(f, cohort, OutcomeRules()) == (
        f"{len(metrics.outcome_rows(cohort, OutcomeRules()))} signed right-handed pitchers from "
        f"SEC schools, drafted 2012–2019 ({len(cohort)} picks, 2012–2025)."
    )
    sentence = metrics.cohort_sentence(Filters(years=(2020, 2025)), df, OutcomeRules())
    assert "None are from the 2012–2019 classes" in sentence


def test_describe_cohort():
    assert metrics.describe_cohort(Filters()) == "All draftees"
    sec_arms = Filters(
        school_types=("4-year college",),
        conference_groups=("Southeastern",),
        position_groups=("RHP", "LHP"),
    )
    assert metrics.describe_cohort(sec_arms) == "SEC pitchers"
    assert metrics.describe_cohort(Filters(picks=(1, 100))) == "This group"


def test_takeaway_empty_states(df):
    none = df.iloc[0:0]
    assert "Too few" in metrics.takeaway_tiles(
        "X", metrics.EMPTY_STAT, metrics.EMPTY_STAT, metrics.EMPTY_STAT, False
    )
    assert "No conference" in metrics.takeaway_rankings(
        pd.DataFrame(columns=["group", "value", "lo", "hi", "n", "sig"]), "mlb_pct", "conference", 0
    )
    assert "No signed" in metrics.takeaway_bonus(metrics.bonus_points(none))
    assert "No players" in metrics.takeaway_tiers(
        metrics.metric_stat(none, "regular_pct", OutcomeRules()),
        metrics.metric_stat(df, "regular_pct", OutcomeRules()),
        False,
    )


def test_takeaway_tiers(df):
    rules = OutcomeRules()
    alpha = df[df["school"] == "Alpha U"]
    regular = metrics.metric_stat(alpha, "regular_pct", rules)
    base = metrics.metric_stat(df, "regular_pct", rules)
    # the tile's share and the tier chart's regular-or-better share agree
    assert regular.value == pytest.approx(
        metrics.regular_or_better(metrics.tier_distribution(alpha))
    )
    # Alpha U: WAR 10 and 6 of 8 signed players are regulars; n=8, so the interval is wide
    text = metrics.takeaway_tiers(regular, base, is_baseline=False)
    assert metrics.delta_vs(regular, base.value).sig.direction == "same"
    assert text == (
        "25% of this group became regulars or better, about the same as all draftees (12%)."
    )
    assert metrics.takeaway_tiers(base, base, is_baseline=True) == (
        "12% of all draftees with outcomes became regulars or better."
    )


def test_takeaway_tiers_follows_the_tile_significance():
    base = metrics.Stat(0.033, 0.03, 0.036, 5000)
    same = metrics.Stat(0.047, 0.03, 0.065, 300)  # interval includes 3.3%
    above = metrics.Stat(0.20, 0.15, 0.25, 300)
    for stat in (same, above):
        _, tile_text = metrics.vs_all_draftees(stat, base.value, fmt.pct_short)
        heading = metrics.takeaway_tiers(stat, base, is_baseline=False)
        assert ("about the same" in heading) == ("about the same" in tile_text)
    assert metrics.takeaway_tiers(same, base, False) == (
        "4.7% of this group became regulars or better, about the same as all draftees (3.3%)."
    )
    assert metrics.takeaway_tiers(above, base, False) == (
        "20% of this group became regulars or better, vs 3.3% of all draftees."
    )


def test_trend_share_of_picks(df):
    base = apply_filters(df, Filters())
    cohort = df[df["school_type"] != "High school"]
    lines = {"Alpha U": df[df["school"] == "Alpha U"]}
    trend = metrics.trend_table(base, cohort, lines, "share")
    alpha = trend[trend["line"] == "Alpha U"].set_index("draft_year")["value"]
    assert alpha.loc[2015] == pytest.approx(10 / 30)
    assert alpha.loc[2022] == pytest.approx(5 / 10)
    assert set(trend.loc[trend["role"] == "reference", "line"]) == {"This group"}


def test_trend_outcomes_stop_at_2019(df):
    alpha = df[df["school"] == "Alpha U"]
    for metric in ("mlb_pct", "mlb_vs_slot"):
        trend = metrics.trend_table(df, alpha, {}, metric)
        assert trend["draft_year"].unique().tolist() == [2015]
        assert set(trend["line"]) == {"This group", "All draftees"}


def test_trend_skips_reference_that_repeats_a_line(df):
    assert set(metrics.trend_table(df, df, {}, "mlb_pct")["role"]) == {"line"}
    alpha = df[df["school"] == "Alpha U"]
    assert set(metrics.trend_table(df, alpha, {"Alpha U": alpha}, "share")["line"]) == {"Alpha U"}


def test_takeaway_trend_units(df):
    alpha = df[df["school"] == "Alpha U"]
    trend = metrics.trend_table(df, alpha, {"Alpha U": alpha}, "median_bonus")
    assert re.match(
        r"Median signing bonus for Alpha U went from \$",
        metrics.takeaway_trend(trend, "Median signing bonus"),
    )


@pytest.mark.parametrize(
    ("value", "text"),
    [(1_234_567, "$1.2M"), (1_000_000, "$1M"), (350_000, "$350k"), (999_600, "$1M"), (800, "$800")],
)
def test_fmt_usd(value, text):
    assert fmt.usd(value) == text


def test_fmt_pct_and_points():
    assert fmt.pct(0.2918) == "29.2%"
    assert fmt.pct(None) == fmt.DASH
    assert fmt.pct_short(0.12) == "12%" and fmt.pct_short(0.024) == "2.4%"
    assert fmt.pts(2.84) == "+2.8 pts" and fmt.pts(-3.9) == "−3.9 pts"
