"""Multi-asset portfolio backtest with periodic rebalancing and trading costs.

Rules:
- Only long positions. Unallocated weight stays in cash, which earns 0.
- Weights are decided at a bar's close and executed at that same close (matches the single-asset engine).
- Between rebalances, holdings drift with prices. Rebalance dates come from `freq`.
- Fractional shares are allowed. Use a lot size in live trading.
- Only dates where every symbol has a price are used (inner join), so no price is invented.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from quant_platform.backtest import CostModel
from quant_platform.strategy import sma_crossover

FREQ_CODES = {"daily": None, "weekly": "W", "monthly": "M", "quarterly": "Q", "never": "never"}


def align_prices(price_frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Return a wide table of closes indexed by date, keeping only dates present for every symbol."""
    if not price_frames:
        raise ValueError("at least one symbol is required")
    wide = None
    for symbol, df in price_frames.items():
        series = df.set_index("date")["close"].astype(float).rename(symbol)
        series = series[~series.index.duplicated(keep="last")]
        wide = series.to_frame() if wide is None else wide.join(series, how="inner")
    wide = wide.sort_index().dropna()
    if wide.empty:
        raise ValueError("no dates shared by all symbols")
    return wide


def rebalance_flags(dates: pd.DatetimeIndex, freq: str) -> np.ndarray:
    """True on the bar where a rebalance happens. The first bar always rebalances."""
    if freq not in FREQ_CODES:
        raise ValueError(f"freq must be one of: {', '.join(FREQ_CODES)}")
    flags = np.zeros(len(dates), dtype=bool)
    flags[0] = True
    code = FREQ_CODES[freq]
    if code is None:
        flags[:] = True
    elif code != "never":
        periods = pd.Series(dates.to_period(code))
        flags = np.array(periods != periods.shift(-1), dtype=bool)  # last bar of each period
        flags[0] = True
    return flags


def signal_weights(wide: pd.DataFrame, fast: int, slow: int) -> pd.DataFrame:
    """Per-symbol SMA signals. Each active symbol gets an equal share of the portfolio. The rest is cash."""
    signals = pd.DataFrame(
        {symbol: sma_crossover(wide[symbol], fast=fast, slow=slow).values for symbol in wide.columns},
        index=wide.index,
    )
    active = signals.sum(axis=1)
    weights = signals.div(active.where(active > 0, np.nan), axis=0).fillna(0.0)
    return weights


@dataclass
class PortfolioResult:
    equity: pd.Series
    net_returns: pd.Series
    weights: pd.DataFrame
    total_costs: float
    rebalances: int
    trades: int
    turnover_per_year: float
    log: list[dict] = field(default_factory=list)


def run_portfolio(
    wide: pd.DataFrame,
    target_weights: pd.DataFrame | dict[str, float] | None,
    costs: CostModel,
    freq: str = "monthly",
    periods_per_year: int = 252,
) -> PortfolioResult:
    """Backtest target weights over a wide close table.

    target_weights:
      - None: equal weight across all symbols.
      - dict: fixed weights (must sum to <= 1). The remainder is cash.
      - DataFrame: time-varying weights aligned to wide.index (for example from signal_weights).
    """
    symbols = list(wide.columns)
    dates = wide.index
    n = len(dates)

    if target_weights is None:
        base = pd.DataFrame(1.0 / len(symbols), index=dates, columns=symbols)
    elif isinstance(target_weights, dict):
        missing = set(symbols) - set(target_weights)
        if missing:
            raise ValueError(f"missing weights for: {sorted(missing)}")
        total = sum(target_weights[s] for s in symbols)
        if total > 1 + 1e-9 or any(target_weights[s] < 0 for s in symbols):
            raise ValueError("weights must be non-negative and sum to at most 1")
        base = pd.DataFrame([[target_weights[s] for s in symbols]] * n, index=dates, columns=symbols)
    else:
        base = target_weights.reindex(index=dates, columns=symbols).fillna(0.0)

    flags = rebalance_flags(dates, freq)
    prices = wide.to_numpy()
    targets = base.to_numpy()

    cash = 1.0
    shares = np.zeros(len(symbols))
    equity_values = np.empty(n)
    held_weights = np.zeros((n, len(symbols)))
    total_costs = 0.0
    traded_notional = 0.0
    rebalances = 0
    trades = 0
    log: list[dict] = []

    for i in range(n):
        price = prices[i]
        if flags[i]:
            value = cash + float(shares @ price)
            target_value = targets[i] * value
            current_value = shares * price
            for j, symbol in enumerate(symbols):
                delta_value = target_value[j] - current_value[j]
                if abs(delta_value) < 1e-12:
                    continue
                if delta_value > 0:
                    cost = delta_value * costs.buy_rate
                    cash -= delta_value + cost
                    shares[j] += delta_value / price[j]
                    side = "BUY"
                else:
                    sell_value = -delta_value
                    cost = sell_value * costs.sell_rate
                    cash += sell_value - cost
                    shares[j] -= sell_value / price[j]
                    side = "SELL"
                total_costs += cost
                traded_notional += abs(delta_value)
                trades += 1
                log.append({"date": dates[i].date().isoformat(), "symbol": symbol, "side": side, "value": round(abs(delta_value), 6), "cost": round(cost, 6)})
            rebalances += 1
        equity_values[i] = cash + float(shares @ price)
        total_value = equity_values[i]
        held_weights[i] = (shares * price) / total_value if total_value > 0 else 0.0

    equity = pd.Series(equity_values, index=dates, name="equity")
    net_returns = equity.pct_change().fillna(0.0)
    years = n / periods_per_year if n else 0.0
    avg_equity = float(np.mean(equity_values)) if n else 0.0
    turnover = (traded_notional / avg_equity / years) if years > 0 and avg_equity > 0 else 0.0

    return PortfolioResult(
        equity=equity,
        net_returns=net_returns,
        weights=pd.DataFrame(held_weights, index=dates, columns=symbols),
        total_costs=total_costs,
        rebalances=rebalances,
        trades=trades,
        turnover_per_year=turnover,
        log=log,
    )
