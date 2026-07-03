import os
import json
import requests
from datetime import datetime
from fastapi import FastAPI, BackgroundTasks, Request
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

load_dotenv()

# 引入 Yahoo Fantasy API 相關套件
from yahoo_oauth import OAuth2
import yahoo_fantasy_api as yfa

app = FastAPI(title="Yahoo Fantasy API & LINE Mailer")

# ==================== 1. 環境變數讀取與暫存檔處理 ====================
YAHOO_LEAGUE_ID = os.environ.get("YAHOO_LEAGUE_ID")
YAHOO_OAUTH_JSON_STR = os.environ.get("YAHOO_OAUTH_JSON")
YAHOO_SPORT = os.environ.get("YAHOO_SPORT", "mlb")

LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
LINE_TARGET_ID            = os.environ.get("LINE_TARGET_ID", "")

KEYWORDS_TOP3  = ["冠軍", "猛哥", "前三"]
KEYWORDS_TAIL3 = ["豆汁", "墊底", "阿嬤都比你強"]
KEYWORDS_ALL   = ["戰報", "戰爆"]

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

# ==================== 2. LINE 推播函數 ====================

LINE_MAX_CHARS_PER_MESSAGE = 4900  # LINE 單則文字訊息上限 5000 字，留點餘裕
LINE_MAX_MESSAGES_PER_PUSH = 5     # LINE push API 一次最多帶 5 則 message


## group message 使用
def send_line_message(text: str):
    if not LINE_CHANNEL_ACCESS_TOKEN:
        print("❌ 推播失敗：未設定 LINE_CHANNEL_ACCESS_TOKEN")
        return False
    if not LINE_TARGET_ID:
        print("❌ 推播失敗：未設定 LINE_TARGET_ID（群組 ID）")
        return False

    chunks = [text[i:i + LINE_MAX_CHARS_PER_MESSAGE]
              for i in range(0, len(text), LINE_MAX_CHARS_PER_MESSAGE)] or [text]
    chunks = chunks[:LINE_MAX_MESSAGES_PER_PUSH]

    try:
        resp = requests.post(
            "https://api.line.me/v2/bot/message/push",
            headers={
                "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
                "Content-Type":  "application/json",
            },
            json={
                "to":       LINE_TARGET_ID,
                "messages": [{"type": "text", "text": chunk} for chunk in chunks],
            },
            timeout=15,
        )
        if resp.status_code == 200:
            print(f"📱 LINE 訊息成功推播至: {LINE_TARGET_ID}")
            return True
        print(f"❌ LINE 推播失敗 (HTTP {resp.status_code}): {resp.text}")
        return False
    except Exception as e:
        print(f"❌ LINE 推播發生未預期錯誤: {e}")
        return False


## 關鍵字推播使用
def reply_line_message(reply_token: str, text: str):
    if not LINE_CHANNEL_ACCESS_TOKEN:
        print("❌ 回覆失敗：未設定 LINE_CHANNEL_ACCESS_TOKEN")
        return False

    chunks = [text[i:i + LINE_MAX_CHARS_PER_MESSAGE]
              for i in range(0, len(text), LINE_MAX_CHARS_PER_MESSAGE)] or [text]
    chunks = chunks[:LINE_MAX_MESSAGES_PER_PUSH]

    try:
        resp = requests.post(
            "https://api.line.me/v2/bot/message/reply",
            headers={
                "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
                "Content-Type":  "application/json",
            },
            json={
                "replyToken": reply_token,
                "messages":   [{"type": "text", "text": chunk} for chunk in chunks],
            },
            timeout=15,
        )
        if resp.status_code == 200:
            print("📱 LINE 訊息成功回覆！")
            return True
        print(f"❌ LINE 回覆失敗 (HTTP {resp.status_code}): {resp.text}")
        return False
    except Exception as e:
        print(f"❌ LINE 回覆發生未預期錯誤: {e}")
        return False

def reply_keyword_task(reply_token: str, keyword: str):
    init_yahoo_oauth_file()
    full_report = fetch_yahoo_fantasy_data()

    if keyword in KEYWORDS_TOP3:
        reply_content = filter_standings(full_report, "top3")
    elif keyword in KEYWORDS_TAIL3:
        reply_content = filter_standings(full_report, "tail3")
    else:  # 戰報
        reply_content = full_report

    reply_line_message(reply_token, reply_content)

