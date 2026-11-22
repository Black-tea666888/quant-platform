import numpy as np
import pandas as pd
import pytest

from quant_platform.cli import main
from quant_platform.strategy import build_position, donchian_breakout, sma_crossover


def test_donchian_enters_on_breakout_and_exits_on_breakdown():
    close = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0, 4.0, 3.0, 2.0])
    pos = donchian_breakout(close, entry_days=3, exit_days=2)
    # Bar 3 (close 4) breaks above 1,2,3 -> long. Bar 6 (close 3) breaks below 5,4 -> flat.
    assert pos.tolist() == [0, 0, 0, 1, 1, 1, 0, 0]


def test_donchian_uses_only_past_data():
    rng = np.random.default_rng(1)
    close = pd.Series(100 * np.cumprod(1 + rng.normal(0, 0.02, 300)))
    full = donchian_breakout(close, entry_days=20, exit_days=10)
    cut = 150
    truncated = donchian_breakout(close.iloc[:cut], entry_days=20, exit_days=10)
    pd.testing.assert_series_equal(full.iloc[:cut], truncated, check_names=False)


def test_donchian_rejects_exit_not_below_entry():
    with pytest.raises(ValueError):
        donchian_breakout(pd.Series([1.0, 2.0, 3.0]), entry_days=5, exit_days=5)


def test_build_position_dispatches_and_rejects_unknown():
    close = pd.Series(np.linspace(1, 100, 120))
    assert build_position("sma", close, fast=5, slow=20).equals(sma_crossover(close, fast=5, slow=20))
    assert build_position("donchian", close, entry_days=10, exit_days=5).equals(
        donchian_breakout(close, entry_days=10, exit_days=5)
    )
    with pytest.raises(ValueError):
        build_position("nope", close)


def test_cli_runs_donchian(tmp_path, capsys):
    closes = [100.0 + i * 0.5 for i in range(200)]
    path = tmp_path / "prices.csv"
    pd.DataFrame({"date": pd.bdate_range("2020-01-01", periods=200), "close": closes}).to_csv(path, index=False)
    assert main(["--csv", str(path), "--strategy", "donchian", "--entry-days", "20", "--exit-days", "10"]) == 0
    assert "Donchian breakout (entry 20 / exit 10)" in capsys.readouterr().out


def test_cli_rejects_donchian_exit_not_below_entry(tmp_path):
    path = tmp_path / "prices.csv"
    pd.DataFrame({"date": pd.bdate_range("2020-01-01", periods=50), "close": range(1, 51)}).to_csv(path, index=False)
    with pytest.raises(SystemExit):
        main(["--csv", str(path), "--strategy", "donchian", "--entry-days", "10", "--exit-days", "10"])


def test_momentum_long_when_above_lookback_close():
    from quant_platform.strategy import time_series_momentum

    close = pd.Series([1.0, 2.0, 3.0, 2.0, 1.0, 4.0])
    pos = time_series_momentum(close, lookback=2)
    # Bar 2: 3 > 1 -> long. Bar 3: 2 > 2 is False -> flat. Bar 4: 1 < 3 -> flat. Bar 5: 4 > 1 -> long.
    assert pos.tolist() == [0, 0, 1, 0, 0, 1]


def test_momentum_uses_only_past_data():
    from quant_platform.strategy import time_series_momentum

    rng = np.random.default_rng(2)
    close = pd.Series(100 * np.cumprod(1 + rng.normal(0, 0.02, 300)))
    full = time_series_momentum(close, lookback=30)
    truncated = time_series_momentum(close.iloc[:150], lookback=30)
    pd.testing.assert_series_equal(full.iloc[:150], truncated, check_names=False)


def test_momentum_rejects_non_positive_lookback():
    from quant_platform.strategy import time_series_momentum

    with pytest.raises(ValueError):
        time_series_momentum(pd.Series([1.0, 2.0]), lookback=0)


def test_cli_runs_momentum(tmp_path, capsys):
    closes = [100.0 + i * 0.5 for i in range(200)]
    path = tmp_path / "prices.csv"
    pd.DataFrame({"date": pd.bdate_range("2020-01-01", periods=200), "close": closes}).to_csv(path, index=False)
    assert main(["--csv", str(path), "--strategy", "momentum", "--lookback", "30"]) == 0
    assert "Time-series momentum (lookback 30 days)" in capsys.readouterr().out
