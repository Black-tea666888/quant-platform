"""Backtest engine with Taiwan-style trading costs.

Timing assumption: a target position decided at bar t's close is held from bar t's close,
so the return earned on bar t+1 is the first one that counts. This avoids look-ahead bias.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from quant_platform.quant_math import calmar_ratio, sortino_ratio

TRADING_DAYS = 252


@dataclass(frozen=True)
class CostModel:
    """Costs as fractions of traded value. Defaults approximate Taiwan stocks."""

    commission: float = 0.001425  # brokerage fee rate per side (0.1425%)
    discount: float = 1.0         # broker discount, e.g. 0.6 for a 6-折 deal
    sell_tax: float = 0.003       # securities transaction tax on sells (0.3% for stocks, ETFs differ)
    slippage: float = 0.0005      # assumed one-way slippage

    @property
    def buy_rate(self) -> float:
        return self.commission * self.discount + self.slippage

    @property
    def sell_rate(self) -> float:
        return self.commission * self.discount + self.sell_tax + self.slippage

    @classmethod
    def from_market(cls, market, discount: float = 1.0, slippage: float | None = None) -> "CostModel":
        """Build costs from a Market profile (see quant_platform.markets)."""
        return cls(
            commission=market.commission,
            discount=discount,
            sell_tax=market.sell_tax,
            slippage=market.default_slippage if slippage is None else slippage,
        )


@dataclass
class Trade:
    entry_date: pd.Timestamp
    exit_date: pd.Timestamp | None
    return_: float  # net compounded return over the holding period


@dataclass
class BacktestResult:
    equity: pd.Series
    net_returns: pd.Series
    position: pd.Series
    trades: list[Trade] = field(default_factory=list)


def run_backtest(prices: pd.DataFrame, position: pd.Series, costs: CostModel | None = None) -> BacktestResult:
    """Run a long-only backtest.

    prices:   DataFrame with `date` and `close`.
    position: target position per bar (0..1), decided at that bar's close.
    """
    costs = costs or CostModel()
    close = prices["close"].astype(float).reset_index(drop=True)
    dates = pd.Series(prices["date"]).reset_index(drop=True)
    target = pd.Series(position, dtype=float).reset_index(drop=True).clip(0.0, 1.0)

    held = target.shift(1).fillna(0.0)          # position actually held during each bar
    bar_return = close.pct_change().fillna(0.0)  # market return earned by holding during the bar

    change = held.diff().fillna(held.iloc[0])
    cost = change.clip(lower=0) * costs.buy_rate + (-change).clip(lower=0) * costs.sell_rate

    net = held * bar_return - cost
    equity = (1.0 + net).cumprod()

    trades = _extract_trades(dates, held, net)
    return BacktestResult(
        equity=pd.Series(equity.values, index=dates.values, name="equity"),
        net_returns=pd.Series(net.values, index=dates.values, name="net_return"),
        position=pd.Series(held.values, index=dates.values, name="position"),
        trades=trades,
    )


def _extract_trades(dates: pd.Series, held: pd.Series, net: pd.Series) -> list[Trade]:
    trades: list[Trade] = []
    in_trade = False
    entry_idx = 0
    growth = 1.0
    for i in range(len(held)):
        if not in_trade and held.iloc[i] > 0:
            in_trade, entry_idx, growth = True, i, 1.0
        if in_trade:
            growth *= 1.0 + net.iloc[i]
            if held.iloc[i] == 0:
                trades.append(Trade(dates.iloc[entry_idx], dates.iloc[i], growth - 1.0))
                in_trade = False
    if in_trade:  # still open at the end of the data
        trades.append(Trade(dates.iloc[entry_idx], None, growth - 1.0))
    return trades


def summarize(result: BacktestResult, prices: pd.DataFrame, periods_per_year: int = TRADING_DAYS) -> dict:
    """Key statistics for a backtest, plus buy-and-hold for comparison (gross of costs)."""
    eq = result.equity
    rets = result.net_returns.iloc[1:]  # first bar has no real return
    n = len(rets)
    total_return = float(eq.iloc[-1] - 1.0)
    years = n / periods_per_year if n else 0.0
    cagr = float(eq.iloc[-1] ** (1 / years) - 1) if years > 0 and eq.iloc[-1] > 0 else float("nan")
    drawdown = eq / eq.cummax() - 1.0
    std = rets.std()
    sharpe = float(rets.mean() / std * np.sqrt(periods_per_year)) if std and std > 0 else float("nan")
    closed = [t for t in result.trades if t.exit_date is not None]
    wins = [t for t in closed if t.return_ > 0]
    close = prices["close"].astype(float)
    buy_hold = float(close.iloc[-1] / close.iloc[0] - 1.0)
    return {
        "start_date": str(result.equity.index[0].date()),
        "end_date": str(result.equity.index[-1].date()),
        "total_return": total_return,
        "cagr": cagr,
        "max_drawdown": float(drawdown.min()),
        "sharpe": sharpe,
        "sortino": sortino_ratio(rets, periods_per_year),
        "calmar": calmar_ratio(cagr, float(drawdown.min())),
        "exposure": float(result.position.mean()),
        "trades": len(closed),
        "win_rate": len(wins) / len(closed) if closed else float("nan"),
        "buy_hold": buy_hold,
    }
