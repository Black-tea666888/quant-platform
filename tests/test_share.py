import importlib.util
from pathlib import Path

import pytest
import streamlit as st

APP_PATH = Path(__file__).resolve().parent.parent / "app.py"


@pytest.fixture(scope="module")
def app():
    spec = importlib.util.spec_from_file_location("quant_app", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def params(monkeypatch):
    values: dict = {}
    monkeypatch.setattr(st, "query_params", values)
    return values


def test_query_value_overrides_default(app, params):
    params["fast"] = "10"
    assert app._qp_int("fast", 20, 1) == 10


def test_bad_query_values_fall_back_to_defaults(app, params):
    params["fast"] = "abc"
    params["slow"] = "0"
    params["discount"] = "9"
    params["strategy"] = "nope"
    assert app._qp_int("fast", 20, 1) == 20
    assert app._qp_int("slow", 60, 2) == 60
    assert app._qp_float("discount", 1.0, 0.01, 1.0) == 1.0
    assert app._qp_index("strategy", ["sma", "donchian"], "sma") == 0


def test_share_settings_round_trip(app):
    settings = app._share_settings("zh-TW", "TW", "2330.TW", "2015-01-01", "donchian",
                                   {"entry_days": 55, "exit_days": 20}, 0.6)
    assert settings["symbol"] == "2330.TW"
    assert settings["strategy"] == "donchian"
    assert settings["entry_days"] == "55"
    assert settings["discount"] == "0.6"
    assert "fast" not in settings


def test_share_settings_omit_empty_symbol(app):
    settings = app._share_settings("en", "TW", "", "2015-01-01", "sma", {"fast": 20, "slow": 60}, 1.0)
    assert "symbol" not in settings
