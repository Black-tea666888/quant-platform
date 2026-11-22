"""Streamlit dashboard for the SMA crossover backtest.

Run locally:
    pip install -r requirements-ui.txt
    streamlit run app.py
"""

from __future__ import annotations

import io

import pandas as pd
import streamlit as st

from quant_platform.backtest import CostModel, run_backtest, summarize
from quant_platform.data import clean_prices
from quant_platform.i18n import DEFAULT_LANG, SUPPORTED_LANGS, t
from quant_platform.markets import MARKETS, get_market
from quant_platform.strategy import sma_crossover

PERCENT_KEYS = {"total_return", "cagr", "max_drawdown", "exposure", "win_rate", "buy_hold"}


def _read_upload(uploaded) -> pd.DataFrame:
    return clean_prices(pd.read_csv(io.BytesIO(uploaded.getvalue())))


def _format(key: str, value: object, lang: str) -> str:
    if isinstance(value, float):
        if value != value:  # NaN
            return t("not_available", lang)
        return f"{value:.2%}" if key in PERCENT_KEYS else f"{value:.4f}"
    return str(value)


def main() -> None:
    st.set_page_config(page_title="quant-platform", layout="wide")

    with st.sidebar:
        langs = list(SUPPORTED_LANGS)
        lang = st.selectbox(t("ui_language", DEFAULT_LANG), langs, index=langs.index(DEFAULT_LANG))
        market_codes = sorted(MARKETS)
        market_code = st.selectbox(t("market", lang), market_codes, index=market_codes.index("TW"))
        uploaded = st.file_uploader(t("ui_csv_label", lang), type="csv")
        fast = st.number_input(t("ui_fast", lang), min_value=1, value=20, step=1)
        slow = st.number_input(t("ui_slow", lang), min_value=2, value=60, step=1)
        discount = st.number_input(t("ui_discount", lang), min_value=0.01, max_value=1.0, value=1.0, step=0.05)
        run = st.button(t("ui_run", lang), type="primary", use_container_width=True)

    st.title(t("strategy_sma", lang, fast=int(fast), slow=int(slow)))
    st.caption(t("disclaimer", lang))

    if not run:
        st.info(t("ui_upload_hint", lang))
        return
    if uploaded is None:
        st.error(t("ui_need_file", lang))
        return
    if fast >= slow:
        st.error(t("error_bad_windows", lang))
        return

    try:
        prices = _read_upload(uploaded)
    except ValueError as exc:
        st.error(str(exc))
        return

    market = get_market(market_code)
    costs = CostModel.from_market(market, discount=discount)
    position = sma_crossover(prices["close"], fast=int(fast), slow=int(slow))
    result = run_backtest(prices, position, costs)
    stats = summarize(result, prices, periods_per_year=market.trading_days_per_year)

    cols = st.columns(4)
    cols[0].metric(t("total_return", lang), _format("total_return", stats["total_return"], lang))
    cols[1].metric(t("cagr", lang), _format("cagr", stats["cagr"], lang))
    cols[2].metric(t("max_drawdown", lang), _format("max_drawdown", stats["max_drawdown"], lang))
    cols[3].metric(t("buy_hold", lang), _format("buy_hold", stats["buy_hold"], lang))

    st.subheader(t("ui_equity", lang))
    st.line_chart(result.equity.rename("strategy"))

    st.subheader(t("trades", lang))
    if result.trades:
        trades = pd.DataFrame(
            [
                {
                    "entry": trade.entry_date.date(),
                    "exit": trade.exit_date.date() if trade.exit_date is not None else "open",
                    "return": f"{trade.return_:.2%}",
                }
                for trade in result.trades
            ]
        )
        st.dataframe(trades, use_container_width=True, hide_index=True)
    else:
        st.write(t("ui_no_trades", lang))


if __name__ == "__main__":
    main()
