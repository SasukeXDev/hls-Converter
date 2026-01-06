import os
import subprocess
import hashlib
import time
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HLS_DIR = os.path.join(BASE_DIR, "static", "streams")
os.makedirs(HLS_DIR, exist_ok=True)

FFMPEG_BIN = "ffmpeg"

@app.route("/convert", methods=["POST"])
def convert():
    data = request.get_json(silent=True)
    if not data or "url" not in data:
        return jsonify({"status": "error", "message": "URL missing"}), 400

    video_url = data["url"]
    stream_id = hashlib.md5(video_url.encode()).hexdigest()
    out_dir = os.path.join(HLS_DIR, stream_id)
    playlist = os.path.join(out_dir, "index.m3u8")

    os.makedirs(out_dir, exist_ok=True)

    if os.path.exists(playlist):
        # Re-check protocol to avoid Mixed Content
        proto = request.headers.get("X-Forwarded-Proto", "https")
        return jsonify({
            "status": "success",
            "hls_link": f"{proto}://{request.host}/static/streams/{stream_id}/index.m3u8"
        })

    # -------- FIXED FFMPEG COMMAND --------
    cmd = [
        FFMPEG_BIN, "-y",
        "-hide_banner", "-loglevel", "warning",
        "-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "5",
        "-i", video_url,

        # Map 1st video and ALL available audio streams
        "-map", "0:v:0",
        "-map", "0:a?",

        "-c:v", "copy",        # Fast copy video
        "-c:a", "aac",         # Encode all audio to AAC
        "-ac", "2",            # Downmix to stereo for web compatibility

        # HLS SETTINGS FOR VOD (Removes Live Badge)
        "-f", "hls",
        "-hls_time", "10",
        "-hls_list_size", "0",              # Keep all segments in the playlist
        "-hls_playlist_type", "vod",        # CRITICAL: Tells player it's NOT live
        "-hls_flags", "independent_segments",
        "-master_pl_name", "master.m3u8",   # Optional: useful for multi-track
        
        "-hls_segment_filename",
        os.path.join(out_dir, "seg_%05d.ts"),
        playlist
    ]

    try:
        # We don't wait for the whole movie to finish, just the first few segments
        subprocess.Popen(cmd) 
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

    # -------- WAIT UNTIL INITIAL PLAYLIST IS CREATED --------
    timeout = 15
    while timeout > 0:
        if os.path.exists(playlist):
            # Verify file has content before serving
            if os.path.getsize(playlist) > 0:
                break
        time.sleep(1)
        timeout -= 1

    if not os.path.exists(playlist):
        return jsonify({"status": "error", "message": "FFmpeg timed out"}), 500

    proto = request.headers.get("X-Forwarded-Proto", "https")
    host = request.headers.get("Host")
    hls_url = f"{proto}://{host}/static/streams/{stream_id}/index.m3u8"

    return jsonify({
        "status": "success",
        "hls_link": hls_url
    })

@app.route("/static/streams/<path:filename>")
def serve_hls(filename):
    response = send_from_directory(HLS_DIR, filename)
    # Correct Mime-Types are vital for Audio/Sub selection to show up
    if filename.endswith(".m3u8"):
        response.headers["Content-Type"] = "application/vnd.apple.mpegurl"
    elif filename.endswith(".ts"):
        response.headers["Content-Type"] = "video/MP2T"
    
    response.headers.update({
        "Access-Control-Allow-Origin": "*",
        "Cache-Control": "no-cache"
    })
    return response

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
