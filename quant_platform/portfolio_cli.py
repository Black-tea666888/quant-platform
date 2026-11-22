"""Multi-asset portfolio backtest from the command line.

Examples:
    # Equal weight, monthly rebalance
    python -m quant_platform.portfolio_cli --csv A=a.csv --csv B=b.csv --freq monthly

    # SMA signals per symbol, weekly rebalance
    python -m quant_platform.portfolio_cli --csv A=a.csv --csv B=b.csv --mode signal --fast 20 --slow 60 --freq weekly
"""

from __future__ import annotations

import argparse
import math
import sys

import pandas as pd

from quant_platform.backtest import CostModel
from quant_platform.data_sources import get_source
from quant_platform.i18n import DEFAULT_LANG, SUPPORTED_LANGS, t
from quant_platform.markets import MARKETS, get_market
from quant_platform.portfolio import FREQ_CODES, align_prices, run_portfolio, signal_weights
from quant_platform.risk import cap_weights
from quant_platform.validation import stats_from_returns


def _parse_csv_args(items: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for item in items:
        if "=" not in item:
            raise argparse.ArgumentTypeError(f"expected SYMBOL=path.csv, got {item!r}")
        symbol, path = item.split("=", 1)
        if not symbol or not path:
            raise argparse.ArgumentTypeError(f"expected SYMBOL=path.csv, got {item!r}")
        out[symbol] = path
    return out


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Multi-asset portfolio backtest with rebalancing")
    p.add_argument("--lang", default=DEFAULT_LANG, choices=SUPPORTED_LANGS)
    p.add_argument("--csv", action="append", required=True, type=str, help="SYMBOL=path.csv, repeat for each asset")
    p.add_argument("--market", default="TW", choices=sorted(MARKETS))
    p.add_argument("--freq", default="monthly", choices=sorted(FREQ_CODES))
    p.add_argument("--mode", default="equal", choices=["equal", "signal"])
    p.add_argument("--fast", type=int, default=20)
    p.add_argument("--slow", type=int, default=60)
    p.add_argument("--discount", type=float, default=1.0)
    p.add_argument("--max-weight", type=float, default=None, help="cap each symbol's weight, e.g. 0.25; excess becomes cash")
    return p


def _fmt_pct(value: float) -> str:
    return "N/A" if isinstance(value, float) and math.isnan(value) else f"{value:.2%}"


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    lang = args.lang
    try:
        sources = _parse_csv_args(args.csv)
    except argparse.ArgumentTypeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    try:
        market = get_market(args.market)
        frames = {symbol: get_source("csv").fetch(path) for symbol, path in sources.items()}
        wide = align_prices(frames)
        costs = CostModel.from_market(market, discount=args.discount)
        periods = market.trading_days_per_year

        if args.mode == "signal":
            if args.fast >= args.slow:
                raise ValueError(t("error_bad_windows", lang))
            weights = signal_weights(wide, fast=args.fast, slow=args.slow)
            mode_label = t("pf_mode_signal", lang)
        else:
            weights = pd.DataFrame(1.0 / len(wide.columns), index=wide.index, columns=wide.columns)
            mode_label = t("pf_mode_equal", lang)
        if args.max_weight is not None:
            weights = cap_weights(weights, args.max_weight)

        result = run_portfolio(wide, weights, costs, freq=args.freq, periods_per_year=periods)
        bench = run_portfolio(wide, None, costs, freq="never", periods_per_year=periods)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    stats = stats_from_returns(result.net_returns.iloc[1:], periods)
    bench_stats = stats_from_returns(bench.net_returns.iloc[1:], periods)

    print(t("pf_title", lang, freq=args.freq, mode=mode_label))
    print(f"{t('market', lang)}: {market.name} ({market.code}, {market.currency})   symbols: {', '.join(wide.columns)}")
    print("-" * 60)
    rows = [
        (t("total_return", lang), _fmt_pct(stats["total_return"]), _fmt_pct(bench_stats["total_return"])),
        (t("cagr", lang), _fmt_pct(stats["cagr"]), _fmt_pct(bench_stats["cagr"])),
        (t("max_drawdown", lang), _fmt_pct(stats["max_drawdown"]), _fmt_pct(bench_stats["max_drawdown"])),
        (t("sharpe", lang), "N/A" if math.isnan(stats["sharpe"]) else f"{stats['sharpe']:.4f}",
         "N/A" if math.isnan(bench_stats["sharpe"]) else f"{bench_stats['sharpe']:.4f}"),
    ]
    print(f"{'':<38} {'Portfolio':>12} {'Benchmark':>12}")
    for label, a, b in rows:
        print(f"{label:<38} {a:>12} {b:>12}")
    print("-" * 60)
    print(f"{t('pf_rebalances', lang)}: {result.rebalances}   {t('pf_orders', lang)}: {result.trades}")
    print(f"{t('pf_turnover', lang)}: {result.turnover_per_year:.2f}x   {t('pf_costs', lang)}: {_fmt_pct(result.total_costs)}")
    print(f"{t('pf_bench', lang)}")
    print(t("disclaimer", lang))
    return 0


if __name__ == "__main__":
    sys.exit(main())
