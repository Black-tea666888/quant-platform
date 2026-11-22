"""Streamlit dashboard: SMA crossover backtest and paper trading.

Run locally:
    pip install -r requirements-ui.txt
    streamlit run app.py
"""

from __future__ import annotations

import io
import json
from datetime import datetime

import pandas as pd
import streamlit as st

from quant_platform.backtest import CostModel, run_backtest, summarize
from quant_platform.data import clean_prices
from quant_platform.data_sources import get_source
from quant_platform.i18n import DEFAULT_LANG, SUPPORTED_LANGS, t
from quant_platform.markets import MARKETS, get_market
from quant_platform.paper import PaperAccount, advance
from quant_platform.strategy import (
    DEFAULT_STRATEGY, DONCHIAN_ENTRY_DAYS, DONCHIAN_EXIT_DAYS, MOMENTUM_LOOKBACK, STRATEGIES, build_position,
)

PERCENT_KEYS = {"total_return", "cagr", "max_drawdown", "exposure", "win_rate", "buy_hold"}
TW_LOT_SIZE = 1000
DEFAULT_START = "2015-01-01"


def _read_upload(uploaded) -> pd.DataFrame:
    return clean_prices(pd.read_csv(io.BytesIO(uploaded.getvalue())))


def _load_prices(lang: str, symbol: str, start: str, uploaded) -> pd.DataFrame:
    """Prices from a Yahoo symbol when one is entered, otherwise from the uploaded CSV. Raises ValueError."""
    symbol = symbol.strip()
    if symbol:
        try:
            datetime.strptime(start.strip(), "%Y-%m-%d")
        except ValueError as exc:
            raise ValueError(t("error_bad_date", lang)) from exc
        try:
            return get_source("yahoo").fetch(symbol, start.strip())
        except ValueError:
            raise
        except Exception as exc:  # network and provider errors from yfinance
            raise ValueError(str(exc)) from exc
    if uploaded is None:
        raise ValueError(t("ui_need_file", lang))
    return _read_upload(uploaded)


def _strategy_error(lang: str, strategy: str, params: dict) -> str | None:
    if strategy == "sma" and params["fast"] >= params["slow"]:
        return t("error_bad_windows", lang)
    if strategy == "donchian" and params["exit_days"] >= params["entry_days"]:
        return t("error_bad_donchian", lang)
    return None


def _format(key: str, value: object, lang: str) -> str:
    if isinstance(value, float):
        if value != value:  # NaN
            return t("not_available", lang)
        return f"{value:.2%}" if key in PERCENT_KEYS else f"{value:.4f}"
    return str(value)


def _render_backtest(lang: str, market_code: str, source: tuple, run: bool, strategy: str, params: dict, discount: float) -> None:
    if not run:
        st.info(t("ui_upload_hint", lang))
        return
    error = _strategy_error(lang, strategy, params)
    if error:
        st.error(error)
        return

    try:
        prices = _load_prices(lang, *source)
    except ValueError as exc:
        st.error(str(exc))
        return

    market = get_market(market_code)
    costs = CostModel.from_market(market, discount=discount)
    position = build_position(strategy, prices["close"], **params)
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

    st.download_button(
        t("ui_download_equity", lang),
        data=result.equity.rename("equity").to_csv(),
        file_name="equity.csv",
        mime="text/csv",
        key="bt_download_equity",
    )
    trade_rows = pd.DataFrame(
        [
            {
                "entry_date": trade.entry_date.date().isoformat(),
                "exit_date": trade.exit_date.date().isoformat() if trade.exit_date is not None else "",
                "return": trade.return_,
            }
            for trade in result.trades
        ],
        columns=["entry_date", "exit_date", "return"],
    )
    st.download_button(
        t("ui_download_trades", lang),
        data=trade_rows.to_csv(index=False),
        file_name="trades.csv",
        mime="text/csv",
        key="bt_download_trades",
    )


