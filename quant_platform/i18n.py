"""Minimal message catalog. Keys are stable identifiers; translations live here.

Add a language by adding a dict to CATALOGS. Missing keys fall back to English.
"""

from __future__ import annotations

DEFAULT_LANG = "en"

CATALOGS: dict[str, dict[str, str]] = {
    "en": {
        "market": "Market",
        "strategy": "Strategy",
        "strategy_sma": "SMA crossover (fast {fast} / slow {slow})",
        "start_date": "Start date",
        "end_date": "End date",
        "total_return": "Total return",
        "cagr": "Annualized return (CAGR)",
        "max_drawdown": "Max drawdown",
        "sharpe": "Sharpe (risk-free rate = 0)",
        "exposure": "Time invested",
        "trades": "Closed trades",
        "win_rate": "Win rate",
        "buy_hold": "Buy & hold return (before costs)",
        "not_available": "N/A",
        "disclaimer": "Backtests do not predict future results. Validate with paper trading first.",
        "error_unknown_market": "Unknown market {code!r}. Known markets: {known}",
        "error_no_data": "No data returned for {symbol!r}",
        "error_missing_columns": "Missing required columns: {missing}",
        "error_no_rows": "No usable price rows after cleaning",
        "error_bad_windows": "Require 0 < fast < slow",
        "error_file_not_found": "File not found: {path}",
        "error_bad_range": "Start date must be before end date",
        "error_bad_date": "Dates must use the YYYY-MM-DD format",
        "error_bad_discount": "--discount must be greater than 0 and at most 1",
        "error_negative_rate": "{name} must be zero or positive",
        "error_positive_int": "{name} must be a positive integer",
        "ui_language": "Language",
        "ui_csv_label": "Price CSV (date, close)",
        "ui_fast": "Fast window",
        "ui_slow": "Slow window",
        "ui_discount": "Broker discount",
        "ui_run": "Run backtest",
        "ui_upload_hint": "Upload a CSV, then press Run backtest.",
        "ui_need_file": "Please upload a CSV file first.",
        "ui_no_trades": "No trades in this period.",
        "ui_equity": "Equity curve",
    },
    "zh-TW": {
        "market": "市場",
        "strategy": "策略",
        "strategy_sma": "SMA 交叉（短 {fast} / 長 {slow}）",
        "start_date": "起始日",
        "end_date": "結束日",
        "total_return": "總報酬",
        "cagr": "年化報酬 (CAGR)",
        "max_drawdown": "最大回撤",
        "sharpe": "Sharpe（無風險利率 = 0）",
        "exposure": "持股比例",
        "trades": "已平倉交易次數",
        "win_rate": "勝率",
        "buy_hold": "買進持有報酬（未扣成本）",
        "not_available": "N/A",
        "disclaimer": "回測結果不代表未來績效，請先用紙上交易驗證。",
        "error_unknown_market": "未知市場 {code!r}，已知市場：{known}",
        "error_no_data": "{symbol!r} 沒有回傳資料",
        "error_missing_columns": "缺少必要欄位：{missing}",
        "error_no_rows": "清理後沒有可用的價格資料",
        "error_bad_windows": "需要 0 < 短均線 < 長均線",
        "error_file_not_found": "找不到檔案：{path}",
        "error_bad_range": "起始日必須早於結束日",
        "error_bad_date": "日期格式必須為 YYYY-MM-DD",
        "error_bad_discount": "--discount 必須大於 0 且不超過 1",
        "error_negative_rate": "{name} 必須為 0 或正數",
        "error_positive_int": "{name} 必須為正整數",
        "ui_language": "語言",
        "ui_csv_label": "價格 CSV（date, close）",
        "ui_fast": "短均線天數",
        "ui_slow": "長均線天數",
        "ui_discount": "手續費折扣",
        "ui_run": "執行回測",
        "ui_upload_hint": "請上傳 CSV 檔，然後按「執行回測」。",
        "ui_need_file": "請先上傳 CSV 檔。",
        "ui_no_trades": "此期間沒有交易。",
        "ui_equity": "權益曲線",
    },
}

SUPPORTED_LANGS = tuple(CATALOGS)


def t(key: str, lang: str = DEFAULT_LANG, **params: object) -> str:
    """Look up a message, falling back to English, then to the key itself."""
    catalog = CATALOGS.get(lang, {})
    template = catalog.get(key) or CATALOGS[DEFAULT_LANG].get(key, key)
    return template.format(**params) if params else template
