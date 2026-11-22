import numpy as np
import pandas as pd
import pytest

from quant_platform.backtest import CostModel, run_backtest, summarize
from quant_platform.report import build_report_html, monthly_returns, write_report
from quant_platform.strategy import sma_crossover


def _result(n=400, seed=4):
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0.0004, 0.012, n)))
    prices = pd.DataFrame({"date": pd.bdate_range("2021-01-01", periods=n), "close": close})
    result = run_backtest(prices, sma_crossover(prices["close"], 5, 20), CostModel(0, 1, 0, 0))
    stats = summarize(result, prices)
    return result, stats


def test_report_contains_key_sections_and_svg():
    result, stats = _result()
    doc = build_report_html("Test", result.equity, stats, result.trades, lang="en")
    assert "<svg" in doc and "Monthly returns" in doc and "Summary" in doc
    assert "Total return" in doc


def test_report_localizes_to_chinese():
    result, stats = _result()
    doc = build_report_html("測試", result.equity, stats, result.trades, lang="zh-TW")
    assert "月報酬" in doc and "摘要" in doc


def test_title_is_escaped():
    result, stats = _result()
    doc = build_report_html("<script>x</script>", result.equity, stats, result.trades)
    assert "<script>x</script>" not in doc
    assert "&lt;script&gt;" in doc


def test_monthly_table_covers_each_year():
    result, _ = _result(n=600)
    table = monthly_returns(result.equity)
    assert len(table.columns) == 12
    assert len(table) == result.equity.index.year.nunique()


def test_write_report_creates_file(tmp_path):
    result, stats = _result()
    out = write_report(tmp_path / "r.html", title="T", equity=result.equity, stats=stats, trades=result.trades)
    assert out.exists() and out.read_text(encoding="utf-8").startswith("<!DOCTYPE html>")


def test_cli_writes_report(tmp_path, capsys):
    from quant_platform.cli import main

    rng = np.random.default_rng(12)
    closes = 100 * np.exp(np.cumsum(rng.normal(0.0004, 0.012, 300)))
    csv = tmp_path / "p.csv"
    pd.DataFrame({"date": pd.bdate_range("2021-01-01", periods=300), "close": closes}).to_csv(csv, index=False)
    report = tmp_path / "report.html"
    assert main(["--csv", str(csv), "--fast", "5", "--slow", "20", "--report", str(report)]) == 0
    assert report.exists()
    assert "<svg" in report.read_text(encoding="utf-8")
