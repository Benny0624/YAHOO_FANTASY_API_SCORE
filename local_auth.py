"""
本機執行 Yahoo OAuth 授權流程，產生包含 refresh_token 的 oauth2.json。

執行前請確認：
1. 已安裝套件：pip install yahoo-oauth
2. 已在 https://developer.yahoo.com/apps/ 建立 App，取得 consumer_key / consumer_secret
3. App 的 Redirect URI 設為 oob（Out-of-band）

用法：python local_auth.py
"""

import json
from yahoo_oauth import OAuth2

OAUTH_FILE = "oauth2.json"

# ─────────────────────────────────────────
# 若 oauth2.json 不存在，先建立一個只含 key/secret 的骨架
# ─────────────────────────────────────────
import os, sys

if not os.path.exists(OAUTH_FILE):
    consumer_key    = input("請輸入 Yahoo App Consumer Key: ").strip()
    consumer_secret = input("請輸入 Yahoo App Consumer Secret: ").strip()
    skeleton = {
        "consumer_key": consumer_key,
        "consumer_secret": consumer_secret
    }
    with open(OAUTH_FILE, "w", encoding="utf-8") as f:
        json.dump(skeleton, f)
    print(f"✅ 已建立 {OAUTH_FILE}，準備開始授權流程...\n")

# ─────────────────────────────────────────
# 執行 OAuth2 授權（會自動開瀏覽器並提示你貼上 verifier code）
# ─────────────────────────────────────────
sc = OAuth2(None, None, from_file=OAUTH_FILE)

if sc.token_is_valid():
    print("✅ 授權成功！\n")
else:
    print("❌ 授權失敗，請重試。")
    sys.exit(1)

# ─────────────────────────────────────────
# 印出供 Render 使用的環境變數值
# ─────────────────────────────────────────
with open(OAUTH_FILE, "r", encoding="utf-8") as f:
    oauth_data = json.load(f)

print("=" * 60)
print("請將以下 JSON 整串複製，貼到 Render 的 YAHOO_OAUTH_JSON 環境變數：")
print("=" * 60)
print(json.dumps(oauth_data))
print("=" * 60)

# 確認 refresh_token 是否存在
if oauth_data.get("refresh_token"):
    print("✅ refresh_token 存在，可正常部署到 Render。")
else:
    print("⚠️  警告：oauth2.json 中沒有 refresh_token，部署後 token 過期時將無法自動更新。")
    print("   請確認 Yahoo App 的 Redirect URI 設為 oob，並重新授權。")
