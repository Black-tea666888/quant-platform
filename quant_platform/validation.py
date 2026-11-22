"""Validation tools that help separate real edges from curve fitting.

- grid_search: score every (fast, slow) pair on one period.
- walk_forward: repeatedly pick parameters on a training window, then test them on the next
  window that the selection never saw. Only out-of-sample returns are combined.
- overfit_warning: flags large drops from in-sample to out-of-sample performance.

Timing matches the backtest engine. Indicators only use bars up to each decision.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from quant_platform.backtest import CostModel, run_backtest, summarize
from quant_platform.strategy import sma_crossover

METRIC_COLUMNS = ("sharpe", "cagr", "max_drawdown", "total_return", "trades")


def make_grid(fast_values, slow_values) -> list[tuple[int, int]]:
    """All (fast, slow) pairs with fast < slow."""
    return [(f, s) for f in fast_values for s in slow_values if f < s]


def grid_search(
    prices: pd.DataFrame,
    combos: list[tuple[int, int]],
    costs: CostModel,
    periods_per_year: int,
    metric: str = "sharpe",
) -> pd.DataFrame:
    """Score each combination on `prices`, best first by `metric`."""
    if not combos:
        raise ValueError("combos must not be empty")
    rows = []
    for fast, slow in combos:
        position = sma_crossover(prices["close"], fast=fast, slow=slow)
        result = run_backtest(prices, position, costs)
        stats = summarize(result, prices, periods_per_year=periods_per_year)
        rows.append({"fast": fast, "slow": slow, **{k: stats[k] for k in METRIC_COLUMNS}})
    table = pd.DataFrame(rows)
    return table.sort_values(metric, ascending=False, na_position="last").reset_index(drop=True)


def stats_from_returns(returns: pd.Series, periods_per_year: int) -> dict:
    """Summary statistics for a return series that starts from a flat equity of 1.0."""
    rets = returns.dropna()
    if rets.empty:
        return {"total_return": float("nan"), "cagr": float("nan"), "max_drawdown": float("nan"), "sharpe": float("nan")}
    equity = (1.0 + rets).cumprod()
    years = len(rets) / periods_per_year
    total = float(equity.iloc[-1] - 1.0)
    cagr = float(equity.iloc[-1] ** (1 / years) - 1) if years > 0 and equity.iloc[-1] > 0 else float("nan")
    drawdown = equity / equity.cummax() - 1.0
    std = rets.std()
    sharpe = float(rets.mean() / std * np.sqrt(periods_per_year)) if std and std > 0 else float("nan")
    return {"total_return": total, "cagr": cagr, "max_drawdown": float(drawdown.min()), "sharpe": sharpe}


@dataclass
class WalkForwardWindow:
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp
    fast: int
    slow: int
    in_sample_sharpe: float
    out_of_sample_sharpe: float


@dataclass
class WalkForwardResult:
    windows: list[WalkForwardWindow] = field(default_factory=list)
    oos_returns: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    oos_stats: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def walk_forward(
    prices: pd.DataFrame,
    combos: list[tuple[int, int]],
    costs: CostModel,
    periods_per_year: int,
    train_bars: int,
    test_bars: int,
    metric: str = "sharpe",
) -> WalkForwardResult:
    """Roll a train/test window forward through the data.

    For each window, parameters are chosen on the training bars only, then applied to the test bars.
    Test bars are never used for selection, so the combined result is out-of-sample.
    """
    if train_bars <= 0 or test_bars <= 0:
        raise ValueError("train_bars and test_bars must be positive")
    if len(prices) < train_bars + test_bars:
        raise ValueError("not enough data for one train/test window")

    prices = prices.reset_index(drop=True)
    result = WalkForwardResult()
    oos_parts: list[pd.Series] = []
    start = 0

    while start + train_bars + test_bars <= len(prices):
        train_end_idx = start + train_bars
        test_end_idx = train_end_idx + test_bars
        train = prices.iloc[start:train_end_idx].reset_index(drop=True)

        ranked = grid_search(train, combos, costs, periods_per_year, metric)
        best = ranked.iloc[0]
        fast, slow = int(best["fast"]), int(best["slow"])

        # Indicators use only past bars, so the full history up to this window's end is safe to use.
        upto = prices.iloc[:test_end_idx].reset_index(drop=True)
        position = sma_crossover(upto["close"], fast=fast, slow=slow)
        net = run_backtest(upto, position, costs).net_returns.reset_index(drop=True)
        test_returns = net.iloc[train_end_idx:test_end_idx]
        oos_parts.append(pd.Series(test_returns.values, index=prices["date"].iloc[train_end_idx:test_end_idx].values))

        oos_stats = stats_from_returns(test_returns, periods_per_year)
        result.windows.append(
            WalkForwardWindow(
                train_start=prices["date"].iloc[start],
                train_end=prices["date"].iloc[train_end_idx - 1],
                test_start=prices["date"].iloc[train_end_idx],
                test_end=prices["date"].iloc[test_end_idx - 1],
                fast=fast,
                slow=slow,
                in_sample_sharpe=float(best["sharpe"]),
                out_of_sample_sharpe=oos_stats["sharpe"],
            )
        )
        start += test_bars  # roll forward by one test window

    result.oos_returns = pd.concat(oos_parts) if oos_parts else pd.Series(dtype=float)
    result.oos_stats = stats_from_returns(result.oos_returns, periods_per_year)
    result.warnings = overfit_warnings(result.windows, result.oos_stats)
    return result


def overfit_warnings(windows: list[WalkForwardWindow], oos_stats: dict) -> list[str]:
    """Plain-language warnings. These flag risk. They do not prove or disprove an edge."""
    warnings: list[str] = []
    is_values = [w.in_sample_sharpe for w in windows if not np.isnan(w.in_sample_sharpe)]
    oos_sharpe = oos_stats.get("sharpe", float("nan"))
    if is_values and not np.isnan(oos_sharpe):
        mean_is = float(np.mean(is_values))
        if oos_sharpe < 0:
            warnings.append("Out-of-sample Sharpe is negative.")
        if mean_is > 0 and oos_sharpe < 0.5 * mean_is:
            warnings.append("Out-of-sample Sharpe is less than half of the in-sample Sharpe. Possible overfitting.")
    if windows:
        unique_params = {(w.fast, w.slow) for w in windows}
        if len(unique_params) > max(1, len(windows) // 2):
            warnings.append("Selected parameters change often between windows. The result may be unstable.")
    if len(windows) < 3:
        warnings.append("Fewer than 3 windows. The out-of-sample sample is small.")
    return warnings
