"""Pluggable price sources. Each source returns a DataFrame with `date` and `close` columns.

To support a new data provider, subclass PriceSource and register it in SOURCES.
"""

from __future__ import annotations

import json
import time
import urllib.request
from abc import ABC, abstractmethod
from datetime import date

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


TWSE_MONTH_URL = "https://www.twse.com.tw/exchangeReport/STOCK_DAY?response=json&date={yyyymm}01&stockNo={code}"
TWSE_REQUEST_DELAY_SECONDS = 0.5


class TwseSource(PriceSource):
    """Daily closes from the Taiwan Stock Exchange monthly report (official, free, no key).

    Caveat: TWSE prices are NOT adjusted for dividends or splits, so they can show gaps
    on ex-dividend days. Yahoo prices are adjusted. Do not compare the two directly.
    """

    name = "twse"

    def fetch(self, symbol: str, start: str | None = None, end: str | None = None) -> pd.DataFrame:
        code = symbol.upper().removesuffix(".TW").removesuffix(".TWO")
        first = pd.Timestamp(start) if start else pd.Timestamp("2015-01-01")
        last = pd.Timestamp(end) - pd.Timedelta(days=1) if end else pd.Timestamp(date.today())
        frames = []
        months = pd.period_range(first.to_period("M"), last.to_period("M"), freq="M")
        for i, month in enumerate(months):
            if i:
                time.sleep(TWSE_REQUEST_DELAY_SECONDS)
            frames.append(parse_twse_month(fetch_twse_month(code, month.strftime("%Y%m"))))
        if not frames:
            raise ValueError(f"No TWSE data for {symbol!r}")
        df = pd.concat(frames, ignore_index=True)
        if df.empty:
            raise ValueError(f"No TWSE data for {symbol!r}")
        return _filter_dates(df, start, end)


def fetch_twse_month(code: str, yyyymm: str) -> dict:
    url = TWSE_MONTH_URL.format(yyyymm=yyyymm, code=code)
    with urllib.request.urlopen(url, timeout=30) as response:  # noqa: S310 - fixed official host
        return json.loads(response.read().decode("utf-8"))


def parse_twse_month(payload: dict) -> pd.DataFrame:
    """Turn one TWSE monthly payload into a DataFrame with `date` and `close`. Raises ValueError on errors."""
    if payload.get("stat") != "OK":
        raise ValueError(f"TWSE error: {payload.get('stat', 'unknown response')}")
    rows = []
    for row in payload.get("data", []):
        roc_date, close_text = row[0], row[6]
        close_text = close_text.replace(",", "")
        if close_text in ("", "--"):
            continue  # no trade that day
        year, month, day = (int(part) for part in roc_date.split("/"))
        rows.append({"date": pd.Timestamp(year + 1911, month, day), "close": float(close_text)})
    return pd.DataFrame(rows, columns=["date", "close"])


def _filter_dates(df: pd.DataFrame, start: str | None, end: str | None) -> pd.DataFrame:
    out = df
    if start:
        out = out[out["date"] >= pd.Timestamp(start)]
    if end:
        out = out[out["date"] < pd.Timestamp(end)]
    return out.reset_index(drop=True)


SOURCES: dict[str, PriceSource] = {source.name: source for source in (CsvSource(), YahooSource(), TwseSource())}


def get_source(name: str) -> PriceSource:
    try:
        return SOURCES[name]
    except KeyError as exc:
        raise ValueError(f"Unknown data source {name!r}. Known sources: {', '.join(sorted(SOURCES))}") from exc
