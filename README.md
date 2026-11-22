# quant-platform（回測 MVP）

免費、開源的台股量化回測工具。第一版只做回測，不連接券商、不下真實訂單、不提供投資建議。

## 功能
- 讀取本機 CSV，或從 Yahoo Finance 下載台股日線（代號加 `.TW`，例如 `2330.TW`）
- SMA 均線交叉策略（可調短、長均線天數）
- 台股成本模型：手續費、折扣、證交稅（賣出）、滑價假設
- 績效統計：總報酬、CAGR、最大回撤、Sharpe、交易次數、勝率，並與買進持有比較

## 模擬交易（紙上交易）
不連接券商，每次執行只處理上次之後的新 K 線，狀態存在 JSON 檔中，適合每天執行一次。

```bash
python -m quant_platform.paper_cli --csv prices.csv --state paper.json --capital 1000000 --market US --lot-size 1
python -m quant_platform.paper_cli --csv prices.csv --state paper.json   # 之後每天重跑
```

- 訊號只在改變時才交易，避免每天因市值變動產生小額交易。
- 同一個狀態檔不能切換市場。
- 台股預設每張 1000 股（`--lot-size` 可改）。

## 網頁介面（Streamlit）
```bash
pip install -r requirements-ui.txt
streamlit run app.py
```
在側邊欄上傳 CSV、設定均線與折扣，即可看到績效指標、權益曲線與交易紀錄。介面支援英文與繁體中文。

## 語言
預設英文，可用 `--lang zh-TW` 切換為繁體中文。新增語言只需在 `quant_platform/i18n.py` 加入一組翻譯。

## 資料來源
`quant_platform/data_sources.py` 定義了可插拔的資料來源（目前有 `csv` 與 `yahoo`）。新增資料商時，繼承 `PriceSource` 並登錄到 `SOURCES` 即可。

## 市場設定
成本、幣別、交易日數等規則放在 `quant_platform/markets.py` 的市場設定檔中，不寫死在引擎裡。
- 內建：`TW`（台股，預設）、`US`（美股，示範用，費率請依你的券商確認）
- 自訂：用 `--market-file` 指定 JSON 檔，欄位與 `Market` 相同

```bash
python -m quant_platform.cli --csv prices.csv --market US
python -m quant_platform.cli --csv prices.csv --market-file my_market.json
```

## 安裝
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## 使用
```bash
# 用 Yahoo Finance 資料回測
python -m quant_platform.cli --symbol 2330.TW --start 2015-01-01 --fast 20 --slow 60

# 用本機 CSV（需包含 date, close 欄位）
python -m quant_platform.cli --csv prices.csv --fast 10 --slow 50 --discount 0.6
```

## 測試
```bash
pytest -q
```

## 重要假設（請務必了解）
- **無前視偏誤**：在第 t 日收盤根據資料做的決策，最早從第 t 日起持有，只計入之後的報酬。
- **成交假設**：以收盤價成交，並未模擬盤中流動性、漲跌停或無法成交的情況。
- **滑價**：預設為固定比例，實際會因股票流動性而不同。
- **資料**：Yahoo 資料為還原股價（已處理除權息），仍可能有缺漏或錯誤，需自行檢查。
- **績效**：回測結果不代表未來績效，容易因參數過度最佳化而失真。

本專案僅供學習與研究，不構成任何投資建議。
