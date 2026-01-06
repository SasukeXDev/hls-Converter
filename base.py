import os
import subprocess
import hashlib
import time
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# Setup directories
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HLS_DIR = os.path.join(BASE_DIR, "static", "streams")
os.makedirs(HLS_DIR, exist_ok=True)

@app.route("/convert", methods=["POST", "OPTIONS"])
def convert():
    if request.method == "OPTIONS":
        return jsonify({"status": "ok"}), 200

    data = request.get_json(silent=True)
    if not data or "url" not in data:
        return jsonify({"status": "error", "message": "URL missing"}), 400

    video_url = data["url"]
    stream_id = hashlib.md5(video_url.encode()).hexdigest()
    out_dir = os.path.join(HLS_DIR, stream_id)
    playlist = os.path.join(out_dir, "index.m3u8")

    if not os.path.exists(out_dir):
        os.makedirs(out_dir, exist_ok=True)

    # 1. If playlist exists, return it immediately
    if os.path.exists(playlist) and os.path.getsize(playlist) > 0:
        proto = request.headers.get("X-Forwarded-Proto", "https")
        return jsonify({
            "status": "success",
            "hls_link": f"{proto}://{request.host}/static/streams/{stream_id}/index.m3u8"
        })

    # 2. Strict Browser Headers
    headers = (
        "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36\r\n"
        "Accept: */*\r\n"
        "Connection: keep-alive\r\n"
    )

    # 3. Streamlined FFmpeg Command
    # We remove complex flags to ensure it starts on any server
    cmd = [
        "ffmpeg", "-y",
        "-headers", headers,
        "-i", video_url,
        "-map", "0:v:0", 
        "-map", "0:a",
        "-c:v", "copy", 
        "-c:a", "aac", 
        "-ac", "2",
        "-sn", "-dn", 
        "-f", "hls",
        "-hls_time", "10",
        "-hls_list_size", "0",
        "-hls_playlist_type", "vod",
        "-hls_segment_filename", os.path.join(out_dir, "seg_%05d.ts"),
        playlist
    ]

    try:
        # Start FFmpeg and catch errors immediately if it fails to launch
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        
        # Short wait to see if it crashes instantly
        time.sleep(3) 
        
        if process.poll() is not None:
            # Process died. Capture the error output
            _, stderr = process.communicate()
            return jsonify({"status": "error", "message": "FFmpeg crashed on start", "details": stderr}), 500

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

    # 4. Success check loop
    ready = False
    for _ in range(15): # Wait up to 15 seconds for the file to appear
        if os.path.exists(playlist) and os.path.getsize(playlist) > 0:
            ready = True
            break
        time.sleep(1)

    if ready:
        proto = request.headers.get("X-Forwarded-Proto", "https")
        hls_url = f"{proto}://{request.host}/static/streams/{stream_id}/index.m3u8"
        return jsonify({"status": "success", "hls_link": hls_url})
    else:
        return jsonify({"status": "error", "message": "FFmpeg is taking too long or failed to write file."}), 500

@app.route("/static/streams/<path:filename>")
def serve_hls(filename):
    response = send_from_directory(HLS_DIR, filename)
    response.headers["Access-Control-Allow-Origin"] = "*"
    return response

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
