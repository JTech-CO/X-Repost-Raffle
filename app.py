# app.py
import os, json, random
from flask import Flask, request, jsonify
from flask_cors import CORS

from selenium_crawler import collect_retweeters

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}}) # 나중에 실제 도메인 들어갈 장소 

@app.get("/api/health")
def health():
    return {"ok": True}

@app.get("/api/crawl")
def crawl():
    url = request.args.get("url", "").strip()
    if not url:
        return jsonify({"error": "missing url"}), 400

    users = collect_retweeters(
        tweet_url=url,
        username=os.getenv("X_USERNAME"),
        password=os.getenv("X_PASSWORD"),
        headless=True
    )
    return jsonify({"users": users, "count": len(users)})

@app.post("/api/draw")
def draw():
    data = request.get_json(force=True) or {}
    users = data.get("users") or []
    count = int(data.get("count") or 1)
    if not users: return jsonify({"error":"no users"}), 400
    count = max(1, min(count, len(users)))
    return jsonify({"winners": random.sample(users, count), "count": count})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
