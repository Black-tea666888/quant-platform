import json

import numpy as np
import pandas as pd
import pytest

from quant_platform.bot import BotConfigError, main, parse_config, run_once


def _base(**overrides):
    cfg = {
        "mode": "paper",
        "market": "US",
        "capital": 100000,
        "lot_size": 1,
        "strategies": [{"name": "s1", "csv": "x.csv", "fast": 5, "slow": 20}],
    }
    cfg.update(overrides)
    return cfg


def _write_csv(path, n=120, seed=1):
    rng = np.random.default_rng(seed)
    closes = 100 * np.exp(np.cumsum(rng.normal(0.0003, 0.01, n)))
    pd.DataFrame({"date": pd.bdate_range("2023-01-02", periods=n), "close": closes}).to_csv(path, index=False)
    return str(path)


def test_live_mode_is_rejected():
    with pytest.raises(BotConfigError, match="paper"):
        parse_config(_base(mode="live"))


def test_missing_mode_is_rejected():
    cfg = _base()
    del cfg["mode"]
    with pytest.raises(BotConfigError, match="paper"):
        parse_config(cfg)


def test_unknown_top_level_key_is_rejected():
    with pytest.raises(BotConfigError, match="unknown top-level"):
        parse_config(_base(broker="ibkr"))


def test_unknown_strategy_key_is_rejected():
    cfg = _base()
    cfg["strategies"][0]["order_type"] = "market"
    with pytest.raises(BotConfigError, match="unknown strategy"):
        parse_config(cfg)


def test_duplicate_names_are_rejected():
    cfg = _base()
    cfg["strategies"].append({"name": "s1", "csv": "y.csv", "fast": 5, "slow": 20})
    with pytest.raises(BotConfigError, match="duplicate"):
        parse_config(cfg)


def test_bad_strategy_name_is_rejected():
    cfg = _base()
    cfg["strategies"][0]["name"] = "../evil"
    with pytest.raises(BotConfigError, match="letters"):
        parse_config(cfg)


def test_fast_must_be_below_slow():
    cfg = _base()
    cfg["strategies"][0].update(fast=30, slow=10)
    with pytest.raises(BotConfigError, match="fast < slow"):
        parse_config(cfg)


def test_risk_values_are_validated():
    cfg = _base()
    cfg["strategies"][0]["stop_loss"] = 1.5
    with pytest.raises(ValueError):
        parse_config(cfg)


def test_run_once_creates_state_and_is_idempotent(tmp_path):
    csv = _write_csv(tmp_path / "x.csv")
    config = parse_config(_base(strategies=[{"name": "s1", "csv": csv, "fast": 5, "slow": 20}]))
    first = run_once(config, tmp_path / "state")
    assert (tmp_path / "state" / "s1.json").exists()
    assert first[0]["last_bar"] is not None
    second = run_once(config, tmp_path / "state")
    assert second[0]["new_orders"] == 0  # nothing new, so nothing traded


def test_each_run_only_processes_new_bars(tmp_path):
    full = _write_csv(tmp_path / "full.csv", n=150)
    short = tmp_path / "short.csv"
    pd.read_csv(full).head(120).to_csv(short, index=False)
    state = tmp_path / "state"
    run_once(parse_config(_base(strategies=[{"name": "s1", "csv": str(short), "fast": 5, "slow": 20}])), state)
    summary = run_once(parse_config(_base(strategies=[{"name": "s1", "csv": full, "fast": 5, "slow": 20}])), state)[0]
    assert summary["last_bar"] == pd.bdate_range("2023-01-02", periods=150)[-1].date().isoformat()


def test_capital_is_split_between_strategies(tmp_path):
    a = _write_csv(tmp_path / "a.csv", seed=2)
    b = _write_csv(tmp_path / "b.csv", seed=3)
    config = parse_config(
        _base(
            capital=200000,
            strategies=[
                {"name": "a", "csv": a, "fast": 5, "slow": 20},
                {"name": "b", "csv": b, "fast": 5, "slow": 20},
            ],
        )
    )
    run_once(config, tmp_path / "state")
    state_a = json.loads((tmp_path / "state" / "a.json").read_text(encoding="utf-8"))
    assert state_a["capital"] == pytest.approx(100000)


def test_state_cannot_switch_market(tmp_path):
    csv = _write_csv(tmp_path / "x.csv")
    state = tmp_path / "state"
    run_once(parse_config(_base(market="US", strategies=[{"name": "s1", "csv": csv, "fast": 5, "slow": 20}])), state)
    with pytest.raises(BotConfigError, match="market"):
        run_once(parse_config(_base(market="TW", strategies=[{"name": "s1", "csv": csv, "fast": 5, "slow": 20}])), state)


def test_log_file_gets_one_line_per_strategy(tmp_path):
    csv = _write_csv(tmp_path / "x.csv")
    log = tmp_path / "bot.log"
    config = parse_config(_base(strategies=[{"name": "s1", "csv": csv, "fast": 5, "slow": 20}]))
    run_once(config, tmp_path / "state", log)
    run_once(config, tmp_path / "state", log)
    lines = log.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["strategy"] == "s1"


def test_cli_returns_error_code_for_live_mode(tmp_path, capsys):
    cfg = tmp_path / "bot.json"
    cfg.write_text(json.dumps(_base(mode="live")), encoding="utf-8")
    assert main(["--config", str(cfg), "--state-dir", str(tmp_path / "s")]) == 2
    assert "paper" in capsys.readouterr().err


def test_cli_runs_paper_config(tmp_path, capsys):
    csv = _write_csv(tmp_path / "x.csv")
    cfg = tmp_path / "bot.json"
    cfg.write_text(json.dumps(_base(strategies=[{"name": "s1", "csv": csv, "fast": 5, "slow": 20}])), encoding="utf-8")
    assert main(["--config", str(cfg), "--state-dir", str(tmp_path / "s")]) == 0
    assert "No real orders were placed" in capsys.readouterr().out
