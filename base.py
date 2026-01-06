import os, subprocess, hashlib, time
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HLS_DIR = os.path.join(BASE_DIR, "static", "streams")
os.makedirs(HLS_DIR, exist_ok=True)

@app.route("/convert", methods=["POST", "OPTIONS"])
def convert():
    if request.method == "OPTIONS": return jsonify({"status": "ok"}), 200

    data = request.get_json(silent=True)
    video_url = data.get("url")
    if not video_url: return jsonify({"error": "No URL"}), 400

    stream_id = hashlib.md5(video_url.encode()).hexdigest()
    out_dir = os.path.join(HLS_DIR, stream_id)
    playlist = os.path.join(out_dir, "index.m3u8")

    if not os.path.exists(out_dir):
        os.makedirs(out_dir, exist_ok=True)

    # If it doesn't exist, start the conversion
    if not os.path.exists(playlist):
        # UNIVERSAL COMMAND: Works for MKV, x265, x264, MP4
        cmd = [
            "ffmpeg", "-y",
            "-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "5",
            "-i", video_url,
            "-map", "0:v:0",           # Take only the first video track
            "-map", "0:a:0",           # Take only the first audio track
            "-c:v", "copy",             # Fast copy video (works if source is h264/h265)
            "-c:a", "aac",              # Convert audio to standard AAC
            "-ac", "2",                 # Force Stereo
            "-sn", "-dn",               # REMOVE SUBTITLES AND DATA (Prevents crashes)
            "-f", "hls",
            "-hls_time", "10",
            "-hls_list_size", "0",
            "-hls_playlist_type", "vod", # REMOVES LIVE BADGE
            "-hls_segment_filename", os.path.join(out_dir, "seg_%05d.ts"),
            playlist
        ]
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Return the link immediately
    proto = request.headers.get("X-Forwarded-Proto", "https")
    hls_url = f"{proto}://{request.host}/static/streams/{stream_id}/index.m3u8"
    return jsonify({"status": "success", "hls_link": hls_url})

@app.route("/static/streams/<path:filename>")
def serve_hls(filename):
    response = send_from_directory(HLS_DIR, filename)
    response.headers["Access-Control-Allow-Origin"] = "*"
    # Crucial for browser to recognize it's a video stream
    if filename.endswith(".m3u8"):
        response.headers["Content-Type"] = "application/vnd.apple.mpegurl"
    return response

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
