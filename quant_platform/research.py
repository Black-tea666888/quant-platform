"""Research checks that make a backtest harder to fool yourself with.

- split_periods: statistics for a time period before and after a split date. The position is
  decided on the full history, so the split only changes which bars are scored, not the signal.
- cost_sensitivity: the same strategy under different cost assumptions. It reports results for
  each assumption; it does not pick the best one.
"""

from __future__ import annotations

import math
from dataclasses import replace

import numpy as np
import pandas as pd

from quant_platform.backtest import TRADING_DAYS, CostModel, run_backtest


def _period_stats(net: pd.Series, position: pd.Series, periods_per_year: int) -> dict:
    n = len(net)
    if n == 0:
        return {"bars": 0, "total_return": float("nan"), "cagr": float("nan"),
                "max_drawdown": float("nan"), "sharpe": float("nan"), "exposure": float("nan")}
    equity = (1.0 + net).cumprod()
    total = float(equity.iloc[-1] - 1.0)
    years = n / periods_per_year
    cagr = float(equity.iloc[-1] ** (1 / years) - 1) if years > 0 and equity.iloc[-1] > 0 else float("nan")
    drawdown = equity / equity.cummax() - 1.0
    std = net.std()
    sharpe = float(net.mean() / std * math.sqrt(periods_per_year)) if std and std > 0 else float("nan")
    return {
        "bars": n,
        "total_return": total,
        "cagr": cagr,
        "max_drawdown": float(drawdown.min()),
        "sharpe": sharpe,
        "exposure": float(position.mean()),
    }


def split_periods(
    prices: pd.DataFrame,
    position: pd.Series,
    costs: CostModel,
    split_date: str,
    periods_per_year: int = TRADING_DAYS,
) -> dict[str, dict]:
    """Statistics for bars before `split_date` (in-sample) and on or after it (out-of-sample)."""
    split = pd.Timestamp(split_date)
    result = run_backtest(prices, position, costs)
    dates = pd.DatetimeIndex(result.net_returns.index)
    # The first bar has no real return, so it is excluded from both periods.
    usable = pd.Series(True, index=dates)
    usable.iloc[0] = False
    held = pd.Series(result.position.to_numpy(), index=dates)
    net = result.net_returns
    in_sample = usable & (dates < split)
    out_sample = usable & (dates >= split)
    return {
        "in_sample": _period_stats(net[in_sample.to_numpy()], held[in_sample.to_numpy()], periods_per_year),
        "out_of_sample": _period_stats(net[out_sample.to_numpy()], held[out_sample.to_numpy()], periods_per_year),
    }


def cost_sensitivity(
    prices: pd.DataFrame,
    position: pd.Series,
    base: CostModel,
    discounts: tuple[float, ...] = (1.0, 0.6),
    slippages: tuple[float, ...] = (0.0005, 0.001, 0.002),
    periods_per_year: int = TRADING_DAYS,
) -> pd.DataFrame:
    """Total return and CAGR for each (discount, slippage) pair. Rows are sorted by discount, then slippage."""
    rows = []
    for discount in discounts:
        for slippage in slippages:
            costs = replace(base, discount=discount, slippage=slippage)
            result = run_backtest(prices, position, costs)
            stats = _period_stats(result.net_returns.iloc[1:], result.position.iloc[1:], periods_per_year)
            rows.append({"discount": discount, "slippage": slippage,
                         "total_return": stats["total_return"], "cagr": stats["cagr"]})
    return pd.DataFrame(rows)