# ==================== 3. Yahoo Fantasy API 抓取邏輯 ====================

def _to_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
    if keyword == "冠軍":
        reply_content = filter_standings(full_report, "top3")
    elif keyword == "後三名":
        reply_content = filter_standings(full_report, "tail3")
    else:  # 戰報
        reply_content = full_report

    reply_line_message(reply_token, reply_content)


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

        # 5. 格式化成戰報文字
        report = f"🏆 Yahoo Fantasy 聯盟戰報 ({YAHOO_SPORT.upper()})\n"
        report += "=" * 30 + "\n"
        report += f"聯盟名稱：{settings.get('name', '未知')}\n"
        report += f"目前週次：Week {current_week}\n"
        report += f"更新時間：{datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"

        # --- A. 聯盟排名 (Standings) ---
        report += "📊 聯盟排名\n"
        report += "-" * 30 + "\n"

        medals = {1: "🥇", 2: "🥈", 3: "🥉", 8: "[豆汁組]🤮", 9: "[豆汁組]🤮", 10: "[豆汁組]🤢"}
        for team in standings:
            name = team.get("name", "未知隊伍")
            rank_raw = team.get("rank", "?")
            rank = int(rank_raw) if str(rank_raw).isdigit() else None
            medal = medals.get(rank, "　")

            outcome = team.get("outcome_totals", {})
            wins   = outcome.get("wins", "-")
            losses = outcome.get("losses", "-")
            ties   = outcome.get("ties", "0")
            pct    = outcome.get("percentage", "-")
            games_back = team.get("games_back", "-") or "-"

            record = f"{wins}-{losses}" + (f"-{ties}" if ties not in ("0", 0, None) else "")
            report += f"{medal} {rank_raw}. {name}\n"
            report += f"    戰績 {record}（勝率 {pct}）落後 {games_back} 場\n"
        report += "\n"

        # --- B. 本週對戰成績 (Matchups) ---
        report += f"⚔️ Week {current_week} 對戰戰況\n"
        report += "-" * 30 + "\n"

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

                            t1_val, t2_val = _to_float(t1_score), _to_float(t2_score)
                            diff = abs(t1_val - t2_val)

                            if t1_val > t2_val:
                                line = f"👑 {t1_name} {t1_score}  -  {t2_score} {t2_name}"
                            elif t2_val > t1_val:
                                line = f"{t1_name} {t1_score}  -  {t2_score} 👑 {t2_name}"
                            else:
                                line = f"🤝 {t1_name} {t1_score}  -  {t2_score} {t2_name}（平手）"

                            report += f"Match {match_idx}：{line}\n"
                            report += f"    分差 {diff:.1f} 分\n\n"
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


def filter_standings(full_report: str, mode: str) -> str:
    """
    輔助函式：從完整戰報中，過濾出前三名或後三名的純文字
    mode: "top3" 或 "tail3"
    """
    if "❌" in full_report or "錯誤" in full_report:
        return full_report
        
    lines = full_report.split("\n")
    output = []

    # 保留標頭資訊（到 "📊 聯盟排名" 為止）
    for line in lines:
        output.append(line)
        if "📊 聯盟排名" in line:
            break
            
    # 找出所有排名資料行
    # 原本格式範例：
    # 🥇 1. 隊伍名稱
    #     戰績 10-5（勝率 .667）落後 - 場
    standing_lines = []
    start_collect = False
    for line in lines:
        if "📊 聯盟排名" in line:
            start_collect = True
            continue
        if start_collect:
            # 遇到下一個區塊（例如對戰戰況）就停止收集
            if "⚔️" in line or "Match" in line:
                break
            standing_lines.append(line)

    # 清理尾部空行
    while standing_lines and standing_lines[-1].strip() == "":
        standing_lines.pop()

    # 每一隊佔 2 行（隊伍名稱 + 戰績數據）
    teams = []
    for i in range(0, len(standing_lines), 2):
        if i + 1 < len(standing_lines):
            teams.append((standing_lines[i], standing_lines[i+1]))

    # 根據需求篩選
    if mode == "top3":
        selected_teams = teams[:3]
        output[0] = output[0].replace("聯盟戰報", "🥇頒獎前三名")
    else:  # tail3
        selected_teams = teams[-3:]
        output[0] = output[0].replace("聯盟戰報", "🤮豆汁倒楣鬼")
        
    # 重新組合
    for team_name_line, team_data_line in selected_teams:
        output.append(team_name_line)
        output.append(team_data_line)
        
    return "\n".join(output)
