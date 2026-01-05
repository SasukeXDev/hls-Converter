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
    
    stream_id = hashlib.md5(video_url.encode()).hexdigest()
    output_path = os.path.join(HLS_OUTPUT_DIR, stream_id)
    playlist_file = os.path.join(output_path, 'index.m3u8')
    
    os.makedirs(output_path, exist_ok=True)
    base_server_url = request.host_url.rstrip('/').replace('http://', 'https://')

    if not os.path.exists(playlist_file):
        # NEW FFMPEG STRATEGY: 
        # 1. Map all video and audio.
        # 2. We use -sn to DISCARD subtitles initially to ensure the stream starts.
        #    (Many HLS players crash on subtitle conversion issues).
        # 3. We use -movflags +faststart for remote link efficiency.
        
        cmd = [
            'ffmpeg', '-hide_banner', '-loglevel', 'error',
            '-reconnect', '1', '-reconnect_streamed', '1', '-reconnect_delay_max', '5',
            '-i', video_url,
            '-map', '0:v:0',           # Map 1st video
            '-map', '0:a',             # Map ALL audio
            '-c:v', 'copy',             # Don't re-encode video
            '-c:a', 'aac',              # Audio to AAC (Standard for HLS)
            '-sn',                      # STRIP SUBTITLES (To prevent the crash you are seeing)
            '-f', 'hls', 
            '-hls_time', '10', 
            '-hls_list_size', '0',
            '-hls_segment_filename', os.path.join(output_path, 'seg_%03d.ts'),
            playlist_file
        ]
        
        subprocess.Popen(cmd)

        # WAIT logic: Give FFmpeg 2 seconds to create the file before replying
        # This prevents the 404 error on the very first request.
        timeout = 5 
        while not os.path.exists(playlist_file) and timeout > 0:
            time.sleep(1)
            timeout -= 1

    if os.path.exists(playlist_file):
        return jsonify({
            "status": "success",
            "hls_link": f"{base_server_url}/static/streams/{stream_id}/index.m3u8"
        }), 200
    else:
        return jsonify({"status": "error", "message": "FFmpeg failed to start stream"}), 500

@app.route('/static/streams/<path:filename>')
def custom_static(filename):
    response = send_from_directory(HLS_OUTPUT_DIR, filename)
    response.headers.add("Access-Control-Allow-Origin", "*")
    return response

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
