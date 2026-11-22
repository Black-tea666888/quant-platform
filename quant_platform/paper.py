"""Paper trading: a simulated account that places orders at the close, with no broker connection.

Each run processes only bars that are newer than the last one recorded, so it is safe to run daily.
Orders are sized to a target weight of account equity and rounded down to whole lots.
Timing matches the backtest: a position decided at a bar's close is executed at that close.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path

import pandas as pd

from quant_platform.backtest import CostModel


@dataclass
class PaperAccount:
    capital: float
    cash: float
    market: str | None = None   # market the account was opened in; a state file cannot switch markets
    shares: float = 0.0
    last_date: str | None = None
    target_weight: float = 0.0  # last target acted on; trades happen only when this changes
    orders: list[dict] = field(default_factory=list)
    equity_curve: list[dict] = field(default_factory=list)

    @classmethod
    def new(cls, capital: float) -> "PaperAccount":
        if capital <= 0:
            raise ValueError("capital must be positive")
        return cls(capital=capital, cash=capital)

    def equity(self, price: float) -> float:
        return self.cash + self.shares * price

    def rebalance(self, date: str, price: float, target_weight: float, costs: CostModel, lot_size: int = 1) -> dict | None:
        """Trade toward `target_weight` of equity at `price`. Returns the order, or None if no trade."""
        target_weight = min(max(target_weight, 0.0), 1.0)
        equity = self.equity(price)
        target_shares = math.floor(equity * target_weight / price / lot_size) * lot_size
        delta = target_shares - self.shares
        if delta == 0:
            return None

        if delta > 0:
            fill = price * (1 + costs.slippage)
            affordable = math.floor(self.cash / (fill * (1 + costs.commission * costs.discount)) / lot_size) * lot_size
            delta = min(delta, affordable)
            if delta <= 0:
                return None
            gross = delta * fill
            fee = gross * costs.commission * costs.discount
            tax = 0.0
            self.cash -= gross + fee
            self.shares += delta
            side = "BUY"
        else:
            sell = -delta
            fill = price * (1 - costs.slippage)
            gross = sell * fill
            fee = gross * costs.commission * costs.discount
            tax = gross * costs.sell_tax
            self.cash += gross - fee - tax
            self.shares -= sell
            side = "SELL"
            delta = -sell

        order = {
            "date": date,
            "side": side,
            "shares": delta,  # signed: positive for buys, negative for sells
            "price": round(fill, 6),
            "fee": round(fee, 6),
            "tax": round(tax, 6),
            "cash_after": round(self.cash, 6),
        }
        self.orders.append(order)
        return order

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "PaperAccount":
        return cls(**data)

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "PaperAccount":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def advance(
    account: PaperAccount,
    prices: pd.DataFrame,
    position: pd.Series,
    costs: CostModel,
    lot_size: int = 1,
) -> list[dict]:
    """Process every bar after `account.last_date`. `position` is aligned with `prices` by row."""
    if len(position) != len(prices):
        raise ValueError("position must have the same length as prices")

    new_orders: list[dict] = []
    for i, row in enumerate(prices.itertuples(index=False)):
        date = pd.Timestamp(row.date).date().isoformat()
        if account.last_date is not None and date <= account.last_date:
            continue
        price = float(row.close)
        target = float(position.iloc[i])
        # Act only when the signal changes, so daily equity drift does not cause constant tiny trades.
        if target != account.target_weight:
            order = account.rebalance(date, price, target, costs, lot_size)
            account.target_weight = target
            if order:
                new_orders.append(order)
        account.equity_curve.append({"date": date, "equity": round(account.equity(price), 6)})
        account.last_date = date
    return new_orders