# ==================== 4. API 路由設定 ====================

@app.get("/")
def home():
    return {
        "status": "Yahoo Fantasy Mailer is running!",
        "config_check": {
            "has_league_id":       bool(YAHOO_LEAGUE_ID),
            "has_oauth_json":      bool(YAHOO_OAUTH_JSON_STR),
            "sport":               YAHOO_SPORT,
            "has_line_token":      bool(LINE_CHANNEL_ACCESS_TOKEN),
            "line_target_id_set":  bool(LINE_TARGET_ID),
        },
        "endpoints": {
            "Trigger Send Report": "/send-report",
            "Test LINE Push":      "/test-line",
            "LINE Webhook (取得 Group ID 用)": "/line-webhook"
        }
    }

@app.get("/get-top3")
def get_top3():
    """取得前三名"""
    init_yahoo_oauth_file()
    full_report = fetch_yahoo_fantasy_data()
    top3_report = filter_standings(full_report, "top3")

    if "❌" in top3_report or "錯誤" in top3_report:
        return JSONResponse(status_code=500, content={"status": "Failed", "error": top3_report})
    return JSONResponse(content={"status": "Success", "data": top3_report})


@app.get("/get-tail3")
def get_tail3():
    """取得後三名"""
    init_yahoo_oauth_file()
    full_report = fetch_yahoo_fantasy_data()
    tail3_report = filter_standings(full_report, "tail3")

    if "❌" in tail3_report or "錯誤" in tail3_report:
        return JSONResponse(status_code=500, content={"status": "Failed", "error": tail3_report})
    return JSONResponse(content={"status": "Success", "data": tail3_report})


@app.get("/test-line")
def test_line():
    """同步推播一則測試訊息，直接回傳成功或錯誤原因，方便除錯。"""
    text = "🔧 Yahoo Fantasy Mailer 測試訊息，確認 LINE 推播設定正確。"
    ok = send_line_message(text)
    if ok:
        return JSONResponse(content={"status": "Success", "message": "測試訊息已推播，請檢查 LINE。"})
    return JSONResponse(status_code=500, content={"status": "Failed", "message": "推播失敗，請查看 Render logs 取得詳細錯誤。"})



@app.post("/line-webhook")
async def line_webhook(request: Request):
    """
    LINE Bot 的 webhook URL。主要用途是幫忙撈出 LINE_TARGET_ID：
    把 Bot 加入群組後，群組裡任何人傳訊息或有成員異動，LINE 都會打這支
    endpoint，Render logs 會印出 groupId，複製貼到環境變數即可。
    """
    body = await request.json()
    for event in body.get("events", []):
        source = event.get("source", {})
        print(f"📩 LINE webhook event: type={source.get('type')}, "
              f"groupId={source.get('groupId')}, userId={source.get('userId')}")
    return JSONResponse(content={"status": "ok"})


@app.get("/send-report")
def trigger_send_report(background_tasks: BackgroundTasks):
    # 1. 每次觸發時，確保暫存檔存在（防範 Render 容器重啟導致 /tmp 遺失）
    init_yahoo_oauth_file()

    # 2. 抓取 Yahoo Fantasy 資料
    report_content = fetch_yahoo_fantasy_data()
    # 3. 如果抓取成功，丟到背景推播
    if "錯誤" not in report_content and "❌" not in report_content:
        background_tasks.add_task(send_line_message, report_content)

        return JSONResponse(content={
            "status": "Success",
            "message": "已成功抓取資料，正在背景透過 LINE 推播！",
            "preview_data": report_content[:300] + "\n... (下略) ..."
        })
    else:
        # 如果抓取失敗，不推播，直接回傳錯誤原因
        return JSONResponse(status_code=500, content={
            "status": "Failed",
            "message": "抓取資料失敗，未推播訊息。",
            "error_detail": report_content
        })
