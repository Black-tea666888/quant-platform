"""Smoke tests for the walk-forward validation tab in the Streamlit app."""
from pathlib import Path

import pytest

pytest.importorskip("streamlit")

from streamlit.testing.v1 import AppTest  # noqa: E402

from app import _parse_int_list  # noqa: E402

APP = str(Path(__file__).resolve().parent.parent / "app.py")


def test_page_renders_four_tabs_without_exceptions():
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert not at.exception
    assert len(at.tabs) == 4


def test_validation_tab_shows_inputs_and_run_button():
    at = AppTest.from_file(APP, default_timeout=30).run()
    keys = {w.key for w in at.text_input}
    assert {"wf_fast", "wf_slow"} <= keys
    assert any(b.key == "wf_run" for b in at.button)


def test_run_without_data_shows_error_not_crash():
    at = AppTest.from_file(APP, default_timeout=30).run()
    next(b for b in at.button if b.key == "wf_run").click().run()
    assert not at.exception
    assert any("CSV" in e.value or "csv" in e.value.lower() for e in at.error)


def test_parse_int_list_accepts_and_rejects():
    assert _parse_int_list("5, 10,20", "en") == [5, 10, 20]
    with pytest.raises(ValueError):
        _parse_int_list("5,x", "en")
    with pytest.raises(ValueError):
        _parse_int_list("0,5", "en")


def test_portfolio_run_without_symbols_shows_error():
    at = AppTest.from_file(APP, default_timeout=30).run()
    next(b for b in at.button if b.key == "pf_run").click().run()
    assert not at.exception
    assert any("two" in e.value.lower() or "兩個" in e.value for e in at.error)
