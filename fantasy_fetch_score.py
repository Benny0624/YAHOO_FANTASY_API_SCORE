import os
import json
import smtplib
from email.mime.text import MIMEText
from email.header import Header
from fastapi import FastAPI, BackgroundTasks
from fastapi.responses import JSONResponse

# 引入 Yahoo Fantasy API 相關套件
from yahoo_oauth import OAuth2
import yahoo_fantasy_api as yfa

app = FastAPI(title="Yahoo Fantasy API & Outlook Mailer")

# ==================== 1. 環境變數讀取與暫存檔處理 ====================
YAHOO_LEAGUE_ID = os.environ.get("YAHOO_LEAGUE_ID")
YAHOO_OAUTH_JSON_STR = os.environ.get("YAHOO_OAUTH_JSON")
YAHOO_SPORT = os.environ.get("YAHOO_SPORT", "mlb")

OUTLOOK_EMAIL = os.environ.get("OUTLOOK_EMAIL")
OUTLOOK_PASSWORD = os.environ.get("OUTLOOK_PASSWORD")
OUTLOOK_TO_EMAILS = os.environ.get("OUTLOOK_TO_EMAILS", "")

# 將 Yahoo OAuth JSON 寫入暫存檔，供 yahoo_oauth 套件讀取
OAUTH_FILE_PATH = "/tmp/oauth2.json"

def init_yahoo_oauth_file():
    if YAHOO_OAUTH_JSON_STR:
        try:
            # 驗證是否為合法 JSON，並寫入 /tmp/oauth2.json
            oauth_data = json.loads(YAHOO_OAUTH_JSON_STR)
            with open(OAUTH_FILE_PATH, "w", encoding="utf-8") as f:
                json.dump(oauth_data, f)
            print(f"✅ 成功將 YAHOO_OAUTH_JSON 寫入暫存路徑: {OAUTH_FILE_PATH}")
        except Exception as e:
            print(f"❌ 解析 YAHOO_OAUTH_JSON 失敗: {e}")
    else:
        print("⚠️ 未偵測到 YAHOO_OAUTH_JSON 環境變數")

# 啟動時立即執行一次
init_yahoo_oauth_file()

# ==================== 2. Outlook 寄信函數 ====================

def send_outlook_email(subject: str, body_text: str):
    if not OUTLOOK_EMAIL or not OUTLOOK_PASSWORD:
        print("❌ 寄信失敗：未設定 Outlook 帳號或密碼環境變數")
        return False

    # 解析多個收件者
    recipients = [email.strip() for email in OUTLOOK_TO_EMAILS.split(",") if email.strip()]
    if not recipients:
        print("❌ 寄信失敗：收件者清單 (OUTLOOK_TO_EMAILS) 為空")
        return False

    try:
        msg = MIMEText(body_text, 'plain', 'utf-8')
        msg['Subject'] = Header(subject, 'utf-8')
        msg['From'] = OUTLOOK_EMAIL
        msg['To'] = ", ".join(recipients)

        # Outlook 使用 smtp-mail.outlook.com 587 埠口 (TLS)
        with smtplib.SMTP("smtp-mail.outlook.com", 587) as server:
            server.starttls()  # 啟動安全加密
            server.login(OUTLOOK_EMAIL, OUTLOOK_PASSWORD)
            server.sendmail(OUTLOOK_EMAIL, recipients, msg.as_string())
        
        print(f"📧 郵件成功寄出至: {recipients}")
        return True
    except Exception as e:
        print(f"❌ Outlook 寄信發生錯誤: {e}")
        return False

# ==================== 3. Yahoo Fantasy API 抓取邏輯 ====================

def fetch_yahoo_fantasy_data():
    if not os.path.exists(OAUTH_FILE_PATH):
        return "錯誤：找不到 Yahoo OAuth 憑證檔，請確認環境變數 YAHOO_OAUTH_JSON 是否正確。"

    try:
        # 1. 認證登入 (yahoo_oauth 會自動讀取並更新 /tmp/oauth2.json)
        sc = OAuth2(None, None, from_file=OAUTH_FILE_PATH)

        # 2. 建立 Game 物件
        gm = yfa.Game(sc, YAHOO_SPORT)
        # 3. 取得 League 物件
        # 如果沒有設定 League ID，就抓取使用者目前擁有的第一個 League ID
        league_id = YAHOO_LEAGUE_ID
        if not league_id:
            leagues = gm.league_ids()
            if leagues:
                league_id = leagues[0]
            else:
                return "錯誤：此 Yahoo 帳號目前沒有任何聯盟資料。"
        lg = gm.to_league(league_id)
        
        # 4. 抓取聯盟基本資訊
        settings = lg.settings()
        standings = lg.standings()

        # 5. 格式化成信件要顯示的文字
        report = f"🏆 Yahoo Fantasy 聯盟報告 ({YAHOO_SPORT.upper()})\n"
        report += "=" * 40 + "\n"
        report += f"聯盟名稱: {settings.get('name', '未知')}\n"
        report += f"聯盟 ID: {league_id}\n\n"
        report += "📊 目前聯盟排名 (Standings):\n"
        report += "-" * 40 + "\n"
        for idx, team in enumerate(standings, 1):
            # 根據套件回傳結構，可能為 dict 或物件，這裡做安全讀取
            team_name = team.get('name') if isinstance(team, dict) else getattr(team, 'name', str(team))
            report += f"{idx}. {team_name}\n"
        return report

    except Exception as e:
        return f"❌ 抓取 Yahoo Fantasy 資料時發生錯誤: {str(e)}"


# ==================== 4. API 路由設定 ====================

@app.get("/")
def home():
    return {
        "status": "Yahoo Fantasy Mailer is running!",
        "config_check": {
            "has_league_id": bool(YAHOO_LEAGUE_ID),
            "has_oauth_json": bool(YAHOO_OAUTH_JSON_STR),
            "sport": YAHOO_SPORT
            "outlook_sender": OUTLOOK_EMAIL,
            "has_outlook_password": bool(OUTLOOK_PASSWORD),
            "recipients": OUTLOOK_TO_EMAILS
        },
        "endpoints": {
            "Trigger Send Mail": "/send-report"
        }
    }
    
@app.get("/send-report")
def trigger_send_report(background_tasks: BackgroundTasks):
    # 1. 每次觸發時，確保暫存檔存在（防範 Render 容器重啟導致 /tmp 遺失）
    init_yahoo_oauth_file()
    
    # 2. 抓取 Yahoo Fantasy 資料
    report_content = fetch_yahoo_fantasy_data()
    # 3. 如果抓取成功，丟到背景寄信
    if "錯誤" not in report_content and "❌" not in report_content:
        subject = f"📢 Yahoo Fantasy ({YAHOO_SPORT.upper()}) 聯盟最新戰報"
        background_tasks.add_task(send_outlook_email, subject, report_content)
        
        return JSONResponse(content={
            "status": "Success",
            "message": "已成功抓取資料，正在背景透過 Outlook 寄出信件！",
            "preview_data": report_content[:300] + "\n... (下略) ..."
        })
    else:
        # 如果抓取失敗，不寄信，直接回傳錯誤原因
        return JSONResponse(status_code=500, content={
            "status": "Failed",
            "message": "抓取資料失敗，未寄出信件。",
            "error_detail": report_content
        })
