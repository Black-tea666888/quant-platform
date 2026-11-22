"""Market profiles: currency, trading calendar, and cost rules live here instead of in the engine.

Adding a market means adding a profile (in code or a JSON file), not changing the backtest engine.
Rates are defaults for illustration. Always verify them against your broker and official sources.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path

from quant_platform.i18n import t


@dataclass(frozen=True)
class Market:
    code: str                 # short identifier, e.g. "TW"
    name: str                 # display name
    currency: str             # ISO currency code
    timezone: str             # IANA timezone of the exchange
    ticker_suffix: str        # suffix used by Yahoo Finance, e.g. ".TW" (empty if none)
    trading_days_per_year: int = 252
    commission: float = 0.0          # brokerage fee rate per side
    sell_tax: float = 0.0            # transaction tax on sells
    default_slippage: float = 0.0005 # assumed one-way slippage


MARKETS: dict[str, Market] = {
    "TW": Market(
        code="TW",
        name="Taiwan Stock Exchange",
        currency="TWD",
        timezone="Asia/Taipei",
        ticker_suffix=".TW",
        commission=0.001425,   # 0.1425% per side, before any broker discount
        sell_tax=0.003,        # 0.3% on sells for ordinary stocks (ETFs differ)
    ),
    "US": Market(
        code="US",
        name="US equities (illustrative)",
        currency="USD",
        timezone="America/New_York",
        ticker_suffix="",
        commission=0.0,        # many brokers charge no commission; verify yours
        sell_tax=0.0,          # regulatory fees are small; verify and add if needed
    ),
}


def get_market(code: str) -> Market:
    try:
        return MARKETS[code.upper()]
    except KeyError as exc:
        known = ", ".join(sorted(MARKETS))
        raise ValueError(t("error_unknown_market", code=code, known=known)) from exc


def load_market_file(path: str | Path) -> Market:
    """Load a market profile from a JSON file with the same fields as Market."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return Market(**data)


def market_to_dict(market: Market) -> dict:
    return asdict(market)
