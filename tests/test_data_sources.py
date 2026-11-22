import pandas as pd
import pytest

from quant_platform.data_sources import CsvSource, get_source


@pytest.fixture
def csv_path(tmp_path):
    path = tmp_path / "p.csv"
    pd.DataFrame(
        {"date": pd.date_range("2020-01-01", periods=10, freq="D"), "close": range(100, 110)}
    ).to_csv(path, index=False)
    return str(path)


def test_csv_source_loads_all_rows(csv_path):
    df = CsvSource().fetch(csv_path)
    assert len(df) == 10
    assert list(df.columns) == ["date", "close"]


def test_csv_source_filters_by_date_range(csv_path):
    df = CsvSource().fetch(csv_path, start="2020-01-03", end="2020-01-06")
    assert df["date"].min() == pd.Timestamp("2020-01-03")
    assert df["date"].max() == pd.Timestamp("2020-01-05")  # end is exclusive


def test_get_source_rejects_unknown_name():
    with pytest.raises(ValueError, match="Unknown data source"):
        get_source("nope")


def test_registry_contains_builtin_sources():
    assert get_source("csv").name == "csv"
    assert get_source("yahoo").name == "yahoo"


SAMPLE_TWSE = {
    "stat": "OK",
    "data": [
        ["113/03/01", "24,167,721", "16,699,995,060", "697.00", "697.00", "688.00", "689.00", "-1.00", "26,282", ""],
        ["113/03/04", "97,210,112", "69,868,348,694", "714.00", "725.00", "711.00", "725.00", "+36.00", "125,799", ""],
        ["113/03/05", "0", "0", "--", "--", "--", "--", "0", "0", ""],
    ],
}


def test_parse_twse_month_converts_roc_dates_and_skips_no_trade_days():
    from quant_platform.data_sources import parse_twse_month

    df = parse_twse_month(SAMPLE_TWSE)
    assert df["date"].tolist() == [pd.Timestamp("2024-03-01"), pd.Timestamp("2024-03-04")]
    assert df["close"].tolist() == [689.0, 725.0]


def test_parse_twse_month_raises_on_error_response():
    import pytest

    from quant_platform.data_sources import parse_twse_month

    with pytest.raises(ValueError):
        parse_twse_month({"stat": "很抱歉，目前無法提供資料"})


def test_twse_source_fetches_each_month_and_filters(monkeypatch):
    from quant_platform import data_sources

    requested = []

    def fake_fetch(code, yyyymm):
        requested.append((code, yyyymm))
        return SAMPLE_TWSE

    monkeypatch.setattr(data_sources, "fetch_twse_month", fake_fetch)
    monkeypatch.setattr(data_sources, "TWSE_REQUEST_DELAY_SECONDS", 0)
    df = data_sources.get_source("twse").fetch("2330.TW", "2024-03-01", "2024-04-01")
    assert requested == [("2330", "202403")]
    assert df["close"].tolist() == [689.0, 725.0]
