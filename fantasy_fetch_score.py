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

app = FastAPI(title="Yahoo Fantasy API & Brevo Mailer")

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

    try:
        with open(OAUTH_FILE_PATH, "r", encoding="utf-8") as f:
            oauth_data = json.load(f)
        if not oauth_data.get("refresh_token"):
            return "❌ oauth2.json 缺少 refresh_token"
    except Exception as e:
        return f"❌ 讀取 oauth2.json 失敗: {str(e)}"

    try:
        sc = OAuth2(None, None, from_file=OAUTH_FILE_PATH, browser_callback=None)
        gm = yfa.Game(sc, YAHOO_SPORT)
        league_id = YAHOO_LEAGUE_ID
        if not league_id:
            leagues = gm.league_ids()
            if leagues:
                league_id = leagues[0]
            else:
                return "錯誤：此 Yahoo 帳號目前沒有任何聯盟資料。"
        if "." not in str(league_id):
            league_id = f"{gm.game_id()}.l.{league_id}"
        lg = gm.to_league(league_id)

        settings = lg.settings()
        standings = lg.standings()
        current_week = lg.current_week()
        matchups_data = lg.matchups()

        # 5. 格式化成信件要顯示的文字
        report = f"🏆 Yahoo Fantasy 聯盟報告 ({YAHOO_SPORT.upper()})\n"
        report += "=" * 40 + "\n"
        report += f"聯盟名稱: {settings.get('name', '未知')}\n"
        report += f"目前週次: Week {current_week}\n\n"

        # --- A. 聯盟排名 (Standings) ---
        report += "📊 目前聯盟排名 (Standings):\n"
        report += "-" * 40 + "\n"

        for idx, team in enumerate(standings, 1):
            team_name = team.get('name') if isinstance(team, dict) else getattr(team, 'name', str(team))
            report += f"{idx}. {team_name}\n"
        report += "\n"
        
        # --- B. 本週對戰成績 (Matchups) ---
        report += f"⚔️ Week {current_week} 本週對戰成績 (Matchups):\n"
        report += "-" * 40 + "\n"

        # 解析 Yahoo 奇葩的 matchups 結構
        matchups_dict = {}
        try:
            # 依據你的 JSON 結構定位到 matchups 節點
            matchups_dict = matchups_data.get('fantasy_content', {}).get('league', [{}, {}])[1].get('scoreboard', {}).get('0', {}).get('matchups', {})
        except Exception as e:
            print(f"定位 matchups 節點失敗: {e}")

        if matchups_dict:
            match_idx = 1
            # 遍歷 "0", "1", "2", "3"... 等對戰組合
            for key, val in matchups_dict.items():
                if key.isdigit():
                    try:
                        matchup = val.get('matchup', {})
                        # 取得 teams 中的 "0" 與 "1" 兩隊
                        teams_data = matchup.get('0', {}).get('teams', {})

                        t1_obj = teams_data.get('0', {}).get('team', [])
                        t2_obj = teams_data.get('1', {}).get('team', [])


                        if len(t1_obj) >= 2 and len(t2_obj) >= 2:
                            # 1. 解析隊伍名稱 (在第一個陣列元素的 index 2 的 'name')
                            t1_name = t1_obj[0][2].get('name', '未知隊伍1')
                            t2_name = t2_obj[0][2].get('name', '未知隊伍2')
                            
                            # 2. 解析當前比分 (在第二個元素 dictionary 的 'team_points' 裡)
                            t1_score = t1_obj[1].get('team_points', {}).get('total', '0')
                            t2_score = t2_obj[1].get('team_points', {}).get('total', '0')

                            report += f"Match {match_idx}:\n"
                            report += f"  🔥 {t1_name} ({t1_score})  vs  {t2_name} ({t2_score})\n\n"
                            match_idx += 1
                    except Exception as e:
                        print(f"解析對戰組合 {key} 失敗: {e}")
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
    body    = "這是一封測試信，確認 Brevo API 設定正確。"
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
            "message": "已成功抓取資料，正在背景透過 Brevo 寄出信件！",
            "preview_data": report_content[:300] + "\n... (下略) ..."
        })
    else:
        # 如果抓取失敗，不寄信，直接回傳錯誤原因
        return JSONResponse(status_code=500, content={
            "status": "Failed",
            "message": "抓取資料失敗，未寄出信件。",
            "error_detail": report_content
        })
