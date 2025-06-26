from flask import Flask, request, jsonify
import requests
import json
import os

app = Flask(__name__)

# 👇 Set your API key here (or through env var)
MY_SECRET_KEY = os.environ.get("API_KEY", " ")

# 🧠 Headers for hanime.tv
HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "X-Signature-Version": "web2",
    "X-Signature": os.urandom(16).hex()
}


def proxy_hanime_api(url, is_json=True):
    try:
        res = requests.get(url, headers=HEADERS)
        return res.json() if is_json else res.text
    except Exception as e:
        return {"error": str(e)}, 500


# ✅ API KEY PROTECTION
@app.before_request
def check_api_key():
    client_key = request.headers.get("X-API-Key")
    if client_key != MY_SECRET_KEY:
        return jsonify({"error": "Unauthorized"}), 401


# 🔥 Trending
@app.route("/trending")
def trending():
    time = request.args.get("time", "month")
    page = request.args.get("page", 0)
    url = f"https://hanime.tv/api/v8/browse-trending?time={time}&page={page}&order_by=views&ordering=desc"
    return proxy_hanime_api(url)


# 🔥 Video Details
@app.route("/video")
def video():
    slug = request.args.get("slug")
    url = f"https://hanime.tv/api/v8/video?id={slug}"
    return proxy_hanime_api(url)

# 🔥 Play Details
@app.route('/play')
def m3u8():
    link = request.args.get('link')
    if not link:
        return jsonify({"error": "Missing link"}), 400
    return render_template('play.html', link=link)
    return proxy_hanime_api(url)


# 🔥 Browse Tags & Brands
@app.route("/browse")
def browse():
    url = "https://hanime.tv/api/v8/browse"
    return proxy_hanime_api(url)


# 🔥 Browse category
@app.route("/getbrowsevideos")
def getbrowsevideos():
    page = request.args.get("page", 0)
    type_ = request.args.get("type")
    category = request.args.get("category")
    url = f"https://hanime.tv/api/v8/browse/{type_}/{category}?page={page}&order_by=views&ordering=desc"
    return proxy_hanime_api(url)


# 🔍 Search (POST to Search API)
@app.route("/search")
def search():
    query = request.args.get("query", "")
    page = int(request.args.get("page", 0))
    body = {
        "search_text": query,
        "tags": [],
        "brands": [],
        "blacklist": [],
        "order_by": [],
        "ordering": [],
        "page": page
    }
    try:
        res = requests.post("https://search.htv-services.com", json=body)
        return res.json()
    except Exception as e:
        return {"error": str(e)}, 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
