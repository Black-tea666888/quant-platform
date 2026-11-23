"""Self-contained HTML performance report. No external scripts, styles or fonts are needed.

Contents: summary statistics, equity curve (with optional benchmark), drawdown chart,
monthly returns table, and the trade list. Charts are inline SVG.
"""

from __future__ import annotations

import html
import math
from pathlib import Path

import pandas as pd

from quant_platform.i18n import t


def _svg_line(series_list: list[tuple[pd.Series, str]], width: int = 720, height: int = 220, pct: bool = False) -> str:
    """Inline SVG line chart for one or more series that share the same index."""
    values = [s.dropna().astype(float) for s, _ in series_list]
    lows = min(float(v.min()) for v in values if len(v))
    highs = max(float(v.max()) for v in values if len(v))
    if highs == lows:
        highs = lows + 1.0
    pad_left, pad_bottom, pad_top, pad_right = 58, 26, 10, 10
    plot_w, plot_h = width - pad_left - pad_right, height - pad_top - pad_bottom

    def y_of(v: float) -> float:
        return pad_top + plot_h * (1 - (v - lows) / (highs - lows))

    parts = [f'<svg viewBox="0 0 {width} {height}" width="100%" role="img" xmlns="http://www.w3.org/2000/svg">']
    parts.append(f'<rect x="{pad_left}" y="{pad_top}" width="{plot_w}" height="{plot_h}" fill="none" stroke="#ddd"/>')
    for frac in (0.0, 0.5, 1.0):
        v = lows + (highs - lows) * frac
        y = y_of(v)
        label = f"{v:.1%}" if pct else f"{v:.2f}"
        parts.append(f'<line x1="{pad_left}" x2="{pad_left + plot_w}" y1="{y:.1f}" y2="{y:.1f}" stroke="#eee"/>')
        parts.append(f'<text x="{pad_left - 6}" y="{y + 4:.1f}" font-size="11" text-anchor="end" fill="#555">{html.escape(label)}</text>')
    for series, color in series_list:
        clean = series.dropna().astype(float)
        if len(clean) < 2:
            continue
        n = len(clean)
        points = []
        for i, v in enumerate(clean.values):
            x = pad_left + plot_w * i / (n - 1)
            points.append(f"{x:.1f},{y_of(float(v)):.1f}")
        parts.append(f'<polyline fill="none" stroke="{color}" stroke-width="1.6" points="{" ".join(points)}"/>')
    parts.append("</svg>")
    return "".join(parts)


def monthly_returns(equity: pd.Series) -> pd.DataFrame:
    """Table of monthly returns: rows are years, columns are months 1 to 12."""
    month_end = equity.resample("ME").last()
    monthly = month_end.pct_change()
    if len(monthly):
        # First month: compare its last value with the first equity value.
        monthly.iloc[0] = month_end.iloc[0] / equity.iloc[0] - 1.0 if equity.iloc[0] else math.nan
    table = monthly.to_frame("r")
    table["year"] = table.index.year
    table["month"] = table.index.month
    return table.pivot(index="year", columns="month", values="r").reindex(columns=range(1, 13))


def _fmt_pct(value: float) -> str:
    return "N/A" if isinstance(value, float) and math.isnan(value) else f"{value:.2%}"


def build_report_html(
    title: str,
    equity: pd.Series,
    stats: dict,
    trades: list,
    lang: str = "en",
    benchmark: pd.Series | None = None,
    subtitle: str = "",
) -> str:
    """Build the HTML document as a string."""
    drawdown = equity / equity.cummax() - 1.0
    series_main = [(equity, "#1f77b4")]
    if benchmark is not None:
        series_main.append((benchmark, "#999999"))

    summary_rows = []
    for key in ("total_return", "cagr", "max_drawdown", "sharpe", "sortino", "calmar", "exposure", "trades", "win_rate", "buy_hold"):
        if key not in stats:
            continue
        value = stats[key]
        if isinstance(value, float):
            shown = _fmt_pct(value) if key not in ("sharpe", "sortino", "calmar") else ("N/A" if math.isnan(value) else f"{value:.4f}")
        else:
            shown = html.escape(str(value))
        summary_rows.append(f"<tr><th>{html.escape(t(key, lang))}</th><td>{shown}</td></tr>")

    month_table = monthly_returns(equity)
    month_header = "".join(f"<th>{m}</th>" for m in range(1, 13))
    month_body = []
    for year, row in month_table.iterrows():
        cells = "".join(
            "<td></td>" if pd.isna(v) else f'<td style="color:{"#1a7f37" if v >= 0 else "#b42318"}">{v:.1%}</td>'
            for v in row.values
        )
        month_body.append(f"<tr><th>{year}</th>{cells}</tr>")

    trade_rows = []
    for trade in trades:
        exit_text = trade.exit_date.date().isoformat() if trade.exit_date is not None else t("ui_open", lang)
        trade_rows.append(
            f"<tr><td>{trade.entry_date.date().isoformat()}</td><td>{exit_text}</td><td>{trade.return_:.2%}</td></tr>"
        )
    trade_body = "".join(trade_rows) or f'<tr><td colspan="3">{html.escape(t("ui_no_trades", lang))}</td></tr>'

    return f"""<!DOCTYPE html>
<html lang="{html.escape(lang)}">
<head>
<meta charset="utf-8">
<title>{html.escape(title)}</title>
<style>
body {{ font-family: -apple-system, "Helvetica Neue", Arial, "Noto Sans TC", sans-serif; margin: 24px; color: #222; max-width: 900px; }}
h1 {{ font-size: 22px; margin-bottom: 4px; }}
h2 {{ font-size: 16px; margin-top: 28px; }}
.sub {{ color: #666; font-size: 13px; margin-top: 0; }}
table {{ border-collapse: collapse; font-size: 13px; }}
th, td {{ padding: 4px 8px; border-bottom: 1px solid #eee; text-align: right; }}
th {{ font-weight: 600; text-align: left; }}
.summary th {{ width: 260px; }}
.note {{ color: #666; font-size: 12px; margin-top: 28px; }}
</style>
</head>
<body>
<h1>{html.escape(title)}</h1>
<p class="sub">{html.escape(subtitle)}</p>
<h2>{html.escape(t("total_return", lang))}</h2>
{_svg_line(series_main)}
<h2>{html.escape(t("max_drawdown", lang))}</h2>
{_svg_line([(drawdown, "#b42318")], pct=True)}
<h2>{html.escape(t("ui_summary", lang))}</h2>
<table class="summary">{''.join(summary_rows)}</table>
<h2>{html.escape(t("ui_monthly", lang))}</h2>
<table><tr><th></th>{month_header}</tr>{''.join(month_body)}</table>
<h2>{html.escape(t("trades", lang))}</h2>
<table><tr><th>{html.escape(t("ui_entry", lang))}</th><th>{html.escape(t("ui_exit", lang))}</th><th>{html.escape(t("ui_return", lang))}</th></tr>{trade_body}</table>
<p class="note">{html.escape(t("disclaimer", lang))}</p>
</body>
</html>
"""


def write_report(path: str | Path, **kwargs) -> Path:
    out = Path(path)
    out.write_text(build_report_html(**kwargs), encoding="utf-8")
    return out
