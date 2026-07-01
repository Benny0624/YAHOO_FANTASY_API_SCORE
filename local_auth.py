"""
本機執行 Yahoo OAuth2 授權流程，產生包含 refresh_token 的 oauth2.json。

執行前請確認：
1. 已安裝套件：pip install requests
2. 已在 https://developer.yahoo.com/apps/ 建立 App，取得 consumer_key / consumer_secret
3. App 的 Redirect URI 設為 oob（Out-of-band / 本機應用程式）

用法：python local_auth.py
"""

import json
import os
import sys
import time
import webbrowser
from base64 import b64encode

import requests
from dotenv import load_dotenv

load_dotenv()

OAUTH_FILE = "oauth2.json"

# ─────────────────────────────────────────
# 讀取 consumer_key / consumer_secret
# 優先順序：oauth2.json → .env YAHOO_OAUTH_JSON → 手動輸入
# ─────────────────────────────────────────
consumer_key = None
consumer_secret = None

if os.path.exists(OAUTH_FILE):
    with open(OAUTH_FILE, "r", encoding="utf-8") as f:
        existing = json.load(f)
    consumer_key    = existing.get("consumer_key")
    consumer_secret = existing.get("consumer_secret")

if not consumer_key or not consumer_secret:
    env_json_str = os.environ.get("YAHOO_OAUTH_JSON", "")
    if env_json_str:
        try:
            env_data        = json.loads(env_json_str)
            consumer_key    = consumer_key    or env_data.get("consumer_key")
            consumer_secret = consumer_secret or env_data.get("consumer_secret")
        except json.JSONDecodeError:
            pass

if not consumer_key:
    consumer_key = input("請輸入 Yahoo App Consumer Key: ").strip()
if not consumer_secret:
    consumer_secret = input("請輸入 Yahoo App Consumer Secret: ").strip()

# ─────────────────────────────────────────
# Step 1：產生授權 URL，請使用者手動開啟
# ─────────────────────────────────────────
auth_url = (
    "https://api.login.yahoo.com/oauth2/request_auth"
    f"?client_id={consumer_key}"
    "&redirect_uri=oob"
    "&response_type=code"
    "&language=en-us"
)

print("\n" + "=" * 60)
print("請用瀏覽器開啟以下網址並登入 Yahoo 授權：")
print("=" * 60)
print(auth_url)
print("=" * 60)

opened = False
try:
    opened = webbrowser.open(auth_url)
except Exception:
    pass

if opened:
    print("（已嘗試自動開啟瀏覽器）")
else:
    print("（自動開啟失敗，請手動複製上方網址貼到瀏覽器）")

# ─────────────────────────────────────────
# Step 2：使用者貼回授權碼
# ─────────────────────────────────────────
print()
code = input("授權完成後，請貼上 Yahoo 頁面顯示的授權碼 (authorization code): ").strip()

if not code:
    print("❌ 授權碼不能為空，請重試。")
    sys.exit(1)

# ─────────────────────────────────────────
# Step 3：用授權碼換取 access_token + refresh_token
# ─────────────────────────────────────────
creds_b64 = b64encode(f"{consumer_key}:{consumer_secret}".encode()).decode()

resp = requests.post(
    "https://api.login.yahoo.com/oauth2/get_token",
    headers={
        "Authorization": f"Basic {creds_b64}",
        "Content-Type": "application/x-www-form-urlencoded",
    },
    data={
        "grant_type": "authorization_code",
        "redirect_uri": "oob",
        "code": code,
    },
    timeout=15,
)

if resp.status_code != 200:
    print(f"❌ 取得 token 失敗 (HTTP {resp.status_code}):")
    print(resp.text)
    sys.exit(1)

token_data = resp.json()

# ─────────────────────────────────────────
# Step 4：寫入 oauth2.json（格式與 yahoo_oauth 相容）
# ─────────────────────────────────────────
oauth2_json = {
    "consumer_key": consumer_key,
    "consumer_secret": consumer_secret,
    "access_token": token_data["access_token"],
    "refresh_token": token_data["refresh_token"],
    "token_type": token_data.get("token_type", "bearer"),
    "guid": token_data.get("xoauth_yahoo_guid", ""),
    "token_time": time.time(),
    "expires_in": token_data.get("expires_in", 3600),
}

with open(OAUTH_FILE, "w", encoding="utf-8") as f:
    json.dump(oauth2_json, f, indent=2)

print(f"\n✅ 已成功寫入 {OAUTH_FILE}")

# ─────────────────────────────────────────
# Step 5：印出供 Render 使用的環境變數值
# ─────────────────────────────────────────
print("\n" + "=" * 60)
print("請將以下 JSON 整串複製，貼到 Render 的 YAHOO_OAUTH_JSON 環境變數：")
print("=" * 60)
print(json.dumps(oauth2_json))
print("=" * 60)

if oauth2_json.get("refresh_token"):
    print("✅ refresh_token 存在，可正常部署到 Render。")
else:
    print("⚠️  警告：未取得 refresh_token，請確認 App 的 Redirect URI 設為 oob 後重試。")
