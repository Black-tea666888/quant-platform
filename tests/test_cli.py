import pandas as pd
import pytest

from quant_platform.cli import main
from quant_platform.i18n import CATALOGS, t


@pytest.fixture
def csv_path(tmp_path):
    closes = [100.0 + i * 0.5 for i in range(200)]
    path = tmp_path / "prices.csv"
    pd.DataFrame({"date": pd.bdate_range("2020-01-01", periods=200), "close": closes}).to_csv(path, index=False)
    return str(path)


def test_runs_in_english_by_default(csv_path, capsys):
    assert main(["--csv", csv_path, "--fast", "5", "--slow", "20"]) == 0
    out = capsys.readouterr().out
    assert "Total return" in out
    assert "Taiwan" in out or "TW" in out


def test_runs_in_traditional_chinese(csv_path, capsys):
    assert main(["--csv", csv_path, "--fast", "5", "--slow", "20", "--lang", "zh-TW"]) == 0
    out = capsys.readouterr().out
    assert "總報酬" in out
    assert "回測結果不代表未來績效" in out


def test_rejects_fast_not_below_slow(csv_path):
    with pytest.raises(SystemExit):
        main(["--csv", csv_path, "--fast", "30", "--slow", "20"])


def test_rejects_non_positive_window(csv_path):
    with pytest.raises(SystemExit):
        main(["--csv", csv_path, "--fast", "0", "--slow", "20"])


def test_rejects_discount_out_of_range(csv_path):
    with pytest.raises(SystemExit):
        main(["--csv", csv_path, "--discount", "1.5"])


def test_rejects_negative_rate(csv_path):
    with pytest.raises(SystemExit):
        main(["--csv", csv_path, "--commission", "-0.01"])


def test_rejects_bad_date_format(capsys):
    with pytest.raises(SystemExit):
        main(["--symbol", "2330", "--start", "2020/01/01"])


def test_rejects_start_after_end():
    with pytest.raises(SystemExit):
        main(["--symbol", "2330", "--start", "2021-01-01", "--end", "2020-01-01"])


def test_missing_csv_gives_friendly_error(tmp_path, capsys):
    code = main(["--csv", str(tmp_path / "nope.csv")])
    assert code == 2
    assert "File not found" in capsys.readouterr().err


def test_unknown_market_gives_friendly_error(csv_path, capsys):
    code = main(["--csv", csv_path, "--market", "XX"])
    assert code == 2
    assert "Unknown market" in capsys.readouterr().err


def test_every_key_has_a_translation_in_each_language():
    english_keys = set(CATALOGS["en"])
    for lang, catalog in CATALOGS.items():
        missing = english_keys - set(catalog)
        assert not missing, f"{lang} is missing: {sorted(missing)}"


def test_translation_falls_back_to_english():
    assert t("total_return", "fr") == CATALOGS["en"]["total_return"]


def test_cli_accepts_twse_source(monkeypatch, capsys):
    import numpy as np
    from quant_platform import data_sources

    dates = pd.bdate_range("2020-01-01", periods=200)
    fake = pd.DataFrame({"date": dates, "close": np.linspace(100, 150, 200)})
    monkeypatch.setattr(data_sources.TwseSource, "fetch", lambda self, symbol, start=None, end=None: fake)
    assert main(["--symbol", "2330", "--source", "twse", "--fast", "5", "--slow", "20"]) == 0
    assert "Total return" in capsys.readouterr().out
