"""Paper-trading bot: runs your own rule-based strategies on a schedule, in simulation only.

Safety boundaries (enforced in code):
- mode must be "paper". Any other value is rejected. There is no live-order path.
- No broker connection, no real orders, and no recommendations to other people.
- Each strategy lives in its own state file, so runs are incremental and idempotent.

Example config (bot.json):
    {
      "mode": "paper",
      "market": "TW",
      "capital": 1000000,
      "lot_size": 1000,
      "strategies": [
        {"name": "tsmc", "csv": "data/2330.csv", "fast": 20, "slow": 60, "stop_loss": 0.08}
      ]
    }

Run daily (for example from cron or launchd):
    python -m quant_platform.bot --config bot.json --state-dir state --log bot.log
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from quant_platform.backtest import CostModel
from quant_platform.data_sources import get_source
from quant_platform.markets import get_market
from quant_platform.paper import PaperAccount, advance
from quant_platform.risk import RiskRules, apply_risk_overlay
from quant_platform.strategy import sma_crossover

ALLOWED_MODE = "paper"
TOP_LEVEL_KEYS = {"mode", "market", "capital", "discount", "lot_size", "strategies"}
STRATEGY_KEYS = {"name", "csv", "fast", "slow", "stop_loss", "daily_loss_limit", "max_drawdown_halt"}
_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class BotConfigError(ValueError):
    pass


@dataclass(frozen=True)
class StrategyConfig:
    name: str
    csv: str
    fast: int
    slow: int
    rules: RiskRules


@dataclass(frozen=True)
class BotConfig:
    market: str
    capital: float
    discount: float
    lot_size: int
    strategies: list[StrategyConfig]


def load_config(path: str | Path) -> BotConfig:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BotConfigError(f"cannot read config: {exc}") from exc
    return parse_config(raw)


def parse_config(raw: dict) -> BotConfig:
    if not isinstance(raw, dict):
        raise BotConfigError("config must be a JSON object")
    unknown = set(raw) - TOP_LEVEL_KEYS
    if unknown:
        raise BotConfigError(f"unknown top-level keys: {sorted(unknown)}")
    if raw.get("mode") != ALLOWED_MODE:
        raise BotConfigError('mode must be "paper". This bot does not place live orders.')

    market = str(raw.get("market", "TW")).upper()
    get_market(market)  # raises ValueError if unknown
    capital = float(raw.get("capital", 0))
    if capital <= 0:
        raise BotConfigError("capital must be positive")
    discount = float(raw.get("discount", 1.0))
    if not 0 < discount <= 1:
        raise BotConfigError("discount must be in (0, 1]")
    lot_size = int(raw.get("lot_size", 1))
    if lot_size <= 0:
        raise BotConfigError("lot_size must be a positive integer")

    strategies_raw = raw.get("strategies")
    if not isinstance(strategies_raw, list) or not strategies_raw:
        raise BotConfigError("strategies must be a non-empty list")

    strategies: list[StrategyConfig] = []
    seen: set[str] = set()
    for item in strategies_raw:
        if not isinstance(item, dict):
            raise BotConfigError("each strategy must be an object")
        unknown = set(item) - STRATEGY_KEYS
        if unknown:
            raise BotConfigError(f"unknown strategy keys: {sorted(unknown)}")
        name = str(item.get("name", ""))
        if not _NAME_RE.fullmatch(name):
            raise BotConfigError("strategy names may use letters, digits, '-' and '_' only")
        if name in seen:
            raise BotConfigError(f"duplicate strategy name: {name}")
        seen.add(name)
        fast, slow = int(item.get("fast", 20)), int(item.get("slow", 60))
        if not 0 < fast < slow:
            raise BotConfigError(f"{name}: need 0 < fast < slow")
        csv = str(item.get("csv", ""))
        if not csv:
            raise BotConfigError(f"{name}: csv is required")
        rules = RiskRules(
            stop_loss=item.get("stop_loss"),
            daily_loss_limit=item.get("daily_loss_limit"),
            max_drawdown_halt=item.get("max_drawdown_halt"),
        )
        strategies.append(StrategyConfig(name=name, csv=csv, fast=fast, slow=slow, rules=rules))

    return BotConfig(market=market, capital=capital, discount=discount, lot_size=lot_size, strategies=strategies)


def run_once(config: BotConfig, state_dir: str | Path, log_path: str | Path | None = None) -> list[dict]:
    """Run every strategy once. Each one only processes bars newer than its saved state."""
    state_dir = Path(state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    market = get_market(config.market)
    costs = CostModel.from_market(market, discount=config.discount)
    per_strategy_capital = config.capital / len(config.strategies)
    summaries: list[dict] = []

    for strategy in config.strategies:
        state_path = state_dir / f"{strategy.name}.json"
        if state_path.exists():
            account = PaperAccount.load(state_path)
            if account.market and account.market != market.code:
                raise BotConfigError(f"{strategy.name}: state was opened in market {account.market}")
        else:
            account = PaperAccount.new(per_strategy_capital)
            account.market = market.code

        prices = get_source("csv").fetch(strategy.csv)
        raw_position = sma_crossover(prices["close"], fast=strategy.fast, slow=strategy.slow)
        position = apply_risk_overlay(prices["close"], raw_position, strategy.rules)
        orders = advance(account, prices, position, costs, lot_size=config.lot_size)
        account.save(state_path)

        last = account.equity_curve[-1] if account.equity_curve else None
        summaries.append(
            {
                "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "strategy": strategy.name,
                "new_orders": len(orders),
                "last_bar": last["date"] if last else None,
                "equity": last["equity"] if last else account.cash,
                "shares": account.shares,
                "cash": round(account.cash, 2),
            }
        )

    if log_path is not None:
        with Path(log_path).open("a", encoding="utf-8") as handle:
            for summary in summaries:
                handle.write(json.dumps(summary, ensure_ascii=False) + "\n")
    return summaries


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Paper-trading bot (simulation only, no live orders)")
    p.add_argument("--config", required=True)
    p.add_argument("--state-dir", required=True)
    p.add_argument("--log", default=None, help="append one JSON line per strategy per run")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = load_config(args.config)
        summaries = run_once(config, args.state_dir, args.log)
    except (BotConfigError, ValueError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    for s in summaries:
        print(f"{s['strategy']}: {s['new_orders']} new order(s), last bar {s['last_bar']}, equity {s['equity']:,.2f}")
    print("Paper trading only. No real orders were placed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
