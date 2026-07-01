# Yahoo Fantasy API Score Mailer

定期抓取 Yahoo Fantasy 聯盟排名，透過 Outlook SMTP 寄出戰報信件。部署於 [Render](https://render.com/)，提供 HTTP endpoint 觸發。

---

## 架構

```
GET /send-report
  └─ fetch_yahoo_fantasy_data()   # 呼叫 Yahoo Fantasy API
  └─ send_outlook_email()          # 透過 Outlook SMTP 寄信（背景執行）
```

---

## 環境變數

| 變數名稱 | 必填 | 說明 |
|---|---|---|
| `YAHOO_LEAGUE_ID` | 否 | 聯盟 ID（未填則自動抓第一個）|
| `YAHOO_OAUTH_JSON` | **是** | 完整 OAuth2 憑證 JSON，一行字串 |
| `YAHOO_SPORT` | 否 | 運動類型，預設 `mlb` |
| `OUTLOOK_EMAIL` | **是** | 寄件者 Outlook 帳號 |
| `OUTLOOK_PASSWORD` | **是** | App Password（非帳號密碼）|
| `OUTLOOK_TO_EMAILS` | **是** | 收件者，多位用逗號分隔 |

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

複製範本並填入實際值：

```bash
cp .env.example .env
```

編輯 `.env`，填入所有必填欄位（詳見下方「取得 Yahoo OAuth 憑證」）。

### 4. 啟動本機伺服器

```bash
uvicorn fantasy_fetch_score:app --reload
```

開啟 [http://localhost:8000](http://localhost:8000) 確認服務狀態，
觸發寄信：[http://localhost:8000/send-report](http://localhost:8000/send-report)

---

## 取得 Yahoo OAuth 憑證

> 每次 Token 過期或需要重新授權時執行此步驟。

### 前置：建立 Yahoo App

1. 前往 [developer.yahoo.com/apps](https://developer.yahoo.com/apps/) 建立新 App
2. **Redirect URI** 填入 `oob`
3. **Permissions** 勾選 `Fantasy Sports` → Read（或 Read/Write）
4. 取得 `Consumer Key` 與 `Consumer Secret`

### 執行授權腳本

```bash
python local_auth.py
```

流程說明：
1. 腳本印出 Yahoo 授權網址，並嘗試自動開啟瀏覽器
2. 在瀏覽器中登入 Yahoo 並點擊「允許」
3. Yahoo 頁面顯示授權碼，複製後貼回終端機
4. 腳本完成後印出完整 JSON，同時寫入本機 `oauth2.json`

### 更新 YAHOO_OAUTH_JSON

將腳本印出的 JSON（一行）：
- **本機**：貼入 `.env` 的 `YAHOO_OAUTH_JSON=` 後方
- **Render**：貼入 Dashboard → Environment → `YAHOO_OAUTH_JSON`

---

## 部署到 Render

1. 連結此 GitHub Repo
2. **Build Command**：`pip install -r requirements.txt`
3. **Start Command**：`uvicorn fantasy_fetch_score:app --host 0.0.0.0 --port $PORT`
4. 在 Environment 頁面設定所有環境變數
5. Deploy 後打 `GET /send-report` 觸發寄信

---

## Outlook App Password 設定

帳號若開啟兩步驟驗證（建議開啟），需使用 App Password：

1. 前往 [account.microsoft.com/security](https://account.microsoft.com/security)
2. 進階安全性選項 → 應用程式密碼 → 建立新密碼
3. 將產生的密碼填入 `OUTLOOK_PASSWORD`
