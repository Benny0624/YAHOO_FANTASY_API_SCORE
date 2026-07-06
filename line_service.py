import os
import requests

from yahoo_service import (
    init_yahoo_oauth_file,
    fetch_yahoo_fantasy_data,
    fetch_stat_leaders,
    filter_standings,
)

# ==================== 環境變數 ====================
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
LINE_TARGET_ID            = os.environ.get("LINE_TARGET_ID", "")

KEYWORDS_TOP3  = ["冠軍", "猛哥", "前三"]
KEYWORDS_TAIL3 = ["豆汁", "墊底", "阿嬤都比你強"]
KEYWORDS_ALL   = ["戰報", "戰爆"]
KEYWORDS_STATS = ["全壘打", "打點", "雙冠王", "打擊王", "hr", "rbi"]

# ==================== LINE 推播函數 ====================

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

    # 比對時轉小寫，確保英文關鍵字（如 top3）大小寫都能通
    keyword_lower = keyword.lower()
    if keyword_lower in [k.lower() for k in KEYWORDS_STATS]:
        reply_content = fetch_stat_leaders(keyword_lower)
    elif keyword_lower in [k.lower() for k in KEYWORDS_TOP3]:
        reply_content = filter_standings(full_report, "top3")
    elif keyword_lower in [k.lower() for k in KEYWORDS_TAIL3]:
        reply_content = filter_standings(full_report, "tail3")
    else:  # 戰報
        reply_content = full_report

    reply_line_message(reply_token, reply_content)
