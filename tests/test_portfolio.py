import numpy as np
import pandas as pd
import pytest

from quant_platform.backtest import CostModel
from quant_platform.portfolio import (
    align_prices,
    rebalance_flags,
    run_portfolio,
    signal_weights,
)

FREE = CostModel(commission=0.0, discount=1.0, sell_tax=0.0, slippage=0.0)


def _frame(closes, start="2024-01-01"):
    return pd.DataFrame({"date": pd.bdate_range(start, periods=len(closes)), "close": closes})


def _wide(**series):
    return align_prices({k: _frame(v) for k, v in series.items()})


def test_align_keeps_only_shared_dates():
    a = pd.DataFrame({"date": pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"]), "close": [1.0, 2.0, 3.0]})
    b = pd.DataFrame({"date": pd.to_datetime(["2024-01-03", "2024-01-04"]), "close": [10.0, 20.0]})
    wide = align_prices({"A": a, "B": b})
    assert len(wide) == 2
    assert list(wide.columns) == ["A", "B"]


def test_flat_prices_with_free_costs_keep_equity_at_one():
    wide = _wide(A=[100.0] * 10, B=[50.0] * 10)
    result = run_portfolio(wide, None, FREE, freq="monthly")
    assert result.equity.iloc[-1] == pytest.approx(1.0)
    assert result.total_costs == 0


def test_monthly_rebalance_resets_drift():
    # A doubles while B stays flat. A monthly rebalance should bring weights back toward 50/50.
    n = 60
    wide = _wide(A=np.linspace(100, 200, n), B=[100.0] * n)
    drifting = run_portfolio(wide, None, FREE, freq="never")
    rebalanced = run_portfolio(wide, None, FREE, freq="monthly")
    assert drifting.weights["A"].iloc[-1] > 0.6
    assert rebalanced.weights["A"].iloc[-1] < drifting.weights["A"].iloc[-1]
    assert rebalanced.rebalances > 1


def test_costs_reduce_equity_when_rebalancing():
    n = 60
    wide = _wide(A=np.linspace(100, 200, n), B=[100.0] * n)
    costs = CostModel(commission=0.001425, discount=1.0, sell_tax=0.003, slippage=0.0005)
    free = run_portfolio(wide, None, FREE, freq="monthly")
    paid = run_portfolio(wide, None, costs, freq="monthly")
    assert paid.total_costs > 0
    assert paid.equity.iloc[-1] < free.equity.iloc[-1]


def test_never_rebalance_only_trades_once():
    wide = _wide(A=np.linspace(100, 120, 30), B=np.linspace(50, 60, 30))
    result = run_portfolio(wide, None, FREE, freq="never")
    assert result.rebalances == 1
    assert result.trades == 2  # one buy per symbol


def test_fixed_weights_leave_remainder_in_cash():
    wide = _wide(A=[100.0] * 5, B=[100.0] * 5)
    result = run_portfolio(wide, {"A": 0.3, "B": 0.3}, FREE, freq="never")
    assert result.weights.iloc[-1].sum() == pytest.approx(0.6)


def test_rejects_weights_over_one():
    wide = _wide(A=[100.0] * 5, B=[100.0] * 5)
    with pytest.raises(ValueError):
        run_portfolio(wide, {"A": 0.8, "B": 0.5}, FREE)


def test_signal_weights_go_to_cash_when_no_signal():
    closes = np.linspace(100, 50, 200)  # falling: SMA stays flat
    wide = _wide(A=closes, B=closes)
    weights = signal_weights(wide, fast=5, slow=20)
    assert (weights.iloc[-1] == 0).all()


def test_signal_weights_split_among_active_symbols():
    rising = np.linspace(100, 200, 200)
    falling = np.linspace(200, 100, 200)
    wide = _wide(A=rising, B=falling)
    weights = signal_weights(wide, fast=5, slow=20)
    assert weights["A"].iloc[-1] == pytest.approx(1.0)
    assert weights["B"].iloc[-1] == pytest.approx(0.0)


def test_rebalance_flags_monthly_marks_month_ends():
    dates = pd.bdate_range("2024-01-01", "2024-03-31")
    flags = rebalance_flags(dates, "monthly")
    marked = dates[flags]
    # First bar, plus the last bar of January, February and March.
    assert len(marked) == 4
    assert marked[0] == pd.Timestamp("2024-01-01")
    assert marked[-1] == pd.Timestamp("2024-03-29")


def test_rebalance_flags_rejects_unknown_frequency():
    with pytest.raises(ValueError):
        rebalance_flags(pd.bdate_range("2024-01-01", periods=5), "yearly")
