"""HTML summary for the paper-trading bot."""
from quant_platform.bot import build_summary_html, main, write_summary_html

SUMMARY = [
    {
        "time": "2026-11-22T15:00:00+00:00",
        "strategy": "tsmc<script>",
        "new_orders": 2,
        "last_bar": "2026-11-20",
        "equity": 512345.678,
        "shares": 1000,
        "cash": 1234.5,
    }
]


def test_summary_escapes_values_and_shows_disclaimer():
    html = build_summary_html(SUMMARY, "en")
    assert "tsmc&lt;script&gt;" in html
    assert "<script>" not in html
    assert "512,345.68" in html
    assert "Paper trading only" in html


def test_summary_chinese_labels():
    html = build_summary_html(SUMMARY, "zh-TW")
    assert "模擬交易機器人" in html
    assert "僅為模擬交易" in html


def test_empty_run_has_placeholder():
    assert "No strategies have run yet." in build_summary_html([], "en")


def test_write_summary_html_creates_file(tmp_path):
    out = tmp_path / "summary.html"
    write_summary_html(SUMMARY, out, "en")
    assert out.read_text(encoding="utf-8").startswith("<!DOCTYPE html>")


def test_cli_rejects_unknown_language(tmp_path, capsys):
    import pytest

    with pytest.raises(SystemExit):
        main(["--config", str(tmp_path / "missing.json"), "--state-dir", str(tmp_path), "--summary-html", str(tmp_path / "x.html"), "--lang", "bad"])
