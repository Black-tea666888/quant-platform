"""Risk overlay for a single-asset strategy and position caps for portfolios.

Single asset (apply_risk_overlay), decisions made at each bar's close:
- Stop loss: exit when the close falls this far below the entry price.
- Daily loss limit: exit when the held position loses more than this in one bar.
- Max drawdown halt: exit when strategy equity falls this far below its peak, and stay flat.
- After any exit, the strategy stays flat until its own signal turns off and back on. This avoids
  re-entering the same move immediately.

Timing matches the backtest engine: a position decided at a bar's close is held from the next bar.
Risk checks use gross returns (no costs), so they react to price, not to fees.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class RiskRules:
    stop_loss: float | None = None         # e.g. 0.08 = exit 8% below entry
    daily_loss_limit: float | None = None  # e.g. 0.03 = exit after a 3% loss in one bar
    max_drawdown_halt: float | None = None # e.g. 0.20 = halt after a 20% drawdown from peak

    def __post_init__(self) -> None:
        for name in ("stop_loss", "daily_loss_limit", "max_drawdown_halt"):
            value = getattr(self, name)
            if value is not None and not (0 < value < 1):
                raise ValueError(f"{name} must be between 0 and 1 (exclusive), got {value}")

    @property
    def is_active(self) -> bool:
        return any(v is not None for v in (self.stop_loss, self.daily_loss_limit, self.max_drawdown_halt))


def apply_risk_overlay(close: pd.Series, target: pd.Series, rules: RiskRules) -> pd.Series:
    """Return the risk-adjusted target position (0 or 1) per bar."""
    close = close.astype(float).reset_index(drop=True)
    target = pd.Series(target, dtype=float).reset_index(drop=True).clip(0.0, 1.0)
    if not rules.is_active:
        return target.copy()

    n = len(close)
    out = np.zeros(n)
    held_prev = 0.0      # position held during the current bar (decided at the previous close)
    entry_price = np.nan
    equity = 1.0
    peak = 1.0
    halted = False       # set after an exit; cleared when the raw signal goes flat

    for i in range(n):
        if i == 0:
            bar_return = 0.0
        else:
            bar_return = close.iloc[i] / close.iloc[i - 1] - 1.0
        equity *= 1.0 + held_prev * bar_return
        peak = max(peak, equity)
        raw = target.iloc[i]

        exit_now = False
        if held_prev > 0:
            if rules.daily_loss_limit is not None and held_prev * bar_return <= -rules.daily_loss_limit:
                exit_now = True
            if rules.stop_loss is not None and close.iloc[i] <= entry_price * (1.0 - rules.stop_loss):
                exit_now = True
        if rules.max_drawdown_halt is not None and equity / peak - 1.0 <= -rules.max_drawdown_halt:
            exit_now = True
            halted = True

        if exit_now:
            out[i] = 0.0
            halted = True
        elif halted:
            out[i] = 0.0
            if raw <= 0:
                halted = False  # the signal has turned off; a later signal may enter again
        else:
            out[i] = raw

        if out[i] > 0 and held_prev <= 0:
            entry_price = close.iloc[i]
        held_prev = out[i]

    return pd.Series(out, name="position")


def cap_weights(weights: pd.DataFrame, max_weight: float) -> pd.DataFrame:
    """Clip each symbol's weight at `max_weight`. Excess weight becomes cash rather than being redistributed."""
    if not 0 < max_weight <= 1:
        raise ValueError("max_weight must be in (0, 1]")
    return weights.clip(lower=0.0, upper=max_weight)
