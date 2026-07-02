# Yahoo Fantasy API Score Mailer

定期抓取 Yahoo Fantasy 聯盟排名，透過 [Brevo](https://brevo.com) 寄出戰報信件。部署於 [Render](https://render.com/)，提供 HTTP endpoint 觸發，搭配 GitHub Actions 每日自動執行。

---

## 架構

```
GET /send-report
  └─ fetch_yahoo_fantasy_data()   # 呼叫 Yahoo Fantasy API
  └─ send_email()                  # 透過 Brevo HTTP API 寄信（背景執行）

GET /test-email                    # 同步寄一封測試信，確認設定正確
```

---

## 環境變數

| 變數名稱 | 必填 | 說明 |
|---|---|---|
| `YAHOO_LEAGUE_ID` | 否 | 聯盟 ID，純數字或完整格式 `469.l.230329` 皆可 |
| `YAHOO_OAUTH_JSON` | **是** | 完整 OAuth2 憑證 JSON（一行字串），由 `local_auth.py` 產生 |
| `YAHOO_SPORT` | 否 | 運動類型，預設 `mlb` |
| `BREVO_API_KEY` | **是** | Brevo API Key |
| `BREVO_FROM_EMAIL` | **是** | 寄件者信箱（需在 Brevo 完成驗證） |
| `BREVO_FROM_NAME` | 否 | 寄件者顯示名稱，預設 `Yahoo Fantasy Report` |
| `TO_EMAILS` | **是** | 收件者，多位用逗號分隔 |

---

## 本機開發

### 1. 安裝 uv

```bash
pip install uv
```

### 2. 建立虛擬環境並安裝套件

```bash
uv venv
.venv\Scripts\activate       # Windows
# source .venv/bin/activate  # macOS / Linux

uv pip install -r requirements.txt
```

### 3. 設定環境變數

```bash
cp .env.example .env
```

編輯 `.env`，填入所有必填欄位（詳見下方各節說明）。

### 4. 啟動本機伺服器

```bash
uvicorn fantasy_fetch_score:app --reload
```

- 服務狀態：[http://localhost:8000](http://localhost:8000)
- 觸發寄信：[http://localhost:8000/send-report](http://localhost:8000/send-report)
- 測試信件：[http://localhost:8000/test-email](http://localhost:8000/test-email)

---

## 取得 Yahoo OAuth 憑證

> Token 有效期約一年，到期後重新執行此步驟即可。

### 前置：建立 Yahoo Developer App

1. 前往 [developer.yahoo.com/apps](https://developer.yahoo.com/apps/) 建立新 App
2. **Redirect URI** 填入 `oob`
3. **Permissions** 勾選 `Fantasy Sports` → Read（或 Read/Write）
4. 記下 `Consumer Key` 與 `Consumer Secret`

### 執行本機授權腳本

```bash
python local_auth.py
```

1. 腳本自動讀取 `.env` 中的 `YAHOO_OAUTH_JSON`（若有）取出 key/secret，否則手動輸入
2. 印出 Yahoo 授權網址，開啟瀏覽器登入並點擊「允許」
3. 將 Yahoo 頁面顯示的授權碼貼回終端機
4. 腳本完成後印出完整 JSON（含 `refresh_token`）並寫入本機 `oauth2.json`

### 更新 YAHOO_OAUTH_JSON

將腳本最後印出的 JSON 整行複製：
- **本機**：貼入 `.env` 的 `YAHOO_OAUTH_JSON=` 後方
- **Render**：貼入 Dashboard → Environment → `YAHOO_OAUTH_JSON` → Save

---

## 設定 Brevo 寄信

> Render free tier 封鎖 SMTP port，改用 Brevo HTTP API（port 443）寄信。

### 1. 取得 API Key

1. 註冊 [brevo.com](https://brevo.com)
2. 右上角帳號 → **SMTP & API** → **API Keys** → 建立新 Key
3. 複製 Key（格式為 `xkeysib-...`）

### 2. 驗證寄件信箱

1. Brevo 左側選單 → **Senders & IP** → **Senders** → **Add a sender**
2. 填入你要用來寄信的信箱（Gmail、Outlook 皆可）
3. Brevo 會寄驗證信到該信箱，點擊確認連結即完成

### 3. 設定 Render 環境變數

在 Render Dashboard → **Environment** 新增：

| 變數 | 範例值 |
|---|---|
| `BREVO_API_KEY` | `xkeysib-abc123...` |
| `BREVO_FROM_EMAIL` | `your_email@gmail.com` |
| `BREVO_FROM_NAME` | `Yahoo Fantasy Report` |
| `TO_EMAILS` | `alice@example.com,bob@example.com` |

---

## 部署到 Render

### 首次部署

1. 登入 [render.com](https://render.com) → **New** → **Web Service**
2. 連結此 GitHub Repo
3. 填入以下設定：

| 項目 | 值 |
|---|---|
| **Runtime** | Python |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `uvicorn fantasy_fetch_score:app --host 0.0.0.0 --port $PORT` |

4. **Environment** 頁面填入所有環境變數（參考上方各節）
5. 點擊 **Deploy**，等待部署完成

### 確認部署成功

```
GET https://your-app.onrender.com/
```

回傳 `config_check` 中所有 `has_*` 為 `true` 即代表設定正確。

### 測試寄信

```
GET https://your-app.onrender.com/test-email
```

回傳 `"status": "Success"` 且收到信件即完成。

### 後續更新

push 到 `main` branch 後，Render 會自動重新部署。

---

## 設定 GitHub Actions 每日自動排程

### 1. 新增 GitHub Secret

GitHub Repo → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

| Name | Value |
|---|---|
| `RENDER_ENDPOINT_URL` | `https://your-app.onrender.com` |

### 2. 確認 Workflow 檔案已存在

`.github/workflows/daily-report.yml` 已設定每天 UTC 12:00（台灣時間 20:00）自動觸發。

### 3. 手動測試

GitHub → **Actions** → **Daily Fantasy Score Report** → **Run workflow**

> **注意**：Render free tier 服務閒置後會休眠，GitHub Actions 的請求會觸發 cold start（約 30–60 秒）。若請求超時，可在 workflow 的 `curl` 指令加上 `-m 90` 延長 timeout。
