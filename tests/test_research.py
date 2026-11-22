import numpy as np
import pandas as pd

from quant_platform.backtest import CostModel, run_backtest
from quant_platform.research import cost_sensitivity, split_periods
from quant_platform.strategy import donchian_breakout


def _prices(n=500, seed=4):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2019-01-01", periods=n)
    close = 100 * np.cumprod(1 + rng.normal(0.0003, 0.015, n))
    return pd.DataFrame({"date": dates, "close": close})


def test_split_covers_every_scored_bar_once():
    prices = _prices()
    pos = donchian_breakout(prices["close"], entry_days=30, exit_days=10)
    out = split_periods(prices, pos, CostModel(), "2020-12-31")
    total_bars = out["in_sample"]["bars"] + out["out_of_sample"]["bars"]
    assert total_bars == len(prices) - 1  # first bar has no return


def test_split_periods_use_the_same_signal():
    prices = _prices()
    pos = donchian_breakout(prices["close"], entry_days=30, exit_days=10)
    full = run_backtest(prices, pos, CostModel())
    out = split_periods(prices, pos, CostModel(), "2020-06-01")
    # Exposure is measured on the same held positions as the full run, so the two periods average to it.
    weighted = (out["in_sample"]["exposure"] * out["in_sample"]["bars"]
                + out["out_of_sample"]["exposure"] * out["out_of_sample"]["bars"])
    assert abs(weighted / (len(prices) - 1) - full.position.iloc[1:].mean()) < 1e-9


def test_higher_costs_never_improve_return():
    prices = _prices()
    pos = donchian_breakout(prices["close"], entry_days=30, exit_days=10)
    table = cost_sensitivity(prices, pos, CostModel(), discounts=(1.0,), slippages=(0.0005, 0.001, 0.002))
    returns = table.sort_values("slippage")["total_return"].tolist()
    assert returns == sorted(returns, reverse=True)


def test_cost_sensitivity_has_one_row_per_assumption():
    prices = _prices(200)
    pos = donchian_breakout(prices["close"], entry_days=20, exit_days=10)
    table = cost_sensitivity(prices, pos, CostModel(), discounts=(1.0, 0.6), slippages=(0.0005, 0.001))
    assert len(table) == 4
    assert set(table.columns) == {"discount", "slippage", "total_return", "cagr"}
