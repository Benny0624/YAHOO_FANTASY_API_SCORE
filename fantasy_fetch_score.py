import os
import json
import requests
from fastapi import FastAPI, BackgroundTasks
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

load_dotenv()

# 引入 Yahoo Fantasy API 相關套件
from yahoo_oauth import OAuth2
import yahoo_fantasy_api as yfa

app = FastAPI(title="Yahoo Fantasy API & Outlook Mailer")

# ==================== 1. 環境變數讀取與暫存檔處理 ====================
YAHOO_LEAGUE_ID = os.environ.get("YAHOO_LEAGUE_ID")
YAHOO_OAUTH_JSON_STR = os.environ.get("YAHOO_OAUTH_JSON")
YAHOO_SPORT = os.environ.get("YAHOO_SPORT", "mlb")

BREVO_API_KEY    = os.environ.get("BREVO_API_KEY")
BREVO_FROM_EMAIL = os.environ.get("BREVO_FROM_EMAIL", "")
BREVO_FROM_NAME  = os.environ.get("BREVO_FROM_NAME", "Yahoo Fantasy Report")
TO_EMAILS        = os.environ.get("TO_EMAILS", "")

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

# ==================== 2. Brevo 寄信函數 ====================

def send_email(subject: str, body_text: str):
    if not BREVO_API_KEY:
        print("❌ 寄信失敗：未設定 BREVO_API_KEY")
        return False
    if not BREVO_FROM_EMAIL:
        print("❌ 寄信失敗：未設定 BREVO_FROM_EMAIL")
        return False

    recipients = [{"email": e.strip()} for e in TO_EMAILS.split(",") if e.strip()]
    if not recipients:
        print("❌ 寄信失敗：收件者清單 (TO_EMAILS) 為空")
        return False

    try:
        resp = requests.post(
            "https://api.brevo.com/v3/smtp/email",
            headers={
                "api-key":      BREVO_API_KEY,
                "Content-Type": "application/json",
            },
            json={
                "sender":      {"email": BREVO_FROM_EMAIL, "name": BREVO_FROM_NAME},
                "to":          recipients,
                "subject":     subject,
                "textContent": body_text,
            },
            timeout=15,
        )
        if resp.status_code == 201:
            print(f"📧 郵件成功寄出至: {[r['email'] for r in recipients]}")
            return True
        print(f"❌ Brevo 寄信失敗 (HTTP {resp.status_code}): {resp.text}")
        return False
    except Exception as e:
        print(f"❌ Brevo 寄信發生未預期錯誤: {e}")
        return False

# ==================== 3. Yahoo Fantasy API 抓取邏輯 ====================

