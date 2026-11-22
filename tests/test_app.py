import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

from pathlib import Path

APP = str(Path(__file__).resolve().parent.parent / "app.py")


def test_app_loads_with_upload_hint():
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert not at.exception
    assert any("Upload a CSV" in info.value for info in at.info)


def test_run_without_file_shows_error():
    at = AppTest.from_file(APP, default_timeout=30).run()
    run_button = next(b for b in at.button if b.label == "Run backtest")
    at = run_button.click().run()
    assert not at.exception
    assert any("upload a csv" in err.value.lower() for err in at.error)


def test_language_switch_to_chinese():
    at = AppTest.from_file(APP, default_timeout=30).run()
    at.selectbox[0].set_value("zh-TW").run()
    assert not at.exception
    assert any("請上傳 CSV" in info.value for info in at.info)
