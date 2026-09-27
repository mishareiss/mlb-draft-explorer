"""Expected-by-pick model on synthetic data where the true P(MLB) by pick is known."""

import numpy as np
import pandas as pd
import pytest
from scipy.special import expit

from transform import slot_model

PICKS = np.tile(np.arange(1, 1001), 8)  # 8 classes of 1,000 picks
GRID = np.arange(1, 1001)


def truth(pick: np.ndarray) -> np.ndarray:
    return expit(2.5 - 0.9 * np.log(pick))  # ~61% at pick 10, 16% at 100, 4% at 500


def draws(p: np.ndarray, seed: int = 0) -> np.ndarray:
    return (np.random.default_rng(seed).random(len(p)) < p).astype(int)


def test_fitted_curve_recovers_truth_and_is_monotone():
    fitted, method = slot_model.fit_curve(PICKS, draws(truth(PICKS)), GRID)
    assert method == "logistic_spline"
    for pick in (10, 100, 500):
        assert fitted[pick - 1] == pytest.approx(truth(np.array([pick]))[0], abs=0.03)
    assert slot_model.max_rise(fitted) <= slot_model.MAX_RISE


def test_fit_is_deterministic():
    y = draws(truth(PICKS))
    first, _ = slot_model.fit_curve(PICKS, y, GRID)
    second, _ = slot_model.fit_curve(PICKS, y, GRID)
    assert np.array_equal(first, second)


def test_non_monotone_data_falls_back_to_isotonic():
    bump = 0.1 + 0.7 * np.exp(-((np.log(PICKS) - np.log(20)) ** 2) / 0.5)  # peaks at pick 20
    fitted, method = slot_model.fit_curve(PICKS, draws(bump), GRID)
    assert method == "isotonic"
    assert slot_model.max_rise(fitted) == 0


@pytest.fixture(scope="module")
def synthetic() -> pd.DataFrame:
    """2012-2019 classes (10% unsigned, 5% drafted again later) plus a 2021 class."""
    rng = np.random.default_rng(1)
    years = np.repeat(np.arange(2012, 2020), 1000)
    df = pd.DataFrame({"draft_year": years, "pick_number": PICKS})
    df = pd.concat(
        [df, pd.DataFrame({"draft_year": 2021, "pick_number": np.arange(1, 601)})],
        ignore_index=True,
    )
    final = rng.random(len(df)) > 0.05
    signed = final & (rng.random(len(df)) > 0.10)
    reached = signed & (rng.random(len(df)) < truth(df["pick_number"].to_numpy()))
    eligible = final & (df["draft_year"] <= 2019)
    return df.assign(
        is_final_draft=final,
        signed=signed,
        outcome_eligible=eligible,
        reached_mlb=pd.Series(reached, dtype="boolean").where(final),
        became_regular=pd.Series(reached & (rng.random(len(df)) < 0.2), dtype="boolean").where(
            eligible
        ),
    )


@pytest.fixture(scope="module")
def scored(synthetic) -> pd.DataFrame:
    curve, _ = slot_model.fit_all(synthetic)
    extra = slot_model.row_columns(synthetic, curve).drop(columns=["draft_year", "pick_number"])
    return synthetic.join(extra)


def test_every_row_gets_expectations(scored):
    for col in slot_model.CURVES:
        assert scored[col].between(0, 1).all()


def test_minus_exp_is_null_outside_signed_eligible_rows(scored):
    unsigned = scored["is_final_draft"] & ~scored["signed"] & (scored["draft_year"] <= 2019)
    for mask in (unsigned, ~scored["is_final_draft"], scored["draft_year"] == 2021):
        assert mask.any()
        assert scored.loc[mask, ["mlb_minus_exp", "regular_minus_exp"]].isna().all().all()


def test_minus_exp_averages_to_zero(scored):
    scored_rows = scored["outcome_eligible"] & scored["signed"]
    assert scored.loc[scored_rows, "mlb_minus_exp"].notna().all()
    assert scored["mlb_minus_exp"].mean() == pytest.approx(0, abs=0.01)


def test_calibration_bins_are_equal_count_deciles():
    y = draws(truth(PICKS))
    bins = slot_model.calibration_bins(y, truth(PICKS))
    assert [b["decile"] for b in bins] == list(range(1, 11))
    assert sum(b["n"] for b in bins) == len(y)
    assert bins[0]["expected"] < bins[-1]["expected"]


def test_wilson_interval_contains_rate():
    lo, hi = slot_model.wilson_interval(0.2, 700)
    assert lo < 0.2 < hi and hi - lo < 0.06