def fetch_yahoo_fantasy_data():
    if not os.path.exists(OAUTH_FILE_PATH):
        return "錯誤：找不到 Yahoo OAuth 憑證檔，請確認環境變數 YAHOO_OAUTH_JSON 是否正確。"

    # 確認 oauth2.json 包含 refresh_token，避免進入互動授權流程
    try:
        with open(OAUTH_FILE_PATH, "r", encoding="utf-8") as f:
            oauth_data = json.load(f)
        if not oauth_data.get("refresh_token"):
            return "❌ oauth2.json 缺少 refresh_token，請在本機重新執行 Yahoo OAuth 授權流程，取得包含 refresh_token 的憑證後更新 YAHOO_OAUTH_JSON 環境變數。"
    except Exception as e:
        return f"❌ 讀取 oauth2.json 失敗: {str(e)}"
        
    try:
        # 1. 認證登入 (yahoo_oauth 會自動讀取並更新 /tmp/oauth2.json)
        # browser_callback=None 確保在無頭環境中不嘗試開啟瀏覽器互動
        sc = OAuth2(None, None, from_file=OAUTH_FILE_PATH, browser_callback=None)
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
        # Yahoo 要求完整格式 "{game_key}.l.{league_number}"
        # 若只填了數字部分，自動補上當前賽季 game_id
        if "." not in str(league_id):
            league_id = f"{gm.game_id()}.l.{league_id}"
        lg = gm.to_league(league_id)

        # 4. 抓取聯盟基本資訊
        settings = lg.settings()
        standings = lg.standings()
        # 🚀【新增】抓取當前週次與對戰組合 (Matchups) 資料
        current_week = lg.current_week()
        matchups_data = lg.matchups()

        # 5. 格式化成信件要顯示的文字
        report = f"🏆 Yahoo Fantasy 聯盟報告 ({YAHOO_SPORT.upper()})\n"
        report += "=" * 40 + "\n"
        report += f"聯盟名稱: {settings.get('name', '未知')}\n"
        report += f"聯盟 ID: {league_id}\n"
        report += f"目前週次: Week {current_week}\n\n" # 🚀【新增】信頭加上週次
        report += "📊 目前聯盟排名 (Standings):\n"
        report += "-" * 40 + "\n"
        for idx, team in enumerate(standings, 1):
            # 根據套件回傳結構，可能為 dict 或物件，這裡做安全讀取
            team_name = team.get('name') if isinstance(team, dict) else getattr(team, 'name', str(team))
            report += f"{idx}. {team_name}\n"
        report += "\n"

        # 🚀【新增】B. 本週對戰成績 (Matchups) 區段
        report += f"⚔️ Week {current_week} 本週對戰成績 (Matchups):\n"
        report += "-" * 40 + "\n"

        matchups_list = []
        if isinstance(matchups_data, dict):
            try:
                # 解析 Yahoo API 的巢狀結構
                matchups_list = matchups_data.get('fantasy_content', {}).get('league', [{}, {}])[1].get('scoreboard', {}).get('matchups', {}).get('matchup', [])
            except Exception:
                matchups_list = matchups_data if isinstance(matchups_data, list) else []
        elif isinstance(matchups_data, list):
            matchups_list = matchups_data
        if matchups_list:
            if isinstance(matchups_list, dict):
                matchups_list = [matchups_list]
            for idx, match in enumerate(matchups_list, 1):
                try:
                    teams = match.get('teams', {}).get('team', [])
                    if len(teams) >= 2:
                        team1 = teams[0]
                        team2 = teams[1]
                        team1_name = team1.get('name', '未知隊伍1')
                        team2_name = team2.get('name', '未知隊伍2')
                        # 取得兩隊目前的得分/勝場數 (Points / Category Wins)
                        team1_points = team1.get('team_points', {}).get('total', '0')
                        team2_points = team2.get('team_points', {}).get('total', '0')
                        report += f"Match {idx}:\n"
                        report += f"  🔥 {team1_name} ({team1_points})  vs  {team2_name} ({team2_points})\n\n"
                except Exception as e:
                    print(f"⚠️ 解析單一 Matchup 失敗: {e}")
        else:
            report += "（暫無本週對戰資料或格式解析失敗）\n"
        return report

    except EOFError:
        return "❌ Yahoo OAuth Token 已過期且無法在伺服器環境中互動授權。請在本機重新執行授權流程，取得新的 oauth2.json（包含有效的 refresh_token）後更新 YAHOO_OAUTH_JSON 環境變數。"
    except Exception as e:
        return f"❌ 抓取 Yahoo Fantasy 資料時發生錯誤: {str(e)}"
# ==================== 4. API 路由設定 ====================

@app.get("/")
def home():
    return {
        "status": "Yahoo Fantasy Mailer is running!",
        "config_check": {
            "has_league_id":    bool(YAHOO_LEAGUE_ID),
            "has_oauth_json":   bool(YAHOO_OAUTH_JSON_STR),
            "sport":            YAHOO_SPORT,
            "has_brevo_key":  bool(BREVO_API_KEY),
            "brevo_from":     BREVO_FROM_EMAIL,
            "recipients":     TO_EMAILS,
        },
        "endpoints": {
            "Trigger Send Mail": "/send-report",
            "Test Email Only":   "/test-email"
        }
    }


@app.get("/test-email")
def test_email():
    """同步寄一封測試信，直接回傳成功或錯誤原因，方便除錯。"""
    subject = "🔧 Yahoo Fantasy Mailer 測試信"
    body    = "這是一封測試信，確認 Outlook SMTP 設定正確。"
    ok = send_email(subject, body)
    if ok:
        return JSONResponse(content={"status": "Success", "message": "測試信已寄出，請檢查收件匣（含垃圾郵件）。"})
    return JSONResponse(status_code=500, content={"status": "Failed", "message": "寄信失敗，請查看 Render logs 取得詳細錯誤。"})
    
@app.get("/send-report")
def trigger_send_report(background_tasks: BackgroundTasks):
    # 1. 每次觸發時，確保暫存檔存在（防範 Render 容器重啟導致 /tmp 遺失）
    init_yahoo_oauth_file()
    
    # 2. 抓取 Yahoo Fantasy 資料
    report_content = fetch_yahoo_fantasy_data()
    # 3. 如果抓取成功，丟到背景寄信
    if "錯誤" not in report_content and "❌" not in report_content:
        subject = f"📢 Yahoo Fantasy ({YAHOO_SPORT.upper()}) 聯盟最新戰報"
        background_tasks.add_task(send_email, subject, report_content)
        
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
