import pandas as pd
import pytest

from quant_platform.paper_cli import main


def _write_csv(path, n):
    closes = [100.0 + (i % 7) * 2.0 + i * 0.3 for i in range(n)]
    pd.DataFrame({"date": pd.bdate_range("2023-01-02", periods=n), "close": closes}).to_csv(path, index=False)


def test_daily_runs_catch_up_without_duplicating(tmp_path, capsys):
    csv = tmp_path / "p.csv"
    state = tmp_path / "state.json"
    _write_csv(csv, 80)
    assert main(["--csv", str(csv), "--state", str(state), "--capital", "100000", "--fast", "5", "--slow", "20", "--lot-size", "1"]) == 0
    first_run = capsys.readouterr().out
    assert "Last bar" in first_run

    # Second run on the same data should place no new orders.
    assert main(["--csv", str(csv), "--state", str(state), "--fast", "5", "--slow", "20", "--lot-size", "1"]) == 0
    assert "New orders this run: 0" in capsys.readouterr().out


def test_new_state_requires_capital(tmp_path, capsys):
    csv = tmp_path / "p.csv"
    _write_csv(csv, 30)
    code = main(["--csv", str(csv), "--state", str(tmp_path / "missing.json")])
    assert code == 2
    assert "--capital is required" in capsys.readouterr().err


def test_state_cannot_switch_market(tmp_path, capsys):
    csv = tmp_path / "p.csv"
    state = tmp_path / "state.json"
    _write_csv(csv, 30)
    assert main(["--csv", str(csv), "--state", str(state), "--capital", "5000", "--fast", "3", "--slow", "10", "--market", "US"]) == 0
    code = main(["--csv", str(csv), "--state", str(state), "--fast", "3", "--slow", "10", "--market", "TW"])
    assert code == 2
    assert "opened in market US" in capsys.readouterr().err


def test_state_file_is_written(tmp_path):
    csv = tmp_path / "p.csv"
    state = tmp_path / "state.json"
    _write_csv(csv, 30)
    main(["--csv", str(csv), "--state", str(state), "--capital", "5000", "--fast", "3", "--slow", "10"])
    assert state.exists()
    assert '"capital": 5000.0' in state.read_text(encoding="utf-8")
