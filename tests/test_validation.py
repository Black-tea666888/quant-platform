import numpy as np
import pandas as pd
import pytest

from quant_platform.backtest import CostModel
from quant_platform.validation import (
    grid_search,
    make_grid,
    overfit_warnings,
    stats_from_returns,
    walk_forward,
    WalkForwardWindow,
)

FREE = CostModel(commission=0.0, discount=1.0, sell_tax=0.0, slippage=0.0)


def _prices(closes):
    return pd.DataFrame({"date": pd.bdate_range("2018-01-01", periods=len(closes)), "close": closes})


def _random_walk(n, seed=0, drift=0.0003):
    rng = np.random.default_rng(seed)
    return 100 * np.exp(np.cumsum(rng.normal(drift, 0.01, n)))


def test_make_grid_keeps_only_fast_below_slow():
    combos = make_grid([5, 20], [10, 60])
    assert (5, 10) in combos and (20, 60) in combos
    assert all(f < s for f, s in combos)
    assert (20, 10) not in combos


def test_grid_search_is_sorted_best_first():
    prices = _prices(_random_walk(600, seed=1))
    table = grid_search(prices, make_grid([5, 10], [30, 60]), FREE, periods_per_year=252)
    sharpes = table["sharpe"].dropna().tolist()
    assert sharpes == sorted(sharpes, reverse=True)


def test_grid_search_rejects_empty_combos():
    with pytest.raises(ValueError):
        grid_search(_prices([1.0, 2.0, 3.0]), [], FREE, periods_per_year=252)


def test_walk_forward_windows_do_not_overlap_and_cover_test_bars():
    prices = _prices(_random_walk(900, seed=2))
    result = walk_forward(prices, make_grid([5, 10], [30, 60]), FREE, 252, train_bars=300, test_bars=100)
    assert len(result.windows) >= 3
    for prev, nxt in zip(result.windows, result.windows[1:]):
        assert nxt.test_start > prev.test_end
    assert len(result.oos_returns) == sum(
        int((prices["date"].between(w.test_start, w.test_end)).sum()) for w in result.windows
    )


def test_selection_ignores_future_data():
    # Changing prices after the first window's test period must not change its selected parameters.
    base = _random_walk(900, seed=3)
    altered = base.copy()
    altered[600:] = altered[600:] * 1.5  # shock the data after the first window's test bars
    combos = make_grid([5, 10], [30, 60])
    first = walk_forward(_prices(base), combos, FREE, 252, train_bars=300, test_bars=100).windows[0]
    first_altered = walk_forward(_prices(altered), combos, FREE, 252, train_bars=300, test_bars=100).windows[0]
    assert (first.fast, first.slow) == (first_altered.fast, first_altered.slow)


def test_out_of_sample_returns_are_flat_when_position_is_flat():
    # A strictly falling series keeps the fast MA below the slow MA, so the strategy stays flat.
    prices = _prices(np.linspace(200, 100, 700))
    result = walk_forward(prices, make_grid([5, 10], [30, 60]), FREE, 252, train_bars=300, test_bars=100)
    assert result.oos_stats["total_return"] == pytest.approx(0.0, abs=1e-9)


def test_stats_from_returns_drawdown_and_total():
    rets = pd.Series([0.2, -0.25, 0.2222222])
    stats = stats_from_returns(rets, periods_per_year=252)
    assert stats["max_drawdown"] == pytest.approx(0.9 / 1.2 - 1.0, rel=1e-4)


def test_overfit_warning_flags_large_degradation():
    windows = [
        WalkForwardWindow(None, None, None, None, 5, 30, in_sample_sharpe=2.0, out_of_sample_sharpe=0.1),
        WalkForwardWindow(None, None, None, None, 5, 30, in_sample_sharpe=2.2, out_of_sample_sharpe=0.2),
        WalkForwardWindow(None, None, None, None, 5, 30, in_sample_sharpe=1.8, out_of_sample_sharpe=0.1),
    ]
    warnings = overfit_warnings(windows, {"sharpe": 0.15})
    assert any("overfitting" in w.lower() for w in warnings)


def test_walk_forward_rejects_short_data():
    with pytest.raises(ValueError):
        walk_forward(_prices([1.0] * 50), make_grid([2], [5]), FREE, 252, train_bars=40, test_bars=40)
