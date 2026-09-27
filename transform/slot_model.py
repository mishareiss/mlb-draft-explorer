"""Expected outcome by pick: the chance a pick reaches MLB (or 5+ WAR) given only where it went.

Four curves: target (reached_mlb, became_regular) x population (signed players, or every
outcome-eligible pick including unsigned ones). Each is a logistic regression on a cubic spline
of log(pick_number), trained on outcome-eligible rows (final drafts, 2012-2019 classes). The
expectation depends only on the pick, so every row of every year gets a value.

A curve must not rise with pick number. If a fitted curve climbs more than MAX_RISE above its
value at any earlier pick, it is refit with isotonic regression, which is monotone by
construction.
"""

from __future__ import annotations

import logging
import math

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import FunctionTransformer, SplineTransformer

log = logging.getLogger(__name__)

MAX_RISE = 0.005  # 0.5 percentage points
# 4 knots (6 cubic basis functions) with light L2. Stronger penalties (C=1) or a 5th knot pull
# the curve down at picks 1-5, where there are only ~8 players per pick, and break monotonicity.
N_KNOTS, DEGREE, C = 4, 3, 10.0
REPORT_PICKS = [1, 10, 30, 100, 300, 1000]
N_BINS = 10

# column -> (target, signed players only?)
CURVES = {
    "exp_mlb_signed": ("reached_mlb", True),
    "exp_mlb_all": ("reached_mlb", False),
    "exp_regular_signed": ("became_regular", True),
    "exp_regular_all": ("became_regular", False),
}


def fit_curve(pick: np.ndarray, y: np.ndarray, grid: np.ndarray) -> tuple[np.ndarray, str]:
    """P(y) at each pick in `grid`, and the method used ("logistic_spline" or "isotonic")."""
    pick, y = np.asarray(pick, dtype=float), np.asarray(y, dtype=int)
    if len(np.unique(y)) < 2:  # nothing to fit (tiny test inputs)
        return np.full(len(grid), float(y.mean()) if len(y) else 0.0), "constant"
    model = make_pipeline(
        FunctionTransformer(np.log),
        SplineTransformer(n_knots=N_KNOTS, degree=DEGREE, extrapolation="constant"),
        LogisticRegression(C=C, max_iter=5000),
    )
    model.fit(pick.reshape(-1, 1), y)
    probs = model.predict_proba(np.asarray(grid, dtype=float).reshape(-1, 1))[:, 1]
    if max_rise(probs) <= MAX_RISE:
        return probs, "logistic_spline"
    iso = IsotonicRegression(increasing=False, y_min=0, y_max=1, out_of_bounds="clip")
    return iso.fit(pick, y).predict(grid), "isotonic"


def max_rise(probs: np.ndarray) -> float:
    """Largest amount the curve climbs above its lowest value at any earlier pick.

    Measured against the running minimum rather than the previous pick, so a slow climb
    spread over many picks counts in full.
    """
    probs = np.asarray(probs, dtype=float)
    return float((probs - np.minimum.accumulate(probs)).max(initial=0.0))


def training_rows(df: pd.DataFrame, signed_only: bool) -> pd.DataFrame:
    mask = df["outcome_eligible"].astype(bool)
    if signed_only:
        mask &= df["signed"].astype(bool)
    return df[mask]


def _target(rows: pd.DataFrame, target: str) -> np.ndarray:
    return rows[target].fillna(False).astype(int).to_numpy()


def fit_all(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, str]]:
    """Curve table (one row per pick 1..max pick in any year) and the method per curve."""
    grid = np.arange(1, int(df["pick_number"].max()) + 1)
    curve, methods = pd.DataFrame({"pick_number": grid}), {}
    for col, (target, signed_only) in CURVES.items():
        rows = training_rows(df, signed_only)
        curve[col], methods[col] = fit_curve(rows["pick_number"], _target(rows, target), grid)
        log.info("%-18s %s on %d rows", col, methods[col], len(rows))
    return curve, methods


def row_columns(df: pd.DataFrame, curve: pd.DataFrame) -> pd.DataFrame:
    """Per-row exp_* columns plus observed-minus-expected for signed outcome-eligible rows."""
    out = df[["draft_year", "pick_number"]].merge(curve, on="pick_number", how="left")
    scored = (df["outcome_eligible"].astype(bool) & df["signed"].astype(bool)).to_numpy()
    for target, col, name in [
        ("reached_mlb", "exp_mlb_signed", "mlb_minus_exp"),
        ("became_regular", "exp_regular_signed", "regular_minus_exp"),
    ]:
        diff = df[target].fillna(False).astype(float).to_numpy() - out[col].to_numpy()
        out[name] = np.where(scored, diff, np.nan)
    return out


# --- evaluation ------------------------------------------------------------------------------


def _scores(y: np.ndarray, p: np.ndarray) -> dict:
    p = np.clip(p, 1e-6, 1 - 1e-6)  # isotonic can output exactly 0 or 1
    return {
        "brier": round(float(brier_score_loss(y, p)), 5),
        "log_loss": round(float(log_loss(y, p, labels=[0, 1])), 5),
    }


def leave_one_class_out(rows: pd.DataFrame, target: str) -> np.ndarray:
    """Each draft class predicted by a curve fit on the other classes."""
    pred = np.empty(len(rows))
    years = rows["draft_year"].to_numpy()
    for year in np.unique(years):
        test = years == year
        train = rows[~test]
        grid = rows.loc[test, "pick_number"].to_numpy()
        pred[test], _ = fit_curve(train["pick_number"], _target(train, target), grid)
    return pred


def calibration_bins(y: np.ndarray, pred: np.ndarray) -> list[dict]:
    """Predictions split into N_BINS equal-count bins (deciles), lowest expected first."""
    order = np.argsort(pred, kind="stable")
    bins = []
    for i, idx in enumerate(np.array_split(order, N_BINS), start=1):
        if not len(idx):  # fewer rows than bins
            continue
        bins.append(
            {
                "decile": i,
                "n": len(idx),
                "expected": round(float(pred[idx].mean()), 4),
                "observed": round(float(y[idx].mean()), 4),
            }
        )
    return bins


def wilson_interval(p: float, n: int, z: float = 1.645) -> tuple[float, float]:
    """Wilson score interval around rate p for n trials (90% by default)."""
    if n == 0:
        return 0.0, 1.0
    center = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return center - half, center + half


def evaluate(df: pd.DataFrame) -> dict:
    """Fit quality for the report: in-sample and leave-one-class-out scores vs. a constant."""
    curve, methods = fit_all(df)
    at_pick = curve.set_index("pick_number")
    result = {"method": methods, "curves": {}}
    for col, (target, signed_only) in CURVES.items():
        rows = training_rows(df, signed_only)
        y = _target(rows, target)
        fitted = rows["pick_number"].map(at_pick[col]).to_numpy()
        loco = leave_one_class_out(rows, target)
        result["curves"][col] = {
            "n": len(rows),
            "base_rate": round(float(y.mean()), 4),
            "baseline": _scores(y, np.full(len(y), y.mean())),
            "in_sample": _scores(y, fitted),
            "leave_one_class_out": _scores(y, loco),
            "loco_deciles": calibration_bins(y, loco),
            "expected_at_pick": {
                str(p): round(float(at_pick[col].get(p, np.nan)), 4) for p in REPORT_PICKS
            },
        }
    return result
