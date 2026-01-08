import os
import subprocess
import hashlib
import time
import json
from threading import Thread
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HLS_DIR = os.path.join(BASE_DIR, "static/streams")
os.makedirs(HLS_DIR, exist_ok=True)

# Map ffprobe language codes to readable names
LANG_MAP = {
    "eng": "English",
    "hin": "Hindi",
    "ara": "Arabic",
    "spa": "Spanish",
    "fre": "French",
    "jpn": "Japanese",
    "kor": "Korean",
}

def get_audio_streams(url):
    """Return list of (index, language name)"""
    try:
        cmd = [
            "ffprobe", "-v", "error",
            "-select_streams", "a",
            "-show_entries", "stream=index:stream_tags=language",
            "-of", "json",
            url
        ]
        data = subprocess.check_output(cmd).decode()
        streams = json.loads(data).get("streams", [])
        result = []
        for i, s in enumerate(streams):
            lang = s.get("tags", {}).get("language", f"Audio {i+1}")
            lang_name = LANG_MAP.get(lang.lower(), lang.upper())
            result.append((s["index"], lang_name))
        return result
    except Exception as e:
        print("FFprobe failed:", e)
        return []

def hls_worker(video_url, out_dir):
    """Background HLS conversion"""
    master = os.path.join(out_dir, "master.m3u8")
    os.makedirs(out_dir, exist_ok=True)

    # 1️⃣ Video track
    video_cmd = [
        "ffmpeg", "-y", "-i", video_url,
        "-map", "0:v:0",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-profile:v", "main",
        "-pix_fmt", "yuv420p",
        "-an",
        "-f", "hls",
        "-hls_time", "6",
        "-hls_list_size", "0",
        "-hls_flags", "independent_segments",
        "-hls_segment_filename", f"{out_dir}/v_%05d.ts",
        f"{out_dir}/video.m3u8"
    ]
    subprocess.run(video_cmd, check=True)

    # 2️⃣ Audio tracks
    audio_streams = get_audio_streams(video_url)
    audio_playlists = []

    for i, (idx, lang) in enumerate(audio_streams):
        plist = f"audio_{i}.m3u8"
        audio_playlists.append((plist, lang))
        audio_cmd = [
            "ffmpeg", "-y", "-i", video_url,
            "-map", f"0:{idx}",
            "-c:a", "aac",
            "-ac", "2",
            "-vn",
            "-f", "hls",
            "-hls_time", "6",
            "-hls_list_size", "0",
            "-hls_segment_filename", f"{out_dir}/a{i}_%05d.ts",
            f"{out_dir}/{plist}"
        ]
        subprocess.run(audio_cmd, check=True)

    # 3️⃣ Master playlist
    with open(master, "w") as m:
        m.write("#EXTM3U\n#EXT-X-VERSION:3\n\n")
        # audio tracks
        for i, (plist, lang) in enumerate(audio_playlists):
            m.write(
                f'#EXT-X-MEDIA:TYPE=AUDIO,'
                f'GROUP-ID="audio",'
                f'NAME="{lang}",'
                f'DEFAULT={"YES" if i==0 else "NO"},'
                f'AUTOSELECT=YES,'
                f'URI="{plist}"\n'
            )
        # video
        m.write(
            '\n#EXT-X-STREAM-INF:BANDWIDTH=6000000,CODECS="avc1.4d401f,mp4a.40.2",AUDIO="audio"\n'
            'video.m3u8\n'
        )

@app.route("/convert", methods=["POST"])
def convert():
    data = request.get_json(silent=True)
    video_url = data.get("url")
    if not video_url:
        return jsonify({"error": "Missing URL"}), 400

    stream_id = hashlib.md5(video_url.encode()).hexdigest()
    out_dir = os.path.join(HLS_DIR, stream_id)
    master = os.path.join(out_dir, "master.m3u8")
    os.makedirs(out_dir, exist_ok=True)

    # Start background thread if master playlist does not exist
    if not os.path.exists(master):
        Thread(target=hls_worker, args=(video_url, out_dir), daemon=True).start()

    # Return HLS link immediately
    return jsonify({
        "status": "success",
        "hls_link": f"{request.host_url}static/streams/{stream_id}/master.m3u8"
    })

@app.route("/static/streams/<stream_id>/<path:filename>")
def serve(stream_id, filename):
    directory = os.path.join(HLS_DIR, stream_id)
    resp = send_from_directory(directory, filename)
    resp.headers["Access-Control-Allow-Origin"] = "*"
    if filename.endswith(".m3u8"):
        resp.headers["Content-Type"] = "application/vnd.apple.mpegurl"
    elif filename.endswith(".ts"):
        resp.headers["Content-Type"] = "video/MP2T"
    return resp

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
