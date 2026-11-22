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
