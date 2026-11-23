import math

import numpy as np
import pandas as pd
import pytest

from quant_platform.backtest import CostModel, run_backtest, summarize
from quant_platform.strategy import sma_crossover

FREE = CostModel(commission=0.0, discount=1.0, sell_tax=0.0, slippage=0.0)


def _prices(closes):
    dates = pd.date_range("2024-01-01", periods=len(closes), freq="D")
    return pd.DataFrame({"date": dates, "close": closes})


def test_decision_on_bar_does_not_capture_same_bar_move():
    # Jump happens from bar 2 to bar 3. A decision made at bar 2's close
    # cannot earn that jump, because it is only held from bar 3 onward.
    prices = _prices([100.0, 100.0, 110.0, 110.0])
    position = pd.Series([0.0, 0.0, 1.0, 1.0])
    result = run_backtest(prices, position, FREE)
    assert result.equity.iloc[-1] == pytest.approx(1.0)


def test_decision_before_jump_captures_it():
    # Decision at bar 1's close (100) is held through the 100 -> 110 move on bar 2.
    prices = _prices([100.0, 100.0, 110.0, 110.0])
    position = pd.Series([0.0, 1.0, 1.0, 1.0])
    result = run_backtest(prices, position, FREE)
    assert result.equity.iloc[-1] == pytest.approx(1.10)


def test_round_trip_costs_reduce_equity():
    prices = _prices([100.0] * 5)
    position = pd.Series([1.0, 1.0, 0.0, 0.0, 0.0])
    costs = CostModel(commission=0.001425, discount=1.0, sell_tax=0.003, slippage=0.0)
    result = run_backtest(prices, position, costs)
    expected = (1 - costs.buy_rate) * (1 - costs.sell_rate)
    assert result.equity.iloc[-1] == pytest.approx(expected)
    assert result.equity.iloc[-1] < 1.0


def test_no_trades_means_no_costs():
    prices = _prices(np.linspace(100, 120, 10))
    result = run_backtest(prices, pd.Series([0.0] * 10), CostModel())
    assert result.equity.iloc[-1] == pytest.approx(1.0)
    assert result.trades == []


def test_trade_records_entry_and_exit():
    prices = _prices([100.0, 100.0, 110.0, 110.0, 99.0, 99.0])
    position = pd.Series([0.0, 1.0, 1.0, 0.0, 0.0, 0.0])
    result = run_backtest(prices, position, FREE)
    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.exit_date is not None
    assert trade.return_ == pytest.approx(0.10)


def test_sma_is_flat_during_warmup_and_long_in_uptrend():
    close = pd.Series(np.arange(1.0, 101.0))  # steadily rising
    pos = sma_crossover(close, fast=5, slow=20)
    assert (pos.iloc[:19] == 0).all()
    assert (pos.iloc[25:] == 1).all()


def test_sma_rejects_bad_windows():
    with pytest.raises(ValueError):
        sma_crossover(pd.Series([1.0, 2.0, 3.0]), fast=5, slow=5)


def test_max_drawdown_and_summary_fields():
    prices = _prices([100.0, 120.0, 90.0, 110.0])
    position = pd.Series([1.0, 1.0, 1.0, 1.0])
    result = run_backtest(prices, position, FREE)
    stats = summarize(result, prices)
    # Holding from bar 1 onward: equity goes 1.0 -> 1.2 -> 0.9 -> 1.1 (relative to bar 0 close).
    assert stats["max_drawdown"] == pytest.approx(0.9 / 1.2 - 1.0)
    assert stats["buy_hold"] == pytest.approx(0.10)
    assert not math.isnan(stats["sharpe"])


def test_summary_includes_sortino_and_calmar():
    prices = _prices([100.0, 120.0, 90.0, 110.0])
    position = pd.Series([1.0, 1.0, 1.0, 1.0])
    result = run_backtest(prices, position, FREE)
    stats = summarize(result, prices)
    assert stats["calmar"] == pytest.approx(stats["cagr"] / abs(stats["max_drawdown"]))
    assert not math.isnan(stats["sortino"])
