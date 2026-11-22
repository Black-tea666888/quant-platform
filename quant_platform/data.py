"""Price data loading: local CSV files or Yahoo Finance (free)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from quant_platform.i18n import t

REQUIRED_COLUMNS = ("date", "close")


def load_csv(path: str) -> pd.DataFrame:
    """Load prices from a CSV with at least `date` and `close` columns."""
    if not Path(path).is_file():
        raise ValueError(t("error_file_not_found", path=path))
    df = pd.read_csv(path)
    return _clean(df)


def fetch_yahoo(symbol: str, start: str, end: str | None = None) -> pd.DataFrame:
    """Download daily prices from Yahoo Finance. Taiwan stocks use the `.TW` suffix, e.g. `2330.TW`."""
    import yfinance as yf  # imported lazily so CSV-only use does not need it

    raw = yf.download(symbol, start=start, end=end, auto_adjust=True, progress=False)
    if raw.empty:
        raise ValueError(t("error_no_data", symbol=symbol))
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    df = raw.reset_index().rename(columns=str.lower)
    return _clean(df)


def clean_prices(df: pd.DataFrame) -> pd.DataFrame:
    """Validate and normalize a raw price table to `date` and `close` columns."""
    return _clean(df)


def _clean(df: pd.DataFrame) -> pd.DataFrame:
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(t("error_missing_columns", missing=missing))
    out = df.loc[:, list(REQUIRED_COLUMNS)].copy()
    out["date"] = pd.to_datetime(out["date"])
    out = out.dropna(subset=["close"]).sort_values("date").reset_index(drop=True)
    if out.empty:
        raise ValueError(t("error_no_rows"))
    return out
