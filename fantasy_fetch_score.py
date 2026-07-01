import os
import requests
from fastapi import FastAPI
from fastapi.responses import JSONResponse

app = FastAPI(title="Yahoo Connection Test API")

# 模擬測試的函數，將結果改為回傳 dict
def run_test_url(name, url, headers=None, data=None):
    result = {"name": name, "url": url}
    try:
        if data:
            response = requests.post(url, headers=headers, data=data, timeout=10)
        else:
            response = requests.get(url, headers=headers, timeout=10)

        result.update({
            "status": "Success",
            "http_status_code": response.status_code,
            "content_length": len(response.text),
            "preview": response.text[:200].strip()
        })
    except Exception as e:
        result.update({
            "status": "Failed",
            "error": str(e)
        })
    return result

@app.get("/")
def home():
    return {
        "message": "Yahoo Connection Test API is running!",
        "endpoints": {
            "Run All Tests": "/test"
        }
    }

@app.get("/test")
def run_all_tests():
    # 測試 A：預設 Python UA 連到 Yahoo
    test_a = run_test_url(
        "A. 預設 Python UA 連到 Yahoo", 
        "https://api.login.yahoo.com/oauth2/get_token", 
        data={"test": "1"}
    )
    # 測試 B：偽裝成 Chrome 瀏覽器連到 Yahoo
    chrome_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    test_b = run_test_url(
        "B. 偽裝 Chrome UA 連到 Yahoo", 
        "https://api.login.yahoo.com/oauth2/get_token", 
        headers=chrome_headers, 
        data={"test": "1"}
    )

    # 測試 C：測試連線到 Google
    test_c = run_test_url(
        "C. 測試連線到 Google", 
        "https://www.google.com", 
        headers=chrome_headers
    )
    return JSONResponse(content={
        "environment": "Render Cloud",
        "results": [test_a, test_b, test_c]
    })
