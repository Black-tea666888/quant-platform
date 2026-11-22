"""Strategies. Each returns a target position per bar, decided using only that bar's close and earlier data."""

from __future__ import annotations

import pandas as pd

from quant_platform.i18n import t


def sma_crossover(close: pd.Series, fast: int = 20, slow: int = 60) -> pd.Series:
    """Long (1.0) when the fast moving average is above the slow one, otherwise flat (0.0)."""
    if not 0 < fast < slow:
        raise ValueError(t("error_bad_windows"))
    fast_ma = close.rolling(fast).mean()
    slow_ma = close.rolling(slow).mean()
    # NaN comparisons are False, so the warm-up period stays flat.
    return (fast_ma > slow_ma).astype(float)
