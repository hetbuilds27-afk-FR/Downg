from flask import Flask, render_template, request, jsonify, send_file
import yt_dlp
import os
import uuid
import threading
import traceback

app = Flask(__name__)

# ---------------- SETTINGS ----------------

DOWNLOAD_FOLDER = "downloads"

if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER)

download_progress = {}

# If ffmpeg is not on your system PATH, set the full path to its folder here.
# Example: r"C:\ffmpeg\bin"
FFMPEG_LOCATION = None  # e.g. r"C:\ffmpeg\bin"

# ---------------- HOME PAGE ----------------

@app.route("/")
def home():
    return render_template("index.html")

# ---------------- DOWNLOAD API ----------------

@app.route("/download", methods=["POST"])
def download():

    data = request.json
    url = data.get("url")

    if not url:
        return jsonify({
            "success": False,
            "error": "No URL provided"
        })

    download_id = str(uuid.uuid4())

    download_progress[download_id] = {
        "progress": 0,
        "status": "Starting...",
        "filename": "",
        "title": ""
    }

    thread = threading.Thread(
        target=download_audio,
        args=(url, download_id)
    )

    thread.start()

    return jsonify({
        "success": True,
        "download_id": download_id
    })

# ---------------- DOWNLOAD FUNCTION ----------------

def download_audio(url, download_id):

    def progress_hook(d):

        if d['status'] == 'downloading':

            total = d.get('total_bytes') or d.get('total_bytes_estimate')
            downloaded = d.get('downloaded_bytes', 0)

            if total:

                percent = int(downloaded / total * 100)

                download_progress[download_id]["progress"] = percent

                download_progress[download_id]["status"] = (
                    f"Downloading... {percent}%"
                )

        elif d['status'] == 'finished':

            download_progress[download_id]["progress"] = 100

            download_progress[download_id]["status"] = (
                "Converting to MP3..."
            )

    try:

        # ---------------- GET TITLE FIRST ----------------

        with yt_dlp.YoutubeDL({'quiet': True}) as ydl:

            info = ydl.extract_info(url, download=False)

            title = info.get("title", "Unknown Song")

            download_progress[download_id]["title"] = title

        # ---------------- DOWNLOAD ----------------

        output_template = os.path.join(
            DOWNLOAD_FOLDER,
            '%(title)s [%(id)s].%(ext)s'
        )

        ydl_opts = {

            'format': 'bestaudio/best',

            'outtmpl': output_template,

            'progress_hooks': [progress_hook],

            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],

            'quiet': False,
            'no_warnings': False,

            'geo_bypass': True,

            'ignoreerrors': False,
        }

        if FFMPEG_LOCATION:
            ydl_opts['ffmpeg_location'] = FFMPEG_LOCATION

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:

            info = ydl.extract_info(url, download=True)

            if info is None:
                raise RuntimeError("yt-dlp returned no info — download failed.")

            original_file = ydl.prepare_filename(info)

            mp3_file = (
                os.path.splitext(original_file)[0]
                + ".mp3"
            )

            if not os.path.exists(mp3_file):
                raise RuntimeError(
                    f"MP3 file was not created at expected path: {mp3_file}. "
                    f"This usually means ffmpeg is not installed or not on PATH. "
                    f"Set FFMPEG_LOCATION at the top of this file to your ffmpeg "
                    f"bin folder if it's installed but not on PATH."
                )

            download_progress[download_id]["filename"] = mp3_file

        download_progress[download_id]["status"] = "Completed"

    except Exception as e:

        traceback.print_exc()

        download_progress[download_id]["status"] = (
            f"Error: {str(e)}"
        )

# ---------------- PROGRESS API ----------------

@app.route("/progress/<download_id>")
def progress(download_id):

    return jsonify(
        download_progress.get(download_id, {})
    )

# ---------------- FILE DOWNLOAD ----------------

@app.route("/file/<download_id>")
def get_file(download_id):

    data = download_progress.get(download_id)

    if not data:
        return "Invalid download ID"

    file_path = data.get("filename")

    if not file_path:
        return "File not ready"

    if not os.path.exists(file_path):
        return "File not found"

    return send_file(
        file_path,
        as_attachment=True
    )

# ---------------- RUN SERVER ----------------

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )