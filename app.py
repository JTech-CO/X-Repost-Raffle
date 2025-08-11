# app.py
import os, json, random, time, traceback
from flask import Flask, request, jsonify
from flask_cors import CORS
from selenium_crawler import collect_retweeters

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})

@app.get("/api/health")
def health():
    return {"ok": True, "ts": time.time()}

@app.get("/api/crawl")
def crawl():
    url = request.args.get("url","").strip()
    if not url:
        return jsonify({"error":"missing url"}), 400
    start = time.time()
    try:
        users = collect_retweeters(url, headless=True, max_scroll=50, pause=1.0)
        return jsonify({"users": users, "count": len(users), "duration": round(time.time()-start,1)})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.post("/api/draw")
def draw():
    data = request.get_json(force=True, silent=True) or {}
    users = data.get("users") or []
    count = max(1, min(int(data.get("count") or 1), len(users) or 1))
    return jsonify({"winners": random.sample(users, count), "count": count})


