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

## 驗證（滾動前進測試）
避免過度擬合的核心工具：在訓練區段選參數，只用下一段未參與選擇的測試區段計算績效，最後合併所有樣本外結果。

```bash
python -m quant_platform.validate_cli --csv prices.csv --fast 5,10,20 --slow 40,60,120 --train-bars 750 --test-bars 250 --market TW
```

- 參數只用訓練區段選擇，測試區段資料不會影響選擇（有對應測試）。
- 會提示：樣本外 Sharpe 為負、樣本內遠高於樣本外、參數頻繁變動、區段太少。
- 警示只是風險提示，不能證明策略有效或無效。

## 投資組合回測（多標的）
多個標的、定期再平衡，並與等權重買進持有比較。

```bash
python -m quant_platform.portfolio_cli --csv A=a.csv --csv B=b.csv --csv C=c.csv --freq monthly --market TW
python -m quant_platform.portfolio_cli --csv A=a.csv --csv B=b.csv --mode signal --fast 20 --slow 60 --freq weekly
```

- 只使用所有標的都有資料的日期（內連接），不會憑空補價格。
- 權重在再平衡當天收盤決定並以收盤成交，與單一標的引擎一致。
- 現金部位報酬為 0。採用可分割股數，實盤請改用整張或整股。
- 再平衡頻率：`daily`、`weekly`、`monthly`、`quarterly`、`never`。

## 風控
單一標的回測與紙上交易都可以加上風控覆寫（決策仍在收盤做出）：

```bash
python -m quant_platform.cli --csv prices.csv --stop-loss 0.08 --daily-loss-limit 0.03 --max-drawdown-halt 0.20
python -m quant_platform.paper_cli --csv prices.csv --state paper.json --stop-loss 0.08
python -m quant_platform.portfolio_cli --csv A=a.csv --csv B=b.csv --max-weight 0.25
```

- **停損**：收盤價低於進場價達設定比例時出場。
- **單日虧損上限**：持有部位單一 K 線虧損超過設定比例時出場。
- **最大回撤停止交易**：策略權益從高點回落超過設定比例時出場，並保持空手。
- **再進場條件**：出場後，必須等原訊號先關閉再開啟，才會重新進場。
- **部位上限**：投資組合中單一標的權重不超過設定值，超出的部分保留為現金。
- 風控判斷使用毛報酬（不含費用）。

## 績效報告（HTML）
加上 `--report` 會產生單一 HTML 檔，不需要網路或外部資源，內容包含：摘要指標、權益曲線與買進持有比較、回撤圖、月報酬表、交易明細。

```bash
python -m quant_platform.cli --csv prices.csv --fast 20 --slow 60 --report report.html
```

## 多用戶基礎（尚未上線）
`quant_platform/accounts.py` 提供帳號、密碼雜湊（PBKDF2-SHA256）、登入失敗鎖定、角色（admin / member）與每位使用者的獨立資料夾。

- 密碼至少 12 個字元，儲存的是雜湊值，不是明文。
- 連續 5 次登入失敗會鎖定 15 分鐘；錯誤訊息不會洩露帳號是否存在。
- 使用者只能讀寫自己的文件，admin 可以讀取所有人的文件。
- 檔名只允許英數字、`-` 與 `_`，避免路徑穿越。

**上線前仍需要**：HTTPS、正式資料庫（例如 PostgreSQL）、Email 驗證、密碼重設、稽核紀錄、權限與安全性審查，以及正式的 session 管理。

## 模擬交易機器人（僅紙上交易）
依你自己的設定檔每天執行策略，只做模擬，不會下真實訂單。

```bash
python -m quant_platform.bot --config examples/bot.example.json --state-dir state --log bot.log
```

- 設定檔的 `mode` 必須是 `"paper"`，其他值會被拒絕。
- 沒有券商連線，也不會替其他人下單或推薦標的。
- 每個策略有獨立的狀態檔，重複執行只會處理新的 K 線。
- 每次執行會把摘要寫入 log（每行一筆 JSON）。
- 可用 cron 或 launchd 每天排程執行。

**刻意不提供的功能**：真實下單、代客操作、替多人自動交易，以及付費的交易訊號。這些會涉及投顧、代客操作等法規，需要相關執照與法律審查，我不會在沒有你與律師確認的情況下實作。

### 網頁登入（可選）

- 設定 `QP_AUTH_DB` 指向 SQLite 檔案後，網頁會要求登入；未設定時維持原本的開放模式。
- 帳號由命令列建立（不提供自助註冊）：

```bash
python -m quant_platform.accounts_cli --db accounts.sqlite --workspace workspace create --email you@example.com --role admin
```

- 登入失敗只顯示一般性錯誤，不會透露帳號是否存在。
- 管理指令（需要能讀寫資料庫檔案，這是信任邊界）：

```bash
python -m quant_platform.accounts_cli --db accounts.sqlite --workspace workspace reset-password --email you@example.com
python -m quant_platform.accounts_cli --db accounts.sqlite --workspace workspace audit --limit 20
```

- 稽核紀錄會記下登入成功、失敗、鎖定、建立帳號、改密碼與改角色。紀錄不含密碼。
- 這只是基礎登入閘門。上線前仍需要 HTTPS、託管資料庫、Email 驗證、重設密碼、稽核紀錄與安全審查（見上方「多用戶基礎」）。

### 每日摘要 HTML（機器人）

```bash
python -m quant_platform.bot --config bot.json --state-dir state --summary-html summary.html --lang zh-TW
```

摘要頁面是獨立的 HTML，所有欄位都經過轉義，並標示「僅為模擬交易」。

## 上線前決策（已選定）

- **帳號開放方式：邀請制。** 只由管理者用 `accounts_cli create` 建立帳號，不提供自助註冊。在律師審查完成前，不對外開放註冊。
- **部署方式：單一 Linux 主機 + HTTPS 反向代理 + 持久化磁碟上的 SQLite。** 不把帳號資料庫放在 Streamlit Community Cloud，因為其檔案系統不保證持久。
- **仍待完成：** 網頁版重設密碼、Email 驗證（僅在改為自助註冊時需要）、託管資料庫（資料量變大時再評估）、安全審查、法律審查。
- **公開與收費上線：** 須先完成法律審查，並確認第 1 節的禁止事項（不代客下單、不保管資金、不做報酬承諾、不推薦個股）仍然成立。

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
