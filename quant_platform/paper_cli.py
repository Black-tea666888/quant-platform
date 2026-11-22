"""Daily paper-trading runner. Each run catches up on new bars and saves the account state.

Example:
    python -m quant_platform.paper_cli --csv prices.csv --state paper.json --capital 1000000
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from quant_platform.backtest import CostModel
from quant_platform.data_sources import get_source
from quant_platform.i18n import DEFAULT_LANG, SUPPORTED_LANGS, t
from quant_platform.markets import get_market, load_market_file
from quant_platform.paper import PaperAccount, advance
from quant_platform.strategy import DEFAULT_STRATEGY, DONCHIAN_ENTRY_DAYS, DONCHIAN_EXIT_DAYS, STRATEGIES, build_position


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Paper trade an SMA or Donchian strategy (no broker connection)")
    p.add_argument("--lang", default=DEFAULT_LANG, choices=SUPPORTED_LANGS)
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--csv", help="price CSV with date and close columns")
    src.add_argument("--symbol", help="Yahoo Finance symbol")
    p.add_argument("--start", default=None, help="start date YYYY-MM-DD (only with --symbol)")
    p.add_argument("--end", default=None, help="end date YYYY-MM-DD (only with --symbol)")
    p.add_argument("--state", required=True, help="JSON file that stores the account between runs")
    p.add_argument("--capital", type=float, default=None, help="starting capital (only when creating a new state)")
    mkt = p.add_mutually_exclusive_group()
    mkt.add_argument("--market", default="TW")
    mkt.add_argument("--market-file")
    p.add_argument("--strategy", default=DEFAULT_STRATEGY, choices=STRATEGIES, help="sma or donchian")
    p.add_argument("--fast", type=int, default=20)
    p.add_argument("--slow", type=int, default=60)
    p.add_argument("--entry-days", type=int, default=DONCHIAN_ENTRY_DAYS)
    p.add_argument("--exit-days", type=int, default=DONCHIAN_EXIT_DAYS)
    p.add_argument("--lot-size", type=int, default=None, help="shares per lot (defaults to 1000 for TW, 1 otherwise)")
    p.add_argument("--discount", type=float, default=1.0)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    lang = args.lang
    try:
        market = load_market_file(args.market_file) if args.market_file else get_market(args.market)
        if args.strategy == "sma" and args.fast >= args.slow:
            raise ValueError(t("error_bad_windows", lang))
        if args.strategy == "donchian" and args.exit_days >= args.entry_days:
            raise ValueError(t("error_bad_donchian", lang))

        state_path = Path(args.state)
        if state_path.exists():
            account = PaperAccount.load(state_path)
            if account.market and account.market != market.code:
                raise ValueError(
                    f"state file was opened in market {account.market}, not {market.code}; use a different --state file"
                )
        else:
            if args.capital is None:
                raise ValueError("--capital is required when creating a new state file")
            account = PaperAccount.new(args.capital)
            account.market = market.code

        if args.csv:
            prices = get_source("csv").fetch(args.csv)
        else:
            prices = get_source("yahoo").fetch(args.symbol, args.start, args.end)

        costs = CostModel.from_market(market, discount=args.discount)
        lot_size = args.lot_size if args.lot_size is not None else (1000 if market.code == "TW" else 1)
        position = build_position(
            args.strategy, prices["close"], fast=args.fast, slow=args.slow, entry_days=args.entry_days, exit_days=args.exit_days
        )

        orders = advance(account, prices, position, costs, lot_size=lot_size)
        account.save(state_path)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    last = account.equity_curve[-1] if account.equity_curve else None
    print(f"Market: {market.name} ({market.code}, {market.currency})")
    print(f"New orders this run: {len(orders)}")
    for o in orders:
        print(f"  {o['date']}  {o['side']:<4}  {o['shares']:>10,.0f} @ {o['price']:,.4f}  fee {o['fee']:,.2f}  tax {o['tax']:,.2f}")
    if last:
        print(f"Last bar: {last['date']}  equity {last['equity']:,.2f}  cash {account.cash:,.2f}  shares {account.shares:,.0f}")
    print(t("disclaimer", lang))
    return 0


if __name__ == "__main__":
    sys.exit(main())
