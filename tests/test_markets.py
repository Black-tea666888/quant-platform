import json

import pytest

from quant_platform.backtest import CostModel
from quant_platform.markets import MARKETS, get_market, load_market_file


def test_taiwan_profile_matches_documented_rates():
    tw = get_market("TW")
    assert tw.currency == "TWD"
    assert tw.ticker_suffix == ".TW"
    assert tw.commission == pytest.approx(0.001425)
    assert tw.sell_tax == pytest.approx(0.003)


def test_market_lookup_is_case_insensitive_and_rejects_unknown():
    assert get_market("tw").code == "TW"
    with pytest.raises(ValueError, match="Unknown market"):
        get_market("XX")


def test_cost_model_from_market_uses_profile_rates():
    tw = get_market("TW")
    costs = CostModel.from_market(tw, discount=0.6)
    assert costs.commission == tw.commission
    assert costs.discount == 0.6
    assert costs.sell_tax == tw.sell_tax
    assert costs.sell_rate > costs.buy_rate  # selling also pays the tax


def test_slippage_override_wins_over_profile_default():
    costs = CostModel.from_market(get_market("US"), slippage=0.0)
    assert costs.slippage == 0.0


def test_load_market_file_round_trip(tmp_path):
    path = tmp_path / "custom.json"
    path.write_text(
        json.dumps(
            {
                "code": "JP",
                "name": "Japan (test)",
                "currency": "JPY",
                "timezone": "Asia/Tokyo",
                "ticker_suffix": ".T",
                "trading_days_per_year": 245,
                "commission": 0.001,
                "sell_tax": 0.0,
                "default_slippage": 0.0005,
            }
        ),
        encoding="utf-8",
    )
    market = load_market_file(path)
    assert market.code == "JP"
    assert market.trading_days_per_year == 245


def test_every_builtin_market_has_required_fields():
    for code, market in MARKETS.items():
        assert market.code == code
        assert market.currency and market.timezone
        assert market.trading_days_per_year > 0
