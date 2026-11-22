import pandas as pd
import pytest

from quant_platform.backtest import CostModel
from quant_platform.paper import PaperAccount, advance

FREE = CostModel(commission=0.0, discount=1.0, sell_tax=0.0, slippage=0.0)


def _prices(closes):
    return pd.DataFrame({"date": pd.date_range("2024-01-01", periods=len(closes), freq="D"), "close": closes})


def test_buy_then_sell_round_trip_free_costs():
    prices = _prices([100.0, 100.0, 110.0])
    position = pd.Series([1.0, 1.0, 0.0])
    account = PaperAccount.new(1000.0)
    orders = advance(account, prices, position, FREE)
    assert [o["side"] for o in orders] == ["BUY", "SELL"]
    assert account.shares == 0
    assert account.cash == pytest.approx(1100.0)


def test_orders_execute_at_the_decision_bar_close():
    prices = _prices([100.0, 120.0])
    position = pd.Series([0.0, 1.0])
    account = PaperAccount.new(1000.0)
    orders = advance(account, prices, position, FREE)
    assert len(orders) == 1
    assert orders[0]["date"] == "2024-01-02"
    assert orders[0]["price"] == pytest.approx(120.0)


def test_lot_size_is_respected():
    prices = _prices([100.0])
    account = PaperAccount.new(1000.0)
    advance(account, prices, pd.Series([1.0]), FREE, lot_size=1000)
    assert account.shares == 0  # cannot afford one full lot of 1000 at 100 with 1000 capital


def test_fees_and_tax_reduce_cash():
    costs = CostModel(commission=0.001425, discount=1.0, sell_tax=0.003, slippage=0.0)
    prices = _prices([100.0, 100.0])
    account = PaperAccount.new(10_000.0)
    advance(account, prices, pd.Series([1.0, 0.0]), costs)
    assert account.cash < 10_000.0
    assert account.shares == 0


def test_running_again_does_not_duplicate_orders(tmp_path):
    prices = _prices([100.0, 101.0, 102.0])
    position = pd.Series([1.0, 1.0, 1.0])
    account = PaperAccount.new(1000.0)
    first = advance(account, prices, position, FREE)
    second = advance(account, prices, position, FREE)
    assert len(first) == 1
    assert second == []
    assert len(account.equity_curve) == 3


def test_incremental_run_matches_single_run():
    prices = _prices([100.0, 105.0, 95.0, 110.0])
    position = pd.Series([1.0, 1.0, 0.0, 1.0])

    whole = PaperAccount.new(1000.0)
    advance(whole, prices, position, FREE)

    piecewise = PaperAccount.new(1000.0)
    advance(piecewise, prices.iloc[:2].reset_index(drop=True), position.iloc[:2].reset_index(drop=True), FREE)
    advance(piecewise, prices, position, FREE)

    assert piecewise.cash == pytest.approx(whole.cash)
    assert piecewise.shares == pytest.approx(whole.shares)


def test_state_round_trip(tmp_path):
    path = tmp_path / "state.json"
    account = PaperAccount.new(1000.0)
    advance(account, _prices([100.0, 101.0]), pd.Series([1.0, 1.0]), FREE)
    account.save(path)
    loaded = PaperAccount.load(path)
    assert loaded.to_dict() == account.to_dict()


def test_cash_never_goes_negative():
    costs = CostModel(commission=0.001425, discount=0.6, sell_tax=0.003, slippage=0.0005)
    prices = _prices([50.0, 51.0, 49.0, 52.0, 48.0])
    account = PaperAccount.new(777.0)
    advance(account, prices, pd.Series([1.0, 0.5, 1.0, 0.0, 1.0]), costs, lot_size=1)
    assert account.cash >= 0


def test_no_churn_while_signal_is_unchanged():
    # Holding a full position through price moves should not generate extra orders.
    prices = _prices([100.0, 105.0, 98.0, 110.0, 120.0])
    account = PaperAccount.new(1000.0)
    orders = advance(account, prices, pd.Series([1.0, 1.0, 1.0, 1.0, 1.0]), FREE)
    assert len(orders) == 1
    assert orders[0]["side"] == "BUY"


def test_rejects_capital_not_positive():
    with pytest.raises(ValueError):
        PaperAccount.new(0)
