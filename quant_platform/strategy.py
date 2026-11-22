"""Strategies. Each returns a target position per bar, decided using only that bar's close and earlier data."""

from __future__ import annotations

import pandas as pd

from quant_platform.i18n import t

STRATEGIES = ("sma", "donchian", "momentum")
DEFAULT_STRATEGY = "sma"
DONCHIAN_ENTRY_DAYS = 55
DONCHIAN_EXIT_DAYS = 20
MOMENTUM_LOOKBACK = 126


def sma_crossover(close: pd.Series, fast: int = 20, slow: int = 60) -> pd.Series:
    """Long (1.0) when the fast moving average is above the slow one, otherwise flat (0.0)."""
    if not 0 < fast < slow:
        raise ValueError(t("error_bad_windows"))
    fast_ma = close.rolling(fast).mean()
    slow_ma = close.rolling(slow).mean()
    # NaN comparisons are False, so the warm-up period stays flat.
    return (fast_ma > slow_ma).astype(float)


def donchian_breakout(close: pd.Series, entry_days: int = DONCHIAN_ENTRY_DAYS, exit_days: int = DONCHIAN_EXIT_DAYS) -> pd.Series:
    """Enter long when the close breaks above the highest close of the previous `entry_days` bars.
    Exit to flat when the close breaks below the lowest close of the previous `exit_days` bars.

    Uses closes only. The channel is shifted by one bar so today's close is compared with earlier bars only.
    """
    if not 0 < exit_days < entry_days:
        raise ValueError(t("error_bad_donchian"))
    upper = close.shift(1).rolling(entry_days).max()
    lower = close.shift(1).rolling(exit_days).min()
    position = []
    holding = 0.0
    for price, hi, lo in zip(close.to_numpy(), upper.to_numpy(), lower.to_numpy()):
        # NaN comparisons are False, so the warm-up period stays flat.
        if holding == 0.0 and price > hi:
            holding = 1.0
        elif holding == 1.0 and price < lo:
            holding = 0.0
        position.append(holding)
    return pd.Series(position, index=close.index, dtype=float)


def time_series_momentum(close: pd.Series, lookback: int = MOMENTUM_LOOKBACK) -> pd.Series:
    """Long (1.0) when the close is above the close `lookback` bars ago, otherwise flat (0.0).

    Compares with a past close only, so the decision at bar t uses data up to bar t.
    """
    if lookback < 1:
        raise ValueError(t("error_positive_int", name="lookback"))
    past = close.shift(lookback)
    # NaN comparisons are False, so the first `lookback` bars stay flat.
    return (close > past).astype(float)


def build_position(strategy: str, close: pd.Series, **params: int) -> pd.Series:
    """Target position for the named strategy. Pass `fast`/`slow` for SMA, `entry_days`/`exit_days` for Donchian."""
    if strategy == "sma":
        return sma_crossover(close, fast=params.get("fast", 20), slow=params.get("slow", 60))
    if strategy == "donchian":
        return donchian_breakout(
            close,
            entry_days=params.get("entry_days", DONCHIAN_ENTRY_DAYS),
            exit_days=params.get("exit_days", DONCHIAN_EXIT_DAYS),
        )
    if strategy == "momentum":
        return time_series_momentum(close, lookback=params.get("lookback", MOMENTUM_LOOKBACK))
    raise ValueError(t("error_unknown_strategy", name=strategy, known=", ".join(STRATEGIES)))
