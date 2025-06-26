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


# ▶️ /play for m3u8 & ts proxying
@app.route("/play")
def play_proxy():
    target_url = request.args.get("url")
    if not target_url:
        return jsonify({"error": "Missing URL parameter"}), 400

    try:
        resp = requests.get(target_url, headers={"User-Agent": "Mozilla/5.0"}, stream=True, timeout=10)
        content_type = resp.headers.get("Content-Type", "")

        # .m3u8 playlist rewrite
        if "application/vnd.apple.mpegurl" in content_type or target_url.endswith(".m3u8"):
            base_url = target_url.rsplit("/", 1)[0] + "/"
            content = resp.text

            def rewrite_line(line):
                if line.strip().startswith("#") or not line.strip():
                    return line
                return "/play?url=" + urljoin(base_url, line.strip())

            rewritten = "\n".join(rewrite_line(line) for line in content.splitlines())
            return Response(rewritten, content_type=content_type)

        # .ts segments or other files — stream directly
        return Response(resp.iter_content(chunk_size=1024), content_type=content_type)

    except Exception as e:
        return jsonify({"error": f"Proxy error: {str(e)}"}), 500
        


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
