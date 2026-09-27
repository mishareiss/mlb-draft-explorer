"""Number formatting shared by takeaways, tiles and charts. None/NaN -> an em dash."""

from __future__ import annotations

import math

DASH = "—"


def _missing(x: float | None) -> bool:
    return x is None or (isinstance(x, float) and math.isnan(x))


def pct(x: float | None) -> str:
    """Fraction -> '29.0%'."""
    return DASH if _missing(x) else f"{100 * x:.1f}%"


def usd(x: float | None) -> str:
    """Dollars -> '$1.2M' / '$350k' / '$800'."""
    if _missing(x):
        return DASH
    if round(x / 1e3) >= 1000:
        return f"${x / 1e6:.1f}".removesuffix(".0") + "M"
    if x >= 1e3:
        return f"${x / 1e3:.0f}k"
    return f"${x:.0f}"


def war(x: float | None) -> str:
    return DASH if _missing(x) else f"{x:.1f}"


def years(x: float | None) -> str:
    return DASH if _missing(x) else f"{x:.1f} yrs"


def count(n: int) -> str:
    return f"{n:,}"
