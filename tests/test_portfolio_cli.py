import numpy as np
import pandas as pd
import pytest

from quant_platform.i18n import CATALOGS
from quant_platform.portfolio_cli import main


@pytest.fixture
def two_csvs(tmp_path):
    rng = np.random.default_rng(11)
    dates = pd.bdate_range("2018-01-01", periods=900)
    a = 100 * np.exp(np.cumsum(rng.normal(0.0005, 0.01, 900)))
    b = 50 * np.exp(np.cumsum(rng.normal(0.0001, 0.012, 900)))
    pa, pb = tmp_path / "a.csv", tmp_path / "b.csv"
    pd.DataFrame({"date": dates, "close": a}).to_csv(pa, index=False)
    pd.DataFrame({"date": dates, "close": b}).to_csv(pb, index=False)
    return str(pa), str(pb)


def test_equal_weight_mode_runs(two_csvs, capsys):
    a, b = two_csvs
    assert main(["--csv", f"A={a}", "--csv", f"B={b}", "--freq", "monthly", "--market", "US"]) == 0
    out = capsys.readouterr().out
    assert "Portfolio backtest" in out
    assert "Benchmark" in out


def test_signal_mode_runs(two_csvs, capsys):
    a, b = two_csvs
    code = main(["--csv", f"A={a}", "--csv", f"B={b}", "--mode", "signal", "--fast", "10", "--slow", "40", "--freq", "weekly"])
    assert code == 0
    assert "SMA signal" in capsys.readouterr().out


def test_bad_csv_argument_is_an_error(two_csvs, capsys):
    a, _ = two_csvs
    assert main(["--csv", a]) == 2  # missing SYMBOL=
    assert "SYMBOL=path.csv" in capsys.readouterr().err


def test_portfolio_keys_exist_in_both_languages():
    for key in ("pf_title", "pf_bench", "pf_rebalances", "pf_turnover", "pf_costs", "pf_orders", "pf_mode_equal", "pf_mode_signal"):
        assert key in CATALOGS["en"] and key in CATALOGS["zh-TW"]


def test_max_weight_caps_equal_weights(two_csvs, capsys):
    a, b = two_csvs
    assert main(["--csv", f"A={a}", "--csv", f"B={b}", "--max-weight", "0.3", "--freq", "monthly"]) == 0
    assert "Portfolio backtest" in capsys.readouterr().out
