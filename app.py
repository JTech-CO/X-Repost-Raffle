# app.py
import os, json, random, time, traceback
from flask import Flask, request, jsonify
from flask_cors import CORS
from selenium_crawler import collect_retweeters

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}}, supports_credentials=False)

@app.after_request
def add_headers(resp):
    # 일부 프록시에서 프리플라이트 캐시가 안 잡히는 경우 대비
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    resp.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    return resp

@app.get("/api/health")
def health():
    return {"ok": True, "ts": time.time()}

@app.get("/api/crawl")
def crawl():
    url = request.args.get("url", "").strip()
    if not url:
        return jsonify({"error": "missing url"}), 400

    # Render 프록시 한계(≈100s) 안에서 끝내기 위해 가드 타임아웃(80s) 권장
    start = time.time()
    try:
        users = collect_retweeters(
            tweet_url=url,
            username=os.getenv("X_USERNAME"),
            password=os.getenv("X_PASSWORD"),
            headless=True,
            max_scroll=50,
            pause=0.8,
        )
        dur = round(time.time() - start, 1)
        return jsonify({"users": users, "count": len(users), "duration": dur})
    except Exception as e:
        print("[crawl-error]", e)
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.post("/api/draw")
def draw():
    data = request.get_json(force=True, silent=True) or {}
    users = data.get("users") or []
    count = int(data.get("count") or 1)
    if not users: return jsonify({"error":"no users"}), 400
    count = max(1, min(count, len(users)))
    return jsonify({"winners": random.sample(users, count), "count": count})
