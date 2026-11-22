import numpy as np
import pandas as pd
import pytest

from quant_platform.i18n import CATALOGS
from quant_platform.validate_cli import main


@pytest.fixture
def csv_path(tmp_path):
    rng = np.random.default_rng(7)
    closes = 100 * np.exp(np.cumsum(rng.normal(0.0003, 0.01, 1200)))
    path = tmp_path / "p.csv"
    pd.DataFrame({"date": pd.bdate_range("2015-01-01", periods=1200), "close": closes}).to_csv(path, index=False)
    return str(path)


def test_runs_and_prints_windows(csv_path, capsys):
    code = main(["--csv", csv_path, "--fast", "5,10", "--slow", "30,60", "--train-bars", "400", "--test-bars", "200"])
    assert code == 0
    out = capsys.readouterr().out
    assert "Window 1" in out
    assert "out-of-sample" in out.lower()


def test_chinese_output(csv_path, capsys):
    main(["--csv", csv_path, "--fast", "5", "--slow", "30", "--train-bars", "400", "--test-bars", "200", "--lang", "zh-TW"])
    assert "滾動前進驗證" in capsys.readouterr().out


def test_no_valid_pairs_is_an_error(csv_path, capsys):
    code = main(["--csv", csv_path, "--fast", "50", "--slow", "10"])
    assert code == 2
    assert "no valid" in capsys.readouterr().err


def test_rejects_non_numeric_windows(csv_path):
    with pytest.raises(SystemExit):
        main(["--csv", csv_path, "--fast", "abc"])


def test_new_keys_exist_in_both_languages():
    for key in ("wf_title", "wf_window", "wf_oos", "wf_warnings", "wf_no_warnings"):
        assert key in CATALOGS["en"] and key in CATALOGS["zh-TW"]