def _render_paper(lang: str, market_code: str, source: tuple, run_hint: bool, strategy: str, params: dict, discount: float) -> None:
    st.caption(t("paper_intro", lang))
    capital = st.number_input(
        t("paper_capital", lang), min_value=1.0, value=1_000_000.0, step=100_000.0, key="paper_capital"
    )
    state_upload = st.file_uploader(t("paper_state_label", lang), type="json", key="paper_state")
    run = st.button(t("paper_run", lang), type="primary", key="paper_run")

    if not run:
        st.info(t("paper_hint", lang))
        return
    error = _strategy_error(lang, strategy, params)
    if error:
        st.error(error)
        return

    market = get_market(market_code)
    try:
        prices = _load_prices(lang, *source)
        if state_upload is not None:
            account = PaperAccount.from_dict(json.loads(state_upload.getvalue().decode("utf-8")))
        else:
            account = PaperAccount.new(capital)
        if account.market and account.market != market.code:
            raise ValueError(t("paper_market_mismatch", lang, state=account.market, market=market.code))
        account.market = account.market or market.code

        costs = CostModel.from_market(market, discount=discount)
        lot_size = TW_LOT_SIZE if market.code == "TW" else 1
        position = build_position(strategy, prices["close"], **params)
        orders = advance(account, prices, position, costs, lot_size=lot_size)
    except (ValueError, TypeError) as exc:
        st.error(str(exc))
        return

    last = account.equity_curve[-1] if account.equity_curve else None
    cols = st.columns(3)
    cols[0].metric(t("paper_equity", lang), f"{last['equity']:,.0f}" if last else t("not_available", lang))
    cols[1].metric(t("paper_cash", lang), f"{account.cash:,.0f}")
    cols[2].metric(t("paper_shares", lang), f"{account.shares:,.0f}")

    st.subheader(t("paper_orders", lang))
    if orders:
        st.dataframe(pd.DataFrame(orders), use_container_width=True, hide_index=True)
    else:
        st.write(t("paper_no_orders", lang))

    if account.equity_curve:
        st.subheader(t("paper_equity_curve", lang))
        curve = pd.DataFrame(account.equity_curve).set_index("date")["equity"].rename("account")
        st.line_chart(curve)

    st.download_button(
        t("paper_download_state", lang),
        data=json.dumps(account.to_dict(), ensure_ascii=False, indent=2),
        file_name="paper_state.json",
        mime="application/json",
        key="paper_download",
    )


def main() -> None:
    st.set_page_config(page_title="quant-platform", layout="wide")

    with st.sidebar:
        langs = list(SUPPORTED_LANGS)
        lang = st.selectbox(t("ui_language", DEFAULT_LANG), langs, index=langs.index(DEFAULT_LANG))
        market_codes = sorted(MARKETS)
        market_code = st.selectbox(t("market", lang), market_codes, index=market_codes.index("TW"))
        symbol = st.text_input(t("ui_symbol", lang), value="", key="symbol")
        start = st.text_input(t("ui_start", lang), value=DEFAULT_START, key="start")
        uploaded = st.file_uploader(t("ui_csv_label", lang), type="csv")
        strategy = st.selectbox(
            t("ui_strategy", lang), list(STRATEGIES),
            format_func=lambda name: t(f"strategy_name_{name}", lang), key="strategy",
        )
        params: dict[str, int] = {}
        if strategy == "sma":
            params["fast"] = int(st.number_input(t("ui_fast", lang), min_value=1, value=20, step=1))
            params["slow"] = int(st.number_input(t("ui_slow", lang), min_value=2, value=60, step=1))
        else:
            params["entry_days"] = int(st.number_input(t("ui_entry_days", lang), min_value=2, value=DONCHIAN_ENTRY_DAYS, step=1))
            params["exit_days"] = int(st.number_input(t("ui_exit_days", lang), min_value=1, value=DONCHIAN_EXIT_DAYS, step=1))
        if strategy == "momentum":
            params["lookback"] = int(st.number_input(t("ui_lookback", lang), min_value=1, value=MOMENTUM_LOOKBACK, step=1))
        discount = st.number_input(t("ui_discount", lang), min_value=0.01, max_value=1.0, value=1.0, step=0.05)
        run = st.button(t("ui_run", lang), type="primary", use_container_width=True)

    source = (symbol, start, uploaded)
    if strategy == "sma":
        st.title(t("strategy_sma", lang, fast=params["fast"], slow=params["slow"]))
    elif strategy == "donchian":
        st.title(t("strategy_donchian", lang, entry=params["entry_days"], exit=params["exit_days"]))
    else:
        st.title(t("strategy_momentum", lang, lookback=params["lookback"]))
    st.caption(t("disclaimer", lang))

    tab_backtest, tab_paper = st.tabs([t("tab_backtest", lang), t("tab_paper", lang)])
    with tab_backtest:
        _render_backtest(lang, market_code, source, run, strategy, params, discount)
    with tab_paper:
        _render_paper(lang, market_code, source, run, strategy, params, discount)


if __name__ == "__main__":
    main()
