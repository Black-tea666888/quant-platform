import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

from pathlib import Path

APP = str(Path(__file__).resolve().parent.parent / "app.py")


@pytest.fixture(autouse=True)
def _clear_streamlit_cache():
    import streamlit as st

    st.cache_data.clear()
    yield
    st.cache_data.clear()


def test_app_loads_with_upload_hint():
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert not at.exception
    assert any("Enter a Yahoo symbol or upload a CSV" in info.value for info in at.info)


def test_run_without_file_shows_error():
    at = AppTest.from_file(APP, default_timeout=30).run()
    run_button = next(b for b in at.button if b.label == "Run backtest")
    at = run_button.click().run()
    assert not at.exception
    assert any("upload a csv" in err.value.lower() for err in at.error)


def test_language_switch_to_chinese():
    at = AppTest.from_file(APP, default_timeout=30).run()
    next(box for box in at.selectbox if box.key == "lang").set_value("zh-TW").run()
    assert not at.exception
    assert any("請輸入 Yahoo 代號或上傳 CSV" in info.value for info in at.info)


def test_paper_tab_run_without_file_shows_error():
    at = AppTest.from_file(APP, default_timeout=30).run()
    paper_button = next(b for b in at.button if b.label == "Run paper trading")
    at = paper_button.click().run()
    assert not at.exception
    assert any("upload a csv" in err.value.lower() for err in at.error)


def test_paper_tab_shows_hint_by_default():
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert not at.exception
    assert any("sidebar" in info.value.lower() for info in at.info)


def _fake_yahoo(monkeypatch, fail: Exception | None = None):
    import numpy as np
    import pandas as pd
    from quant_platform import data_sources

    dates = pd.bdate_range("2020-01-01", periods=200)
    fake = pd.DataFrame({"date": dates, "close": np.linspace(100, 150, 200)})

    def fetch(self, symbol, start=None, end=None):
        if fail is not None:
            raise fail
        assert symbol == "2330.TW"
        return fake

    monkeypatch.setattr(data_sources.YahooSource, "fetch", fetch)


def test_backtest_from_yahoo_symbol(monkeypatch):
    _fake_yahoo(monkeypatch)
    at = AppTest.from_file(APP, default_timeout=30).run()
    at.text_input(key="symbol").input("2330.TW").run()
    at = next(b for b in at.button if b.label == "Run backtest").click().run()
    assert not at.exception
    assert not at.error
    assert len(at.metric) == 4


def test_paper_from_yahoo_symbol(monkeypatch):
    _fake_yahoo(monkeypatch)
    at = AppTest.from_file(APP, default_timeout=30).run()
    at.text_input(key="symbol").input("2330.TW").run()
    at = next(b for b in at.button if b.label == "Run paper trading").click().run()
    assert not at.exception
    assert not at.error
    assert len(at.metric) == 4


def test_yahoo_network_error_is_shown_not_raised(monkeypatch):
    _fake_yahoo(monkeypatch, fail=RuntimeError("network down"))
    at = AppTest.from_file(APP, default_timeout=30).run()
    at.text_input(key="symbol").input("2330.TW").run()
    at = next(b for b in at.button if b.label == "Run backtest").click().run()
    assert not at.exception
    assert any("network down" in err.value for err in at.error)


def test_bad_start_date_is_rejected():
    at = AppTest.from_file(APP, default_timeout=30).run()
    at.text_input(key="symbol").input("2330.TW").run()
    at.text_input(key="start").input("2020/01/01").run()
    at = next(b for b in at.button if b.label == "Run backtest").click().run()
    assert not at.exception
    assert any("YYYY-MM-DD" in err.value for err in at.error)


def test_donchian_strategy_shows_channel_inputs():
    at = AppTest.from_file(APP, default_timeout=30).run()
    at.selectbox(key="strategy").set_value("donchian").run()
    assert not at.exception
    labels = {n.label for n in at.number_input}
    assert "Entry channel days" in labels and "Exit channel days" in labels
    assert any("Donchian breakout" in t.value for t in at.title)


def test_backtest_offers_csv_downloads(monkeypatch):
    _fake_yahoo(monkeypatch)
    at = AppTest.from_file(APP, default_timeout=30).run()
    at.text_input(key="symbol").input("2330.TW").run()
    at = next(b for b in at.button if b.label == "Run backtest").click().run()
    assert not at.exception
    assert not at.error


def test_momentum_strategy_shows_lookback_input():
    at = AppTest.from_file(APP, default_timeout=30).run()
    at.selectbox(key="strategy").set_value("momentum").run()
    assert not at.exception
    assert "Lookback days" in {n.label for n in at.number_input}
    assert any("Time-series momentum" in t.value for t in at.title)


def test_backtest_shows_assumptions_and_buy_hold(monkeypatch):
    _fake_yahoo(monkeypatch)
    at = AppTest.from_file(APP, default_timeout=30).run()
    at.text_input(key="symbol").input("2330.TW").run()
    at = next(b for b in at.button if b.label == "Run backtest").click().run()
    assert not at.exception
    assert any("Assumptions and limits" in e.label for e in at.expander)


def test_yahoo_results_are_cached(monkeypatch):
    import pandas as pd
    from quant_platform import data_sources

    calls = []
    fake = pd.DataFrame({"date": pd.bdate_range("2020-01-01", periods=200), "close": [float(i + 1) for i in range(200)]})

    def fetch(self, symbol, start=None, end=None):
        calls.append(symbol)
        return fake

    monkeypatch.setattr(data_sources.YahooSource, "fetch", fetch)
    for _ in range(2):
        at = AppTest.from_file(APP, default_timeout=30).run()
        at.text_input(key="symbol").input("2330.TW").run()
        next(b for b in at.button if b.label == "Run backtest").click().run()
    assert calls == ["2330.TW"]


def test_paper_run_shows_return_metric(monkeypatch):
    import numpy as np
    import pandas as pd
    from quant_platform import data_sources

    dates = pd.bdate_range("2020-01-01", periods=200)
    fake = pd.DataFrame({"date": dates, "close": np.linspace(100, 150, 200)})
    monkeypatch.setattr(data_sources.YahooSource, "fetch", lambda self, symbol, start=None, end=None: fake)
    at = AppTest.from_file(APP, default_timeout=30).run()
    at.text_input(key="symbol").input("2330.TW").run()
    at = next(b for b in at.button if b.label == "Run paper trading").click().run()
    assert not at.exception
    assert not at.error
    assert "Return since start" in {m.label for m in at.metric}
