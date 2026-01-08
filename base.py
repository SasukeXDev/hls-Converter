import os
import subprocess
import hashlib
import time
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HLS_OUTPUT_DIR = os.path.join(BASE_DIR, "static", "streams")
os.makedirs(HLS_OUTPUT_DIR, exist_ok=True)

@app.route('/convert', methods=['POST', 'OPTIONS'])
def convert():
    if request.method == 'OPTIONS':
        return jsonify({"status": "ok"}), 200

    data = request.get_json()
    video_url = data.get('url')
    if not video_url:
        return jsonify({"status": "error", "message": "Missing URL"}), 400

    stream_id = hashlib.md5(video_url.encode()).hexdigest()
    output_path = os.path.join(HLS_OUTPUT_DIR, stream_id)
    master_playlist = os.path.join(output_path, "master.m3u8")

    os.makedirs(output_path, exist_ok=True)
    base_server_url = request.host_url.rstrip('/')

    if not os.path.exists(master_playlist):

        # 1️⃣ VIDEO ONLY HLS
        subprocess.Popen([
            "ffmpeg", "-y",
            "-i", video_url,
            "-map", "0:v:0",
            "-c:v", "copy",
            "-an",
            "-f", "hls",
            "-hls_time", "10",
            "-hls_list_size", "0",
            "-hls_playlist_type", "vod"
            "-hls_segment_filename", f"{output_path}/v_%03d.ts",
            f"{output_path}/video.m3u8"
        ])

        # 2️⃣ EXTRACT ALL AUDIO TRACKS
        probe = subprocess.check_output([
            "ffprobe", "-v", "error",
            "-select_streams", "a",
            "-show_entries", "stream=index",
            "-of", "csv=p=0",
            video_url
        ]).decode().strip().splitlines()

        audio_playlists = []

        for i, stream_index in enumerate(probe):
            audio_playlist = f"audio_{i}.m3u8"
            audio_playlists.append(audio_playlist)

            subprocess.Popen([
                "ffmpeg", "-y",
                "-i", video_url,
                "-map", f"0:{stream_index}",
                "-c:a", "aac",
                "-vn",
                "-f", "hls",
                "-hls_time", "10",
                "-hls_list_size", "0",
                "-hls_segment_filename", f"{output_path}/a{i}_%03d.ts",
                f"{output_path}/{audio_playlist}"
            ])



        # Extract language names
        audio_languages = []
        for stream in info.get("streams", []):
            lang = stream.get("tags", {}).get("language", "").lower()
            if lang.startswith("en"):
                audio_languages.append("English")
            elif lang.startswith("hi"):
                audio_languages.append("Hindi")
            else:
                audio_languages.append("Audio")  # fallback



        

        # 3️⃣ MASTER PLAYLIST

        with open(master_playlist, "w") as m3u8:
            m3u8.write("#EXTM3U\n")
            m3u8.write("#EXT-X-VERSION:3\n\n")

            for i, (a, lang_name) in enumerate(zip(audio_playlists, audio_languages)):
                m3u8.write(
                    f'#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="audio",NAME="{lang_name}",'
                    f'DEFAULT={"YES" if i == 0 else "NO"},AUTOSELECT=YES,URI="{a}"\n'
                )

            m3u8.write(
                '\n#EXT-X-STREAM-INF:BANDWIDTH=8000000,'
                'CODECS="avc1.640028,mp4a.40.2",AUDIO="audio"\n'
                'video.m3u8\n'
            )


        # wait for file creation
        for _ in range(5):
            if os.path.exists(master_playlist):
                break
            time.sleep(1)

    if os.path.exists(master_playlist):
        return jsonify({
            "status": "success",
            "hls_link": f"{base_server_url}/static/streams/{stream_id}/master.m3u8"
        })

    return jsonify({"status": "error", "message": "Stream failed"}), 500


@app.route('/static/streams/<path:filename>')
def custom_static(filename):
    response = send_from_directory(HLS_OUTPUT_DIR, filename)
    response.headers.add("Access-Control-Allow-Origin", "*")
    response.headers.add("Content-Type", "application/vnd.apple.mpegurl")
    return response


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
