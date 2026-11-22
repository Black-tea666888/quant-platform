# quant-platform（回測 MVP）

免費、開源的台股量化回測工具。第一版只做回測，不連接券商、不下真實訂單、不提供投資建議。

## 功能
- 讀取本機 CSV，或從 Yahoo Finance 下載台股日線（代號加 `.TW`，例如 `2330.TW`）
- 證交所官方日線（`--source twse`）：未還原除權息，與 Yahoo 的還原價不能直接比較
- SMA 均線交叉策略（可調短、長均線天數）
- 唐奇安通道突破策略（收盤突破前 N 日高點進場、跌破前 M 日低點出場，預設 55 / 20）
- 時間序列動能策略（收盤高於 N 日前即持有，預設 N=126）
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

### 每日排程（可選，範例未安裝）
資料來源用 Yahoo 時，台股收盤後（約 14:00 後）再跑較合適。以下是 macOS/Linux crontab 範例（週一至週五 18:00），請把路徑換成你的實際路徑：

```cron
0 18 * * 1-5 cd /路徑/quant-platform && .venv/bin/python -m quant_platform.paper_cli --symbol 2330.TW --state paper_2330.json --capital 1000000 >> paper.log 2>&1
```

- 狀態檔（`paper_2330.json`）第一次執行會自動建立，之後接續。
- macOS 的 launchd 代理程式無法存取「文件」資料夾（隱私權限），排程放在「文件」底下會以結束碼 78 失敗。請把排程用的副本放在家目錄下（例如 `~/quant-paper`），並在那裡建立 `.venv`。
- 排程會自動下單到模擬帳戶，不會連接券商；請定期檢查 `paper.log`。

## 網頁介面（Streamlit）
```bash
pip install -r requirements-ui.txt
streamlit run app.py
```
- 側邊欄可輸入 Yahoo 代號（例如 `2330.TW`）與起始日，或上傳 CSV；有輸入代號時優先使用代號。
- 「回測」分頁：設定均線與折扣，看績效指標、權益曲線與交易紀錄。
- 「紙上交易」分頁：設定初始資金（僅新帳戶），可上傳上次下載的狀態 JSON 接續，看帳戶權益與本次新增委託，並可下載新的狀態檔。
- 「回測」分頁底部的「研究檢查」：可設定樣本外切分日期，比較樣本內與樣本外的績效；另有成本敏感度表，列出券商折扣與滑價各種假設的結果，不挑最佳參數。
- 介面支援英文與繁體中文。

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
# 唐奇安突破（進場 55 日 / 出場 20 日）
python -m quant_platform.cli --symbol 2330.TW --strategy donchian --entry-days 55 --exit-days 20

# 用 Yahoo Finance 資料回測（SMA，預設）
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
