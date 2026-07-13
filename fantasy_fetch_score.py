from fastapi import FastAPI, BackgroundTasks, Request
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

load_dotenv()

from yahoo_service import (
    YAHOO_LEAGUE_ID,
    YAHOO_OAUTH_JSON_STR,
    YAHOO_SPORT,
    init_yahoo_oauth_file,
    fetch_yahoo_fantasy_data,
    filter_standings,
)
from line_service import (
    LINE_CHANNEL_ACCESS_TOKEN,
    LINE_TARGET_ID,
    KEYWORDS_TOP3,
    KEYWORDS_TAIL3,
    KEYWORDS_ALL,
    KEYWORDS_STATS,
    KEYWORDS_STANDINGS,
    KEYWORDS_LIVE_STANDINGS,
    send_line_message,
    reply_keyword_task,
)

app = FastAPI(title="Yahoo Fantasy API & LINE Mailer")

# ==================== API 路由設定 ====================

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
            "Get Top 3":           "/get-top3",
            "Get Tail 3":          "/get-tail3",
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
async def line_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    LINE Bot 的 webhook URL。
    1. 幫忙撈出 LINE_TARGET_ID (印在 Render logs 裡)
    2. 監聽關鍵字：輸入「前三名」、「後三名」或「戰報」自動回覆
    """
    body = await request.json()
    for event in body.get("events", []):
        source = event.get("source", {})
        reply_token = event.get("replyToken")
        print(f"📩 LINE webhook event: type={source.get('type')}, "
              f"groupId={source.get('groupId')}, userId={source.get('userId')}")
        # 關鍵字觸發邏輯
        if event.get("type") == "message" and event.get("message", {}).get("type") == "text" and reply_token:
            user_text = event["message"]["text"].strip()
            user_text_lower = user_text.lower()

            # 合併所有支援的關鍵字清單
            all_supported = (
                KEYWORDS_TOP3 + KEYWORDS_TAIL3 + KEYWORDS_ALL + KEYWORDS_STATS
                + KEYWORDS_STANDINGS + KEYWORDS_LIVE_STANDINGS
            )
            # 判斷使用者輸入是否符合任何一組關鍵字
            if user_text_lower in [k.lower() for k in all_supported]:
                # 使用 FastAPI 的 BackgroundTasks 在背景執行，防止 LINE 平台因 3 秒沒收到 200 OK 而判定逾時
                background_tasks.add_task(reply_keyword_task, reply_token, user_text)

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
