import os, subprocess, hashlib, time, json
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HLS_ROOT = os.path.join(BASE_DIR, "static", "streams")
os.makedirs(HLS_ROOT, exist_ok=True)


def ffprobe_stream_id(url: str) -> str:
    """
    Generate a stable stream-id based on actual media info
    """
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_format", "-of", "json", url],
        capture_output=True,
        text=True
    )

    raw = probe.stdout or url
    return hashlib.md5(raw.encode()).hexdigest()


@app.route("/convert", methods=["POST"])
def convert():
    data = request.get_json(silent=True)
    video_url = data.get("url")

    if not video_url:
        return jsonify({"error": "No URL provided"}), 400

    stream_id = ffprobe_stream_id(video_url)
    out_dir = os.path.join(HLS_ROOT, stream_id)
    playlist = os.path.join(out_dir, "index.m3u8")

    os.makedirs(out_dir, exist_ok=True)

    # If conversion not started yet
    if not os.path.exists(playlist):
        cmd = [
            "ffmpeg", "-y",
            "-reconnect", "1",
            "-reconnect_streamed", "1",
            "-reconnect_delay_max", "5",
            "-i", video_url,

            # MAP ALL VIDEO + AUDIO
            "-map", "0:v:0",
            "-map", "0:a?",

            # Video
            "-c:v", "copy",

            # Audio (browser safe)
            "-c:a", "aac",
            "-ac", "2",

            # HLS output
            "-f", "hls",
            "-hls_time", "6",
            "-hls_list_size", "0",
            "-hls_playlist_type", "vod",
            "-hls_flags", "independent_segments",
            "-hls_segment_filename",
            os.path.join(out_dir, "seg_%05d.ts"),

            playlist
        ]

        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

        # WAIT until playlist exists (important)
        for _ in range(20):
            if os.path.exists(playlist):
                break
            time.sleep(0.5)

    proto = request.headers.get("X-Forwarded-Proto", "https")
    hls_url = f"{proto}://{request.host}/streams/{stream_id}/index.m3u8"

    return jsonify({
        "status": "ok",
        "stream_id": stream_id,
        "hls": hls_url
    })


# ✅ CORRECT STATIC ROUTE
@app.route("/streams/<stream_id>/<path:filename>")
def serve_hls(stream_id, filename):
    directory = os.path.join(HLS_ROOT, stream_id)
    response = send_from_directory(directory, filename)
    response.headers["Access-Control-Allow-Origin"] = "*"

    if filename.endswith(".m3u8"):
        response.headers["Content-Type"] = "application/vnd.apple.mpegurl"
    elif filename.endswith(".ts"):
        response.headers["Content-Type"] = "video/mp2t"

    return response


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
