import os
import subprocess
import hashlib
import time
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# Use absolute paths for Render
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
    log_file = os.path.join(out_dir, "ffmpeg_log.txt") # For debugging

    os.makedirs(out_dir, exist_ok=True)

    # 1. Check if already exists
    if os.path.exists(playlist) and os.path.getsize(playlist) > 0:
        proto = request.headers.get("X-Forwarded-Proto", "https")
        return jsonify({
            "status": "success",
            "hls_link": f"{proto}://{request.host}/static/streams/{stream_id}/index.m3u8"
        })

    # 2. Browser-like headers (Crucial for remote links)
    headers = (
        "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36\r\n"
        "Referer: https://360hub.fun/\r\n"
    )

    # 3. Enhanced FFmpeg Command
    cmd = [
        "ffmpeg", "-y",
        "-headers", headers,  # Mimic browser
        "-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "5",
        "-i", video_url,
        "-map", "0:v:0",      # 1st Video
        "-map", "0:a",        # All Audio
        "-c:v", "copy",       # Direct Copy (Super Fast)
        "-c:a", "aac",        # AAC for web
        "-ac", "2",
        "-sn", "-dn",         # Disable subs and data (Prevents PNG crash)
        "-f", "hls",
        "-hls_time", "10",
        "-hls_list_size", "0",
        "-hls_playlist_type", "vod", # Removes LIVE badge
        "-hls_flags", "independent_segments",
        "-hls_segment_filename", os.path.join(out_dir, "seg_%05d.ts"),
        playlist
    ]

    try:
        # Open log file to capture errors
        with open(log_file, "w") as log:
            subprocess.Popen(cmd, stdout=log, stderr=log)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

    # 4. Wait for the file to be created (Max 20 seconds)
    ready = False
    for i in range(20):
        if os.path.exists(playlist) and os.path.getsize(playlist) > 100: # Ensure it has data
            ready = True
            break
        time.sleep(1)

    if ready:
        proto = request.headers.get("X-Forwarded-Proto", "https")
        hls_url = f"{proto}://{request.host}/static/streams/{stream_id}/index.m3u8"
        return jsonify({"status": "success", "hls_link": hls_url})
    else:
        # If it failed, send the last few lines of the log to help us debug
        error_msg = "Unknown Error"
        if os.path.exists(log_file):
            with open(log_file, "r") as f:
                error_msg = f.readlines()[-3:] # Last 3 lines
        return jsonify({"status": "error", "message": "FFmpeg Failed", "details": error_msg}), 500

@app.route("/static/streams/<path:filename>")
def serve_hls(filename):
    response = send_from_directory(HLS_DIR, filename)
    if filename.endswith(".m3u8"):
        response.headers["Content-Type"] = "application/vnd.apple.mpegurl"
    response.headers["Access-Control-Allow-Origin"] = "*"
    return response

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
