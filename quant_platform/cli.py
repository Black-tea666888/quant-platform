"""Command-line entry point: run a backtest (SMA crossover or Donchian breakout) on a CSV file or a Yahoo Finance symbol."""

from __future__ import annotations

import argparse
import math
import sys
from datetime import date

from quant_platform.backtest import CostModel, run_backtest, summarize
from quant_platform.data_sources import get_source
from quant_platform.i18n import DEFAULT_LANG, SUPPORTED_LANGS, t
from quant_platform.markets import MARKETS, Market, get_market, load_market_file
from quant_platform.strategy import (
    DEFAULT_STRATEGY, DONCHIAN_ENTRY_DAYS, DONCHIAN_EXIT_DAYS, MOMENTUM_LOOKBACK, STRATEGIES, build_position,
)

PERCENT_KEYS = {"total_return", "cagr", "max_drawdown", "exposure", "win_rate", "buy_hold"}
ROW_ORDER = [
    "start_date", "end_date", "total_return", "cagr", "max_drawdown", "sharpe",
    "exposure", "trades", "win_rate", "buy_hold",
]


def _format_value(key: str, value: object, lang: str) -> str:
    if isinstance(value, float):
        if math.isnan(value):
            return t("not_available", lang)
        return f"{value:.2%}" if key in PERCENT_KEYS else f"{value:.4f}"
    return str(value)


def _resolve_symbol(symbol: str, market: Market) -> str:
    """Append the market's ticker suffix (e.g. .TW) when the user omitted it."""
    if market.ticker_suffix and "." not in symbol:
        return symbol + market.ticker_suffix
    return symbol


def _non_negative(name: str):
    def parse(value: str) -> float:
        number = float(value)
        if number < 0:
            raise argparse.ArgumentTypeError(t("error_negative_rate", name=name))
        return number
    return parse


def _positive_int(name: str):
    def parse(value: str) -> int:
        try:
            number = int(value)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(t("error_positive_int", name=name)) from exc
        if number <= 0:
            raise argparse.ArgumentTypeError(t("error_positive_int", name=name))
        return number
    return parse


def _discount(value: str) -> float:
    number = float(value)
    if not 0 < number <= 1:
        raise argparse.ArgumentTypeError(t("error_bad_discount"))
    return number


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="SMA crossover backtest with market-specific costs")
    p.add_argument("--lang", default=DEFAULT_LANG, choices=SUPPORTED_LANGS, help="output language")

    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--csv", help="price CSV with at least date and close columns")
    src.add_argument("--symbol", help="Yahoo Finance symbol, e.g. 2330 or 2330.TW")

    mkt = p.add_mutually_exclusive_group()
    mkt.add_argument("--market", default="TW", help=f"market code: {', '.join(sorted(MARKETS))} (default TW)")
    mkt.add_argument("--market-file", help="JSON file describing a custom market profile")

    p.add_argument("--start", default="2015-01-01", help="start date YYYY-MM-DD (only with --symbol)")
    p.add_argument("--end", default=None, help="end date YYYY-MM-DD (only with --symbol)")
    p.add_argument("--strategy", default=DEFAULT_STRATEGY, choices=STRATEGIES, help="sma or donchian")
    p.add_argument("--fast", type=_positive_int("--fast"), default=20, help="SMA fast window")
    p.add_argument("--slow", type=_positive_int("--slow"), default=60, help="SMA slow window")
    p.add_argument("--entry-days", type=_positive_int("--entry-days"), default=DONCHIAN_ENTRY_DAYS, help="Donchian entry channel")
    p.add_argument("--exit-days", type=_positive_int("--exit-days"), default=DONCHIAN_EXIT_DAYS, help="Donchian exit channel")
    p.add_argument("--lookback", type=_positive_int("--lookback"), default=MOMENTUM_LOOKBACK, help="momentum lookback in bars")

    # Overrides. If omitted, values come from the market profile.
    p.add_argument("--discount", type=_discount, default=1.0, help="broker fee discount, e.g. 0.6")
    p.add_argument("--commission", type=_non_negative("--commission"), default=None, help="override commission rate")
    p.add_argument("--sell-tax", type=_non_negative("--sell-tax"), default=None, help="override sell tax rate")
    p.add_argument("--slippage", type=_non_negative("--slippage"), default=None, help="override one-way slippage")
    return p


def _validate(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    if args.strategy == "sma" and args.fast >= args.slow:
        parser.error(t("error_bad_windows", args.lang))
    if args.strategy == "donchian" and args.exit_days >= args.entry_days:
        parser.error(t("error_bad_donchian", args.lang))
    if args.symbol:
        try:
            start = date.fromisoformat(args.start)
            end = date.fromisoformat(args.end) if args.end else None
        except ValueError:
            parser.error(t("error_bad_date", args.lang))
        if end is not None and start >= end:
            parser.error(t("error_bad_range", args.lang))


def run(args: argparse.Namespace) -> int:
    market = load_market_file(args.market_file) if args.market_file else get_market(args.market)

    if args.csv:
        prices = get_source("csv").fetch(args.csv)
    else:
        symbol = _resolve_symbol(args.symbol, market)
        prices = get_source("yahoo").fetch(symbol, args.start, args.end)

    costs = CostModel(
        commission=market.commission if args.commission is None else args.commission,
        discount=args.discount,
        sell_tax=market.sell_tax if args.sell_tax is None else args.sell_tax,
        slippage=market.default_slippage if args.slippage is None else args.slippage,
    )

    position = build_position(
        args.strategy, prices["close"], fast=args.fast, slow=args.slow,
        entry_days=args.entry_days, exit_days=args.exit_days, lookback=args.lookback,
    )
    result = run_backtest(prices, position, costs)
    stats = summarize(result, prices, periods_per_year=market.trading_days_per_year)

    lang = args.lang
    print(f"{t('market', lang)}: {market.name} ({market.code}, {market.currency})")
    if args.strategy == "donchian":
        label = t('strategy_donchian', lang, entry=args.entry_days, exit=args.exit_days)
    elif args.strategy == "momentum":
        label = t('strategy_momentum', lang, lookback=args.lookback)
    else:
        label = t('strategy_sma', lang, fast=args.fast, slow=args.slow)
    print(f"{t('strategy', lang)}: {label}")
    print("-" * 52)
    for key in ROW_ORDER:
        label = t(key, lang)
        print(f"{label:<38} {_format_value(key, stats[key], lang):>12}")
    print("-" * 52)
    print(t("disclaimer", lang))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _validate(args, parser)
    try:
        return run(args)
    except ValueError as exc:  # user-facing errors raised by the library
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
