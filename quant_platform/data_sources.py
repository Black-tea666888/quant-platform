"""Pluggable price sources. Each source returns a DataFrame with `date` and `close` columns.

To support a new data provider, subclass PriceSource and register it in SOURCES.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd

from quant_platform.data import fetch_yahoo, load_csv


class PriceSource(ABC):
    name: str

    @abstractmethod
    def fetch(self, symbol: str, start: str | None = None, end: str | None = None) -> pd.DataFrame:
        """Return daily prices for `symbol` between `start` and `end` (inclusive of start, exclusive of end)."""


class CsvSource(PriceSource):
    """Reads a local CSV file. `symbol` is the file path; dates are filtered if given."""

    name = "csv"

    def fetch(self, symbol: str, start: str | None = None, end: str | None = None) -> pd.DataFrame:
        df = load_csv(symbol)
        return _filter_dates(df, start, end)


class YahooSource(PriceSource):
    """Downloads adjusted daily prices from Yahoo Finance (free, unofficial, no SLA)."""

    name = "yahoo"

    def fetch(self, symbol: str, start: str | None = None, end: str | None = None) -> pd.DataFrame:
        return fetch_yahoo(symbol, start or "2015-01-01", end)


def _filter_dates(df: pd.DataFrame, start: str | None, end: str | None) -> pd.DataFrame:
    out = df
    if start:
        out = out[out["date"] >= pd.Timestamp(start)]
    if end:
        out = out[out["date"] < pd.Timestamp(end)]
    return out.reset_index(drop=True)


SOURCES: dict[str, PriceSource] = {source.name: source for source in (CsvSource(), YahooSource())}


def get_source(name: str) -> PriceSource:
    try:
        return SOURCES[name]
    except KeyError as exc:
        raise ValueError(f"Unknown data source {name!r}. Known sources: {', '.join(sorted(SOURCES))}") from exc
