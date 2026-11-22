import numpy as np
import pandas as pd
import pytest

from quant_platform.backtest import CostModel, run_backtest
from quant_platform.risk import RiskRules, apply_risk_overlay, cap_weights

FREE = CostModel(commission=0.0, discount=1.0, sell_tax=0.0, slippage=0.0)


def _close(values):
    return pd.Series(values, dtype=float)


def test_inactive_rules_return_target_unchanged():
    close = _close([100, 90, 80, 70])
    target = _close([1, 1, 1, 1])
    out = apply_risk_overlay(close, target, RiskRules())
    assert out.tolist() == target.tolist()


def test_stop_loss_exits_and_stays_flat_while_signal_stays_on():
    # Entry at 100 (decided at bar 0 close, held from bar 1). Price falls to 85 at bar 3.
    close = _close([100, 100, 100, 85, 80, 70])
    target = _close([1, 1, 1, 1, 1, 1])
    out = apply_risk_overlay(close, target, RiskRules(stop_loss=0.10))
    assert out.iloc[3] == 0.0  # close 85 is 15% below entry, so exit
    assert (out.iloc[3:] == 0.0).all()  # no re-entry while the signal stays on


def test_reentry_after_signal_turns_off_and_on_again():
    close = _close([100, 100, 100, 85, 85, 90, 90])
    target = _close([1, 1, 1, 1, 0, 1, 1])
    out = apply_risk_overlay(close, target, RiskRules(stop_loss=0.10))
    assert out.iloc[3] == 0.0
    assert out.iloc[4] == 0.0  # signal turns off here
    assert out.iloc[5] == 1.0  # signal turns on again: re-entry allowed


def test_daily_loss_limit_exits_after_big_bar():
    close = _close([100, 100, 100, 90, 90])  # bar 3 falls 10%
    target = _close([1, 1, 1, 1, 1])
    out = apply_risk_overlay(close, target, RiskRules(daily_loss_limit=0.05))
    assert out.iloc[3] == 0.0


def test_max_drawdown_halt_stops_trading_until_signal_resets():
    close = _close([100, 110, 120, 96, 80, 85, 95])
    target = _close([1, 1, 1, 1, 1, 1, 0])
    out = apply_risk_overlay(close, target, RiskRules(max_drawdown_halt=0.15))
    # Equity peaks near 120 and falls to 96 (about -20%) at bar 3, so it halts.
    assert out.iloc[3] == 0.0
    assert (out.iloc[3:6] == 0.0).all()
    assert out.iloc[6] == 0.0


def test_overlay_reduces_worst_drawdown_in_backtest():
    rng = np.random.default_rng(3)
    close = _close(100 * np.exp(np.cumsum(rng.normal(0.0, 0.02, 400))))
    target = _close(np.ones(400))
    prices = pd.DataFrame({"date": pd.bdate_range("2020-01-01", periods=400), "close": close.values})
    raw = run_backtest(prices, target, FREE)
    guarded = run_backtest(prices, apply_risk_overlay(close, target, RiskRules(stop_loss=0.05)), FREE)
    raw_dd = (raw.equity / raw.equity.cummax() - 1).min()
    guarded_dd = (guarded.equity / guarded.equity.cummax() - 1).min()
    assert guarded_dd >= raw_dd  # less negative (or equal) when the stop is active


@pytest.mark.parametrize("value", [0.0, 1.0, -0.1, 1.5])
def test_rules_reject_out_of_range_values(value):
    with pytest.raises(ValueError):
        RiskRules(stop_loss=value)


def test_cap_weights_clips_and_leaves_cash():
    weights = pd.DataFrame({"A": [0.9, 0.5], "B": [0.1, 0.5]})
    capped = cap_weights(weights, 0.4)
    assert capped["A"].tolist() == [0.4, 0.4]
    assert capped.sum(axis=1).tolist() == pytest.approx([0.5, 0.8])


def test_cap_weights_rejects_bad_cap():
    with pytest.raises(ValueError):
        cap_weights(pd.DataFrame({"A": [0.5]}), 0.0)


def test_cli_runs_with_risk_flags(tmp_path, capsys):
    from quant_platform.cli import main

    rng = np.random.default_rng(9)
    closes = 100 * np.exp(np.cumsum(rng.normal(0.0, 0.02, 400)))
    path = tmp_path / "p.csv"
    pd.DataFrame({"date": pd.bdate_range("2020-01-01", periods=400), "close": closes}).to_csv(path, index=False)
    code = main(["--csv", str(path), "--fast", "5", "--slow", "20", "--stop-loss", "0.08", "--max-drawdown-halt", "0.25"])
    assert code == 0
    assert "Total return" in capsys.readouterr().out


def test_paper_cli_runs_with_risk_flags(tmp_path, capsys):
    from quant_platform.paper_cli import main as paper_main

    rng = np.random.default_rng(10)
    closes = 100 * np.exp(np.cumsum(rng.normal(0.0, 0.02, 200)))
    csv = tmp_path / "p.csv"
    pd.DataFrame({"date": pd.bdate_range("2020-01-01", periods=200), "close": closes}).to_csv(csv, index=False)
    state = tmp_path / "s.json"
    code = paper_main(["--csv", str(csv), "--state", str(state), "--capital", "10000", "--fast", "5", "--slow", "20", "--stop-loss", "0.1", "--lot-size", "1"])
    assert code == 0
