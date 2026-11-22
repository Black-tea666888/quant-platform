import importlib.util
from pathlib import Path

import pytest

APP_PATH = Path(__file__).resolve().parent.parent / "app.py"


@pytest.fixture(scope="module")
def app():
    spec = importlib.util.spec_from_file_location("quant_app_csv", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeUpload:
    """Stands in for Streamlit's UploadedFile: only getvalue() is used by the app."""

    def __init__(self, text: str):
        self._data = text.encode("utf-8")

    def getvalue(self) -> bytes:
        return self._data


CSV_TEXT = "date,close\n2020-01-02,100\n2020-01-03,101.5\n2020-01-06,99\n"


def test_csv_upload_is_loaded_and_cleaned(app):
    prices = app._load_prices("en", "", "2015-01-01", FakeUpload(CSV_TEXT), "yahoo")
    assert prices["close"].tolist() == [100.0, 101.5, 99.0]
    assert str(prices["date"].dtype).startswith("datetime64")


def test_symbol_takes_priority_over_csv(app, monkeypatch):
    from quant_platform import data_sources

    seen = []

    def fake_fetch(self, symbol, start=None, end=None):
        seen.append(symbol)
        return app.clean_prices(app.pd.DataFrame({"date": ["2020-01-02"], "close": [1.0]}))

    monkeypatch.setattr(data_sources.YahooSource, "fetch", fake_fetch)
    app.st.cache_data.clear()
    app._load_prices("en", "2330.TW", "2015-01-01", FakeUpload(CSV_TEXT), "yahoo")
    assert seen == ["2330.TW"]


def test_no_symbol_and_no_file_is_an_error(app):
    with pytest.raises(ValueError):
        app._load_prices("en", "", "2015-01-01", None, "yahoo")


def test_csv_missing_close_column_is_an_error(app):
    with pytest.raises(ValueError):
        app._load_prices("en", "", "2015-01-01", FakeUpload("date,price\n2020-01-02,1\n"), "yahoo")
