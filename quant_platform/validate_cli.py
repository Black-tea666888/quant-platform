"""Walk-forward validation from the command line.

Example:
    python -m quant_platform.validate_cli --csv prices.csv --fast 5,10,20 --slow 40,60,120 \
        --train-bars 750 --test-bars 250 --market TW
"""

from __future__ import annotations

import argparse
import math
import sys

from quant_platform.backtest import CostModel
from quant_platform.data_sources import get_source
from quant_platform.i18n import DEFAULT_LANG, SUPPORTED_LANGS, t
from quant_platform.markets import MARKETS, get_market
from quant_platform.validation import make_grid, walk_forward


def _ints(text: str) -> list[int]:
    try:
        values = [int(part) for part in text.split(",") if part.strip()]
    except ValueError as exc:
        raise argparse.ArgumentTypeError("use comma-separated whole numbers, e.g. 5,10,20") from exc
    if not values or any(v <= 0 for v in values):
        raise argparse.ArgumentTypeError("values must be positive whole numbers")
    return values


def _fmt(value: float) -> str:
    return "N/A" if isinstance(value, float) and math.isnan(value) else f"{value:.2f}"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Walk-forward validation for the SMA crossover strategy")
    p.add_argument("--lang", default=DEFAULT_LANG, choices=SUPPORTED_LANGS)
    p.add_argument("--csv", required=True, help="price CSV with date and close columns")
    p.add_argument("--market", default="TW", choices=sorted(MARKETS))
    p.add_argument("--fast", type=_ints, default=[5, 10, 20], help="fast windows to try, e.g. 5,10,20")
    p.add_argument("--slow", type=_ints, default=[40, 60, 120], help="slow windows to try, e.g. 40,60,120")
    p.add_argument("--train-bars", type=int, default=750, help="training bars per window")
    p.add_argument("--test-bars", type=int, default=250, help="test bars per window (rolled forward by this amount)")
    p.add_argument("--discount", type=float, default=1.0)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    lang = args.lang
    market = get_market(args.market)
    try:
        prices = get_source("csv").fetch(args.csv)
        costs = CostModel.from_market(market, discount=args.discount)
        combos = make_grid(args.fast, args.slow)
        if not combos:
            raise ValueError("no valid (fast, slow) pairs: every fast must be smaller than a slow")
        result = walk_forward(
            prices,
            combos,
            costs,
            periods_per_year=market.trading_days_per_year,
            train_bars=args.train_bars,
            test_bars=args.test_bars,
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(t("wf_title", lang))
    print("-" * 60)
    for n, w in enumerate(result.windows, start=1):
        print(
            t(
                "wf_window",
                lang,
                n=n,
                train_start=w.train_start.date(),
                train_end=w.train_end.date(),
                test_start=w.test_start.date(),
                test_end=w.test_end.date(),
                fast=w.fast,
                slow=w.slow,
                is_sharpe=_fmt(w.in_sample_sharpe),
                oos_sharpe=_fmt(w.out_of_sample_sharpe),
            )
        )
    print("-" * 60)
    s = result.oos_stats
    cagr = t("not_available", lang) if math.isnan(s["cagr"]) else f"{s['cagr']:.2%}"
    print(
        f"{t('wf_oos', lang)}: {t('total_return', lang)} {s['total_return']:.2%}, "
        f"{t('cagr', lang)} {cagr}, {t('max_drawdown', lang)} {s['max_drawdown']:.2%}, "
        f"{t('sharpe', lang)} {_fmt(s['sharpe'])}"
    )
    print("-" * 60)
    if result.warnings:
        print(t("wf_warnings", lang) + ":")
        for warning in result.warnings:
            print(f"  - {warning}")
    else:
        print(t("wf_no_warnings", lang))
    print(t("disclaimer", lang))
    return 0


if __name__ == "__main__":
    sys.exit(main())
